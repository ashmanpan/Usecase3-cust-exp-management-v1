"""
Orchestrator Agent

Supervisor agent that coordinates the entire protection workflow using
a state machine with hybrid (rules + LLM) decision logic.

State Machine Flow:
    START -> detect -> assess -> compute -> provision -> steer -> monitor -> restore -> close -> END

    Branches:
    - detect -> dampen (if flapping)
    - assess -> close (if no services affected)
    - compute -> escalate (if no path found)
    - provision -> escalate (if max retries exceeded)
"""

from .workflow import OrchestratorWorkflow
from .schemas.state import OrchestratorState, create_initial_state

__version__ = "1.0.0"

__all__ = [
    "OrchestratorWorkflow",
    "OrchestratorState",
    "create_initial_state",
]
