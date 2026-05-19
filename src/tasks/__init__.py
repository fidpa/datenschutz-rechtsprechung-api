"""
Celery Tasks für automatisierte Crawls und Verarbeitung.
"""

from .celery_app import app
from .crawler_tasks import (
    crawl_gdprhub,
    crawl_openlegaldata,
    crawl_all_sources,
    deduplicate_decisions,
)

__all__ = [
    "app",
    "crawl_gdprhub",
    "crawl_openlegaldata",
    "crawl_all_sources",
    "deduplicate_decisions",
]
