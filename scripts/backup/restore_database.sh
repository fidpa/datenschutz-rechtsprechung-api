#!/bin/bash

# =============================================================================
# PostgreSQL Restore Script für Datenschutz-Rechtsprechung API
# =============================================================================
# Dieses Script stellt ein Backup der PostgreSQL Datenbank wieder her.
#
# Verwendung:
#   ./restore_database.sh <backup-file> [--production] [--force]
#
# Argumente:
#   backup-file     Pfad zur Backup-Datei (.sql.gz)
#
# Optionen:
#   --production    Verwendet Production-Umgebungsvariablen
#   --force         Überspringt Sicherheitsabfragen
# =============================================================================

set -e  # Exit on error

# Konfiguration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_prompt() {
    echo -e "${BLUE}[?]${NC} $1"
}

# Hilfe anzeigen
show_help() {
    echo "PostgreSQL Restore Script für Datenschutz-Rechtsprechung API"
    echo ""
    echo "Verwendung:"
    echo "  $0 <backup-file> [--production] [--force]"
    echo ""
    echo "Argumente:"
    echo "  backup-file     Pfad zur Backup-Datei (.sql.gz) oder 'latest'"
    echo ""
    echo "Optionen:"
    echo "  --production    Verwendet Production-Umgebungsvariablen"
    echo "  --force         Überspringt Sicherheitsabfragen"
    echo "  --help          Zeigt diese Hilfe"
    echo ""
    echo "Beispiele:"
    echo "  $0 backups/daily/latest.sql.gz"
    echo "  $0 latest --production"
    echo "  $0 backups/daily/datenschutz_rechtsprechung_api_daily_20250113_030000.sql.gz --force"
    exit 0
}

# Argumente parsen
BACKUP_FILE=""
PRODUCTION_MODE=false
FORCE_MODE=false

for arg in "$@"; do
    case $arg in
        --production)
            PRODUCTION_MODE=true
            ;;
        --force)
            FORCE_MODE=true
            ;;
        --help|-h)
            show_help
            ;;
        *)
            if [ -z "$BACKUP_FILE" ]; then
                BACKUP_FILE="$arg"
            fi
            ;;
    esac
done

# Backup-Datei prüfen
if [ -z "$BACKUP_FILE" ]; then
    log_error "Keine Backup-Datei angegeben!"
    echo ""
    show_help
fi

# Production-Flag prüfen
if [ "$PRODUCTION_MODE" = true ]; then
    ENV_FILE="$PROJECT_ROOT/.env.production"
    CONTAINER_NAME="dsr_postgres_prod"
    log_warn "⚠️  PRODUCTION-MODUS AKTIVIERT ⚠️"
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

# "latest" als Alias behandeln
if [ "$BACKUP_FILE" == "latest" ]; then
    # Suche neuestes Backup
    if [ "$PRODUCTION_MODE" = true ]; then
        LATEST_DAILY="$BACKUP_DIR/daily/latest.sql.gz"
        LATEST_WEEKLY="$BACKUP_DIR/weekly/latest.sql.gz"
        
        if [ -f "$LATEST_WEEKLY" ]; then
            BACKUP_FILE="$LATEST_WEEKLY"
            log_info "Verwende neuestes wöchentliches Backup"
        elif [ -f "$LATEST_DAILY" ]; then
            BACKUP_FILE="$LATEST_DAILY"
            log_info "Verwende neuestes tägliches Backup"
        else
            log_error "Kein 'latest' Backup gefunden!"
            exit 1
        fi
    else
        BACKUP_FILE="$BACKUP_DIR/daily/latest.sql.gz"
        if [ ! -f "$BACKUP_FILE" ]; then
            log_error "Kein 'latest' Backup gefunden!"
            exit 1
        fi
    fi
fi

# Absoluten Pfad ermitteln
if [[ ! "$BACKUP_FILE" = /* ]]; then
    BACKUP_FILE="$PROJECT_ROOT/$BACKUP_FILE"
fi

# Backup-Datei prüfen
if [ ! -f "$BACKUP_FILE" ]; then
    log_error "Backup-Datei nicht gefunden: $BACKUP_FILE"
    exit 1
fi

# Backup-Informationen anzeigen
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
BACKUP_DATE=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$BACKUP_FILE" 2>/dev/null || stat -c "%y" "$BACKUP_FILE" 2>/dev/null | cut -d' ' -f1-2)

log_info "=== Backup-Informationen ==="
log_info "Datei: $BACKUP_FILE"
log_info "Größe: $BACKUP_SIZE"
log_info "Erstellt: $BACKUP_DATE"
log_info "Ziel-Datenbank: $POSTGRES_DB"

# Checksum prüfen falls vorhanden
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [ -f "$CHECKSUM_FILE" ]; then
    log_info "Prüfe Backup-Integrität..."
    if sha256sum -c "$CHECKSUM_FILE" > /dev/null 2>&1; then
        log_info "✅ Backup-Integrität bestätigt"
    else
        log_error "❌ Backup-Integrität fehlgeschlagen!"
        if [ "$FORCE_MODE" = false ]; then
            exit 1
        else
            log_warn "Force-Modus aktiv, fahre trotzdem fort..."
        fi
    fi
else
    log_warn "Keine Checksum-Datei gefunden, überspringe Integritätsprüfung"
fi

# Sicherheitsabfrage
if [ "$FORCE_MODE" = false ]; then
    echo ""
    log_warn "⚠️  WARNUNG: Diese Operation wird die aktuelle Datenbank überschreiben!"
    log_warn "⚠️  Alle aktuellen Daten in '$POSTGRES_DB' gehen verloren!"
    echo ""
    
    # Aktuelles Backup erstellen
    log_prompt "Soll vorher ein Backup der aktuellen Datenbank erstellt werden? (empfohlen) [Y/n]: "
    read -r CREATE_BACKUP
    
    if [[ ! "$CREATE_BACKUP" =~ ^[Nn]$ ]]; then
        log_info "Erstelle Sicherheits-Backup der aktuellen Datenbank..."
        SAFETY_BACKUP="$BACKUP_DIR/safety/before_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
        mkdir -p "$BACKUP_DIR/safety"
        
        if [ "$PRODUCTION_MODE" = true ]; then
            "$SCRIPT_DIR/backup_database.sh" --production
        else
            "$SCRIPT_DIR/backup_database.sh"
        fi
        
        log_info "Sicherheits-Backup erstellt: $SAFETY_BACKUP"
    fi
    
    echo ""
    log_prompt "Wirklich fortfahren mit dem Restore? [y/N]: "
    read -r CONFIRM
    
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        log_info "Restore abgebrochen."
        exit 0
    fi
fi

log_info "Starte Restore-Prozess..."

# Temporäre entpackte Datei
TEMP_SQL="/tmp/dsr_restore_$(date +%Y%m%d_%H%M%S).sql"

# Backup entpacken
log_info "Entpacke Backup..."
gunzip -c "$BACKUP_FILE" > "$TEMP_SQL"

# Prüfen ob Docker läuft
RESTORE_METHOD=""
if command -v docker &> /dev/null; then
    # Versuche Restore via Docker Container
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "Restore via Docker Container: $CONTAINER_NAME"
        
        # SQL-Datei in Container kopieren
        docker cp "$TEMP_SQL" "${CONTAINER_NAME}:/tmp/restore.sql"
        
        # Restore ausführen
        docker exec -t "$CONTAINER_NAME" psql \
            -U "$POSTGRES_USER" \
            -d "$POSTGRES_DB" \
            -f "/tmp/restore.sql" \
            --quiet \
            --single-transaction
        
        # Aufräumen im Container
        docker exec "$CONTAINER_NAME" rm "/tmp/restore.sql"
        
        RESTORE_METHOD="docker"
    else
        log_warn "Container $CONTAINER_NAME nicht gefunden, verwende direkten Zugriff"
        RESTORE_METHOD="direct"
    fi
else
    RESTORE_METHOD="direct"
fi

# Direkter Restore falls Docker nicht verfügbar
if [ "$RESTORE_METHOD" == "direct" ]; then
    if command -v psql &> /dev/null; then
        log_info "Restore via direkten PostgreSQL-Zugriff"
        
        PGPASSWORD="$POSTGRES_PASSWORD" psql \
            -h "$POSTGRES_HOST" \
            -p "$POSTGRES_PORT" \
            -U "$POSTGRES_USER" \
            -d "$POSTGRES_DB" \
            -f "$TEMP_SQL" \
            --quiet \
            --single-transaction
    else
        log_error "psql nicht gefunden. Bitte PostgreSQL-Client installieren."
        rm "$TEMP_SQL"
        exit 1
    fi
fi

# Temporäre Datei löschen
rm "$TEMP_SQL"

# Restore verifizieren
log_info "Verifiziere Restore..."

# Anzahl der Entscheidungen prüfen
if [ "$RESTORE_METHOD" == "docker" ]; then
    DECISION_COUNT=$(docker exec -t "$CONTAINER_NAME" psql \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        -t -c "SELECT COUNT(*) FROM decisions;" 2>/dev/null | tr -d ' \r\n' || echo "0")
else
    DECISION_COUNT=$(PGPASSWORD="$POSTGRES_PASSWORD" psql \
        -h "$POSTGRES_HOST" \
        -p "$POSTGRES_PORT" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        -t -c "SELECT COUNT(*) FROM decisions;" 2>/dev/null | tr -d ' \r\n' || echo "0")
fi

log_info "=== Restore-Ergebnis ==="
log_info "Anzahl Entscheidungen: $DECISION_COUNT"

if [ "$DECISION_COUNT" -eq 0 ]; then
    log_warn "⚠️  Keine Entscheidungen in der Datenbank - Restore möglicherweise fehlgeschlagen!"
else
    log_info "✅ Restore erfolgreich abgeschlossen!"
fi

# Hinweise für weitere Schritte
echo ""
log_info "=== Nächste Schritte ==="
log_info "1. Prüfen Sie die Anwendung: http://localhost:8000/health"
log_info "2. Testen Sie die API: http://localhost:8000/docs"
log_info "3. Prüfen Sie die Logs auf Fehler"

if [ "$PRODUCTION_MODE" = true ]; then
    log_info "4. Starten Sie die Production-Services neu:"
    log_info "   docker-compose -f docker-compose.production.yml restart"
fi

exit 0