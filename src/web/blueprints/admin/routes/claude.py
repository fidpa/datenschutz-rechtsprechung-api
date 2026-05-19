"""
Claude Code Monitoring API Endpoints für Admin Dashboard.
Integration der CLI-Commands in Web-Interface.
"""

import logging
import subprocess
import json
import sys
import glob
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from functools import wraps

logger = logging.getLogger(__name__)

# Blueprint erstellen
bp = Blueprint("claude_monitoring", __name__)


def admin_required(f):
    """Decorator für Admin-only API Routes"""

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({"error": "Admin-Berechtigung erforderlich"}), 403
        return f(*args, **kwargs)

    return decorated_function


@bp.route("/api/claude/analysis", methods=["GET", "POST"])
@admin_required
def claude_analysis():
    """
    Trigger Claude Analysis und return JSON-Ergebnisse.
    GET: Return cached analysis
    POST: Trigger new analysis
    """
    try:
        if request.method == "POST":
            # Trigger neue Analysis
            script_path = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "admin.py"

            result = subprocess.run(
                [sys.executable, str(script_path), "claude-analysis", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return (
                    jsonify(
                        {"success": False, "error": f"Analysis fehlgeschlagen: {result.stderr}"}
                    ),
                    500,
                )

        # Lade neueste Analysis-Daten (cached oder gerade generiert)
        analysis_pattern = "data/logs/claude_analysis/daily_analysis_*.json"
        analysis_files = sorted(glob.glob(analysis_pattern), reverse=True)

        if not analysis_files:
            return jsonify({"success": False, "error": "Keine Analysis-Daten gefunden"}), 404

        with open(analysis_files[0], "r", encoding="utf-8") as f:
            analysis_data = json.load(f)

        return jsonify(
            {
                "success": True,
                "data": analysis_data,
                "generated_at": analysis_data.get("metadata", {}).get("generated_at"),
                "file": analysis_files[0],
            }
        )

    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Analysis-Timeout nach 60 Sekunden"}), 504
    except Exception as e:
        logger.error(f"Claude Analysis API Fehler: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/claude/health", methods=["GET"])
@admin_required
def claude_health():
    """
    Aktueller System Health Score basierend auf Claude Events.
    """
    try:
        script_path = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "admin.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "claude-health", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return (
                jsonify(
                    {"success": False, "error": f"Health-Check fehlgeschlagen: {result.stderr}"}
                ),
                500,
            )

        # Parse JSON Output
        health_data = json.loads(result.stdout.strip())

        return jsonify(
            {"success": True, "data": health_data, "timestamp": datetime.now().isoformat()}
        )

    except json.JSONDecodeError as e:
        return jsonify({"success": False, "error": f"Invalid JSON response: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Claude Health API Fehler: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/claude/logs", methods=["GET"])
@admin_required
def claude_logs():
    """
    Kritische Events aus Claude Logging System.
    Query-Parameter: priority, component, hours
    """
    try:
        # Parse Query-Parameter
        priority = request.args.get("priority", "critical")
        component = request.args.get("component", "")
        hours = int(request.args.get("hours", 24))

        # Build CLI command
        script_path = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "admin.py"
        cmd = [
            sys.executable,
            str(script_path),
            "claude-logs",
            "--format",
            "json",
            "--hours",
            str(hours),
        ]

        if priority:
            cmd.extend(["--priority", priority])
        if component:
            cmd.extend(["--component", component])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return (
                jsonify({"success": False, "error": f"Log-Query fehlgeschlagen: {result.stderr}"}),
                500,
            )

        # Parse JSON Output
        events_data = json.loads(result.stdout.strip()) if result.stdout.strip() else []

        return jsonify(
            {
                "success": True,
                "data": events_data,
                "count": len(events_data),
                "filters": {"priority": priority, "component": component, "hours": hours},
                "timestamp": datetime.now().isoformat(),
            }
        )

    except (ValueError, json.JSONDecodeError) as e:
        return (
            jsonify({"success": False, "error": f"Invalid parameters or response: {str(e)}"}),
            400,
        )
    except Exception as e:
        logger.error(f"Claude Logs API Fehler: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/claude/performance", methods=["GET"])
@admin_required
def claude_performance():
    """
    Performance-Trends und Component-Statistics.
    """
    try:
        # Lade neueste Analysis-Daten
        analysis_pattern = "data/logs/claude_analysis/daily_analysis_*.json"
        analysis_files = sorted(glob.glob(analysis_pattern), reverse=True)

        if not analysis_files:
            return jsonify({"success": False, "error": "Keine Performance-Daten gefunden"}), 404

        with open(analysis_files[0], "r", encoding="utf-8") as f:
            analysis_data = json.load(f)

        performance_data = analysis_data.get("performance_analysis", {})

        # Strukturiere Daten für Chart.js
        component_stats = performance_data.get("component_statistics", {})
        chart_data = {
            "components": list(component_stats.keys()),
            "mean_times": [stats.get("mean", 0) for stats in component_stats.values()],
            "p95_times": [stats.get("p95", 0) for stats in component_stats.values()],
            "counts": [stats.get("count", 0) for stats in component_stats.values()],
        }

        return jsonify(
            {
                "success": True,
                "data": {
                    "chart_data": chart_data,
                    "performance_analysis": performance_data,
                    "insights": performance_data.get("insights", []),
                    "slowest_operations": performance_data.get("slowest_operations", []),
                },
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Claude Performance API Fehler: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/claude/status", methods=["GET"])
@admin_required
def claude_status():
    """
    Kombinierter Status-Endpoint für Dashboard-Overview.
    """
    try:
        # Sammle alle wichtigen Metriken
        status_data = {}

        # 1. Health Score
        try:
            script_path = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "admin.py"
            health_result = subprocess.run(
                [sys.executable, str(script_path), "claude-health", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if health_result.returncode == 0:
                status_data["health"] = json.loads(health_result.stdout.strip())
        except:
            status_data["health"] = {"health_score": 0, "status": "unknown"}

        # 2. Recent Critical Events Count
        try:
            logs_result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "claude-logs",
                    "--format",
                    "json",
                    "--priority",
                    "critical",
                    "--hours",
                    "24",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if logs_result.returncode == 0:
                events = (
                    json.loads(logs_result.stdout.strip()) if logs_result.stdout.strip() else []
                )
                status_data["critical_events_24h"] = len(events)
            else:
                status_data["critical_events_24h"] = 0
        except:
            status_data["critical_events_24h"] = 0

        # 3. Analysis Freshness
        try:
            analysis_pattern = "data/logs/claude_analysis/daily_analysis_*.json"
            analysis_files = sorted(glob.glob(analysis_pattern), reverse=True)

            if analysis_files:
                # Check file modification time
                file_mtime = Path(analysis_files[0]).stat().st_mtime
                last_analysis = datetime.fromtimestamp(file_mtime)
                hours_old = (datetime.now() - last_analysis).total_seconds() / 3600
                status_data["last_analysis_hours_ago"] = round(hours_old, 1)
                status_data["analysis_fresh"] = hours_old < 25  # Less than 25 hours old
            else:
                status_data["last_analysis_hours_ago"] = None
                status_data["analysis_fresh"] = False
        except:
            status_data["last_analysis_hours_ago"] = None
            status_data["analysis_fresh"] = False

        # 4. System-Status zusammenfassen
        health_score = status_data.get("health", {}).get("health_score", 0)
        if health_score >= 80:
            overall_status = "healthy"
        elif health_score >= 60:
            overall_status = "degraded"
        elif health_score >= 30:
            overall_status = "unhealthy"
        else:
            overall_status = "critical"

        status_data["overall_status"] = overall_status
        status_data["timestamp"] = datetime.now().isoformat()

        return jsonify({"success": True, "data": status_data})

    except Exception as e:
        logger.error(f"Claude Status API Fehler: {str(e)}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": str(e),
                    "data": {
                        "overall_status": "unknown",
                        "health": {"health_score": 0, "status": "unknown"},
                        "critical_events_24h": 0,
                        "analysis_fresh": False,
                    },
                }
            ),
            500,
        )
