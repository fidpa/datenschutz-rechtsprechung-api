"""
Celery Application Konfiguration.
"""

from celery import Celery
from celery.schedules import crontab
from src.config import settings

# Erstelle Celery App
app = Celery(
    "datenschutz_rechtsprechung_api",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks.crawler_tasks"],
)

# Konfiguration
app.conf.update(
    # Zeitzone
    timezone="Europe/Berlin",
    # Task-Einstellungen
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=3600,
    # Worker-Einstellungen
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    # Rate Limits
    task_annotations={
        "src.tasks.crawler_tasks.crawl_gdprhub": {"rate_limit": "1/m"},  # Max 1 pro Minute
        "src.tasks.crawler_tasks.crawl_openlegaldata": {"rate_limit": "2/m"},  # Max 2 pro Minute
    },
)

# Celery Beat Schedule (Cron-Jobs)
app.conf.beat_schedule = {
    # Täglicher GDPRhub Crawl um 02:00 Uhr
    "crawl-gdprhub-daily": {
        "task": "src.tasks.crawler_tasks.crawl_gdprhub",
        "schedule": crontab(hour=2, minute=0),
        "args": (False,),  # incremental crawl
        "options": {
            "expires": 3600,  # Task expires nach 1 Stunde
        },
    },
    # Täglicher OpenLegalData Crawl um 03:00 Uhr
    "crawl-openlegaldata-daily": {
        "task": "src.tasks.crawler_tasks.crawl_openlegaldata",
        "schedule": crontab(hour=3, minute=0),
        "args": (False, 50),  # incremental, max 50 pages
        "options": {
            "expires": 7200,  # Task expires nach 2 Stunden
        },
    },
    # Deduplizierung täglich um 05:00 Uhr
    "deduplicate-daily": {
        "task": "src.tasks.crawler_tasks.deduplicate_decisions",
        "schedule": crontab(hour=5, minute=0),
        "options": {
            "expires": 3600,
        },
    },
    # Statistik-Update täglich um 06:00 Uhr
    "update-stats-daily": {
        "task": "src.tasks.crawler_tasks.update_statistics",
        "schedule": crontab(hour=6, minute=0),
        "options": {
            "expires": 1800,
        },
    },
}

if __name__ == "__main__":
    app.start()
