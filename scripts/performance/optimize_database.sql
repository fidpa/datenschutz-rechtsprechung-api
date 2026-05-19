-- =============================================================================
-- PostgreSQL Performance-Optimierungen für Datenschutz-Rechtsprechung API
-- =============================================================================
-- Dieses Script optimiert die Datenbank für bessere Performance
-- bei 10.000+ Entscheidungen.
--
-- Ausführung:
--   psql -U dsr_user -d datenschutz_rechtsprechung_api -f optimize_database.sql
-- =============================================================================

-- =============================================================================
-- 1. ANALYSE AKTUELLE SITUATION
-- =============================================================================

-- Zeige aktuelle Tabellen-Größen
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Zeige existierende Indizes
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;

-- =============================================================================
-- 2. NEUE PERFORMANCE-INDIZES
-- =============================================================================

-- Index für häufige Zeitbereichs-Abfragen
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_created_at_desc
    ON decisions(created_at DESC)
    WHERE deleted_at IS NULL;

-- Index für Quellen-basierte Abfragen mit Datum
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_source_date
    ON decisions(source, decision_date DESC)
    WHERE deleted_at IS NULL;

-- Index für Court-basierte Abfragen
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_court_date
    ON decisions(court, decision_date DESC)
    WHERE deleted_at IS NULL;

-- Partial Index für aktuelle Entscheidungen (letzte 30 Tage)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_recent_decisions
    ON decisions(created_at)
    WHERE created_at > NOW() - INTERVAL '30 days'
    AND deleted_at IS NULL;

-- Index für DSGVO-Artikel Suche (GIN Index für Array)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_gdpr_articles_gin
    ON decisions USING gin(gdpr_articles)
    WHERE gdpr_articles IS NOT NULL;

-- Index für Status-Abfragen
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_status
    ON decisions(processing_status)
    WHERE processing_status != 'completed';

-- Composite Index für häufige Filter-Kombinationen
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_composite_filter
    ON decisions(source, court, decision_date DESC)
    WHERE deleted_at IS NULL;

-- Index für Qualitäts-Abfragen
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_quality
    ON decisions(quality_score DESC)
    WHERE quality_score IS NOT NULL;

-- =============================================================================
-- 3. CRAWL_LOGS INDIZES
-- =============================================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_crawl_logs_created_at
    ON crawl_logs(created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_crawl_logs_source_status
    ON crawl_logs(source, status, created_at DESC);

-- =============================================================================
-- 4. VOLLTEXT-SUCHE OPTIMIERUNG
-- =============================================================================

-- Stelle sicher, dass der Volltext-Index existiert
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decisions_search_vector
    ON decisions USING gin(search_vector);

-- Aktualisiere Volltext-Vektor für alle Einträge (falls nötig)
UPDATE decisions 
SET search_vector = 
    setweight(to_tsvector('german', COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('german', COALESCE(summary, '')), 'B') ||
    setweight(to_tsvector('german', COALESCE(full_text_anonymized, '')), 'C')
WHERE search_vector IS NULL;

-- =============================================================================
-- 5. TABELLEN-STATISTIKEN AKTUALISIEREN
-- =============================================================================

-- Analysiere alle Tabellen für bessere Query-Planung
ANALYZE decisions;
ANALYZE crawl_logs;
ANALYZE decision_documents;

-- =============================================================================
-- 6. VACUUM UND REINDEX
-- =============================================================================

-- Aufräumen und Speicherplatz zurückgewinnen
VACUUM (VERBOSE, ANALYZE) decisions;
VACUUM (VERBOSE, ANALYZE) crawl_logs;

-- Reindex für optimale Performance (VORSICHT: Blockiert Tabelle!)
-- Nur außerhalb der Geschäftszeiten ausführen!
-- REINDEX TABLE CONCURRENTLY decisions;
-- REINDEX TABLE CONCURRENTLY crawl_logs;

-- =============================================================================
-- 7. POSTGRESQL KONFIGURATION (Empfehlungen)
-- =============================================================================

-- Diese Einstellungen müssen als Superuser oder in postgresql.conf gesetzt werden
-- Zeige aktuelle Einstellungen:
SELECT name, setting, unit, short_desc 
FROM pg_settings 
WHERE name IN (
    'shared_buffers',
    'effective_cache_size',
    'maintenance_work_mem',
    'work_mem',
    'max_connections',
    'random_page_cost',
    'effective_io_concurrency',
    'max_parallel_workers_per_gather'
);

-- Empfohlene Einstellungen für 4GB RAM Server:
-- ALTER SYSTEM SET shared_buffers = '1GB';
-- ALTER SYSTEM SET effective_cache_size = '3GB';
-- ALTER SYSTEM SET maintenance_work_mem = '256MB';
-- ALTER SYSTEM SET work_mem = '16MB';
-- ALTER SYSTEM SET max_connections = 100;
-- ALTER SYSTEM SET random_page_cost = 1.1;  -- Für SSD
-- ALTER SYSTEM SET effective_io_concurrency = 200;  -- Für SSD
-- ALTER SYSTEM SET max_parallel_workers_per_gather = 2;

-- Autovacuum aggressiver für große Tabellen
-- ALTER SYSTEM SET autovacuum_vacuum_scale_factor = 0.05;
-- ALTER SYSTEM SET autovacuum_analyze_scale_factor = 0.05;
-- ALTER SYSTEM SET autovacuum_vacuum_cost_delay = 10;

-- Nach Änderungen: SELECT pg_reload_conf();

-- =============================================================================
-- 8. MONITORING QUERIES
-- =============================================================================

-- Langsame Queries identifizieren (benötigt pg_stat_statements Extension)
-- CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Top 10 langsamste Queries
-- SELECT 
--     round(total_exec_time::numeric, 2) AS total_time_ms,
--     calls,
--     round(mean_exec_time::numeric, 2) AS mean_time_ms,
--     round((100 * total_exec_time / sum(total_exec_time) OVER ())::numeric, 2) AS percentage,
--     regexp_replace(query, '\s+', ' ', 'g') AS query_text
-- FROM pg_stat_statements
-- ORDER BY total_exec_time DESC
-- LIMIT 10;

-- =============================================================================
-- 9. CACHE HIT RATIO
-- =============================================================================

-- Prüfe Cache-Effizienz (sollte > 95% sein)
SELECT 
    sum(heap_blks_read) as heap_read,
    sum(heap_blks_hit) as heap_hit,
    CASE 
        WHEN sum(heap_blks_hit) + sum(heap_blks_read) > 0
        THEN round(sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read))::numeric * 100, 2)
        ELSE 0
    END as cache_hit_ratio
FROM pg_statio_user_tables;

-- =============================================================================
-- 10. INDEX USAGE
-- =============================================================================

-- Zeige ungenutzte Indizes (Kandidaten zum Löschen)
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

-- Zeige Tabellen die möglicherweise zusätzliche Indizes brauchen
SELECT
    schemaname,
    tablename,
    seq_scan,
    seq_tup_read,
    idx_scan,
    seq_scan::numeric / NULLIF(idx_scan, 0) AS seq_to_idx_ratio
FROM pg_stat_user_tables
WHERE seq_scan > 100
ORDER BY seq_scan::numeric / NULLIF(idx_scan, 1) DESC;

-- =============================================================================
-- ENDE - Performance-Optimierungen abgeschlossen
-- =============================================================================

-- Zusammenfassung der Änderungen
SELECT 
    'Neue Indizes erstellt' AS action,
    COUNT(*) AS count
FROM pg_indexes
WHERE schemaname = 'public'
AND indexname LIKE 'idx_%';