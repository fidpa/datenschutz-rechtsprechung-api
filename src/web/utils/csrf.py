"""
CSRF Protection ohne Flask-WTF
Wiederverwendbares CSRF-Utility
"""
import secrets
from flask import session, request, abort
from functools import wraps
import logging

logger = logging.getLogger(__name__)


def generate_csrf_token():
    """Generate CSRF token"""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


def validate_csrf_token(token):
    """Validate CSRF token"""
    return token == session.get("_csrf_token")


def csrf_protect(f):
    """Decorator for CSRF protection on POST routes"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "POST":
            token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")

            if not token or not validate_csrf_token(token):
                logger.warning(f"CSRF token validation failed for {request.endpoint}")
                logger.warning(f"Expected: {session.get('_csrf_token')}, Got: {token}")
                abort(403)

        return f(*args, **kwargs)

    return decorated_function


def init_csrf(app):
    """Initialize CSRF protection"""
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def csrf_token_helper():
        """Ensure CSRF token is available in templates"""
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_hex(16)

    logger.info("CSRF protection initialized")
