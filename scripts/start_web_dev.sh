#!/bin/bash
# Start Flask Web-UI in Development Mode

echo "🔧 Datenschutz-Rechtsprechung API Web-UI - Development Mode"
echo "==========================================="

# Projekt-Root ermitteln
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Virtual Environment aktivieren
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✅ Virtual Environment aktiviert"
else
    echo "❌ Virtual Environment nicht gefunden!"
    echo "   Führe aus: python3 -m venv venv && pip install -r requirements.txt"
    exit 1
fi

# FastAPI Status prüfen
echo "🔍 Prüfe FastAPI Backend..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ FastAPI läuft auf Port 8000"
else
    echo "⚠️  FastAPI nicht erreichbar auf Port 8000"
    echo "   Starte mit: ./venv/bin/uvicorn src.api.main:app --reload"
fi

# Waitress Development Server starten
echo ""
echo "🚀 Starte Waitress Development Server auf Port 5001..."
echo "====================================================="
export FLASK_ENV=development
export FLASK_DEBUG=1
export FASTAPI_BASE_URL=http://localhost:8000
export WEB_UI_PORT=5001

python src/web/development_server.py