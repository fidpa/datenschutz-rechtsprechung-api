"""
Configuration Management für Claude Code Logging System.

Environment-based Configuration mit intelligent defaults
und Production-ready settings.
"""

from typing import Dict, Optional
from pathlib import Path
from pydantic import BaseModel, Field, validator
from enum import Enum
import os


class LogLevel(str, Enum):
    """Log levels for the enterprise logging system."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StorageBackendType(str, Enum):
    """Available storage backends."""

    JSONL = "jsonl"
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    HYBRID = "hybrid"  # JSONL + Database


class AnalysisMode(str, Enum):
    """Claude analysis modes."""

    REALTIME = "realtime"
    BATCH = "batch"
    HYBRID = "hybrid"


class LoggingConfig(BaseModel):
    """
    Zentrale Konfiguration für das Enterprise Logging System.

    Optimiert für:
    - Environment-based Configuration
    - Production-ready Defaults
    - Claude Code Integration
    - Future Scalability
    """

    # =============================================================================
    # CORE LOGGING SETTINGS
    # =============================================================================

    log_level: LogLevel = Field(default=LogLevel.INFO, description="Minimum log level to process")

    enable_performance_logging: bool = Field(
        default=True, description="Enable performance monitoring"
    )

    enable_business_logging: bool = Field(
        default=True, description="Enable business event tracking"
    )

    enable_error_tracking: bool = Field(
        default=True, description="Enable comprehensive error tracking"
    )

    # =============================================================================
    # STORAGE CONFIGURATION
    # =============================================================================

    storage_backend: StorageBackendType = Field(
        default=StorageBackendType.JSONL, description="Primary storage backend"
    )

    storage_path: Path = Field(
        default=Path("data/logs/claude_logging"), description="Storage directory for logs"
    )

    jsonl_file_pattern: str = Field(
        default="{date}_{component}_{category}.jsonl", description="JSONL file naming pattern"
    )

    max_file_size_mb: int = Field(
        default=100, ge=10, le=1000, description="Maximum JSONL file size before rotation"
    )

    retention_days: int = Field(
        default=30, ge=1, le=365, description="Log retention period in days"
    )

    # =============================================================================
    # CLAUDE ANALYSIS CONFIGURATION
    # =============================================================================

    claude_analysis_mode: AnalysisMode = Field(
        default=AnalysisMode.BATCH, description="Claude analysis execution mode"
    )

    claude_analysis_interval_minutes: int = Field(
        default=60, ge=5, le=1440, description="Interval for batch analysis in minutes"
    )

    claude_priority_threshold: int = Field(
        default=50, ge=0, le=100, description="Minimum priority score for Claude analysis"
    )

    enable_predictive_analysis: bool = Field(
        default=True, description="Enable predictive pattern detection"
    )

    # =============================================================================
    # PERFORMANCE SETTINGS
    # =============================================================================

    max_events_per_second: int = Field(
        default=1000, ge=100, le=10000, description="Maximum events processed per second"
    )

    batch_size: int = Field(
        default=100, ge=10, le=1000, description="Event batch size for processing"
    )

    async_processing: bool = Field(default=True, description="Enable asynchronous event processing")

    buffer_size: int = Field(
        default=10000, ge=1000, le=100000, description="In-memory event buffer size"
    )

    # =============================================================================
    # MIDDLEWARE CONFIGURATION
    # =============================================================================

    enable_flask_middleware: bool = Field(
        default=True, description="Enable Flask request/response logging"
    )

    enable_fastapi_middleware: bool = Field(
        default=True, description="Enable FastAPI performance monitoring"
    )

    enable_celery_middleware: bool = Field(
        default=True, description="Enable Celery task monitoring"
    )

    enable_database_middleware: bool = Field(
        default=True, description="Enable database query logging"
    )

    # =============================================================================
    # PERFORMANCE THRESHOLDS
    # =============================================================================

    slow_request_threshold_ms: int = Field(
        default=1000, ge=100, le=10000, description="Threshold for slow request detection (ms)"
    )

    critical_response_time_ms: int = Field(
        default=5000, ge=1000, le=30000, description="Critical response time threshold (ms)"
    )

    high_memory_threshold_mb: int = Field(
        default=500, ge=100, le=2000, description="High memory usage threshold (MB)"
    )

    high_cpu_threshold_percent: int = Field(
        default=80, ge=50, le=95, description="High CPU usage threshold (%)"
    )

    # =============================================================================
    # SECURITY & PRIVACY
    # =============================================================================

    enable_pii_detection: bool = Field(
        default=True, description="Enable PII detection and redaction"
    )

    anonymize_user_data: bool = Field(
        default=True, description="Anonymize user identifiers in logs"
    )

    log_request_bodies: bool = Field(
        default=False, description="Log HTTP request bodies (security risk)"
    )

    log_response_bodies: bool = Field(
        default=False, description="Log HTTP response bodies (security risk)"
    )

    # =============================================================================
    # INTEGRATION SETTINGS
    # =============================================================================

    enable_health_monitoring: bool = Field(
        default=True, description="Enable system health monitoring"
    )

    enable_metrics_export: bool = Field(
        default=True, description="Enable metrics export for monitoring"
    )

    integration_endpoints: Dict[str, str] = Field(
        default_factory=dict, description="External integration endpoints"
    )

    # =============================================================================
    # ENVIRONMENT CONFIGURATION
    # =============================================================================

    environment: str = Field(default="development", description="Deployment environment")

    debug_mode: bool = Field(default=True, description="Enable debug features")

    enable_console_output: bool = Field(default=True, description="Enable console log output")

    @validator("storage_path")
    def validate_storage_path(cls, v: Path) -> Path:
        """Ensure storage directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    @validator("environment")
    def validate_environment(cls, v: str) -> str:
        """Validate environment setting."""
        valid_envs = ["development", "staging", "production"]
        if v not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"

    def get_storage_file_path(self, component: str, category: str) -> Path:
        """Generate storage file path for component and category."""
        from datetime import datetime

        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = self.jsonl_file_pattern.format(
            date=date_str, component=component, category=category
        )
        return self.storage_path / filename

    def should_analyze_with_claude(self, priority_score: int) -> bool:
        """Determine if event should be analyzed by Claude."""
        return priority_score >= self.claude_priority_threshold

    def get_performance_thresholds(self) -> Dict[str, int]:
        """Get all performance thresholds as dictionary."""
        return {
            "slow_request_ms": self.slow_request_threshold_ms,
            "critical_response_ms": self.critical_response_time_ms,
            "high_memory_mb": self.high_memory_threshold_mb,
            "high_cpu_percent": self.high_cpu_threshold_percent,
        }


def load_config_from_env() -> LoggingConfig:
    """
    Load configuration from environment variables.

    Environment variables:
    - CLAUDE_LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - CLAUDE_STORAGE_BACKEND: Storage backend (jsonl, postgresql, redis, hybrid)
    - CLAUDE_STORAGE_PATH: Storage directory path
    - CLAUDE_ANALYSIS_MODE: Analysis mode (realtime, batch, hybrid)
    - CLAUDE_ENVIRONMENT: Environment (development, staging, production)
    - etc.
    """
    env_config = {}

    # Map environment variables to config fields
    env_mappings = {
        "CLAUDE_LOG_LEVEL": "log_level",
        "CLAUDE_STORAGE_BACKEND": "storage_backend",
        "CLAUDE_STORAGE_PATH": "storage_path",
        "CLAUDE_ANALYSIS_MODE": "claude_analysis_mode",
        "CLAUDE_ENVIRONMENT": "environment",
        "CLAUDE_DEBUG_MODE": "debug_mode",
        "CLAUDE_ASYNC_PROCESSING": "async_processing",
        "CLAUDE_ENABLE_PERFORMANCE": "enable_performance_logging",
        "CLAUDE_ENABLE_BUSINESS": "enable_business_logging",
        "CLAUDE_PRIORITY_THRESHOLD": "claude_priority_threshold",
        "CLAUDE_SLOW_THRESHOLD_MS": "slow_request_threshold_ms",
        "CLAUDE_RETENTION_DAYS": "retention_days",
    }

    for env_var, config_field in env_mappings.items():
        value = os.getenv(env_var)
        if value is not None:
            # Convert string values to appropriate types
            if config_field in [
                "debug_mode",
                "async_processing",
                "enable_performance_logging",
                "enable_business_logging",
            ]:
                env_config[config_field] = value.lower() in ("true", "1", "yes", "on")
            elif config_field in [
                "claude_priority_threshold",
                "slow_request_threshold_ms",
                "retention_days",
            ]:
                env_config[config_field] = int(value)
            elif config_field == "storage_path":
                env_config[config_field] = Path(value)
            else:
                env_config[config_field] = value

    return LoggingConfig(**env_config)


def get_production_config() -> LoggingConfig:
    """Get production-optimized configuration."""
    return LoggingConfig(
        log_level=LogLevel.WARNING,
        environment="production",
        debug_mode=False,
        enable_console_output=False,
        storage_backend=StorageBackendType.HYBRID,
        claude_analysis_mode=AnalysisMode.BATCH,
        claude_analysis_interval_minutes=30,
        claude_priority_threshold=60,
        max_events_per_second=5000,
        batch_size=500,
        retention_days=90,
        log_request_bodies=False,
        log_response_bodies=False,
        anonymize_user_data=True,
        enable_pii_detection=True,
    )


def get_development_config() -> LoggingConfig:
    """Get development-optimized configuration."""
    return LoggingConfig(
        log_level=LogLevel.DEBUG,
        environment="development",
        debug_mode=True,
        enable_console_output=True,
        storage_backend=StorageBackendType.JSONL,
        claude_analysis_mode=AnalysisMode.REALTIME,
        claude_analysis_interval_minutes=5,
        claude_priority_threshold=30,
        max_events_per_second=1000,
        batch_size=50,
        retention_days=7,
        log_request_bodies=True,
        log_response_bodies=True,
        anonymize_user_data=False,
        enable_pii_detection=False,
    )


# Global config instance
_config: Optional[LoggingConfig] = None


def get_config() -> LoggingConfig:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = load_config_from_env()
    return _config


def set_config(config: LoggingConfig) -> None:
    """Set global configuration instance."""
    global _config
    _config = config
