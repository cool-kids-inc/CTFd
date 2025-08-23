import secrets
from flask import request, current_app
from flask_restx import Namespace, Resource

from CTFd.utils.config import is_setup
from CTFd.utils.initialization import setup_ctf
from CTFd.models import Users
from CTFd.utils.validators.users import validate_admin_user

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

        errors = validate_admin_user(
            name=data.get("name"),
            email=data.get("email"),
            password=data.get("password"),
        )

        if len(errors) > 0:
            return {"success": False, "errors": errors}, 400

        setup_ctf(args=data)

        return {"success": True}
