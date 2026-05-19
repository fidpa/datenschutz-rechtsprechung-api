#!/usr/bin/env python
"""
Test-Skript für die Datenschutz-Rechtsprechung API API.
Testet alle wichtigen Endpoints und gibt eine Zusammenfassung aus.
"""

import asyncio
import sys
from pathlib import Path
import httpx
import json
from datetime import datetime

# API Base URL
API_BASE = "http://localhost:8000"


async def test_health():
    """Testet Health-Check Endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE}/health")
        data = response.json()

        print("🏥 Health Check:")
        print(f"   Status: {data['status']}")
        print(f"   Database: {data['database']}")
        print(f"   Environment: {data['environment']}")

        return response.status_code == 200 and data["status"] == "healthy"


async def test_decisions():
    """Testet Decisions CRUD Endpoints."""
    async with httpx.AsyncClient() as client:
        # Liste mit Pagination
        response = await client.get(
            f"{API_BASE}/api/v1/decisions/", params={"page": 1, "page_size": 5}
        )
        data = response.json()

        print("\n📋 Decisions API:")
        print(f"   Gesamt: {data.get('total', 0)} Entscheidungen")
        print(f"   Seiten: {data.get('pages', 0)}")
        print(f"   Aktuelle Seite: {data.get('page', 1)}")

        # Wenn Entscheidungen vorhanden, hole Details der ersten
        if data.get("items"):
            first_id = data["items"][0]["id"]
            detail_response = await client.get(f"{API_BASE}/api/v1/decisions/{first_id}")
            if detail_response.status_code == 200:
                detail = detail_response.json()
                print(f"   Erste Entscheidung: {detail['title'][:50]}...")

        return response.status_code == 200


async def test_search():
    """Testet Volltext-Suche."""
    async with httpx.AsyncClient() as client:
        # Einfache Suche
        response = await client.get(
            f"{API_BASE}/api/v1/search/", params={"q": "Datenschutz", "limit": 5}
        )

        if response.status_code == 200:
            data = response.json()
            print("\n🔍 Volltext-Suche:")
            print(f"   Query: '{data['query']}'")
            print(f"   Treffer: {data.get('total', 0)}")
            print(f"   Suchzeit: {data.get('took_ms', 0)}ms")

            if data.get("results"):
                print(f"   Top-Ergebnis: {data['results'][0]['title'][:50]}...")
                print(f"   Relevanz: {data['results'][0]['relevance']:.2f}")
        else:
            print("\n🔍 Volltext-Suche:")
            print(f"   ⚠️ Fehler: Status {response.status_code}")

        return response.status_code == 200


async def test_stats():
    """Testet Statistik-Endpoints."""
    async with httpx.AsyncClient() as client:
        # Haupt-Statistiken
        response = await client.get(f"{API_BASE}/api/v1/stats/")

        if response.status_code == 200:
            data = response.json()
            print("\n📊 Statistiken:")
            print(f"   Gesamt Entscheidungen: {data['total_decisions']}")
            print(f"   Anonymisiert: {data['total_anonymized']}")
            print(f"   Mit DSGVO-Referenz: {data['total_with_gdpr']}")

            if data.get("by_source"):
                print("   Nach Quelle:")
                for source, count in data["by_source"].items():
                    print(f"     - {source}: {count}")

            if data.get("top_gdpr_articles"):
                print("   Top DSGVO-Artikel:")
                for i, article in enumerate(data["top_gdpr_articles"][:3], 1):
                    print(f"     {i}. {article['article']}: {article['count']}x")

        # Summary Stats
        summary_response = await client.get(f"{API_BASE}/api/v1/stats/summary")
        if summary_response.status_code == 200:
            summary = summary_response.json()
            print(f"   Anonymisierungsrate: {summary['overview']['anonymized_percentage']}%")

        return response.status_code == 200


async def test_swagger():
    """Prüft ob Swagger UI verfügbar ist."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE}/docs")

        print("\n📚 API Dokumentation:")
        if response.status_code == 200 and "Swagger UI" in response.text:
            print(f"   ✅ Swagger UI verfügbar: {API_BASE}/docs")
        else:
            print(f"   ⚠️ Swagger UI nicht verfügbar")

        # OpenAPI Schema
        openapi_response = await client.get(f"{API_BASE}/openapi.json")
        if openapi_response.status_code == 200:
            openapi = openapi_response.json()
            print(f"   OpenAPI Version: {openapi.get('openapi', 'unknown')}")
            print(f"   API Version: {openapi['info']['version']}")

            # Zähle Endpoints
            paths = openapi.get("paths", {})
            total_endpoints = sum(len(methods) for methods in paths.values())
            print(f"   Endpoints: {total_endpoints}")

        return response.status_code == 200


async def main():
    """Hauptfunktion für alle Tests."""

    print("\n" + "=" * 60)
    print("🚀 Datenschutz-Rechtsprechung API API Test Suite")
    print("=" * 60)
    print(f"📍 API URL: {API_BASE}")
    print(f"🕐 Zeitpunkt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Prüfe ob API erreichbar ist
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE}/", timeout=5.0)
            if response.status_code != 200:
                print("\n❌ API nicht erreichbar!")
                print("   Starte die API mit: uvicorn src.api.main:app --reload")
                return
    except Exception as e:
        print(f"\n❌ Verbindung zur API fehlgeschlagen: {e}")
        print("   Starte die API mit: uvicorn src.api.main:app --reload")
        return

    # Führe Tests aus
    results = {}

    tests = [
        ("Health Check", test_health),
        ("Decisions API", test_decisions),
        ("Volltext-Suche", test_search),
        ("Statistiken", test_stats),
        ("API Dokumentation", test_swagger),
    ]

    for name, test_func in tests:
        try:
            result = await test_func()
            results[name] = "✅ OK" if result else "⚠️ Fehler"
        except Exception as e:
            results[name] = f"❌ Exception: {str(e)[:50]}"
            print(f"\n❌ Fehler bei {name}: {e}")

    # Zusammenfassung
    print("\n" + "=" * 60)
    print("📊 Test-Zusammenfassung:")
    print("=" * 60)

    for test_name, result in results.items():
        print(f"   {test_name}: {result}")

    # Gesamt-Status
    all_passed = all("✅" in r for r in results.values())

    print("=" * 60)
    if all_passed:
        print("✨ Alle Tests erfolgreich!")
    else:
        print("⚠️ Einige Tests fehlgeschlagen - siehe Details oben")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
