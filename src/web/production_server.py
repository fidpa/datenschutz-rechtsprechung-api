#!/usr/bin/env python3
"""Production Server mit Waitress für Datenschutz-Rechtsprechung API Web-UI"""

import os
import sys
from pathlib import Path

# Projekt-Root zu Python-Path hinzufügen
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from waitress import serve
from src.web.app import create_app
import structlog

logger = structlog.get_logger()

if __name__ == "__main__":
    # Production Environment
    os.environ.setdefault("FLASK_ENV", "production")
    os.environ.setdefault("FASTAPI_BASE_URL", "http://localhost:8000")

    app = create_app("production")
    port = int(os.environ.get("WEB_UI_PORT", 5001))  # Production Port

    logger.info(
        "web_ui_starting", port=port, server="waitress", threads=8, environment="production"
    )

    print(f"🚀 Datenschutz-Rechtsprechung API Web-UI (Waitress Production): http://localhost:{port}")
    print(f"📊 FastAPI Backend: http://localhost:8000")
    print(f"📝 Swagger Docs: http://localhost:8000/docs")
    print(f"⚡ Server: Waitress mit 8 Threads")
    print(f"📈 Optimiert für: Parallele Anfragen & Excel-Exporte")
    print("\nDrücke Ctrl+C zum Beenden")

    try:
        serve(
            app,
            host="127.0.0.1",
            port=port,
            threads=8,  # Optimiert für parallele Anfragen
            channel_timeout=300,  # 5 Min für große Exporte
            max_request_body_size=10485760,  # 10MB
            cleanup_interval=30,  # Memory cleanup alle 30s
            connection_limit=200,  # Max 200 gleichzeitige Verbindungen
            expose_tracebacks=False,
        )  # Keine sensiblen Daten in Prod
    except KeyboardInterrupt:
        print("\n🛑 Web-UI wird beendet...")
        print("✅ Shutdown abgeschlossen")
