from CTFd.models import Users
from CTFd.utils import validators


def validate_admin_user(name, email, password):
    errors = []
    name = name.strip()
    email = email.strip()
    password = password.strip()

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

    return errors
