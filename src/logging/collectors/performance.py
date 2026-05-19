"""
Performance Data Collector für Response-Time, Memory, CPU Monitoring.

Comprehensive performance metrics collection mit intelligent
baseline detection und trend analysis.
"""

import asyncio
import time
import psutil
import threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from collections import deque, defaultdict
from dataclasses import dataclass
import statistics

from ..core.logger import get_logger
from ..core.events import EventPriority
from ..core.config import get_config


@dataclass
class PerformanceMetric:
    """Einzelne Performance-Metrik."""

    timestamp: datetime
    component: str
    operation: str
    duration_ms: float
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    context: Dict[str, Any] = None


class PerformanceBaseline:
    """Performance Baseline für intelligent threshold detection."""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.metrics: deque = deque(maxlen=window_size)
        self._lock = threading.Lock()

    def add_metric(self, duration_ms: float) -> None:
        """Add performance metric to baseline."""
        with self._lock:
            self.metrics.append(duration_ms)

    def get_baseline_stats(self) -> Dict[str, float]:
        """Get baseline statistics."""
        with self._lock:
            if len(self.metrics) < 10:  # Need minimum data
                return {"mean": 0, "median": 0, "p95": 0, "p99": 0, "std_dev": 0}

            sorted_metrics = sorted(self.metrics)
            return {
                "mean": statistics.mean(sorted_metrics),
                "median": statistics.median(sorted_metrics),
                "p95": sorted_metrics[int(len(sorted_metrics) * 0.95)],
                "p99": sorted_metrics[int(len(sorted_metrics) * 0.99)],
                "std_dev": statistics.stdev(sorted_metrics) if len(sorted_metrics) > 1 else 0,
            }

    def is_anomaly(self, duration_ms: float, sensitivity: float = 2.0) -> bool:
        """Check if metric is performance anomaly."""
        stats = self.get_baseline_stats()
        if stats["mean"] == 0:
            return False

        # Anomaly if more than sensitivity * std_dev above mean
        threshold = stats["mean"] + (sensitivity * stats["std_dev"])
        return duration_ms > threshold


class PerformanceCollector:
    """
    Performance Data Collector für Enterprise Monitoring.

    Features:
    - Response Time Monitoring
    - Memory Usage Tracking
    - CPU Utilization Monitoring
    - Automatic Baseline Detection
    - Performance Anomaly Detection
    - Trend Analysis
    """

    def __init__(self, component_name: str = "performance_collector"):
        self.component_name = component_name
        self.config = get_config()
        self.logger = get_logger(component_name)

        # Performance baselines per operation
        self.baselines: Dict[str, PerformanceBaseline] = defaultdict(lambda: PerformanceBaseline())

        # Recent metrics für trend analysis
        self.recent_metrics: deque = deque(maxlen=1000)
        self._metrics_lock = threading.Lock()

        # System monitoring
        self.process = psutil.Process()
        self.system_monitor_enabled = True
        self.system_monitor_task: Optional[asyncio.Task] = None

        # Performance thresholds
        self.default_thresholds = {
            "slow_ms": 1000,
            "critical_ms": 5000,
            "memory_high_mb": 500,
            "cpu_high_percent": 80,
        }

        # Start system monitoring
        if self.system_monitor_enabled:
            self.start_system_monitoring()

    def start_system_monitoring(self) -> None:
        """Start background system monitoring."""
        if self.system_monitor_task is None:
            self.system_monitor_task = asyncio.create_task(self._system_monitor_loop())

    async def stop_system_monitoring(self) -> None:
        """Stop background system monitoring."""
        if self.system_monitor_task:
            self.system_monitor_task.cancel()
            try:
                await self.system_monitor_task
            except asyncio.CancelledError:
                pass

    async def _system_monitor_loop(self) -> None:
        """Background loop für system monitoring."""
        while True:
            try:
                await self.collect_system_metrics()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self.logger.error(
                    "System monitoring error", error=e, context={"monitor": "system_metrics"}
                )
                await asyncio.sleep(60)

    async def collect_performance_metric(
        self,
        component: str,
        operation: str,
        duration_ms: float,
        memory_mb: Optional[float] = None,
        cpu_percent: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Collect single performance metric."""

        # Create metric object
        metric = PerformanceMetric(
            timestamp=datetime.utcnow(),
            component=component,
            operation=operation,
            duration_ms=duration_ms,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            context=context or {},
        )

        # Store metric
        with self._metrics_lock:
            self.recent_metrics.append(metric)

        # Update baseline
        operation_key = f"{component}:{operation}"
        self.baselines[operation_key].add_metric(duration_ms)

        # Analyze performance
        await self._analyze_performance_metric(metric, operation_key)

    async def _analyze_performance_metric(
        self, metric: PerformanceMetric, operation_key: str
    ) -> None:
        """Analyze performance metric for issues."""

        baseline = self.baselines[operation_key]
        baseline_stats = baseline.get_baseline_stats()

        # Check for performance issues
        issues = []
        priority = EventPriority.INFO

        # Duration analysis
        if metric.duration_ms > self.default_thresholds["critical_ms"]:
            issues.append("critical_duration")
            priority = EventPriority.CRITICAL
        elif metric.duration_ms > self.default_thresholds["slow_ms"]:
            issues.append("slow_duration")
            priority = EventPriority.MEDIUM
        elif baseline.is_anomaly(metric.duration_ms):
            issues.append("duration_anomaly")
            priority = EventPriority.MEDIUM

        # Memory analysis
        if metric.memory_mb and metric.memory_mb > self.default_thresholds["memory_high_mb"]:
            issues.append("high_memory")
            if priority == EventPriority.INFO:
                priority = EventPriority.MEDIUM

        # CPU analysis
        if metric.cpu_percent and metric.cpu_percent > self.default_thresholds["cpu_high_percent"]:
            issues.append("high_cpu")
            if priority == EventPriority.INFO:
                priority = EventPriority.MEDIUM

        # Log if there are issues or if it's a significant operation
        if issues or priority != EventPriority.INFO:
            context = metric.context.copy()
            context.update(
                {
                    "issues": issues,
                    "baseline_stats": baseline_stats,
                    "performance_score": self._calculate_performance_score(metric, baseline_stats),
                }
            )

            await self.logger.performance(
                operation=f"{metric.component}.{metric.operation}",
                duration_ms=metric.duration_ms,
                memory_mb=metric.memory_mb,
                cpu_percent=metric.cpu_percent,
                context=context,
            )

    def _calculate_performance_score(
        self, metric: PerformanceMetric, baseline_stats: Dict[str, float]
    ) -> int:
        """Calculate performance score (0-100, higher is better)."""
        score = 100

        # Duration impact
        if baseline_stats["mean"] > 0:
            duration_ratio = metric.duration_ms / baseline_stats["mean"]
            if duration_ratio > 3:
                score -= 40
            elif duration_ratio > 2:
                score -= 25
            elif duration_ratio > 1.5:
                score -= 15

        # Memory impact
        if metric.memory_mb:
            if metric.memory_mb > 1000:
                score -= 20
            elif metric.memory_mb > 500:
                score -= 10

        # CPU impact
        if metric.cpu_percent:
            if metric.cpu_percent > 90:
                score -= 20
            elif metric.cpu_percent > 70:
                score -= 10

        return max(score, 0)

    async def collect_system_metrics(self) -> None:
        """Collect system-wide performance metrics."""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()

            # Memory metrics
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024**3)

            # Disk metrics
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent
            disk_free_gb = disk.free / (1024**3)

            # Process-specific metrics
            try:
                process_memory = self.process.memory_info()
                process_memory_mb = process_memory.rss / (1024**2)
                process_cpu_percent = self.process.cpu_percent()
            except psutil.NoSuchProcess:
                process_memory_mb = 0
                process_cpu_percent = 0

            # Network metrics (if available)
            try:
                network = psutil.net_io_counters()
                network_sent_mb = network.bytes_sent / (1024**2)
                network_recv_mb = network.bytes_recv / (1024**2)
            except:
                network_sent_mb = 0
                network_recv_mb = 0

            context = {
                "system_cpu_percent": cpu_percent,
                "system_cpu_count": cpu_count,
                "system_memory_percent": memory_percent,
                "system_memory_available_gb": memory_available_gb,
                "system_disk_percent": disk_percent,
                "system_disk_free_gb": disk_free_gb,
                "process_memory_mb": process_memory_mb,
                "process_cpu_percent": process_cpu_percent,
                "network_sent_mb": network_sent_mb,
                "network_recv_mb": network_recv_mb,
            }

            # Determine if system metrics indicate issues
            issues = []
            priority = EventPriority.INFO

            if cpu_percent > 90:
                issues.append("critical_cpu")
                priority = EventPriority.CRITICAL
            elif cpu_percent > 80:
                issues.append("high_cpu")
                priority = EventPriority.MEDIUM

            if memory_percent > 95:
                issues.append("critical_memory")
                priority = EventPriority.CRITICAL
            elif memory_percent > 85:
                issues.append("high_memory")
                priority = EventPriority.MEDIUM

            if disk_percent > 95:
                issues.append("critical_disk")
                priority = EventPriority.CRITICAL
            elif disk_percent > 85:
                issues.append("high_disk")
                priority = EventPriority.MEDIUM

            if issues:
                context["issues"] = issues
                await self.logger.warning(
                    f"System resource issues detected: {', '.join(issues)}",
                    user_impact="medium" if priority == EventPriority.MEDIUM else "high",
                    context=context,
                )
            else:
                # Log normal metrics at debug level
                await self.logger.debug("System metrics collected", context=context)

        except Exception as e:
            await self.logger.error(
                "Failed to collect system metrics", error=e, context={"collector": "system_metrics"}
            )

    async def get_performance_summary(
        self, component: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        """Get performance summary for last N hours."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        with self._metrics_lock:
            relevant_metrics = [
                m
                for m in self.recent_metrics
                if m.timestamp >= cutoff_time and (component is None or m.component == component)
            ]

        if not relevant_metrics:
            return {"message": "No metrics available", "count": 0}

        # Calculate statistics
        durations = [m.duration_ms for m in relevant_metrics]
        memory_values = [m.memory_mb for m in relevant_metrics if m.memory_mb]
        cpu_values = [m.cpu_percent for m in relevant_metrics if m.cpu_percent]

        summary = {
            "count": len(relevant_metrics),
            "time_range_hours": hours,
            "duration_stats": {
                "mean": statistics.mean(durations),
                "median": statistics.median(durations),
                "min": min(durations),
                "max": max(durations),
                "p95": sorted(durations)[int(len(durations) * 0.95)],
                "p99": sorted(durations)[int(len(durations) * 0.99)],
            },
        }

        if memory_values:
            summary["memory_stats"] = {
                "mean": statistics.mean(memory_values),
                "max": max(memory_values),
            }

        if cpu_values:
            summary["cpu_stats"] = {"mean": statistics.mean(cpu_values), "max": max(cpu_values)}

        # Component breakdown
        component_stats = defaultdict(list)
        for metric in relevant_metrics:
            component_stats[metric.component].append(metric.duration_ms)

        summary["by_component"] = {
            comp: {"count": len(durations), "mean_duration": statistics.mean(durations)}
            for comp, durations in component_stats.items()
        }

        return summary

    async def get_slow_operations(self, hours: int = 24, limit: int = 10) -> List[Dict[str, Any]]:
        """Get slowest operations in the last N hours."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        with self._metrics_lock:
            relevant_metrics = [m for m in self.recent_metrics if m.timestamp >= cutoff_time]

        # Sort by duration (slowest first)
        sorted_metrics = sorted(relevant_metrics, key=lambda m: m.duration_ms, reverse=True)

        slow_ops = []
        for metric in sorted_metrics[:limit]:
            baseline_key = f"{metric.component}:{metric.operation}"
            baseline_stats = self.baselines[baseline_key].get_baseline_stats()

            slow_ops.append(
                {
                    "timestamp": metric.timestamp.isoformat(),
                    "component": metric.component,
                    "operation": metric.operation,
                    "duration_ms": metric.duration_ms,
                    "memory_mb": metric.memory_mb,
                    "cpu_percent": metric.cpu_percent,
                    "baseline_mean": baseline_stats["mean"],
                    "performance_score": self._calculate_performance_score(metric, baseline_stats),
                    "context": metric.context,
                }
            )

        return slow_ops


# Convenience functions
async def track_performance(component: str, operation: str, func: Callable, *args, **kwargs) -> Any:
    """Track performance of function execution."""
    collector = PerformanceCollector()
    start_time = time.perf_counter()

    try:
        # Get initial memory
        process = psutil.Process()
        initial_memory = process.memory_info().rss / (1024**2)

        # Execute function
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            result = func(*args, **kwargs)

        # Calculate metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        final_memory = process.memory_info().rss / (1024**2)
        memory_delta = final_memory - initial_memory
        cpu_percent = process.cpu_percent()

        # Collect metric
        await collector.collect_performance_metric(
            component=component,
            operation=operation,
            duration_ms=duration_ms,
            memory_mb=memory_delta,
            cpu_percent=cpu_percent,
            context={"function": func.__name__},
        )

        return result

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Still collect metric for failed operations
        await collector.collect_performance_metric(
            component=component,
            operation=f"failed_{operation}",
            duration_ms=duration_ms,
            context={"function": func.__name__, "error": str(e)},
        )

        raise


def performance_monitor(component: str, operation: Optional[str] = None):
    """Decorator für automatic performance monitoring."""

    def decorator(func):
        op_name = operation or func.__name__

        if asyncio.iscoroutinefunction(func):

            async def async_wrapper(*args, **kwargs):
                return await track_performance(component, op_name, func, *args, **kwargs)

            return async_wrapper
        else:

            def sync_wrapper(*args, **kwargs):
                return asyncio.run(track_performance(component, op_name, func, *args, **kwargs))

            return sync_wrapper

    return decorator
