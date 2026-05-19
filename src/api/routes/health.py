"""
Health-Check und System-Monitoring Endpoints.
Bietet detaillierte Informationen über System-Status und Komponenten.
"""

import shutil
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text, select, func
import redis.asyncio as redis
import structlog

from src.database import db_manager
from src.database import Decision, CrawlLog
from src.config import settings

logger = structlog.get_logger()
router = APIRouter()


async def check_database() -> Dict[str, Any]:
    """Prüft Datenbank-Verbindung und Status."""
    try:
        async with db_manager.get_session() as session:
            # Verbindungstest
            await session.execute(text("SELECT 1"))

            # Anzahl Entscheidungen
            count_query = select(func.count()).select_from(Decision)
            decision_count = await session.scalar(count_query)

            # Letzte Crawl-Aktivität
            last_crawl_query = select(CrawlLog).order_by(CrawlLog.started_at.desc()).limit(1)
            last_crawl_result = await session.execute(last_crawl_query)
            last_crawl = last_crawl_result.scalar_one_or_none()

            return {
                "status": "healthy",
                "connected": True,
                "decision_count": decision_count,
                "last_crawl": last_crawl.started_at.isoformat() if last_crawl else None,
                "pool_size": db_manager.engine.pool.size()
                if hasattr(db_manager.engine.pool, "size")
                else None,
            }
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {"status": "unhealthy", "connected": False, "error": str(e)}


async def check_redis() -> Dict[str, Any]:
    """Prüft Redis-Verbindung und Status."""
    try:
        redis_client = redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=5
        )

        # Ping-Test
        await redis_client.ping()

        # Basis-Info
        info = await redis_client.info()

        # Memory-Info
        memory_info = await redis_client.info("memory")

        await redis_client.close()

        return {
            "status": "healthy",
            "connected": True,
            "version": info.get("redis_version"),
            "used_memory_human": memory_info.get("used_memory_human"),
            "connected_clients": info.get("connected_clients"),
        }
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        return {"status": "unhealthy", "connected": False, "error": str(e)}


def check_disk_space() -> Dict[str, Any]:
    """Prüft verfügbaren Speicherplatz."""
    try:
        usage = shutil.disk_usage("/")
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        used_percent = (usage.used / usage.total) * 100

        status = "healthy"
        if free_gb < 1:
            status = "critical"
        elif free_gb < 5:
            status = "warning"

        return {
            "status": status,
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "used_percent": round(used_percent, 2),
        }
    except Exception as e:
        logger.error("disk_space_check_failed", error=str(e))
        return {"status": "unknown", "error": str(e)}


def check_memory() -> Dict[str, Any]:
    """Prüft Speichernutzung."""
    try:
        memory = psutil.virtual_memory()

        status = "healthy"
        if memory.percent > 90:
            status = "critical"
        elif memory.percent > 80:
            status = "warning"

        return {
            "status": status,
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "used_percent": round(memory.percent, 2),
        }
    except Exception as e:
        logger.error("memory_check_failed", error=str(e))
        return {"status": "unknown", "error": str(e)}


def check_cpu() -> Dict[str, Any]:
    """Prüft CPU-Auslastung."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()

        status = "healthy"
        if cpu_percent > 90:
            status = "critical"
        elif cpu_percent > 70:
            status = "warning"

        return {"status": status, "cores": cpu_count, "usage_percent": round(cpu_percent, 2)}
    except Exception as e:
        logger.error("cpu_check_failed", error=str(e))
        return {"status": "unknown", "error": str(e)}


@router.get("/health", response_model=Dict[str, Any])
async def health_check() -> Dict[str, Any]:
    """
    Umfassender Health-Check aller System-Komponenten.

    Returns:
        Dict mit Status aller Komponenten
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.environment,
        "version": "1.0.0",
        "checks": {},
    }

    # Datenbank-Check
    health["checks"]["database"] = await check_database()
    if health["checks"]["database"]["status"] != "healthy":
        health["status"] = "degraded"

    # Redis-Check
    health["checks"]["redis"] = await check_redis()
    if health["checks"]["redis"]["status"] != "healthy":
        health["status"] = "degraded"

    # System-Checks
    health["checks"]["disk"] = check_disk_space()
    if health["checks"]["disk"]["status"] == "critical":
        health["status"] = "unhealthy"
    elif health["checks"]["disk"]["status"] == "warning":
        health["status"] = "degraded"

    health["checks"]["memory"] = check_memory()
    if health["checks"]["memory"]["status"] == "critical":
        health["status"] = "unhealthy"
    elif health["checks"]["memory"]["status"] == "warning":
        health["status"] = "degraded"

    health["checks"]["cpu"] = check_cpu()
    if health["checks"]["cpu"]["status"] == "critical":
        health["status"] = "unhealthy"

    # HTTP Status Code basierend auf Health-Status
    if health["status"] == "unhealthy":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=health)

    return health


@router.get("/ready", response_model=Dict[str, Any])
async def readiness_check() -> Dict[str, Any]:
    """
    Kubernetes-kompatibler Readiness-Check.
    Prüft ob die Anwendung bereit ist, Traffic zu empfangen.

    Returns:
        Dict mit Readiness-Status
    """
    ready = {"ready": True, "timestamp": datetime.utcnow().isoformat(), "checks": {}}

    # Datenbank muss verfügbar sein
    db_check = await check_database()
    ready["checks"]["database"] = db_check["connected"]
    if not db_check["connected"]:
        ready["ready"] = False

    # Redis sollte verfügbar sein
    redis_check = await check_redis()
    ready["checks"]["redis"] = redis_check["connected"]
    if not redis_check["connected"]:
        ready["ready"] = False

    if not ready["ready"]:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=ready)

    return ready


@router.get("/metrics", response_model=Dict[str, Any])
async def metrics_endpoint() -> Dict[str, Any]:
    """
    Basis-Metriken für Monitoring.
    Kann später durch Prometheus-Metriken ersetzt werden.

    Returns:
        Dict mit System-Metriken
    """
    try:
        async with db_manager.get_session() as session:
            # Entscheidungs-Statistiken
            total_decisions = await session.scalar(select(func.count()).select_from(Decision))

            # Entscheidungen letzte 24h
            yesterday = datetime.utcnow() - timedelta(days=1)
            recent_decisions = await session.scalar(
                select(func.count()).select_from(Decision).where(Decision.created_at >= yesterday)
            )

            # Quellen-Verteilung
            source_stats_query = select(
                Decision.source, func.count(Decision.id).label("count")
            ).group_by(Decision.source)
            source_result = await session.execute(source_stats_query)
            source_stats = {row.source: row.count for row in source_result}

            # Crawl-Statistiken
            total_crawls = await session.scalar(select(func.count()).select_from(CrawlLog))

            successful_crawls = await session.scalar(
                select(func.count()).select_from(CrawlLog).where(CrawlLog.status == "success")
            )

            # System-Metriken
            memory = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.1)

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "decisions": {
                    "total": total_decisions,
                    "last_24h": recent_decisions,
                    "by_source": source_stats,
                },
                "crawls": {
                    "total": total_crawls,
                    "successful": successful_crawls,
                    "success_rate": round(successful_crawls / total_crawls * 100, 2)
                    if total_crawls > 0
                    else 0,
                },
                "system": {
                    "memory_percent": round(memory.percent, 2),
                    "cpu_percent": round(cpu, 2),
                    "uptime_seconds": (
                        datetime.utcnow() - datetime.fromtimestamp(psutil.boot_time())
                    ).total_seconds(),
                },
            }
    except Exception as e:
        logger.error("metrics_generation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate metrics: {str(e)}",
        )


@router.get("/live", response_model=Dict[str, str])
async def liveness_check() -> Dict[str, str]:
    """
    Kubernetes-kompatibler Liveness-Check.
    Sehr einfacher Check ob die Anwendung noch läuft.

    Returns:
        Dict mit Status
    """
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}
