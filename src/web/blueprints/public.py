"""
Public Blueprint für Datenschutz-Rechtsprechung API Web-UI.
Enthält alle öffentlichen Routes (Suche, Detail-Ansicht).
"""

from flask import Blueprint, render_template, request, current_app, flash
from src.web.services.api_client import APIClientError
import logging

logger = logging.getLogger(__name__)

# Blueprint erstellen
public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def index():
    """Startseite mit Such-Box und Statistiken."""
    try:
        # Statistiken von FastAPI holen
        stats = current_app.api_client.get_stats()

        # Daten für Template vorbereiten
        template_data = {
            "total_decisions": stats.get("overview", {}).get("total_decisions", 0),
            "total_courts": len(stats.get("by_court", [])),
            "total_sources": len(stats.get("by_source", [])),
            "stats": stats,
        }

        return render_template("public/index.html", **template_data)

    except APIClientError as e:
        logger.error(f"API error in index: {str(e)}")

        # Spezifische Fehlermeldung für Connection Refused
        if "Connection refused" in str(e):
            flash(
                "⚠️ Backend-Server nicht erreichbar. Bitte starten Sie die FastAPI mit: uvicorn src.api.main:app --reload",
                "danger",
            )
        else:
            flash("Fehler beim Laden der Statistiken", "warning")

        # Fallback-Daten
        return render_template(
            "public/index.html", total_decisions=0, total_courts=0, total_sources=0, stats=None
        )


@public_bp.route("/search")
def search():
    """Kombinierte Such- und Ergebnisseite."""
    # Query-Parameter extrahieren
    query = request.args.get("q", "").strip()

    # Sichere Pagination-Verarbeitung
    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
        elif page > 10000:  # Sinnvolles Maximum
            page = 10000
    except (ValueError, TypeError):
        page = 1  # Fallback bei ungültigen Werten

    # Einfache Filter (erstmal nur die wichtigsten)
    court = request.args.get("court", "").strip()
    source = request.args.get("source", "").strip()

    results = None

    # Nur API aufrufen wenn eine Suche durchgeführt wurde
    if query or court or source:
        try:
            # API-Call für Suche
            search_params = {"query": query, "page": page}

            if court:
                search_params["court"] = court
            if source:
                search_params["source"] = source

            results = current_app.api_client.search(**search_params)

        except APIClientError as e:
            logger.error(f"API error in search: {str(e)}")

            # Spezifische Fehlermeldung für Connection Refused
            if "Connection refused" in str(e):
                flash(
                    "⚠️ Backend-Server nicht erreichbar. Bitte starten Sie die FastAPI mit: uvicorn src.api.main:app --reload",
                    "danger",
                )
            else:
                flash(f"Fehler bei der Suche: {str(e)}", "error")

            results = {"items": [], "total": 0, "page": 1, "pages": 0}

    return render_template(
        "public/search.html",
        query=query,
        results=results,
        court=court,
        source=source,
        current_page=page,
    )


@public_bp.route("/decision/<string:decision_id>")
def decision_detail(decision_id):
    """Einzelne Entscheidung anzeigen."""
    try:
        decision = current_app.api_client.get_decision(decision_id)
        return render_template("public/decision.html", decision=decision)

    except APIClientError as e:
        logger.error(f"API error getting decision {decision_id}: {str(e)}")
        flash("Entscheidung nicht gefunden", "error")
        return render_template("public/decision.html", decision=None)
