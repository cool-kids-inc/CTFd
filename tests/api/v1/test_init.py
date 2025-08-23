from CTFd.utils import get_config
from CTFd.utils.config import is_setup
from tests.helpers import create_ctfd, destroy_ctfd, gen_user


def test_api_setup_post_not_enabled():
    """
    Test that `POST /api/v1/init/setup` fails if the API is not enabled
    """
    app = create_ctfd(setup=False)
    with app.app_context():
        with app.test_client() as client:
            r = client.post("/api/v1/init/setup")
            assert r.status_code == 403
    destroy_ctfd(app)


def test_api_setup_post_invalid_token():
    """
    Test that `POST /api/v1/init/setup` fails with an invalid token
    """
    app = create_ctfd(setup=False)
    with app.app_context():
        app.config["INIT_API_ENABLED"] = True
        app.config["INIT_API_TOKEN"] = "valid_token"
        with app.test_client() as client:
            r = client.post(
                "/api/v1/init/setup",
                headers={"Authorization": "Bearer invalid_token"},
                json={},
            )
            assert r.status_code == 401
    destroy_ctfd(app)


def test_api_setup_post_already_configured():
    """
    Test that `POST /api/v1/init/setup` fails if CTFd is already configured
    """
    app = create_ctfd(setup=True)
    with app.app_context():
        app.config["INIT_API_ENABLED"] = True
        app.config["INIT_API_TOKEN"] = "valid_token"
        with app.test_client() as client:
            r = client.post(
                "/api/v1/init/setup",
                headers={"Authorization": "Bearer valid_token"},
                json={},
            )
            assert r.status_code == 409
    destroy_ctfd(app)


def test_api_setup_post_success():
    """
    Test that `POST /api/v1/init/setup` succeeds with valid data
    """
    app = create_ctfd(setup=False)
    with app.app_context():
        app.config["INIT_API_ENABLED"] = True
        app.config["INIT_API_TOKEN"] = "valid_token"
        with app.test_client() as client:
            data = {
                "ctf_name": "Test CTF",
                "ctf_description": "This is a test CTF",
                "user_mode": "users",
                "name": "admin",
                "email": "admin@test.com",
                "password": "password",
            }
            r = client.post(
                "/api/v1/init/setup",
                headers={"Authorization": "Bearer valid_token"},
                json=data,
            )
            assert r.status_code == 200
            assert get_config("ctf_name") == "Test CTF"
            assert is_setup() is True
    destroy_ctfd(app)
