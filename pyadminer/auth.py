from functools import wraps
from typing import Optional

from flask import Response, current_app, request


def check_app_basic_auth() -> Optional[Response]:
    """If PYADMINER_AUTH_* is set, require HTTP Basic Auth. Returns 401 response or None."""
    user = current_app.config.get("PYADMINER_AUTH_USERNAME", "")
    password = current_app.config.get("PYADMINER_AUTH_PASSWORD", "")
    if not user:
        return None

    auth = request.authorization
    if auth and auth.username == user and auth.password == password:
        return None

    return Response(
        "Unauthorized",
        401,
        {"WWW-Authenticate": 'Basic realm="PyAdminer"'},
    )


def require_app_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        resp = check_app_basic_auth()
        if resp:
            return resp
        return f(*args, **kwargs)

    return decorated
