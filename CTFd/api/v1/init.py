import secrets
from flask import request, current_app
from flask_restx import Namespace, Resource

from CTFd.utils.config import is_setup
from CTFd.utils.initialization import setup_ctf
from CTFd.models import Users
from CTFd.utils import validators

init_namespace = Namespace("init", description="Endpoint to initialize CTFd")


@init_namespace.route("/setup", methods=["POST"])
class Setup(Resource):
    def post(self):
        if not current_app.config.get("INIT_API_ENABLED"):
            return {"success": False, "message": "API is not enabled"}, 403

        auth_header = request.headers.get("Authorization", "")
        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != "Bearer":
            return {"success": False, "message": "Invalid token format"}, 401
        token = parts[1]

        if not secrets.compare_digest(token, current_app.config.get("INIT_API_TOKEN", "")):
            return {"success": False, "message": "Invalid token"}, 401

        if is_setup():
            return {"success": False, "message": "Already configured"}, 409

        data = request.get_json()

        errors = []
        # Administration
        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()

        name_len = len(name) == 0
        names = (
            Users.query.add_columns(Users.name, Users.id)
            .filter_by(name=name)
            .first()
        )
        emails = (
            Users.query.add_columns(Users.email, Users.id)
            .filter_by(email=email)
            .first()
        )
        pass_short = len(password) == 0
        pass_long = len(password) > 128
        valid_email = validators.validate_email(email)
        team_name_email_check = validators.validate_email(name)

        if not valid_email:
            errors.append("Please enter a valid email address")
        if names:
            errors.append("That user name is already taken")
        if team_name_email_check is True:
            errors.append("Your user name cannot be an email address")
        if emails:
            errors.append("That email has already been used")
        if pass_short:
            errors.append("Pick a longer password")
        if pass_long:
            errors.append("Pick a shorter password")
        if name_len:
            errors.append("Pick a longer user name")

        if len(errors) > 0:
            return {"success": False, "errors": errors}, 400

        setup_ctf(args=data)

        return {"success": True}
