"""Capture Event Node - From DESIGN.md"""
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


async def capture_event_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    CAPTURE_EVENT Node - From DESIGN.md
    Receives event from any agent and extracts event data.

    Input: A2A task payload with event details
    Output: Extracted event fields for formatting
    """
    logger.info(
        "Capturing audit event",
        task_id=state.get("task_id"),
        task_type=state.get("task_type"),
    )

    payload = state.get("payload", {})
    task_type = state.get("task_type", "log_event")

    # Handle different task types
    if task_type == "log_event":
        # Extract event data from payload
        return {
            "stage": "capture_event",
            "event_type": payload.get("event_type", "state_change"),
            "agent_name": payload.get("agent_name", "unknown"),
            "node_name": payload.get("node_name"),
            "event_payload": payload.get("data", {}),
            "previous_state": payload.get("previous_state"),
            "new_state": payload.get("new_state"),
            "decision_type": payload.get("decision_type"),
            "decision_reasoning": payload.get("decision_reasoning"),
            "actor": payload.get("actor", "system"),
        }

    elif task_type == "get_timeline":
        # Timeline query - incident_id already in state
        return {
            "stage": "capture_event",
            "event_type": "timeline_query",
            "agent_name": "audit",
            "node_name": "capture_event",
            "event_payload": {"query_type": "timeline"},
            "actor": "system",
        }

    elif task_type == "generate_report":
        # Compliance report generation
        return {
            "stage": "capture_event",
            "event_type": "report_query",
            "agent_name": "audit",
            "node_name": "capture_event",
            "event_payload": {"query_type": "compliance_report"},
            "report_start_date": payload.get("start_date"),
            "report_end_date": payload.get("end_date"),
            "actor": "system",
        }

    else:
        logger.warning(
            "Unknown task type for audit",
            task_type=task_type,
        )
        return {
            "stage": "capture_event",
            "event_type": "unknown",
            "agent_name": payload.get("agent_name", "unknown"),
            "event_payload": payload,
            "actor": "system",
        }
