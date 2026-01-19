"""
Event Correlator Agent Tools
"""

from .flap_detector import FlapDetector, check_flapping
from .dedup_checker import DedupChecker, check_duplicate
from .correlator import AlertCorrelator, correlate_alerts

__all__ = [
    "FlapDetector",
    "check_flapping",
    "DedupChecker",
    "check_duplicate",
    "AlertCorrelator",
    "correlate_alerts",
]
