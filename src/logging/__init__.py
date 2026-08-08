"""
Claude Code Logging & Monitoring Integration System

Ein intelligentes Logging-System designed für Claude Code consumption
mit proaktiver Systemoptimierung und predictive maintenance.

Hauptkomponenten:
- Core: Basis-Infrastruktur und Event-Classification
- Middleware: Automatische Integration in Flask/FastAPI/Celery
- Collectors: Performance, Error, Business und System Metriken
- Backends: Storage mit JSONL (Claude-friendly) und Database-Migration-Path
- Formatters: Claude-optimierte Datenformate

Architektur:
Application → Middleware → Intelligence → Storage → Claude Analysis → Actions
"""

from .._version import PROJECT_VERSION
from .core.logger import EnterpriseLogger
from .core.events import EventClassifier, EventPriority
from .core.config import LoggingConfig

# The version is the project's, read from pyproject.toml via src._version.
# This module used to carry its own "12.1.0", a number that never matched a
# release and made log events unusable for "which build is running here?".
__version__ = PROJECT_VERSION
__all__ = ["EnterpriseLogger", "EventClassifier", "EventPriority", "LoggingConfig"]
