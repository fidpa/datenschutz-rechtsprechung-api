#!/usr/bin/env python3
"""
Demo Script für Claude Code Logging System Integration.

Demonstrates:
- Core Logger Usage
- Middleware Integration  
- Performance Monitoring
- Error Tracking
- Business Event Logging
"""

import asyncio
import time
import random
from pathlib import Path
import sys

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.logging.core.logger import get_logger, performance_monitor
from src.logging.core.config import get_development_config, set_config
from src.logging.core.events import (
    create_performance_event,
    create_error_event,
    create_business_event,
)
from src.logging.collectors.performance import PerformanceCollector


async def demo_basic_logging():
    """Demo basic logging functionality."""
    print("🔄 Demo: Basic Logging")

    logger = get_logger("demo_basic")

    # Basic log levels
    await logger.debug("Debug message for development")
    await logger.info("Application started successfully")
    await logger.warning("This is a warning message")

    # Simulate error
    try:
        raise ValueError("Demo error for testing")
    except Exception as e:
        await logger.error("An error occurred", error=e)

    print("✅ Basic logging completed")


async def demo_performance_monitoring():
    """Demo performance monitoring."""
    print("\n🔄 Demo: Performance Monitoring")

    logger = get_logger("demo_performance")

    # Manual performance logging
    start_time = time.perf_counter()
    await asyncio.sleep(0.1)  # Simulate work
    duration_ms = (time.perf_counter() - start_time) * 1000

    await logger.performance(
        operation="simulate_work", duration_ms=duration_ms, memory_mb=50.5, cpu_percent=25.0
    )

    # Using performance monitoring decorator
    @performance_monitor("slow_operation")
    async def slow_operation():
        """Simulate slow operation."""
        await asyncio.sleep(0.2)
        return "operation completed"

    result = await slow_operation()
    print(f"   Result: {result}")

    print("✅ Performance monitoring completed")


async def demo_business_events():
    """Demo business event tracking."""
    print("\n🔄 Demo: Business Event Tracking")

    logger = get_logger("demo_business")

    # User actions
    await logger.business_event(
        action="user_search", feature="search_interface", user_id="user_12345", impact="high"
    )

    await logger.business_event(
        action="export_data", feature="data_export", user_id="user_67890", impact="medium"
    )

    # Using helper function
    business_event = create_business_event(
        component="demo_business",
        feature="critical_feature",
        action="feature_used",
        user_id="user_99999",
    )

    # Simulate business event storage
    from src.logging.core.storage import create_storage_backend

    storage = create_storage_backend()
    await storage.store_event(business_event)

    print("✅ Business event tracking completed")


async def demo_error_tracking():
    """Demo comprehensive error tracking."""
    print("\n🔄 Demo: Error Tracking")

    logger = get_logger("demo_errors")

    # Simulate different types of errors
    errors_to_simulate = [
        ("ValueError", "Invalid input parameter"),
        ("ConnectionError", "Database connection failed"),
        ("TimeoutError", "Request timeout after 30 seconds"),
    ]

    for error_type, message in errors_to_simulate:
        try:
            if error_type == "ValueError":
                raise ValueError(message)
            elif error_type == "ConnectionError":
                raise ConnectionError(message)
            elif error_type == "TimeoutError":
                raise TimeoutError(message)
        except Exception as e:
            await logger.error(f"Simulated {error_type}", error=e)

    # Security event
    await logger.security_event(
        event_type="suspicious_login",
        description="Multiple failed login attempts",
        severity="medium",
        user_id="suspicious_user",
    )

    print("✅ Error tracking completed")


async def demo_context_management():
    """Demo context management features."""
    print("\n🔄 Demo: Context Management")

    logger = get_logger("demo_context")

    # Using operation context
    async with logger.operation_context("complex_operation", user_id="user_123"):
        await logger.info("Starting complex operation")
        await asyncio.sleep(0.15)  # Simulate work
        await logger.info("Operation step 1 completed")
        await asyncio.sleep(0.1)  # More work
        await logger.info("Operation completed successfully")

    print("✅ Context management completed")


async def demo_performance_collector():
    """Demo performance collector functionality."""
    print("\n🔄 Demo: Performance Collector")

    collector = PerformanceCollector("demo_collector")

    # Simulate various operations
    operations = [
        ("web_request", random.uniform(50, 500)),
        ("database_query", random.uniform(10, 200)),
        ("file_processing", random.uniform(100, 1000)),
        ("api_call", random.uniform(25, 300)),
    ]

    for operation, duration in operations:
        await collector.collect_performance_metric(
            component="demo_app",
            operation=operation,
            duration_ms=duration,
            memory_mb=random.uniform(10, 100),
            cpu_percent=random.uniform(5, 50),
        )

    # Get performance summary
    summary = await collector.get_performance_summary(hours=1)
    print(f"   Performance summary: {summary['count']} metrics collected")

    print("✅ Performance collector completed")


async def demo_claude_analysis_queue():
    """Demo Claude analysis queue functionality."""
    print("\n🔄 Demo: Claude Analysis Queue")

    from src.logging.core.storage import create_storage_backend

    storage = create_storage_backend()

    # Create high-priority events for Claude analysis
    high_priority_events = [
        create_error_event(
            component="critical_system",
            error_type="CriticalError",
            error_message="System failure detected",
        ),
        create_performance_event(
            component="user_interface",
            operation="page_load",
            duration_ms=5500,  # Very slow
            message="Extremely slow page load",
        ),
    ]

    # Store events
    await storage.store_events(high_priority_events)

    # Get Claude analysis queue
    claude_queue = await storage.get_claude_analysis_queue()
    print(f"   Events requiring Claude analysis: {len(claude_queue)}")

    for event in claude_queue[:3]:  # Show first 3
        print(f"   - {event.component}: {event.message} (score: {event.claude_priority_score})")

    print("✅ Claude analysis queue completed")


async def run_all_demos():
    """Run all demo functions."""
    print("🚀 Starting Claude Code Logging System Demo\n")

    # Set development configuration
    config = get_development_config()
    set_config(config)

    # Run all demos
    await demo_basic_logging()
    await demo_performance_monitoring()
    await demo_business_events()
    await demo_error_tracking()
    await demo_context_management()
    await demo_performance_collector()
    await demo_claude_analysis_queue()

    print(f"\n🎉 All demos completed successfully!")
    print(f"\n📁 Check logs directory: {config.storage_path}")
    print(f"📊 Run daily analysis: python scripts/claude_analysis/daily_analysis.py")


if __name__ == "__main__":
    asyncio.run(run_all_demos())
