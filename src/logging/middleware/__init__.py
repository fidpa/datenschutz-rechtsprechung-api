"""Middleware Integration Framework für automatisches Logging."""

from .flask_middleware import FlaskLoggingMiddleware


# Import other middleware only when needed
def _lazy_import():
    try:
        from .fastapi_middleware import FastAPILoggingMiddleware

        return FastAPILoggingMiddleware
    except ImportError:
        return None


def _lazy_import_celery():
    try:
        from .celery_middleware import CeleryLoggingMiddleware

        return CeleryLoggingMiddleware
    except ImportError:
        return None


def _lazy_import_database():
    try:
        from .database_middleware import DatabaseLoggingMiddleware

        return DatabaseLoggingMiddleware
    except ImportError:
        return None


# Make lazy imports available
FastAPILoggingMiddleware = _lazy_import()
CeleryLoggingMiddleware = _lazy_import_celery()
DatabaseLoggingMiddleware = _lazy_import_database()

__all__ = ["FlaskLoggingMiddleware"]

# Add to __all__ only if successfully imported
if FastAPILoggingMiddleware:
    __all__.append("FastAPILoggingMiddleware")
if CeleryLoggingMiddleware:
    __all__.append("CeleryLoggingMiddleware")
if DatabaseLoggingMiddleware:
    __all__.append("DatabaseLoggingMiddleware")
