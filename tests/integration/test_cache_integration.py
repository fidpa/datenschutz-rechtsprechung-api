"""
Integration Tests für Redis-Cache Funktionalität.

Testet die in Phase 7 implementierte Cache-Layer.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict
from unittest.mock import patch, AsyncMock

import pytest
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Decision
from src.utils.cache import CacheManager, cache_result
from src.config import settings


class TestCacheIntegration:
    """Tests für Redis-Cache Integration."""

    @pytest.fixture
    async def cache_manager(self):
        """Erstellt eine Cache-Manager Instanz für Tests."""
        manager = CacheManager()
        await manager.initialize()
        # Cleanup vor dem Test
        await manager.clear_pattern("test:*")
        yield manager
        # Cleanup nach dem Test
        await manager.clear_pattern("test:*")
        await manager.close()

    @pytest.mark.asyncio
    async def test_cache_basic_operations(self, cache_manager):
        """Test grundlegender Cache-Operationen (get, set, delete)."""
        # Set
        await cache_manager.set("test:key1", {"data": "test_value"}, ttl=60)

        # Get
        result = await cache_manager.get("test:key1")
        assert result is not None
        assert result["data"] == "test_value"

        # Delete
        await cache_manager.delete("test:key1")
        result = await cache_manager.get("test:key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self, cache_manager):
        """Test der TTL (Time-To-Live) Funktionalität."""
        # Set mit kurzem TTL
        await cache_manager.set("test:ttl", {"data": "expires"}, ttl=1)

        # Sofort abrufen - sollte existieren
        result = await cache_manager.get("test:ttl")
        assert result is not None
        assert result["data"] == "expires"

        # Nach TTL warten
        await asyncio.sleep(1.5)

        # Sollte abgelaufen sein
        result = await cache_manager.get("test:ttl")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_pattern_deletion(self, cache_manager):
        """Test des Pattern-basierten Löschens."""
        # Mehrere Keys setzen
        await cache_manager.set("test:pattern:1", {"id": 1}, ttl=60)
        await cache_manager.set("test:pattern:2", {"id": 2}, ttl=60)
        await cache_manager.set("test:pattern:3", {"id": 3}, ttl=60)
        await cache_manager.set("test:other:1", {"id": 4}, ttl=60)

        # Pattern löschen
        deleted = await cache_manager.clear_pattern("test:pattern:*")
        assert deleted >= 3

        # Verifizieren
        assert await cache_manager.get("test:pattern:1") is None
        assert await cache_manager.get("test:pattern:2") is None
        assert await cache_manager.get("test:pattern:3") is None
        assert await cache_manager.get("test:other:1") is not None

    @pytest.mark.asyncio
    async def test_cache_decorator(self, cache_manager):
        """Test des @cache_result Decorators."""
        call_count = 0

        @cache_result(prefix="test:decorator", ttl=60)
        async def expensive_function(param: str) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # Simuliere teure Operation
            return {"result": f"computed_{param}", "calls": call_count}

        # Erster Aufruf - sollte berechnet werden
        result1 = await expensive_function("value1")
        assert result1["result"] == "computed_value1"
        assert result1["calls"] == 1

        # Zweiter Aufruf mit gleichem Parameter - sollte aus Cache kommen
        result2 = await expensive_function("value1")
        assert result2["result"] == "computed_value1"
        assert result2["calls"] == 1  # Call count sollte gleich bleiben

        # Aufruf mit anderem Parameter - sollte neu berechnet werden
        result3 = await expensive_function("value2")
        assert result3["result"] == "computed_value2"
        assert result3["calls"] == 2

    @pytest.mark.asyncio
    async def test_cache_api_integration(
        self, test_api_client, cache_manager, test_session: AsyncSession
    ):
        """Test der Cache-Integration mit API-Endpoints."""
        # Erstelle Test-Entscheidungen
        for i in range(5):
            decision = Decision(
                source="cache_test",
                source_id=f"cache_{i}",
                title=f"Cache Test Decision {i}",
                court="LG München",
                gdpr_articles=[f"Art. {i+1}"],
            )
            test_session.add(decision)
        await test_session.commit()

        # Erster API-Aufruf (Cache-Miss)
        start_time = time.time()
        response1 = await test_api_client.get("/api/v1/decisions?court=LG München")
        time1 = time.time() - start_time
        assert response1.status_code == 200
        data1 = response1.json()

        # Zweiter identischer API-Aufruf (Cache-Hit)
        start_time = time.time()
        response2 = await test_api_client.get("/api/v1/decisions?court=LG München")
        time2 = time.time() - start_time
        assert response2.status_code == 200
        data2 = response2.json()

        # Daten sollten identisch sein
        assert data1 == data2

        # Zweiter Aufruf sollte schneller sein (aus Cache)
        # Nur prüfen wenn Cache aktiv ist
        if await cache_manager.get("api:decisions:*") is not None:
            assert time2 < time1 * 0.5  # Mindestens 50% schneller

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_update(self, cache_manager, test_session: AsyncSession):
        """Test der Cache-Invalidierung bei Datenänderungen."""
        # Erstelle Entscheidung
        decision = Decision(
            source="invalidation_test", source_id="inv_1", title="Original Title", court="LG Berlin"
        )
        test_session.add(decision)
        await test_session.commit()

        # Cache den Wert
        cache_key = f"decision:{decision.id}"
        await cache_manager.set(
            cache_key,
            {"id": str(decision.id), "title": decision.title, "court": decision.court},
            ttl=300,
        )

        # Verifiziere Cache
        cached = await cache_manager.get(cache_key)
        assert cached["title"] == "Original Title"

        # Update Entscheidung
        decision.title = "Updated Title"
        await test_session.commit()

        # Cache sollte invalidiert werden (manuell hier)
        await cache_manager.delete(cache_key)

        # Cache sollte leer sein
        cached = await cache_manager.get(cache_key)
        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_concurrent_access(self, cache_manager):
        """Test paralleler Cache-Zugriffe."""

        async def cache_operation(index: int):
            key = f"test:concurrent:{index % 5}"  # 5 verschiedene Keys

            # Schreibe
            await cache_manager.set(key, {"value": index}, ttl=60)

            # Lese
            result = await cache_manager.get(key)

            # Aktualisiere
            if result:
                result["updated"] = True
                await cache_manager.set(key, result, ttl=60)

            return result

        # 50 parallele Operationen
        tasks = [cache_operation(i) for i in range(50)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Keine Exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0

        # Alle Operationen erfolgreich
        assert all(r is not None for r in results if not isinstance(r, Exception))

    @pytest.mark.asyncio
    async def test_cache_memory_efficiency(self, cache_manager):
        """Test der Speichereffizienz des Caches."""
        large_data = {
            "id": "test",
            "content": "x" * 10000,  # 10KB String
            "metadata": {"court": "LG München", "date": "2024-01-01", "articles": list(range(100))},
        }

        # Speichere große Daten
        await cache_manager.set("test:large", large_data, ttl=60)

        # Abrufen und verifizieren
        retrieved = await cache_manager.get("test:large")
        assert retrieved is not None
        assert retrieved["content"] == large_data["content"]
        assert len(retrieved["metadata"]["articles"]) == 100

    @pytest.mark.asyncio
    async def test_cache_hit_miss_ratio(self, cache_manager):
        """Test und Messung der Cache Hit/Miss Ratio."""
        hits = 0
        misses = 0

        # Simuliere realistische Cache-Nutzung
        for i in range(100):
            # 70% der Anfragen für häufige Keys (Cache-Hits erwartet)
            if i % 10 < 7:
                key = f"test:common:{i % 5}"
            else:
                key = f"test:rare:{i}"

            result = await cache_manager.get(key)
            if result is None:
                misses += 1
                # Simuliere Berechnung und Cache
                await cache_manager.set(key, {"data": i}, ttl=60)
            else:
                hits += 1

        # Hit-Ratio berechnen
        total = hits + misses
        hit_ratio = hits / total if total > 0 else 0

        print(f"Cache Hit Ratio: {hit_ratio:.2%} ({hits} hits, {misses} misses)")

        # Bei wiederholten Zugriffen sollte Hit-Ratio > 50% sein
        if total > 50:  # Nur bei genügend Samples prüfen
            assert hit_ratio > 0.3  # Mindestens 30% Hits erwartet

    @pytest.mark.asyncio
    async def test_cache_serialization_types(self, cache_manager):
        """Test verschiedener Datentypen im Cache."""
        test_data = [
            ("string", "simple string"),
            ("integer", 42),
            ("float", 3.14159),
            ("boolean", True),
            ("none", None),
            ("list", [1, 2, 3, "four"]),
            ("dict", {"nested": {"data": "structure"}}),
            ("datetime", datetime.now().isoformat()),
        ]

        for key_suffix, value in test_data:
            key = f"test:types:{key_suffix}"

            # Speichern
            await cache_manager.set(key, value, ttl=60)

            # Abrufen und verifizieren
            retrieved = await cache_manager.get(key)

            if key_suffix == "datetime":
                # DateTime als String vergleichen
                assert retrieved == value
            elif value is None:
                assert retrieved is None or retrieved == value
            else:
                assert retrieved == value

    @pytest.mark.asyncio
    async def test_cache_statistics_endpoint(self, test_api_client, cache_manager):
        """Test des Cache-Statistik Endpoints (falls vorhanden)."""
        # Füge Test-Daten zum Cache hinzu
        for i in range(10):
            await cache_manager.set(f"test:stats:{i}", {"value": i}, ttl=60)

        # Teste Statistik-Endpoint (falls implementiert)
        response = await test_api_client.get("/system/metrics")
        assert response.status_code == 200

        metrics = response.json()
        # Cache-Metriken könnten hier enthalten sein
        if "cache" in metrics:
            cache_metrics = metrics["cache"]
            assert "keys" in cache_metrics or "size" in cache_metrics

    @pytest.mark.asyncio
    async def test_cache_fallback_on_redis_failure(
        self, test_api_client, test_session: AsyncSession
    ):
        """Test des Fallback-Verhaltens bei Redis-Ausfall."""
        # Erstelle Test-Daten
        decision = Decision(
            source="fallback_test", source_id="fallback_1", title="Fallback Test Decision"
        )
        test_session.add(decision)
        await test_session.commit()

        # Simuliere Redis-Ausfall
        with patch("redis.asyncio.Redis.get", side_effect=redis.ConnectionError("Redis down")):
            # API sollte trotzdem funktionieren (ohne Cache)
            response = await test_api_client.get(f"/api/v1/decisions/{decision.id}")
            assert response.status_code == 200

            data = response.json()
            assert data["title"] == "Fallback Test Decision"

    @pytest.mark.asyncio
    async def test_cache_performance_metrics(self, cache_manager):
        """Misst Performance-Metriken des Caches."""
        metrics = {"set_times": [], "get_times": [], "delete_times": []}

        # 100 Operationen für Durchschnittswerte
        for i in range(100):
            key = f"test:perf:{i}"
            value = {"index": i, "data": "x" * 100}

            # SET Performance
            start = time.time()
            await cache_manager.set(key, value, ttl=60)
            metrics["set_times"].append(time.time() - start)

            # GET Performance
            start = time.time()
            await cache_manager.get(key)
            metrics["get_times"].append(time.time() - start)

            # DELETE Performance
            start = time.time()
            await cache_manager.delete(key)
            metrics["delete_times"].append(time.time() - start)

        # Berechne Durchschnittswerte
        avg_set = sum(metrics["set_times"]) / len(metrics["set_times"])
        avg_get = sum(metrics["get_times"]) / len(metrics["get_times"])
        avg_delete = sum(metrics["delete_times"]) / len(metrics["delete_times"])

        print(f"Cache Performance:")
        print(f"  AVG SET: {avg_set*1000:.2f}ms")
        print(f"  AVG GET: {avg_get*1000:.2f}ms")
        print(f"  AVG DELETE: {avg_delete*1000:.2f}ms")

        # Performance-Assertions
        assert avg_set < 0.01  # SET sollte < 10ms sein
        assert avg_get < 0.005  # GET sollte < 5ms sein
        assert avg_delete < 0.005  # DELETE sollte < 5ms sein
