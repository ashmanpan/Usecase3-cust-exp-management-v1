"""
Event Correlator Agent

LangGraph-based agent for alert correlation, deduplication, and flap detection.
From DESIGN.md: Receives alerts from PCA/CNC, correlates related events,
detects flapping, and emits incidents to Orchestrator.

Port: 8001
"""

from .workflow import EventCorrelatorWorkflow
from .main import EventCorrelatorRunner, main

__all__ = [
    "EventCorrelatorWorkflow",
    "EventCorrelatorRunner",
    "main",
]
