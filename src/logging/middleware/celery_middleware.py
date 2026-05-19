"""
Celery Middleware für Background Task Monitoring.

Comprehensive tracking von Celery tasks mit performance monitoring,
error tracking und business impact assessment.
"""

import time
from typing import Dict, Any, Optional
from functools import wraps
import asyncio

try:
    from celery import Celery
    from celery.signals import (
        task_prerun,
        task_postrun,
        task_failure,
        task_retry,
        task_success,
        task_revoked,
        worker_ready,
        worker_shutdown,
    )

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

from ..core.logger import get_logger
from ..core.events import EventPriority
from ..core.config import get_config


class CeleryLoggingMiddleware:
    """
    Celery Middleware für Enterprise Task Monitoring.

    Features:
    - Task Performance Monitoring
    - Error Tracking mit Retry Logic
    - Business Impact Assessment
    - Worker Health Monitoring
    - Queue Monitoring
    - Task Chain/Group Tracking
    """

    def __init__(self, celery_app: Optional["Celery"] = None, component_name: str = "celery"):
        if not CELERY_AVAILABLE:
            raise ImportError("Celery not available. Install with: pip install celery")

        self.component_name = component_name
        self.config = get_config()
        self.logger = get_logger(component_name)
        self.celery_app = celery_app

        # Task categories für business impact assessment
        self.task_categories = {
            "crawler": ["crawl", "scrape", "fetch", "collect"],
            "processing": ["process", "parse", "extract", "analyze"],
            "export": ["export", "generate", "create_report"],
            "maintenance": ["cleanup", "backup", "optimize", "maintenance"],
            "notification": ["send_email", "notify", "alert"],
        }

        # Performance expectations by task category
        self.performance_expectations = {
            "crawler": {"max_duration_minutes": 30, "critical_duration_minutes": 60},
            "processing": {"max_duration_minutes": 10, "critical_duration_minutes": 30},
            "export": {"max_duration_minutes": 5, "critical_duration_minutes": 15},
            "maintenance": {"max_duration_minutes": 60, "critical_duration_minutes": 120},
            "notification": {"max_duration_minutes": 2, "critical_duration_minutes": 5},
            "default": {"max_duration_minutes": 15, "critical_duration_minutes": 45},
        }

        # Connect signals
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect to Celery signals for automatic monitoring."""
        task_prerun.connect(self._on_task_prerun)
        task_postrun.connect(self._on_task_postrun)
        task_failure.connect(self._on_task_failure)
        task_retry.connect(self._on_task_retry)
        task_success.connect(self._on_task_success)
        task_revoked.connect(self._on_task_revoked)
        worker_ready.connect(self._on_worker_ready)
        worker_shutdown.connect(self._on_worker_shutdown)

    def _categorize_task(self, task_name: str) -> str:
        """Categorize task for business impact assessment."""
        task_lower = task_name.lower()

        for category, keywords in self.task_categories.items():
            if any(keyword in task_lower for keyword in keywords):
                return category

        return "default"

    def _assess_task_business_impact(
        self, task_name: str, state: str, duration_minutes: Optional[float] = None
    ) -> str:
        """Assess business impact of task execution."""
        category = self._categorize_task(task_name)

        # Failed tasks have high impact
        if state in ["FAILURE", "REVOKED"]:
            if category in ["crawler", "processing"]:
                return "high"
            return "medium"

        # Performance impact assessment
        if duration_minutes and category in self.performance_expectations:
            expectations = self.performance_expectations[category]
            if duration_minutes > expectations["critical_duration_minutes"]:
                return "high"
            elif duration_minutes > expectations["max_duration_minutes"]:
                return "medium"

        # Category-based impact
        impact_map = {
            "crawler": "high",  # Data collection is critical
            "processing": "high",  # Data processing is critical
            "export": "medium",  # User-facing but not critical
            "maintenance": "low",  # Background maintenance
            "notification": "medium",  # User communication
        }

        return impact_map.get(category, "low")

    def _extract_task_context(
        self, task_id: str, task_name: str, args: tuple = (), kwargs: dict = None, **extra
    ) -> Dict[str, Any]:
        """Extract context from task execution."""
        context = {
            "task_id": task_id,
            "task_name": task_name,
            "task_category": self._categorize_task(task_name),
            "args_count": len(args) if args else 0,
            "kwargs_count": len(kwargs) if kwargs else 0,
        }

        # Add safe argument information (no sensitive data)
        if args:
            # Only add first few args for context, avoid logging sensitive data
            safe_args = []
            for i, arg in enumerate(args[:3]):  # Only first 3 args
                if isinstance(arg, (str, int, float, bool)):
                    if isinstance(arg, str) and len(arg) > 100:
                        safe_args.append(f"{arg[:100]}...")
                    else:
                        safe_args.append(arg)
                else:
                    safe_args.append(f"<{type(arg).__name__}>")
            context["sample_args"] = safe_args

        # Add safe kwargs keys (not values)
        if kwargs:
            context["kwargs_keys"] = list(kwargs.keys())

        # Add extra metadata
        for key, value in extra.items():
            if key not in ["args", "kwargs"]:  # Avoid duplicating large data
                context[key] = value

        return context

    def _on_task_prerun(self, sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
        """Called before task execution."""
        context = self._extract_task_context(task_id, task.name, args, kwargs, **kwds)

        # Log task start für important tasks
        category = self._categorize_task(task.name)
        if category in ["crawler", "processing", "export"]:
            asyncio.create_task(
                self.logger.business_event(
                    action="task_started",
                    feature=f"task_{category}",
                    impact=self._assess_task_business_impact(task.name, "STARTED"),
                    context=context,
                )
            )

    def _on_task_postrun(
        self,
        sender=None,
        task_id=None,
        task=None,
        args=None,
        kwargs=None,
        retval=None,
        state=None,
        **kwds,
    ):
        """Called after task execution."""
        # This is called for all task completions, we'll handle specifics in other handlers

    def _on_task_success(self, sender=None, result=None, **kwds):
        """Called when task succeeds."""
        task_name = sender.name if sender else "unknown"
        task_id = kwds.get("task_id", "unknown")

        # Calculate duration if we have runtime info
        runtime = kwds.get("runtime", 0)
        duration_minutes = runtime / 60 if runtime else None

        context = self._extract_task_context(task_id, task_name, **kwds)
        if duration_minutes:
            context["duration_minutes"] = duration_minutes

        business_impact = self._assess_task_business_impact(task_name, "SUCCESS", duration_minutes)

        # Performance logging für slow tasks
        category = self._categorize_task(task_name)
        expectations = self.performance_expectations.get(
            category, self.performance_expectations["default"]
        )

        if duration_minutes and duration_minutes > expectations["max_duration_minutes"]:
            asyncio.create_task(
                self.logger.performance(
                    operation=f"Celery Task {task_name}",
                    duration_ms=runtime * 1000 if runtime else 0,
                    context=context,
                )
            )

        # Business event logging
        if business_impact in ["high", "medium"]:
            asyncio.create_task(
                self.logger.business_event(
                    action="task_completed",
                    feature=f"task_{category}",
                    impact=business_impact,
                    context=context,
                )
            )

    def _on_task_failure(
        self, sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds
    ):
        """Called when task fails."""
        task_name = sender.name if sender else "unknown"

        context = self._extract_task_context(task_id, task_name, **kwds)
        context.update(
            {
                "exception_type": type(exception).__name__ if exception else "Unknown",
                "exception_message": str(exception) if exception else "Unknown error",
                "has_traceback": traceback is not None,
            }
        )

        business_impact = self._assess_task_business_impact(task_name, "FAILURE")

        # Log error
        asyncio.create_task(
            self.logger.error(
                f"Celery task failed: {task_name}",
                error=exception,
                user_impact=business_impact,
                feature_affected=f"task_{self._categorize_task(task_name)}",
                context=context,
            )
        )

    def _on_task_retry(self, sender=None, task_id=None, reason=None, einfo=None, **kwds):
        """Called when task is retried."""
        task_name = sender.name if sender else "unknown"

        context = self._extract_task_context(task_id, task_name, **kwds)
        context.update(
            {
                "retry_reason": str(reason) if reason else "Unknown",
                "retry_count": kwds.get("retries", 0),
            }
        )

        # Log retry event
        asyncio.create_task(self.logger.warning(f"Celery task retry: {task_name}", context=context))

    def _on_task_revoked(self, sender=None, terminated=None, signum=None, expired=None, **kwds):
        """Called when task is revoked."""
        task_id = kwds.get("task_id", "unknown")

        context = {
            "task_id": task_id,
            "terminated": terminated,
            "signum": signum,
            "expired": expired,
            "revoke_reason": "terminated" if terminated else "expired" if expired else "manual",
        }

        # Log task revocation
        asyncio.create_task(
            self.logger.warning(
                f"Celery task revoked: {task_id}", user_impact="medium", context=context
            )
        )

    def _on_worker_ready(self, sender=None, **kwds):
        """Called when worker starts."""
        context = {
            "worker_hostname": sender.hostname if sender else "unknown",
            "worker_pid": kwds.get("pid", "unknown"),
        }

        asyncio.create_task(self.logger.info("Celery worker ready", context=context))

    def _on_worker_shutdown(self, sender=None, **kwds):
        """Called when worker shuts down."""
        context = {
            "worker_hostname": sender.hostname if sender else "unknown",
            "worker_pid": kwds.get("pid", "unknown"),
        }

        asyncio.create_task(self.logger.warning("Celery worker shutdown", context=context))


def setup_celery_logging(
    celery_app: "Celery", component_name: str = "celery"
) -> CeleryLoggingMiddleware:
    """
    Setup Celery logging middleware.

    Usage:
        from src.logging.middleware import setup_celery_logging

        app = Celery('myapp')
        setup_celery_logging(app)
    """
    if not CELERY_AVAILABLE:
        raise ImportError("Celery not available. Install with: pip install celery")

    return CeleryLoggingMiddleware(celery_app=celery_app, component_name=component_name)


def log_task_performance(
    feature_name: Optional[str] = None, impact: str = "medium", track_result_size: bool = False
):
    """
    Decorator für detailed task logging.

    Usage:
        @celery_app.task
        @log_task_performance("critical_crawler", impact="high")
        def crawl_critical_data():
            return data
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            logger = get_logger("celery_task")
            task_name = getattr(func, "name", func.__name__)

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Calculate result size if requested
                result_size = None
                if track_result_size and result:
                    try:
                        import json

                        result_size = len(json.dumps(result, default=str))
                    except:
                        try:
                            result_size = len(str(result))
                        except:
                            pass

                # Log success
                context = {
                    "function": func.__name__,
                    "task_name": task_name,
                    "duration_ms": duration_ms,
                }
                if result_size:
                    context["result_size_bytes"] = result_size

                asyncio.create_task(
                    logger.business_event(
                        action="task_function_executed",
                        feature=feature_name or func.__name__,
                        impact=impact,
                        context=context,
                    )
                )

                return result

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Log error
                context = {
                    "function": func.__name__,
                    "task_name": task_name,
                    "duration_ms": duration_ms,
                }

                asyncio.create_task(
                    logger.error(
                        f"Task function error in {func.__name__}: {str(e)}",
                        error=e,
                        feature_affected=feature_name or func.__name__,
                        user_impact=impact,
                        context=context,
                    )
                )
                raise

        return wrapper

    return decorator


# Bare-decorator alias: `@claude_task_monitor` == `@log_task_performance()`
# (used directly on Celery tasks in src/tasks/crawler_tasks.py).
claude_task_monitor = log_task_performance()


# Task monitoring utilities
class TaskMonitor:
    """Utility class für advanced task monitoring."""

    def __init__(self, component_name: str = "celery_monitor"):
        self.logger = get_logger(component_name)

    async def log_queue_status(self, queue_name: str, queue_length: int, **context):
        """Log queue status information."""
        EventPriority.INFO
        if queue_length > 1000:
            EventPriority.HIGH
        elif queue_length > 100:
            EventPriority.MEDIUM

        await self.logger.info(
            f"Queue status: {queue_name} has {queue_length} tasks",
            context={"queue_name": queue_name, "queue_length": queue_length, **context},
        )

    async def log_worker_status(self, worker_name: str, status: str, **context):
        """Log worker status changes."""
        await self.logger.info(
            f"Worker status: {worker_name} is {status}",
            context={"worker_name": worker_name, "worker_status": status, **context},
        )
