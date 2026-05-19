"""
Tests für Claude Code Logging System.

Basic tests für core functionality.
"""

import pytest
import asyncio
from datetime import datetime
from pathlib import Path
import tempfile
import shutil

from src.logging.core.logger import get_logger
from src.logging.core.events import (
    LogEvent,
    EventType,
    EventCategory,
    EventPriority,
    EventClassifier,
)
from src.logging.core.config import LoggingConfig, get_development_config
from src.logging.core.storage import JSONLStorage


class TestLogEvent:
    """Test LogEvent functionality."""

    def test_event_creation(self):
        """Test basic event creation."""
        event = LogEvent(
            message="Test message",
            component="test_component",
            event_type=EventType.SYSTEM_METRIC,
            category=EventCategory.SYSTEM,
        )

        assert event.message == "Test message"
        assert event.component == "test_component"
        assert event.event_type == EventType.SYSTEM_METRIC
        assert event.category == EventCategory.SYSTEM
        assert event.id is not None
        assert isinstance(event.timestamp, datetime)

    def test_event_to_dict(self):
        """Test event serialization."""
        event = LogEvent(message="Test message", component="test_component", duration_ms=100.5)

        data = event.to_dict()

        assert data["message"] == "Test message"
        assert data["component"] == "test_component"
        assert data["performance"]["duration_ms"] == 100.5
        assert "timestamp" in data
        assert "id" in data


class TestEventClassifier:
    """Test EventClassifier functionality."""

    def test_critical_keyword_detection(self):
        """Test critical keyword detection."""
        event = LogEvent(message="Critical error occurred", component="test_component")

        classified = EventClassifier.classify_event(event)

        assert classified.priority == EventPriority.CRITICAL
        assert classified.requires_claude_analysis == True
        assert "critical_pattern" in classified.analysis_tags

    def test_performance_classification(self):
        """Test performance-based classification."""
        event = LogEvent(
            message="Slow operation",
            component="test_component",
            duration_ms=6000,  # 6 seconds - critical
        )

        classified = EventClassifier.classify_event(event)

        assert classified.priority == EventPriority.CRITICAL
        assert classified.event_type == EventType.PERFORMANCE_DEGRADATION
        assert classified.category == EventCategory.PERFORMANCE

    def test_business_impact_assessment(self):
        """Test business impact assessment."""
        event = LogEvent(
            message="Payment processing slow",
            component="payment_service",
            endpoint="/payment/checkout",
        )

        classified = EventClassifier.classify_event(event)

        assert classified.user_impact == "high"  # Payment is high impact


class TestLoggingConfig:
    """Test LoggingConfig functionality."""

    def test_development_config(self):
        """Test development configuration."""
        config = get_development_config()

        assert config.environment == "development"
        assert config.debug_mode == True
        assert config.log_level.value == "DEBUG"
        assert config.is_development == True
        assert config.is_production == False

    def test_storage_path_creation(self):
        """Test storage path creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = LoggingConfig(storage_path=Path(temp_dir) / "test_logs")

            assert config.storage_path.exists()

    def test_performance_thresholds(self):
        """Test performance threshold configuration."""
        config = LoggingConfig()
        thresholds = config.get_performance_thresholds()

        assert "slow_request_ms" in thresholds
        assert "critical_response_ms" in thresholds
        assert thresholds["slow_request_ms"] > 0
        assert thresholds["critical_response_ms"] > thresholds["slow_request_ms"]


@pytest.mark.asyncio
class TestJSONLStorage:
    """Test JSONL storage functionality."""

    async def test_event_storage_and_retrieval(self):
        """Test storing and retrieving events."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = LoggingConfig(storage_path=Path(temp_dir))
            storage = JSONLStorage(config)

            # Create test event
            event = LogEvent(
                message="Test storage event",
                component="test_storage",
                event_type=EventType.SYSTEM_METRIC,
            )

            # Store event
            await storage.store_event(event)

            # Retrieve events
            events = await storage.query_events(component="test_storage")

            assert len(events) == 1
            assert events[0].message == "Test storage event"
            assert events[0].component == "test_storage"

    async def test_claude_analysis_queue(self):
        """Test Claude analysis queue functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = LoggingConfig(storage_path=Path(temp_dir))
            storage = JSONLStorage(config)

            # Create high-priority event
            event = LogEvent(
                message="Critical error for Claude analysis",
                component="critical_system",
                requires_claude_analysis=True,
                claude_priority_score=95,
            )

            await storage.store_event(event)

            # Get Claude analysis queue
            claude_events = await storage.get_claude_analysis_queue()

            assert len(claude_events) == 1
            assert claude_events[0].requires_claude_analysis == True
            assert claude_events[0].claude_priority_score == 95


@pytest.mark.asyncio
class TestEnterpriseLogger:
    """Test EnterpriseLogger functionality."""

    async def test_basic_logging(self):
        """Test basic logging methods."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = LoggingConfig(
                storage_path=Path(temp_dir), async_processing=False  # Synchronous for testing
            )

            logger = get_logger("test_logger")
            logger.config = config
            logger.storage = JSONLStorage(config)

            # Test different log levels
            await logger.info("Test info message")
            await logger.warning("Test warning message")
            await logger.error("Test error message")

            # Verify events were stored
            events = await logger.storage.query_events(component="test_logger")
            assert len(events) >= 2  # info, warning, error (depending on log level)

    async def test_performance_logging(self):
        """Test performance logging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = LoggingConfig(storage_path=Path(temp_dir), async_processing=False)

            logger = get_logger("performance_test")
            logger.config = config
            logger.storage = JSONLStorage(config)

            # Log performance metric
            await logger.performance(
                operation="test_operation",
                duration_ms=1500,  # Slow operation
                memory_mb=100,
                cpu_percent=50,
            )

            # Verify performance event
            events = await logger.storage.query_events(
                component="performance_test", category="performance"
            )

            assert len(events) == 1
            assert events[0].duration_ms == 1500
            assert events[0].memory_mb == 100

    async def test_business_event_logging(self):
        """Test business event logging."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = LoggingConfig(storage_path=Path(temp_dir), async_processing=False)

            logger = get_logger("business_test")
            logger.config = config
            logger.storage = JSONLStorage(config)

            # Log business event
            await logger.business_event(
                action="user_action",
                feature="critical_feature",
                user_id="test_user_123",
                impact="high",
            )

            # Verify business event
            events = await logger.storage.query_events(
                component="business_test", category="business"
            )

            assert len(events) == 1
            assert events[0].operation == "user_action"
            assert events[0].feature_affected == "critical_feature"
            assert events[0].user_impact == "high"


# Integration test
@pytest.mark.asyncio
async def test_end_to_end_logging_flow():
    """Test complete logging flow from event to analysis."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config = LoggingConfig(
            storage_path=Path(temp_dir), async_processing=False, claude_priority_threshold=50
        )

        logger = get_logger("e2e_test")
        logger.config = config
        logger.storage = JSONLStorage(config)

        # Create various events
        await logger.error("Critical system error", error=Exception("Test exception"))

        await logger.performance("slow_operation", 2500)  # Slow

        await logger.business_event("purchase", "checkout", user_id="user123", impact="high")

        # Get all events
        all_events = await logger.storage.query_events(component="e2e_test")
        assert len(all_events) >= 3

        # Get Claude analysis queue
        claude_queue = await logger.storage.get_claude_analysis_queue()
        assert len(claude_queue) >= 1  # At least the error should be there

        # Verify event classification worked
        error_events = [e for e in all_events if e.category == EventCategory.ERROR]
        assert len(error_events) >= 1
        assert error_events[0].priority in [EventPriority.HIGH, EventPriority.CRITICAL]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
