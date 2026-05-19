#!/usr/bin/env python
"""
Test-Script für OpenLegalData Collector.
Testet die API-Verbindung und crawlt einige Test-Entscheidungen.
"""

import asyncio
import sys
from pathlib import Path

# Füge src zum Python-Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import get_async_session
from src.collectors.openlegaldata import OpenLegalDataCollector
from src.processors.deduplicator import DecisionDeduplicator
from src.utils.logging import get_logger

logger = get_logger("test.openlegaldata")


async def test_api_access():
    """Testet die API-Verbindung."""
    print("\n=== Testing OpenLegalData API Access ===")
    
    async with get_async_session() as session:
        collector = OpenLegalDataCollector(session, max_pages=1)
        
        async with collector:
            is_accessible = await collector.validate_access()
            
            if is_accessible:
                print("✅ API is accessible")
                return True
            else:
                print("❌ API is not accessible")
                return False


async def test_crawl_decisions(max_decisions: int = 5):
    """
    Testet das Crawlen von Entscheidungen.
    
    Args:
        max_decisions: Anzahl zu crawlender Test-Entscheidungen
    """
    print(f"\n=== Crawling {max_decisions} Test Decisions ===")
    
    async with get_async_session() as session:
        collector = OpenLegalDataCollector(
            session, 
            max_pages=1,  # Nur erste Seite
            page_size=max_decisions
        )
        
        async with collector:
            decisions_collected = []
            
            async for decision in collector.collect(full_crawl=False):
                decisions_collected.append(decision)
                
                print(f"\n📄 Decision {len(decisions_collected)}:")
                print(f"  Title: {decision.title[:80]}...")
                print(f"  Court: {decision.court}")
                print(f"  Date: {decision.decision_date}")
                print(f"  Case Number: {decision.case_number}")
                print(f"  GDPR Articles: {decision.gdpr_articles}")
                print(f"  Keywords: {decision.keywords[:5] if decision.keywords else []}")
                
                if len(decisions_collected) >= max_decisions:
                    break
            
            # Statistiken
            stats = collector.calculate_progress()
            print(f"\n📊 Statistics:")
            print(f"  Total Fetched: {stats['total_fetched']}")
            print(f"  Total Processed: {stats['total_processed']}")
            print(f"  Total Errors: {stats['total_errors']}")
            print(f"  Success Rate: {stats['success_rate']}%")
            print(f"  GDPR Relevant: {collector.gdpr_relevant_cases}")
            
            return decisions_collected


async def test_deduplication():
    """Testet die Deduplizierung."""
    print("\n=== Testing Deduplication ===")
    
    async with get_async_session() as session:
        deduplicator = DecisionDeduplicator(session)
        
        # Hole Statistiken
        stats = await deduplicator.get_statistics()
        
        print(f"📊 Deduplication Statistics:")
        print(f"  Total Decisions: {stats['database_stats']['total_decisions']}")
        print(f"  Unique Case Numbers: {stats['database_stats']['unique_case_numbers']}")
        print(f"  Potential Duplicates: {stats['database_stats']['potential_duplicates']}")
        
        # Teste Deduplizierung für neueste Entscheidungen
        from sqlalchemy import select
        from src.database import Decision
        
        stmt = select(Decision).limit(10)
        result = await session.execute(stmt)
        recent_decisions = result.scalars().all()
        
        if recent_decisions:
            print(f"\n🔍 Checking {len(recent_decisions)} decisions for duplicates...")
            
            for decision in recent_decisions[:3]:  # Nur erste 3 für Test
                duplicates = await deduplicator.find_duplicates(decision, check_content=False)
                
                if duplicates:
                    print(f"\n  ⚠️ Found {len(duplicates)} duplicates for:")
                    print(f"     {decision.title[:60]}...")
                    for dup in duplicates[:2]:
                        print(f"     - {dup.source}: {dup.title[:50]}...")


async def test_search_terms():
    """Testet verschiedene DSGVO-Suchbegriffe."""
    print("\n=== Testing GDPR Search Terms ===")
    
    import httpx
    
    search_terms = ["DSGVO", "Datenschutz", "Art. 15 DSGVO", "BDSG"]
    
    async with httpx.AsyncClient() as client:
        for term in search_terms:
            try:
                response = await client.get(
                    "https://de.openlegaldata.io/api/cases/",
                    params={"q": term, "page_size": 1},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    count = data.get("count", 0)
                    print(f"  '{term}': {count:,} results")
                else:
                    print(f"  '{term}': ❌ Error {response.status_code}")
                    
            except Exception as e:
                print(f"  '{term}': ❌ {str(e)}")


async def main():
    """Hauptfunktion für Tests."""
    print("=" * 60)
    print("OpenLegalData Collector Test Suite")
    print("=" * 60)
    
    # 1. Test API Access
    if not await test_api_access():
        print("\n❌ API not accessible, aborting tests")
        return
    
    # 2. Test Search Terms
    await test_search_terms()
    
    # 3. Test Crawling
    decisions = await test_crawl_decisions(max_decisions=3)
    
    if decisions:
        print(f"\n✅ Successfully collected {len(decisions)} decisions")
    else:
        print("\n⚠️ No decisions collected")
    
    # 4. Test Deduplication
    await test_deduplication()
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())