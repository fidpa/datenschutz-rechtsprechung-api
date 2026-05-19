# Projektumfang (Scope)

## Was ist im Scope

### ✅ Kernfunktionalitäten (MVP)

1. **Datensammlung**
   - Web-Scraping von GDPRhub
   - API-Integration für Open Legal Data
   - API-Integration für RIS Österreich
   - Strukturierte Datenextraktion
   - Rate-Limiting und respektvolles Crawling

2. **Datenverarbeitung**
   - PDF-zu-Text-Konvertierung
   - Intelligente Anonymisierung mit Erhalt von Rechtsbegriffen
     - **Dual-Backend seit 21.08.2025**: spaCy (primär) + Regex-Fallback
     - **Python 3.12+ Support** durch SimpleGermanLegalAnonymizer
   - DSGVO-Artikel-Extraktion
   - Deutsche Rechtsdokument-Strukturanalyse
   - Metadaten-Extraktion (Gericht, Datum, Aktenzeichen)

3. **Datenspeicherung**
   - PostgreSQL mit deutscher Volltextsuche
   - Strukturierte Speicherung nach deutschem Rechtsschema
   - Audit-Logging für Compliance
   - Verschlüsselte Anonymisierungs-Mappings

4. **API & Zugriff**
   - RESTful API mit FastAPI
   - Volltextsuche
   - Filterung nach Gericht, Datum, DSGVO-Artikel
   - Export in JSON und CSV
   - Swagger/OpenAPI-Dokumentation

5. **Compliance & Sicherheit**
   - DSGVO-konforme Datenverarbeitung
   - Robots.txt-Einhaltung
   - Audit-Trail
   - Betroffenenrechte-Management

### ✅ Erweiterte Funktionen

1. **Zusätzliche Datenquellen**
   - Weitere deutsche Gerichtsportale
   - Österreichische Landesgerichte
   - EU-Datenbanken (EUR-Lex)

2. **Verbesserte Analyse**
   - Keyword-Extraktion
   - Trend-Analyse
   - Statistik-Dashboard
   - Benachrichtigungen bei neuen relevanten Entscheidungen

3. **Performance & Skalierung**
   - Celery für asynchrone Verarbeitung
   - Redis-Caching
   - Horizontale Skalierung
   - Monitoring mit Prometheus

## Was ist NICHT im Scope

### ❌ Explizit ausgeschlossen

1. **Vector-Datenbanken und Embeddings**
   - **Grund**: PostgreSQL FTS reicht für juristische Suche
   - **Alternative**: Strukturierte Volltextsuche mit deutschen Stemmern
   - **Aufwand-Nutzen**: Hohe Komplexität bei marginalem Mehrwert

2. **RAG (Retrieval Augmented Generation)**
   - **Grund**: Keine LLM-Integration erforderlich
   - **Alternative**: Traditionelle Suchmethoden
   - **Risiko**: Rechtliche Unsicherheit bei AI-generierten Inhalten

3. **Komplexe ML-Pipelines**
   - **Grund**: Regelbasierte Verarbeitung ist ausreichend
   - **Alternative**: Deterministische Muster-Erkennung
   - **Wartbarkeit**: Einfachere Systeme sind leichter zu debuggen

4. **Echtzeit-Benachrichtigungen**
   - **Grund**: Batch-Verarbeitung ist ausreichend
   - **Alternative**: Tägliche/wöchentliche Zusammenfassungen
   - **Ressourcen**: Unnötige Infrastruktur-Komplexität

5. **Mehrsprachige Unterstützung**
   - **Grund**: Fokus auf DACH-Raum
   - **Alternative**: Deutscher Content mit englischen Metadaten
   - **Phase**: Eventuell in späteren Versionen

6. **Blockchain-Integration**
   - **Grund**: Löst kein konkretes Problem
   - **Alternative**: Traditionelle Audit-Logs
   - **Komplexität**: Unverhältnismäßiger Overhead

7. **Microservices-Architektur**
   - **Grund**: Monolith ist perfekt für diese Größe
   - **Alternative**: Modularer Monolith
   - **Team-Größe**: Nicht gerechtfertigt für kleines Team

8. **GraphQL API**
   - **Grund**: REST ist ausreichend und etabliert
   - **Alternative**: RESTful API mit guter Filterung
   - **Lernkurve**: Zusätzliche Komplexität ohne klaren Nutzen

9. **Frontend-Anwendung**
   - **Grund**: API-First-Ansatz
   - **Alternative**: Swagger UI für API-Exploration
   - **Fokus**: Backend und Datenqualität priorisieren

10. **Benutzerauthentifizierung**
    - **Grund**: Öffentliche Daten, keine Personalisierung nötig
    - **Alternative**: API-Keys für Rate-Limiting
    - **Phase**: Erst bei kommerzieller Nutzung

### ❌ Technische Entscheidungen

| Technologie | Status | Grund | Alternative |
|------------|--------|-------|-------------|
| Kubernetes | ❌ | Overkill für MVP | Docker Compose |
| Elasticsearch | ❌ | Zu ressourcenintensiv | PostgreSQL FTS |
| Apache Kafka | ❌ | Keine Event-Streaming-Anforderung | Redis Queue |
| MongoDB | ❌ | Relationale Daten | PostgreSQL JSONB |
| AWS Lambda | ❌ | Vendor-Lock-in | Self-hosted |
| React/Vue/Angular | ❌ | Kein Frontend geplant | API-only |
| OAuth2/OIDC | ❌ | Keine User-Authentifizierung | API-Keys |
| gRPC | ❌ | REST ist ausreichend | FastAPI |
| Apache Spark | ❌ | Datenvolumen zu klein | Pandas/SQL |
| Neo4j | ❌ | Keine Graph-Anforderungen | PostgreSQL |

## Zukünftige Überlegungen

### 📝 Künftig zu evaluieren

1. **Schweizer Kantonsgerichte**
   - **Herausforderung**: 26 verschiedene Systeme
   - **Aufwand**: Sehr hoch
   - **Priorität**: Niedrig (wenige DSGVO-Fälle)

2. **Erweiterte Anonymisierung**
   - **Konzept**: k-Anonymität, l-Diversität
   - **Nutzen**: Höhere Datenschutz-Garantien
   - **Komplexität**: Signifikant höher

3. **Zitationsnetzwerk-Analyse**
   - **Technologie**: Neo4j oder NetworkX
   - **Nutzen**: Einflussreiche Entscheidungen identifizieren
   - **Aufwand**: Mittel bis hoch

4. **ML-basierte Klassifizierung**
   - **Anwendung**: Automatische Themen-Zuordnung
   - **Modelle**: BERT für deutsche Rechtstexte
   - **Training**: Benötigt gelabelte Daten

5. **Multi-Tenant-Architektur**
   - **Trigger**: > 10 zahlende Kunden
   - **Nutzen**: Mandantenfähigkeit
   - **Änderungen**: Datenbank-Schema, API

6. **Echtzeit-Monitoring-Dashboard**
   - **Stack**: Grafana + Prometheus
   - **Metriken**: System- und Business-KPIs
   - **Trigger**: Produktivbetrieb

### 📈 Skalierungs-Trigger

**Wann erweitern?**

| Metrik | Schwellwert | Aktion |
|--------|------------|--------|
| Entscheidungen | > 100.000 | Datenbank-Partitionierung |
| API-Anfragen | > 1000/min | Load Balancer |
| Datenquellen | > 10 | Abstraktions-Layer |
| Team-Größe | > 5 | Microservices evaluieren |
| Kunden | > 10 | Multi-Tenancy |
| Datenvolumen | > 1TB | Distributed Storage |

## Entscheidungsmatrix

### Build vs. Buy vs. Open Source

| Komponente | Entscheidung | Begründung |
|------------|--------------|------------|
| Crawler-Framework | Build | Spezifische Anforderungen |
| PDF-Extraktion | Open Source (pdfplumber) | Bewährt und zuverlässig |
| NLP/NER | Dual: spaCy + Regex | Fallback für Kompatibilität |
| Datenbank | Open Source (PostgreSQL) | Robust und feature-reich |
| API-Framework | Open Source (FastAPI) | Modern und performant |
| Task Queue | Open Source (Celery) | De-facto Standard |
| Monitoring | Open Source (Prometheus) | Industriestandard |
| OCR | Open Source (Tesseract) | Falls benötigt |

## Technische Schulden

### Akzeptierte technische Schulden (MVP)

1. **Keine automatisierten E2E-Tests**
   - **Grund**: Schnellere Entwicklung
   - **Mitigation**: Umfassende Unit-Tests
   - **Rückzahlung**: Nach MVP

5. **Reduzierte Anonymisierungs-Genauigkeit bei Fallback**
   - **Grund**: Python 3.12 Kompatibilität wichtiger als 10% Genauigkeit
   - **Mitigation**: Regex-Patterns kontinuierlich verbessern
   - **Rückzahlung**: Wenn spaCy Python 3.12 unterstützt

2. **Monolithische Architektur**
   - **Grund**: Einfachheit
   - **Mitigation**: Modularer Aufbau
   - **Rückzahlung**: Bei Bedarf

3. **Einfaches Error-Handling**
   - **Grund**: MVP-Fokus
   - **Mitigation**: Logging aller Fehler
   - **Rückzahlung**: künftige Iteration

4. **Keine CI/CD-Pipeline**
   - **Grund**: Kleines Team
   - **Mitigation**: Dokumentierte Deploy-Prozesse
   - **Rückzahlung**: Bei regelmäßigen Releases

### Nicht-akzeptable technische Schulden

1. **Fehlende Anonymisierung** - Rechtliches Risiko
2. **Keine Rate-Limits** - Gefahr von Sperrungen
3. **Kein Audit-Logging** - Compliance-Verstoß
4. **Unsichere Secrets** - Sicherheitsrisiko
5. **Keine Backups** - Datenverlust-Risiko

## Ressourcenplanung

### Minimale Ressourcen (MVP)

```yaml
Entwicklung:
  Entwickler: 1-2
  Zeitrahmen: 3-4 Monate
  
Infrastruktur:
  Server: 1x (4 CPU, 8GB RAM)
  Datenbank: PostgreSQL (50GB)
  Redis: 1GB RAM
  
Kosten:
  Hosting: ~50€/Monat
  APIs: Größtenteils kostenlos
  Domains: ~20€/Jahr
```

### Empfohlene Ressourcen (Produktion)

```yaml
Team:
  Lead Developer: 1
  Backend Developer: 1-2
  DevOps: 0.5
  
Infrastruktur:
  App-Server: 2x (8 CPU, 16GB RAM)
  DB-Server: 1x (8 CPU, 32GB RAM)
  Redis: 4GB RAM
  Backup-Storage: 500GB
  
Kosten:
  Hosting: ~300€/Monat
  Monitoring: ~50€/Monat
  Backup: ~50€/Monat
```

## Exit-Strategie

### Daten-Portabilität

- Alle Daten exportierbar (JSON/CSV)
- Dokumentierte Datenbank-Schemas
- Keine proprietären Formate
- Migrations-Skripte bereitstellen

### Vendor-Lock-in vermeiden

- Keine Cloud-spezifischen Services
- Standard-Technologien verwenden
- Container-basiertes Deployment
- Dokumentierte Abhängigkeiten

## Erfolgs-Kriterien

### MVP-Erfolg

- [ ] 1000+ Entscheidungen indexiert
- [ ] < 5% Fehlerrate bei Anonymisierung (spaCy) / < 15% (Fallback)
- [ ] 100% Verfügbarkeit der Anonymisierung (durch Dual-Backend)
- [ ] API-Response < 500ms
- [ ] 99% Uptime über 30 Tage
- [ ] Keine rechtlichen Beschwerden

### Langfrist-Erfolg

- [ ] 10.000+ Entscheidungen
- [ ] 5+ aktive API-Nutzer
- [ ] Selbsttragend (Kosten gedeckt)
- [ ] Referenz-Implementierung für TDM
- [ ] Wissenschaftliche Publikationen