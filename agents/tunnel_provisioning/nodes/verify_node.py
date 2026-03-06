"""Verify Tunnel Node - From DESIGN.md

Supports two verification paths controlled by TUNNEL_PROVISIONING_MODE:

  nso (default) / PCC path:
      Uses CNCTunnelClient.verify_tunnel() — queries CNC/NSO for tunnel state.

  pce / PCE path:
      Uses COETunnelOpsClient to query COE directly:
        - rsvp-te : get_rsvp_tunnel(head_end, end_point, tunnel_id)
        - sr-mpls / srv6 : get_sr_policy_details(head_end, end_point, color)
      Falls back gracefully (tunnel_verified=False) if the COE call fails.

Priority for provisioning_mode resolution:
  1. state["provisioning_mode"]  (per-tunnel override set by create_node)
  2. TUNNEL_PROVISIONING_MODE env var
  3. "nso" (hard default)
"""
import os
from typing import Any
import structlog
from ..tools.cnc_tunnel import get_cnc_tunnel_client

logger = structlog.get_logger(__name__)


async def _verify_via_pce(state: dict[str, Any]) -> dict[str, Any]:
    """PCE verification path using COETunnelOpsClient."""
    from ..tools.coe_tunnel_ops_client import get_coe_tunnel_ops_client

    incident_id = state.get("incident_id")
    tunnel_id = state.get("tunnel_id")
    te_type = state.get("detected_te_type", "sr-mpls")
    head_end = state.get("head_end")
    end_point = state.get("end_point")
    color = state.get("color", 0)

    coe = get_coe_tunnel_ops_client()

    try:
        if te_type == "rsvp-te":
            result = await coe.get_rsvp_tunnel(head_end, end_point, tunnel_id)
            op_status = (
                result.get("operational-status")
                or result.get("admin-status")
                or "unknown"
            )
            verified = op_status == "up"
        else:
            # sr-mpls or srv6
            result = await coe.get_sr_policy_details(head_end, end_point, color)
            op_status = result.get("operational-status", "unknown")
            verified = op_status == "up"

        logger.info(
            "PCE tunnel verification",
            incident_id=incident_id,
            te_type=te_type,
            verified=verified,
            operational_status=op_status,
        )
        return {
            "tunnel_verified": verified,
            "operational_status": op_status,
        }

    except Exception as e:
        logger.error(
            "PCE tunnel verification failed — falling back to unverified",
            incident_id=incident_id,
            te_type=te_type,
            error=str(e),
        )
        return {
            "tunnel_verified": False,
            "operational_status": "unknown",
        }


async def verify_tunnel_node(state: dict[str, Any]) -> dict[str, Any]:
    """Verify tunnel is UP via CNC API or COE API - From DESIGN.md.

    Priority for provisioning_mode:
      1. state["provisioning_mode"]  (per-tunnel override from create_node)
      2. TUNNEL_PROVISIONING_MODE env var
      3. "nso" default
    """
    incident_id = state.get("incident_id")
    tunnel_id = state.get("tunnel_id")
    te_type = state.get("detected_te_type", "sr-mpls")

    # Resolve provisioning mode using same priority as create_node.py
    provisioning_mode = (
        state.get("provisioning_mode")
        or os.getenv("TUNNEL_PROVISIONING_MODE", "nso")
    ).lower()

    logger.info(
        "Verifying tunnel",
        incident_id=incident_id,
        tunnel_id=tunnel_id,
        te_type=te_type,
        provisioning_mode=provisioning_mode,
    )

    if provisioning_mode == "pce":
        # PCE-initiated: query COE directly
        logger.info("Using PCE verification path via COE", incident_id=incident_id)
        verify_result = await _verify_via_pce(state)
    else:
        # NSO/PCC path: query CNC/NSO
        logger.info("Using NSO/PCC verification path via CNC", incident_id=incident_id)
        client = get_cnc_tunnel_client()
        status = await client.verify_tunnel(tunnel_id, te_type)
        op_status = status.get("operational_status", "unknown")
        verified = op_status == "up"
        logger.info(
            "NSO tunnel verification",
            incident_id=incident_id,
            verified=verified,
            operational_status=op_status,
        )
        verify_result = {
            "tunnel_verified": verified,
            "operational_status": op_status,
        }

    return {
        "current_node": "verify_tunnel",
        "nodes_executed": state.get("nodes_executed", []) + ["verify_tunnel"],
        "tunnel_verified": verify_result["tunnel_verified"],
        "operational_status": verify_result["operational_status"],
    }
