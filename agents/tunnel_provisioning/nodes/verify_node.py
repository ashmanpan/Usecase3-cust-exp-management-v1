"""Verify Tunnel Node - From DESIGN.md"""
from typing import Any
import structlog
from ..tools.cnc_tunnel import get_cnc_tunnel_client

logger = structlog.get_logger(__name__)

async def verify_tunnel_node(state: dict[str, Any]) -> dict[str, Any]:
    """Verify tunnel is UP via CNC API - From DESIGN.md"""
    incident_id = state.get("incident_id")
    tunnel_id = state.get("tunnel_id")
    te_type = state.get("detected_te_type", "sr-mpls")

    logger.info("Verifying tunnel", incident_id=incident_id, tunnel_id=tunnel_id)

    client = get_cnc_tunnel_client()
    status = await client.verify_tunnel(tunnel_id, te_type)

    verified = status.get("operational_status") == "up"
    logger.info("Tunnel verification", incident_id=incident_id, verified=verified, status=status.get("operational_status"))

    return {
        "current_node": "verify_tunnel",
        "nodes_executed": state.get("nodes_executed", []) + ["verify_tunnel"],
        "tunnel_verified": verified,
        "operational_status": status.get("operational_status", "unknown"),
    }
