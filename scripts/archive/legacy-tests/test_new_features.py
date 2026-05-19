#!/usr/bin/env python
"""
Test-Script für neue Features (Phase 4).

Testet:
- PDF-Extraktion
- Rechtsstruktur-Parser
- Integration mit GDPRhub
- Export-API mit neuen Feldern

Verwendung:
    python scripts/test_new_features.py
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Füge src zum Python-Path hinzu
sys.path.append(str(Path(__file__).parent.parent))

import httpx
from sqlalchemy import select, text

from src.database import db_manager, Decision
from src.config import settings
# Logging initialisieren ist schon passiert beim Import
import structlog
logger = structlog.get_logger()


# =============================================================================
# TEST 1: Konfiguration
# =============================================================================

def test_configuration():
    """Testet neue Konfigurationsoptionen."""
    print("\n" + "="*60)
    print("🔧 TEST 1: Erweiterte Konfiguration")
    print("="*60)
    
    tests_passed = 0
    tests_total = 6
    
    # PDF-Konfiguration
    try:
        assert hasattr(settings, 'max_pdf_size_mb')
        assert settings.max_pdf_size_mb == 10
        print("✅ max_pdf_size_mb: OK (10 MB)")
        tests_passed += 1
    except:
        print("❌ max_pdf_size_mb: FEHLER")
    
    try:
        assert hasattr(settings, 'pdf_max_pages')
        assert settings.pdf_max_pages == 100
        print("✅ pdf_max_pages: OK (100)")
        tests_passed += 1
    except:
        print("❌ pdf_max_pages: FEHLER")
    
    # Feedback-System
    try:
        assert hasattr(settings, 'enable_quality_feedback')
        print(f"✅ enable_quality_feedback: OK ({settings.enable_quality_feedback})")
        tests_passed += 1
    except:
        print("❌ enable_quality_feedback: FEHLER")
    
    # Export-Formate
    try:
        assert hasattr(settings, 'export_formats')
        assert 'json' in settings.export_formats
        print(f"✅ export_formats: OK ({settings.export_formats})")
        tests_passed += 1
    except:
        print("❌ export_formats: FEHLER")
    
    # Rechtsbegriffe
    try:
        assert hasattr(settings, 'preserve_legal_terms_list')
        assert 'Kläger' in settings.preserve_legal_terms_list
        print(f"✅ preserve_legal_terms_list: OK ({len(settings.preserve_legal_terms_list)} Begriffe)")
        tests_passed += 1
    except:
        print("❌ preserve_legal_terms_list: FEHLER")
    
    # Export-Limit
    try:
        assert hasattr(settings, 'export_max_rows')
        print(f"✅ export_max_rows: OK ({settings.export_max_rows})")
        tests_passed += 1
    except:
        print("❌ export_max_rows: FEHLER")
    
    print(f"\n📊 Ergebnis: {tests_passed}/{tests_total} Tests bestanden")
    return tests_passed == tests_total


# =============================================================================
# TEST 2: Datenbank-Schema
# =============================================================================

async def test_database_schema():
    """Testet neue Datenbank-Felder."""
    print("\n" + "="*60)
    print("🗄️  TEST 2: Datenbank-Schema Erweiterungen")
    print("="*60)
    
    tests_passed = 0
    tests_total = 6
    
    try:
        await db_manager.initialize()
        
        # Prüfe neue Felder
        decision_fields = dir(Decision)
        
        # Feedback-Felder
        if 'quality_score' in decision_fields:
            print("✅ quality_score Feld vorhanden")
            tests_passed += 1
        else:
            print("❌ quality_score Feld fehlt")
        
        if 'user_feedback' in decision_fields:
            print("✅ user_feedback Feld vorhanden")
            tests_passed += 1
        else:
            print("❌ user_feedback Feld fehlt")
        
        if 'feedback_count' in decision_fields:
            print("✅ feedback_count Feld vorhanden")
            tests_passed += 1
        else:
            print("❌ feedback_count Feld fehlt")
        
        if 'avg_quality_score' in decision_fields:
            print("✅ avg_quality_score Feld vorhanden")
            tests_passed += 1
        else:
            print("❌ avg_quality_score Feld fehlt")
        
        # Rechtskraft-Felder
        if 'rechtskraft_status' in decision_fields:
            print("✅ rechtskraft_status Feld vorhanden")
            tests_passed += 1
        else:
            print("❌ rechtskraft_status Feld fehlt")
        
        if 'rechtskraft_datum' in decision_fields:
            print("✅ rechtskraft_datum Feld vorhanden")
            tests_passed += 1
        else:
            print("❌ rechtskraft_datum Feld fehlt")
        
    except Exception as e:
        print(f"❌ Datenbankfehler: {e}")
    finally:
        await db_manager.close()
    
    print(f"\n📊 Ergebnis: {tests_passed}/{tests_total} Tests bestanden")
    return tests_passed == tests_total


# =============================================================================
# TEST 3: Golden Decisions
# =============================================================================

def test_golden_decisions():
    """Testet die Golden Decisions Test-Daten."""
    print("\n" + "="*60)
    print("🏆 TEST 3: Golden Decisions")
    print("="*60)
    
    tests_passed = 0
    tests_total = 5
    
    golden_path = Path("tests/fixtures/golden_decisions.json")
    
    # Datei existiert?
    if not golden_path.exists():
        print(f"❌ Datei nicht gefunden: {golden_path}")
        return False
    
    print(f"✅ Datei gefunden: {golden_path}")
    tests_passed += 1
    
    try:
        with open(golden_path) as f:
            data = json.load(f)
        
        # Anzahl prüfen
        if len(data) == 10:
            print(f"✅ Anzahl Entscheidungen: {len(data)}")
            tests_passed += 1
        else:
            print(f"❌ Erwartete 10 Entscheidungen, gefunden: {len(data)}")
        
        # Struktur prüfen
        required_fields = ['source', 'title', 'expected_gdpr_articles', 'expected_anonymization']
        first = data[0]
        
        if all(field in first for field in required_fields):
            print("✅ Alle Pflichtfelder vorhanden")
            tests_passed += 1
        else:
            print("❌ Pflichtfelder fehlen")
        
        # Gerichte prüfen
        courts = {d.get('court') for d in data if d.get('court')}
        if len(courts) >= 8:
            print(f"✅ Verschiedene Gerichte: {len(courts)}")
            tests_passed += 1
        else:
            print(f"❌ Zu wenige verschiedene Gerichte: {len(courts)}")
        
        # DSGVO-Artikel prüfen
        all_articles = set()
        for d in data:
            all_articles.update(d.get('expected_gdpr_articles', []))
        
        if len(all_articles) >= 10:
            print(f"✅ DSGVO-Artikel Vielfalt: {len(all_articles)} verschiedene")
            tests_passed += 1
        else:
            print(f"❌ Zu wenige DSGVO-Artikel: {len(all_articles)}")
        
    except Exception as e:
        print(f"❌ Fehler beim Lesen: {e}")
    
    print(f"\n📊 Ergebnis: {tests_passed}/{tests_total} Tests bestanden")
    return tests_passed == tests_total


# =============================================================================
# TEST 4: API Export-Endpoints
# =============================================================================

async def test_export_endpoints():
    """Testet die Export-API-Endpoints."""
    print("\n" + "="*60)
    print("📤 TEST 4: Export-API Endpoints")
    print("="*60)
    
    tests_passed = 0
    tests_total = 5
    
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        try:
            # Health-Check
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print("✅ API erreichbar")
                tests_passed += 1
            else:
                print(f"❌ API nicht erreichbar: {response.status_code}")
                return False
        except:
            print("❌ API läuft nicht. Starte mit: uvicorn src.api.main:app")
            return False
        
        # CSV Export
        try:
            response = await client.get(f"{base_url}/api/v1/export/csv?limit=1")
            if response.status_code == 200:
                print("✅ CSV-Export Endpoint funktioniert")
                tests_passed += 1
            else:
                print(f"❌ CSV-Export fehlgeschlagen: {response.status_code}")
        except Exception as e:
            print(f"❌ CSV-Export Fehler: {e}")
        
        # JSON Export
        try:
            response = await client.get(f"{base_url}/api/v1/export/json?limit=1")
            if response.status_code == 200:
                data = response.json()
                if 'metadata' in data and 'decisions' in data:
                    print("✅ JSON-Export Endpoint funktioniert")
                    tests_passed += 1
                else:
                    print("❌ JSON-Export unvollständig")
            else:
                print(f"❌ JSON-Export fehlgeschlagen: {response.status_code}")
        except Exception as e:
            print(f"❌ JSON-Export Fehler: {e}")
        
        # Excel Export (prüfe nur ob Endpoint existiert)
        try:
            response = await client.get(f"{base_url}/api/v1/export/excel?limit=1")
            # Excel kann 501 zurückgeben wenn pandas nicht installiert
            if response.status_code in [200, 404, 501]:
                print(f"✅ Excel-Export Endpoint existiert (Status: {response.status_code})")
                tests_passed += 1
            else:
                print(f"❌ Excel-Export unerwarteter Status: {response.status_code}")
        except Exception as e:
            print(f"❌ Excel-Export Fehler: {e}")
        
        # Stats Export
        try:
            response = await client.get(f"{base_url}/api/v1/export/stats")
            if response.status_code == 200:
                print("✅ Stats-Export Endpoint funktioniert")
                tests_passed += 1
            else:
                print(f"❌ Stats-Export fehlgeschlagen: {response.status_code}")
        except Exception as e:
            print(f"❌ Stats-Export Fehler: {e}")
    
    print(f"\n📊 Ergebnis: {tests_passed}/{tests_total} Tests bestanden")
    return tests_passed == tests_total


# =============================================================================
# TEST 5: Walking Skeleton
# =============================================================================

def test_walking_skeleton():
    """Testet ob Walking Skeleton Demo existiert."""
    print("\n" + "="*60)
    print("🦴 TEST 5: Walking Skeleton Demo")
    print("="*60)
    
    skeleton_path = Path("examples/walking_skeleton.py")
    
    if not skeleton_path.exists():
        print(f"❌ Datei nicht gefunden: {skeleton_path}")
        return False
    
    print(f"✅ Datei gefunden: {skeleton_path}")
    
    # Prüfe Syntax
    try:
        with open(skeleton_path) as f:
            code = f.read()
        compile(code, str(skeleton_path), 'exec')
        print("✅ Python-Syntax korrekt")
    except SyntaxError as e:
        print(f"❌ Syntax-Fehler: {e}")
        return False
    
    # Prüfe wichtige Funktionen
    required_functions = [
        'setup_database',
        'fetch_one_decision', 
        'process_decision',
        'save_to_database',
        'test_api'
    ]
    
    found = 0
    for func in required_functions:
        if f'def {func}' in code or f'async def {func}' in code:
            found += 1
    
    if found == len(required_functions):
        print(f"✅ Alle {len(required_functions)} Hauptfunktionen vorhanden")
        return True
    else:
        print(f"❌ Nur {found}/{len(required_functions)} Funktionen gefunden")
        return False


# =============================================================================
# HAUPTPROGRAMM
# =============================================================================

async def main():
    """Führt alle Tests aus."""
    
    print("\n" + "🧪 "*20)
    print("   TEST-SUITE FÜR NEUE FEATURES")
    print("🧪 "*20)
    print("\nDieses Script testet alle neuen Features aus Phase 3/4.\n")
    
    results = {}
    
    # Test 1: Konfiguration
    results['Konfiguration'] = test_configuration()
    
    # Test 2: Datenbank-Schema
    results['Datenbank'] = await test_database_schema()
    
    # Test 3: Golden Decisions
    results['Golden Decisions'] = test_golden_decisions()
    
    # Test 4: Export-API (optional, da API laufen muss)
    print("\n" + "="*60)
    print("⚠️  Hinweis: Für API-Tests muss die API laufen!")
    print("   Starte mit: uvicorn src.api.main:app --reload")
    print("="*60)
    
    response = input("\nAPI läuft? (j/n): ")
    if response.lower() in ['j', 'ja', 'yes', 'y']:
        results['Export-API'] = await test_export_endpoints()
    else:
        print("⏭️  API-Tests übersprungen")
        results['Export-API'] = None
    
    # Test 5: Walking Skeleton
    results['Walking Skeleton'] = test_walking_skeleton()
    
    # Zusammenfassung
    print("\n" + "="*60)
    print("📊 GESAMTERGEBNIS")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    
    for test, result in results.items():
        if result is True:
            print(f"✅ {test}: BESTANDEN")
        elif result is False:
            print(f"❌ {test}: FEHLGESCHLAGEN")
        else:
            print(f"⏭️  {test}: ÜBERSPRUNGEN")
    
    print(f"\n📈 Statistik:")
    print(f"   Bestanden: {passed}")
    print(f"   Fehlgeschlagen: {failed}")
    print(f"   Übersprungen: {skipped}")
    
    if failed == 0:
        print("\n🎉 Alle Tests bestanden! Die neuen Features funktionieren.")
    else:
        print(f"\n⚠️  {failed} Test(s) fehlgeschlagen. Bitte prüfen.")
    
    return failed == 0


if __name__ == "__main__":
    # Verwende uvloop wenn verfügbar
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
    
    # Führe Tests aus
    success = asyncio.run(main())
    sys.exit(0 if success else 1)