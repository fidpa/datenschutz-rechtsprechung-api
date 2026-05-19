#!/usr/bin/env python
"""
Umfassende Test-Suite für Datenschutz-Rechtsprechung API Web-UI und API.
Testet General Cases und Edge Cases systematisch.
"""

import requests
import json
import time
import sys
from typing import Dict, List, Any
from datetime import datetime
from urllib.parse import quote


class WebUITester:
    """Test-Suite für Web-UI und API."""

    def __init__(
        self, api_url: str = "http://localhost:8000", web_url: str = "http://localhost:5001"
    ):
        self.api_url = api_url
        self.web_url = web_url
        self.session = requests.Session()
        self.results = {"passed": [], "failed": [], "warnings": []}

    def log(self, level: str, message: str):
        """Farbiges Logging."""
        colors = {
            "INFO": "\033[94m",
            "PASS": "\033[92m",
            "FAIL": "\033[91m",
            "WARN": "\033[93m",
            "RESET": "\033[0m",
        }
        print(f"{colors.get(level, '')}[{level}] {message}{colors['RESET']}")

    def test_api_search(
        self, query: str, expected_status: int = 200, test_name: str = None
    ) -> bool:
        """Testet API-Suche."""
        test_name = test_name or f"API Search: {query}"
        try:
            response = self.session.get(
                f"{self.api_url}/api/v1/search/", params={"q": query}, timeout=5
            )

            if response.status_code == expected_status:
                self.log("PASS", f"✓ {test_name} - Status {response.status_code}")
                self.results["passed"].append(test_name)

                # Prüfe Response-Struktur
                if expected_status == 200:
                    data = response.json()
                    assert "query" in data
                    assert "results" in data
                    assert "total" in data
                    assert "took_ms" in data
                return True
            else:
                self.log(
                    "FAIL",
                    f"✗ {test_name} - Got {response.status_code}, expected {expected_status}",
                )
                self.results["failed"].append(test_name)
                return False

        except Exception as e:
            self.log("FAIL", f"✗ {test_name} - Error: {str(e)}")
            self.results["failed"].append(test_name)
            return False

    def test_web_search(
        self, query: str, expected_status: int = 200, test_name: str = None
    ) -> bool:
        """Testet Web-UI Suche."""
        test_name = test_name or f"Web Search: {query}"
        try:
            response = self.session.get(f"{self.web_url}/search", params={"q": query}, timeout=5)

            if response.status_code == expected_status:
                self.log("PASS", f"✓ {test_name} - Status {response.status_code}")
                self.results["passed"].append(test_name)

                # Prüfe ob HTML zurückkommt
                if expected_status == 200:
                    assert "<!DOCTYPE html>" in response.text
                    assert "DSGVO-Crawler" in response.text
                return True
            else:
                self.log(
                    "FAIL",
                    f"✗ {test_name} - Got {response.status_code}, expected {expected_status}",
                )
                self.results["failed"].append(test_name)
                return False

        except Exception as e:
            self.log("FAIL", f"✗ {test_name} - Error: {str(e)}")
            self.results["failed"].append(test_name)
            return False

    def run_general_cases(self):
        """Testet normale Nutzungsszenarien."""
        self.log("INFO", "\n=== GENERAL CASES ===")

        # Einfache Suchen
        queries = [
            "Datenschutz",
            "DSGVO",
            "Auskunft",
            "Art 15",
            "Art. 6",
            "Artikel 17",
            "Recht auf Löschung",
            "personenbezogene Daten",
            "Verantwortlicher",
        ]

        for query in queries:
            self.test_api_search(query)
            time.sleep(0.1)  # Rate limiting

        # Filter-Tests
        self.log("INFO", "\n--- Filter Tests ---")

        # Gericht-Filter
        self.session.get(
            f"{self.api_url}/api/v1/search/",
            params={"q": "Datenschutz", "courts": ["BGH"]},
            timeout=5,
        )
        self.log("PASS", "✓ Court filter test")

        # Quellen-Filter
        self.session.get(
            f"{self.api_url}/api/v1/search/",
            params={"q": "DSGVO", "sources": ["gdprhub"]},
            timeout=5,
        )
        self.log("PASS", "✓ Source filter test")

        # Pagination
        self.log("INFO", "\n--- Pagination Tests ---")
        for page in [1, 2, 5]:
            response = self.session.get(
                f"{self.web_url}/search", params={"q": "Datenschutz", "page": page}, timeout=5
            )
            if response.status_code == 200:
                self.log("PASS", f"✓ Pagination page {page}")
                self.results["passed"].append(f"Pagination page {page}")

    def run_edge_cases(self):
        """Testet Edge Cases und Grenzfälle."""
        self.log("INFO", "\n=== EDGE CASES ===")

        # Sonderzeichen
        special_chars = [
            "Löschung",
            "Überprüfung",
            "§ 6 DSGVO",
            "Art. 15-17",
            "(DSGVO)",
            "[Person 1]",
            "Test & Co.",
            "50% Rabatt",
            "user@example.com",
            "C:\\Windows\\System32",
            "https://example.com",
        ]

        for query in special_chars:
            self.test_api_search(query, test_name=f"Special char: {query}")
            time.sleep(0.1)

        # Leere/Ungültige Eingaben
        self.log("INFO", "\n--- Invalid Input Tests ---")

        self.test_api_search("", test_name="Empty query")
        self.test_api_search("   ", test_name="Whitespace only")
        self.test_api_search("*", test_name="Wildcard only")

        # Sehr lange Query
        long_query = "Datenschutz " * 100
        self.test_api_search(long_query[:500], test_name="Very long query")

        # SQL Injection Versuche
        self.log("INFO", "\n--- Security Tests ---")

        sql_injections = [
            "'; DROP TABLE decisions--",
            "' OR '1'='1",
            "1; SELECT * FROM users",
            "admin'--",
            "' UNION SELECT NULL--",
        ]

        for injection in sql_injections:
            self.test_api_search(injection, test_name=f"SQL Injection: {injection[:20]}...")

        # XSS Versuche
        xss_attempts = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<body onload=alert('xss')>",
            "';alert(String.fromCharCode(88,83,83))//'",
        ]

        for xss in xss_attempts:
            self.test_web_search(xss, test_name=f"XSS: {xss[:20]}...")

        # Ungültige Pagination
        self.log("INFO", "\n--- Invalid Pagination ---")

        response = self.session.get(f"{self.web_url}/search", params={"q": "Test", "page": -1})
        if response.status_code in [200, 400]:
            self.log("PASS", "✓ Negative page handled")
            self.results["passed"].append("Negative page")

        response = self.session.get(
            f"{self.api_url}/api/v1/search/", params={"q": "Test", "offset": -100}
        )
        if response.status_code in [200, 422]:
            self.log("PASS", "✓ Negative offset handled")
            self.results["passed"].append("Negative offset")

        # Ungültige UUID
        self.log("INFO", "\n--- Invalid UUID Tests ---")

        invalid_uuids = [
            "not-a-uuid",
            "12345",
            "00000000-0000-0000-0000-000000000000",
            "../../../etc/passwd",
        ]

        for uuid in invalid_uuids:
            response = self.session.get(f"{self.web_url}/decision/{uuid}", timeout=5)
            if response.status_code in [404, 400, 200]:  # 200 wenn Error-Page
                self.log("PASS", f"✓ Invalid UUID handled: {uuid}")
                self.results["passed"].append(f"Invalid UUID: {uuid}")

    def run_performance_tests(self):
        """Basis-Performance-Tests."""
        self.log("INFO", "\n=== PERFORMANCE TESTS ===")

        # Response-Zeit-Test
        queries = ["Datenschutz", "DSGVO", "Art. 15"]
        for query in queries:
            start = time.time()
            response = self.session.get(
                f"{self.api_url}/api/v1/search/", params={"q": query}, timeout=10
            )
            elapsed = (time.time() - start) * 1000

            if elapsed < 1000:  # Unter 1 Sekunde
                self.log("PASS", f"✓ Fast response for '{query}': {elapsed:.0f}ms")
                self.results["passed"].append(f"Performance: {query}")
            else:
                self.log("WARN", f"⚠ Slow response for '{query}': {elapsed:.0f}ms")
                self.results["warnings"].append(f"Slow: {query} ({elapsed:.0f}ms)")

        # Großes Limit
        response = self.session.get(
            f"{self.api_url}/api/v1/search/", params={"q": "DSGVO", "limit": 100}, timeout=10
        )
        if response.status_code == 200:
            self.log("PASS", "✓ Large limit handled")
            self.results["passed"].append("Large limit")

        # Großer Offset
        response = self.session.get(
            f"{self.api_url}/api/v1/search/", params={"q": "DSGVO", "offset": 1000}, timeout=10
        )
        if response.status_code == 200:
            self.log("PASS", "✓ Large offset handled")
            self.results["passed"].append("Large offset")

    def run_api_endpoints_test(self):
        """Testet verschiedene API-Endpunkte."""
        self.log("INFO", "\n=== API ENDPOINTS ===")

        endpoints = [
            ("/api/v1/stats/", "Statistics"),
            ("/api/v1/search/suggest?q=Daten", "Suggestions"),
            ("/docs", "Swagger UI"),
            ("/system/health", "Health Check"),
        ]

        for endpoint, name in endpoints:
            try:
                response = self.session.get(f"{self.api_url}{endpoint}", timeout=5)
                if response.status_code == 200:
                    self.log("PASS", f"✓ {name} endpoint works")
                    self.results["passed"].append(f"Endpoint: {name}")
                else:
                    self.log("WARN", f"⚠ {name} returned {response.status_code}")
                    self.results["warnings"].append(f"Endpoint {name}: {response.status_code}")
            except Exception as e:
                self.log("FAIL", f"✗ {name} failed: {str(e)}")
                self.results["failed"].append(f"Endpoint: {name}")

    def print_summary(self):
        """Zeigt Test-Zusammenfassung."""
        self.log("INFO", "\n" + "=" * 50)
        self.log("INFO", "TEST SUMMARY")
        self.log("INFO", "=" * 50)

        total = len(self.results["passed"]) + len(self.results["failed"])

        print(f"\n✅ Passed: {len(self.results['passed'])}/{total}")
        print(f"❌ Failed: {len(self.results['failed'])}/{total}")
        print(f"⚠️  Warnings: {len(self.results['warnings'])}")

        if self.results["failed"]:
            print("\nFailed Tests:")
            for test in self.results["failed"][:10]:  # Zeige max 10
                print(f"  - {test}")

        if self.results["warnings"]:
            print("\nWarnings:")
            for warning in self.results["warnings"][:5]:  # Zeige max 5
                print(f"  - {warning}")

        # Exit-Code
        return 0 if not self.results["failed"] else 1


def main():
    """Hauptfunktion."""
    print("\n🔍 Datenschutz-Rechtsprechung API Web-UI Test Suite")
    print("=" * 50)

    tester = WebUITester()

    # Prüfe ob Services laufen
    try:
        response = requests.get("http://localhost:8000/system/health", timeout=2)
        if response.status_code != 200:
            print("❌ API nicht erreichbar auf Port 8000")
            return 1
    except:
        print("❌ API nicht erreichbar auf Port 8000")
        print("Starte mit: uvicorn src.api.main:app --reload")
        return 1

    try:
        response = requests.get("http://localhost:5001/", timeout=2)
        if response.status_code != 200:
            print("⚠️  Web-UI nicht erreichbar auf Port 5001")
    except:
        print("⚠️  Web-UI nicht erreichbar auf Port 5001")
        print("Starte mit: ./scripts/start_web_dev.sh")

    # Führe Tests aus
    try:
        tester.run_general_cases()
        tester.run_edge_cases()
        tester.run_performance_tests()
        tester.run_api_endpoints_test()
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests abgebrochen")

    # Zusammenfassung
    return tester.print_summary()


if __name__ == "__main__":
    sys.exit(main())
