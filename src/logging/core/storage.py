"""
Storage Backend für Claude Code Logging System.

JSONL-basierte Storage mit Database-Migration-Path für
Claude-friendly log analysis und future scalability.
"""

import json
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta
import gzip
import aiofiles

from .events import LogEvent
from .config import LoggingConfig, get_config


class StorageBackend(ABC):
    """Abstract base class für Storage Backends."""

    @abstractmethod
    async def store_event(self, event: LogEvent) -> None:
        """Store single event."""

    @abstractmethod
    async def store_events(self, events: List[LogEvent]) -> None:
        """Store multiple events in batch."""

    @abstractmethod
    async def query_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        component: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 1000,
    ) -> List[LogEvent]:
        """Query events with filters."""

    @abstractmethod
    async def get_claude_analysis_queue(self) -> List[LogEvent]:
        """Get events that require Claude analysis."""


class JSONLStorage(StorageBackend):
    """
    JSONL Storage Backend für Claude Code consumption.

    Features:
    - Claude-friendly JSONL format
    - Automatic file rotation
    - Compression für alte Files
    - Fast queries für recent data
    - Database migration path
    """

    def __init__(self, config: Optional[LoggingConfig] = None):
        self.config = config or get_config()
        self.storage_path = self.config.storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # In-memory buffer für performance
        self._buffer: List[LogEvent] = []
        self._buffer_lock = asyncio.Lock()

        # File handles cache
        self._file_handles: Dict[str, Any] = {}

    async def store_event(self, event: LogEvent) -> None:
        """Store single event."""
        await self.store_events([event])

    async def store_events(self, events: List[LogEvent]) -> None:
        """Store multiple events efficiently."""
        if not events:
            return

        # Group events by component and category for optimal file organization
        grouped_events = self._group_events_by_file(events)

        # Write to appropriate files
        for file_key, event_list in grouped_events.items():
            await self._write_events_to_file(file_key, event_list)

    def _group_events_by_file(self, events: List[LogEvent]) -> Dict[str, List[LogEvent]]:
        """Group events by target file for optimal storage."""
        grouped = {}

        for event in events:
            file_path = self.config.get_storage_file_path(
                event.component or "unknown", event.category.value
            )
            file_key = str(file_path)

            if file_key not in grouped:
                grouped[file_key] = []
            grouped[file_key].append(event)

        return grouped

    async def _write_events_to_file(self, file_path: str, events: List[LogEvent]) -> None:
        """Write events to JSONL file."""
        path = Path(file_path)

        # Check if file rotation is needed
        if path.exists() and path.stat().st_size > (self.config.max_file_size_mb * 1024 * 1024):
            await self._rotate_file(path)

        # Write events as JSONL
        async with aiofiles.open(path, "a", encoding="utf-8") as f:
            for event in events:
                json_line = json.dumps(event.to_dict(), ensure_ascii=False, default=str)
                await f.write(json_line + "\n")

    async def _rotate_file(self, file_path: Path) -> None:
        """Rotate log file when it becomes too large."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated_path = file_path.with_suffix(f".{timestamp}.jsonl")

        # Move current file
        file_path.rename(rotated_path)

        # Compress old file in background
        asyncio.create_task(self._compress_file(rotated_path))

    async def _compress_file(self, file_path: Path) -> None:
        """Compress rotated log file."""
        try:
            compressed_path = file_path.with_suffix(file_path.suffix + ".gz")

            with open(file_path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    f_out.writelines(f_in)

            # Remove original file after compression
            file_path.unlink()

        except Exception as e:
            # Log compression error but don't fail the application
            print(f"Warning: Failed to compress {file_path}: {e}")

    async def query_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        component: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 1000,
    ) -> List[LogEvent]:
        """Query events from JSONL files."""
        events = []

        # Determine which files to search
        files_to_search = self._get_relevant_files(start_time, end_time, component, category)

        for file_path in files_to_search:
            file_events = await self._read_events_from_file(
                file_path, start_time, end_time, component, category, priority
            )
            events.extend(file_events)

            if len(events) >= limit:
                break

        # Sort by timestamp (newest first) and limit
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]

    def _get_relevant_files(
        self,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        component: Optional[str],
        category: Optional[str],
    ) -> List[Path]:
        """Get list of files that might contain relevant events."""
        files = []

        # Get all JSONL files in storage directory
        for file_path in self.storage_path.glob("*.jsonl"):
            # Basic filtering by filename patterns
            if component and component not in file_path.name:
                continue
            if category and category not in file_path.name:
                continue

            files.append(file_path)

        # Also check compressed files if time range extends back
        if start_time and start_time < datetime.now() - timedelta(days=1):
            for file_path in self.storage_path.glob("*.jsonl.gz"):
                if component and component not in file_path.name:
                    continue
                if category and category not in file_path.name:
                    continue

                files.append(file_path)

        # Sort by modification time (newest first)
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files

    async def _read_events_from_file(
        self,
        file_path: Path,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        component: Optional[str],
        category: Optional[str],
        priority: Optional[str],
    ) -> List[LogEvent]:
        """Read and filter events from a single file."""
        events = []

        try:
            # Handle compressed files
            if file_path.suffix == ".gz":
                # For now, skip compressed files in queries (optimization for later)
                return []

            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                async for line in f:
                    try:
                        event_data = json.loads(line.strip())
                        event = self._dict_to_event(event_data)

                        # Apply filters
                        if not self._event_matches_filters(
                            event, start_time, end_time, component, category, priority
                        ):
                            continue

                        events.append(event)

                    except (json.JSONDecodeError, KeyError):
                        # Skip malformed lines
                        continue

        except Exception as e:
            # Log file read error but continue
            print(f"Warning: Failed to read {file_path}: {e}")

        return events

    def _dict_to_event(self, data: Dict[str, Any]) -> LogEvent:
        """Convert dictionary back to LogEvent."""
        from .events import EventType, EventPriority, EventCategory

        # Convert timestamp string back to datetime
        if isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

        # Convert enum strings back to enums
        data["event_type"] = EventType(data["event_type"])
        data["priority"] = EventPriority(data["priority"])
        data["category"] = EventCategory(data["category"])

        # Extract nested data
        if "performance" in data:
            perf = data.pop("performance")
            data.update(
                {
                    "duration_ms": perf.get("duration_ms"),
                    "memory_mb": perf.get("memory_mb"),
                    "cpu_percent": perf.get("cpu_percent"),
                }
            )

        if "business_impact" in data:
            business = data.pop("business_impact")
            data.update(
                {
                    "user_impact": business.get("user_impact"),
                    "revenue_impact": business.get("revenue_impact"),
                    "feature_affected": business.get("feature_affected"),
                }
            )

        if "error" in data:
            error = data.pop("error")
            data.update(
                {
                    "error_type": error.get("type"),
                    "error_message": error.get("message"),
                    "stack_trace": error.get("stack_trace"),
                }
            )

        if "request" in data:
            request = data.pop("request")
            data.update(
                {
                    "request_id": request.get("id"),
                    "user_id": request.get("user_id"),
                    "endpoint": request.get("endpoint"),
                    "method": request.get("method"),
                    "status_code": request.get("status_code"),
                }
            )

        if "technical" in data:
            tech = data.pop("technical")
            data.update(
                {
                    "environment": tech.get("environment", "development"),
                    "version": tech.get("version"),
                    "host": tech.get("host"),
                }
            )

        if "claude_analysis" in data:
            claude = data.pop("claude_analysis")
            data.update(
                {
                    "analysis_tags": claude.get("tags", []),
                    "requires_claude_analysis": claude.get("requires_analysis", False),
                    "claude_priority_score": claude.get("priority_score", 0),
                }
            )

        return LogEvent(**data)

    def _event_matches_filters(
        self,
        event: LogEvent,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        component: Optional[str],
        category: Optional[str],
        priority: Optional[str],
    ) -> bool:
        """Check if event matches query filters."""
        if start_time and event.timestamp < start_time:
            return False

        if end_time and event.timestamp > end_time:
            return False

        if component and event.component != component:
            return False

        if category and event.category.value != category:
            return False

        if priority and event.priority.value != priority:
            return False

        return True

    async def get_claude_analysis_queue(self) -> List[LogEvent]:
        """Get events that require Claude analysis."""
        # Query recent events that need Claude analysis
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)  # Last 24 hours

        all_events = await self.query_events(start_time=start_time, limit=10000)

        # Filter for events requiring Claude analysis
        claude_events = [
            event
            for event in all_events
            if event.requires_claude_analysis
            and event.claude_priority_score >= self.config.claude_priority_threshold
        ]

        # Sort by priority score (highest first)
        claude_events.sort(key=lambda e: e.claude_priority_score, reverse=True)

        return claude_events

    async def cleanup_old_files(self) -> None:
        """Clean up files older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.config.retention_days)

        for file_path in self.storage_path.glob("*.jsonl*"):
            try:
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_date:
                    file_path.unlink()
                    print(f"Deleted old log file: {file_path}")
            except Exception as e:
                print(f"Warning: Failed to delete {file_path}: {e}")


class HybridStorage(StorageBackend):
    """
    Hybrid storage backend combining JSONL and Database.

    Strategy:
    - Recent events (last 7 days): JSONL for fast Claude access
    - Older events: Database for efficient queries
    - Critical events: Both for redundancy
    """

    def __init__(self, config: Optional[LoggingConfig] = None):
        self.config = config or get_config()
        self.jsonl_storage = JSONLStorage(config)
        # Database storage will be implemented in future phase
        self.db_storage = None

    async def store_event(self, event: LogEvent) -> None:
        """Store event in appropriate backend(s)."""
        # Always store in JSONL for Claude access
        await self.jsonl_storage.store_event(event)

        # Store critical events in database for redundancy (future feature)
        if event.priority.value in ["critical", "high"]:
            # TODO: Implement database storage
            pass

    async def store_events(self, events: List[LogEvent]) -> None:
        """Store multiple events."""
        await self.jsonl_storage.store_events(events)

        # Future: Also store in database

    async def query_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        component: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 1000,
    ) -> List[LogEvent]:
        """Query from appropriate storage based on time range."""
        # For now, use JSONL storage
        return await self.jsonl_storage.query_events(
            start_time, end_time, component, category, priority, limit
        )

    async def get_claude_analysis_queue(self) -> List[LogEvent]:
        """Get events for Claude analysis."""
        return await self.jsonl_storage.get_claude_analysis_queue()


def create_storage_backend(config: Optional[LoggingConfig] = None) -> StorageBackend:
    """Factory function to create appropriate storage backend."""
    config = config or get_config()

    if config.storage_backend.value == "jsonl":
        return JSONLStorage(config)
    elif config.storage_backend.value == "hybrid":
        return HybridStorage(config)
    else:
        # Default to JSONL for MVP
        return JSONLStorage(config)
