#!/bin/bash

# =============================================================================
# Secret Generation Script für Datenschutz-Rechtsprechung API Production
# =============================================================================
# Dieses Script generiert sichere Secrets für die Production-Umgebung.
#
# Verwendung:
#   ./generate_secrets.sh [--update-env]
#
# Optionen:
#   --update-env    Aktualisiert .env.production automatisch (Vorsicht!)
# =============================================================================

set -e

# Konfiguration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_TEMPLATE="$PROJECT_ROOT/.env.production.template"
ENV_FILE="$PROJECT_ROOT/.env.production"

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

log_secret() {
    echo -e "${BLUE}[SECRET]${NC} $1"
}

# Prüfe ob OpenSSL verfügbar ist
if ! command -v openssl &> /dev/null; then
    log_error "OpenSSL ist nicht installiert!"
    echo "Bitte installieren Sie OpenSSL:"
    echo "  macOS: brew install openssl"
    echo "  Ubuntu/Debian: apt-get install openssl"
    echo "  CentOS/RHEL: yum install openssl"
    exit 1
fi

# Generiere sichere Secrets
log_info "=== Generiere sichere Secrets für Datenschutz-Rechtsprechung API ==="
echo ""

# Application Secret Key (32 bytes hex)
SECRET_KEY=$(openssl rand -hex 32)
log_secret "SECRET_KEY=$SECRET_KEY"
echo ""

# PostgreSQL Password (24 bytes base64)
POSTGRES_PASSWORD=$(openssl rand -base64 24)
log_secret "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
echo ""

# Redis Password (24 bytes base64)
REDIS_PASSWORD=$(openssl rand -base64 24)
log_secret "REDIS_PASSWORD=$REDIS_PASSWORD"
echo ""

# Grafana Admin Password (16 bytes base64)
GRAFANA_PASSWORD=$(openssl rand -base64 16)
log_secret "GRAFANA_PASSWORD=$GRAFANA_PASSWORD"
echo ""

# JWT Secret für API (optional, 32 bytes hex)
JWT_SECRET=$(openssl rand -hex 32)
log_secret "JWT_SECRET=$JWT_SECRET"
echo ""

# Celery Secret (optional, 24 bytes base64)
CELERY_SECRET=$(openssl rand -base64 24)
log_secret "CELERY_SECRET=$CELERY_SECRET"
echo ""

# Backup Encryption Key (optional, 32 bytes hex)
BACKUP_ENCRYPTION_KEY=$(openssl rand -hex 32)
log_secret "BACKUP_ENCRYPTION_KEY=$BACKUP_ENCRYPTION_KEY"
echo ""

# API Key für externe Services (optional, 32 bytes hex)
API_KEY=$(openssl rand -hex 32)
log_secret "API_KEY=$API_KEY"
echo ""

# Session Secret (16 bytes base64)
SESSION_SECRET=$(openssl rand -base64 16)
log_secret "SESSION_SECRET=$SESSION_SECRET"
echo ""

# Prüfe ob --update-env Flag gesetzt ist
if [[ "$1" == "--update-env" ]]; then
    log_warn "⚠️  Auto-Update Modus aktiviert!"
    
    # Backup erstellen falls .env.production existiert
    if [ -f "$ENV_FILE" ]; then
        BACKUP_FILE="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$BACKUP_FILE"
        log_info "Backup erstellt: $BACKUP_FILE"
    fi
    
    # Template kopieren falls .env.production nicht existiert
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_TEMPLATE" ]; then
            cp "$ENV_TEMPLATE" "$ENV_FILE"
            log_info "Template kopiert nach: $ENV_FILE"
        else
            log_error "Template nicht gefunden: $ENV_TEMPLATE"
            exit 1
        fi
    fi
    
    # Secrets in .env.production einfügen
    log_info "Aktualisiere $ENV_FILE mit generierten Secrets..."
    
    # macOS und Linux kompatible sed-Befehle
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" "$ENV_FILE"
        sed -i '' "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|" "$ENV_FILE"
        sed -i '' "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=$REDIS_PASSWORD|" "$ENV_FILE"
        sed -i '' "s|GRAFANA_PASSWORD=.*|GRAFANA_PASSWORD=$GRAFANA_PASSWORD|" "$ENV_FILE"
    else
        # Linux
        sed -i "s|SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" "$ENV_FILE"
        sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|" "$ENV_FILE"
        sed -i "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=$REDIS_PASSWORD|" "$ENV_FILE"
        sed -i "s|GRAFANA_PASSWORD=.*|GRAFANA_PASSWORD=$GRAFANA_PASSWORD|" "$ENV_FILE"
    fi
    
    log_info "✅ Secrets erfolgreich in $ENV_FILE eingefügt!"
    echo ""
    log_warn "⚠️  WICHTIG: Bewahren Sie diese Secrets sicher auf!"
    log_warn "⚠️  Commiten Sie NIEMALS .env.production in Git!"
else
    echo ""
    log_info "=== Manuelle Konfiguration ==="
    log_info "Kopieren Sie die generierten Secrets in Ihre .env.production Datei."
    log_info "Oder führen Sie das Script mit --update-env aus für automatisches Update:"
    log_info "  $0 --update-env"
fi

# Speichere Secrets in separater Datei (optional)
SECRETS_FILE="$PROJECT_ROOT/.secrets.$(date +%Y%m%d_%H%M%S).txt"
cat > "$SECRETS_FILE" << EOF
# Datenschutz-Rechtsprechung API Production Secrets
# Generated: $(date)
# WARNUNG: Diese Datei enthält sensible Daten!

SECRET_KEY=$SECRET_KEY
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
REDIS_PASSWORD=$REDIS_PASSWORD
GRAFANA_PASSWORD=$GRAFANA_PASSWORD
JWT_SECRET=$JWT_SECRET
CELERY_SECRET=$CELERY_SECRET
BACKUP_ENCRYPTION_KEY=$BACKUP_ENCRYPTION_KEY
API_KEY=$API_KEY
SESSION_SECRET=$SESSION_SECRET
EOF

chmod 600 "$SECRETS_FILE"
log_info "Secrets gespeichert in: $SECRETS_FILE (chmod 600)"

echo ""
log_info "=== Sicherheits-Checkliste ==="
echo "[ ] .env.production ist NICHT in Git committed"
echo "[ ] Secrets sind in Password-Manager gespeichert"
echo "[ ] Backup der Secrets erstellt"
echo "[ ] Firewall-Regeln konfiguriert"
echo "[ ] SSL-Zertifikate installiert"
echo "[ ] Rate-Limiting aktiviert"
echo "[ ] CORS richtig konfiguriert"
echo "[ ] Debug-Modus deaktiviert"

echo ""
log_info "=== Nächste Schritte ==="
log_info "1. Prüfen Sie .env.production"
log_info "2. Starten Sie die Production-Services:"
log_info "   docker-compose -f docker-compose.production.yml up -d"
log_info "3. Testen Sie die Health-Checks:"
log_info "   curl https://your-domain.com/system/health"

exit 0