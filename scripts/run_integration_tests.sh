#!/bin/bash
#
# Integration Test Runner für Datenschutz-Rechtsprechung API
# Führt umfassende Tests mit Docker-Umgebung durch
#

set -e  # Exit on error

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Konfiguration
TEST_COUNT=${1:-500}  # Standard: 500 Dokumente
TEST_SOURCE=${2:-openlegaldata}  # Standard: OpenLegalData
COMPOSE_FILE="docker-compose.test.yml"
REPORT_DIR="reports/$(date +%Y%m%d_%H%M%S)"

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Datenschutz-Rechtsprechung API - Integration Test Suite         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# 1. Vorbereitung
echo -e "${YELLOW}📦 Vorbereitung...${NC}"
mkdir -p "$REPORT_DIR"
mkdir -p data/cache
mkdir -p logs

# 2. Docker Environment starten
echo -e "${YELLOW}🐳 Starte Docker Test-Umgebung...${NC}"
docker-compose -f "$COMPOSE_FILE" down -v 2>/dev/null || true
docker-compose -f "$COMPOSE_FILE" up -d test-postgres test-redis

# Warte auf Services
echo -e "${YELLOW}⏳ Warte auf Services...${NC}"
for i in {1..30}; do
    if docker-compose -f "$COMPOSE_FILE" exec -T test-postgres pg_isready -U dsr_test_user >/dev/null 2>&1; then
        echo -e "${GREEN}✅ PostgreSQL bereit${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

for i in {1..10}; do
    if docker-compose -f "$COMPOSE_FILE" exec -T test-redis redis-cli ping >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Redis bereit${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

# 3. Datenbank initialisieren
echo -e "${YELLOW}🗄️ Initialisiere Test-Datenbank...${NC}"
export TEST_DATABASE_URL="postgresql://dsr_test_user:dsr_test_password@localhost:5433/dsr_test"
export DATABASE_URL="$TEST_DATABASE_URL"
python scripts/init_db.py

# 4. Unit Tests
echo -e "${YELLOW}🧪 Führe Unit-Tests aus...${NC}"
pytest tests/test_importers_optimized.py -v --tb=short --cov=src/importers --cov-report=html --cov-report=term

# 5. Integration Tests
echo -e "${YELLOW}🔗 Führe Integration-Tests aus...${NC}"
pytest tests/integration/test_real_import.py::TestRealDatabaseIntegration -v --tb=short

# 6. Performance Benchmarks
echo -e "${YELLOW}⚡ Führe Performance-Benchmarks aus...${NC}"
python tests/integration/test_real_import.py --benchmark

# 7. Praxis-Test mit echten Daten
echo -e "${YELLOW}🌍 Führe Praxis-Test mit ${TEST_COUNT} echten Dokumenten aus...${NC}"
python scripts/validate_import_quality.py \
    --source "$TEST_SOURCE" \
    --count "$TEST_COUNT" \
    --output-dir "$REPORT_DIR"

# 8. Memory Profiling (optional)
if [ "$RUN_MEMORY_PROFILE" = "true" ]; then
    echo -e "${YELLOW}💾 Führe Memory-Profiling aus...${NC}"
    mprof run python scripts/import_openlegaldata_dump.py --limit 1000 --dry-run
    mprof plot -o "$REPORT_DIR/memory_profile.png"
fi

# 9. Load Testing (optional)
if [ "$RUN_LOAD_TEST" = "true" ]; then
    echo -e "${YELLOW}🔥 Führe Load-Tests aus...${NC}"
    locust -f tests/load/test_import_load.py \
        --host=http://localhost:8000 \
        --users=10 \
        --spawn-rate=2 \
        --run-time=60s \
        --headless \
        --html="$REPORT_DIR/load_test.html"
fi

# 10. Ergebnisse sammeln
echo -e "${YELLOW}📊 Sammle Test-Ergebnisse...${NC}"

# Datenbank-Statistiken
echo -e "\n${BLUE}=== Datenbank-Statistiken ===${NC}"
docker-compose -f "$COMPOSE_FILE" exec -T test-postgres psql -U dsr_test_user -d dsr_test -c "
SELECT 
    COUNT(*) as total_decisions,
    COUNT(CASE WHEN gdpr_articles IS NOT NULL THEN 1 END) as with_gdpr,
    COUNT(CASE WHEN anonymization_applied = true THEN 1 END) as anonymized,
    AVG(LENGTH(full_text)) as avg_text_length
FROM decisions;
"

# Performance-Metriken
if [ -f "$REPORT_DIR/import_quality_report_"*.html ]; then
    echo -e "\n${BLUE}=== Quality Report ===${NC}"
    echo -e "${GREEN}✅ Report erstellt: ${REPORT_DIR}/import_quality_report_*.html${NC}"
fi

# Coverage Report
if [ -d "htmlcov" ]; then
    mv htmlcov "$REPORT_DIR/coverage"
    echo -e "${GREEN}✅ Coverage Report: ${REPORT_DIR}/coverage/index.html${NC}"
fi

# 11. Cleanup (optional)
if [ "$KEEP_CONTAINERS" != "true" ]; then
    echo -e "${YELLOW}🧹 Cleanup...${NC}"
    docker-compose -f "$COMPOSE_FILE" down -v
fi

# 12. Zusammenfassung
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║            ✅ Tests abgeschlossen!                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "📁 Reports gespeichert in: ${BLUE}${REPORT_DIR}${NC}"
echo ""
echo "Nächste Schritte:"
echo "  1. Report öffnen: open ${REPORT_DIR}/import_quality_report_*.html"
echo "  2. Coverage ansehen: open ${REPORT_DIR}/coverage/index.html"
echo "  3. Logs prüfen: tail -f logs/*.log"
echo ""

# Exit Code basierend auf Test-Ergebnissen
if [ -f "$REPORT_DIR/.test_failed" ]; then
    echo -e "${RED}⚠️ Einige Tests sind fehlgeschlagen${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Alle Tests erfolgreich${NC}"
    exit 0
fi