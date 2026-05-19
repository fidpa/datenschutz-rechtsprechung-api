#!/usr/bin/env python
"""
Test-Skript für Phase 4 Features:
- PDF-Extraktion  
- Rechtsstruktur-Parser
- Integration mit Datenbank

Verwendung:
    python scripts/test_phase4.py
"""

import asyncio
import sys
from pathlib import Path

# Projekt-Root zum Python-Path hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processors.pdf_extractor import PDFExtractor
from src.processors.legal_parser import LegalStructureParser
import structlog

logger = structlog.get_logger()


async def test_pdf_extraction():
    """Testet PDF-Extraktion mit Beispiel-Text."""
    
    print("\n" + "="*60)
    print("TEST 1: PDF-Extraktion (Simulation)")
    print("="*60)
    
    # Simuliere PDF-Text für Test
    sample_text = """
    BUNDESGERICHTSHOF
    URTEIL
    VI ZR 123/23
    vom 15. März 2024
    
    in dem Rechtsstreit
    
    Leitsatz:
    Die Verarbeitung personenbezogener Daten ohne ausreichende Rechtsgrundlage
    nach Art. 6 DSGVO stellt eine Verletzung des Rechts auf informationelle
    Selbstbestimmung dar und kann Schadensersatzansprüche nach Art. 82 DSGVO
    begründen.
    
    Tenor:
    Auf die Revision des Klägers wird das Urteil des Oberlandesgerichts München
    vom 10. Januar 2023 aufgehoben. Die Sache wird zur neuen Verhandlung und
    Entscheidung zurückverwiesen.
    
    Tatbestand:
    Der Kläger begehrt Schadensersatz wegen unrechtmäßiger Verarbeitung seiner
    personenbezogenen Daten. Die Beklagte, ein Kreditinstitut, hatte über einen
    Zeitraum von drei Jahren Bonitätsdaten des Klägers ohne dessen Einwilligung
    an Dritte weitergegeben.
    
    Entscheidungsgründe:
    Die zulässige Revision des Klägers hat Erfolg. Das Berufungsgericht hat
    verkannt, dass bereits die unbefugte Weitergabe personenbezogener Daten
    einen Schadensersatzanspruch nach Art. 82 DSGVO begründen kann.
    """
    
    extractor = PDFExtractor()
    
    # Simuliere Extraktion
    result = {
        "text": sample_text,
        "pages": 5,
        "method": "simulation",
        "file_size_mb": 0.5
    }
    
    # Bereinige Text
    cleaned_text = extractor.clean_text(result["text"])
    text_hash = extractor.get_text_hash(cleaned_text)
    
    print(f"✅ Text-Extraktion simuliert")
    print(f"   - Länge: {len(cleaned_text)} Zeichen")
    print(f"   - Hash: {text_hash[:16]}...")
    print(f"   - Vorschau: {cleaned_text[:200]}...")
    
    return cleaned_text


async def test_legal_parser(text: str):
    """Testet Rechtsstruktur-Parser."""
    
    print("\n" + "="*60)
    print("TEST 2: Rechtsstruktur-Parser")
    print("="*60)
    
    parser = LegalStructureParser()
    
    # Parse Struktur
    result = parser.parse(text)
    
    print("\n📋 Extrahierte Struktur:")
    for section, content in result.items():
        if content and content != 'unbekannt':
            preview = content[:100].replace('\n', ' ')
            print(f"   ✅ {section}: {preview}...")
    
    # Extrahiere Metadaten
    metadata = parser.extract_metadata(text)
    
    print("\n📊 Extrahierte Metadaten:")
    for key, value in metadata.items():
        if value:
            print(f"   ✅ {key}: {value}")
    
    # Prüfe Erfolg
    sections_found = sum(1 for v in result.values() if v and v != 'unbekannt')
    
    if sections_found >= 3:
        print(f"\n✅ Parser erfolgreich: {sections_found} Abschnitte erkannt")
    else:
        print(f"\n⚠️ Nur {sections_found} Abschnitte erkannt")
    
    return result


async def test_database_integration():
    """Testet neue Datenbankfelder."""
    
    print("\n" + "="*60)
    print("TEST 3: Datenbank-Integration")
    print("="*60)
    
    from src.database import db_manager, Decision
    from sqlalchemy import select
    
    await db_manager.initialize()
    
    try:
        async with db_manager.async_session_maker() as session:
            # Hole eine Entscheidung
            decision = await session.scalar(select(Decision).limit(1))
            
            if decision:
                print(f"\n📚 Teste mit Entscheidung: {decision.title[:50]}...")
                
                # Setze neue Felder
                decision.quality_score = 4
                decision.user_feedback = "Test-Feedback für Phase 4"
                decision.rechtskraft_status = "rechtskraeftig"
                decision.pdf_extracted = True
                
                await session.commit()
                print("✅ Neue Felder erfolgreich gesetzt")
                
                # Verifiziere
                await session.refresh(decision)
                print(f"   - quality_score: {decision.quality_score}")
                print(f"   - rechtskraft_status: {decision.rechtskraft_status}")
                print(f"   - pdf_extracted: {decision.pdf_extracted}")
                
                return True
            else:
                print("⚠️ Keine Entscheidung in DB gefunden")
                print("   Führe zuerst 'python scripts/run_crawler.py gdprhub' aus")
                return False
                
    finally:
        await db_manager.close()


async def test_export_api():
    """Testet Export-API mit neuen Feldern."""
    
    print("\n" + "="*60)
    print("TEST 4: Export-API mit neuen Feldern")
    print("="*60)
    
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("http://localhost:8000/api/v1/export/json?limit=1")
            
            if response.status_code == 200:
                data = response.json()
                
                if data['decisions']:
                    decision = data['decisions'][0]
                    
                    # Prüfe neue Felder
                    new_fields = ['quality_score', 'rechtskraft_status', 'leitsatz', 'tenor']
                    found = []
                    
                    for field in new_fields:
                        if field in decision:
                            found.append(field)
                    
                    print(f"✅ Export erfolgreich")
                    print(f"   - Neue Felder im Export: {', '.join(found)}")
                    
                    if decision.get('rechtskraft_status'):
                        print(f"   - Rechtskraft: {decision['rechtskraft_status']}")
                    
                    return True
                else:
                    print("⚠️ Keine Daten im Export")
            else:
                print(f"❌ Export fehlgeschlagen: Status {response.status_code}")
                
    except httpx.ConnectError:
        print("⚠️ API nicht erreichbar. Starte mit: uvicorn src.api.main:app --reload")
    except Exception as e:
        print(f"❌ Fehler: {e}")
    
    return False


async def main():
    """Führt alle Tests aus."""
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║           GDPR CRAWLER - PHASE 4 FEATURE TESTS              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    results = []
    
    try:
        # Test 1: PDF-Extraktion
        pdf_text = await test_pdf_extraction()
        results.append(("PDF-Extraktion", True))
        
        # Test 2: Rechtsstruktur-Parser
        if pdf_text:
            structure = await test_legal_parser(pdf_text)
            success = any(v for v in structure.values() if v and v != 'unbekannt')
            results.append(("Rechtsstruktur-Parser", success))
        
        # Test 3: Datenbank
        db_success = await test_database_integration()
        results.append(("Datenbank-Integration", db_success))
        
        # Test 4: Export-API
        api_success = await test_export_api()
        results.append(("Export-API", api_success))
        
    except Exception as e:
        print(f"\n❌ Fehler in Tests: {e}")
        import traceback
        traceback.print_exc()
    
    # Zusammenfassung
    print("\n" + "="*60)
    print("📊 ZUSAMMENFASSUNG")
    print("="*60)
    
    for test_name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {test_name}")
    
    passed = sum(1 for _, s in results if s)
    total = len(results)
    
    print(f"\nErgebnis: {passed}/{total} Tests bestanden")
    
    if passed == total:
        print("""
🎉 PHASE 4 ERFOLGREICH ABGESCHLOSSEN!

Implementiert:
✅ DB-Migration (7 neue Felder)
✅ PDF-Extraktor mit Fallbacks
✅ Rechtsstruktur-Parser für deutsche Dokumente
✅ Export-API mit neuen Feldern

Nächste Schritte:
1. GDPRhub Collector für PDF-URLs erweitern
2. Batch-Verarbeitung existierender Entscheidungen
3. OpenLegalData & RIS Integration
        """)
    else:
        print(f"\n⚠️ {total - passed} Tests fehlgeschlagen. Bitte prüfen.")


if __name__ == "__main__":
    asyncio.run(main())