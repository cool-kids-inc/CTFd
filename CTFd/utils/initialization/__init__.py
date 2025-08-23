import datetime
import logging
import os
import sys

from flask import abort, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from CTFd.cache import clear_user_recent_ips
from CTFd.exceptions import UserNotFoundException, UserTokenExpiredException
from CTFd.exceptions.email import UserResetPasswordTokenInvalidException
from CTFd.models import Tracking, db
from CTFd.utils import config, get_app_config, get_config, import_in_progress, markdown
from CTFd.utils.config import (
    can_send_mail,
    ctf_logo,
    ctf_name,
    ctf_theme,
    integrations,
    is_setup,
)
from CTFd.utils.config.pages import get_pages
from CTFd.utils.dates import isoformat, unix_time, unix_time_millis, unix_time_to_utc
from CTFd.utils.events import EventManager, RedisEventManager
from CTFd.utils.humanize.words import pluralize
from CTFd.utils.modes import generate_account_url, get_mode_as_word
from CTFd.utils.plugins import (
    get_configurable_plugins,
    get_menubar_plugins,
    get_registered_admin_scripts,
    get_registered_admin_stylesheets,
    get_registered_scripts,
    get_registered_stylesheets,
)
from CTFd.utils.security.auth import login_user, logout_user, lookup_user_token
from CTFd.utils.security.csrf import generate_nonce
from CTFd.utils.security.email import (
    generate_password_reset_token,
    verify_reset_password_token,
)
from CTFd.utils.user import (
    authed,
    get_current_team_attrs,
    get_current_user_attrs,
    get_current_user_recent_ips,
    get_ip,
    get_locale,
    is_admin,
)
from CTFd.models import Admins, Pages, db
from CTFd.utils import get_config, set_config
from CTFd.utils.uploads import upload_file
from CTFd.utils.email import (
    DEFAULT_PASSWORD_RESET_BODY,
    DEFAULT_PASSWORD_RESET_SUBJECT,
    DEFAULT_SUCCESSFUL_REGISTRATION_EMAIL_BODY,
    DEFAULT_SUCCESSFUL_REGISTRATION_EMAIL_SUBJECT,
    DEFAULT_USER_CREATION_EMAIL_BODY,
    DEFAULT_USER_CREATION_EMAIL_SUBJECT,
    DEFAULT_VERIFICATION_EMAIL_BODY,
    DEFAULT_VERIFICATION_EMAIL_SUBJECT,
)
from CTFd.constants.config import ConfigTypes
from CTFd.constants.themes import DEFAULT_THEME

def setup_ctf(args):
    # General
    ctf_name = args.get("ctf_name")
    ctf_description = args.get("ctf_description")
    user_mode = args.get("user_mode")
    set_config("ctf_name", ctf_name)
    set_config("ctf_description", ctf_description)
    set_config("user_mode", user_mode)

    # Settings
    challenge_visibility = args.get("challenge_visibility")
    account_visibility = args.get("account_visibility")
    score_visibility = args.get("score_visibility")
    registration_visibility = args.get("registration_visibility")
    verify_emails = args.get("verify_emails")
    social_shares = args.get("social_shares")
    team_size = args.get("team_size")

    # Style
    ctf_logo = args.get("ctf_logo")
    if ctf_logo:
        f = upload_file(file=ctf_logo)
        set_config("ctf_logo", f.location)

    ctf_small_icon = args.get("ctf_small_icon")
    if ctf_small_icon:
        f = upload_file(file=ctf_small_icon)
        set_config("ctf_small_icon", f.location)

    theme = args.get("ctf_theme", DEFAULT_THEME)
    set_config("ctf_theme", theme)
    theme_color = args.get("theme_color")
    theme_header = get_config("theme_header")
    if theme_color and bool(theme_header) is False:
        # Uses {{ and }} to insert curly braces while using the format method
        css = (
            '<style id="theme-color">\n'
            ":root {{--theme-color: {theme_color};}}\n"
            ".navbar{{background-color: var(--theme-color) !important;}}\n"
            ".jumbotron{{background-color: var(--theme-color) !important;}}\n"
            "</style>\n"
        ).format(theme_color=theme_color)
        set_config("theme_header", css)

    # DateTime
    start = args.get("start")
    end = args.get("end")
    set_config("start", start)
    set_config("end", end)
    set_config("freeze", None)

    # Administration
    name = args.get("name")
    email = args.get("email")
    password = args.get("password")

    admin = Admins(
        name=name, email=email, password=password, type="admin", hidden=True
    )

    # Create an empty index page
    page = Pages(title=ctf_name, route="index", content="", draft=False)

    # Upload banner
    default_ctf_banner_location = url_for("views.themes", path="img/logo.png")
    ctf_banner = args.get("ctf_banner")
    if ctf_banner:
        f = upload_file(file=ctf_banner, page_id=page.id)
        default_ctf_banner_location = url_for("views.files", path=f.location)
        set_config("ctf_banner", f.location)

    # Splice in our banner
    index = f"""<div class="row">
<div class="col-md-6 offset-md-3">
<img class="w-100 mx-auto d-block" style="max-width: 500px;padding: 50px;padding-top: 14vh;" src="{default_ctf_banner_location}" />
<h3 class="text-center">
    <p>A cool CTF platform from <a href="https://ctfd.io">ctfd.io</a></p>
    <p>Follow us on social media:</p>
    <a href="https://twitter.com/ctfdio"><i class="fab fa-twitter fa-2x" aria-hidden="true"></i></a>&nbsp;
    <a href="https://facebook.com/ctfdio"><i class="fab fa-facebook fa-2x" aria-hidden="true"></i></a>&nbsp;
    <a href="https://github.com/ctfd"><i class="fab fa-github fa-2x" aria-hidden="true"></i></a>
</h3>
<br>
<h4 class="text-center">
    <a href="admin">Click here</a> to login and setup your CTF
</h4>
</div>
</div>"""
    page.content = index

    # Visibility
    set_config(ConfigTypes.CHALLENGE_VISIBILITY, challenge_visibility)
    set_config(ConfigTypes.REGISTRATION_VISIBILITY, registration_visibility)
    set_config(ConfigTypes.SCORE_VISIBILITY, score_visibility)
    set_config(ConfigTypes.ACCOUNT_VISIBILITY, account_visibility)

    # Verify emails
    set_config("verify_emails", verify_emails)

    # Social shares
    set_config("social_shares", social_shares)

    # Team Size
    set_config("team_size", team_size)

    set_config("mail_server", None)
    set_config("mail_port", None)
    set_config("mail_tls", None)
    set_config("mail_ssl", None)
    set_config("mail_username", None)
    set_config("mail_password", None)
    set_config("mail_useauth", None)

    # Set up default emails
    set_config("verification_email_subject", DEFAULT_VERIFICATION_EMAIL_SUBJECT)
    set_config("verification_email_body", DEFAULT_VERIFICATION_EMAIL_BODY)

    set_config(
        "successful_registration_email_subject",
        DEFAULT_SUCCESSFUL_REGISTRATION_EMAIL_SUBJECT,
    )
    set_config(
        "successful_registration_email_body",
        DEFAULT_SUCCESSFUL_REGISTRATION_EMAIL_BODY,
    )

    set_config(
        "user_creation_email_subject", DEFAULT_USER_CREATION_EMAIL_SUBJECT
    )
    set_config("user_creation_email_body", DEFAULT_USER_CREATION_EMAIL_BODY)

    set_config("password_reset_subject", DEFAULT_PASSWORD_RESET_SUBJECT)
    set_config("password_reset_body", DEFAULT_PASSWORD_RESET_BODY)

    set_config(
        "password_change_alert_subject",
        "Password Change Confirmation for {ctf_name}",
    )
    set_config(
        "password_change_alert_body",
        (
            "Your password for {ctf_name} has been changed.\n\n"
            "If you didn't request a password change you can reset your password here: {url}"
        ),
    )

    set_config("setup", True)

    try:
        db.session.add(admin)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

    try:
        db.session.add(page)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

    return admin


def init_cli(app):
    from CTFd.cli import _cli

    app.register_blueprint(_cli, cli_group=None)


def init_template_filters(app):
    app.jinja_env.filters["markdown"] = markdown
    app.jinja_env.filters["unix_time"] = unix_time
    app.jinja_env.filters["unix_time_millis"] = unix_time_millis
    app.jinja_env.filters["unix_time_to_utc"] = unix_time_to_utc
    app.jinja_env.filters["isoformat"] = isoformat
    app.jinja_env.filters["pluralize"] = pluralize


def init_template_globals(app):
    from CTFd.constants import JINJA_ENUMS  # noqa: I001
    from CTFd.constants.assets import Assets
    from CTFd.constants.config import Configs
    from CTFd.constants.languages import Languages
    from CTFd.constants.plugins import Plugins
    from CTFd.constants.sessions import Session
    from CTFd.constants.static import Static
    from CTFd.constants.teams import Team
    from CTFd.constants.users import User
    from CTFd.forms import Forms
    from CTFd.utils.config.visibility import (
        accounts_visible,
        challenges_visible,
        registration_visible,
        scores_visible,
    )
    from CTFd.utils.countries import get_countries, lookup_country_code
    from CTFd.utils.countries.geoip import lookup_ip_address, lookup_ip_address_city

    app.jinja_env.globals.update(config=config)
    app.jinja_env.globals.update(get_pages=get_pages)
    app.jinja_env.globals.update(can_send_mail=can_send_mail)
    app.jinja_env.globals.update(get_ctf_name=ctf_name)
    app.jinja_env.globals.update(get_ctf_logo=ctf_logo)
    app.jinja_env.globals.update(get_ctf_theme=ctf_theme)
    app.jinja_env.globals.update(get_menubar_plugins=get_menubar_plugins)
    app.jinja_env.globals.update(get_configurable_plugins=get_configurable_plugins)
    app.jinja_env.globals.update(get_registered_scripts=get_registered_scripts)
    app.jinja_env.globals.update(get_registered_stylesheets=get_registered_stylesheets)
    app.jinja_env.globals.update(
        get_registered_admin_scripts=get_registered_admin_scripts
    )
    app.jinja_env.globals.update(
        get_registered_admin_stylesheets=get_registered_admin_stylesheets
    )
    app.jinja_env.globals.update(get_config=get_config)
    app.jinja_env.globals.update(generate_account_url=generate_account_url)
    app.jinja_env.globals.update(get_countries=get_countries)
    app.jinja_env.globals.update(lookup_country_code=lookup_country_code)
    app.jinja_env.globals.update(lookup_ip_address=lookup_ip_address)
    app.jinja_env.globals.update(lookup_ip_address_city=lookup_ip_address_city)
    app.jinja_env.globals.update(accounts_visible=accounts_visible)
    app.jinja_env.globals.update(challenges_visible=challenges_visible)
    app.jinja_env.globals.update(registration_visible=registration_visible)
    app.jinja_env.globals.update(scores_visible=scores_visible)
    app.jinja_env.globals.update(get_mode_as_word=get_mode_as_word)
    app.jinja_env.globals.update(integrations=integrations)
    app.jinja_env.globals.update(authed=authed)
    app.jinja_env.globals.update(is_admin=is_admin)
    app.jinja_env.globals.update(get_current_user_attrs=get_current_user_attrs)
    app.jinja_env.globals.update(get_current_team_attrs=get_current_team_attrs)
    app.jinja_env.globals.update(get_ip=get_ip)
    app.jinja_env.globals.update(get_locale=get_locale)
    app.jinja_env.globals.update(Assets=Assets)
    app.jinja_env.globals.update(Configs=Configs)
    app.jinja_env.globals.update(Plugins=Plugins)
    app.jinja_env.globals.update(Session=Session)
    app.jinja_env.globals.update(Static=Static)
    app.jinja_env.globals.update(Forms=Forms)
    app.jinja_env.globals.update(User=User)
    app.jinja_env.globals.update(Team=Team)
    app.jinja_env.globals.update(Languages=Languages)

    # Add in JinjaEnums
    # The reason this exists is that on double import, JinjaEnums are not reinitialized
    # Thus, if you try to create two jinja envs (e.g. during testing), sometimes
    # an Enum will not be available to Jinja.
    # Instead we can just directly grab them from the persisted global dictionary.
    for k, v in JINJA_ENUMS.items():
        # .update() can't be used here because it would use the literal value k
        app.jinja_env.globals[k] = v


def init_logs(app):
    logger_submissions = logging.getLogger("submissions")
    logger_logins = logging.getLogger("logins")
    logger_registrations = logging.getLogger("registrations")

    logger_submissions.setLevel(logging.INFO)
    logger_logins.setLevel(logging.INFO)
    logger_registrations.setLevel(logging.INFO)

    log_dir = app.config["LOG_FOLDER"]
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logs = {
        "submissions": os.path.join(log_dir, "submissions.log"),
        "logins": os.path.join(log_dir, "logins.log"),
        "registrations": os.path.join(log_dir, "registrations.log"),
    }

    try:
        for log in logs.values():
            if not os.path.exists(log):
                open(log, "a").close()

        submission_log = logging.handlers.RotatingFileHandler(
            logs["submissions"], maxBytes=10485760, backupCount=5
        )
        login_log = logging.handlers.RotatingFileHandler(
            logs["logins"], maxBytes=10485760, backupCount=5
        )
        registration_log = logging.handlers.RotatingFileHandler(
            logs["registrations"], maxBytes=10485760, backupCount=5
        )

        logger_submissions.addHandler(submission_log)
        logger_logins.addHandler(login_log)
        logger_registrations.addHandler(registration_log)
    except IOError:
        pass

    stdout = logging.StreamHandler(stream=sys.stdout)

    logger_submissions.addHandler(stdout)
    logger_logins.addHandler(stdout)
    logger_registrations.addHandler(stdout)

    logger_submissions.propagate = 0
    logger_logins.propagate = 0
    logger_registrations.propagate = 0


def init_events(app):
    if app.config.get("CACHE_TYPE") == "redis":
        app.events_manager = RedisEventManager()
    elif app.config.get("CACHE_TYPE") == "filesystem":
        app.events_manager = EventManager()
    else:
        app.events_manager = EventManager()
    app.events_manager.listen()


def init_request_processors(app):
    @app.url_defaults
    def inject_theme(endpoint, values):
        if "theme" not in values and app.url_map.is_endpoint_expecting(
            endpoint, "theme"
        ):
            values["theme"] = ctf_theme()

    @app.before_request
    def needs_setup():
        if import_in_progress():
            if request.endpoint == "admin.import_ctf":
                return
            else:
                return "Import currently in progress", 403
        if is_setup() is False:
            if request.endpoint in (
                "views.setup",
                "views.integrations",
                "views.themes",
                "views.files",
                "views.healthcheck",
                "views.robots",
                "api.init_setup",
            ):
                return
            else:
                return redirect(url_for("views.setup"))

    @app.before_request
    def tracker():
        if request.endpoint == "views.themes":
            return

        if import_in_progress():
            if request.endpoint == "admin.import_ctf":
                return
            else:
                return "Import currently in progress", 403

        if authed():
            user_ips = get_current_user_recent_ips()
            ip = get_ip()

            track = None
            if ip not in user_ips or request.method in (
                "POST",
                "PATCH",
                "DELETE",
            ):
                track = Tracking.query.filter_by(
                    ip=get_ip(), user_id=session["id"]
                ).first()

                if track:
                    track.date = datetime.datetime.utcnow()
                else:
                    track = Tracking(ip=get_ip(), user_id=session["id"])
                    db.session.add(track)

            if track:
                try:
                    db.session.commit()
                except (InvalidRequestError, IntegrityError):
                    db.session.rollback()
                    db.session.close()
                    logout_user()
                else:
                    clear_user_recent_ips(user_id=session["id"])

    @app.before_request
    def banned():
        if request.endpoint == "views.themes":
            return

        if authed():
            user = get_current_user_attrs()
            team = get_current_team_attrs()

            if user and user.banned:
                return (
                    render_template(
                        "errors/403.html", error="You have been banned from this CTF"
                    ),
                    403,
                )

            if team and team.banned:
                return (
                    render_template(
                        "errors/403.html",
                        error="Your team has been banned from this CTF",
                    ),
                    403,
                )

    @app.before_request
    def change_password():
        if request.endpoint in ("views.themes", "auth.logout", "auth.reset_password"):
            return

        if authed():
            user = get_current_user_attrs()

            if user and user.change_password:
                reset_token = session.get("reset_password")
                valid = False

                if reset_token:
                    try:
                        verify_reset_password_token(reset_token)
                        valid = True
                    except UserResetPasswordTokenInvalidException:
                        session.pop("reset_password")
                        valid = False

                if not valid:
                    reset_token = generate_password_reset_token(user.email)
                    session["reset_password"] = reset_token

                return redirect(url_for("auth.reset_password", data=reset_token))

    @app.before_request
    def tokens():
        if request.endpoint == "api.init_setup":
            return
        token = request.headers.get("Authorization")
        if token and (
            request.mimetype == "application/json"
            # Specially allow multipart/form-data for file uploads
            or (
                request.endpoint == "api.files_files_list"
                and request.method == "POST"
                and request.mimetype == "multipart/form-data"
            )
        ):
            try:
                token_type, token = token.split(" ", 1)
                user = lookup_user_token(token)
            except UserNotFoundException:
                abort(401)
            except UserTokenExpiredException:
                abort(401, description="Your access token has expired")
            except Exception:
                abort(401)
            else:
                login_user(user)

    @app.before_request
    def csrf():
        try:
            func = app.view_functions[request.endpoint]
        except KeyError:
            abort(404)
        if hasattr(func, "_bypass_csrf"):
            return
        if request.headers.get("Authorization"):
            return
        if not session.get("nonce"):
            session["nonce"] = generate_nonce()
        if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            if request.content_type == "application/json":
                if session["nonce"] != request.headers.get("CSRF-Token"):
                    abort(403)
            if request.content_type != "application/json":
                if session["nonce"] != request.form.get("nonce"):
                    abort(403)

    @app.after_request
    def response_headers(response):
        response.headers["Cross-Origin-Opener-Policy"] = get_app_config(
            "CROSS_ORIGIN_OPENER_POLICY", default="same-origin-allow-popups"
        )
        return response

    application_root = app.config.get("APPLICATION_ROOT")
    if application_root != "/":

        @app.before_request
        def force_subdirectory_redirect():
            if request.path.startswith(application_root) is False:
                return redirect(
                    application_root + request.script_root + request.full_path
                )

        app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {application_root: app})
