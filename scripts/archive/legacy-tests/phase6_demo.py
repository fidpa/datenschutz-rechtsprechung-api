#!/usr/bin/env python
"""
Phase 6 Demo Script - Testet die neuen Komponenten.
"""

import asyncio
import sys
from pathlib import Path

# Füge src zum Python-Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import get_async_session, Decision
from src.collectors.openlegaldata import OpenLegalDataCollector
from src.processors.deduplicator import DecisionDeduplicator
from src.utils.logging import get_logger

logger = get_logger("phase6.demo")


async def demo_openlegaldata():
    """Demonstriert OpenLegalData Collector."""
    print("\n" + "="*60)
    print("🚀 Phase 6: OpenLegalData Integration Demo")
    print("="*60)
    
    async with get_async_session() as session:
        print("\n📡 Initialisiere OpenLegalData Collector...")
        collector = OpenLegalDataCollector(
            session, 
            max_pages=1,
            page_size=3  # Nur 3 Entscheidungen für Demo
        )
        
        async with collector:
            # 1. API-Zugang prüfen
            print("\n✅ Prüfe API-Zugang...")
            if await collector.validate_access():
                print("   → API ist erreichbar!")
            else:
                print("   → ❌ API nicht erreichbar")
                return
            
            # 2. Sammle einige DSGVO-Entscheidungen
            print("\n📥 Sammle DSGVO-relevante Entscheidungen...")
            decisions = []
            
            async for decision in collector.collect(full_crawl=False):
                decisions.append(decision)
                print(f"\n   📄 Entscheidung {len(decisions)}:")
                print(f"      Titel: {decision.title[:60]}...")
                print(f"      Gericht: {decision.court}")
                print(f"      Datum: {decision.decision_date}")
                print(f"      DSGVO-Artikel: {', '.join(decision.gdpr_articles[:3]) if decision.gdpr_articles else 'Keine'}")
                
                if len(decisions) >= 3:
                    break
            
            # 3. Statistiken
            stats = collector.calculate_progress()
            print(f"\n📊 Crawler-Statistiken:")
            print(f"   → Gesammelt: {stats['total_processed']} Entscheidungen")
            print(f"   → Erfolgsrate: {stats['success_rate']}%")
            print(f"   → DSGVO-relevant: {collector.gdpr_relevant_cases}")
    
    return decisions


async def demo_deduplication(decisions):
    """Demonstriert Deduplizierung."""
    print("\n" + "="*60)
    print("🔍 Deduplizierungs-Demo")
    print("="*60)
    
    if not decisions:
        print("   → Keine Entscheidungen zum Deduplizieren")
        return
    
    async with get_async_session() as session:
        deduplicator = DecisionDeduplicator(session)
        
        print(f"\n🔎 Prüfe {len(decisions)} Entscheidungen auf Duplikate...")
        
        for decision in decisions[:2]:  # Nur erste 2 für Demo
            duplicates = await deduplicator.find_duplicates(
                decision, 
                check_content=False  # Schneller ohne Content-Check
            )
            
            if duplicates:
                print(f"\n   ⚠️ Duplikate gefunden für: {decision.title[:50]}...")
                print(f"      → {len(duplicates)} potenzielle Duplikate")
            else:
                print(f"\n   ✅ Keine Duplikate für: {decision.title[:50]}...")
        
        # Statistiken
        stats = await deduplicator.get_statistics()
        print(f"\n📊 Deduplizierungs-Statistiken:")
        print(f"   → Gesamt in DB: {stats['database_stats']['total_decisions']}")
        print(f"   → Eindeutige Aktenzeichen: {stats['database_stats']['unique_case_numbers']}")
        print(f"   → Potenzielle Duplikate: {stats['database_stats']['potential_duplicates']}")


async def demo_celery_tasks():
    """Zeigt Celery Tasks Setup."""
    print("\n" + "="*60)
    print("⏰ Celery Tasks Setup")
    print("="*60)
    
    print("\n📅 Konfigurierte automatische Crawls:")
    print("   → 02:00 Uhr: GDPRhub (täglich)")
    print("   → 03:00 Uhr: OpenLegalData (täglich)")
    print("   → 05:00 Uhr: Deduplizierung (täglich)")
    print("   → 06:00 Uhr: Statistik-Update (täglich)")
    
    print("\n🚀 Celery Worker starten mit:")
    print("   celery -A src.tasks.celery_app worker --loglevel=info")
    
    print("\n📊 Celery Beat (Scheduler) starten mit:")
    print("   celery -A src.tasks.celery_app beat --loglevel=info")


async def main():
    """Hauptfunktion."""
    print("\n" + "="*80)
    print("                    GDPR CRAWLER - PHASE 6 DEMO")
    print("                     Datenquellen-Erweiterung")
    print("="*80)
    
    print("\n✅ Implementierte Komponenten:")
    print("   1. OpenLegalData Collector (250k+ deutsche Entscheidungen)")
    print("   2. Deduplizierungs-System (Exact, Fuzzy, Content-basiert)")
    print("   3. Celery Tasks für automatisierte Crawls")
    print("   4. Unit-Tests für alle neuen Komponenten")
    
    # 1. OpenLegalData Demo
    decisions = await demo_openlegaldata()
    
    # 2. Deduplizierungs-Demo
    await demo_deduplication(decisions)
    
    # 3. Celery Tasks Info
    await demo_celery_tasks()
    
    print("\n" + "="*80)
    print("✅ Phase 6 Demo abgeschlossen!")
    print("\n🎯 Nächste Schritte:")
    print("   → RIS Österreich Integration evaluieren")
    print("   → Performance-Optimierung für 10k+ Entscheidungen")
    print("   → Excel-Export mit Pandas implementieren")
    print("="*80 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Demo abgebrochen")
    except Exception as e:
        print(f"\n\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()