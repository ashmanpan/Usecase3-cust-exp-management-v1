"""Steer Traffic Node - From DESIGN.md"""
import os
from typing import Any, Tuple

import httpx
import structlog
from ..tools.cnc_srte_config_client import get_srte_config_client

logger = structlog.get_logger(__name__)

CNC_NSO_URL = os.getenv("CNC_NSO_URL", "https://cnc.example.com:8888")


async def _steer_rsvp_te_vrfs(
    head_end: str,
    affected_vrfs: list[str],
    tunnel_endpoint_ip: str,
    tunnel_id: str,
) -> Tuple[bool, str]:
    """POST VRF steering update to CNC/NSO for RSVP-TE tunnels.

    Builds a REST payload that updates the BGP next-hop / static route for
    each affected VRF on the head-end PE so that traffic is forwarded into
    the RSVP-TE tunnel.

    Returns:
        (success, error_message) — error_message is empty string on success.
    """
    url = f"{CNC_NSO_URL}/api/running/devices/device/{head_end}/config/vrf-steering"
    payload = {
        "input": {
            "vrfs": [
                {
                    "name": vrf,
                    "tunnel-id": tunnel_id,
                    "next-hop": tunnel_endpoint_ip,
                }
                for vrf in affected_vrfs
            ]
        }
    }

    logger.info(
        "Posting RSVP-TE VRF steering to CNC/NSO",
        url=url,
        head_end=head_end,
        affected_vrfs=affected_vrfs,
        tunnel_id=tunnel_id,
        tunnel_endpoint_ip=tunnel_endpoint_ip,
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        logger.info(
            "RSVP-TE VRF steering succeeded",
            head_end=head_end,
            tunnel_id=tunnel_id,
            status_code=response.status_code,
        )
        return (True, "")
    except httpx.HTTPError as e:
        error_msg = str(e)
        logger.error(
            "RSVP-TE VRF steering failed",
            head_end=head_end,
            tunnel_id=tunnel_id,
            error=error_msg,
        )
        return (False, error_msg)


async def steer_traffic_node(state: dict[str, Any]) -> dict[str, Any]:
    """Activate traffic steering to new tunnel - From DESIGN.md.

    Behaviour depends on the detected TE type stored in state:

    SR-MPLS / SRv6:
        Traffic steering via BGP color / ODN is automatic when the SR policy
        is created.  This node simply confirms steering is active and returns
        traffic_steered=True without any additional API call.

    RSVP-TE:
        Steering is NOT automatic.  Each affected VRF on the head-end PE must
        have its BGP next-hop updated to point at the tunnel endpoint IP.
        This node calls _steer_rsvp_te_vrfs() which POSTs the update to the
        CNC/NSO REST API.
    """
    incident_id = state.get("incident_id")
    tunnel_id = state.get("tunnel_id")
    detected_te_type = state.get("detected_te_type")

    logger.info(
        "Steering traffic",
        incident_id=incident_id,
        tunnel_id=tunnel_id,
        detected_te_type=detected_te_type,
    )

    base_update: dict[str, Any] = {
        "current_node": "steer_traffic",
        "nodes_executed": state.get("nodes_executed", []) + ["steer_traffic"],
    }

    # ------------------------------------------------------------------
    # SR-MPLS / SRv6: ODN / color-based steering is automatic.
    # Add a lightweight CAT verification to confirm the policy exists.
    # ------------------------------------------------------------------
    if detected_te_type in ("sr-mpls", "srv6"):
        logger.info(
            "SR ODN/color auto-steering active — no explicit API call required",
            incident_id=incident_id,
            tunnel_id=tunnel_id,
            te_type=detected_te_type,
        )

        head_end = state.get("head_end")
        color = state.get("color", 0)
        end_point = state.get("end_point")

        policy_verified = False
        try:
            srte = get_srte_config_client()
            policy = await srte.get_sr_policy(head_end, color, end_point)
            if policy:
                policy_verified = True
                logger.info(
                    "SR-TE policy confirmed on CAT",
                    incident_id=incident_id,
                    head_end=head_end,
                    color=color,
                    end_point=end_point,
                )
            else:
                logger.warning(
                    "SR-TE policy not found on CAT — ODN steering still active",
                    incident_id=incident_id,
                    head_end=head_end,
                    color=color,
                    end_point=end_point,
                )
        except Exception as e:
            logger.warning(
                "SR-TE CAT policy verification failed — ODN steering still active",
                incident_id=incident_id,
                head_end=head_end,
                color=color,
                end_point=end_point,
                error=str(e),
            )

        return {
            **base_update,
            "traffic_steered": True,
            "policy_verified": policy_verified,
        }

    # ------------------------------------------------------------------
    # RSVP-TE: must explicitly update VRF next-hop via CNC/NSO
    # ------------------------------------------------------------------
    if detected_te_type == "rsvp-te":
        head_end = state.get("head_end")
        affected_vrfs = state.get("affected_vrfs")
        tunnel_endpoint_ip = state.get("tunnel_endpoint_ip")

        missing = [
            name
            for name, val in (
                ("head_end", head_end),
                ("affected_vrfs", affected_vrfs),
                ("tunnel_endpoint_ip", tunnel_endpoint_ip),
                ("tunnel_id", tunnel_id),
            )
            if not val
        ]

        if missing:
            error_msg = "Missing VRF steering parameters for RSVP-TE"
            logger.warning(
                error_msg,
                incident_id=incident_id,
                missing_fields=missing,
            )
            return {
                **base_update,
                "traffic_steered": False,
                "steer_error": error_msg,
            }

        success, error = await _steer_rsvp_te_vrfs(
            head_end=head_end,
            affected_vrfs=affected_vrfs,
            tunnel_endpoint_ip=tunnel_endpoint_ip,
            tunnel_id=tunnel_id,
        )

        if success:
            logger.info(
                "Traffic steered to RSVP-TE protection tunnel",
                incident_id=incident_id,
                tunnel_id=tunnel_id,
            )
            return {
                **base_update,
                "traffic_steered": True,
            }
        else:
            return {
                **base_update,
                "traffic_steered": False,
                "steer_error": error,
            }

    # ------------------------------------------------------------------
    # Unknown TE type — fail safely
    # ------------------------------------------------------------------
    error_msg = f"Unknown detected_te_type: {detected_te_type!r}"
    logger.error(error_msg, incident_id=incident_id, tunnel_id=tunnel_id)
    return {
        **base_update,
        "traffic_steered": False,
        "steer_error": error_msg,
    }
