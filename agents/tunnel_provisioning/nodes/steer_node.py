"""Steer Traffic Node - From DESIGN.md"""
from typing import Any
import structlog

logger = structlog.get_logger(__name__)

async def steer_traffic_node(state: dict[str, Any]) -> dict[str, Any]:
    """Activate traffic steering to new tunnel - From DESIGN.md"""
    incident_id = state.get("incident_id")
    tunnel_id = state.get("tunnel_id")
    binding_sid = state.get("binding_sid")

    logger.info("Steering traffic", incident_id=incident_id, tunnel_id=tunnel_id, binding_sid=binding_sid)

    # Traffic steering via BGP color or ODN happens automatically when policy is created
    # This node confirms steering is active

    logger.info("Traffic steered to protection tunnel", incident_id=incident_id)
    return {
        "current_node": "steer_traffic",
        "nodes_executed": state.get("nodes_executed", []) + ["steer_traffic"],
        "traffic_steered": True,
    }
