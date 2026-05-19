"""
Stats Service für Datenschutz-Rechtsprechung API Admin Dashboard
Sammelt und bereitet Statistiken für das Dashboard auf
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from src.web.services.api_client import FastAPIClient

logger = logging.getLogger(__name__)


def get_dashboard_stats() -> Dict[str, Any]:
    """
    Hauptfunktion für Dashboard-Statistiken
    Sammelt alle relevanten Metriken für das Admin Dashboard
    """
    try:
        client = FastAPIClient()
        stats = {}

        # Entscheidungs-Statistiken
        try:
            decisions_stats = client.get("/api/v1/stats/")
            stats["decisions"] = {
                "total": decisions_stats.get("total_decisions", 0),
                "today": _get_today_count(client),
                "this_week": _get_week_count(client),
                "this_month": _get_month_count(client),
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Entscheidungs-Stats: {e}")
            stats["decisions"] = {"total": 0, "today": 0, "this_week": 0, "this_month": 0}

        # Quellen-Verteilung
        try:
            sources_data = client.get("/api/v1/stats/by-source")
            stats["sources"] = _process_sources(sources_data)
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Quellen-Stats: {e}")
            stats["sources"] = {"gdprhub": 0, "openlegaldata": 0}

        # Top DSGVO-Artikel
        try:
            articles_data = client.get("/api/v1/stats/gdpr-articles")
            stats["articles"] = _process_top_articles(articles_data, limit=10)
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der DSGVO-Artikel: {e}")
            stats["articles"] = []

        # Top Gerichte
        try:
            courts_data = client.get("/api/v1/stats/by-court")
            stats["courts"] = _process_top_courts(courts_data, limit=10)
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Gerichts-Stats: {e}")
            stats["courts"] = []

        # System-Informationen
        stats["system"] = _get_system_stats()

        # Letzte Aktivitäten
        stats["recent_activity"] = _get_recent_activity(client)

        # Qualitäts-Metriken
        stats["quality"] = _get_quality_metrics(client)

        return stats

    except Exception as e:
        logger.error(f"Kritischer Fehler beim Sammeln der Dashboard-Stats: {e}")
        return _get_default_stats()


def _get_today_count(client: FastAPIClient) -> int:
    """Anzahl der heutigen Entscheidungen"""
    try:
        today = datetime.now().date()
        response = client.get(f"/api/v1/decisions/?created_after={today}")
        return response.get("total", 0) if isinstance(response, dict) else 0
    except:
        return 0


def _get_week_count(client: FastAPIClient) -> int:
    """Anzahl der Entscheidungen dieser Woche"""
    try:
        week_ago = datetime.now() - timedelta(days=7)
        response = client.get(f"/api/v1/decisions/?created_after={week_ago.date()}")
        return response.get("total", 0) if isinstance(response, dict) else 0
    except:
        return 0


def _get_month_count(client: FastAPIClient) -> int:
    """Anzahl der Entscheidungen diesen Monat"""
    try:
        month_ago = datetime.now() - timedelta(days=30)
        response = client.get(f"/api/v1/decisions/?created_after={month_ago.date()}")
        return response.get("total", 0) if isinstance(response, dict) else 0
    except:
        return 0


def _process_sources(sources_data: List[Dict]) -> Dict[str, int]:
    """Verarbeitet Quellen-Daten für Chart"""
    result = {"gdprhub": 0, "openlegaldata": 0, "andere": 0}

    if not sources_data:
        return result

    for source in sources_data:
        source_name = source.get("source", "").lower()
        count = source.get("count", 0)

        if "gdprhub" in source_name:
            result["gdprhub"] += count
        elif "openlegaldata" in source_name:
            result["openlegaldata"] += count
        else:
            result["andere"] += count

    return result


def _process_top_articles(articles_data: List[Dict], limit: int = 10) -> List[Dict]:
    """Verarbeitet Top DSGVO-Artikel"""
    if not articles_data:
        return []

    processed = []
    for article in articles_data[:limit]:
        processed.append(
            {"article": article.get("gdpr_article", "Unbekannt"), "count": article.get("count", 0)}
        )

    return processed


def _process_top_courts(courts_data: List[Dict], limit: int = 10) -> List[Dict]:
    """Verarbeitet Top Gerichte"""
    if not courts_data:
        return []

    processed = []
    for court in courts_data[:limit]:
        court_name = court.get("court", "Unbekannt")
        # Kürze lange Gerichtsnamen
        if len(court_name) > 30:
            court_name = court_name[:27] + "..."

        processed.append({"court": court_name, "count": court.get("count", 0)})

    return processed


def _get_system_stats() -> Dict[str, Any]:
    """Sammelt System-Statistiken"""
    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(memory.percent, 1),
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "disk_percent": round(disk.percent, 1),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
        }
    except Exception as e:
        logger.error(f"Fehler beim Sammeln der System-Stats: {e}")
        return {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0}


def _get_recent_activity(client: FastAPIClient) -> List[Dict]:
    """Holt die letzten Aktivitäten"""
    try:
        # Hole die letzten 5 Entscheidungen
        response = client.get("/api/v1/decisions/?limit=5&sort=-created_at")

        if not response or "items" not in response:
            return []

        activities = []
        for decision in response["items"][:5]:
            activities.append(
                {
                    "type": "new_decision",
                    "title": decision.get("title", "Unbekannt")[:50],
                    "source": decision.get("source", "Unbekannt"),
                    "time": decision.get("created_at", ""),
                }
            )

        return activities
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Aktivitäten: {e}")
        return []


def _get_quality_metrics(client: FastAPIClient) -> Dict[str, Any]:
    """Holt Qualitäts-Metriken"""
    try:
        # Hole Anonymisierungs-Rate
        stats = client.get("/api/v1/stats/")

        total = stats.get("total_decisions", 0)
        anonymized = stats.get("anonymized_count", 0)

        return {
            "anonymization_rate": round((anonymized / total * 100) if total > 0 else 0, 1),
            "avg_quality_score": 3.5,  # Placeholder
            "extraction_success_rate": 85.0,  # Placeholder
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Qualitäts-Metriken: {e}")
        return {"anonymization_rate": 0, "avg_quality_score": 0, "extraction_success_rate": 0}


def _get_default_stats() -> Dict[str, Any]:
    """Gibt Standard-Stats zurück bei Fehlern"""
    return {
        "decisions": {"total": 0, "today": 0, "this_week": 0, "this_month": 0},
        "sources": {"gdprhub": 0, "openlegaldata": 0},
        "articles": [],
        "courts": [],
        "system": {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0},
        "recent_activity": [],
        "quality": {"anonymization_rate": 0, "avg_quality_score": 0, "extraction_success_rate": 0},
    }
