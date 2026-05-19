"""
Zentrale Konfiguration für den Datenschutz-Rechtsprechung API.
Verwendet pydantic für Type-Safety und Validierung.
"""

from typing import List, Optional
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator


class Settings(BaseSettings):
    """Hauptkonfigurationsklasse mit Validierung."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # =============================================================================
    # DATENBANK
    # =============================================================================
    database_url: str = Field(
        default="postgresql+asyncpg://dsr_user:dsr_password@localhost:5432/datenschutz_rechtsprechung_api",
        description="Async PostgreSQL Verbindungs-URL",
    )
    database_url_sync: str = Field(
        default="postgresql://dsr_user:dsr_password@localhost:5432/datenschutz_rechtsprechung_api",
        description="Synchrone PostgreSQL URL für Migrationen",
    )
    database_pool_size: int = Field(default=20, ge=5, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=50)
    database_echo: bool = Field(default=False)

    # =============================================================================
    # REDIS
    # =============================================================================
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis URL für Cache und Task Queue"
    )
    redis_cache_ttl: int = Field(default=3600, ge=60, description="Cache TTL in Sekunden")

    # =============================================================================
    # API
    # =============================================================================
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_reload: bool = Field(default=True)
    api_workers: int = Field(default=4, ge=1, le=16)
    api_cors_origins: List[str] = Field(default=["http://localhost:3000", "http://localhost:8000"])

    # =============================================================================
    # CRAWLER RATE LIMITS (Anfragen pro Sekunde)
    # =============================================================================
    gdprhub_rate_limit: float = Field(
        default=0.5, ge=0.1, le=10.0, description="GDPRhub Rate Limit (max 0.5 req/s empfohlen)"
    )
    openlegaldata_rate_limit: float = Field(
        default=3.0, ge=0.1, le=10.0, description="OpenLegalData Rate Limit"
    )
    ris_austria_rate_limit: float = Field(
        default=5.0, ge=0.1, le=10.0, description="RIS Austria Rate Limit"
    )

    # =============================================================================
    # CRAWLER TIMEOUTS
    # =============================================================================
    default_crawler_timeout: int = Field(
        default=30, ge=5, le=300, description="Standard Timeout für HTTP Requests in Sekunden"
    )
    pdf_processing_timeout: int = Field(
        default=60, ge=10, le=600, description="Timeout für PDF-Verarbeitung in Sekunden"
    )

    # =============================================================================
    # RETRY KONFIGURATION
    # =============================================================================
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay: int = Field(
        default=5, ge=1, le=60, description="Wartezeit zwischen Retries in Sekunden"
    )

    # =============================================================================
    # EXTERNE APIs
    # =============================================================================
    ris_austria_api_key: Optional[str] = Field(default=None)

    # =============================================================================
    # ANONYMISIERUNG
    # =============================================================================
    anonymization_enabled: bool = Field(default=True)
    preserve_legal_terms: bool = Field(default=True)
    anonymization_cache_size: int = Field(default=1000, ge=100, le=10000)
    preserve_legal_terms_list: List[str] = Field(
        default=[
            "Kläger",
            "Beklagter",
            "Antragsteller",
            "Antragsgegner",
            "BGH",
            "OLG",
            "LG",
            "AG",
            "VG",
            "OVG",
            "BVerwG",
            "EuGH",
            "EGMR",
            "BVerfG",
        ],
        description="Rechtsbegriffe die NICHT anonymisiert werden",
    )

    # =============================================================================
    # PDF VERARBEITUNG
    # =============================================================================
    max_pdf_size_mb: int = Field(default=10, ge=1, le=100, description="Maximale PDF-Größe in MB")
    pdf_max_pages: int = Field(
        default=100, ge=10, le=500, description="Maximale Anzahl Seiten pro PDF"
    )
    pdf_ocr_enabled: bool = Field(default=False, description="OCR für gescannte PDFs aktivieren")

    # =============================================================================
    # FEEDBACK & QUALITÄT
    # =============================================================================
    enable_quality_feedback: bool = Field(
        default=False, description="Aktiviert Quality Score und Feedback-System"
    )
    min_quality_score: int = Field(
        default=1, ge=1, le=5, description="Minimaler Quality Score (Sterne)"
    )
    max_quality_score: int = Field(
        default=5, ge=1, le=5, description="Maximaler Quality Score (Sterne)"
    )

    # =============================================================================
    # EXPORT
    # =============================================================================
    export_formats: List[str] = Field(
        default=["json", "csv", "excel"], description="Verfügbare Export-Formate"
    )
    export_max_rows: int = Field(
        default=10000, ge=100, le=100000, description="Maximale Anzahl Zeilen pro Export"
    )
    excel_template_path: Optional[str] = Field(
        default=None, description="Pfad zur Excel-Vorlage (optional)"
    )

    # =============================================================================
    # LOGGING
    # =============================================================================
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_format: str = Field(default="json", pattern="^(json|plain)$")
    log_file_path: Optional[str] = Field(default="logs/datenschutz_rechtsprechung_api.log")
    log_file_max_bytes: int = Field(default=10485760, ge=1048576)  # Min 1MB
    log_file_backup_count: int = Field(default=5, ge=1, le=20)
    log_show_sql: bool = Field(default=False)

    # =============================================================================
    # CELERY
    # =============================================================================
    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")
    celery_task_time_limit: int = Field(default=3600, ge=60)
    celery_task_soft_time_limit: int = Field(default=3300, ge=60)
    celery_worker_concurrency: int = Field(default=4, ge=1, le=16)

    # =============================================================================
    # SICHERHEIT
    # =============================================================================
    secret_key: str = Field(
        default="change-this-to-a-secure-random-string-in-production", min_length=32
    )
    allowed_hosts: List[str] = Field(default=["localhost", "127.0.0.1"])
    secure_cookies: bool = Field(default=False)

    # =============================================================================
    # MONITORING
    # =============================================================================
    enable_metrics: bool = Field(default=True)
    metrics_port: int = Field(default=9090, ge=1, le=65535)
    health_check_path: str = Field(default="/health")
    sentry_dsn: Optional[str] = Field(default=None)

    # =============================================================================
    # ENTWICKLUNG
    # =============================================================================
    debug: bool = Field(default=True)
    testing: bool = Field(default=False)
    environment: str = Field(default="development", pattern="^(development|staging|production)$")

    # =============================================================================
    # FLASK WEB-UI (Phase 8)
    # =============================================================================
    flask_secret_key: str = Field(default="dev-secret-key-change-in-production")
    flask_env: str = Field(default="development")
    web_ui_port: int = Field(default=5001, ge=1, le=65535)
    fastapi_base_url: str = Field(default="http://localhost:8000")
    api_timeout: int = Field(default=30, ge=5, le=300)
    api_max_retries: int = Field(default=3, ge=1, le=10)

    # =============================================================================
    # LOGGING
    # =============================================================================
    log_file: Optional[str] = Field(default="/tmp/datenschutz_rechtsprechung_api.log")

    # =============================================================================
    # CELERY ERWEITERT
    # =============================================================================
    celery_task_serializer: str = Field(default="json")
    celery_accept_content: List[str] = Field(default=["json"])
    celery_result_serializer: str = Field(default="json")
    celery_timezone: str = Field(default="Europe/Berlin")
    celery_enable_utc: bool = Field(default=True)

    # =============================================================================
    # SPEICHER & CACHE
    # =============================================================================
    max_cache_size_mb: int = Field(default=500, ge=50, le=5000)
    temp_files_path: str = Field(default="/tmp/datenschutz_rechtsprechung_api")

    # =============================================================================
    # CRAWL SCHEDULING (Cron-Expressions)
    # =============================================================================
    gdprhub_crawl_schedule: str = Field(default="0 2 * * *", description="Cron für GDPRhub Crawl")
    openlegaldata_crawl_schedule: str = Field(
        default="0 3 * * *", description="Cron für OpenLegalData Crawl"
    )
    ris_crawl_schedule: str = Field(default="0 4 * * 1", description="Cron für RIS Crawl")

    # =============================================================================
    # VOLLTEXT-SUCHE
    # =============================================================================
    postgres_text_search_config: str = Field(
        default="german", description="PostgreSQL Text-Such-Konfiguration"
    )
    min_search_word_length: int = Field(default=3, ge=2, le=10)
    max_search_results: int = Field(default=1000, ge=10, le=10000)

    # =============================================================================
    # EXPORT
    # =============================================================================
    max_export_rows: int = Field(default=10000, ge=100, le=100000)
    export_formats: str = Field(default="json,csv,xlsx")

    @validator("export_formats")
    def validate_export_formats(cls, v: str) -> List[str]:
        """Konvertiert komma-getrennte Export-Formate in Liste."""
        formats = [f.strip().lower() for f in v.split(",")]
        valid_formats = {"json", "csv", "xlsx", "xml"}
        for fmt in formats:
            if fmt not in valid_formats:
                raise ValueError(f"Ungültiges Export-Format: {fmt}")
        return formats

    @validator("celery_accept_content", pre=True)
    def validate_celery_accept_content(cls, v):
        """Konvertiert String-Liste von .env in echte Liste."""
        if isinstance(v, str):
            # Entferne eckige Klammern und parse als JSON
            import json

            try:
                return json.loads(v)
            except:
                return ["json"]
        return v

    @validator("secret_key")
    def validate_secret_key(cls, v: str, values: dict) -> str:
        """Warnt vor unsicherem Secret Key in Produktion."""
        if (
            values.get("environment") == "production"
            and v == "change-this-to-a-secure-random-string-in-production"
        ):
            raise ValueError("Unsicherer Secret Key in Produktionsumgebung!")
        return v

    @property
    def is_production(self) -> bool:
        """Prüft ob Produktionsumgebung."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Prüft ob Entwicklungsumgebung."""
        return self.environment == "development"

    @property
    def rate_limits(self) -> dict:
        """Gibt Rate Limits als Dictionary zurück."""
        return {
            "gdprhub": self.gdprhub_rate_limit,
            "openlegaldata": self.openlegaldata_rate_limit,
            "ris_austria": self.ris_austria_rate_limit,
        }

    def get_delay_for_source(self, source: str) -> float:
        """Berechnet Verzögerung basierend auf Rate Limit."""
        rate_limit = self.rate_limits.get(source.lower(), 1.0)
        return 1.0 / rate_limit if rate_limit > 0 else 1.0


@lru_cache()
def get_settings() -> Settings:
    """
    Cached Settings-Instanz.
    Verwende diese Funktion für Dependency Injection.
    """
    return Settings()


# Globale Settings-Instanz für einfachen Zugriff
settings = get_settings()
