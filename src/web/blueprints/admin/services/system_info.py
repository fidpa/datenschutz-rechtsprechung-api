"""
System Information Service für Datenschutz-Rechtsprechung API
Sammelt detaillierte System-Informationen
"""

import logging
import os
import sys
import platform
import psutil
from datetime import datetime

try:
    import pkg_resources
except ImportError:
    pkg_resources = None

logger = logging.getLogger(__name__)


def get_system_info():
    """
    Sammelt umfassende System-Informationen

    Returns:
        dict: System-Details
    """
    try:
        info = {
            # Python-Umgebung
            "python_version": sys.version,
            "python_path": sys.executable,
            # Betriebssystem
            "os": platform.system(),
            "os_version": platform.version(),
            "platform": platform.platform(),
            "hostname": platform.node(),
            # Hardware
            "cpu_count": psutil.cpu_count(),
            "cpu_name": platform.processor(),
            "total_memory_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            # Prozess-Info
            "process_id": os.getpid(),
            "start_time": datetime.fromtimestamp(psutil.Process().create_time()).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            # Wichtige Packages für Datenschutz-Rechtsprechung API
            "packages": get_important_packages(),
            # Verzeichnisse
            "working_dir": os.getcwd(),
            "logs_dir": os.path.abspath("logs/"),
            "scripts_dir": os.path.abspath("scripts/"),
            # Datenschutz-Rechtsprechung API spezifisch
            "api_url": "http://localhost:8000",
            "web_url": "http://localhost:5001",
            "redis_url": "redis://localhost:6379",
            "postgres_status": check_postgres_connection(),
        }

        return info
    except Exception as e:
        logger.error(f"Fehler beim Sammeln der System-Info: {str(e)}")
        return {
            "python_version": sys.version,
            "os": sys.platform,
            "error": "Einige Informationen konnten nicht geladen werden",
        }


def get_live_status():
    """
    Liefert Live-System-Status für AJAX-Updates

    Returns:
        dict: Aktuelle System-Metriken
    """
    try:
        process = psutil.Process()

        return {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "percent": psutil.cpu_percent(interval=1),
                "per_core": psutil.cpu_percent(percpu=True, interval=1),
            },
            "memory": {
                "percent": psutil.virtual_memory().percent,
                "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
                "process_mb": round(process.memory_info().rss / (1024**2), 2),
            },
            "disk": {
                "percent": psutil.disk_usage("/").percent,
                "free_gb": round(psutil.disk_usage("/").free / (1024**3), 2),
            },
            "network": get_network_stats(),
            "services": check_services_status(),
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Live-Status: {str(e)}")
        return {"error": "Status konnte nicht abgerufen werden"}


def get_important_packages():
    """Liste wichtiger installierter Packages für Datenschutz-Rechtsprechung API"""
    important = [
        "fastapi",
        "uvicorn",
        "flask",
        "waitress",
        "sqlalchemy",
        "psycopg2-binary",
        "redis",
        "celery",
        "httpx",
        "beautifulsoup4",
        "spacy",
        "pdfplumber",
        "openpyxl",
    ]
    packages = {}

    if pkg_resources:
        for package in important:
            try:
                version = pkg_resources.get_distribution(package).version
                packages[package] = version
            except:
                packages[package] = "nicht installiert"
    else:
        # Fallback ohne pkg_resources
        packages = {pkg: "Version unbekannt" for pkg in important}

    return packages


def get_network_stats():
    """Netzwerk-Statistiken"""
    try:
        stats = psutil.net_io_counters()
        return {
            "bytes_sent_mb": round(stats.bytes_sent / (1024**2), 2),
            "bytes_recv_mb": round(stats.bytes_recv / (1024**2), 2),
        }
    except:
        return {"bytes_sent_mb": 0, "bytes_recv_mb": 0}


def check_postgres_connection():
    """Prüft PostgreSQL-Verbindung"""
    try:
        from src.database import get_session

        with get_session() as session:
            session.execute("SELECT 1")
            return "Verbunden"
    except:
        return "Nicht verbunden"


def check_services_status():
    """Prüft Status der wichtigen Services"""
    services = {}

    # FastAPI
    try:
        import httpx

        response = httpx.get("http://localhost:8000/health", timeout=2)
        services["fastapi"] = "online" if response.status_code == 200 else "offline"
    except:
        services["fastapi"] = "offline"

    # Redis
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379)
        r.ping()
        services["redis"] = "online"
    except:
        services["redis"] = "offline"

    # PostgreSQL
    services["postgres"] = "online" if check_postgres_connection() == "Verbunden" else "offline"

    return services
