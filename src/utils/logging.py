"""
Logging-Konfiguration für den Datenschutz-Rechtsprechung API.
Verwendet structlog für strukturiertes Logging mit deutschen Nachrichten.
"""

import sys
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime

import structlog
from structlog.processors import JSONRenderer, TimeStamper
from structlog.stdlib import LoggerFactory
from pythonjsonlogger import jsonlogger

from src.config import settings


# Deutsche Log-Level-Namen für bessere Lesbarkeit
GERMAN_LOG_LEVELS = {
    "DEBUG": "FEHLERSUCHE",
    "INFO": "INFO",
    "WARNING": "WARNUNG",
    "ERROR": "FEHLER",
    "CRITICAL": "KRITISCH",
}


class GermanFormatter(logging.Formatter):
    """Formatter mit deutschen Log-Level-Namen."""

    def format(self, record):
        # Ersetze Log-Level mit deutschem Namen
        original_levelname = record.levelname
        record.levelname = GERMAN_LOG_LEVELS.get(original_levelname, original_levelname)
        result = super().format(record)
        record.levelname = original_levelname
        return result


class ContextFilter(logging.Filter):
    """Filter der Kontext-Informationen zu Log-Records hinzufügt."""

    def filter(self, record):
        # Füge Standard-Kontext hinzu
        record.environment = settings.environment
        record.application = "datenschutz_rechtsprechung_api"
        record.timestamp = datetime.utcnow().isoformat()
        return True


def setup_stdlib_logging():
    """Konfiguriert Python's Standard-Logging."""

    # Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level))

    # Entferne existierende Handler
    root_logger.handlers = []

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)

    if settings.log_format == "json":
        # JSON Format für strukturiertes Logging
        json_formatter = jsonlogger.JsonFormatter(
            "%(timestamp)s %(levelname)s %(name)s %(message)s",
            rename_fields={"levelname": "stufe", "name": "modul", "message": "nachricht"},
        )
        console_handler.setFormatter(json_formatter)
    else:
        # Plain Text Format mit deutschen Labels
        plain_formatter = GermanFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(plain_formatter)

    console_handler.addFilter(ContextFilter())
    root_logger.addHandler(console_handler)

    # File Handler (falls konfiguriert)
    if settings.log_file_path:
        setup_file_logging(root_logger)

    # SQL Logging
    if settings.log_show_sql:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    else:
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    # Reduziere Noise von externen Libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def setup_file_logging(logger: logging.Logger):
    """Richtet File-Logging mit Rotation ein."""

    log_path = Path(settings.log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Rotating File Handler
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path,
        maxBytes=settings.log_file_max_bytes,
        backupCount=settings.log_file_backup_count,
        encoding="utf-8",
    )

    if settings.log_format == "json":
        json_formatter = jsonlogger.JsonFormatter(
            "%(timestamp)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d"
        )
        file_handler.setFormatter(json_formatter)
    else:
        file_formatter = GermanFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s | %(pathname)s:%(lineno)d",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)

    file_handler.addFilter(ContextFilter())
    logger.addHandler(file_handler)


def setup_structlog():
    """Konfiguriert structlog für strukturiertes Logging."""

    timestamper = TimeStamper(fmt="iso")

    # Prozessoren für Entwicklung vs. Produktion
    if settings.is_development:
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.dict_tracebacks,
            JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Deutsche Log-Nachrichten Templates
LOG_MESSAGES = {
    # Crawler
    "crawling_started": "Crawling gestartet für Quelle: {source}",
    "crawling_completed": "Crawling abgeschlossen. {count} Entscheidungen verarbeitet",
    "crawling_failed": "Crawling fehlgeschlagen: {error}",
    # Datenbank
    "database_connected": "Datenbankverbindung hergestellt",
    "database_error": "Datenbankfehler: {error}",
    "decision_saved": "Entscheidung gespeichert: {id}",
    "duplicate_found": "Duplikat gefunden, überspringe: {id}",
    # Verarbeitung
    "anonymization_started": "Anonymisierung gestartet",
    "anonymization_completed": "{count} Namen anonymisiert",
    "pdf_extraction_started": "PDF-Extraktion gestartet: {file}",
    "pdf_extraction_failed": "PDF-Extraktion fehlgeschlagen: {error}",
    # API
    "api_request": "{method} {path} - Status: {status}",
    "api_error": "API-Fehler: {error}",
    # Rate Limiting
    "rate_limit_waiting": "Rate-Limit erreicht, warte {seconds}s",
    "rate_limit_exceeded": "Rate-Limit überschritten für {source}",
    # Fehler
    "unexpected_error": "Unerwarteter Fehler: {error}",
    "validation_error": "Validierungsfehler: {field} - {error}",
    "configuration_error": "Konfigurationsfehler: {error}",
}


class GDPRLogger:
    """
    Wrapper-Klasse für einheitliches Logging mit deutschen Nachrichten.
    """

    def __init__(self, name: str):
        self.logger = structlog.get_logger(name)
        self.name = name

    def _format_message(self, message_key: str, **kwargs) -> str:
        """Formatiert Nachricht mit deutschem Template."""
        template = LOG_MESSAGES.get(message_key, message_key)
        try:
            return template.format(**kwargs)
        except KeyError:
            return f"{template} | Kontext: {kwargs}"

    def debug(self, message_key: str, **kwargs):
        """Debug-Level Logging."""
        msg = self._format_message(message_key, **kwargs)
        self.logger.debug(msg, **kwargs)

    def info(self, message_key: str, **kwargs):
        """Info-Level Logging."""
        msg = self._format_message(message_key, **kwargs)
        self.logger.info(msg, **kwargs)

    def warning(self, message_key: str, **kwargs):
        """Warning-Level Logging."""
        msg = self._format_message(message_key, **kwargs)
        self.logger.warning(msg, **kwargs)

    def error(self, message_key: str, **kwargs):
        """Error-Level Logging."""
        msg = self._format_message(message_key, **kwargs)
        self.logger.error(msg, **kwargs)

    def critical(self, message_key: str, **kwargs):
        """Critical-Level Logging."""
        msg = self._format_message(message_key, **kwargs)
        self.logger.critical(msg, **kwargs)

    def exception(self, message_key: str, exc_info=True, **kwargs):
        """Exception Logging mit Traceback."""
        msg = self._format_message(message_key, **kwargs)
        self.logger.exception(msg, exc_info=exc_info, **kwargs)

    def measure_time(self, operation: str):
        """Context Manager für Zeit-Messung."""
        return TimeMeasurement(self, operation)


class TimeMeasurement:
    """Context Manager für Performance-Messung."""

    def __init__(self, logger: GDPRLogger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(f"operation_started", operation=self.operation)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()

        if exc_type:
            self.logger.error(
                "operation_failed",
                operation=self.operation,
                duration_seconds=duration,
                error=str(exc_val),
            )
        else:
            self.logger.info(
                "operation_completed", operation=self.operation, duration_seconds=duration
            )


# =============================================================================
# LOGGING INITIALISIERUNG
# =============================================================================


def initialize_logging():
    """Initialisiert das gesamte Logging-System."""
    setup_stdlib_logging()
    setup_structlog()

    # Test-Nachricht
    logger = get_logger("system")
    logger.info("logging_initialized", environment=settings.environment)


def get_logger(name: str) -> GDPRLogger:
    """
    Factory-Funktion für Logger-Instanzen.

    Args:
        name: Logger-Name (z.B. "collector.gdprhub")

    Returns:
        GDPRLogger Instanz
    """
    return GDPRLogger(name)


# Initialisiere beim Import
initialize_logging()
