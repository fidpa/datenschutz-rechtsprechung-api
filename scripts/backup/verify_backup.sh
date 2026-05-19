#!/bin/bash

# =============================================================================
# Backup-Verifikations-Script für Datenschutz-Rechtsprechung API
# =============================================================================
# Dieses Script testet die Integrität eines Backups ohne es zu restoren.
#
# Verwendung:
#   ./verify_backup.sh <backup-file>
# =============================================================================

set -e  # Exit on error

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging-Funktionen
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Argument prüfen
if [ $# -eq 0 ]; then
    log_error "Verwendung: $0 <backup-file>"
    exit 1
fi

BACKUP_FILE="$1"

# Backup-Datei prüfen
if [ ! -f "$BACKUP_FILE" ]; then
    log_error "Backup-Datei nicht gefunden: $BACKUP_FILE"
    exit 1
fi

log_info "=== Backup-Verifikation ==="
log_info "Datei: $BACKUP_FILE"

# Dateigröße prüfen
FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
FILE_SIZE_BYTES=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null)

if [ "$FILE_SIZE_BYTES" -eq 0 ]; then
    log_error "❌ Backup ist leer!"
    exit 1
fi

log_info "Dateigröße: $FILE_SIZE"

# Checksum prüfen falls vorhanden
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [ -f "$CHECKSUM_FILE" ]; then
    log_info "Prüfe SHA256-Checksum..."
    if sha256sum -c "$CHECKSUM_FILE" > /dev/null 2>&1; then
        log_info "✅ Checksum korrekt"
    else
        log_error "❌ Checksum fehlgeschlagen!"
        exit 1
    fi
else
    log_warn "Keine Checksum-Datei gefunden"
fi

# Kompression testen
log_info "Teste Kompression..."
if gunzip -t "$BACKUP_FILE" 2>/dev/null; then
    log_info "✅ Kompression intakt"
else
    log_error "❌ Kompression beschädigt!"
    exit 1
fi

# SQL-Struktur prüfen
log_info "Prüfe SQL-Struktur..."
TEMP_CHECK="/tmp/backup_check_$(date +%Y%m%d_%H%M%S).sql"

# Erste 1000 Zeilen extrahieren und prüfen
gunzip -c "$BACKUP_FILE" | head -n 1000 > "$TEMP_CHECK"

# Prüfe auf wichtige SQL-Befehle
CHECKS_PASSED=0
CHECKS_FAILED=0

# Prüfe auf CREATE TABLE
if grep -q "CREATE TABLE" "$TEMP_CHECK"; then
    log_info "✅ CREATE TABLE Befehle gefunden"
    ((CHECKS_PASSED++))
else
    log_warn "⚠️  Keine CREATE TABLE Befehle gefunden"
    ((CHECKS_FAILED++))
fi

# Prüfe auf decisions Tabelle
if grep -q "decisions" "$TEMP_CHECK"; then
    log_info "✅ decisions Tabelle gefunden"
    ((CHECKS_PASSED++))
else
    log_error "❌ decisions Tabelle nicht gefunden"
    ((CHECKS_FAILED++))
fi

# Prüfe auf PostgreSQL-spezifische Syntax
if grep -q "SET" "$TEMP_CHECK" && grep -q "ALTER" "$TEMP_CHECK"; then
    log_info "✅ PostgreSQL-Syntax erkannt"
    ((CHECKS_PASSED++))
else
    log_warn "⚠️  PostgreSQL-Syntax nicht eindeutig"
fi

# Aufräumen
rm "$TEMP_CHECK"

# Erweiterte Analyse (optional)
log_info "Führe erweiterte Analyse durch..."

# Zähle Tabellen
TABLE_COUNT=$(gunzip -c "$BACKUP_FILE" | grep -c "CREATE TABLE" || true)
log_info "Anzahl Tabellen: $TABLE_COUNT"

# Zähle INSERT Statements (nur erste 10000 Zeilen für Performance)
INSERT_COUNT=$(gunzip -c "$BACKUP_FILE" | head -n 10000 | grep -c "INSERT INTO" || true)
log_info "INSERT Statements (erste 10k Zeilen): $INSERT_COUNT"

# Geschätzte Anzahl Entscheidungen (basierend auf COPY Befehlen)
COPY_DECISIONS=$(gunzip -c "$BACKUP_FILE" | grep "COPY decisions" | head -1 || true)
if [ -n "$COPY_DECISIONS" ]; then
    log_info "COPY Befehl für decisions gefunden"
fi

# Zusammenfassung
echo ""
log_info "=== Verifikations-Ergebnis ==="
log_info "Prüfungen bestanden: $CHECKS_PASSED"
if [ $CHECKS_FAILED -gt 0 ]; then
    log_warn "Prüfungen fehlgeschlagen: $CHECKS_FAILED"
fi

# Gesamtbewertung
if [ $CHECKS_FAILED -eq 0 ]; then
    log_info "✅ Backup scheint gültig zu sein"
    exit 0
elif [ $CHECKS_PASSED -gt $CHECKS_FAILED ]; then
    log_warn "⚠️  Backup möglicherweise gültig, aber mit Warnungen"
    exit 0
else
    log_error "❌ Backup scheint beschädigt zu sein"
    exit 1
fi