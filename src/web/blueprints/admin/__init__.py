"""
Admin Blueprint für Datenschutz-Rechtsprechung API mit Authentication
Dashboard mit Statistiken und System-Monitoring
"""

from flask import Blueprint, render_template, request, abort, flash, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Erstelle das Haupt-Admin-Blueprint
admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="templates")


def localhost_only(f):
    """Decorator für localhost-only Zugriff (legacy - nur noch für Fallback)"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Nur von localhost erlauben
        if request.remote_addr not in ["127.0.0.1", "localhost", "::1"]:
            abort(403)  # Forbidden
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """Decorator für Admin-only Routes"""

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("Sie haben keine Berechtigung für diesen Bereich.", "danger")
            logger.warning(f"Unauthorized admin access attempt by user: {current_user.username}")
            return redirect(url_for("public.index"))
        return f(*args, **kwargs)

    return decorated_function


@admin_bp.route("/")
@admin_bp.route("/dashboard")
@admin_required  # Ersetze localhost_only mit admin_required
def dashboard():
    """Admin Dashboard Hauptseite - jetzt mit Authentication"""
    try:
        from .services import stats

        dashboard_stats = stats.get_dashboard_stats()

        return render_template(
            "admin/dashboard.html", stats=dashboard_stats, active_page="dashboard"
        )
    except Exception as e:
        logger.error(f"Fehler beim Laden des Admin Dashboards: {str(e)}")
        return render_template(
            "admin/dashboard.html",
            stats={
                "decisions": {"total": 0, "today": 0, "this_week": 0},
                "sources": {"gdprhub": 0, "openlegaldata": 0},
                "articles": [],
                "courts": [],
                "system": {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0},
            },
            active_page="dashboard",
            error_message="Statistiken konnten nicht geladen werden",
        )


# Registriere die Sub-Module
from .routes import dashboard as dashboard_routes
from .routes import system
from .routes import claude

admin_bp.register_blueprint(dashboard_routes.bp)
admin_bp.register_blueprint(system.bp)
admin_bp.register_blueprint(claude.bp)
