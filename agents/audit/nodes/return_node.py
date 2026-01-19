"""Return Audit Node - From DESIGN.md"""
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


async def return_audit_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    RETURN_AUDIT Node
    Builds final response based on task type.

    Input: Processing results from previous nodes
    Output: Final audit response
    """
    logger.info(
        "Building audit response",
        task_id=state.get("task_id"),
        task_type=state.get("task_type"),
    )

    task_type = state.get("task_type", "log_event")

    if task_type == "get_timeline":
        # Return timeline
        result = {
            "task_type": "timeline_response",
            "incident_id": state.get("incident_id"),
            "events": state.get("timeline_events", []),
            "event_count": state.get("timeline_count", 0),
        }

        logger.info(
            "Timeline response ready",
            incident_id=state.get("incident_id"),
            event_count=result["event_count"],
        )

    elif task_type == "generate_report":
        # Return compliance report
        report_data = state.get("report_data", {})
        result = {
            "task_type": "report_response",
            "report": report_data,
            "incident_count": report_data.get("incident_count", 0),
            "avg_resolution_time_seconds": report_data.get("avg_resolution_time_seconds", 0.0),
        }

        logger.info(
            "Compliance report response ready",
            incident_count=result["incident_count"],
        )

    else:
        # Return event logged confirmation (log_event)
        result = {
            "task_type": "event_logged",
            "payload": {
                "event_id": state.get("event_id"),
                "stored": state.get("db_stored", False),
                "indexed": state.get("indexed", False),
            },
        }

        if state.get("db_store_error"):
            result["payload"]["error"] = state.get("db_store_error")

        logger.info(
            "Event logged response ready",
            event_id=state.get("event_id"),
            stored=result["payload"]["stored"],
        )

    return {
        "stage": "return_audit",
        "status": "completed" if state.get("db_stored", True) else "failed",
        "result": result,
    }
