# src/web/app.py
"""
Flask Application Factory für Datenschutz-Rechtsprechung API Web-UI mit Authentication.

Nutze die Server-Scripts zum Starten:
- Development: scripts/start_web_dev.sh
- Production: scripts/start_web_prod.sh
"""

from flask import Flask, request
from flask_login import LoginManager, current_user
from datetime import datetime, timedelta
import logging
import os

from src.web.config import config
from src.web.services.api_client import create_api_client
from src.web.models.user import AuthManager
from src.web.utils.csrf import init_csrf

# Claude Code Logging Integration
from src.logging.middleware.flask_middleware import setup_flask_logging

logger = logging.getLogger(__name__)


def create_app(config_name="development"):
    """
    Application Factory Pattern für Flask-App mit Authentication.

    Args:
        config_name: development, production, testing

    Returns:
        Flask Application Instance
    """
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Konfiguration laden
    app.config.from_object(config[config_name])

    # Enhanced Security Configuration
    app.config.update(
        {
            "SECRET_KEY": os.environ.get(
                "FLASK_SECRET_KEY", "dev-key-change-in-production-immediately"
            ),
            "SESSION_COOKIE_SECURE": config_name == "production",
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SAMESITE": "Lax",
            "PERMANENT_SESSION_LIFETIME": timedelta(hours=24),
            "SESSION_COOKIE_NAME": "dsr_session",
            "WTF_CSRF_ENABLED": False,  # We use our own CSRF protection
        }
    )

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Bitte melden Sie sich an, um fortzufahren."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID für Flask-Login"""
        return AuthManager.load_user(user_id)

    @login_manager.unauthorized_handler
    def unauthorized():
        """Handle unauthorized access"""
        from flask import redirect, url_for, flash

        # Store the attempted URL
        next_url = request.url if request.endpoint != "static" else None

        flash("Sie müssen sich anmelden, um diese Seite zu sehen.", "warning")
        return redirect(url_for("auth.login", next=next_url))

    # Initialize CSRF Protection
    init_csrf(app)

    # Initialize Claude Code Logging (Zero-Code-Change Monitoring)
    setup_flask_logging(app)

    # API-Client als Extension registrieren
    app.api_client = create_api_client(app.config)

    # Blueprints registrieren
    from src.web.blueprints.public import public_bp
    from src.web.blueprints.export import export_bp
    from src.web.blueprints.admin import admin_bp
    from src.web.blueprints.auth import auth_bp
    from src.web.blueprints.system import system_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(system_bp)

    # Security Headers
    @app.after_request
    def security_headers(response):
        """Add security headers"""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Content Security Policy (basic)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "font-src 'self' cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self' localhost:8000"
        )

        return response

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template

        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        from flask import render_template

        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal error: {error}")
        from flask import render_template

        return render_template("errors/500.html"), 500

    # Template filters and globals
    @app.template_filter("datetime")
    def datetime_filter(value, format="%d.%m.%Y %H:%M"):
        """Format datetime für deutsche Locale"""
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except:
                return value
        return value.strftime(format)

    @app.context_processor
    def inject_globals():
        """Inject global variables into templates"""
        return {
            "asset_version": os.environ.get("ASSET_VERSION", "1.0.0"),
            "app_name": "Datenschutz-Rechtsprechung API",
            "current_year": datetime.now().year,
            "current_user": current_user,  # Make sure current_user is available
        }

    # Health-Check Route
    @app.route("/health")
    def health():
        """Flask Health-Check mit Auth-Status."""
        try:
            # Teste FastAPI-Verbindung
            fastapi_healthy = app.api_client.test_connection()

            # Teste Auth-System
            auth_healthy = AuthManager.test_connection()

            return {
                "status": "healthy" if (fastapi_healthy and auth_healthy) else "degraded",
                "flask": "ok",
                "fastapi": "ok" if fastapi_healthy else "error",
                "auth": "ok" if auth_healthy else "error",
                "version": "1.0.0",
            }
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {"status": "error", "error": str(e)}, 500

    logger.info(f"Flask app created with authentication - config: {config_name}")
    return app
