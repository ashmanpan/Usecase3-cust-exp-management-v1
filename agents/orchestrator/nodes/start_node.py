"""
Start Node

Entry point - Initialize incident, call Event Correlator.
From DESIGN.md: start -> detect
"""

from typing import Any
import structlog

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)


async def start_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Start Node - Entry point for orchestrator workflow.

    Actions:
    1. Initialize incident in Redis
    2. Call Event Correlator to process raw alert
    3. Return correlated event data

    Args:
        state: Current workflow state

    Returns:
        Updated state with correlation results
    """
    incident_id = state.get("incident_id")
    task_id = state.get("task_id")

    logger.info(
        "Starting orchestrator workflow",
        incident_id=incident_id,
        task_id=task_id,
    )

    # Save initial state to Redis
    await update_incident(
        incident_id=incident_id,
        updates={
            "status": "detecting",
            "alert_type": state.get("alert_type"),
            "degraded_links": state.get("degraded_links"),
            "severity": state.get("severity"),
        },
    )

    # Call Event Correlator Agent
    correlation_result = await call_agent(
        agent_name="event_correlator",
        task_type="correlate_alert",
        payload={
            "alert_source": state.get("alert_type"),
            "raw_alert": {
                "degraded_links": state.get("degraded_links"),
                "severity": state.get("severity"),
            },
        },
        incident_id=incident_id,
        timeout=30.0,
    )

    # Track A2A call
    a2a_tasks = state.get("a2a_tasks_sent", [])
    a2a_tasks.append({
        "agent": "event_correlator",
        "task_type": "correlate_alert",
        "success": correlation_result.get("success"),
    })

    # Update state with correlation results
    updates = {
        "current_node": "start",
        "nodes_executed": state.get("nodes_executed", []) + ["start"],
        "status": "detecting",
        "a2a_tasks_sent": a2a_tasks,
    }

    if correlation_result.get("success"):
        result = correlation_result.get("result", {})
        updates["a2a_responses"] = {
            **state.get("a2a_responses", {}),
            "event_correlator": result,
        }
        # Update degraded links from correlation if available
        if result.get("degraded_links"):
            updates["degraded_links"] = result.get("degraded_links")
        if result.get("severity"):
            updates["severity"] = result.get("severity")
        if result.get("is_flapping") is not None:
            updates["is_flapping"] = result.get("is_flapping")
    else:
        updates["error_message"] = correlation_result.get("error")

    logger.info(
        "Start node completed",
        incident_id=incident_id,
        correlation_success=correlation_result.get("success"),
    )

    return updates
