# src/web/blueprints/export.py
"""
Minimaler Export-Blueprint für Flask Web-UI.
Nutzt die existierende FastAPI Export-Funktionalität.
"""

from flask import Blueprint, request, Response, redirect, url_for, flash, current_app
import logging

logger = logging.getLogger(__name__)

# Blueprint erstellen
export_bp = Blueprint("export", __name__, url_prefix="/export")


@export_bp.route("/excel")
def export_excel():
    """
    Excel-Export - leitet zur FastAPI weiter und streamt die Antwort.

    Die FastAPI hat bereits vollständige Excel-Export-Funktionalität
    mit deutschen Spalten, Formatierung etc.
    """
    try:
        # Query-Parameter sammeln
        params = {}

        # Such-Query
        if request.args.get("q"):
            params["q"] = request.args.get("q")

        # Filter
        if request.args.get("court"):
            params["court"] = request.args.get("court")
        if request.args.get("source"):
            params["source"] = request.args.get("source")
        if request.args.get("date_from"):
            params["date_from"] = request.args.get("date_from")
        if request.args.get("date_to"):
            params["date_to"] = request.args.get("date_to")
        if request.args.get("gdpr_article"):
            params["gdpr_article"] = request.args.get("gdpr_article")

        # Limit (max 1000 für Performance)
        params["limit"] = min(int(request.args.get("limit", 500)), 1000)

        logger.info(f"Excel-Export angefordert mit Parametern: {params}")

        # Von FastAPI holen
        response = current_app.api_client.export_excel(**params)

        # Als Download zurückgeben
        return Response(
            response.content,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": response.headers.get(
                    "Content-Disposition", "attachment; filename=dsr_decisions.xlsx"
                )
            },
        )

    except Exception as e:
        logger.error(f"Excel-Export fehlgeschlagen: {str(e)}")
        flash(f"Export fehlgeschlagen: {str(e)}", "error")
        return redirect(request.referrer or url_for("public.search"))


@export_bp.route("/csv")
def export_csv():
    """CSV-Export - vorerst deaktiviert."""
    flash("CSV-Export wird in einer späteren Version verfügbar sein.", "info")
    return redirect(url_for("export.export_excel", **request.args))
