#!/usr/bin/env python3
"""
Daily Analysis Script für Claude Code Logging System.

Generiert täglich comprehensive reports mit:
- Performance Trends
- Error Analysis  
- Business Metrics
- Optimization Recommendations
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import argparse

# Add src to path for imports
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.logging.core.storage import create_storage_backend
from src.logging.core.config import get_config
from src.logging.core.events import LogEvent, EventPriority, EventCategory


class DailyAnalyzer:
    """
    Daily Analysis Engine für Claude Code Integration.

    Analysiert Events der letzten 24h und generiert
    actionable insights und recommendations.
    """

    def __init__(self):
        self.config = get_config()
        self.storage = create_storage_backend()
        self.analysis_date = datetime.now()

    async def run_daily_analysis(self, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Run complete daily analysis."""
        print(f"🚀 Starting daily analysis for {self.analysis_date.strftime('%Y-%m-%d')}")

        # Get events from last 24 hours
        end_time = self.analysis_date
        start_time = end_time - timedelta(hours=24)

        events = await self.storage.query_events(
            start_time=start_time, end_time=end_time, limit=10000
        )

        print(f"📊 Analyzing {len(events)} events from last 24 hours")

        # Run analysis modules
        analysis_results = {
            "metadata": {
                "analysis_date": self.analysis_date.isoformat(),
                "time_range": {"start": start_time.isoformat(), "end": end_time.isoformat()},
                "total_events": len(events),
                "generated_at": datetime.now().isoformat(),
            },
            "performance_analysis": await self._analyze_performance(events),
            "error_analysis": await self._analyze_errors(events),
            "business_analysis": await self._analyze_business_metrics(events),
            "system_health": await self._analyze_system_health(events),
            "recommendations": await self._generate_recommendations(events),
            "claude_priority_events": await self._get_claude_priority_events(events),
        }

        # Generate reports
        if output_dir:
            await self._save_reports(analysis_results, output_dir)

        return analysis_results

    async def _analyze_performance(self, events: List[LogEvent]) -> Dict[str, Any]:
        """Analyze performance metrics and trends."""
        performance_events = [
            e for e in events if e.category == EventCategory.PERFORMANCE and e.duration_ms
        ]

        if not performance_events:
            return {"message": "No performance events found"}

        # Component performance breakdown
        component_performance = {}
        for event in performance_events:
            comp = event.component
            if comp not in component_performance:
                component_performance[comp] = []
            component_performance[comp].append(event.duration_ms)

        # Calculate statistics per component
        component_stats = {}
        for comp, durations in component_performance.items():
            durations.sort()
            count = len(durations)
            component_stats[comp] = {
                "count": count,
                "mean": sum(durations) / count,
                "median": durations[count // 2],
                "p95": durations[int(count * 0.95)] if count > 0 else 0,
                "p99": durations[int(count * 0.99)] if count > 0 else 0,
                "max": max(durations),
                "min": min(durations),
            }

        # Find slow operations
        slow_operations = [
            {
                "component": e.component,
                "operation": e.operation,
                "duration_ms": e.duration_ms,
                "timestamp": e.timestamp.isoformat(),
                "priority_score": e.claude_priority_score,
            }
            for e in sorted(performance_events, key=lambda x: x.duration_ms, reverse=True)[:10]
        ]

        # Performance trends (simplified)
        hourly_performance = {}
        for event in performance_events:
            hour = event.timestamp.hour
            if hour not in hourly_performance:
                hourly_performance[hour] = []
            hourly_performance[hour].append(event.duration_ms)

        hourly_avg = {
            hour: sum(durations) / len(durations) for hour, durations in hourly_performance.items()
        }

        return {
            "total_performance_events": len(performance_events),
            "component_statistics": component_stats,
            "slowest_operations": slow_operations,
            "hourly_averages": hourly_avg,
            "insights": self._generate_performance_insights(component_stats, slow_operations),
        }

    def _generate_performance_insights(
        self, component_stats: Dict, slow_operations: List
    ) -> List[str]:
        """Generate actionable performance insights."""
        insights = []

        # Check for problematic components
        for comp, stats in component_stats.items():
            if stats["p95"] > 2000:  # 2 second p95
                insights.append(
                    f"🚨 {comp}: 95th percentile response time is {stats['p95']:.0f}ms - "
                    f"investigate slow queries/operations"
                )
            elif stats["mean"] > 1000:  # 1 second average
                insights.append(
                    f"⚠️ {comp}: Average response time is {stats['mean']:.0f}ms - "
                    f"consider optimization"
                )

        # Check for extreme outliers
        if slow_operations:
            slowest = slow_operations[0]
            if slowest["duration_ms"] > 10000:  # 10 seconds
                insights.append(
                    f"🐌 Extremely slow operation detected: "
                    f"{slowest['component']}.{slowest['operation']} took "
                    f"{slowest['duration_ms']:.0f}ms - immediate investigation required"
                )

        return insights

    async def _analyze_errors(self, events: List[LogEvent]) -> Dict[str, Any]:
        """Analyze error patterns and frequencies."""
        error_events = [
            e
            for e in events
            if e.category == EventCategory.ERROR
            or e.priority in [EventPriority.HIGH, EventPriority.CRITICAL]
        ]

        if not error_events:
            return {"message": "No error events found - excellent!", "error_count": 0}

        # Error categorization
        error_types = {}
        component_errors = {}

        for event in error_events:
            # By error type
            error_type = event.error_type or "Unknown"
            error_types[error_type] = error_types.get(error_type, 0) + 1

            # By component
            comp = event.component
            component_errors[comp] = component_errors.get(comp, 0) + 1

        # Recent critical errors
        critical_errors = [
            {
                "timestamp": e.timestamp.isoformat(),
                "component": e.component,
                "error_type": e.error_type,
                "message": e.message,
                "priority": e.priority.value,
                "user_impact": e.user_impact,
            }
            for e in error_events
            if e.priority == EventPriority.CRITICAL
        ]

        return {
            "total_errors": len(error_events),
            "error_types": error_types,
            "errors_by_component": component_errors,
            "critical_errors": critical_errors,
            "error_rate_per_hour": len(error_events) / 24,
            "insights": self._generate_error_insights(error_events, error_types),
        }

    def _generate_error_insights(
        self, error_events: List[LogEvent], error_types: Dict
    ) -> List[str]:
        """Generate actionable error insights."""
        insights = []

        total_errors = len(error_events)

        if total_errors > 100:
            insights.append(
                f"🚨 High error rate: {total_errors} errors in 24h "
                f"({total_errors/24:.1f} errors/hour) - investigate immediately"
            )
        elif total_errors > 50:
            insights.append(
                f"⚠️ Elevated error rate: {total_errors} errors in 24h - monitor closely"
            )

        # Most common error types
        if error_types:
            most_common = max(error_types.items(), key=lambda x: x[1])
            if most_common[1] > 10:
                insights.append(
                    f"🔍 Most common error: {most_common[0]} "
                    f"({most_common[1]} occurrences) - focus optimization here"
                )

        return insights

    async def _analyze_business_metrics(self, events: List[LogEvent]) -> Dict[str, Any]:
        """Analyze business-relevant metrics."""
        business_events = [e for e in events if e.category == EventCategory.BUSINESS]

        if not business_events:
            return {"message": "No business events tracked"}

        # Feature usage analysis
        feature_usage = {}
        user_actions = {}

        for event in business_events:
            # Feature tracking
            feature = event.feature_affected or "unknown"
            feature_usage[feature] = feature_usage.get(feature, 0) + 1

            # User action tracking
            if event.operation:
                user_actions[event.operation] = user_actions.get(event.operation, 0) + 1

        # High impact events
        high_impact_events = [
            {
                "timestamp": e.timestamp.isoformat(),
                "feature": e.feature_affected,
                "action": e.operation,
                "user_impact": e.user_impact,
                "duration_ms": e.duration_ms,
            }
            for e in business_events
            if e.user_impact in ["high", "critical"]
        ]

        return {
            "total_business_events": len(business_events),
            "feature_usage": feature_usage,
            "user_actions": user_actions,
            "high_impact_events": high_impact_events,
            "insights": self._generate_business_insights(feature_usage, high_impact_events),
        }

    def _generate_business_insights(
        self, feature_usage: Dict, high_impact_events: List
    ) -> List[str]:
        """Generate business insights."""
        insights = []

        if feature_usage:
            most_used = max(feature_usage.items(), key=lambda x: x[1])
            insights.append(
                f"📈 Most used feature: {most_used[0]} "
                f"({most_used[1]} uses) - ensure optimal performance"
            )

            least_used = min(feature_usage.items(), key=lambda x: x[1])
            if least_used[1] < 5:
                insights.append(
                    f"📉 Underused feature: {least_used[0]} "
                    f"({least_used[1]} uses) - consider UX improvements or removal"
                )

        if len(high_impact_events) > 10:
            insights.append(
                f"⚠️ {len(high_impact_events)} high-impact events detected - "
                f"review user experience impacts"
            )

        return insights

    async def _analyze_system_health(self, events: List[LogEvent]) -> Dict[str, Any]:
        """Analyze overall system health."""
        system_events = [e for e in events if e.category == EventCategory.SYSTEM]

        # Health score calculation (simplified)
        error_count = len(
            [e for e in events if e.priority in [EventPriority.HIGH, EventPriority.CRITICAL]]
        )
        total_events = len(events)

        if total_events == 0:
            health_score = 100
        else:
            error_rate = error_count / total_events
            health_score = max(0, 100 - (error_rate * 1000))  # Penalize errors heavily

        return {
            "health_score": round(health_score, 1),
            "total_events": total_events,
            "error_events": error_count,
            "error_rate_percent": round(
                (error_count / total_events * 100) if total_events > 0 else 0, 2
            ),
            "status": "healthy"
            if health_score > 90
            else "warning"
            if health_score > 70
            else "critical",
        }

    async def _generate_recommendations(self, events: List[LogEvent]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations."""
        recommendations = []

        # Performance recommendations
        slow_events = [e for e in events if e.duration_ms and e.duration_ms > 2000]
        if len(slow_events) > 10:
            recommendations.append(
                {
                    "priority": "high",
                    "category": "performance",
                    "title": "Optimize Slow Operations",
                    "description": f"{len(slow_events)} operations took >2s in last 24h",
                    "action": "Review slowest queries and add database indexes or optimize algorithms",
                    "impact": "Improved user experience and system efficiency",
                }
            )

        # Error reduction recommendations
        error_events = [
            e for e in events if e.priority in [EventPriority.HIGH, EventPriority.CRITICAL]
        ]
        if len(error_events) > 20:
            recommendations.append(
                {
                    "priority": "critical",
                    "category": "reliability",
                    "title": "Reduce Error Rate",
                    "description": f"{len(error_events)} critical/high priority errors in 24h",
                    "action": "Implement better error handling and input validation",
                    "impact": "Increased system reliability and user satisfaction",
                }
            )

        # Memory optimization
        high_memory_events = [e for e in events if e.memory_mb and e.memory_mb > 100]
        if len(high_memory_events) > 5:
            recommendations.append(
                {
                    "priority": "medium",
                    "category": "resource_optimization",
                    "title": "Memory Usage Optimization",
                    "description": f"{len(high_memory_events)} operations used >100MB memory",
                    "action": "Review memory-intensive operations and implement optimization",
                    "impact": "Better resource utilization and system scalability",
                }
            )

        return recommendations

    async def _get_claude_priority_events(self, events: List[LogEvent]) -> List[Dict[str, Any]]:
        """Get high-priority events for Claude analysis."""
        claude_events = [
            e for e in events if e.requires_claude_analysis and e.claude_priority_score >= 70
        ]

        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "component": e.component,
                "category": e.category.value,
                "priority": e.priority.value,
                "claude_priority_score": e.claude_priority_score,
                "message": e.message,
                "analysis_tags": e.analysis_tags,
                "context": e.context,
            }
            for e in sorted(claude_events, key=lambda x: x.claude_priority_score, reverse=True)[:20]
        ]

    async def _save_reports(self, analysis_results: Dict[str, Any], output_dir: Path) -> None:
        """Save analysis results to files."""
        output_dir.mkdir(parents=True, exist_ok=True)

        date_str = self.analysis_date.strftime("%Y-%m-%d")

        # Save JSON report
        json_file = output_dir / f"daily_analysis_{date_str}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(analysis_results, f, indent=2, ensure_ascii=False)

        # Save Markdown summary
        md_file = output_dir / f"daily_summary_{date_str}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(self._generate_markdown_report(analysis_results))

        print(f"📄 Reports saved to {output_dir}")
        print(f"   - JSON: {json_file}")
        print(f"   - Markdown: {md_file}")

    def _generate_markdown_report(self, results: Dict[str, Any]) -> str:
        """Generate human-readable Markdown report."""
        metadata = results["metadata"]

        md = f"""# Daily System Analysis Report

**Date**: {metadata['analysis_date'][:10]}  
**Generated**: {metadata['generated_at'][:19]}  
**Events Analyzed**: {metadata['total_events']}  

## 🎯 Executive Summary

"""

        # System health
        health = results["system_health"]
        health_emoji = (
            "🟢" if health["status"] == "healthy" else "🟡" if health["status"] == "warning" else "🔴"
        )
        md += f"{health_emoji} **System Health Score**: {health['health_score']}/100 ({health['status']})\n\n"

        # Key metrics
        perf = results["performance_analysis"]
        errors = results["error_analysis"]

        if isinstance(perf, dict) and "total_performance_events" in perf:
            md += f"- **Performance Events**: {perf['total_performance_events']}\n"

        if isinstance(errors, dict) and "total_errors" in errors:
            md += f"- **Error Events**: {errors['total_errors']}\n"

        # Recommendations
        recommendations = results["recommendations"]
        if recommendations:
            md += "\n## 🚀 Priority Recommendations\n\n"
            for i, rec in enumerate(recommendations[:5], 1):
                priority_emoji = (
                    "🚨"
                    if rec["priority"] == "critical"
                    else "⚠️"
                    if rec["priority"] == "high"
                    else "💡"
                )
                md += f"{i}. {priority_emoji} **{rec['title']}**\n"
                md += f"   - {rec['description']}\n"
                md += f"   - *Action*: {rec['action']}\n\n"

        # Performance insights
        if isinstance(perf, dict) and "insights" in perf:
            md += "\n## ⚡ Performance Insights\n\n"
            for insight in perf["insights"]:
                md += f"- {insight}\n"

        # Error insights
        if isinstance(errors, dict) and "insights" in errors:
            md += "\n## 🐛 Error Analysis\n\n"
            for insight in errors["insights"]:
                md += f"- {insight}\n"

        md += f"\n---\n*Generated by Claude Code Logging System v12.1*"

        return md


async def main():
    """CLI entry point für daily analysis."""
    parser = argparse.ArgumentParser(description="Run daily analysis")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("logs/claude_analysis"),
        help="Output directory für reports",
    )
    parser.add_argument(
        "--json-only", action="store_true", help="Only output JSON results to stdout"
    )

    args = parser.parse_args()

    analyzer = DailyAnalyzer()
    results = await analyzer.run_daily_analysis(
        output_dir=None if args.json_only else args.output_dir
    )

    if args.json_only:
        print(json.dumps(results, indent=2, default=str))
    else:
        print("✅ Daily analysis completed successfully!")

        # Print summary to console
        health = results["system_health"]
        print(f"\n📊 System Health: {health['health_score']}/100 ({health['status']})")

        recommendations = results["recommendations"]
        if recommendations:
            print(f"\n🚀 Top Recommendations:")
            for i, rec in enumerate(recommendations[:3], 1):
                print(f"  {i}. {rec['title']}")


if __name__ == "__main__":
    asyncio.run(main())
