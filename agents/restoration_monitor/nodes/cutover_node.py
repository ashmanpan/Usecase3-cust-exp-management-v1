"""Cutover Traffic Node - From DESIGN.md cutover_traffic"""
from typing import Any
from datetime import datetime
import structlog

from ..tools.cutover import get_cutover_manager
from ..tools.pca_client import get_pca_client

logger = structlog.get_logger(__name__)


async def cutover_traffic_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Execute immediate or gradual cutover.
    From DESIGN.md: cutover_traffic executes immediate or gradual cutover.
    """
    incident_id = state.get("incident_id")
    protection_tunnel_id = state.get("protection_tunnel_id")
    original_path_source = state.get("original_path_source")
    original_path_dest = state.get("original_path_dest")
    cutover_mode = state.get("cutover_mode", "immediate")
    sla_tier = state.get("sla_tier", "silver")

    # Construct original path ID
    original_path_id = f"{original_path_source}-{original_path_dest}"

    logger.info(
        "Executing traffic cutover",
        incident_id=incident_id,
        cutover_mode=cutover_mode,
        protection_tunnel_id=protection_tunnel_id,
    )

    try:
        cutover_manager = get_cutover_manager()

        if cutover_mode == "immediate":
            # Immediate cutover - 100% to original
            result = await cutover_manager.execute_immediate_cutover(
                incident_id=incident_id,
                protection_tunnel_id=protection_tunnel_id,
                original_path_id=original_path_id,
            )

            if result.success:
                logger.info(
                    "Immediate cutover completed",
                    incident_id=incident_id,
                )
                return {
                    "cutover_started": True,
                    "cutover_complete": True,
                    "current_cutover_stage": 3,  # Final stage
                    "cutover_stages_completed": [
                        {"stage": 3, "protection": 0, "original": 100}
                    ],
                    "stage": "cutover_traffic",
                    "status": "cleanup",
                }
            else:
                logger.error(
                    "Immediate cutover failed",
                    incident_id=incident_id,
                    message=result.message,
                )
                return {
                    "cutover_started": True,
                    "cutover_complete": False,
                    "stage": "cutover_traffic",
                    "error": f"Cutover failed: {result.message}",
                }

        else:
            # Gradual cutover - staged ECMP weight migration
            pca_client = get_pca_client()

            async def verify_sla():
                """SLA verification callback for gradual cutover"""
                result = await pca_client.get_path_sla(
                    path_endpoints=(original_path_source, original_path_dest),
                    sla_tier=sla_tier,
                )
                return result.meets_sla

            success, stages = await cutover_manager.execute_gradual_cutover(
                incident_id=incident_id,
                protection_tunnel_id=protection_tunnel_id,
                original_path_id=original_path_id,
                verify_sla_func=verify_sla,
            )

            stages_completed = [
                {
                    "stage": s.stage_index,
                    "protection": s.protection_weight,
                    "original": s.original_weight,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in stages
            ]

            if success:
                logger.info(
                    "Gradual cutover completed",
                    incident_id=incident_id,
                    stages_completed=len(stages),
                )
                return {
                    "cutover_started": True,
                    "cutover_complete": True,
                    "current_cutover_stage": len(stages) - 1,
                    "cutover_stages_completed": stages_completed,
                    "stage": "cutover_traffic",
                    "status": "cleanup",
                }
            else:
                logger.warning(
                    "Gradual cutover incomplete - SLA degraded",
                    incident_id=incident_id,
                    stages_completed=len(stages),
                )
                return {
                    "cutover_started": True,
                    "cutover_complete": False,
                    "current_cutover_stage": len(stages) - 1 if stages else 0,
                    "cutover_stages_completed": stages_completed,
                    "stability_verified": False,  # Go back to verification
                    "stage": "cutover_traffic",
                    "status": "verifying",
                }

    except Exception as e:
        logger.error(
            "Cutover execution failed",
            error=str(e),
            incident_id=incident_id,
        )
        return {
            "cutover_started": True,
            "cutover_complete": False,
            "stage": "cutover_traffic",
            "error": f"Cutover execution error: {str(e)}",
        }
