"""
Integration Tests für Health-Monitoring und System-Status Endpoints.

Testet die in Phase 7 implementierten Health-Check Features.
"""

import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

import pytest
import psutil
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Decision, CrawlLog
from src.config import settings


class TestHealthMonitoring:
    """Tests für Health-Check und Monitoring Endpoints."""

    @pytest.mark.asyncio
    async def test_basic_health_endpoint(self, test_api_client):
        """Test des grundlegenden /health Endpoints."""
        response = await test_api_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_system_health_comprehensive(self, test_api_client, test_session: AsyncSession):
        """Test des umfassenden /system/health Endpoints."""
        # Erstelle Test-Daten
        decision = Decision(
            source="health_test",
            source_id="health_1",
            title="Health Test Decision",
            full_text_original="Test content for health check",
        )
        test_session.add(decision)

        crawl_log = CrawlLog(
            source="health_test",
            status="completed",
            decisions_found=1,
            decisions_processed=1,
            duration_seconds=10.5,
        )
        test_session.add(crawl_log)
        await test_session.commit()

        # Teste Health-Endpoint
        response = await test_api_client.get("/system/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "components" in data

        # Prüfe Komponenten-Status
        components = data["components"]
        assert "database" in components
        assert "redis" in components
        assert "disk_space" in components
        assert "memory" in components

        # Database-Komponente
        db_component = components["database"]
        assert db_component["status"] in ["healthy", "unhealthy"]
        assert "decision_count" in db_component
        assert db_component["decision_count"] >= 1
        assert "last_crawl" in db_component

        # System-Ressourcen
        if "disk_space" in components:
            disk = components["disk_space"]
            assert "used_percent" in disk
            assert 0 <= disk["used_percent"] <= 100

        if "memory" in components:
            memory = components["memory"]
            assert "used_percent" in memory
            assert 0 <= memory["used_percent"] <= 100

    @pytest.mark.asyncio
    async def test_readiness_check(self, test_api_client):
        """Test des Kubernetes-kompatiblen /system/ready Endpoints."""
        response = await test_api_client.get("/system/ready")
        assert response.status_code in [200, 503]

        data = response.json()
        assert "ready" in data
        assert isinstance(data["ready"], bool)

        if data["ready"]:
            assert response.status_code == 200
            assert "checks" in data
            checks = data["checks"]
            assert "database" in checks
            assert "redis" in checks
        else:
            assert response.status_code == 503
            assert "reason" in data

    @pytest.mark.asyncio
    async def test_liveness_check(self, test_api_client):
        """Test des einfachen /system/live Endpoints."""
        response = await test_api_client.get("/system/live")
        assert response.status_code == 200

        data = response.json()
        assert data["alive"] is True
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, test_api_client, test_session: AsyncSession):
        """Test des /system/metrics Endpoints für Basis-Metriken."""
        # Erstelle Test-Daten für Metriken
        for i in range(5):
            decision = Decision(
                source="metrics_test",
                source_id=f"metrics_{i}",
                title=f"Metrics Test {i}",
                decision_date=datetime.now() - timedelta(days=i),
                gdpr_articles=[f"Art. {i+1}", f"Art. {i+2}"],
            )
            test_session.add(decision)

        await test_session.commit()

        response = await test_api_client.get("/system/metrics")
        assert response.status_code == 200

        metrics = response.json()
        assert "decisions" in metrics
        assert "system" in metrics
        assert "timestamp" in metrics

        # Decision-Metriken
        decision_metrics = metrics["decisions"]
        assert "total" in decision_metrics
        assert decision_metrics["total"] >= 5
        assert "by_source" in decision_metrics
        assert "recent_24h" in decision_metrics

        # System-Metriken
        system_metrics = metrics["system"]
        assert "cpu_percent" in system_metrics
        assert "memory_percent" in system_metrics
        assert "disk_usage_percent" in system_metrics

        # Werte-Validierung
        assert 0 <= system_metrics["cpu_percent"] <= 100
        assert 0 <= system_metrics["memory_percent"] <= 100
        assert 0 <= system_metrics["disk_usage_percent"] <= 100

    @pytest.mark.asyncio
    async def test_health_check_database_failure(self, test_api_client):
        """Test des Health-Checks bei Datenbank-Ausfall."""
        with patch("src.api.routes.health.check_database") as mock_check:
            mock_check.return_value = {
                "status": "unhealthy",
                "connected": False,
                "error": "Connection refused",
            }

            response = await test_api_client.get("/system/health")
            assert response.status_code == 200  # Endpoint sollte trotzdem antworten

            data = response.json()
            assert data["status"] in ["degraded", "unhealthy"]
            assert data["components"]["database"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_redis_failure(self, test_api_client):
        """Test des Health-Checks bei Redis-Ausfall."""
        with patch("src.api.routes.health.check_redis") as mock_check:
            mock_check.return_value = {
                "status": "unhealthy",
                "connected": False,
                "error": "Redis connection failed",
            }

            response = await test_api_client.get("/system/health")
            assert response.status_code == 200

            data = response.json()
            # Redis-Ausfall sollte zu degraded führen, nicht unhealthy
            assert data["status"] in ["degraded", "healthy"]
            assert data["components"]["redis"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_performance(self, test_api_client):
        """Test der Performance der Health-Check Endpoints."""
        endpoints = [
            "/health",
            "/system/health",
            "/system/ready",
            "/system/live",
            "/system/metrics",
        ]

        for endpoint in endpoints:
            start_time = time.time()
            response = await test_api_client.get(endpoint)
            elapsed_time = time.time() - start_time

            assert response.status_code in [200, 503]
            # Health-Checks sollten schnell sein (< 500ms)
            assert elapsed_time < 0.5, f"{endpoint} took {elapsed_time:.3f}s"

            # Besonders kritisch: live und ready sollten < 100ms sein
            if endpoint in ["/system/live", "/health"]:
                assert elapsed_time < 0.1, f"{endpoint} took {elapsed_time:.3f}s"

    @pytest.mark.asyncio
    async def test_monitoring_dashboard_endpoint(self, test_api_client):
        """Test des Monitoring-Dashboard Endpoints."""
        response = await test_api_client.get("/dashboard")
        assert response.status_code == 200

        # Dashboard sollte HTML zurückgeben
        assert "text/html" in response.headers.get("content-type", "")

        # Prüfe wichtige Dashboard-Elemente
        html = response.text
        assert "System Status" in html or "System-Status" in html
        assert "Database" in html or "Datenbank" in html
        assert "Decisions" in html or "Entscheidungen" in html

    @pytest.mark.asyncio
    async def test_health_check_disk_space_warning(self, test_api_client):
        """Test der Disk-Space Warnung bei wenig Speicherplatz."""
        with patch("shutil.disk_usage") as mock_disk:
            # Simuliere 95% Disk-Usage
            mock_disk.return_value = MagicMock(
                total=100 * 1024**3,  # 100 GB
                used=95 * 1024**3,  # 95 GB
                free=5 * 1024**3,  # 5 GB
            )

            response = await test_api_client.get("/system/health")
            assert response.status_code == 200

            data = response.json()
            disk_component = data["components"]["disk_space"]
            assert disk_component["status"] in ["degraded", "unhealthy"]
            assert disk_component["used_percent"] >= 90

    @pytest.mark.asyncio
    async def test_health_check_memory_warning(self, test_api_client):
        """Test der Memory-Warnung bei hoher Auslastung."""
        with patch("psutil.virtual_memory") as mock_memory:
            # Simuliere 85% Memory-Usage
            mock_memory.return_value = MagicMock(
                total=16 * 1024**3,  # 16 GB
                available=2.4 * 1024**3,  # 2.4 GB
                percent=85.0,
                used=13.6 * 1024**3,  # 13.6 GB
            )

            response = await test_api_client.get("/system/health")
            assert response.status_code == 200

            data = response.json()
            memory_component = data["components"]["memory"]
            # 85% ist noch OK, sollte nicht unhealthy sein
            assert memory_component["status"] in ["healthy", "degraded"]
            assert memory_component["used_percent"] >= 80

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, test_api_client):
        """Test paralleler Health-Check Anfragen."""

        async def make_health_check():
            response = await test_api_client.get("/system/health")
            return response.status_code, response.json()

        # 20 parallele Health-Checks
        tasks = [make_health_check() for _ in range(20)]
        results = await asyncio.gather(*tasks)

        # Alle sollten erfolgreich sein
        for status_code, data in results:
            assert status_code == 200
            assert data["status"] in ["healthy", "degraded", "unhealthy"]

    @pytest.mark.asyncio
    async def test_health_history_tracking(self, test_api_client, test_session: AsyncSession):
        """Test ob Health-Checks historisiert werden können."""
        # Erste Messung
        response1 = await test_api_client.get("/system/metrics")
        metrics1 = response1.json()

        # Füge neue Entscheidung hinzu
        decision = Decision(
            source="history_test",
            source_id="history_1",
            title="History Test",
            decision_date=datetime.now(),
        )
        test_session.add(decision)
        await test_session.commit()

        # Zweite Messung
        await asyncio.sleep(0.1)  # Kurze Pause
        response2 = await test_api_client.get("/system/metrics")
        metrics2 = response2.json()

        # Entscheidungs-Zähler sollte sich erhöht haben
        assert metrics2["decisions"]["total"] > metrics1["decisions"]["total"]

        # Timestamps sollten unterschiedlich sein
        assert metrics1["timestamp"] != metrics2["timestamp"]
