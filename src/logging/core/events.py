"""
Event Classification und Priority System für Claude Code Logging.

Intelligente Klassifizierung von Log-Events für optimale Claude-Analysis
und Business-Impact-driven Prioritization.
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import uuid


class EventType(Enum):
    """Event-Typen für intelligente Routing und Analysis."""

    # Critical Path - Immediate Claude Analysis
    CRITICAL_ERROR = "critical_error"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SECURITY_INCIDENT = "security_incident"

    # Business Path - Daily/Weekly Claude Reports
    USER_ACTION = "user_action"
    FEATURE_USAGE = "feature_usage"
    BUSINESS_METRIC = "business_metric"

    # Operational Path - Automated Monitoring
    HEALTH_CHECK = "health_check"
    SYSTEM_METRIC = "system_metric"
    RESOURCE_USAGE = "resource_usage"

    # Intelligence Path - Pattern Detection
    TREND_DATA = "trend_data"
    PATTERN_MATCH = "pattern_match"
    ANOMALY_DETECTED = "anomaly_detected"


class EventPriority(Enum):
    """Business-Impact-driven Event Prioritization."""

    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"  # Action within 1 hour
    MEDIUM = "medium"  # Action within 24 hours
    LOW = "low"  # Action within 1 week
    INFO = "info"  # No action required


class EventCategory(Enum):
    """Event-Kategorien für Claude-Analysis-Routing."""

    PERFORMANCE = "performance"
    ERROR = "error"
    SECURITY = "security"
    BUSINESS = "business"
    SYSTEM = "system"
    USER_EXPERIENCE = "user_experience"


@dataclass
class LogEvent:
    """
    Strukturierte Log-Event Klasse für Claude Code consumption.

    Optimized für:
    - Claude Pattern Recognition
    - Business Impact Assessment
    - Automated Analysis
    - Context-Rich Information
    """

    # Core Event Information
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: EventType = EventType.SYSTEM_METRIC
    priority: EventPriority = EventPriority.INFO
    category: EventCategory = EventCategory.SYSTEM

    # Event Content
    message: str = ""
    component: str = ""  # Flask, FastAPI, Celery, Database, etc.
    operation: Optional[str] = None

    # Context Information for Claude
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Performance Metrics
    duration_ms: Optional[float] = None
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None

    # Business Impact Assessment
    user_impact: Optional[str] = None  # none, low, medium, high, critical
    revenue_impact: Optional[str] = None
    feature_affected: Optional[str] = None

    # Error Information
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None

    # Request/Response Context
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    status_code: Optional[int] = None

    # Technical Details
    environment: str = "development"
    version: Optional[str] = None
    host: Optional[str] = None

    # Claude Analysis Tags
    analysis_tags: List[str] = field(default_factory=list)
    requires_claude_analysis: bool = False
    claude_priority_score: int = 0  # 0-100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Claude-friendly dictionary format."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "priority": self.priority.value,
            "category": self.category.value,
            "message": self.message,
            "component": self.component,
            "operation": self.operation,
            "context": self.context,
            "metadata": self.metadata,
            "performance": {
                "duration_ms": self.duration_ms,
                "memory_mb": self.memory_mb,
                "cpu_percent": self.cpu_percent,
            },
            "business_impact": {
                "user_impact": self.user_impact,
                "revenue_impact": self.revenue_impact,
                "feature_affected": self.feature_affected,
            },
            "error": {
                "type": self.error_type,
                "message": self.error_message,
                "stack_trace": self.stack_trace,
            },
            "request": {
                "id": self.request_id,
                "user_id": self.user_id,
                "endpoint": self.endpoint,
                "method": self.method,
                "status_code": self.status_code,
            },
            "technical": {
                "environment": self.environment,
                "version": self.version,
                "host": self.host,
            },
            "claude_analysis": {
                "tags": self.analysis_tags,
                "requires_analysis": self.requires_claude_analysis,
                "priority_score": self.claude_priority_score,
            },
        }


class EventClassifier:
    """
    Intelligente Event-Klassifizierung für Claude Code Analysis.

    Automatische Bestimmung von:
    - Event Priority basierend auf Business Impact
    - Claude Analysis Requirements
    - Routing Decisions
    """

    # Critical Keywords für automatische Priorisierung
    CRITICAL_KEYWORDS = [
        "error",
        "exception",
        "failed",
        "crash",
        "timeout",
        "security",
        "breach",
        "unauthorized",
        "injection",
        "performance",
        "slow",
        "degradation",
        "bottleneck",
    ]

    # Business Impact Keywords
    BUSINESS_IMPACT_KEYWORDS = {
        "high": [
            "payment",
            "checkout",
            "login",
            "signup",
            "billing",
            "critical",
            "critical_feature",
        ],
        "medium": ["search", "export", "dashboard", "report"],
        "low": ["analytics", "logging", "cache", "background"],
    }

    # Performance Thresholds
    PERFORMANCE_THRESHOLDS = {
        "critical": {"response_time": 5000, "error_rate": 0.1, "cpu": 90},
        "high": {"response_time": 2000, "error_rate": 0.05, "cpu": 80},
        "medium": {"response_time": 1000, "error_rate": 0.02, "cpu": 70},
    }

    @classmethod
    def classify_event(cls, event: LogEvent) -> LogEvent:
        """
        Klassifiziert Event und setzt Priority/Tags automatisch.

        Args:
            event: Log-Event zum klassifizieren

        Returns:
            Klassifiziertes Event mit gesetzter Priority und Analysis-Tags
        """
        # 1. Analyze Message Content
        message_lower = event.message.lower()

        # 2. Check for Critical Keywords
        if any(keyword in message_lower for keyword in cls.CRITICAL_KEYWORDS):
            event.priority = EventPriority.CRITICAL
            event.requires_claude_analysis = True
            event.claude_priority_score = 90
            event.analysis_tags.append("critical_pattern")

        # 3. Assess Business Impact
        business_impact = cls._assess_business_impact(event)
        event.user_impact = business_impact

        if business_impact in ["high", "critical"]:
            # Only upgrade priority if it's not already critical
            if event.priority != EventPriority.CRITICAL:
                event.priority = EventPriority.HIGH
            event.requires_claude_analysis = True
            event.claude_priority_score = max(event.claude_priority_score, 70)
            event.analysis_tags.append("business_critical")

        # 4. Performance Analysis
        if (
            event.duration_ms
            and event.duration_ms > cls.PERFORMANCE_THRESHOLDS["critical"]["response_time"]
        ):
            # Performance issues can override other priorities
            event.priority = EventPriority.CRITICAL
            event.event_type = EventType.PERFORMANCE_DEGRADATION
            event.category = EventCategory.PERFORMANCE
            event.requires_claude_analysis = True
            event.analysis_tags.append("performance_critical")

        # 5. Error Classification
        if event.error_type or event.error_message:
            event.category = EventCategory.ERROR
            if event.priority == EventPriority.INFO:  # Don't downgrade already set priority
                event.priority = EventPriority.MEDIUM
            event.analysis_tags.append("error_analysis")

        # 6. Set Event Type based on Category
        cls._set_event_type(event)

        # 7. Calculate Claude Priority Score
        event.claude_priority_score = cls._calculate_claude_priority(event)

        return event

    @classmethod
    def _assess_business_impact(cls, event: LogEvent) -> str:
        """Assess business impact based on context and keywords."""
        message = event.message.lower()
        endpoint = (event.endpoint or "").lower()
        feature = (event.feature_affected or "").lower()

        # Check all text for business impact keywords
        text_to_check = f"{message} {endpoint} {feature}"

        for impact_level, keywords in cls.BUSINESS_IMPACT_KEYWORDS.items():
            if any(keyword in text_to_check for keyword in keywords):
                return impact_level

        # Default assessment based on component
        if event.component in ["flask", "fastapi"]:
            return "medium"  # User-facing components
        elif event.component in ["celery", "database"]:
            return "low"  # Background components

        return "none"

    @classmethod
    def _set_event_type(cls, event: LogEvent) -> None:
        """Set appropriate event type based on classification."""
        if event.category == EventCategory.ERROR and event.priority == EventPriority.CRITICAL:
            event.event_type = EventType.CRITICAL_ERROR
        elif event.category == EventCategory.PERFORMANCE:
            event.event_type = EventType.PERFORMANCE_DEGRADATION
        elif event.category == EventCategory.SECURITY:
            event.event_type = EventType.SECURITY_INCIDENT
        elif event.category == EventCategory.BUSINESS:
            event.event_type = EventType.BUSINESS_METRIC
        elif event.category == EventCategory.USER_EXPERIENCE:
            event.event_type = EventType.USER_ACTION
        else:
            event.event_type = EventType.SYSTEM_METRIC

    @classmethod
    def _calculate_claude_priority(cls, event: LogEvent) -> int:
        """Calculate Claude analysis priority score (0-100)."""
        score = 0

        # Base score from priority
        priority_scores = {
            EventPriority.CRITICAL: 90,
            EventPriority.HIGH: 70,
            EventPriority.MEDIUM: 50,
            EventPriority.LOW: 30,
            EventPriority.INFO: 10,
        }
        score += priority_scores.get(event.priority, 10)

        # Bonus for business impact
        if event.user_impact in ["high", "critical"]:
            score += 10

        # Bonus for performance issues
        if event.duration_ms and event.duration_ms > 1000:
            score += 5

        # Bonus for errors
        if event.error_type:
            score += 5

        return min(score, 100)


# Convenience Functions for Event Creation


def create_performance_event(
    component: str, operation: str, duration_ms: float, message: str = "", **kwargs
) -> LogEvent:
    """Create performance monitoring event."""
    return LogEvent(
        event_type=EventType.PERFORMANCE_DEGRADATION,
        category=EventCategory.PERFORMANCE,
        component=component,
        operation=operation,
        duration_ms=duration_ms,
        message=message or f"Performance event: {operation} took {duration_ms}ms",
        **kwargs,
    )


def create_error_event(
    component: str, error_type: str, error_message: str, stack_trace: Optional[str] = None, **kwargs
) -> LogEvent:
    """Create error event."""
    return LogEvent(
        event_type=EventType.CRITICAL_ERROR,
        category=EventCategory.ERROR,
        component=component,
        error_type=error_type,
        error_message=error_message,
        stack_trace=stack_trace,
        message=f"Error in {component}: {error_message}",
        **kwargs,
    )


def create_business_event(
    component: str, feature: str, action: str, user_id: Optional[str] = None, **kwargs
) -> LogEvent:
    """Create business/user action event."""
    return LogEvent(
        event_type=EventType.USER_ACTION,
        category=EventCategory.BUSINESS,
        component=component,
        feature_affected=feature,
        operation=action,
        user_id=user_id,
        message=f"User action: {action} on {feature}",
        **kwargs,
    )
