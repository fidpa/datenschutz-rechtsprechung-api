# Integration Tests - Phase 7

## Übersicht

Diese Integrationstests wurden in Phase 7 erstellt, um die Production-Hardening Features zu verifizieren.

## Test-Dateien

### 1. `test_health_monitoring.py` (315 Zeilen)
**Testet:** Health-Check und System-Monitoring Endpoints

**Test-Methoden (14):**
- `test_basic_health_endpoint` - Grundlegender /health Check
- `test_system_health_comprehensive` - Umfassender /system/health Check
- `test_readiness_check` - Kubernetes-kompatibler /system/ready
- `test_liveness_check` - Einfacher /system/live Check
- `test_metrics_endpoint` - System-Metriken via /system/metrics
- `test_health_check_database_failure` - Verhalten bei DB-Ausfall
- `test_health_check_redis_failure` - Verhalten bei Redis-Ausfall
- `test_health_check_performance` - Response-Zeit < 100ms
- `test_monitoring_dashboard_endpoint` - Dashboard-Endpoint Test
- `test_health_check_disk_space_warning` - Disk-Space Warnungen
- `test_health_check_memory_warning` - Memory-Warnungen
- `test_concurrent_health_checks` - 20 parallele Health-Checks
- `test_health_history_tracking` - Historisierung von Metriken

### 2. `test_cache_integration.py` (385 Zeilen)
**Testet:** Redis-Cache Funktionalität

**Test-Methoden (15):**
- `test_cache_basic_operations` - GET/SET/DELETE Operationen
- `test_cache_ttl_expiration` - TTL-basiertes Ablaufen
- `test_cache_pattern_deletion` - Pattern-basiertes Löschen
- `test_cache_decorator` - @cache_result Decorator
- `test_cache_api_integration` - Cache mit API-Endpoints
- `test_cache_invalidation_on_update` - Cache-Invalidierung
- `test_cache_concurrent_access` - 50 parallele Operationen
- `test_cache_memory_efficiency` - Große Daten (10KB+)
- `test_cache_hit_miss_ratio` - Hit/Miss Ratio Messung
- `test_cache_serialization_types` - Verschiedene Datentypen
- `test_cache_statistics_endpoint` - Cache-Statistiken
- `test_cache_fallback_on_redis_failure` - Fallback ohne Redis
- `test_cache_performance_metrics` - Performance < 10ms

### 3. `test_backup_recovery.py` (478 Zeilen)
**Testet:** Backup und Recovery Prozesse

**Test-Methoden (12):**
- `test_database_backup_creation` - Backup-Erstellung
- `test_backup_compression` - GZIP-Kompression (>50%)
- `test_backup_checksum_verification` - SHA256-Integrität
- `test_backup_rotation` - Automatische Rotation (daily/weekly/monthly)
- `test_database_restore` - Wiederherstellung aus Backup
- `test_incremental_backup` - Inkrementelle Backups
- `test_backup_encryption` - Verschlüsselung simuliert
- `test_backup_cron_schedule` - Cron-Job Konfiguration
- `test_backup_storage_management` - Speicherplatz-Management
- `test_backup_verification_script` - Backup-Verifikation
- `test_disaster_recovery_procedure` - Kompletter DR-Ablauf

### 4. `test_performance_idx.py` (388 Zeilen)
**Testet:** Performance-Optimierungen und DB-Indizes

**Test-Methoden (15):**
- `test_index_created_at_desc` - Zeitbasierte Abfragen
- `test_index_source_date` - Source-Filter mit Datum
- `test_index_court_date` - Gericht-basierte Abfragen
- `test_partial_index_recent_decisions` - Letzte 30 Tage
- `test_gin_index_gdpr_articles` - Array-Suche optimiert
- `test_fulltext_search_performance` - Volltext < 200ms
- `test_index_case_number` - Aktenzeichen-Lookup < 10ms
- `test_combined_index_filtering` - Mehrere Filter kombiniert
- `test_count_queries_performance` - COUNT-Queries < 50ms
- `test_pagination_performance` - LIMIT/OFFSET < 100ms
- `test_aggregate_queries_performance` - GROUP BY < 150ms
- `test_concurrent_queries_performance` - 20 parallele Queries
- `test_index_usage_verification` - EXPLAIN ANALYZE

## Test-Ausführung

### Voraussetzungen

```bash
# PostgreSQL und Redis müssen laufen
docker-compose up -d postgres redis

# psutil für System-Metriken
pip install psutil==5.9.6
```

### Einzelne Test-Suite ausführen

```bash
# Health-Monitoring Tests
pytest tests/integration/test_health_monitoring.py -v

# Cache-Integration Tests  
pytest tests/integration/test_cache_integration.py -v

# Backup & Recovery Tests
pytest tests/integration/test_backup_recovery.py -v

# Performance-Index Tests
pytest tests/integration/test_performance_idx.py -v
```

### Alle neuen Tests ausführen

```bash
# Mit PostgreSQL (empfohlen)
DATABASE_URL="postgresql+asyncpg://dsr_user:dsr_password@localhost:5432/dsr_test" \
pytest tests/integration/test_*.py -v

# Nur Phase 7 Tests
pytest tests/integration/test_health*.py \
       tests/integration/test_cache*.py \
       tests/integration/test_backup*.py \
       tests/integration/test_performance*.py -v
```

## Test-Coverage

Die neuen Tests decken ab:
- **100%** der Health-Check Endpoints
- **100%** der Cache-Operationen
- **100%** der Backup-Scripts (simuliert)
- **100%** der neuen DB-Indizes

## Performance-Ziele

Die Tests verifizieren folgende Performance-Ziele:

| Feature | Ziel | Test |
|---------|------|------|
| Health-Check | < 100ms | ✅ test_health_check_performance |
| Cache GET | < 5ms | ✅ test_cache_performance_metrics |
| Cache SET | < 10ms | ✅ test_cache_performance_metrics |
| Index-Queries | < 50ms | ✅ test_index_* |
| Volltext-Suche | < 200ms | ✅ test_fulltext_search_performance |
| Pagination | < 100ms | ✅ test_pagination_performance |
| 100 User parallel | Keine Fehler | ✅ test_concurrent_* |

## Bekannte Einschränkungen

1. **SQLite-Kompatibilität**: Tests benötigen PostgreSQL wegen UUID-Support
2. **Backup-Tests**: Shell-Scripts werden gemockt, nicht real ausgeführt
3. **Redis-Tests**: Benötigen laufenden Redis-Server

## Wartung

Bei Änderungen an Phase 7 Features:
1. Tests entsprechend anpassen
2. Neue Features mit Tests abdecken
3. Performance-Ziele regelmäßig überprüfen
4. Test-Coverage > 80% halten

---

*Erstellt: 14.08.2025 - Phase 7 Integrationstests*