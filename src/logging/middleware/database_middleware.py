"""
Database Middleware für SQL Query Performance Monitoring.

Comprehensive tracking von Database queries mit performance analysis,
slow query detection und optimization suggestions.
"""

import time
import re
from typing import Dict, Any, Optional
from functools import wraps
import asyncio

try:
    from sqlalchemy.event import listens_for
    from sqlalchemy.pool import Pool

    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

from ..core.logger import get_logger
from ..core.events import EventPriority
from ..core.config import get_config


class DatabaseLoggingMiddleware:
    """
    Database Middleware für Enterprise Query Monitoring.

    Features:
    - SQL Query Performance Tracking
    - Slow Query Detection
    - Connection Pool Monitoring
    - Query Pattern Analysis
    - Optimization Recommendations
    - Database Error Tracking
    """

    def __init__(self, engine=None, component_name: str = "database"):
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError("SQLAlchemy not available. Install with: pip install sqlalchemy")

        self.component_name = component_name
        self.config = get_config()
        self.logger = get_logger(component_name)

        # Query performance thresholds
        self.slow_query_threshold_ms = 1000  # 1 second
        self.critical_query_threshold_ms = 5000  # 5 seconds

        # Query categories for business impact assessment
        self.query_patterns = {
            "search": [r"SELECT.*FROM.*decisions.*WHERE.*search", r"SELECT.*ts_rank", r"@@"],
            "crud_read": [r"^SELECT.*FROM.*(?:decisions|users)"],
            "crud_write": [r"^(?:INSERT|UPDATE|DELETE).*(?:decisions|users)"],
            "analytics": [r"SELECT.*COUNT\(", r"SELECT.*GROUP BY", r"SELECT.*DISTINCT"],
            "export": [r"SELECT.*LIMIT.*OFFSET", r"SELECT.*ORDER BY.*LIMIT"],
            "admin": [r"SELECT.*pg_", r"SELECT.*information_schema", r"ANALYZE", r"VACUUM"],
            "migration": [r"CREATE TABLE", r"ALTER TABLE", r"DROP TABLE", r"CREATE INDEX"],
        }

        # Business impact by query category
        self.category_impact = {
            "search": "high",  # User-facing search is critical
            "crud_read": "medium",  # Data access is important
            "crud_write": "high",  # Data modification is critical
            "analytics": "low",  # Analytics can be slower
            "export": "medium",  # User-facing but not critical
            "admin": "low",  # Admin queries are background
            "migration": "low",  # Migrations are planned
        }

        # Common slow query patterns
        self.slow_patterns = {
            "missing_index": [r"Seq Scan", r"Sequential Scan"],
            "cartesian_product": [r"Nested Loop.*Nested Loop"],
            "large_sort": [r"Sort.*rows=\d{4,}"],
            "full_table_scan": [r"Seq Scan.*rows=\d{4,}"],
        }

        self.engine = engine
        if engine:
            self._setup_sqlalchemy_events(engine)

    def _setup_sqlalchemy_events(self, engine) -> None:
        """Setup SQLAlchemy event listeners."""

        @listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.perf_counter()
            context._query_statement = statement
            context._query_parameters = parameters

        @listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            if hasattr(context, "_query_start_time"):
                duration = time.perf_counter() - context._query_start_time
                duration_ms = duration * 1000

                # Log query completion
                asyncio.create_task(
                    self._log_query_execution(
                        statement=statement,
                        parameters=parameters,
                        duration_ms=duration_ms,
                        connection_info=self._extract_connection_info(conn),
                    )
                )

        @listens_for(engine, "handle_error")
        def handle_error(exception_context):
            # Log database errors
            asyncio.create_task(self._log_database_error(exception_context))

        @listens_for(Pool, "connect")
        def pool_connect(dbapi_conn, connection_record):
            # Log new connections
            asyncio.create_task(self._log_connection_event("connected"))

        @listens_for(Pool, "checkout")
        def pool_checkout(dbapi_conn, connection_record, connection_proxy):
            # Log connection checkout from pool
            asyncio.create_task(self._log_connection_event("checkout"))

        @listens_for(Pool, "checkin")
        def pool_checkin(dbapi_conn, connection_record):
            # Log connection checkin to pool
            asyncio.create_task(self._log_connection_event("checkin"))

    def _categorize_query(self, statement: str) -> str:
        """Categorize SQL query for business impact assessment."""
        statement_clean = re.sub(r"\s+", " ", statement.strip().upper())

        for category, patterns in self.query_patterns.items():
            for pattern in patterns:
                if re.search(pattern, statement_clean, re.IGNORECASE):
                    return category

        return "unknown"

    def _extract_connection_info(self, conn) -> Dict[str, Any]:
        """Extract connection information."""
        info = {}

        try:
            if hasattr(conn, "info"):
                info.update(
                    {
                        "database_name": conn.info.get("database", "unknown"),
                        "user": conn.info.get("user", "unknown"),
                        "host": conn.info.get("host", "unknown"),
                        "port": conn.info.get("port", "unknown"),
                    }
                )
        except:
            pass

        return info

    def _sanitize_query(self, statement: str, parameters=None) -> str:
        """Sanitize query for logging (remove sensitive data)."""
        # Remove potential sensitive patterns
        sanitized = re.sub(r"'[^']*'", "'***'", statement)
        sanitized = re.sub(r"= \$\d+", "= $***", sanitized)

        # Limit length
        if len(sanitized) > 500:
            sanitized = sanitized[:500] + "..."

        return sanitized

    def _analyze_query_performance(self, statement: str, duration_ms: float) -> Dict[str, Any]:
        """Analyze query performance and provide insights."""
        analysis = {
            "is_slow": duration_ms > self.slow_query_threshold_ms,
            "is_critical": duration_ms > self.critical_query_threshold_ms,
            "performance_score": self._calculate_performance_score(duration_ms),
            "potential_issues": [],
        }

        # Check for common performance issues
        statement_upper = statement.upper()

        if "SELECT *" in statement_upper:
            analysis["potential_issues"].append("select_star")

        if re.search(r"WHERE.*LIKE.*%.*%", statement_upper):
            analysis["potential_issues"].append("like_both_wildcards")

        if re.search(r"ORDER BY.*LIMIT.*OFFSET.*\d{3,}", statement_upper):
            analysis["potential_issues"].append("large_offset")

        if "JOIN" in statement_upper and "WHERE" not in statement_upper:
            analysis["potential_issues"].append("join_without_where")

        return analysis

    def _calculate_performance_score(self, duration_ms: float) -> int:
        """Calculate performance score (0-100, higher is better)."""
        if duration_ms < 10:
            return 100
        elif duration_ms < 100:
            return 90
        elif duration_ms < 500:
            return 70
        elif duration_ms < 1000:
            return 50
        elif duration_ms < 2000:
            return 30
        elif duration_ms < 5000:
            return 15
        else:
            return 5

    async def _log_query_execution(
        self, statement: str, parameters, duration_ms: float, connection_info: Dict[str, Any]
    ) -> None:
        """Log query execution with performance analysis."""
        category = self._categorize_query(statement)
        business_impact = self.category_impact.get(category, "low")
        analysis = self._analyze_query_performance(statement, duration_ms)

        # Sanitize query for logging
        sanitized_query = self._sanitize_query(statement, parameters)

        context = {
            "query_category": category,
            "sanitized_query": sanitized_query,
            "parameter_count": len(parameters) if parameters else 0,
            "performance_analysis": analysis,
            **connection_info,
        }

        # Log slow queries with higher priority
        if analysis["is_critical"]:
            await self.logger.performance(
                operation=f"Critical SQL Query ({category})",
                duration_ms=duration_ms,
                user_impact=business_impact,
                context=context,
            )

            # Also log as error if extremely slow
            await self.logger.error(
                f"Extremely slow database query detected: {duration_ms:.2f}ms",
                user_impact="high",
                feature_affected=f"database_{category}",
                context=context,
            )

        elif analysis["is_slow"]:
            await self.logger.performance(
                operation=f"Slow SQL Query ({category})",
                duration_ms=duration_ms,
                user_impact=business_impact,
                context=context,
            )

        # Log business-critical queries regardless of performance
        elif business_impact == "high":
            await self.logger.business_event(
                action="database_query_executed",
                feature=f"database_{category}",
                impact=business_impact,
                duration_ms=duration_ms,
                context=context,
            )

    async def _log_database_error(self, exception_context) -> None:
        """Log database errors."""
        error = exception_context.original_exception
        statement = getattr(exception_context, "statement", "Unknown")

        # Categorize error
        error_type = type(error).__name__

        context = {
            "error_type": error_type,
            "sanitized_statement": self._sanitize_query(statement),
            "is_connection_error": "connection" in error_type.lower(),
            "is_syntax_error": "syntax" in str(error).lower(),
            "is_constraint_error": "constraint" in str(error).lower(),
        }

        # Assess business impact based on error type
        business_impact = "high"
        if context["is_syntax_error"]:
            business_impact = "medium"  # Development issue
        elif context["is_connection_error"]:
            business_impact = "critical"  # Infrastructure issue

        await self.logger.error(
            f"Database error: {error_type}",
            error=error,
            user_impact=business_impact,
            feature_affected="database_operations",
            context=context,
        )

    async def _log_connection_event(self, event_type: str) -> None:
        """Log connection pool events."""
        await self.logger.debug(
            f"Database connection {event_type}", context={"connection_event": event_type}
        )


def setup_database_logging(engine, component_name: str = "database") -> DatabaseLoggingMiddleware:
    """
    Setup database logging middleware.

    Usage:
        from src.logging.middleware import setup_database_logging

        engine = create_engine(database_url)
        setup_database_logging(engine)
    """
    if not SQLALCHEMY_AVAILABLE:
        raise ImportError("SQLAlchemy not available. Install with: pip install sqlalchemy")

    return DatabaseLoggingMiddleware(engine=engine, component_name=component_name)


def log_database_operation(
    operation_name: Optional[str] = None, impact: str = "medium", track_rows: bool = True
):
    """
    Decorator für database operation logging.

    Usage:
        @log_database_operation("critical_data_update", impact="high")
        def update_critical_data():
            # database operations
            return result
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            logger = get_logger("database_operation")

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Track row count if possible
                row_count = None
                if track_rows and result:
                    if hasattr(result, "rowcount"):
                        row_count = result.rowcount
                    elif isinstance(result, (list, tuple)):
                        row_count = len(result)

                # Log success
                context = {
                    "function": func.__name__,
                    "operation_name": operation_name or func.__name__,
                    "duration_ms": duration_ms,
                }
                if row_count is not None:
                    context["rows_affected"] = row_count

                await logger.business_event(
                    action="database_operation_completed",
                    feature=operation_name or func.__name__,
                    impact=impact,
                    context=context,
                )

                return result

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Log error
                context = {
                    "function": func.__name__,
                    "operation_name": operation_name or func.__name__,
                    "duration_ms": duration_ms,
                }

                await logger.error(
                    f"Database operation error in {func.__name__}: {str(e)}",
                    error=e,
                    feature_affected=operation_name or func.__name__,
                    user_impact=impact,
                    context=context,
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            logger = get_logger("database_operation")

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Track row count if possible
                row_count = None
                if track_rows and result:
                    if hasattr(result, "rowcount"):
                        row_count = result.rowcount
                    elif isinstance(result, (list, tuple)):
                        row_count = len(result)

                # Log success async
                context = {
                    "function": func.__name__,
                    "operation_name": operation_name or func.__name__,
                    "duration_ms": duration_ms,
                }
                if row_count is not None:
                    context["rows_affected"] = row_count

                asyncio.create_task(
                    logger.business_event(
                        action="database_operation_completed",
                        feature=operation_name or func.__name__,
                        impact=impact,
                        context=context,
                    )
                )

                return result

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Log error async
                context = {
                    "function": func.__name__,
                    "operation_name": operation_name or func.__name__,
                    "duration_ms": duration_ms,
                }

                asyncio.create_task(
                    logger.error(
                        f"Database operation error in {func.__name__}: {str(e)}",
                        error=e,
                        feature_affected=operation_name or func.__name__,
                        user_impact=impact,
                        context=context,
                    )
                )
                raise

        # Return appropriate wrapper based on function type
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Database monitoring utilities
class DatabaseMonitor:
    """Utility class für advanced database monitoring."""

    def __init__(self, component_name: str = "database_monitor"):
        self.logger = get_logger(component_name)

    async def log_connection_pool_status(
        self, pool_size: int, checked_out: int, overflow: int, **context
    ):
        """Log connection pool status."""
        utilization = (checked_out / pool_size) * 100 if pool_size > 0 else 0

        EventPriority.INFO
        if utilization > 90:
            EventPriority.CRITICAL
        elif utilization > 75:
            EventPriority.HIGH
        elif utilization > 50:
            EventPriority.MEDIUM

        await self.logger.info(
            f"Connection pool utilization: {utilization:.1f}%",
            context={
                "pool_size": pool_size,
                "checked_out": checked_out,
                "overflow": overflow,
                "utilization_percent": utilization,
                **context,
            },
        )

    async def log_query_plan_analysis(self, query: str, plan: str, execution_time_ms: float):
        """Log query execution plan analysis."""
        context = {
            "sanitized_query": self._sanitize_query(query),
            "execution_time_ms": execution_time_ms,
            "plan_summary": plan[:200] + "..." if len(plan) > 200 else plan,
        }

        await self.logger.performance(
            operation="Query Plan Analysis", duration_ms=execution_time_ms, context=context
        )

    def _sanitize_query(self, query: str) -> str:
        """Sanitize query for logging."""
        sanitized = re.sub(r"'[^']*'", "'***'", query)
        sanitized = re.sub(r"= \$\d+", "= $***", sanitized)
        return sanitized[:500] + "..." if len(sanitized) > 500 else sanitized
