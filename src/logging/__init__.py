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

from .core.logger import EnterpriseLogger
from .core.events import EventClassifier, EventPriority
from .core.config import LoggingConfig

__version__ = "12.1.0"
__all__ = ["EnterpriseLogger", "EventClassifier", "EventPriority", "LoggingConfig"]
