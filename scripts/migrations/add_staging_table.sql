-- Migration: Staging-Tabelle für zweistufige Filterung
-- Datum: 21.08.2025
-- Zweck: Implementierung eines zweistufigen Filtersystems für präzisere DSGVO-Relevanz-Prüfung

-- Enum für Filter-Status
CREATE TYPE filter_stage_status AS ENUM (
    'pending_stage1',    -- Wartet auf Grob-Filter
    'pending_stage2',    -- Grob-Filter bestanden, wartet auf Fein-Filter
    'approved',          -- Beide Filter bestanden, bereit für Import
    'rejected',          -- Von einem Filter abgelehnt
    'imported',          -- Erfolgreich in decisions importiert
    'review_required'    -- Manuelle Überprüfung nötig (Confidence 50-79%)
);

-- Staging-Tabelle für Kandidaten
CREATE TABLE IF NOT EXISTS decision_candidates (
    id SERIAL PRIMARY KEY,
    
    -- Quelldaten
    source VARCHAR(50) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    source_url TEXT,
    raw_data JSONB NOT NULL,  -- Komplette Rohdaten für spätere Verarbeitung
    
    -- Basis-Metadaten (aus Stage 1)
    title TEXT,
    court VARCHAR(255),
    case_number VARCHAR(255),
    decision_date DATE,
    
    -- Filter-Metriken
    stage1_score INTEGER DEFAULT 0,           -- Grob-Filter Score (0-50)
    stage1_keywords TEXT[],                    -- Gefundene Keywords in Stage 1
    stage1_processed_at TIMESTAMP,
    
    stage2_confidence DECIMAL(5,2),           -- Fein-Filter Confidence (0-100%)
    stage2_context_score DECIMAL(5,2),        -- Kontext-Analyse Score
    stage2_structure_score DECIMAL(5,2),      -- Struktur-Analyse Score
    stage2_metadata_score DECIMAL(5,2),       -- Metadaten-Analyse Score
    stage2_patterns JSONB,                    -- Detaillierte Pattern-Matches
    stage2_processed_at TIMESTAMP,
    
    -- Status-Tracking
    status filter_stage_status DEFAULT 'pending_stage1',
    rejection_reason TEXT,                    -- Grund für Ablehnung (wenn rejected)
    
    -- Verweis auf importierte Entscheidung
    decision_id INTEGER REFERENCES decisions(id),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    UNIQUE(source, source_id),
    CHECK (stage1_score >= 0 AND stage1_score <= 50),
    CHECK (stage2_confidence >= 0 AND stage2_confidence <= 100)
);

-- Indizes für Performance
CREATE INDEX idx_candidates_status ON decision_candidates(status);
CREATE INDEX idx_candidates_source ON decision_candidates(source, source_id);
CREATE INDEX idx_candidates_stage1_score ON decision_candidates(stage1_score);
CREATE INDEX idx_candidates_stage2_confidence ON decision_candidates(stage2_confidence);
CREATE INDEX idx_candidates_created ON decision_candidates(created_at);
CREATE INDEX idx_candidates_case_number ON decision_candidates(case_number);

-- Filter-Statistiken Tabelle
CREATE TABLE IF NOT EXISTS filter_statistics (
    id SERIAL PRIMARY KEY,
    date DATE DEFAULT CURRENT_DATE,
    source VARCHAR(50),
    
    -- Stage 1 Metriken
    stage1_total INTEGER DEFAULT 0,
    stage1_passed INTEGER DEFAULT 0,
    stage1_rejected INTEGER DEFAULT 0,
    stage1_avg_score DECIMAL(5,2),
    stage1_processing_time_ms INTEGER,
    
    -- Stage 2 Metriken
    stage2_total INTEGER DEFAULT 0,
    stage2_approved INTEGER DEFAULT 0,
    stage2_rejected INTEGER DEFAULT 0,
    stage2_review_required INTEGER DEFAULT 0,
    stage2_avg_confidence DECIMAL(5,2),
    stage2_processing_time_ms INTEGER,
    
    -- Gesamt-Metriken
    total_imported INTEGER DEFAULT 0,
    false_positives INTEGER DEFAULT 0,    -- Manuell markiert
    false_negatives INTEGER DEFAULT 0,    -- Manuell markiert
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(date, source)
);

-- Trigger für updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_candidates_updated_at 
    BEFORE UPDATE ON decision_candidates 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Hilfsfunktionen

-- Funktion: Kandidaten nach Stage 2 verschieben
CREATE OR REPLACE FUNCTION promote_to_stage2(candidate_id INTEGER, score INTEGER, keywords TEXT[])
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE decision_candidates
    SET 
        status = 'pending_stage2',
        stage1_score = score,
        stage1_keywords = keywords,
        stage1_processed_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = candidate_id AND status = 'pending_stage1';
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Funktion: Kandidaten genehmigen
CREATE OR REPLACE FUNCTION approve_candidate(
    candidate_id INTEGER, 
    confidence DECIMAL,
    context_score DECIMAL,
    structure_score DECIMAL,
    metadata_score DECIMAL,
    patterns JSONB
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE decision_candidates
    SET 
        status = CASE 
            WHEN confidence >= 80 THEN 'approved'
            WHEN confidence >= 50 THEN 'review_required'
            ELSE 'rejected'
        END,
        stage2_confidence = confidence,
        stage2_context_score = context_score,
        stage2_structure_score = structure_score,
        stage2_metadata_score = metadata_score,
        stage2_patterns = patterns,
        stage2_processed_at = CURRENT_TIMESTAMP,
        rejection_reason = CASE 
            WHEN confidence < 50 THEN 'Confidence Score zu niedrig: ' || confidence || '%'
            ELSE NULL
        END,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = candidate_id AND status = 'pending_stage2';
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- View für Dashboard
CREATE OR REPLACE VIEW v_filter_pipeline AS
SELECT 
    status,
    source,
    COUNT(*) as count,
    AVG(stage1_score) as avg_stage1_score,
    AVG(stage2_confidence) as avg_confidence,
    MIN(created_at) as oldest_entry,
    MAX(created_at) as newest_entry
FROM decision_candidates
GROUP BY status, source
ORDER BY status, source;

-- View für Review-Queue
CREATE OR REPLACE VIEW v_review_queue AS
SELECT 
    id,
    source,
    case_number,
    title,
    court,
    decision_date,
    stage1_score,
    stage2_confidence,
    stage2_patterns,
    created_at
FROM decision_candidates
WHERE status = 'review_required'
ORDER BY stage2_confidence DESC, created_at ASC;

-- Kommentare
COMMENT ON TABLE decision_candidates IS 'Staging-Tabelle für zweistufige Filterung von Gerichtsentscheidungen';
COMMENT ON COLUMN decision_candidates.stage1_score IS 'Grob-Filter Score (0-50), basierend auf Keyword-Matching';
COMMENT ON COLUMN decision_candidates.stage2_confidence IS 'Fein-Filter Confidence (0-100%), basierend auf Kontextanalyse';
COMMENT ON COLUMN decision_candidates.status IS 'Aktueller Status im Filter-Pipeline';
COMMENT ON TABLE filter_statistics IS 'Aggregierte Statistiken für Filter-Performance und Qualität';