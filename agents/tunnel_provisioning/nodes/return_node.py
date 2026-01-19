"""Return Success Node - From DESIGN.md"""
from typing import Any
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

async def return_success_node(state: dict[str, Any]) -> dict[str, Any]:
    """Return tunnel details to Orchestrator - From DESIGN.md"""
    incident_id = state.get("incident_id")
    tunnel_id = state.get("tunnel_id")
    binding_sid = state.get("binding_sid")
    te_type = state.get("detected_te_type")
    operational_status = state.get("operational_status", "up")
    creation_success = state.get("creation_success", False)

    if creation_success and state.get("tunnel_verified", False):
        result = {
            "incident_id": incident_id,
            "success": True,
            "tunnel_id": tunnel_id,
            "binding_sid": binding_sid,
            "te_type": te_type,
            "operational_status": operational_status,
            "traffic_steered": state.get("traffic_steered", False),
            "timestamp": datetime.utcnow().isoformat(),
        }
        status = "success"
        logger.info("Tunnel provisioning successful", incident_id=incident_id, tunnel_id=tunnel_id)
    else:
        result = {
            "incident_id": incident_id,
            "success": False,
            "error": state.get("creation_error", "Unknown error"),
            "retry_count": state.get("retry_count", 0),
            "timestamp": datetime.utcnow().isoformat(),
        }
        status = "failed"
        logger.error("Tunnel provisioning failed", incident_id=incident_id)

    return {
        "current_node": "return_success",
        "nodes_executed": state.get("nodes_executed", []) + ["return_success"],
        "result": result,
        "status": status,
        "completed_at": datetime.utcnow().isoformat(),
    }
