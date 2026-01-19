"""
Service Impact Agent

LangGraph-based agent for querying CNC Service Health and assessing impact.
From DESIGN.md: Query CNC Service Health API for affected L3VPN/L2VPN services,
determine impact severity, and return prioritized list to Orchestrator.

Port: 8002
"""

from .workflow import ServiceImpactWorkflow
from .main import ServiceImpactRunner, main

__all__ = [
    "ServiceImpactWorkflow",
    "ServiceImpactRunner",
    "main",
]
