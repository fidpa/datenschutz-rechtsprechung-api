# 🗄️ Datenbank-Schema

> PostgreSQL-Struktur und Indexierung für die Datenschutz-Rechtsprechung API

## 📊 Schema-Übersicht

Die Datenschutz-Rechtsprechung API verwendet **PostgreSQL 15+** mit deutscher Volltext-Suche-Unterstützung.

### Haupttabelle: `decisions`

```sql
CREATE TABLE decisions (
    id SERIAL PRIMARY KEY,
    
    -- Metadaten
    title VARCHAR(500) NOT NULL,
    court VARCHAR(200),
    date DATE,
    decision_type VARCHAR(100),
    case_number VARCHAR(200),
    
    -- Content
    full_text TEXT,
    full_text_anonymized TEXT NOT NULL,
    pdf_url VARCHAR(500),
    source_url VARCHAR(500) NOT NULL,
    
    -- GDPR-spezifisch
    gdpr_articles TEXT[],
    data_categories TEXT[],
    legal_basis TEXT[],
    
    -- Verarbeitung
    source VARCHAR(50) NOT NULL,
    language VARCHAR(10) DEFAULT 'de',
    processed_at TIMESTAMP DEFAULT NOW(),
    
    -- Qualität & Feedback
    quality_score INTEGER CHECK (quality_score >= 1 AND quality_score <= 5),
    user_feedback JSONB,
    
    -- Rechtskraft
    is_final BOOLEAN DEFAULT NULL,
    appeal_status VARCHAR(50),
    
    -- Struktur (Deutsche Rechtsdokumente)
    leitsatz TEXT,
    tenor TEXT,
    tatbestand TEXT,
    entscheidungsgruende TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## 🚀 Performance-Indizes

### Volltext-Suche (Kritisch für Performance)
```sql
-- Hauptindex für deutsche Volltext-Suche
CREATE INDEX idx_decisions_fts 
ON decisions 
USING gin(to_tsvector('german', full_text_anonymized));

-- Titel-Suche
CREATE INDEX idx_decisions_title_fts 
ON decisions 
USING gin(to_tsvector('german', title));
```

### Standard-Indizes
```sql
-- Häufige Filter
CREATE INDEX idx_decisions_source ON decisions(source);
CREATE INDEX idx_decisions_court ON decisions(court);
CREATE INDEX idx_decisions_date ON decisions(date);
CREATE INDEX idx_decisions_decision_type ON decisions(decision_type);

-- GDPR-spezifische Suche
CREATE INDEX idx_decisions_gdpr_articles ON decisions USING gin(gdpr_articles);
CREATE INDEX idx_decisions_data_categories ON decisions USING gin(data_categories);

-- Composite-Index für häufige Kombinationen
CREATE INDEX idx_decisions_source_date ON decisions(source, date DESC);
CREATE INDEX idx_decisions_court_date ON decisions(court, date DESC);
```

### Unique-Constraints
```sql
-- Deduplizierung
CREATE UNIQUE INDEX idx_decisions_url_unique ON decisions(source_url);

-- Fallnummer-Deduplizierung (wenn verfügbar)
CREATE INDEX idx_decisions_case_unique 
ON decisions(court, case_number, date) 
WHERE case_number IS NOT NULL;
```

## 📈 Datenbank-Metriken

### Aktuelle Größe (Stand: 14.08.2025)
- **250.324 Entscheidungen** in `decisions` Tabelle
- **~8GB** Datenbank-Größe (inkl. Indizes)
- **~3GB** Volltext-Index-Größe
- **99.2% Deduplizierungs-Rate**

### Performance-Kennzahlen
```sql
-- Query-Performance testen
EXPLAIN ANALYZE 
SELECT title, court, date 
FROM decisions 
WHERE to_tsvector('german', full_text_anonymized) @@ to_tsquery('german', 'Datenschutz');

-- Typisches Ergebnis: ~45ms für 250k+ Dokumente
```

## 🔍 Volltext-Suche Details

### Deutsche Stemmer-Konfiguration
```sql
-- Stemming-Test
SELECT to_tsvector('german', 'Datenschützer verarbeiten personenbezogene Daten');
-- Ergebnis: 'dat':2 'datenschutz':1 'personenbezog':3 'verarbeit':2
```

### Such-Ranking
```sql
-- Relevanz-Ranking mit ts_rank
SELECT 
    title,
    ts_rank(to_tsvector('german', full_text_anonymized), 
            to_tsquery('german', 'DSGVO & Einwilligung')) as rank
FROM decisions 
WHERE to_tsvector('german', full_text_anonymized) @@ 
      to_tsquery('german', 'DSGVO & Einwilligung')
ORDER BY rank DESC;
```

## 🗂️ Hilfstabellen

### User Management
```sql
-- Benutzer-Tabelle
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP WITH TIME ZONE,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Password-Reset-Tokens
CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Monitoring Tables
```sql
-- Claude Code Health Analysis
CREATE TABLE claude_health_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    health_score FLOAT NOT NULL,
    status VARCHAR(20) NOT NULL, -- healthy/degraded/unhealthy/critical
    component_scores JSONB,
    analysis_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Performance Monitoring
CREATE TABLE performance_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component VARCHAR(50) NOT NULL,
    metric_type VARCHAR(50) NOT NULL, -- response_time, error_rate, etc.
    value FLOAT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

-- Event Logging für Claude Integration
CREATE TABLE system_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL, -- critical/high/medium/low
    event_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Audit & Compliance (Phases 1-12)
```sql
-- Crawl-Logs
CREATE TABLE crawl_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    total_fetched INTEGER DEFAULT 0,
    total_processed INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,
    error_details JSONB,
    status VARCHAR(50) DEFAULT 'running'
);

-- Anonymisierungs-Mappings (verschlüsselt)
CREATE TABLE anonymization_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID REFERENCES decisions(id) ON DELETE CASCADE,
    placeholder VARCHAR(100) NOT NULL,
    original_hash VARCHAR(64) NOT NULL, -- SHA-256 Hash
    entity_type VARCHAR(50) NOT NULL, -- person, organization, location
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Crawler State für Resume-Funktionalität
CREATE TABLE crawl_state (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) UNIQUE NOT NULL,
    state_data JSONB NOT NULL,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Lookup-Tabellen (zukünftige Normalisierung)
```sql
-- Courts-Tabelle (geplant)
CREATE TABLE courts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    abbreviation VARCHAR(20),
    type VARCHAR(50), -- BGH, OLG, LG, AG
    location VARCHAR(100)
);

-- Legal-Basis-Tabelle (geplant)
CREATE TABLE legal_articles (
    id SERIAL PRIMARY KEY,
    law VARCHAR(50), -- DSGVO, BDSG, etc.
    article VARCHAR(20), -- Art. 6, § 7, etc.
    description TEXT
);
```

## 📊 Monitoring-Views

### Datenqualität-Monitoring
```sql
-- View für Datenqualität-Dashboard
CREATE VIEW data_quality_stats AS
SELECT 
    source,
    COUNT(*) as total_decisions,
    COUNT(full_text_anonymized) as anonymized_count,
    COUNT(pdf_url) as pdf_count,
    AVG(quality_score) as avg_quality,
    COUNT(CASE WHEN gdpr_articles IS NOT NULL THEN 1 END) as gdpr_tagged
FROM decisions 
GROUP BY source;
```

### Performance-Monitoring
```sql
-- Index-Usage-Statistiken
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes 
WHERE tablename = 'decisions'
ORDER BY idx_tup_read DESC;
```

## 🔧 Maintenance-Scripts

### Vacuum & Analyze (Wöchentlich)
```sql
-- Performance optimieren
VACUUM ANALYZE decisions;

-- Volltext-Indizes neu aufbauen (monatlich)
REINDEX INDEX idx_decisions_fts;
```

### Partitionierung (bei >1M Datensätzen)
```sql
-- Partitionierung nach Jahr (geplant)
CREATE TABLE decisions_2024 PARTITION OF decisions
FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE decisions_2025 PARTITION OF decisions
FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
```

## 🚨 Backup & Recovery

### Backup-Strategien
```bash
# Täglich: Vollbackup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Inkrementell: WAL-Archivierung
# archive_mode = on
# archive_command = 'cp %p /backup/wal/%f'
```

### Recovery-Szenarien
```bash
# Point-in-Time Recovery
pg_basebackup -D /backup/base -P -W

# Restore from backup
psql $DATABASE_URL < backup_20250814.sql
```

## 📈 Skalierungs-Strategien

### Horizontale Skalierung (>500k Dokumente)
- **Read-Replicas**: Für Such-Queries
- **Sharding**: Nach Quelle oder Jahr
- **Connection-Pooling**: PgBouncer

### Vertikale Skalierung
```sql
-- Arbeitspeicher-Optimierung
SET shared_buffers = '2GB';
SET work_mem = '256MB';
SET maintenance_work_mem = '1GB';
```

---

[← Zurück zur Architektur-Übersicht](README.md) | [API-Design →](API_DESIGN.md)