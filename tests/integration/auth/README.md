# Authentication & Security Integration Tests

Diese Tests validieren das komplette Authentication-System (Phase 9) mit allen Security-Features.

## Test-Dateien

| Datei | Beschreibung | Umfang |
|-------|-------------|--------|
| `test_auth_basic.py` | **Basic Auth Tests** | Login/Logout Flow, CSRF, Rate Limiting |
| `test_auth_comprehensive.py` | **Comprehensive Tests** | Vollständiger Auth-Flow mit allen Security-Features |
| `test_security_features.py` | **Security Tests** | CSRF Protection, Rate Limiting, Session Security |

## Ausführung

```bash
# Alle Auth-Tests
pytest tests/integration/auth/ -v

# Einzelne Test-Datei
pytest tests/integration/auth/test_auth_basic.py -v

# Mit Coverage
pytest tests/integration/auth/ --cov=src.web -v
```

## Voraussetzungen

- Flask Web-UI muss laufen (Port 5001)
- PostgreSQL und Redis müssen verfügbar sein
- Test-User in Datenbank (wird automatisch erstellt)

## Test-Umgebung

Die Tests verwenden:
- **URL**: `http://localhost:5001`
- **Test-User**: `admin@test.com` / `testpass123`
- **Session-Handling**: Automatische Cookie-Verwaltung
- **CSRF-Token**: Automatische Extraktion aus Forms

## Security-Features getestet

- ✅ Flask-Login Session Management
- ✅ CSRF Protection (ohne Flask-WTF)
- ✅ Rate Limiting (5 Versuche / 15 Min)
- ✅ bcrypt Password Hashing
- ✅ Admin/Viewer Rollen-System
- ✅ Security Headers (XSS, CSRF, Content-Type)
- ✅ Password Reset mit Email-Templates
- ✅ Session Invalidation bei Logout

## Fehlerbehebung

**Connection Refused**: Web-UI nicht gestartet
```bash
cd src/web && python development_server.py
```

**Test-User fehlt**: Datenbank initialisieren
```bash
python scripts/init_db.py
```

**Rate Limit erreicht**: 15 Minuten warten oder Redis Cache leeren
```bash
redis-cli FLUSHALL
```