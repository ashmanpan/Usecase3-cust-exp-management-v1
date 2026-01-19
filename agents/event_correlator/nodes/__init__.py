"""
Event Correlator Agent Nodes

LangGraph nodes implementing the event correlator workflow.
Based on DESIGN.md node definitions.
"""

from .ingest_node import ingest_node
from .dedup_node import dedup_node
from .correlate_node import correlate_node
from .flap_detect_node import flap_detect_node
from .emit_node import emit_node
from .suppress_node import suppress_node
from .discard_node import discard_node

from .conditions import (
    check_duplicate,
    check_flap_status,
)

__all__ = [
    # Nodes
    "ingest_node",
    "dedup_node",
    "correlate_node",
    "flap_detect_node",
    "emit_node",
    "suppress_node",
    "discard_node",
    # Conditions
    "check_duplicate",
    "check_flap_status",
]
