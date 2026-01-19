"""Format Log Node - From DESIGN.md"""
from datetime import datetime
from typing import Any
from uuid import uuid4
import structlog

logger = structlog.get_logger(__name__)


async def format_log_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    FORMAT_LOG Node - From DESIGN.md
    Standardizes event into audit log format.

    Input: Raw event data from capture_event
    Output: Formatted log ready for storage
    """
    logger.info(
        "Formatting audit log",
        task_id=state.get("task_id"),
        event_type=state.get("event_type"),
    )

    task_type = state.get("task_type", "log_event")

    # For query tasks, skip formatting
    if task_type in ["get_timeline", "generate_report"]:
        return {
            "stage": "format_log",
            "log_formatted": True,
            "formatted_log": {},
        }

    # Generate event ID and timestamp
    event_id = str(uuid4())
    timestamp = datetime.utcnow()

    # Build formatted log following AuditEvent schema from DESIGN.md
    formatted_log = {
        "event_id": event_id,
        "timestamp": timestamp.isoformat(),
        "incident_id": state.get("incident_id"),
        "agent_name": state.get("agent_name", "unknown"),
        "node_name": state.get("node_name"),
        "event_type": state.get("event_type", "state_change"),
        "payload": state.get("event_payload", {}),
        "previous_state": state.get("previous_state"),
        "new_state": state.get("new_state"),
        "decision_type": state.get("decision_type"),
        "decision_reasoning": state.get("decision_reasoning"),
        "actor": state.get("actor", "system"),
    }

    logger.info(
        "Audit log formatted",
        event_id=event_id,
        event_type=formatted_log["event_type"],
        incident_id=formatted_log["incident_id"],
    )

    return {
        "stage": "format_log",
        "event_id": event_id,
        "timestamp": timestamp.isoformat(),
        "formatted_log": formatted_log,
        "log_formatted": True,
    }
