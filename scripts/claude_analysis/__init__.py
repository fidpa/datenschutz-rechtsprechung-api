"""
Claude Analysis Engine für intelligente Log-Analysis.

Modular Analysis Framework für:
- Daily Performance Reports
- Error Pattern Detection  
- Business Intelligence
- Predictive Maintenance
"""

import sys
from pathlib import Path

# Repository root on sys.path, the same bootstrap the modules in this package
# use, so `src` is importable when the package is imported from anywhere.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src._version import PROJECT_VERSION  # noqa: E402

from .daily_analysis import DailyAnalyzer
from .error_analyzer import ErrorPatternAnalyzer
from .performance_optimizer import PerformanceOptimizer
from .business_insights import BusinessInsightsAnalyzer

# The version is the project's, read from pyproject.toml via src._version --
# not a private "12.1.0" that never corresponded to a release.
__version__ = PROJECT_VERSION
__all__ = [
    "DailyAnalyzer",
    "ErrorPatternAnalyzer",
    "PerformanceOptimizer",
    "BusinessInsightsAnalyzer",
]
