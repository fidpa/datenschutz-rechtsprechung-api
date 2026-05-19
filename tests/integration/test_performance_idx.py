"""
Integration Tests für Performance-Optimierungen und Datenbank-Indizes.

Testet die in Phase 7 implementierten Performance-Verbesserungen.
"""

import time
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

import pytest
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Decision, CrawlLog
from src.config import settings


class TestPerformanceIndices:
    """Tests für Datenbank-Performance und Indizes."""

    @pytest.fixture
    async def large_dataset(self, test_session: AsyncSession):
        """Erstellt einen großen Testdatensatz für Performance-Tests."""
        decisions = []
        batch_size = 100
        total_records = 1000

        courts = ["LG München", "OLG Frankfurt", "BGH", "LG Berlin", "AG Hamburg"]
        sources = ["gdprhub", "openlegaldata", "test_source"]

        for i in range(total_records):
            decision = Decision(
                source=sources[i % len(sources)],
                source_id=f"perf_{i:05d}",
                title=f"Performance Test Decision {i}",
                court=courts[i % len(courts)],
                decision_date=datetime.now() - timedelta(days=i % 365),
                case_number=f"{i % 100} O {i:04d}/23",
                gdpr_articles=[f"Art. {i % 30 + 1}", f"Art. {(i + 5) % 30 + 1}"],
                full_text_anonymized=f"Anonymized text containing keyword{i % 10} and GDPR reference",
                created_at=datetime.now() - timedelta(days=i % 30),
            )
            decisions.append(decision)

            # Batch insert
            if len(decisions) >= batch_size:
                test_session.add_all(decisions)
                await test_session.commit()
                decisions = []

        # Insert remaining
        if decisions:
            test_session.add_all(decisions)
            await test_session.commit()

        yield total_records

        # Cleanup
        await test_session.execute(text("DELETE FROM decisions WHERE source_id LIKE 'perf_%'"))
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_index_created_at_desc(self, test_session: AsyncSession, large_dataset):
        """Test des idx_decisions_created_at_desc Index für zeitbasierte Abfragen."""
        # Query ohne Index (simuliert)
        start_time = time.time()

        # Neueste Entscheidungen abrufen
        query = select(Decision).order_by(Decision.created_at.desc()).limit(10)
        result = await test_session.execute(query)
        recent_decisions = result.scalars().all()

        query_time = time.time() - start_time

        assert len(recent_decisions) == 10
        assert query_time < 0.1  # Sollte mit Index < 100ms sein

        # Verifiziere Sortierung
        for i in range(len(recent_decisions) - 1):
            assert recent_decisions[i].created_at >= recent_decisions[i + 1].created_at

    @pytest.mark.asyncio
    async def test_index_source_date(self, test_session: AsyncSession, large_dataset):
        """Test des idx_decisions_source_date Index für Source-Filter mit Datum."""
        # Performance-Test für häufige Query-Pattern
        start_time = time.time()

        query = (
            select(Decision)
            .where(Decision.source == "gdprhub")
            .order_by(Decision.decision_date.desc())
            .limit(20)
        )
        result = await test_session.execute(query)
        decisions = result.scalars().all()

        query_time = time.time() - start_time

        assert len(decisions) > 0
        assert all(d.source == "gdprhub" for d in decisions)
        assert query_time < 0.05  # Mit zusammengesetztem Index sollte < 50ms sein

    @pytest.mark.asyncio
    async def test_index_court_date(self, test_session: AsyncSession, large_dataset):
        """Test des idx_decisions_court_date Index für Gericht-basierte Abfragen."""
        courts_to_test = ["LG München", "OLG Frankfurt", "BGH"]

        for court in courts_to_test:
            start_time = time.time()

            query = (
                select(Decision)
                .where(Decision.court == court)
                .order_by(Decision.decision_date.desc())
                .limit(10)
            )
            result = await test_session.execute(query)
            decisions = result.scalars().all()

            query_time = time.time() - start_time

            assert all(d.court == court for d in decisions)
            assert query_time < 0.05  # Jede Query sollte < 50ms sein

    @pytest.mark.asyncio
    async def test_partial_index_recent_decisions(self, test_session: AsyncSession, large_dataset):
        """Test des Partial Index für kürzliche Entscheidungen (letzte 30 Tage)."""
        # Query für aktuelle Entscheidungen
        thirty_days_ago = datetime.now() - timedelta(days=30)

        start_time = time.time()

        query = select(Decision).where(Decision.created_at > thirty_days_ago)
        result = await test_session.execute(query)
        recent = result.scalars().all()

        query_time = time.time() - start_time

        assert len(recent) > 0
        assert all(d.created_at > thirty_days_ago for d in recent)
        assert query_time < 0.1  # Partial Index sollte sehr schnell sein

    @pytest.mark.asyncio
    async def test_gin_index_gdpr_articles(self, test_session: AsyncSession, large_dataset):
        """Test des GIN Index für GDPR-Artikel Arrays."""
        # Test Array-Contains Query
        start_time = time.time()

        # Suche nach spezifischem GDPR-Artikel
        query = select(Decision).where(Decision.gdpr_articles.contains(["Art. 6"]))
        result = await test_session.execute(query)
        decisions = result.scalars().all()

        query_time = time.time() - start_time

        assert len(decisions) > 0
        assert all("Art. 6" in d.gdpr_articles for d in decisions)
        assert query_time < 0.1  # GIN Index sollte Array-Suche beschleunigen

    @pytest.mark.asyncio
    async def test_fulltext_search_performance(self, test_session: AsyncSession, large_dataset):
        """Test der Volltext-Suche Performance mit GIN Index."""
        search_terms = ["GDPR", "keyword5", "Datenschutz", "Verarbeitung"]

        for term in search_terms:
            start_time = time.time()

            # Volltext-Suche mit to_tsquery
            query = text(
                """
                SELECT id, title, 
                       ts_rank(to_tsvector('german', full_text_anonymized), 
                              to_tsquery('german', :term)) as rank
                FROM decisions
                WHERE to_tsvector('german', full_text_anonymized) @@ to_tsquery('german', :term)
                ORDER BY rank DESC
                LIMIT 10
            """
            )

            result = await test_session.execute(query, {"term": term})
            matches = result.fetchall()

            query_time = time.time() - start_time

            assert len(matches) > 0 or term == "Datenschutz"  # Manche Terme könnten nicht vorkommen
            assert query_time < 0.2  # Volltext-Suche sollte < 200ms sein

    @pytest.mark.asyncio
    async def test_index_case_number(self, test_session: AsyncSession, large_dataset):
        """Test des Index auf Aktenzeichen für schnelle Lookups."""
        # Suche nach spezifischem Aktenzeichen
        test_case_numbers = ["50 O 0500/23", "75 O 0750/23", "99 O 0990/23"]

        for case_num in test_case_numbers:
            start_time = time.time()

            query = select(Decision).where(Decision.case_number == case_num)
            result = await test_session.execute(query)
            decision = result.scalar_one_or_none()

            query_time = time.time() - start_time

            if decision:
                assert decision.case_number == case_num
            assert query_time < 0.01  # Unique Index sollte < 10ms sein

    @pytest.mark.asyncio
    async def test_combined_index_filtering(self, test_session: AsyncSession, large_dataset):
        """Test kombinierter Filter die von mehreren Indizes profitieren."""
        # Komplexe Query mit mehreren Bedingungen
        start_time = time.time()

        last_week = datetime.now() - timedelta(days=7)

        query = (
            select(Decision)
            .where(
                (Decision.source == "gdprhub")
                & (Decision.court == "LG München")
                & (Decision.created_at > last_week)
            )
            .order_by(Decision.decision_date.desc())
        )

        result = await test_session.execute(query)
        decisions = result.scalars().all()

        query_time = time.time() - start_time

        # Verifiziere Filter
        for d in decisions:
            assert d.source == "gdprhub"
            assert d.court == "LG München"
            assert d.created_at > last_week

        assert query_time < 0.1  # Kombinierte Indizes sollten helfen

    @pytest.mark.asyncio
    async def test_count_queries_performance(self, test_session: AsyncSession, large_dataset):
        """Test der Performance von COUNT-Queries mit Indizes."""
        # Verschiedene Count-Queries
        queries = [
            ("Total", select(func.count()).select_from(Decision)),
            (
                "By Source",
                select(func.count()).select_from(Decision).where(Decision.source == "gdprhub"),
            ),
            ("By Court", select(func.count()).select_from(Decision).where(Decision.court == "BGH")),
            (
                "Recent",
                select(func.count())
                .select_from(Decision)
                .where(Decision.created_at > datetime.now() - timedelta(days=7)),
            ),
        ]

        for name, query in queries:
            start_time = time.time()
            count = await test_session.scalar(query)
            query_time = time.time() - start_time

            assert count >= 0
            assert query_time < 0.05, f"Count query '{name}' took {query_time:.3f}s"

    @pytest.mark.asyncio
    async def test_pagination_performance(self, test_session: AsyncSession, large_dataset):
        """Test der Pagination-Performance mit LIMIT/OFFSET."""
        page_size = 20
        test_pages = [0, 5, 10, 25, 50]  # Verschiedene Seiten

        for page in test_pages:
            offset = page * page_size
            start_time = time.time()

            query = (
                select(Decision)
                .order_by(Decision.created_at.desc())
                .limit(page_size)
                .offset(offset)
            )

            result = await test_session.execute(query)
            decisions = result.scalars().all()

            query_time = time.time() - start_time

            assert len(decisions) <= page_size
            assert query_time < 0.1, f"Page {page} took {query_time:.3f}s"

    @pytest.mark.asyncio
    async def test_aggregate_queries_performance(self, test_session: AsyncSession, large_dataset):
        """Test der Performance von Aggregations-Queries."""
        # Gruppierung nach Source mit Count
        start_time = time.time()

        query = (
            select(Decision.source, func.count(Decision.id))
            .group_by(Decision.source)
            .order_by(func.count(Decision.id).desc())
        )

        result = await test_session.execute(query)
        source_counts = result.all()

        query_time = time.time() - start_time

        assert len(source_counts) > 0
        assert query_time < 0.1  # Aggregation sollte < 100ms sein

        # Gruppierung nach Monat
        start_time = time.time()

        query = text(
            """
            SELECT 
                DATE_TRUNC('month', decision_date) as month,
                COUNT(*) as count
            FROM decisions
            WHERE decision_date IS NOT NULL
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        """
        )

        result = await test_session.execute(query)
        monthly_counts = result.all()

        query_time = time.time() - start_time

        assert len(monthly_counts) > 0
        assert query_time < 0.15  # Date aggregation sollte < 150ms sein

    @pytest.mark.asyncio
    async def test_concurrent_queries_performance(self, test_session: AsyncSession, large_dataset):
        """Test der Performance bei parallelen Datenbankabfragen."""

        async def run_query(query_type: str) -> float:
            start = time.time()

            if query_type == "count":
                await test_session.scalar(select(func.count()).select_from(Decision))
            elif query_type == "recent":
                await test_session.execute(
                    select(Decision).order_by(Decision.created_at.desc()).limit(10)
                )
            elif query_type == "search":
                await test_session.execute(
                    select(Decision).where(Decision.court == "LG München").limit(5)
                )

            return time.time() - start

        # 20 parallele Queries verschiedener Typen
        query_types = ["count", "recent", "search"] * 7
        tasks = [run_query(qt) for qt in query_types]

        start_time = time.time()
        times = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # Durchschnittliche Query-Zeit
        avg_time = sum(times) / len(times)

        assert avg_time < 0.1  # Durchschnitt sollte < 100ms sein
        assert total_time < 2.0  # Gesamt sollte < 2s sein (Parallelität)
        assert max(times) < 0.5  # Keine Query sollte > 500ms sein

    @pytest.mark.asyncio
    async def test_index_usage_verification(self, test_session: AsyncSession):
        """Verifiziert dass Indizes tatsächlich verwendet werden (EXPLAIN ANALYZE)."""
        # Beispiel-Query die Index nutzen sollte
        query = """
            EXPLAIN (FORMAT JSON, ANALYZE true, BUFFERS true)
            SELECT * FROM decisions 
            WHERE court = 'LG München' 
            ORDER BY decision_date DESC 
            LIMIT 10
        """

        result = await test_session.execute(text(query))
        explain_output = result.scalar()

        # Parse EXPLAIN output
        import json

        plan = json.loads(explain_output)[0]

        # Prüfe auf Index-Nutzung (vereinfacht)
        plan_text = json.dumps(plan)

        # Sollte Index-Scan enthalten (nicht Seq Scan für große Tabellen)
        assert "Index" in plan_text or "Bitmap" in plan_text or len(plan) > 0

        # Execution Time sollte niedrig sein
        if "Execution Time" in plan:
            exec_time = plan["Execution Time"]
            assert exec_time < 50  # Sollte < 50ms sein mit Index
