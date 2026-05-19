"""
Claude Analysis Engine für intelligente Log-Analysis.

Modular Analysis Framework für:
- Daily Performance Reports
- Error Pattern Detection  
- Business Intelligence
- Predictive Maintenance
"""

from .daily_analysis import DailyAnalyzer
from .error_analyzer import ErrorPatternAnalyzer
from .performance_optimizer import PerformanceOptimizer
from .business_insights import BusinessInsightsAnalyzer

__version__ = "12.1.0"
__all__ = [
    "DailyAnalyzer",
    "ErrorPatternAnalyzer",
    "PerformanceOptimizer",
    "BusinessInsightsAnalyzer",
]
