"""
Redis-Cache Utilities für Performance-Optimierung.
Bietet Caching-Decorator und Cache-Management.
"""

import json
import hashlib
from typing import Any, Optional, Callable, Union
from functools import wraps
from datetime import timedelta
import redis.asyncio as redis
import structlog
import pickle

from src.config import settings

logger = structlog.get_logger()


class RedisCache:
    """Redis-Cache Manager für die Anwendung."""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.connected = False

    async def connect(self):
        """Verbindung zu Redis herstellen."""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=False,  # Für Binary-Support
                socket_connect_timeout=5,
                socket_timeout=5,
            )

            # Test-Ping
            await self.redis_client.ping()
            self.connected = True
            logger.info("redis_cache_connected")

        except Exception as e:
            logger.error("redis_cache_connection_failed", error=str(e))
            self.connected = False

    async def disconnect(self):
        """Verbindung trennen."""
        if self.redis_client:
            await self.redis_client.close()
            self.connected = False
            logger.info("redis_cache_disconnected")

    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """Erstellt einen Cache-Key aus Prefix und Argumenten."""
        # Kombiniere alle Argumente zu einem String
        key_parts = [prefix]

        # Füge positionale Argumente hinzu
        for arg in args:
            if isinstance(arg, (str, int, float, bool)):
                key_parts.append(str(arg))
            else:
                # Für komplexe Objekte: Hash verwenden
                key_parts.append(hashlib.md5(str(arg).encode()).hexdigest()[:8])

        # Füge Keyword-Argumente sortiert hinzu
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")

        return ":".join(key_parts)

    async def get(self, key: str) -> Optional[Any]:
        """Wert aus Cache abrufen."""
        if not self.connected:
            return None

        try:
            value = await self.redis_client.get(key)
            if value:
                # Versuche JSON zu parsen
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # Falls kein JSON, versuche Pickle
                    try:
                        return pickle.loads(value)
                    except:
                        # Als String zurückgeben
                        return value.decode("utf-8") if isinstance(value, bytes) else value
        except Exception as e:
            logger.warning("cache_get_failed", key=key, error=str(e))

        return None

    async def set(
        self, key: str, value: Any, expire: Optional[Union[int, timedelta]] = None
    ) -> bool:
        """Wert in Cache speichern."""
        if not self.connected:
            return False

        try:
            # Serialisierung
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value, default=str)
            elif isinstance(value, (str, int, float, bool)):
                serialized = json.dumps(value)
            else:
                # Für komplexe Objekte: Pickle verwenden
                serialized = pickle.dumps(value)

            # Expire-Zeit konvertieren
            if isinstance(expire, timedelta):
                expire = int(expire.total_seconds())

            # In Redis speichern
            if expire:
                await self.redis_client.setex(key, expire, serialized)
            else:
                await self.redis_client.set(key, serialized)

            return True

        except Exception as e:
            logger.warning("cache_set_failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Cache-Eintrag löschen."""
        if not self.connected:
            return False

        try:
            result = await self.redis_client.delete(key)
            return bool(result)
        except Exception as e:
            logger.warning("cache_delete_failed", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Alle Keys mit Pattern löschen."""
        if not self.connected:
            return 0

        try:
            keys = []
            async for key in self.redis_client.scan_iter(pattern):
                keys.append(key)

            if keys:
                return await self.redis_client.delete(*keys)
            return 0

        except Exception as e:
            logger.warning("cache_delete_pattern_failed", pattern=pattern, error=str(e))
            return 0

    async def exists(self, key: str) -> bool:
        """Prüft ob Key existiert."""
        if not self.connected:
            return False

        try:
            return bool(await self.redis_client.exists(key))
        except Exception as e:
            logger.warning("cache_exists_failed", key=key, error=str(e))
            return False

    async def get_ttl(self, key: str) -> Optional[int]:
        """TTL (Time-to-Live) eines Keys abrufen."""
        if not self.connected:
            return None

        try:
            ttl = await self.redis_client.ttl(key)
            return ttl if ttl >= 0 else None
        except Exception as e:
            logger.warning("cache_ttl_failed", key=key, error=str(e))
            return None

    async def flush_all(self) -> bool:
        """Gesamten Cache leeren (VORSICHT!)."""
        if not self.connected:
            return False

        try:
            await self.redis_client.flushdb()
            logger.warning("cache_flushed")
            return True
        except Exception as e:
            logger.error("cache_flush_failed", error=str(e))
            return False


# Globale Cache-Instanz
cache_manager = RedisCache()


def cache_result(
    expire: Union[int, timedelta] = 300,
    prefix: str = "cache",
    key_builder: Optional[Callable] = None,
):
    """
    Decorator für Caching von Funktions-Ergebnissen.

    Args:
        expire: Cache-Dauer in Sekunden oder als timedelta
        prefix: Prefix für Cache-Keys
        key_builder: Optionale Funktion zum Erstellen des Cache-Keys

    Example:
        @cache_result(expire=timedelta(minutes=5), prefix="decisions")
        async def get_decisions(source: str):
            return await fetch_from_database(source)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Cache-Key erstellen
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Standard-Key-Builder
                cache_key = cache_manager._make_key(f"{prefix}:{func.__name__}", *args, **kwargs)

            # Aus Cache abrufen
            cached_value = await cache_manager.get(cache_key)
            if cached_value is not None:
                logger.debug("cache_hit", key=cache_key)
                return cached_value

            # Funktion ausführen
            logger.debug("cache_miss", key=cache_key)
            result = await func(*args, **kwargs)

            # In Cache speichern
            await cache_manager.set(cache_key, result, expire)

            return result

        # Hilfsfunktion zum Cache-Invalidierung
        async def invalidate(*args, **kwargs):
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = cache_manager._make_key(f"{prefix}:{func.__name__}", *args, **kwargs)
            return await cache_manager.delete(cache_key)

        wrapper.invalidate = invalidate
        return wrapper

    return decorator


def cache_aside(key: str, expire: Union[int, timedelta] = 300):
    """
    Cache-Aside Pattern für manuelle Cache-Kontrolle.

    Example:
        async with cache_aside("stats:total", expire=60) as cached:
            if cached.value is not None:
                return cached.value

            # Berechne Wert
            result = await calculate_stats()
            cached.value = result  # Speichert automatisch
            return result
    """

    class CacheContext:
        def __init__(self, key: str, expire: Union[int, timedelta]):
            self.key = key
            self.expire = expire
            self._value = None
            self._loaded = False

        async def __aenter__(self):
            self._value = await cache_manager.get(self.key)
            self._loaded = True
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            # Automatisch speichern wenn Wert gesetzt wurde
            if not self._loaded and self._value is not None:
                await cache_manager.set(self.key, self._value, self.expire)

        @property
        def value(self):
            return self._value

        @value.setter
        def value(self, val):
            self._value = val
            self._loaded = False  # Markiere zum Speichern

    return CacheContext(key, expire)


# Vordefinierte Cache-Zeiten
CACHE_TIMES = {
    "short": timedelta(seconds=30),
    "medium": timedelta(minutes=5),
    "long": timedelta(hours=1),
    "day": timedelta(days=1),
}


# Spezielle Cache-Funktionen für häufige Use-Cases
async def cache_stats(stats_type: str, value: dict, expire: int = 300):
    """Cache für Statistiken."""
    key = f"stats:{stats_type}"
    return await cache_manager.set(key, value, expire)


async def get_cached_stats(stats_type: str) -> Optional[dict]:
    """Statistiken aus Cache abrufen."""
    key = f"stats:{stats_type}"
    return await cache_manager.get(key)


async def invalidate_decision_cache(decision_id: Optional[int] = None):
    """Invalidiert Decision-bezogene Caches."""
    if decision_id:
        # Spezifische Decision
        await cache_manager.delete(f"decision:{decision_id}")
        await cache_manager.delete_pattern(f"decisions:*{decision_id}*")
    else:
        # Alle Decisions
        await cache_manager.delete_pattern("decision:*")
        await cache_manager.delete_pattern("decisions:*")
        await cache_manager.delete_pattern("stats:decisions:*")

    logger.info("decision_cache_invalidated", decision_id=decision_id)
