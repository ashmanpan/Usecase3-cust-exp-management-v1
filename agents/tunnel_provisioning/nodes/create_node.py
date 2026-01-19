"""Create Tunnel Node - From DESIGN.md"""
from typing import Any
import structlog
from ..tools.cnc_tunnel import get_cnc_tunnel_client
from ..schemas.tunnels import TunnelConfig

logger = structlog.get_logger(__name__)

async def create_tunnel_node(state: dict[str, Any]) -> dict[str, Any]:
    """Call CNC tunnel provisioning API - From DESIGN.md"""
    incident_id = state.get("incident_id")
    tunnel_payload = state.get("tunnel_payload", {})
    retry_count = state.get("retry_count", 0)

    logger.info("Creating tunnel", incident_id=incident_id, retry=retry_count)

    client = get_cnc_tunnel_client()
    config = TunnelConfig(**tunnel_payload)

    if config.te_type in ["sr-mpls", "srv6"]:
        result = await client.create_sr_policy(config)
    else:
        result = await client.create_rsvp_tunnel(config)

    if result.success:
        logger.info("Tunnel created", incident_id=incident_id, tunnel_id=result.tunnel_id)
        return {
            "current_node": "create_tunnel",
            "nodes_executed": state.get("nodes_executed", []) + ["create_tunnel"],
            "tunnel_id": result.tunnel_id,
            "creation_success": True,
            "binding_sid": result.binding_sid,
        }
    else:
        logger.error("Tunnel creation failed", incident_id=incident_id, error=result.message)
        return {
            "current_node": "create_tunnel",
            "nodes_executed": state.get("nodes_executed", []) + ["create_tunnel"],
            "creation_success": False,
            "creation_error": result.message,
            "retry_count": retry_count + 1,
        }
