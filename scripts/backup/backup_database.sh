#!/bin/bash

# =============================================================================
# PostgreSQL Backup Script für Datenschutz-Rechtsprechung API
# =============================================================================
# Dieses Script erstellt komprimierte Backups der PostgreSQL Datenbank
# und rotiert alte Backups automatisch.
#
# Verwendung:
#   ./backup_database.sh [--production]
#
# Optionen:
#   --production    Verwendet Production-Umgebungsvariablen
# =============================================================================

set -e  # Exit on error

# Konfiguration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)

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

# Production-Flag prüfen
if [[ "$1" == "--production" ]]; then
    ENV_FILE="$PROJECT_ROOT/.env.production"
    CONTAINER_NAME="dsr_postgres_prod"
    log_info "Production-Modus aktiviert"
else
    ENV_FILE="$PROJECT_ROOT/.env"
    CONTAINER_NAME="dsr_postgres"
    log_info "Development-Modus"
fi

# Umgebungsvariablen laden
if [ -f "$ENV_FILE" ]; then
    export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
    log_info "Umgebungsvariablen geladen aus: $ENV_FILE"
else
    log_error "Umgebungsdatei nicht gefunden: $ENV_FILE"
    exit 1
fi

# Standard-Werte setzen falls nicht definiert
POSTGRES_DB="${POSTGRES_DB:-datenschutz_rechtsprechung_api}"
POSTGRES_USER="${POSTGRES_USER:-dsr_user}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

# Backup-Verzeichnisse erstellen
mkdir -p "$BACKUP_DIR/daily"
mkdir -p "$BACKUP_DIR/weekly"
mkdir -p "$BACKUP_DIR/monthly"

# Backup-Typ bestimmen (täglich, wöchentlich, monatlich)
DAY_OF_WEEK=$(date +%u)
DAY_OF_MONTH=$(date +%d)

if [ "$DAY_OF_MONTH" == "01" ]; then
    BACKUP_TYPE="monthly"
    BACKUP_SUBDIR="$BACKUP_DIR/monthly"
    RETENTION_DAYS=365
elif [ "$DAY_OF_WEEK" == "7" ]; then  # Sonntag
    BACKUP_TYPE="weekly"
    BACKUP_SUBDIR="$BACKUP_DIR/weekly"
    RETENTION_DAYS=30
else
    BACKUP_TYPE="daily"
    BACKUP_SUBDIR="$BACKUP_DIR/daily"
    RETENTION_DAYS=7
fi

BACKUP_FILE="$BACKUP_SUBDIR/datenschutz_rechtsprechung_api_${BACKUP_TYPE}_$DATE.sql.gz"

log_info "Starte $BACKUP_TYPE Backup..."
log_info "Datenbank: $POSTGRES_DB"
log_info "Backup-Datei: $BACKUP_FILE"

# Prüfen ob Docker läuft
if command -v docker &> /dev/null; then
    # Versuche Backup via Docker Container
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "Erstelle Backup via Docker Container: $CONTAINER_NAME"
        
        # Backup mit pg_dump im Container
        docker exec -t "$CONTAINER_NAME" pg_dump \
            -U "$POSTGRES_USER" \
            -d "$POSTGRES_DB" \
            --verbose \
            --no-owner \
            --no-acl \
            --clean \
            --if-exists \
            | gzip -9 > "$BACKUP_FILE"
        
        BACKUP_METHOD="docker"
    else
        log_warn "Container $CONTAINER_NAME nicht gefunden, verwende direkten Zugriff"
        BACKUP_METHOD="direct"
    fi
else
    BACKUP_METHOD="direct"
fi

# Direkter Backup falls Docker nicht verfügbar
if [ "$BACKUP_METHOD" == "direct" ]; then
    if command -v pg_dump &> /dev/null; then
        log_info "Erstelle Backup via direkten PostgreSQL-Zugriff"
        
        PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
            -h "$POSTGRES_HOST" \
            -p "$POSTGRES_PORT" \
            -U "$POSTGRES_USER" \
            -d "$POSTGRES_DB" \
            --verbose \
            --no-owner \
            --no-acl \
            --clean \
            --if-exists \
            | gzip -9 > "$BACKUP_FILE"
    else
        log_error "pg_dump nicht gefunden. Bitte PostgreSQL-Client installieren."
        exit 1
    fi
fi

# Backup-Größe prüfen
if [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    
    # Prüfen ob Backup nicht leer ist
    if [ ! -s "$BACKUP_FILE" ]; then
        log_error "Backup ist leer!"
        rm "$BACKUP_FILE"
        exit 1
    fi
    
    log_info "Backup erfolgreich erstellt: $BACKUP_FILE ($BACKUP_SIZE)"
    
    # SHA256 Checksum erstellen
    CHECKSUM_FILE="${BACKUP_FILE}.sha256"
    sha256sum "$BACKUP_FILE" > "$CHECKSUM_FILE"
    log_info "Checksum erstellt: $CHECKSUM_FILE"
    
    # Symlink auf letztes Backup aktualisieren
    LATEST_LINK="$BACKUP_SUBDIR/latest.sql.gz"
    ln -sf "$(basename "$BACKUP_FILE")" "$LATEST_LINK"
    log_info "Latest-Link aktualisiert: $LATEST_LINK"
else
    log_error "Backup-Datei konnte nicht erstellt werden!"
    exit 1
fi

# Alte Backups rotieren
log_info "Rotiere alte Backups (älter als $RETENTION_DAYS Tage)..."
DELETED_COUNT=0

while IFS= read -r old_backup; do
    log_info "Lösche altes Backup: $(basename "$old_backup")"
    rm "$old_backup"
    # Auch Checksum löschen falls vorhanden
    [ -f "${old_backup}.sha256" ] && rm "${old_backup}.sha256"
    ((DELETED_COUNT++))
done < <(find "$BACKUP_SUBDIR" -name "*.sql.gz" -type f -mtime +$RETENTION_DAYS)

if [ $DELETED_COUNT -gt 0 ]; then
    log_info "$DELETED_COUNT alte Backups gelöscht"
else
    log_info "Keine alten Backups zu löschen"
fi

# Backup-Statistiken anzeigen
log_info "=== Backup-Statistiken ==="
log_info "Backup-Typ: $BACKUP_TYPE"
log_info "Backup-Größe: $BACKUP_SIZE"
log_info "Anzahl tägliche Backups: $(ls -1 $BACKUP_DIR/daily/*.sql.gz 2>/dev/null | wc -l)"
log_info "Anzahl wöchentliche Backups: $(ls -1 $BACKUP_DIR/weekly/*.sql.gz 2>/dev/null | wc -l)"
log_info "Anzahl monatliche Backups: $(ls -1 $BACKUP_DIR/monthly/*.sql.gz 2>/dev/null | wc -l)"
log_info "Gesamt-Speicherplatz: $(du -sh $BACKUP_DIR | cut -f1)"

log_info "✅ Backup abgeschlossen!"

# Exit-Code 0 für erfolgreiche Ausführung
exit 0