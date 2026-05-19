#!/usr/bin/env python3
"""Development Server mit Waitress für Datenschutz-Rechtsprechung API Web-UI"""

import os
import sys
from pathlib import Path

# Projekt-Root zu Python-Path hinzufügen
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from waitress import serve
from src.web.app import create_app
import structlog
import logging

# Development Logging aktivieren
logging.basicConfig(level=logging.DEBUG)
logger = structlog.get_logger()

if __name__ == "__main__":
    # Development Environment
    os.environ.setdefault("FLASK_ENV", "development")
    os.environ.setdefault("FLASK_DEBUG", "True")
    os.environ.setdefault("FASTAPI_BASE_URL", "http://localhost:8000")

    app = create_app("development")
    port = int(os.environ.get("WEB_UI_PORT", 5001))

    logger.info(
        "web_ui_starting", port=port, server="waitress", threads=4, environment="development"
    )

    print(
        f"🔧 Datenschutz-Rechtsprechung API Web-UI (Waitress Development): http://localhost:{port}"
    )
    print(f"📊 FastAPI Backend: http://localhost:8000")
    print(f"📝 Swagger Docs: http://localhost:8000/docs")
    print(f"⚡ Server: Waitress mit 4 Threads (Development)")
    print(f"🐛 Debug: Aktiviert")
    print("\nDrücke Ctrl+C zum Beenden")

    try:
        serve(
            app,
            host="127.0.0.1",
            port=port,
            threads=4,  # Weniger Threads für Development
            channel_timeout=120,  # 2 Min für Development
            max_request_body_size=10485760,  # 10MB
            cleanup_interval=60,  # Weniger aggressiv
            connection_limit=100,  # Weniger Connections
            expose_tracebacks=True,  # Debug: Tracebacks anzeigen
            ident="datenschutz-rechtsprechung-api-Dev",
        )  # Server-Identifikation
    except KeyboardInterrupt:
        print("\n🛑 Development Server wird beendet...")
        print("✅ Shutdown abgeschlossen")
