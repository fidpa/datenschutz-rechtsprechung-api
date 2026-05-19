#!/bin/bash

# =============================================================================
# Cron-Job Setup für automatische Backups
# =============================================================================
# Dieses Script richtet automatische Backup-Jobs ein.
#
# Verwendung:
#   ./setup_cron.sh [--production]
# =============================================================================

set -e

# Konfiguration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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
PRODUCTION_FLAG=""
if [[ "$1" == "--production" ]]; then
    PRODUCTION_FLAG=" --production"
    log_info "Production-Modus für Cron-Jobs"
else
    log_info "Development-Modus für Cron-Jobs"
fi

# Cron-Job Definitionen
CRON_JOBS="
# =============================================================================
# Datenschutz-Rechtsprechung API Automatische Backups
# =============================================================================

# Tägliches Backup um 3:00 Uhr
0 3 * * * $SCRIPT_DIR/backup_database.sh${PRODUCTION_FLAG} >> $PROJECT_ROOT/logs/backup.log 2>&1

# Backup-Verifikation um 3:30 Uhr
30 3 * * * $SCRIPT_DIR/verify_backup.sh $PROJECT_ROOT/backups/daily/latest.sql.gz >> $PROJECT_ROOT/logs/backup-verify.log 2>&1

# Cleanup alte Logs jeden Sonntag um 4:00 Uhr
0 4 * * 0 find $PROJECT_ROOT/logs -name '*.log' -mtime +30 -delete

# Optional: Health-Check alle 5 Minuten (auskommentiert)
# */5 * * * * curl -s http://localhost:8000/system/health > /dev/null || echo 'Health check failed' | mail -s 'Datenschutz-Rechtsprechung API Alert' admin@example.com
"

# Log-Verzeichnis erstellen
mkdir -p "$PROJECT_ROOT/logs"

log_info "=== Cron-Job Setup ==="
log_info "Projekt-Verzeichnis: $PROJECT_ROOT"

# Aktuelle Crontab sichern
BACKUP_FILE="/tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt"
crontab -l > "$BACKUP_FILE" 2>/dev/null || true
log_info "Aktuelle Crontab gesichert: $BACKUP_FILE"

# Prüfen ob Jobs bereits existieren
if crontab -l 2>/dev/null | grep -q "Datenschutz-Rechtsprechung API"; then
    log_warn "Datenschutz-Rechtsprechung API Cron-Jobs bereits vorhanden!"
    echo ""
    read -p "Möchten Sie die bestehenden Jobs überschreiben? [y/N]: " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Setup abgebrochen"
        exit 0
    fi
    
    # Alte Datenschutz-Rechtsprechung API Jobs entfernen
    crontab -l | grep -v "Datenschutz-Rechtsprechung API" | grep -v "$SCRIPT_DIR" > /tmp/crontab_new.txt || true
else
    crontab -l > /tmp/crontab_new.txt 2>/dev/null || true
fi

# Neue Jobs hinzufügen
echo "$CRON_JOBS" >> /tmp/crontab_new.txt

# Neue Crontab installieren
crontab /tmp/crontab_new.txt
rm /tmp/crontab_new.txt

log_info "✅ Cron-Jobs erfolgreich eingerichtet!"

# Installierte Jobs anzeigen
echo ""
log_info "=== Installierte Cron-Jobs ==="
crontab -l | grep -A1 "Datenschutz-Rechtsprechung API" | grep -v "^--$"

echo ""
log_info "=== Nächste Schritte ==="
log_info "1. Prüfen Sie die Cron-Jobs: crontab -l"
log_info "2. Testen Sie das Backup manuell: $SCRIPT_DIR/backup_database.sh"
log_info "3. Überwachen Sie die Logs: tail -f $PROJECT_ROOT/logs/backup.log"

# Systemd-Timer Alternative vorschlagen
echo ""
log_info "=== Alternative: systemd Timer (empfohlen für Production) ==="
log_info "Für Production-Umgebungen empfehlen wir systemd Timer statt Cron."
log_info "Siehe: $PROJECT_ROOT/docs/PRODUCTION_SETUP.md"

exit 0