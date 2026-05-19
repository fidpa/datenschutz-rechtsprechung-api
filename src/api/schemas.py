"""
Pydantic Schemas für die Datenschutz-Rechtsprechung API API.
Definiert Request/Response-Modelle für alle Endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, field_validator


# =============================================================================
# ENUMS
# =============================================================================


class DocumentTypeEnum(str, Enum):
    """Dokumenttypen."""

    COURT_DECISION = "court_decision"
    DPA_DECISION = "dpa_decision"
    GUIDANCE = "guidance"
    OPINION = "opinion"
    OTHER = "other"


class SourceTypeEnum(str, Enum):
    """Datenquellen."""

    GDPRHUB = "gdprhub"
    OPENLEGALDATA = "openlegaldata"
    RIS_AUSTRIA = "ris_austria"
    RIS_GERMANY = "ris_germany"
    MANUAL = "manual"


# =============================================================================
# DECISION SCHEMAS
# =============================================================================


class DecisionBase(BaseModel):
    """Basis-Schema für Decisions."""

    title: str = Field(..., description="Titel der Entscheidung")
    source: SourceTypeEnum = Field(..., description="Datenquelle")
    source_id: str = Field(..., description="ID in der Originalquelle")
    source_url: Optional[str] = Field(None, description="URL zur Originalquelle")
    document_type: DocumentTypeEnum = Field(
        default=DocumentTypeEnum.COURT_DECISION, description="Art des Dokuments"
    )
    case_number: Optional[str] = Field(None, description="Aktenzeichen")
    court: Optional[str] = Field(None, description="Gericht/Behörde")
    decision_date: Optional[datetime] = Field(None, description="Entscheidungsdatum")
    publication_date: Optional[datetime] = Field(None, description="Veröffentlichungsdatum")
    gdpr_articles: Optional[List[str]] = Field(
        default=[], description="Referenzierte DSGVO-Artikel"
    )
    bdsg_sections: Optional[List[str]] = Field(
        default=[], description="Referenzierte BDSG-Paragraphen"
    )
    keywords: Optional[List[str]] = Field(default=[], description="Schlagwörter")
    language: str = Field(default="de", description="Sprache des Dokuments")


class DecisionCreate(DecisionBase):
    """Schema für neue Decision (POST)."""

    full_text_original: Optional[str] = Field(None, description="Originaltext")
    leitsatz: Optional[str] = Field(None, description="Leitsatz")
    tenor: Optional[str] = Field(None, description="Tenor/Urteilsformel")
    tatbestand: Optional[str] = Field(None, description="Sachverhalt")
    entscheidungsgruende: Optional[str] = Field(None, description="Entscheidungsgründe")
    extra_metadata: Optional[Dict[str, Any]] = Field(None, description="Zusätzliche Metadaten")


class DecisionUpdate(BaseModel):
    """Schema für Decision-Updates (PATCH)."""

    title: Optional[str] = None
    case_number: Optional[str] = None
    court: Optional[str] = None
    decision_date: Optional[datetime] = None
    gdpr_articles: Optional[List[str]] = None
    keywords: Optional[List[str]] = None

    model_config = ConfigDict(extra="forbid")


class DecisionResponse(DecisionBase):
    """Schema für Decision-Response."""

    id: UUID = Field(..., description="Eindeutige ID")
    full_text_anonymized: Optional[str] = Field(None, description="Anonymisierter Volltext")
    leitsatz: Optional[str] = Field(None, description="Leitsatz")
    tenor: Optional[str] = Field(None, description="Tenor")
    tatbestand: Optional[str] = Field(None, description="Sachverhalt")
    entscheidungsgruende: Optional[str] = Field(None, description="Entscheidungsgründe")
    anonymization_applied: bool = Field(..., description="Wurde anonymisiert?")
    pdf_extracted: bool = Field(..., description="Wurde aus PDF extrahiert?")
    created_at: datetime = Field(..., description="Erstellungsdatum")
    updated_at: datetime = Field(..., description="Letzte Aktualisierung")
    last_crawled_at: Optional[datetime] = Field(None, description="Letzter Crawl")

    model_config = ConfigDict(from_attributes=True)


class DecisionListResponse(BaseModel):
    """Response für Decision-Listen mit Pagination."""

    items: List[DecisionResponse] = Field(..., description="Liste der Entscheidungen")
    total: int = Field(..., description="Gesamtanzahl der Ergebnisse")
    page: int = Field(..., description="Aktuelle Seite")
    page_size: int = Field(..., description="Elemente pro Seite")
    pages: int = Field(..., description="Gesamtanzahl der Seiten")
    has_next: bool = Field(..., description="Gibt es eine nächste Seite?")
    has_prev: bool = Field(..., description="Gibt es eine vorherige Seite?")


# =============================================================================
# SEARCH SCHEMAS
# =============================================================================


class SearchRequest(BaseModel):
    """Request für Volltext-Suche."""

    query: str = Field(..., min_length=3, description="Suchbegriff (min. 3 Zeichen)")
    sources: Optional[List[SourceTypeEnum]] = Field(None, description="Filter nach Datenquellen")
    courts: Optional[List[str]] = Field(None, description="Filter nach Gerichten")
    gdpr_articles: Optional[List[str]] = Field(None, description="Filter nach DSGVO-Artikeln")
    date_from: Optional[datetime] = Field(None, description="Entscheidungen ab diesem Datum")
    date_to: Optional[datetime] = Field(None, description="Entscheidungen bis zu diesem Datum")
    limit: int = Field(default=20, ge=1, le=100, description="Maximale Anzahl Ergebnisse")
    offset: int = Field(default=0, ge=0, description="Offset für Pagination")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validiert und bereinigt Suchanfrage."""
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Suchbegriff muss mindestens 3 Zeichen haben")
        return v


class SearchResult(BaseModel):
    """Einzelnes Suchergebnis."""

    id: UUID = Field(..., description="Decision ID")
    title: str = Field(..., description="Titel")
    court: Optional[str] = Field(None, description="Gericht")
    decision_date: Optional[datetime] = Field(None, description="Entscheidungsdatum")
    snippet: str = Field(..., description="Textausschnitt mit Treffer")
    relevance: float = Field(..., description="Relevanz-Score (0-1)")
    gdpr_articles: List[str] = Field(default=[], description="DSGVO-Artikel")
    source: str = Field(..., description="Datenquelle")
    source_url: Optional[str] = Field(None, description="Link zur Quelle")


class SearchResponse(BaseModel):
    """Response für Suchanfragen."""

    query: str = Field(..., description="Ursprüngliche Suchanfrage")
    results: List[SearchResult] = Field(..., description="Suchergebnisse")
    total: int = Field(..., description="Gesamtanzahl Treffer")
    took_ms: int = Field(..., description="Suchzeit in Millisekunden")
    facets: Optional[Dict[str, List[Dict[str, Any]]]] = Field(
        None, description="Facetten für Filter"
    )


# =============================================================================
# STATISTICS SCHEMAS
# =============================================================================


class StatsResponse(BaseModel):
    """Response für Statistik-Endpoint."""

    total_decisions: int = Field(..., description="Gesamtanzahl Entscheidungen")
    total_anonymized: int = Field(..., description="Anzahl anonymisierter Dokumente")
    total_with_gdpr: int = Field(..., description="Dokumente mit DSGVO-Referenz")

    by_source: Dict[str, int] = Field(..., description="Entscheidungen pro Quelle")
    by_court: Dict[str, int] = Field(..., description="Entscheidungen pro Gericht")
    by_year: Dict[int, int] = Field(..., description="Entscheidungen pro Jahr")

    top_gdpr_articles: List[Dict[str, Any]] = Field(..., description="Häufigste DSGVO-Artikel")
    top_keywords: List[Dict[str, Any]] = Field(..., description="Häufigste Schlagwörter")

    recent_decisions: List[Dict[str, Any]] = Field(..., description="Neueste Entscheidungen")

    last_updated: datetime = Field(..., description="Zeitpunkt der Statistik")


class CrawlStatusResponse(BaseModel):
    """Response für Crawl-Status."""

    source: str = Field(..., description="Datenquelle")
    status: str = Field(..., description="Status (running/completed/failed)")
    last_run: Optional[datetime] = Field(None, description="Letzter Durchlauf")
    next_run: Optional[datetime] = Field(None, description="Nächster geplanter Durchlauf")
    total_fetched: int = Field(..., description="Anzahl geholter Dokumente")
    total_processed: int = Field(..., description="Anzahl verarbeiteter Dokumente")
    total_errors: int = Field(..., description="Anzahl Fehler")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# ERROR SCHEMAS
# =============================================================================


class ErrorDetail(BaseModel):
    """Detail-Information für Fehler."""

    field: Optional[str] = Field(None, description="Betroffenes Feld")
    message: str = Field(..., description="Fehlermeldung")
    type: str = Field(..., description="Fehlertyp")


class ErrorResponse(BaseModel):
    """Standard Error Response."""

    error: str = Field(..., description="Fehlertyp")
    message: str = Field(..., description="Fehlermeldung")
    details: Optional[List[ErrorDetail]] = Field(None, description="Fehlerdetails")
    path: str = Field(..., description="Request-Pfad")
    timestamp: datetime = Field(default_factory=datetime.now, description="Zeitstempel")


# =============================================================================
# PAGINATION
# =============================================================================


class PaginationParams(BaseModel):
    """Pagination-Parameter."""

    page: int = Field(default=1, ge=1, description="Seitennummer")
    page_size: int = Field(default=20, ge=1, le=100, description="Elemente pro Seite")
    sort_by: Optional[str] = Field(None, description="Sortierfeld")
    sort_order: str = Field(
        default="desc", pattern="^(asc|desc)$", description="Sortierreihenfolge"
    )


# =============================================================================
# FILTER
# =============================================================================


class DecisionFilter(BaseModel):
    """Filter-Parameter für Decisions."""

    source: Optional[SourceTypeEnum] = None
    court: Optional[str] = None
    gdpr_article: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    has_anonymization: Optional[bool] = None
    has_pdf: Optional[bool] = None
    keyword: Optional[str] = None
