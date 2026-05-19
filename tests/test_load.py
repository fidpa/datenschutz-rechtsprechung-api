"""
Load-Tests für Datenschutz-Rechtsprechung API API.
Testet Performance und Stabilität unter Last.
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
import httpx
import pytest
from datetime import datetime

# Test-Konfiguration
BASE_URL = "http://localhost:8000"
CONCURRENT_USERS = [1, 10, 50, 100]  # Verschiedene Last-Stufen
REQUESTS_PER_USER = 10
TIMEOUT = 30.0


class LoadTestResults:
    """Sammelt und analysiert Load-Test-Ergebnisse."""

    def __init__(self):
        self.response_times: List[float] = []
        self.status_codes: Dict[int, int] = {}
        self.errors: List[str] = []
        self.start_time = None
        self.end_time = None

    def add_response(self, response_time: float, status_code: int):
        """Fügt eine Response hinzu."""
        self.response_times.append(response_time)
        self.status_codes[status_code] = self.status_codes.get(status_code, 0) + 1

    def add_error(self, error: str):
        """Fügt einen Fehler hinzu."""
        self.errors.append(error)

    def get_statistics(self) -> Dict[str, Any]:
        """Berechnet Statistiken."""
        if not self.response_times:
            return {"error": "Keine Responses"}

        sorted_times = sorted(self.response_times)
        total_requests = len(self.response_times) + len(self.errors)
        duration = (self.end_time - self.start_time) if self.end_time else 0

        return {
            "total_requests": total_requests,
            "successful_requests": len(self.response_times),
            "failed_requests": len(self.errors),
            "duration_seconds": round(duration, 2),
            "requests_per_second": round(total_requests / duration, 2) if duration > 0 else 0,
            "response_times": {
                "min": round(min(sorted_times), 3),
                "max": round(max(sorted_times), 3),
                "mean": round(statistics.mean(sorted_times), 3),
                "median": round(statistics.median(sorted_times), 3),
                "p95": round(sorted_times[int(len(sorted_times) * 0.95)], 3)
                if len(sorted_times) > 20
                else None,
                "p99": round(sorted_times[int(len(sorted_times) * 0.99)], 3)
                if len(sorted_times) > 100
                else None,
            },
            "status_codes": self.status_codes,
            "error_rate": round(len(self.errors) / total_requests * 100, 2)
            if total_requests > 0
            else 0,
        }


async def make_request(client: httpx.AsyncClient, endpoint: str, results: LoadTestResults):
    """Macht einen einzelnen Request und misst die Zeit."""
    try:
        start = time.time()
        response = await client.get(endpoint, timeout=TIMEOUT)
        elapsed = time.time() - start

        results.add_response(elapsed, response.status_code)

        if response.status_code >= 500:
            results.add_error(f"Server Error {response.status_code}")

    except httpx.TimeoutException:
        results.add_error("Timeout")
    except httpx.ConnectError:
        results.add_error("Connection Error")
    except Exception as e:
        results.add_error(str(e))


async def run_user_simulation(user_id: int, endpoints: List[str], results: LoadTestResults):
    """Simuliert einen einzelnen User."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        tasks = []
        for i in range(REQUESTS_PER_USER):
            # Rotiere durch verschiedene Endpoints
            endpoint = endpoints[i % len(endpoints)]
            tasks.append(make_request(client, endpoint, results))

            # Kleine Verzögerung zwischen Requests (simuliert echtes User-Verhalten)
            await asyncio.sleep(0.1)

        await asyncio.gather(*tasks)


async def load_test_endpoint(endpoint: str, concurrent_users: int) -> LoadTestResults:
    """Führt Load-Test für einen Endpoint aus."""
    results = LoadTestResults()
    results.start_time = time.time()

    # Erstelle User-Tasks
    tasks = []
    for user_id in range(concurrent_users):
        tasks.append(run_user_simulation(user_id, [endpoint], results))

    # Führe alle User parallel aus
    await asyncio.gather(*tasks)

    results.end_time = time.time()
    return results


async def load_test_multiple_endpoints(
    endpoints: List[str], concurrent_users: int
) -> LoadTestResults:
    """Führt Load-Test für mehrere Endpoints aus."""
    results = LoadTestResults()
    results.start_time = time.time()

    # Erstelle User-Tasks
    tasks = []
    for user_id in range(concurrent_users):
        tasks.append(run_user_simulation(user_id, endpoints, results))

    # Führe alle User parallel aus
    await asyncio.gather(*tasks)

    results.end_time = time.time()
    return results


@pytest.mark.asyncio
@pytest.mark.load
async def test_health_endpoint_load():
    """Test: Health-Endpoint unter Last."""
    print("\n" + "=" * 60)
    print("🔥 Load-Test: Health Endpoint")
    print("=" * 60)

    for users in CONCURRENT_USERS:
        print(f"\n📊 Testing with {users} concurrent users...")
        results = await load_test_endpoint("/system/health", users)
        stats = results.get_statistics()

        print(f"  ✅ Successful: {stats['successful_requests']}")
        print(f"  ❌ Failed: {stats['failed_requests']}")
        print(f"  ⏱️  Response Time (median): {stats['response_times']['median']}s")
        print(f"  📈 Requests/sec: {stats['requests_per_second']}")

        # Assertions
        assert stats["error_rate"] < 5, f"Error rate too high: {stats['error_rate']}%"
        assert (
            stats["response_times"]["median"] < 1.0
        ), f"Median response time too high: {stats['response_times']['median']}s"


@pytest.mark.asyncio
@pytest.mark.load
async def test_api_endpoints_load():
    """Test: Haupt-API-Endpoints unter Last."""
    print("\n" + "=" * 60)
    print("🔥 Load-Test: API Endpoints")
    print("=" * 60)

    endpoints = [
        "/api/v1/decisions?limit=10",
        "/api/v1/stats/summary",
        "/api/v1/search?query=DSGVO&limit=10",
        "/system/metrics",
    ]

    for users in CONCURRENT_USERS:
        print(f"\n📊 Testing with {users} concurrent users...")
        results = await load_test_multiple_endpoints(endpoints, users)
        stats = results.get_statistics()

        print(f"  ✅ Successful: {stats['successful_requests']}")
        print(f"  ❌ Failed: {stats['failed_requests']}")
        print(f"  ⏱️  Response Times:")
        print(f"     Min: {stats['response_times']['min']}s")
        print(f"     Median: {stats['response_times']['median']}s")
        print(f"     Max: {stats['response_times']['max']}s")
        if stats["response_times"]["p95"]:
            print(f"     P95: {stats['response_times']['p95']}s")
        print(f"  📈 Requests/sec: {stats['requests_per_second']}")
        print(f"  📊 Status Codes: {stats['status_codes']}")

        # Assertions für niedrige Last
        if users <= 10:
            assert (
                stats["error_rate"] < 1
            ), f"Error rate too high for {users} users: {stats['error_rate']}%"
            assert (
                stats["response_times"]["median"] < 0.5
            ), f"Median response time too high: {stats['response_times']['median']}s"

        # Lockerere Kriterien für hohe Last
        elif users <= 50:
            assert (
                stats["error_rate"] < 5
            ), f"Error rate too high for {users} users: {stats['error_rate']}%"
            assert (
                stats["response_times"]["median"] < 2.0
            ), f"Median response time too high: {stats['response_times']['median']}s"

        else:  # 100+ users
            assert (
                stats["error_rate"] < 10
            ), f"Error rate too high for {users} users: {stats['error_rate']}%"
            assert (
                stats["response_times"]["median"] < 5.0
            ), f"Median response time too high: {stats['response_times']['median']}s"


@pytest.mark.asyncio
@pytest.mark.load
async def test_sustained_load():
    """Test: Anhaltende Last über längere Zeit."""
    print("\n" + "=" * 60)
    print("🔥 Load-Test: Sustained Load (30 seconds)")
    print("=" * 60)

    DURATION_SECONDS = 30
    USERS = 20

    results = LoadTestResults()
    results.start_time = time.time()

    print(f"Running {USERS} users for {DURATION_SECONDS} seconds...")

    # Starte User-Simulationen
    tasks = []
    endpoints = ["/api/v1/decisions?limit=5", "/api/v1/stats/summary"]

    async def continuous_user(user_id: int):
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            end_time = time.time() + DURATION_SECONDS
            request_count = 0

            while time.time() < end_time:
                endpoint = endpoints[request_count % len(endpoints)]
                await make_request(client, endpoint, results)
                request_count += 1
                await asyncio.sleep(0.5)  # 2 requests per second per user

    # Starte alle User
    for user_id in range(USERS):
        tasks.append(continuous_user(user_id))

    await asyncio.gather(*tasks)

    results.end_time = time.time()
    stats = results.get_statistics()

    print(f"\n📊 Results after {DURATION_SECONDS} seconds:")
    print(f"  ✅ Total Requests: {stats['total_requests']}")
    print(f"  ✅ Successful: {stats['successful_requests']}")
    print(f"  ❌ Failed: {stats['failed_requests']}")
    print(f"  📈 Avg Requests/sec: {stats['requests_per_second']}")
    print(f"  ⏱️  Response Times:")
    print(f"     Median: {stats['response_times']['median']}s")
    print(f"     P95: {stats['response_times'].get('p95', 'N/A')}s")
    print(f"  📊 Error Rate: {stats['error_rate']}%")

    # Assertions
    assert stats["error_rate"] < 5, f"Error rate too high: {stats['error_rate']}%"
    assert (
        stats["response_times"]["median"] < 1.0
    ), "Median response time degraded under sustained load"


@pytest.mark.asyncio
@pytest.mark.load
async def test_spike_load():
    """Test: Plötzlicher Anstieg der Last."""
    print("\n" + "=" * 60)
    print("🔥 Load-Test: Spike Load")
    print("=" * 60)

    # Phase 1: Normale Last
    print("\n📊 Phase 1: Normal Load (10 users)")
    normal_results = await load_test_endpoint("/api/v1/decisions?limit=10", 10)
    normal_stats = normal_results.get_statistics()
    print(f"  Median Response: {normal_stats['response_times']['median']}s")

    # Phase 2: Spike
    print("\n📊 Phase 2: Spike Load (100 users)")
    spike_results = await load_test_endpoint("/api/v1/decisions?limit=10", 100)
    spike_stats = spike_results.get_statistics()
    print(f"  Median Response: {spike_stats['response_times']['median']}s")
    print(f"  Error Rate: {spike_stats['error_rate']}%")

    # Phase 3: Recovery
    await asyncio.sleep(5)  # Kurze Pause
    print("\n📊 Phase 3: Recovery (10 users)")
    recovery_results = await load_test_endpoint("/api/v1/decisions?limit=10", 10)
    recovery_stats = recovery_results.get_statistics()
    print(f"  Median Response: {recovery_stats['response_times']['median']}s")

    # Assertions
    assert spike_stats["error_rate"] < 20, "System failed under spike load"
    assert (
        recovery_stats["response_times"]["median"] < normal_stats["response_times"]["median"] * 2
    ), "System didn't recover properly after spike"


# Hilfsfunktion für manuellen Test
async def run_load_tests():
    """Führt alle Load-Tests aus."""
    tests = [
        test_health_endpoint_load,
        test_api_endpoints_load,
        test_sustained_load,
        test_spike_load,
    ]

    for test in tests:
        try:
            await test()
            print(f"\n✅ {test.__name__} passed")
        except AssertionError as e:
            print(f"\n❌ {test.__name__} failed: {e}")
        except Exception as e:
            print(f"\n❌ {test.__name__} error: {e}")


if __name__ == "__main__":
    print(
        """
╔══════════════════════════════════════════════════════════════╗
║                Datenschutz-Rechtsprechung API - Load Testing                   ║
╚══════════════════════════════════════════════════════════════╝
    """
    )

    print("\n⚠️  Stelle sicher, dass die API läuft auf: " + BASE_URL)
    input("\nDrücke Enter um die Load-Tests zu starten...")

    asyncio.run(run_load_tests())

    print("\n" + "=" * 60)
    print("🏁 Load-Tests abgeschlossen!")
    print("=" * 60)
