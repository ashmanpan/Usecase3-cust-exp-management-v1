"""Verify Stability Node - From DESIGN.md verify_stability"""
from typing import Any
from datetime import datetime
import structlog

from ..tools.pca_client import get_pca_client

logger = structlog.get_logger(__name__)


async def verify_stability_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Confirm SLA stable for verification period.
    From DESIGN.md: verify_stability confirms SLA stable.
    Output: Stable/Unstable
    """
    incident_id = state.get("incident_id")
    source = state.get("original_path_source")
    dest = state.get("original_path_dest")
    sla_tier = state.get("sla_tier", "silver")
    stability_checks = state.get("stability_checks", 0)

    logger.info(
        "Verifying SLA stability",
        incident_id=incident_id,
        source=source,
        dest=dest,
        stability_checks=stability_checks + 1,
    )

    try:
        pca_client = get_pca_client()

        # Perform stability verification (3 consecutive checks)
        is_stable = await pca_client.verify_stability(
            path_endpoints=(source, dest),
            sla_tier=sla_tier,
            check_count=3,
        )

        if is_stable:
            logger.info(
                "SLA stability verified",
                incident_id=incident_id,
            )
            return {
                "stability_verified": True,
                "stability_checks": stability_checks + 1,
                "last_stability_check": datetime.now().isoformat(),
                "stage": "verify_stability",
                "status": "cutover",
            }
        else:
            logger.warning(
                "SLA stability not verified - resetting timer",
                incident_id=incident_id,
            )
            return {
                "stability_verified": False,
                "stability_checks": stability_checks + 1,
                "last_stability_check": datetime.now().isoformat(),
                "timer_started": False,  # Reset timer to restart hold
                "timer_expired": False,
                "sla_recovered": False,  # Go back to monitoring
                "stage": "verify_stability",
                "status": "monitoring",
            }

    except Exception as e:
        logger.error(
            "Failed to verify stability",
            error=str(e),
            incident_id=incident_id,
        )
        return {
            "stability_verified": False,
            "stability_checks": stability_checks + 1,
            "stage": "verify_stability",
            "error": f"Stability verification failed: {str(e)}",
        }
