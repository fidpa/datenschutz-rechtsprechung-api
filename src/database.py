"""
Datenbank-Models und Session-Management für den Datenschutz-Rechtsprechung API.
Verwendet SQLAlchemy 2.0 mit async Support.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum as PyEnum
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    Date,
    Float,
    JSON,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import (
    DeclarativeBase,
    relationship,
    Mapped,
    mapped_column,
    sessionmaker,
    Session,
)
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import UUID, ARRAY, TSVECTOR
import uuid

from src.config import settings


class Base(DeclarativeBase):
    """Basis-Klasse für alle Datenbank-Models."""


class SourceType(PyEnum):
    """Enumeration für Datenquellen."""

    GDPRHUB = "gdprhub"
    OPENLEGALDATA = "openlegaldata"
    RIS_AUSTRIA = "ris_austria"
    RIS_GERMANY = "ris_germany"
    MANUAL = "manual"


class DocumentType(PyEnum):
    """Enumeration für Dokumenttypen."""

    COURT_DECISION = "court_decision"
    DPA_DECISION = "dpa_decision"  # Datenschutzbehörde
    GUIDANCE = "guidance"
    OPINION = "opinion"
    OTHER = "other"


class Decision(Base):
    """Haupttabelle für Gerichtsentscheidungen und DSGVO-Dokumente."""

    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_source_source_id"),
        Index("ix_decisions_decision_date", "decision_date"),
        Index("ix_decisions_court", "court"),
        Index("ix_decisions_gdpr_articles", "gdpr_articles", postgresql_using="gin"),
        Index("ix_decisions_fulltext", "search_vector", postgresql_using="gin"),
    )

    # Primärschlüssel
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # Quelleninformationen
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Dokumenttyp
    document_type: Mapped[str] = mapped_column(
        String(50), default=DocumentType.COURT_DECISION.value
    )

    # Metadaten
    title: Mapped[str] = mapped_column(Text, nullable=False)
    case_number: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    court: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    decision_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    publication_date: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Rechtliche Referenzen
    gdpr_articles: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))
    bdsg_sections: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))
    keywords: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))

    # Volltext (Original und anonymisiert)
    full_text_original: Mapped[Optional[str]] = mapped_column(Text)
    full_text_anonymized: Mapped[Optional[str]] = mapped_column(Text)

    # Strukturierte Abschnitte (deutsches Rechtsformat)
    leitsatz: Mapped[Optional[str]] = mapped_column(Text)  # Leitsatz
    tenor: Mapped[Optional[str]] = mapped_column(Text)  # Tenor/Urteilsformel
    tatbestand: Mapped[Optional[str]] = mapped_column(Text)  # Sachverhalt
    entscheidungsgruende: Mapped[Optional[str]] = mapped_column(Text)  # Gründe

    # Volltext-Suchvektor (PostgreSQL spezifisch)
    search_vector: Mapped[Optional[Any]] = mapped_column(TSVECTOR)

    # Verarbeitungsstatus
    anonymization_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_errors: Mapped[Optional[Dict]] = mapped_column(JSON)

    # Zusätzliche Metadaten
    extra_metadata: Mapped[Optional[Dict]] = mapped_column(JSON, name="metadata")
    language: Mapped[str] = mapped_column(String(10), default="de")

    # Feedback & Qualität
    quality_score: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5 Sterne
    user_feedback: Mapped[Optional[str]] = mapped_column(Text)  # Kommentare
    feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_quality_score: Mapped[Optional[float]] = mapped_column(Float)

    # Rechtskraft-Status
    rechtskraft_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="rechtskräftig, berufung_möglich, berufung_eingelegt, aufgehoben, vergleich, unbekannt",
    )
    rechtskraft_datum: Mapped[Optional[date]] = mapped_column(Date)
    nachfolge_entscheidung_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decisions.id", ondelete="SET NULL"),
        comment="Verweis auf Berufungs-/Revisionsentscheidung",
    )

    # Zeitstempel
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Beziehungen
    anonymization_mappings: Mapped[List["AnonymizationMapping"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )
    crawl_logs: Mapped[List["CrawlLog"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Decision(id={self.id}, title='{self.title[:50]}...', source={self.source})>"

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert Model zu Dictionary für API-Responses."""
        return {
            "id": str(self.id),
            "source": self.source,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "document_type": self.document_type,
            "title": self.title,
            "case_number": self.case_number,
            "court": self.court,
            "decision_date": self.decision_date.isoformat() if self.decision_date else None,
            "publication_date": self.publication_date.isoformat()
            if self.publication_date
            else None,
            "gdpr_articles": self.gdpr_articles or [],
            "bdsg_sections": self.bdsg_sections or [],
            "keywords": self.keywords or [],
            "anonymization_applied": self.anonymization_applied,
            "language": self.language,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AnonymizationMapping(Base):
    """Speichert Anonymisierungs-Mappings für Rückverfolgbarkeit."""

    __tablename__ = "anonymization_mappings"
    __table_args__ = (Index("ix_anonymization_decision_id", "decision_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False
    )

    # Mapping: Platzhalter -> Originalwert (verschlüsselt gespeichert)
    placeholder: Mapped[str] = mapped_column(String(100), nullable=False)
    original_hash: Mapped[str] = mapped_column(String(256), nullable=False)  # SHA-256 Hash
    entity_type: Mapped[str] = mapped_column(String(50))  # PERSON, ORGANIZATION, etc.

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Beziehung
    decision: Mapped["Decision"] = relationship(back_populates="anonymization_mappings")

    def __repr__(self) -> str:
        return f"<AnonymizationMapping(placeholder={self.placeholder}, type={self.entity_type})>"


class CrawlLog(Base):
    """Protokolliert Crawl-Vorgänge für Monitoring und Debugging."""

    __tablename__ = "crawl_logs"
    __table_args__ = (
        Index("ix_crawl_logs_source", "source"),
        Index("ix_crawl_logs_started_at", "started_at"),
        Index("ix_crawl_logs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Crawl-Informationen
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    crawl_type: Mapped[str] = mapped_column(String(50), default="incremental")  # full, incremental
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Statistiken
    total_fetched: Mapped[int] = mapped_column(Integer, default=0)
    total_processed: Mapped[int] = mapped_column(Integer, default=0)
    total_errors: Mapped[int] = mapped_column(Integer, default=0)

    # Status und Fehler
    status: Mapped[str] = mapped_column(String(50), default="running")  # running, completed, failed
    error_details: Mapped[Optional[Dict]] = mapped_column(JSON)

    # Optional: Referenz zu spezifischer Entscheidung
    decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decisions.id", ondelete="SET NULL")
    )

    # Beziehung
    decision: Mapped[Optional["Decision"]] = relationship(back_populates="crawl_logs")

    def __repr__(self) -> str:
        return f"<CrawlLog(source={self.source}, status={self.status}, started={self.started_at})>"


class CrawlState(Base):
    """Speichert Crawl-Zustand für Resume-Funktionalität."""

    __tablename__ = "crawl_states"
    __table_args__ = (UniqueConstraint("source", name="uq_crawl_state_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    # Zustandsinformationen
    last_page: Mapped[Optional[int]] = mapped_column(Integer)
    last_offset: Mapped[Optional[int]] = mapped_column(Integer)
    last_cursor: Mapped[Optional[str]] = mapped_column(String(500))
    last_successful_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Zusätzlicher Zustand als JSON
    state_data: Mapped[Optional[Dict]] = mapped_column(JSON)

    # Zeitstempel
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CrawlState(source={self.source}, last_page={self.last_page})>"


# =============================================================================
# DATENBANK SESSION MANAGEMENT
# =============================================================================


class DatabaseManager:
    """Manager für Datenbank-Verbindungen und Sessions."""

    def __init__(self):
        self.engine = None
        self.async_session_maker = None
        self.sync_engine = None
        self.sync_session_maker = None

    async def initialize(self):
        """Initialisiert die Datenbank-Engine und Session-Factory."""
        self.engine = create_async_engine(
            settings.database_url,
            echo=settings.database_echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,  # Verbindungen vor Verwendung prüfen
        )

        self.async_session_maker = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

        # Synchrone Engine für Import-Operationen
        sync_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        self.sync_engine = create_engine(
            sync_url,
            echo=settings.database_echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
        )

        self.sync_session_maker = sessionmaker(
            self.sync_engine, class_=Session, expire_on_commit=False
        )

    async def create_all_tables(self):
        """Erstellt alle Tabellen (für Development/Testing)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all_tables(self):
        """Löscht alle Tabellen (VORSICHT: nur für Testing!)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @asynccontextmanager
    async def get_session(self) -> AsyncSession:
        """Gibt eine neue Datenbank-Session zurück."""
        if not self.async_session_maker:
            await self.initialize()

        async with self.async_session_maker() as session:
            yield session

    @contextmanager
    def get_sync_session(self) -> Session:
        """Gibt eine neue synchrone Datenbank-Session zurück."""
        if not self.sync_session_maker:
            # Synchrone Initialisierung
            sync_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
            self.sync_engine = create_engine(
                sync_url,
                echo=settings.database_echo,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,
            )

            self.sync_session_maker = sessionmaker(
                self.sync_engine, class_=Session, expire_on_commit=False
            )

        with self.sync_session_maker() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    async def close(self):
        """Schließt die Datenbank-Engine."""
        if self.engine:
            await self.engine.dispose()


# Globale Instanz
db_manager = DatabaseManager()


# Convenience-Funktion für async context manager
from contextlib import asynccontextmanager


@asynccontextmanager
async def get_async_session():
    """Gibt eine neue Datenbank-Session als async context manager zurück."""
    if not db_manager.async_session_maker:
        await db_manager.initialize()

    async with db_manager.async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# =============================================================================
# HILFSFUNKTIONEN FÜR VOLLTEXT-SUCHE
# =============================================================================


def create_search_vector_trigger():
    """
    SQL für Trigger zur automatischen Aktualisierung des search_vector.
    Muss nach Tabellenerstellung ausgeführt werden.
    """
    return """
    -- Funktion für Volltext-Vektor-Update
    CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
    BEGIN
        NEW.search_vector := 
            setweight(to_tsvector('german', COALESCE(NEW.title, '')), 'A') ||
            setweight(to_tsvector('german', COALESCE(NEW.leitsatz, '')), 'B') ||
            setweight(to_tsvector('german', COALESCE(NEW.full_text_anonymized, '')), 'C') ||
            setweight(to_tsvector('german', COALESCE(array_to_string(NEW.keywords, ' '), '')), 'B');
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    -- Trigger für automatisches Update
    DROP TRIGGER IF EXISTS update_search_vector_trigger ON decisions;
    CREATE TRIGGER update_search_vector_trigger
        BEFORE INSERT OR UPDATE ON decisions
        FOR EACH ROW
        EXECUTE FUNCTION update_search_vector();
    
    -- Index für Performance
    CREATE INDEX IF NOT EXISTS idx_decisions_search_vector 
        ON decisions USING gin(search_vector);
    """
