#!/bin/bash
# 🚀 Datenschutz-Rechtsprechung API - Start All Services
# Startet FastAPI Backend und Flask Web-UI gleichzeitig

set -e  # Bei Fehler abbrechen

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Projekt-Root ermitteln
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       🚀 Datenschutz-Rechtsprechung API System Start           ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""

# Virtual Environment prüfen
if [ ! -f "venv/bin/activate" ]; then
    echo -e "${RED}❌ Virtual Environment nicht gefunden!${NC}"
    echo -e "   Führe aus: python3 -m venv venv && pip install -r requirements.txt"
    exit 1
fi

source venv/bin/activate
echo -e "${GREEN}✅ Virtual Environment aktiviert${NC}"

# Docker-Services prüfen
echo -e "\n${YELLOW}🔍 Prüfe Docker-Services...${NC}"
if docker ps | grep -q "dsr.*postgres" && docker ps | grep -q "dsr.*redis"; then
    echo -e "${GREEN}✅ PostgreSQL und Redis laufen bereits${NC}"
else
    echo -e "${YELLOW}🐳 Starte Docker-Services...${NC}"
    docker-compose up -d postgres redis
    sleep 3
    echo -e "${GREEN}✅ Docker-Services gestartet${NC}"
fi

# Alte Prozesse beenden
echo -e "\n${YELLOW}🧹 Räume alte Prozesse auf...${NC}"
pkill -f "uvicorn src.api.main:app" 2>/dev/null || true
pkill -f "waitress-serve" 2>/dev/null || true
pkill -f "python src/web/production_server.py" 2>/dev/null || true
sleep 1

# FastAPI Backend starten
echo -e "\n${YELLOW}🎯 Starte FastAPI Backend (Port 8000)...${NC}"
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --log-level warning &
FASTAPI_PID=$!

# Warten bis FastAPI bereit ist
for i in {1..10}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ FastAPI läuft auf http://localhost:8000${NC}"
        break
    fi
    sleep 1
done

# Flask Web-UI starten
echo -e "\n${YELLOW}🌐 Starte Flask Web-UI (Port 5001)...${NC}"
export FLASK_ENV=production
export FASTAPI_BASE_URL=http://localhost:8000
export WEB_UI_PORT=5001

python src/web/production_server.py &
FLASK_PID=$!

# Warten bis Flask bereit ist
for i in {1..10}; do
    if curl -s http://localhost:5001/ > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Flask Web-UI läuft auf http://localhost:5001${NC}"
        break
    fi
    sleep 1
done

# Status-Übersicht
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          ✨ System erfolgreich gestartet!    ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📊 Web-UI:${NC}     http://localhost:5001"
echo -e "${GREEN}📚 API Docs:${NC}   http://localhost:8000/docs"
echo -e "${GREEN}🔍 Health:${NC}     http://localhost:8000/health"
echo ""
echo -e "${YELLOW}💡 Tipp:${NC} Drücke Ctrl+C zum sauberen Beenden"
echo ""

# Browser öffnen (nach 2 Sekunden)
(sleep 2 && open http://localhost:5001) &

# Graceful Shutdown bei Ctrl+C
cleanup() {
    echo -e "\n${YELLOW}🛑 Fahre System herunter...${NC}"
    
    # Prozesse beenden
    kill $FASTAPI_PID 2>/dev/null || true
    kill $FLASK_PID 2>/dev/null || true
    
    # Warten bis Prozesse beendet sind
    wait $FASTAPI_PID 2>/dev/null || true
    wait $FLASK_PID 2>/dev/null || true
    
    echo -e "${GREEN}✅ System sauber heruntergefahren${NC}"
    echo -e "${YELLOW}💡 Docker-Services laufen weiter (docker-compose down zum Stoppen)${NC}"
    exit 0
}

trap cleanup INT TERM

# Auf Prozesse warten
wait $FASTAPI_PID $FLASK_PID