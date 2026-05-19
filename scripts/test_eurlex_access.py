#!/usr/bin/env python3
"""
Test-Script für EUR-Lex Datenzugang.

Analysiert verfügbare EUR-Lex Zugangsmöglichkeiten für DSGVO-relevante Fälle.
"""

import json
import sys
from pathlib import Path
import requests
from datetime import datetime

# Füge src/ zum Python-Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_eurlex_access():
    """Testet verschiedene EUR-Lex Zugangsoptionen."""

    print("=" * 60)
    print("🇪🇺 EUR-LEX DATENZUGANG TEST")
    print("=" * 60)

    results = {"tested_at": datetime.now().isoformat(), "access_methods": {}}

    # 1. Test SPARQL Endpoint
    print("\n1️⃣ SPARQL Endpoint Test:")
    print("-" * 40)

    sparql_endpoint = "https://publications.europa.eu/webapi/rdf/sparql"

    # Einfache SPARQL-Abfrage für DSGVO-Dokumente
    sparql_query = """
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
    PREFIX ann: <http://publications.europa.eu/ontology/annotation#>
    
    SELECT ?celexid ?title WHERE {
        ?doc cdm:celexid ?celexid .
        ?doc cdm:title ?title .
        FILTER(CONTAINS(LCASE(STR(?title)), "gdpr") || CONTAINS(LCASE(STR(?title)), "data protection"))
    } LIMIT 5
    """

    try:
        response = requests.post(
            sparql_endpoint,
            data={"query": sparql_query},
            headers={"Accept": "application/json"},
            timeout=10,
        )

        if response.status_code == 200:
            print("✅ SPARQL Endpoint erreichbar")
            data = response.json()
            if "results" in data and "bindings" in data["results"]:
                print(f"   Gefundene Dokumente: {len(data['results']['bindings'])}")
                results["access_methods"]["sparql"] = {
                    "status": "available",
                    "sample_count": len(data["results"]["bindings"]),
                }
            else:
                print("   ⚠️ Keine Ergebnisse gefunden")
                results["access_methods"]["sparql"] = {"status": "no_results"}
        else:
            print(f"❌ SPARQL Endpoint nicht erreichbar (Status: {response.status_code})")
            results["access_methods"]["sparql"] = {"status": "error", "code": response.status_code}

    except requests.exceptions.Timeout:
        print("❌ SPARQL Endpoint Timeout")
        results["access_methods"]["sparql"] = {"status": "timeout"}
    except Exception as e:
        print(f"❌ SPARQL Fehler: {e}")
        results["access_methods"]["sparql"] = {"status": "error", "message": str(e)}

    # 2. Test Cellar REST API
    print("\n2️⃣ Cellar REST API Test:")
    print("-" * 40)

    # Test mit bekannter DSGVO CELEX-Nummer
    celex_gdpr = "32016R0679"  # DSGVO-Verordnung
    cellar_api = f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex_gdpr}"

    try:
        response = requests.head(cellar_api, timeout=10)
        if response.status_code == 200:
            print("✅ Cellar API erreichbar")
            print(f"   DSGVO-Dokument verfügbar (CELEX: {celex_gdpr})")
            results["access_methods"]["cellar"] = {"status": "available"}
        else:
            print(f"❌ Cellar API Problem (Status: {response.status_code})")
            results["access_methods"]["cellar"] = {"status": "error", "code": response.status_code}

    except Exception as e:
        print(f"❌ Cellar API Fehler: {e}")
        results["access_methods"]["cellar"] = {"status": "error", "message": str(e)}

    # 3. Test Webservice (benötigt Registrierung)
    print("\n3️⃣ EUR-Lex Webservice (SOAP):")
    print("-" * 40)
    print("ℹ️ Webservice benötigt EU-Login Registrierung")
    print("   URL: https://eur-lex.europa.eu/content/help/data-reuse/webservice.html")
    results["access_methods"]["webservice"] = {"status": "registration_required"}

    # 4. Bulk Download Information
    print("\n4️⃣ Bulk Download Options:")
    print("-" * 40)

    bulk_info = {
        "data_dump_service": {
            "url": "datadump.publications.europa.eu",
            "requirement": "EU Login Account",
            "formats": ["XML-Formex", "PDF", "HTML"],
        },
        "open_data_portal": {
            "url": "data.europa.eu",
            "availability": "Official Journals from 2004",
            "formats": ["CSV", "XML", "JSON-LD"],
        },
    }

    print("📦 Data Dump Service:")
    print(f"   • URL: {bulk_info['data_dump_service']['url']}")
    print(f"   • Voraussetzung: {bulk_info['data_dump_service']['requirement']}")
    print(f"   • Formate: {', '.join(bulk_info['data_dump_service']['formats'])}")

    print("\n📊 Open Data Portal:")
    print(f"   • URL: {bulk_info['open_data_portal']['url']}")
    print(f"   • Verfügbar: {bulk_info['open_data_portal']['availability']}")
    print(f"   • Formate: {', '.join(bulk_info['open_data_portal']['formats'])}")

    results["access_methods"]["bulk_download"] = bulk_info

    # 5. Alternative: CEPS Dataset
    print("\n5️⃣ Alternative - CEPS EurLex Dataset:")
    print("-" * 40)

    ceps_info = {
        "name": "CEPS EurLex Dataset",
        "size": "142,036 EU laws (1952-2019)",
        "format": "CSV",
        "license": "Open",
        "url": "https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/0EGYWY",
        "content": {"regulations": 102304, "directives": 4070, "decisions": 35798},
    }

    print(f"📚 {ceps_info['name']}:")
    print(f"   • Umfang: {ceps_info['size']}")
    print(f"   • Format: {ceps_info['format']}")
    print(f"   • Inhalt:")
    for doc_type, count in ceps_info["content"].items():
        print(f"     - {doc_type.capitalize()}: {count:,}")
    print(f"   • URL: {ceps_info['url'][:50]}...")

    results["access_methods"]["ceps_dataset"] = ceps_info

    # 6. Test Sample Download (kleines XML)
    print("\n6️⃣ Sample Download Test:")
    print("-" * 40)

    # Versuche ein kleines DSGVO-bezogenes Dokument zu laden
    sample_url = "https://eur-lex.europa.eu/legal-content/EN/TXT/XML/?uri=CELEX:32016R0679"

    try:
        print(f"Lade DSGVO-Verordnung (XML)...")
        response = requests.get(sample_url, timeout=15, stream=True)

        if response.status_code == 200:
            # Lade nur ersten Teil für Analyse
            content_sample = response.content[:5000]

            # Prüfe ob es XML ist
            if b"<?xml" in content_sample:
                print("✅ XML-Download erfolgreich")
                print(f"   Größe: {len(response.content) / 1024:.1f} KB")

                # Speichere Sample
                sample_file = Path("eurlex_gdpr_sample.xml")
                with open(sample_file, "wb") as f:
                    f.write(response.content[:10000])  # Nur erste 10KB
                print(f"   Sample gespeichert: {sample_file}")

                results["sample_download"] = {
                    "status": "success",
                    "file": str(sample_file),
                    "size_kb": len(response.content) / 1024,
                }
            else:
                print("⚠️ Unerwartetes Format (kein XML)")
                results["sample_download"] = {"status": "wrong_format"}
        else:
            print(f"❌ Download fehlgeschlagen (Status: {response.status_code})")
            results["sample_download"] = {"status": "error", "code": response.status_code}

    except Exception as e:
        print(f"❌ Download-Fehler: {e}")
        results["sample_download"] = {"status": "error", "message": str(e)}

    # Zusammenfassung
    print("\n" + "=" * 60)
    print("📊 ZUSAMMENFASSUNG:")
    print("=" * 60)

    available_methods = []
    registration_required = []

    for method, info in results["access_methods"].items():
        if isinstance(info, dict):
            if info.get("status") == "available":
                available_methods.append(method)
            elif info.get("status") == "registration_required" or "requirement" in info:
                registration_required.append(method)

    print("\n✅ Verfügbare Methoden:")
    for method in available_methods:
        print(f"   • {method.upper()}")

    print("\n🔐 Registrierung erforderlich:")
    for method in registration_required:
        print(f"   • {method.replace('_', ' ').title()}")

    print("\n💡 EMPFEHLUNGEN:")
    print("1. Für kleine Tests: Cellar REST API mit bekannten CELEX-Nummern")
    print("2. Für Bulk-Import: CEPS Dataset (142k Dokumente, CSV)")
    print("3. Für aktuelle Daten: EU Login für Data Dump Service")
    print("4. Für Programmierung: eurlex Python/R Packages")

    # Speichere Ergebnisse
    results_file = Path("eurlex_access_test.json")
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n💾 Detaillierte Ergebnisse gespeichert: {results_file}")

    return results


if __name__ == "__main__":
    try:
        results = test_eurlex_access()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unerwarteter Fehler: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
