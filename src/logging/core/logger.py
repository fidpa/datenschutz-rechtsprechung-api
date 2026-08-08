"""
Enterprise Logger für Claude Code Logging System.

Zentraler Logger mit intelligent routing, performance monitoring
und automatischer Claude-Analysis-Integration.
"""

import asyncio
import time
import psutil
import socket
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
from functools import wraps

from ..._version import PROJECT_VERSION
from .events import LogEvent, EventClassifier, EventType, EventCategory, EventPriority
from .config import LoggingConfig, get_config
from .storage import StorageBackend, create_storage_backend


class PerformanceTracker:
    """Performance tracking für method calls und operations."""

    def __init__(self):
        self.start_time: Optional[float] = None
        self.start_memory: Optional[float] = None
        self.process = psutil.Process()

    def start(self) -> None:
        """Start performance tracking."""
        self.start_time = time.perf_counter()
        try:
            memory_info = self.process.memory_info()
            self.start_memory = memory_info.rss / 1024 / 1024  # MB
        except:
            self.start_memory = None

    def finish(self) -> Dict[str, float]:
        """Finish tracking and return metrics."""
        end_time = time.perf_counter()
        duration_ms = (end_time - (self.start_time or end_time)) * 1000

        memory_mb = None
        cpu_percent = None

        try:
            memory_info = self.process.memory_info()
            current_memory = memory_info.rss / 1024 / 1024  # MB

            if self.start_memory:
                memory_mb = current_memory - self.start_memory
            else:
                memory_mb = current_memory

            cpu_percent = self.process.cpu_percent()

        except:
            pass

        return {"duration_ms": duration_ms, "memory_mb": memory_mb, "cpu_percent": cpu_percent}


class EnterpriseLogger:
    """
    Enterprise-Level Logger für Claude Code Integration.

    Features:
    - Intelligent Event Classification
    - Performance Monitoring
    - Automatic Claude Analysis Queue
    - Context-Rich Logging
    - Async Processing
    - Business Impact Assessment
    """

    def __init__(
        self,
        component: str,
        config: Optional[LoggingConfig] = None,
        storage: Optional[StorageBackend] = None,
    ):
        self.component = component
        self.config = config or get_config()
        self.storage = storage or create_storage_backend(self.config)

        # Performance tracking
        self.hostname = socket.gethostname()
        self.version = PROJECT_VERSION

        # Event buffer für async processing
        self._event_buffer: List[LogEvent] = []
        self._buffer_lock = asyncio.Lock()
        self._background_task: Optional[asyncio.Task] = None

        # Context stack für nested operations
        self._context_stack: List[Dict[str, Any]] = []

        # Start background processing if enabled
        if self.config.async_processing:
            self._start_background_processing()

    def _start_background_processing(self) -> None:
        """Start background task für event processing."""
        if self._background_task is None:
            try:
                # Try to create async task if event loop is running
                self._background_task = asyncio.create_task(self._process_events_background())
            except RuntimeError:
                # No event loop running (Flask context) - use thread-based processing
                import threading

                thread = threading.Thread(target=self._process_events_sync_loop, daemon=True)
                thread.start()
                self._background_task = thread

    async def _process_events_background(self) -> None:
        """Background task to process buffered events."""
        while True:
            try:
                if len(self._event_buffer) >= self.config.batch_size:
                    await self._flush_buffer()

                await asyncio.sleep(1)  # Check every second

            except Exception as e:
                # Don't let background processing crash
                print(f"Warning: Background event processing error: {e}")
                await asyncio.sleep(5)

    async def _flush_buffer(self) -> None:
        """Flush event buffer to storage."""
        async with self._buffer_lock:
            if not self._event_buffer:
                return

            events_to_store = self._event_buffer.copy()
            self._event_buffer.clear()

        try:
            await self.storage.store_events(events_to_store)
        except Exception as e:
            print(f"Warning: Failed to store events: {e}")

    def _process_events_sync_loop(self) -> None:
        """Synchronous background thread für event processing in Flask context."""
        import time

        while True:
            try:
                if len(self._event_buffer) >= self.config.batch_size:
                    self._flush_buffer_sync()

                time.sleep(1)  # Check every second

            except Exception as e:
                # Don't let background processing crash
                print(f"Warning: Background event processing error: {e}")
                time.sleep(5)

    def _flush_buffer_sync(self) -> None:
        """Synchronous version of buffer flush für Flask context."""
        if not self._event_buffer:
            return

        events_to_store = self._event_buffer.copy()
        self._event_buffer.clear()

        try:
            # Use sync storage method
            import asyncio

            asyncio.run(self.storage.store_events(events_to_store))
        except Exception as e:
            print(f"Warning: Failed to store events: {e}")
            # Re-add events to buffer for retry
            self._event_buffer.extend(events_to_store)

    def _create_base_event(
        self,
        message: str,
        event_type: EventType = EventType.SYSTEM_METRIC,
        category: EventCategory = EventCategory.SYSTEM,
        **kwargs,
    ) -> LogEvent:
        """Create base event with standard fields."""
        # Merge context from stack
        context = {}
        for ctx in self._context_stack:
            context.update(ctx)
        context.update(kwargs.get("context", {}))

        # Remove context from kwargs to avoid duplicate parameter
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "context"}

        event = LogEvent(
            message=message,
            component=self.component,
            event_type=event_type,
            category=category,
            context=context,
            environment=self.config.environment,
            version=self.version,
            host=self.hostname,
            **filtered_kwargs,
        )

        # Classify event automatically
        return EventClassifier.classify_event(event)

    async def _log_event(self, event: LogEvent) -> None:
        """Log event to storage."""
        if self.config.async_processing:
            # Add to buffer for background processing
            async with self._buffer_lock:
                self._event_buffer.append(event)

                # Immediate flush if buffer is full
                if len(self._event_buffer) >= self.config.buffer_size:
                    await self._flush_buffer()
        else:
            # Immediate storage
            await self.storage.store_event(event)

    # =============================================================================
    # STANDARD LOGGING METHODS
    # =============================================================================

    async def debug(self, message: str, **kwargs) -> None:
        """Debug level logging."""
        if self.config.log_level.value not in ["DEBUG"]:
            return

        event = self._create_base_event(
            message=message,
            event_type=EventType.SYSTEM_METRIC,
            category=EventCategory.SYSTEM,
            priority=EventPriority.INFO,
            **kwargs,
        )
        await self._log_event(event)

    async def info(self, message: str, **kwargs) -> None:
        """Info level logging."""
        if self.config.log_level.value not in ["DEBUG", "INFO"]:
            return

        event = self._create_base_event(
            message=message,
            event_type=EventType.SYSTEM_METRIC,
            category=EventCategory.SYSTEM,
            priority=EventPriority.INFO,
            **kwargs,
        )
        await self._log_event(event)

    async def warning(self, message: str, **kwargs) -> None:
        """Warning level logging."""
        event = self._create_base_event(
            message=message,
            event_type=EventType.SYSTEM_METRIC,
            category=EventCategory.SYSTEM,
            priority=EventPriority.MEDIUM,
            **kwargs,
        )
        await self._log_event(event)

    async def error(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """Error level logging."""
        error_data = {}
        if error:
            error_data.update(
                {
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "stack_trace": self._get_stack_trace(error),
                }
            )

        event = self._create_base_event(
            message=message,
            event_type=EventType.CRITICAL_ERROR,
            category=EventCategory.ERROR,
            priority=EventPriority.HIGH,
            **error_data,
            **kwargs,
        )
        await self._log_event(event)

    async def critical(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """Critical level logging."""
        error_data = {}
        if error:
            error_data.update(
                {
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "stack_trace": self._get_stack_trace(error),
                }
            )

        event = self._create_base_event(
            message=message,
            event_type=EventType.CRITICAL_ERROR,
            category=EventCategory.ERROR,
            priority=EventPriority.CRITICAL,
            requires_claude_analysis=True,
            **error_data,
            **kwargs,
        )
        await self._log_event(event)

    # =============================================================================
    # SPECIALIZED LOGGING METHODS
    # =============================================================================

    async def performance(
        self,
        operation: str,
        duration_ms: float,
        memory_mb: Optional[float] = None,
        cpu_percent: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Log performance metrics."""
        message = f"Performance: {operation} completed in {duration_ms:.2f}ms"

        # Assess performance impact
        priority = EventPriority.INFO
        if duration_ms > self.config.critical_response_time_ms:
            priority = EventPriority.CRITICAL
        elif duration_ms > self.config.slow_request_threshold_ms:
            priority = EventPriority.MEDIUM

        event = self._create_base_event(
            message=message,
            event_type=EventType.PERFORMANCE_DEGRADATION
            if priority != EventPriority.INFO
            else EventType.SYSTEM_METRIC,
            category=EventCategory.PERFORMANCE,
            priority=priority,
            operation=operation,
            duration_ms=duration_ms,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            **kwargs,
        )
        await self._log_event(event)

    async def business_event(
        self,
        action: str,
        feature: str,
        user_id: Optional[str] = None,
        impact: str = "medium",
        **kwargs,
    ) -> None:
        """Log business/user events."""
        message = f"Business Event: {action} on {feature}"

        if user_id and self.config.anonymize_user_data:
            user_id = f"user_{hash(user_id) % 10000:04d}"

        event = self._create_base_event(
            message=message,
            event_type=EventType.USER_ACTION,
            category=EventCategory.BUSINESS,
            priority=EventPriority.MEDIUM if impact == "high" else EventPriority.LOW,
            operation=action,
            feature_affected=feature,
            user_id=user_id,
            user_impact=impact,
            **kwargs,
        )
        await self._log_event(event)

    async def security_event(
        self,
        event_type: str,
        description: str,
        severity: str = "medium",
        user_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log security events."""
        message = f"Security Event: {event_type} - {description}"

        priority_map = {
            "low": EventPriority.LOW,
            "medium": EventPriority.MEDIUM,
            "high": EventPriority.HIGH,
            "critical": EventPriority.CRITICAL,
        }

        if user_id and self.config.anonymize_user_data:
            user_id = f"user_{hash(user_id) % 10000:04d}"

        event = self._create_base_event(
            message=message,
            event_type=EventType.SECURITY_INCIDENT,
            category=EventCategory.SECURITY,
            priority=priority_map.get(severity, EventPriority.MEDIUM),
            operation=event_type,
            user_id=user_id,
            requires_claude_analysis=True,
            **kwargs,
        )
        await self._log_event(event)

    # =============================================================================
    # CONTEXT MANAGEMENT
    # =============================================================================

    @asynccontextmanager
    async def operation_context(self, operation: str, **context_data):
        """Context manager für operations mit automatic performance tracking."""
        tracker = PerformanceTracker()

        # Add operation context to stack
        context = {"operation": operation, **context_data}
        self._context_stack.append(context)

        tracker.start()
        time.perf_counter()

        try:
            await self.info(f"Operation started: {operation}", **context_data)
            yield self

            # Success case
            metrics = tracker.finish()
            await self.performance(
                operation=operation,
                duration_ms=metrics["duration_ms"],
                memory_mb=metrics["memory_mb"],
                cpu_percent=metrics["cpu_percent"],
                **context_data,
            )

        except Exception as e:
            # Error case
            metrics = tracker.finish()
            await self.error(
                f"Operation failed: {operation}",
                error=e,
                duration_ms=metrics["duration_ms"],
                memory_mb=metrics["memory_mb"],
                cpu_percent=metrics["cpu_percent"],
                **context_data,
            )
            raise

        finally:
            # Remove context from stack
            if self._context_stack:
                self._context_stack.pop()

    def with_context(self, **context_data):
        """Decorator to add context to all log calls within function."""

        def decorator(func):
            if asyncio.iscoroutinefunction(func):

                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    self._context_stack.append(context_data)
                    try:
                        return await func(*args, **kwargs)
                    finally:
                        if self._context_stack:
                            self._context_stack.pop()

                return async_wrapper
            else:

                @wraps(func)
                def sync_wrapper(*args, **kwargs):
                    self._context_stack.append(context_data)
                    try:
                        return func(*args, **kwargs)
                    finally:
                        if self._context_stack:
                            self._context_stack.pop()

                return sync_wrapper

        return decorator

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def _get_stack_trace(self, error: Exception) -> Optional[str]:
        """Extract stack trace from exception."""
        import traceback

        try:
            return "".join(traceback.format_exception(type(error), error, error.__traceback__))
        except:
            return None

    async def get_claude_analysis_queue(self) -> List[LogEvent]:
        """Get events requiring Claude analysis."""
        return await self.storage.get_claude_analysis_queue()

    async def query_events(self, **filters) -> List[LogEvent]:
        """Query stored events."""
        return await self.storage.query_events(**filters)

    async def shutdown(self) -> None:
        """Graceful shutdown - flush buffers."""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

        await self._flush_buffer()


# =============================================================================
# CONVENIENCE FUNCTIONS & DECORATORS
# =============================================================================


def get_logger(component: str, config: Optional[LoggingConfig] = None) -> EnterpriseLogger:
    """Get logger instance for component."""
    return EnterpriseLogger(component=component, config=config)


def performance_monitor(operation_name: Optional[str] = None):
    """Decorator für automatic performance monitoring."""

    def decorator(func):
        func_name = operation_name or f"{func.__module__}.{func.__name__}"

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                logger = get_logger("performance_monitor")
                async with logger.operation_context(func_name):
                    return await func(*args, **kwargs)

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                logger = get_logger("performance_monitor")
                # For sync functions, we'll use a simpler approach
                tracker = PerformanceTracker()
                tracker.start()

                try:
                    result = func(*args, **kwargs)
                    metrics = tracker.finish()

                    # Log async in background
                    asyncio.create_task(
                        logger.performance(
                            operation=func_name,
                            duration_ms=metrics["duration_ms"],
                            memory_mb=metrics["memory_mb"],
                            cpu_percent=metrics["cpu_percent"],
                        )
                    )

                    return result

                except Exception as e:
                    metrics = tracker.finish()

                    # Log error async in background
                    asyncio.create_task(
                        logger.error(
                            f"Function failed: {func_name}",
                            error=e,
                            duration_ms=metrics["duration_ms"],
                            memory_mb=metrics["memory_mb"],
                            cpu_percent=metrics["cpu_percent"],
                        )
                    )
                    raise

            return sync_wrapper

    return decorator


# Global logger instance cache
_loggers: Dict[str, EnterpriseLogger] = {}


def get_cached_logger(component: str) -> EnterpriseLogger:
    """Get cached logger instance."""
    if component not in _loggers:
        _loggers[component] = get_logger(component)
    return _loggers[component]
