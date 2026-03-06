"""Create Tunnel Node - From DESIGN.md"""
import os
from typing import Any
import structlog
from ..tools.cnc_tunnel import get_cnc_tunnel_client
from ..schemas.tunnels import TunnelConfig, TunnelResult

logger = structlog.get_logger(__name__)

async def create_tunnel_node(state: dict[str, Any]) -> dict[str, Any]:
    """Call CNC tunnel provisioning API - From DESIGN.md

    Supports synchronous and asynchronous NSO provisioning modes controlled
    by the NSO_PROVISIONING_MODE env var ("sync" or "async", default "async").

    In async mode, if the CNC/NSO response contains a "job-id" field the node
    polls for job completion via CNCTunnelClient._poll_nso_job() before
    returning the result to the graph.
    """
    incident_id = state.get("incident_id")
    tunnel_payload = state.get("tunnel_payload", {})
    retry_count = state.get("retry_count", 0)

    nso_mode = os.getenv("NSO_PROVISIONING_MODE", "async").lower()
    logger.info(
        "Creating tunnel",
        incident_id=incident_id,
        retry=retry_count,
        nso_provisioning_mode=nso_mode,
    )

    client = get_cnc_tunnel_client()
    config = TunnelConfig(**tunnel_payload)

    if config.te_type in ["sr-mpls", "srv6"]:
        result = await client.create_sr_policy(config)
    else:
        result = await client.create_rsvp_tunnel(config)

    # ------------------------------------------------------------------
    # Async NSO job polling (GAP 12)
    # ------------------------------------------------------------------
    # When NSO_PROVISIONING_MODE is "async" and the underlying API
    # returned a job-id (embedded in result.message as a structured
    # marker), poll for completion.  The convention used here is that
    # create_rsvp_tunnel_via_nso (or any future async-capable method)
    # can embed the job-id in result.message with the prefix "job-id:".
    # Example message: "job-id:abc-123"
    if nso_mode == "async" and result.success and result.message.startswith("job-id:"):
        job_id = result.message.removeprefix("job-id:").strip()
        logger.info("Detected async NSO job, beginning poll", incident_id=incident_id, job_id=job_id)
        result = await client._poll_nso_job(job_id)

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
