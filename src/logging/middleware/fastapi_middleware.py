"""
FastAPI Middleware für High-Performance Async Logging.

Optimiert für FastAPI's async nature mit minimal overhead
und comprehensive performance monitoring.
"""

import time
import uuid
from typing import Callable, Optional, Dict, Any
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio

from ..core.logger import get_logger
from ..core.config import get_config


class FastAPILoggingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI Middleware für Enterprise Logging.

    Features:
    - High-Performance Async Logging
    - API Performance Monitoring
    - Error Tracking mit Stack Traces
    - Business Metrics für API Usage
    - Security Event Detection
    - Request/Response Size Monitoring
    """

    def __init__(
        self, app: FastAPI, component_name: str = "fastapi", exclude_paths: Optional[list] = None
    ):
        super().__init__(app)
        self.component_name = component_name
        self.config = get_config()
        self.logger = get_logger(component_name)

        # Paths to exclude from logging (health checks, metrics, etc.)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]

        # API endpoint categories
        self.api_categories = {
            "auth": ["/auth", "/login", "/token", "/signup"],
            "search": ["/search", "/query", "/find"],
            "export": ["/export", "/download"],
            "admin": ["/admin", "/system"],
            "crud": ["/decisions", "/users", "/data"],
        }

        # Performance thresholds by API category
        self.performance_thresholds = {
            "auth": 1000,  # Auth can be slower (crypto operations)
            "search": 500,  # Search should be fast
            "export": 5000,  # Export can be slower
            "admin": 2000,  # Admin operations
            "crud": 300,  # CRUD should be very fast
            "default": 500,  # Default for APIs
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Main middleware dispatch method."""
        # Skip excluded paths
        if any(exclude in request.url.path for exclude in self.exclude_paths):
            return await call_next(request)

        # Generate request ID
        request_id = str(uuid.uuid4())

        # Start performance tracking
        start_time = time.perf_counter()

        # Extract request context
        request_context = await self._extract_request_context(request)

        try:
            # Process request
            response = await call_next(request)

            # Calculate performance metrics
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log request completion
            await self._log_request_completion(
                request, response, duration_ms, request_id, request_context
            )

            return response

        except Exception as error:
            # Calculate error duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log error
            await self._log_request_error(request, error, duration_ms, request_id, request_context)

            # Re-raise error
            raise

    async def _extract_request_context(self, request: Request) -> Dict[str, Any]:
        """Extract comprehensive context from FastAPI request."""
        context = {
            "method": request.method,
            "path": request.url.path,
            "endpoint": str(request.url),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", ""),
            "content_type": request.headers.get("content-type", ""),
            "content_length": request.headers.get("content-length", 0),
        }

        # Add query parameters (filter sensitive data)
        if request.query_params:
            safe_params = {
                k: v
                for k, v in request.query_params.items()
                if k.lower() not in ["password", "token", "secret", "key", "api_key"]
            }
            context["query_params"] = safe_params

        # Add path parameters
        if hasattr(request, "path_params") and request.path_params:
            context["path_params"] = request.path_params

        # Try to extract user information
        user_id = await self._extract_user_id(request)
        if user_id:
            context["user_id"] = user_id

        return context

    async def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from various sources."""
        # Try custom header
        user_id = request.headers.get("X-User-ID")
        if user_id:
            return user_id

        # Try to extract from JWT token
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                # This would need actual JWT decoding implementation
                # For now, just return a placeholder
                token = auth_header[7:]
                return f"token_user_{hash(token) % 10000:04d}"
            except:
                pass

        # Try session or other auth methods
        # This would depend on your specific auth implementation

        return None

    def _categorize_api_endpoint(self, path: str) -> str:
        """Categorize API endpoint for performance thresholds."""
        path_lower = path.lower()

        for category, patterns in self.api_categories.items():
            if any(pattern in path_lower for pattern in patterns):
                return category

        return "default"

    def _assess_api_business_impact(self, status_code: int, path: str, duration_ms: float) -> str:
        """Assess business impact of API request."""
        # Critical errors have high impact
        if status_code >= 500:
            return "high"

        # Client errors have medium impact
        if status_code >= 400:
            return "medium"

        # Slow responses have impact based on endpoint
        category = self._categorize_api_endpoint(path)
        threshold = self.performance_thresholds.get(
            category, self.performance_thresholds["default"]
        )

        if duration_ms > threshold * 3:  # 3x threshold = high impact
            return "high"
        elif duration_ms > threshold * 2:  # 2x threshold = medium impact
            return "medium"

        # Auth endpoints always have medium+ impact
        if category == "auth":
            return "medium"

        # Search and export have medium impact when working
        if category in ["search", "export"] and status_code < 400:
            return "medium"

        return "low"

    async def _log_request_completion(
        self,
        request: Request,
        response: Response,
        duration_ms: float,
        request_id: str,
        context: Dict[str, Any],
    ) -> None:
        """Log successful request completion."""
        path = request.url.path
        status_code = response.status_code
        category = self._categorize_api_endpoint(path)
        threshold = self.performance_thresholds.get(
            category, self.performance_thresholds["default"]
        )

        # Assess business impact
        business_impact = self._assess_api_business_impact(status_code, path, duration_ms)

        # Add response context
        response_context = context.copy()
        response_context.update(
            {
                "status_code": status_code,
                "api_category": category,
                "performance_threshold": threshold,
                "response_headers": dict(response.headers) if hasattr(response, "headers") else {},
            }
        )

        # Performance logging für slow requests
        if duration_ms > threshold:
            await self.logger.performance(
                operation=f"API {request.method} {path}",
                duration_ms=duration_ms,
                request_id=request_id,
                user_id=context.get("user_id"),
                endpoint=path,
                method=request.method,
                status_code=status_code,
                user_impact=business_impact,
                context=response_context,
            )

        # Business event logging für wichtige APIs
        if business_impact in ["high", "medium"] or status_code >= 400:
            action = "api_request_completed"
            if status_code >= 500:
                action = "api_request_failed_server"
            elif status_code >= 400:
                action = "api_request_failed_client"

            await self.logger.business_event(
                action=action,
                feature=f"api_{category}",
                user_id=context.get("user_id"),
                impact=business_impact,
                request_id=request_id,
                duration_ms=duration_ms,
                status_code=status_code,
                context=response_context,
            )

        # Security monitoring
        await self._check_security_events(request, response, context, request_id)

    async def _log_request_error(
        self,
        request: Request,
        error: Exception,
        duration_ms: float,
        request_id: str,
        context: Dict[str, Any],
    ) -> None:
        """Log request errors."""
        path = request.url.path
        category = self._categorize_api_endpoint(path)

        # Determine error severity
        severity = "critical"
        if isinstance(error, ValueError):
            severity = "medium"
        elif isinstance(error, (KeyError, AttributeError)):
            severity = "low"

        error_context = context.copy()
        error_context.update(
            {
                "api_category": category,
                "error_type": type(error).__name__,
                "error_severity": severity,
            }
        )

        await self.logger.error(
            f"FastAPI request error: {str(error)}",
            error=error,
            request_id=request_id,
            user_id=context.get("user_id"),
            endpoint=path,
            method=request.method,
            duration_ms=duration_ms,
            user_impact="high",  # Errors always have high impact
            feature_affected=f"api_{category}",
            context=error_context,
        )

    async def _check_security_events(
        self, request: Request, response: Response, context: Dict[str, Any], request_id: str
    ) -> None:
        """Check for security-relevant events."""
        path = request.url.path.lower()
        status_code = response.status_code

        # Authentication failures
        if status_code in [401, 403]:
            await self.logger.security_event(
                event_type="authentication_failure",
                description=f"Auth failure on {request.method} {path}",
                severity="medium",
                user_id=context.get("user_id"),
                request_id=request_id,
                context=context,
            )

        # Rate limiting detection (429)
        if status_code == 429:
            await self.logger.security_event(
                event_type="rate_limit_exceeded",
                description=f"Rate limit on {request.method} {path}",
                severity="low",
                user_id=context.get("user_id"),
                request_id=request_id,
                context=context,
            )

        # Suspicious patterns in path
        suspicious_patterns = [
            ("sql_injection", ["union select", "drop table", "1=1", "or 1=1"]),
            ("xss_attempt", ["<script", "javascript:", "onerror="]),
            ("path_traversal", ["../", "..\\"]),
            ("command_injection", ["|", ";", "&&", "`"]),
        ]

        for attack_type, patterns in suspicious_patterns:
            if any(pattern in path for pattern in patterns):
                await self.logger.security_event(
                    event_type=attack_type,
                    description=f"Suspicious pattern detected in {request.method} {path}",
                    severity="high",
                    user_id=context.get("user_id"),
                    request_id=request_id,
                    context=context,
                )
                break


def setup_fastapi_logging(
    app: FastAPI, component_name: str = "fastapi", exclude_paths: Optional[list] = None
) -> FastAPILoggingMiddleware:
    """
    Setup FastAPI logging middleware.

    Usage:
        from src.logging.middleware import setup_fastapi_logging

        app = FastAPI()
        setup_fastapi_logging(app)
    """
    middleware = FastAPILoggingMiddleware(
        app=app, component_name=component_name, exclude_paths=exclude_paths
    )
    app.add_middleware(
        FastAPILoggingMiddleware, component_name=component_name, exclude_paths=exclude_paths
    )
    return middleware


# Dependency für route-spezifisches logging
async def get_route_logger(request: Request):
    """FastAPI dependency für route-specific logging."""
    return get_logger(f"fastapi_route_{request.url.path}")


# Decorator für einzelne API routes
def log_api_performance(
    feature_name: Optional[str] = None, impact: str = "medium", track_response_size: bool = False
):
    """
    Decorator für detailed API route logging.

    Usage:
        @app.get("/critical-api")
        @log_api_performance("critical_api", impact="high")
        async def critical_api():
            return {"data": "value"}
    """

    def decorator(func):
        from functools import wraps

        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            logger = get_logger("fastapi_route")

            # Extract request if available
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            try:
                result = func(*args, **kwargs)

                # Handle async functions
                if asyncio.iscoroutine(result):
                    result = await result

                duration_ms = (time.perf_counter() - start_time) * 1000

                # Calculate response size if requested
                response_size = None
                if track_response_size and result:
                    try:
                        import json

                        response_size = len(json.dumps(result, default=str))
                    except:
                        pass

                # Log success
                context = {"function": func.__name__}
                if response_size:
                    context["response_size_bytes"] = response_size
                if request:
                    context["request_path"] = request.url.path

                await logger.business_event(
                    action="api_route_executed",
                    feature=feature_name or func.__name__,
                    impact=impact,
                    duration_ms=duration_ms,
                    context=context,
                )

                return result

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Log error
                context = {"function": func.__name__}
                if request:
                    context["request_path"] = request.url.path

                await logger.error(
                    f"API route error in {func.__name__}: {str(e)}",
                    error=e,
                    duration_ms=duration_ms,
                    feature_affected=feature_name or func.__name__,
                    user_impact=impact,
                    context=context,
                )
                raise

        return wrapper

    return decorator
