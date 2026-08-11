#!/bin/bash
# Start Flask Web-UI with Waitress (Production)

echo "🚀 Datenschutz-Rechtsprechung API Web-UI - Production Mode (Waitress)"
echo "===================================================="

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

# Waitress prüfen
if ! python -c "import waitress" 2>/dev/null; then
    echo "❌ Waitress nicht installiert!"
    echo "   Führe aus: pip install waitress==3.0.0"
    exit 1
fi

# FastAPI Status prüfen
echo "🔍 Prüfe FastAPI Backend..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ FastAPI läuft auf Port 8000"
else
    echo "⚠️  FastAPI nicht erreichbar auf Port 8000"
    echo "   Starte mit: ./venv/bin/uvicorn src.api.main:app"
fi

# Waitress Production Server starten
echo ""
echo "⚡ Starte Waitress Production Server auf Port 5001..."
echo "====================================================="
export FLASK_ENV=production
export FASTAPI_BASE_URL=http://localhost:8000
export WEB_UI_PORT=5001

python src/web/production_server.py