# Scripts - Datenschutz-Rechtsprechung API

**Status**: Post Phase 12.3 Konsolidierung (16.08.2025)  
**System**: Enterprise-Ready Production Scripts

## 📊 Script-Kategorisierung

### 🎯 Aktive Production-Scripts

#### Admin & Management
- **`admin.py`** - Master CLI-Tool für alle Admin-Operationen
  - User-Management, Health-Checks, Claude Integration
  - **Verwendung**: `python scripts/admin.py --help`

- **`fill_database.py`** - Umfassende Datenbank-Befüllung
  - Kombiniert GDPRhub + OpenLegalData
  - **Verwendung**: `python scripts/fill_database.py --limit 100`

- **`init_db.py`** - Datenbank-Initialisierung
  - **Verwendung**: `python scripts/init_db.py`

#### Crawler & Data Collection
- **`run_crawler.py`** - GDPRhub Crawler (Legacy, aber aktiv)
  - **Verwendung**: `python scripts/run_crawler.py --source gdprhub --max-pages 10`

- **`run_openlegaldata.py`** - OpenLegalData Crawler
  - **Verwendung**: `python scripts/run_openlegaldata.py --limit 50`

#### Testing & Development
- **`test_api.py`** - API Integration Tests
- **`test_web_ui.py`** - Web-UI Tests
- **`demo_claude_logging.py`** - Claude Integration Demo
- **`demo_flask_integration.py`** - Flask Demo

#### System Management
- **`migrate_db.py`** - Datenbank-Migrationen
- **`setup_fulltext_search.py`** - Volltext-Suche Setup

### 🚀 Production Scripts (Deployment)

#### Startup Scripts
- **`start_all.sh`** - Startet alle Services
- **`start_web_dev.sh`** - Development Web-Server
- **`start_web_prod.sh`** - Production Web-Server
- **`start-production.sh`** - Production-Startup

#### Setup Scripts
- **`setup-production.sh`** - Production-Environment-Setup
- **`setup-ssl-localhost.sh`** - SSL-Zertifikat für localhost
- **`setup-logging.sh`** - Logging-Konfiguration

#### Testing & Monitoring
- **`test-production.sh`** - Production-Tests
- **`final-production-test.sh`** - Finale Validierung
- **`health-monitor.sh`** - Health-Monitoring
- **`production-commands.sh`** - Wartungs-Kommandos

#### Backup & Security
- **`backup-system.sh`** - System-Backup
- **`restore-system.sh`** - System-Wiederherstellung
- **`install-systemd.sh`** - Systemd-Service-Installation

### 📁 Spezialisierte Ordner

#### `/backup/` - Backup-Automation
- `backup_database.sh` - Datenbank-Backup
- `restore_database.sh` - Datenbank-Wiederherstellung
- `setup_cron.sh` - Cron-Job-Setup
- `verify_backup.sh` - Backup-Verifikation

#### `/security/` - Security-Tools
- `generate_secrets.sh` - Secret-Generation

#### `/performance/` - Performance-Optimierung
- `optimize_database.py` - Datenbank-Optimierung
- `optimize_database.sql` - SQL-Optimierungen

#### `/claude_analysis/` - Claude Code Integration
- `daily_analysis.py` - Tägliche Analysis
- `engines/` - Analysis-Engines
- `patterns/` - Pattern-Matching
- `reports/` - Report-Generation

#### `/cron/` - Cron-Job-Scripts
- `claude_daily_analysis.sh` - Claude Tägliche Analysis
- `setup_claude_cron.sh` - Claude Cron-Setup

### 🗃️ Archivierte Scripts

#### `/archive/legacy-tests/` - Obsolete Test-Scripts
- `test_phase4.py` - Phase 4 Tests (ersetzt)
- `phase6_demo.py` - Phase 6 Demo (ersetzt)
- `test_new_features.py` - Ad-hoc Tests (integriert)
- `test_openlegaldata.py` - Old OpenLegal Tests (ersetzt)

**Grund für Archivierung**: Phase-spezifische Scripts nach Projekt-Abschluss nicht mehr relevant

## 🎯 Häufige Verwendung

### Tägliche Admin-Tasks
```bash
# System-Health prüfen
python scripts/admin.py health

# Claude Integration testen
python scripts/admin.py claude-health

# User-Management
python scripts/admin.py users list
```

### Datensammlung
```bash
# Umfassende Datenbank-Befüllung
python scripts/fill_database.py --limit 100

# Nur GDPRhub
python scripts/run_crawler.py --source gdprhub --max-pages 20
```

### System-Start
```bash
# All Services
./scripts/start_all.sh

# Nur Web-UI (Development)
./scripts/start_web_dev.sh

# Production-Setup
./scripts/setup-production.sh
```

## 📝 Maintenance

### Script-Hinzufügung
Neue Scripts sollten:
1. Kategorisiert werden (Production/Testing/Archive)
2. Dokumentiert werden in diesem README
3. Executable-Permissions haben: `chmod +x script.sh`

### Archivierung
Scripts archivieren wenn:
- Phase-spezifisch und Phase abgeschlossen
- Funktionalität in anderen Scripts integriert
- Nicht mehr wartbar/relevant

### Aktiv halten
Scripts aktiv halten wenn:
- Regelmäßig verwendet
- Production-kritisch
- Wartungsaufgaben

---

**Konsolidierung**: 16.08.2025 - Post Phase 12.3 Script-Inventar und Kategorisierung abgeschlossen.