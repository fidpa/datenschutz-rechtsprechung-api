"""
FastAPI Hauptanwendung der Datenschutz-Rechtsprechung API.
Stellt REST-API für Gerichtsentscheidungen bereit.
"""

from contextlib import asynccontextmanager
from typing import Dict, Any
import structlog

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text

from src._version import PROJECT_VERSION
from src.config import settings
from src.database import db_manager

logger = structlog.get_logger()

# Claude Code Logging Integration
from src.logging.middleware.fastapi_middleware import FastAPILoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle-Manager für FastAPI.
    Initialisiert Datenbank beim Start und schließt sie beim Shutdown.
    """
    # Startup
    logger.info("api_startup", environment=settings.environment)
    await db_manager.initialize()

    # Volltext-Index erstellen (falls noch nicht vorhanden)
    try:
        async with db_manager.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_decisions_search_vector 
                ON decisions USING gin(search_vector);
            """
                )
            )
            logger.info("fulltext_index_created")
    except Exception as e:
        logger.warning("fulltext_index_creation_failed", error=str(e))

    yield

    # Shutdown
    logger.info("api_shutdown")
    await db_manager.close()


# FastAPI App initialisieren
app = FastAPI(
    title="Datenschutz-Rechtsprechung API",
    description="""
    REST-API für Datenschutz-Rechtsprechung im DACH-Raum (DSGVO, BDSG, DSG/FADP).
    
    ## Features
    - 📊 Volltext-Suche in anonymisierten Entscheidungen
    - 🔍 Filterung nach DSGVO-Artikeln, Gerichten und Zeiträumen
    - 📈 Statistische Auswertungen
    - 🔄 Pagination und Sortierung
    - 🛡️ Anonymisierte Daten (DSGVO-konform)
    
    ## Datenquellen
    - GDPRhub Wiki
    - OpenLegalData (geplant)
    - RIS Österreich (geplant)
    """,
    version=PROJECT_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Claude Code Logging Middleware
app.add_middleware(FastAPILoggingMiddleware)


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handler für HTTP-Exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "status_code": exc.status_code,
                "path": str(request.url.path),
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handler für Validierungs-Fehler."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "message": "Validierungsfehler in der Anfrage",
                "details": exc.errors(),
                "path": str(request.url.path),
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handler für unerwartete Fehler."""
    logger.error("unhandled_exception", path=str(request.url.path), error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": "Ein interner Serverfehler ist aufgetreten",
                "status_code": 500,
                "path": str(request.url.path),
            }
        },
    )


# =============================================================================
# HEALTH CHECK & SYSTEM ENDPOINTS
# =============================================================================


@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """
    Health-Check Endpoint.
    Prüft Datenbank-Verbindung und System-Status.
    """
    health_status = {
        "status": "healthy",
        "environment": settings.environment,
        "database": "unknown",
        "version": "1.0.0",
    }

    # Datenbank-Check
    try:
        async with db_manager.engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            if result:
                health_status["database"] = "connected"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["database"] = f"error: {str(e)}"
        logger.error("health_check_db_failed", error=str(e))

    return health_status


@app.get("/", tags=["System"])
async def root():
    """Root-Endpoint mit API-Informationen."""
    return {
        "message": "Datenschutz-Rechtsprechung API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "api_v1": "/api/v1",
    }


# =============================================================================
# API ROUTERS REGISTRIEREN
# =============================================================================

# Routes importieren
from src.api.routes import decisions, search, stats, export, health, dashboard

# Router mit Prefix registrieren
app.include_router(decisions.router, prefix="/api/v1/decisions", tags=["Decisions"])

app.include_router(search.router, prefix="/api/v1/search", tags=["Search"])

app.include_router(stats.router, prefix="/api/v1/stats", tags=["Statistics"])

app.include_router(export.router, prefix="/api/v1/export", tags=["Export"])

app.include_router(health.router, prefix="/system", tags=["System Health"])

app.include_router(dashboard.router, prefix="/dashboard", tags=["Monitoring"])


# =============================================================================
# MIDDLEWARE
# =============================================================================


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware für Request-Logging."""
    # Request-ID generieren (falls nicht vorhanden)
    request_id = request.headers.get("X-Request-ID", None)

    # Log Request
    logger.info(
        "api_request", method=request.method, path=str(request.url.path), request_id=request_id
    )

    # Response verarbeiten
    response = await call_next(request)

    # Log Response
    logger.info(
        "api_response",
        method=request.method,
        path=str(request.url.path),
        status_code=response.status_code,
        request_id=request_id,
    )

    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
