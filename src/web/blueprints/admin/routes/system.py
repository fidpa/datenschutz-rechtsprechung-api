"""
Admin System Information Routes für Datenschutz-Rechtsprechung API mit Authentication
System-Informationen und -Verwaltung
"""

import logging
import sys
from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import login_required, current_user
from functools import wraps
from ..services import system_info

logger = logging.getLogger(__name__)

bp = Blueprint("admin_system", __name__, url_prefix="/system")


def admin_required(f):
    """Decorator für Admin-only Routes"""

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            if request.is_json:
                return jsonify({"error": "Admin-Berechtigung erforderlich"}), 403
            else:
                abort(403)
        return f(*args, **kwargs)

    return decorated_function


def localhost_only(f):
    """Decorator für localhost-only Zugriff (legacy)"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.remote_addr not in ["127.0.0.1", "localhost", "::1"]:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


@bp.route("/")
@admin_required  # Ersetzt localhost_only
def system_overview():
    """
    System-Übersicht mit Server-Informationen
    """
    try:
        # Sammle System-Informationen
        info = system_info.get_system_info()

        return render_template("admin/system.html", system_info=info, active_page="system")
    except Exception as e:
        logger.error(f"Fehler beim Laden der System-Info: {str(e)}")
        return render_template(
            "admin/system.html",
            system_info={
                "python_version": sys.version,
                "os": sys.platform,
                "error": "Einige Informationen konnten nicht geladen werden",
            },
            active_page="system",
        )


@bp.route("/status")
@admin_required  # Ersetzt localhost_only
def system_status():
    """
    AJAX-Endpoint für Live-System-Status
    """
    try:
        status = system_info.get_live_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des System-Status: {str(e)}")
        return jsonify({"error": "Status konnte nicht abgerufen werden"}), 500


@bp.route("/redis-stats")
@admin_required  # Ersetzt localhost_only
def redis_stats():
    """
    Redis Cache Statistiken
    """
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, decode_responses=True)

        info = r.info()
        stats = {
            "connected": True,
            "used_memory_human": info.get("used_memory_human", "N/A"),
            "connected_clients": info.get("connected_clients", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
            "db0_keys": info.get("db0", {}).get("keys", 0)
            if isinstance(info.get("db0"), dict)
            else 0,
        }
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Redis-Stats-Fehler: {str(e)}")
        return jsonify({"connected": False, "error": str(e)}), 200


@bp.route("/db-stats")
@admin_required  # Ersetzt localhost_only
def db_stats():
    """
    PostgreSQL Datenbank Statistiken
    """
    try:
        from src.database import get_session

        with get_session() as session:
            # Anzahl Entscheidungen
            result = session.execute("SELECT COUNT(*) FROM decisions")
            total_decisions = result.scalar()

            # DB-Größe
            result = session.execute(
                """
                SELECT pg_database_size(current_database()) as size,
                       pg_size_pretty(pg_database_size(current_database())) as size_pretty
            """
            )
            db_info = result.fetchone()

            stats = {
                "connected": True,
                "total_decisions": total_decisions,
                "database_size": db_info.size_pretty if db_info else "N/A",
                "database_size_bytes": db_info.size if db_info else 0,
            }
            return jsonify(stats)
    except Exception as e:
        logger.error(f"DB-Stats-Fehler: {str(e)}")
        return jsonify({"connected": False, "error": str(e)}), 200
