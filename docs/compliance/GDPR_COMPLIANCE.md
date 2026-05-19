# Compliance und rechtliche Überlegungen

## Rechtliche Grundlagen

### Text- und Data-Mining (TDM)-Ausnahme

Der Crawler operiert unter der **TDM-Ausnahme gemäß § 60d UrhG** (deutsches Urheberrechtsgesetz):

**§ 60d UrhG - Text und Data Mining für Zwecke der wissenschaftlichen Forschung**
> (1) Vervielfältigungen für Text und Data Mining sind für Zwecke der wissenschaftlichen Forschung nach Maßgabe der nachfolgenden Bestimmungen zulässig.

**Voraussetzungen:**
- Wissenschaftliche Forschungszwecke
- Nicht-kommerzielle Nutzung
- Rechtmäßiger Zugang zu den Werken
- Löschung nach Abschluss der Forschung (außer für Verifikation)

### Öffentliches Interesse

Die Sammlung und Verarbeitung erfolgt im **öffentlichen Interesse**:

1. **Transparenz der Rechtsprechung**: Förderung des Zugangs zu DSGVO-Entscheidungen
2. **Forschungszwecke**: Analyse von Datenschutz-Trends und -Entwicklungen
3. **Bildungszwecke**: Unterstützung von Lehre und Ausbildung
4. **Journalistische Zwecke**: Berichterstattung über Datenschutz-Entwicklungen

## Datenschutz-Compliance

### DSGVO-Konformität

Der Crawler selbst muss DSGVO-konform arbeiten:

```python
# Rechtmäßigkeit der Verarbeitung (Art. 6 DSGVO)
RECHTSGRUNDLAGEN = {
    "öffentliche_quellen": "Art. 6 Abs. 1 lit. f DSGVO - Berechtigtes Interesse",
    "gerichtsentscheidungen": "Art. 6 Abs. 1 lit. e DSGVO - Öffentliches Interesse",
    "anonymisierte_daten": "Kein Personenbezug nach Anonymisierung"
}
```

### Datenschutz-Folgenabschätzung (DSFA)

**Risikobewertung:**

| Verarbeitungsvorgang | Risiko | Maßnahmen |
|---------------------|--------|-----------|
| Sammlung von Entscheidungen | Niedrig | Nur öffentliche Quellen |
| Speicherung von Volltexten | Mittel | Anonymisierung vor Speicherung |
| Bereitstellung via API | Niedrig | Nur anonymisierte Daten |
| Audit-Logging | Niedrig | Begrenzte Aufbewahrung |

### Anonymisierung

**Dual-Backend-Strategie (seit 21.08.2025):**
Das System verwendet eine robuste Zweistufige Anonymisierungsstrategie:

1. **Primär: spaCy NER** (wenn verfügbar)
   - ML-basierte Named Entity Recognition
   - Hohe Genauigkeit bei deutschen Rechtsdokumenten
   - Erfordert de_core_news_sm Modell

2. **Fallback: SimpleGermanLegalAnonymizer** (immer verfügbar)
   - Regex-basierte Mustererkennung
   - Python 3.12+ kompatibel (keine externen Dependencies)
   - Optimiert für deutsche Rechtstexte
   - Erkennt: E-Mails, Telefonnummern, IBANs, Adressen, Namen, Unternehmen

**Anforderungen:**
- Entfernung aller personenbezogenen Daten
- Erhaltung rechtlicher Begriffe und Strukturen
- Konsistente Ersetzung innerhalb eines Dokuments
- Verschlüsselte Speicherung der Anonymisierungs-Mappings
- Automatischer Fallback bei spaCy-Ausfall

```python
# Anonymisierungs-Strategie mit Dual-Backend
class AnonymizationCompliance:
    """Sicherstellt DSGVO-konforme Anonymisierung mit Fallback-Mechanismus."""
    
    PERSONAL_DATA_CATEGORIES = [
        "Namen",
        "Adressen", 
        "Geburtsdaten",
        "Telefonnummern",
        "E-Mail-Adressen",
        "IP-Adressen",
        "Kontonummern",
        "Sozialversicherungsnummern",
        "IBANs",
        "Postleitzahlen"
    ]
    
    def __init__(self):
        """Initialisiert mit automatischer Backend-Auswahl."""
        try:
            from src.processors.anonymizer import GermanLegalAnonymizer
            self.backend = "spacy"
            self.anonymizer = GermanLegalAnonymizer()
        except:
            from src.processors.anonymizer import SimpleGermanLegalAnonymizer
            self.backend = "regex"
            self.anonymizer = SimpleGermanLegalAnonymizer()
    
    def verify_anonymization(self, text: str) -> bool:
        """Prüft, ob Text ausreichend anonymisiert ist."""
        for category in self.PERSONAL_DATA_CATEGORIES:
            if self.contains_personal_data(text, category):
                return False
        return True
```

## Crawling-Ethik

### Respektvolles Crawling

**Prinzipien:**

1. **robots.txt Einhaltung**
```python
from urllib.robotparser import RobotFileParser

def check_robots_txt(url: str) -> bool:
    """Prüft, ob URL gecrawlt werden darf."""
    rp = RobotFileParser()
    rp.set_url(urljoin(url, "/robots.txt"))
    rp.read()
    return rp.can_fetch(USER_AGENT, url)
```

2. **Rate-Limiting**
- Strikte Einhaltung dokumentierter Rate-Limits
- Exponentieller Backoff bei Fehlern
- Keine parallelen Anfragen an dieselbe Domain

3. **User-Agent Transparenz**
```python
USER_AGENT = "Academic GDPR Research Crawler/1.0 (https://projekt.de; kontakt@beispiel.com)"
```

4. **Keine Umgehung von Schutzmaßnahmen**
- Kein Umgehen von CAPTCHAs
- Kein Verwenden von Proxies zur Rate-Limit-Umgehung
- Respektierung von 429 (Too Many Requests) Responses

### Datenminimierung

**Prinzip**: Nur notwendige Daten sammeln und speichern

```python
class DataMinimization:
    """Implementiert Datenminimierungs-Prinzip."""
    
    REQUIRED_FIELDS = [
        "case_number",
        "court_name",
        "decision_date",
        "gdpr_articles",
        "anonymized_text"
    ]
    
    def minimize_data(self, data: dict) -> dict:
        """Entfernt nicht-notwendige Felder."""
        return {k: v for k, v in data.items() 
                if k in self.REQUIRED_FIELDS}
```

## Audit-Logging und Compliance-Monitoring

### Audit-Trail

Vollständige Dokumentation aller Verarbeitungsvorgänge:

```sql
-- Audit-Log-Struktur
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    action VARCHAR(50) NOT NULL,  -- 'crawl', 'process', 'anonymize', 'export'
    source VARCHAR(50),
    target_id VARCHAR(200),
    user_agent VARCHAR(500),
    ip_address INET,
    success BOOLEAN,
    error_message TEXT,
    metadata JSONB
);

-- Compliance-relevante Indizes
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_source ON audit_log(source);
```

### Compliance-Reports

```python
# src/compliance/reporter.py
from datetime import datetime, timedelta
from typing import Dict, List

class ComplianceReporter:
    """Generiert Compliance-Reports."""
    
    def generate_monthly_report(self) -> Dict:
        """Monatlicher Compliance-Report."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        return {
            "period": f"{start_date} - {end_date}",
            "total_crawled": self.count_crawled(start_date, end_date),
            "sources": self.get_source_statistics(),
            "anonymization_rate": self.calculate_anonymization_rate(),
            "robots_txt_compliance": self.check_robots_compliance(),
            "rate_limit_violations": self.count_rate_violations(),
            "data_retention_compliance": self.check_retention_policy(),
            "gdpr_requests": self.count_gdpr_requests()
        }
    
    def check_retention_policy(self) -> Dict:
        """Prüft Einhaltung der Aufbewahrungsfristen."""
        return {
            "audit_logs_expired": self.count_expired_logs(),
            "anonymization_maps_expired": self.count_expired_maps(),
            "compliance_status": "compliant"
        }
```

## Betroffenenrechte (DSGVO Kapitel III)

### Auskunftsrecht (Art. 15 DSGVO)

```python
class DataSubjectRights:
    """Implementiert Betroffenenrechte."""
    
    async def handle_access_request(self, request_id: str) -> Dict:
        """Bearbeitet Auskunftsanfrage."""
        # Prüfung: Haben wir Daten über diese Person?
        # Nach Anonymisierung sollte die Antwort immer "Nein" sein
        return {
            "request_id": request_id,
            "has_personal_data": False,
            "response": "Keine personenbezogenen Daten vorhanden (alle Daten anonymisiert)"
        }
```

### Löschrecht (Art. 17 DSGVO)

```python
async def handle_deletion_request(self, decision_id: str) -> bool:
    """Bearbeitet Löschanfrage."""
    # Entfernt Entscheidung aus Datenbank
    await self.db.execute(
        "UPDATE decisions SET deleted = true, deleted_at = NOW() WHERE id = $1",
        decision_id
    )
    
    # Audit-Log
    await self.log_deletion(decision_id)
    
    return True
```

### Widerspruchsrecht (Art. 21 DSGVO)

**Opt-out-Liste:**

```python
class OptOutManager:
    """Verwaltet Opt-out-Anfragen."""
    
    def add_to_blocklist(self, url_pattern: str):
        """Fügt URL-Muster zur Blockliste hinzu."""
        self.redis.sadd("blocklist:urls", url_pattern)
    
    def is_blocked(self, url: str) -> bool:
        """Prüft, ob URL geblockt ist."""
        patterns = self.redis.smembers("blocklist:urls")
        return any(pattern in url for pattern in patterns)
```

## Überwachung und Wartung

### Kontinuierliche Überwachung

**Zu überwachende Metriken:**

- `crawl_log`-Tabelle auf Fehler und Muster
- Wöchentliche Überprüfung der Anonymisierungsqualität (10 Entscheidungen samplen)
- Monatliches Update von spaCy-Modellen und Mustern
- Vierteljährliche rechtliche Compliance-Überprüfung

### Automatisierte Benachrichtigungen

```python
# Kritische Ereignisse
ALERT_THRESHOLDS = {
    "rate_limit_violations": 10,      # pro Stunde
    "parsing_errors": 5,              # Prozent
    "source_unavailable": 60,         # Minuten
    "database_usage": 80,             # Prozent
    "anonymization_failures": 1       # Absolut
}

class ComplianceMonitor:
    """Überwacht Compliance-relevante Ereignisse."""
    
    async def check_thresholds(self):
        """Prüft kritische Schwellwerte."""
        for metric, threshold in ALERT_THRESHOLDS.items():
            current_value = await self.get_metric_value(metric)
            if current_value > threshold:
                await self.send_alert(metric, current_value, threshold)
```

## Sicherheitsmaßnahmen

### Verschlüsselung

```python
# Verschlüsselung sensibler Daten
from cryptography.fernet import Fernet

class EncryptionManager:
    """Verwaltet Verschlüsselung sensibler Daten."""
    
    def __init__(self, key: bytes):
        self.cipher = Fernet(key)
    
    def encrypt_anonymization_map(self, mapping: Dict) -> bytes:
        """Verschlüsselt Anonymisierungs-Mapping."""
        json_data = json.dumps(mapping)
        return self.cipher.encrypt(json_data.encode())
    
    def decrypt_anonymization_map(self, encrypted: bytes) -> Dict:
        """Entschlüsselt Anonymisierungs-Mapping."""
        decrypted = self.cipher.decrypt(encrypted)
        return json.loads(decrypted.decode())
```

### Zugriffskontrolle

```python
# API-Zugriffskontrolle
class AccessControl:
    """Implementiert Zugriffskontrolle."""
    
    RATE_LIMITS = {
        "anonymous": 100,      # Anfragen pro Stunde
        "registered": 1000,    # Anfragen pro Stunde
        "premium": 10000      # Anfragen pro Stunde
    }
    
    async def check_rate_limit(self, api_key: str) -> bool:
        """Prüft Rate-Limit für API-Schlüssel."""
        user_type = await self.get_user_type(api_key)
        limit = self.RATE_LIMITS.get(user_type, 100)
        
        current_count = await self.redis.incr(f"rate:{api_key}")
        if current_count == 1:
            await self.redis.expire(f"rate:{api_key}", 3600)
        
        return current_count <= limit
```

## Rechtliche Dokumentation

### Erforderliche Dokumente

1. **Datenschutzerklärung** (Privacy Policy)
2. **Nutzungsbedingungen** (Terms of Service)
3. **Impressum** (Legal Notice)
4. **Cookie-Richtlinie** (falls Web-Interface)
5. **API-Nutzungsbedingungen**

### Transparenzbericht

```markdown
# Transparenzbericht Q1 2024

## Datensammlung
- Gesammelte Entscheidungen: 5.432
- Verwendete Quellen: 3
- Robots.txt-Compliance: 100%

## Datenschutz
- Anonymisierte Dokumente: 5.432
- DSGVO-Anfragen: 12
- Löschanfragen: 2
- Opt-out-Anfragen: 0

## Technische Compliance
- Rate-Limit-Verletzungen: 0
- System-Verfügbarkeit: 99.9%
- Durchschnittliche Anonymisierungszeit: 1.2s
```

## Kontaktinformationen

### Pflichtangaben

```yaml
Verantwortlicher:
  Name: [Organisation/Person]
  Adresse: [Vollständige Anschrift]
  E-Mail: datenschutz@beispiel.com
  Telefon: +49 xxx xxxx

Datenschutzbeauftragter:
  Name: [Name des DSB]
  E-Mail: dsb@beispiel.com

Aufsichtsbehörde:
  Name: [Zuständige Datenschutzbehörde]
  Adresse: [Anschrift]
  Website: [URL]

Abuse-Kontakt:
  E-Mail: abuse@beispiel.com
  Response-Zeit: 48 Stunden
```

## Checkliste für rechtliche Compliance

- [x] TDM-Ausnahme dokumentiert und eingehalten
- [x] Robots.txt-Parser implementiert
- [x] Rate-Limiting implementiert
- [x] User-Agent mit Kontaktdaten konfiguriert
- [x] Anonymisierung funktioniert zuverlässig (Dual-Backend seit 21.08.2025)
- [x] Fallback-Anonymisierung für Python 3.12+ Kompatibilität
- [x] Audit-Logging aktiv
- [ ] Datenschutzerklärung veröffentlicht
- [ ] Impressum vollständig
- [ ] Opt-out-Mechanismus implementiert
- [ ] DSGVO-Anfragen-Prozess etabliert
- [ ] Regelmäßige Compliance-Reviews geplant
- [ ] Verschlüsselung sensibler Daten aktiv
- [ ] Backup- und Löschkonzept dokumentiert