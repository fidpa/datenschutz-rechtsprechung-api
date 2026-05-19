"""
Admin Dashboard Routes für Datenschutz-Rechtsprechung API mit Authentication
Hauptübersicht mit Statistiken und CLI-Integration
"""

import logging
import subprocess
from flask import Blueprint, request, abort, jsonify
from flask_login import login_required, current_user
from functools import wraps
from ..services import stats

logger = logging.getLogger(__name__)

# Blueprint ohne url_prefix - wird vom Parent übernommen
bp = Blueprint("admin_dashboard", __name__)


def admin_required(f):
    """Decorator für Admin-only API Routes"""

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({"error": "Admin-Berechtigung erforderlich"}), 403
        return f(*args, **kwargs)

    return decorated_function


def localhost_only(f):
    """Decorator für localhost-only Zugriff (legacy - nur noch für Fallback)"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.remote_addr not in ["127.0.0.1", "localhost", "::1"]:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


@bp.route("/api/stats")
@admin_required  # Ersetzt localhost_only
def api_stats():
    """
    JSON API-Endpoint für Dashboard-Statistiken
    Wird von JavaScript für Live-Updates genutzt
    """
    try:
        dashboard_stats = stats.get_dashboard_stats()
        return jsonify(dashboard_stats), 200
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren der Stats: {str(e)}")
        return jsonify({"error": "Stats konnten nicht geladen werden"}), 500


@bp.route("/api/cli/export", methods=["POST"])
@admin_required  # Ersetzt localhost_only
def trigger_export():
    """
    Trigger CLI Export über subprocess
    """
    try:
        export_type = request.json.get("type", "excel")

        # Führe CLI-Befehl aus
        if export_type == "excel":
            cmd = ["python", "scripts/admin.py", "export", "--format", "excel"]
        elif export_type == "json":
            cmd = ["python", "scripts/admin.py", "export", "--format", "json"]
        else:
            return jsonify({"error": "Ungültiger Export-Typ"}), 400

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            # Parse output für Dateinamen
            output_lines = result.stdout.strip().split("\n")
            filename = output_lines[-1] if output_lines else "export.xlsx"
            return (
                jsonify(
                    {
                        "success": True,
                        "filename": filename,
                        "message": f"Export erfolgreich: {filename}",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify({"success": False, "error": result.stderr or "Export fehlgeschlagen"}),
                500,
            )

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Export-Timeout"}), 504
    except Exception as e:
        logger.error(f"Export-Fehler: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/cli/crawl", methods=["POST"])
@admin_required  # Ersetzt localhost_only
def trigger_crawl():
    """
    Trigger CLI Crawler über subprocess
    """
    try:
        source = request.json.get("source", "gdprhub")

        # Führe Crawler im Hintergrund aus
        cmd = ["python", "scripts/run_crawler.py", source]

        # Starte im Hintergrund ohne zu warten
        subprocess.Popen(cmd)

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Crawler für {source} gestartet (läuft im Hintergrund)",
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Crawler-Start-Fehler: {str(e)}")
        return jsonify({"error": str(e)}), 500
