"""
API Routes für Decision CRUD-Operationen.
Stellt Endpoints für Gerichtsentscheidungen bereit.
"""

from typing import List
from uuid import UUID
import math
import hashlib
import structlog

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Decision, AnonymizationMapping
from src.api import schemas
from src.api.deps import get_db, get_pagination_params, get_decision_filter
from src.processors.anonymizer import GermanLegalAnonymizer as Anonymizer

logger = structlog.get_logger()

router = APIRouter()


# =============================================================================
# GET /decisions - Liste mit Pagination und Filter
# =============================================================================


@router.get(
    "/",
    response_model=schemas.DecisionListResponse,
    summary="Liste aller Entscheidungen",
    description="""
    Gibt eine paginierte Liste aller Gerichtsentscheidungen zurück.
    
    **Features:**
    - Pagination mit konfigurierbarer Seitengröße
    - Filterung nach Quelle, Gericht, DSGVO-Artikeln, etc.
    - Sortierung nach verschiedenen Feldern
    - Nur anonymisierte Texte werden zurückgegeben
    """,
)
async def get_decisions(
    db: AsyncSession = Depends(get_db),
    pagination: schemas.PaginationParams = Depends(get_pagination_params),
    filters: schemas.DecisionFilter = Depends(get_decision_filter),
) -> schemas.DecisionListResponse:
    """Liste aller Entscheidungen mit Pagination und Filtern."""

    # Basis-Query
    query = select(Decision)
    count_query = select(func.count(Decision.id))

    # Filter anwenden
    conditions = []

    if filters.source:
        conditions.append(Decision.source == filters.source)

    if filters.court:
        conditions.append(Decision.court.ilike(f"%{filters.court}%"))

    if filters.gdpr_article:
        conditions.append(Decision.gdpr_articles.contains([filters.gdpr_article]))

    if filters.date_from:
        conditions.append(Decision.decision_date >= filters.date_from)

    if filters.date_to:
        conditions.append(Decision.decision_date <= filters.date_to)

    if filters.has_anonymization is not None:
        conditions.append(Decision.anonymization_applied == filters.has_anonymization)

    if filters.has_pdf is not None:
        conditions.append(Decision.pdf_extracted == filters.has_pdf)

    if filters.keyword:
        conditions.append(
            or_(
                Decision.title.ilike(f"%{filters.keyword}%"),
                Decision.keywords.contains([filters.keyword]),
            )
        )

    # Bedingungen zur Query hinzufügen
    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    # Sortierung
    if pagination.sort_by:
        order_col = getattr(Decision, pagination.sort_by)
        if pagination.sort_order == "desc":
            query = query.order_by(order_col.desc())
        else:
            query = query.order_by(order_col.asc())

    # Gesamtanzahl ermitteln
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Pagination
    offset = (pagination.page - 1) * pagination.page_size
    query = query.offset(offset).limit(pagination.page_size)

    # Daten abrufen
    result = await db.execute(query)
    decisions = result.scalars().all()

    # Berechne Seiten-Info
    pages = math.ceil(total / pagination.page_size) if total > 0 else 0
    has_next = pagination.page < pages
    has_prev = pagination.page > 1

    logger.info(
        "decisions_listed",
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        filters=filters.model_dump(exclude_none=True),
    )

    return schemas.DecisionListResponse(
        items=[schemas.DecisionResponse.model_validate(d) for d in decisions],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=pages,
        has_next=has_next,
        has_prev=has_prev,
    )


# =============================================================================
# GET /decisions/{id} - Einzelne Entscheidung
# =============================================================================


@router.get(
    "/{decision_id}",
    response_model=schemas.DecisionResponse,
    summary="Einzelne Entscheidung abrufen",
    description="Gibt eine spezifische Entscheidung anhand ihrer ID zurück.",
)
async def get_decision(
    decision_id: UUID, db: AsyncSession = Depends(get_db)
) -> schemas.DecisionResponse:
    """Einzelne Entscheidung anhand ID abrufen."""

    query = select(Decision).where(Decision.id == decision_id)
    result = await db.execute(query)
    decision = result.scalar_one_or_none()

    if not decision:
        logger.warning("decision_not_found", decision_id=str(decision_id))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entscheidung mit ID {decision_id} nicht gefunden",
        )

    logger.info("decision_retrieved", decision_id=str(decision_id))
    return schemas.DecisionResponse.model_validate(decision)


# =============================================================================
# GET /decisions/{id}/full - Volltext einer Entscheidung
# =============================================================================


@router.get(
    "/{decision_id}/full",
    summary="Volltext abrufen",
    description="Gibt den anonymisierten Volltext einer Entscheidung zurück.",
)
async def get_decision_fulltext(decision_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Volltext einer Entscheidung abrufen."""

    query = select(Decision).where(Decision.id == decision_id)
    result = await db.execute(query)
    decision = result.scalar_one_or_none()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entscheidung mit ID {decision_id} nicht gefunden",
        )

    # Strukturiere Volltext-Response
    fulltext_response = {
        "id": str(decision.id),
        "title": decision.title,
        "full_text": decision.full_text_anonymized or "Kein Text verfügbar",
        "sections": {
            "leitsatz": decision.leitsatz,
            "tenor": decision.tenor,
            "tatbestand": decision.tatbestand,
            "entscheidungsgruende": decision.entscheidungsgruende,
        },
        "anonymization_applied": decision.anonymization_applied,
        "language": decision.language,
    }

    logger.info("fulltext_retrieved", decision_id=str(decision_id))
    return fulltext_response


# =============================================================================
# GET /decisions/by-source/{source} - Nach Quelle filtern
# =============================================================================


@router.get(
    "/by-source/{source}",
    response_model=List[schemas.DecisionResponse],
    summary="Entscheidungen nach Quelle",
    description="Gibt alle Entscheidungen einer bestimmten Datenquelle zurück.",
)
async def get_decisions_by_source(
    source: schemas.SourceTypeEnum,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> List[schemas.DecisionResponse]:
    """Entscheidungen nach Datenquelle filtern."""

    query = (
        select(Decision)
        .where(Decision.source == source.value)
        .order_by(Decision.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    decisions = result.scalars().all()

    logger.info(
        "decisions_by_source", source=source.value, count=len(decisions), limit=limit, offset=offset
    )

    return [schemas.DecisionResponse.model_validate(d) for d in decisions]


# =============================================================================
# GET /decisions/by-court/{court} - Nach Gericht filtern
# =============================================================================


@router.get(
    "/by-court/{court}",
    response_model=List[schemas.DecisionResponse],
    summary="Entscheidungen nach Gericht",
    description="Gibt alle Entscheidungen eines bestimmten Gerichts zurück.",
)
async def get_decisions_by_court(
    court: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> List[schemas.DecisionResponse]:
    """Entscheidungen nach Gericht filtern."""

    query = (
        select(Decision)
        .where(Decision.court.ilike(f"%{court}%"))
        .order_by(Decision.decision_date.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    decisions = result.scalars().all()

    if not decisions:
        logger.info("no_decisions_for_court", court=court)
        return []

    logger.info("decisions_by_court", court=court, count=len(decisions), limit=limit, offset=offset)

    return [schemas.DecisionResponse.model_validate(d) for d in decisions]


# =============================================================================
# GET /decisions/by-gdpr/{article} - Nach DSGVO-Artikel
# =============================================================================


@router.get(
    "/by-gdpr/{article}",
    response_model=List[schemas.DecisionResponse],
    summary="Entscheidungen nach DSGVO-Artikel",
    description="Gibt alle Entscheidungen zu einem bestimmten DSGVO-Artikel zurück.",
)
async def get_decisions_by_gdpr_article(
    article: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> List[schemas.DecisionResponse]:
    """Entscheidungen nach DSGVO-Artikel filtern."""

    # Normalisiere Artikel-Format (z.B. "6" -> "Art. 6")
    if not article.startswith("Art"):
        article = f"Art. {article}"

    query = (
        select(Decision)
        .where(Decision.gdpr_articles.contains([article]))
        .order_by(Decision.decision_date.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    decisions = result.scalars().all()

    logger.info(
        "decisions_by_gdpr", article=article, count=len(decisions), limit=limit, offset=offset
    )

    return [schemas.DecisionResponse.model_validate(d) for d in decisions]


# =============================================================================
# POST /decisions - Neue Entscheidung (Optional, für manuelle Einträge)
# =============================================================================


@router.post(
    "/",
    response_model=schemas.DecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Neue Entscheidung erstellen",
    description="Erstellt eine neue Entscheidung (für manuelle Einträge).",
)
async def create_decision(
    decision_data: schemas.DecisionCreate, db: AsyncSession = Depends(get_db)
) -> schemas.DecisionResponse:
    """Neue Entscheidung erstellen."""

    # Prüfe ob Entscheidung bereits existiert
    existing_query = select(Decision).where(
        and_(Decision.source == decision_data.source, Decision.source_id == decision_data.source_id)
    )
    existing = await db.execute(existing_query)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Entscheidung mit source={decision_data.source} und source_id={decision_data.source_id} existiert bereits",
        )

    # Erstelle neue Entscheidung
    new_decision = Decision(**decision_data.model_dump())

    # Wenn Volltext vorhanden, anonymisiere ihn
    if decision_data.full_text_original:
        try:
            anonymizer = Anonymizer()
            result = anonymizer.anonymize(decision_data.full_text_original)
            new_decision.full_text_anonymized = result.anonymized_text
            new_decision.anonymization_applied = True

            # Speichere neue Decision zuerst für ID
            db.add(new_decision)
            await db.flush()

            # Speichere Anonymisierungs-Mappings
            for placeholder, original in result.mappings.items():
                mapping = AnonymizationMapping(
                    decision_id=new_decision.id,
                    placeholder=placeholder,
                    original_hash=hashlib.sha256(original.encode()).hexdigest(),
                    entity_type=result.entity_types.get(placeholder, "UNKNOWN"),
                )
                db.add(mapping)
        except Exception as e:
            logger.warning(f"Anonymisierung fehlgeschlagen: {e}")
            new_decision.full_text_anonymized = decision_data.full_text_original
            new_decision.anonymization_applied = False
            db.add(new_decision)
    else:
        db.add(new_decision)

    await db.commit()
    await db.refresh(new_decision)

    logger.info(
        "decision_created",
        decision_id=str(new_decision.id),
        source=new_decision.source,
        source_id=new_decision.source_id,
    )

    return schemas.DecisionResponse.model_validate(new_decision)


# =============================================================================
# DELETE /decisions/{id} - Entscheidung löschen (Admin-Funktion)
# =============================================================================


@router.delete(
    "/{decision_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Entscheidung löschen",
    description="Löscht eine Entscheidung (Admin-Funktion).",
)
async def delete_decision(decision_id: UUID, db: AsyncSession = Depends(get_db)):
    """Entscheidung löschen."""

    # Finde Entscheidung
    query = select(Decision).where(Decision.id == decision_id)
    result = await db.execute(query)
    decision = result.scalar_one_or_none()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entscheidung mit ID {decision_id} nicht gefunden",
        )

    # Lösche Entscheidung
    await db.delete(decision)
    await db.commit()

    logger.info("decision_deleted", decision_id=str(decision_id))
    return None
