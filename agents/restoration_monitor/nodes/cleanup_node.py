"""Cleanup Tunnel Node - From DESIGN.md cleanup_tunnel"""
from typing import Any
import structlog

from ..tools.tunnel_deleter import get_tunnel_deleter

logger = structlog.get_logger(__name__)


async def cleanup_tunnel_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Delete protection tunnel, release BSID.
    From DESIGN.md: cleanup_tunnel deletes protection tunnel, releases BSID.
    """
    incident_id = state.get("incident_id")
    protection_tunnel_id = state.get("protection_tunnel_id")

    logger.info(
        "Cleaning up protection tunnel",
        incident_id=incident_id,
        protection_tunnel_id=protection_tunnel_id,
    )

    if not protection_tunnel_id:
        logger.warning("No protection tunnel to cleanup", incident_id=incident_id)
        return {
            "tunnel_deleted": True,
            "stage": "cleanup_tunnel",
            "status": "completed",
        }

    try:
        tunnel_deleter = get_tunnel_deleter()

        # Determine tunnel type from ID (sr-policy-xxx or rsvp-te-xxx)
        if protection_tunnel_id.startswith("rsvp-te"):
            tunnel_type = "rsvp-te"
        else:
            tunnel_type = "sr-policy"

        result = await tunnel_deleter.delete_tunnel(
            tunnel_id=protection_tunnel_id,
            tunnel_type=tunnel_type,
        )

        if result.success:
            logger.info(
                "Protection tunnel deleted",
                incident_id=incident_id,
                protection_tunnel_id=protection_tunnel_id,
                bsid_released=result.bsid_released,
            )
            return {
                "tunnel_deleted": True,
                "bsid_released": result.bsid_released,
                "stage": "cleanup_tunnel",
                "status": "completed",
            }
        else:
            logger.error(
                "Failed to delete protection tunnel",
                incident_id=incident_id,
                protection_tunnel_id=protection_tunnel_id,
            )
            return {
                "tunnel_deleted": False,
                "stage": "cleanup_tunnel",
                "error": "Tunnel deletion failed",
            }

    except Exception as e:
        logger.error(
            "Tunnel cleanup error",
            error=str(e),
            incident_id=incident_id,
        )
        return {
            "tunnel_deleted": False,
            "stage": "cleanup_tunnel",
            "error": f"Cleanup error: {str(e)}",
        }
