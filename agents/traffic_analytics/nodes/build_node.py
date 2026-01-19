"""Build Matrix Node - From DESIGN.md build_matrix"""
from typing import Any
import structlog

from ..schemas.telemetry import TelemetryData
from ..tools.demand_matrix_builder import get_demand_matrix_builder

logger = structlog.get_logger(__name__)


async def build_matrix_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compute PE-to-PE traffic demand matrix.
    From DESIGN.md: build_matrix computes demand matrix from telemetry.
    """
    task_id = state.get("task_id")
    raw_telemetry = state.get("raw_telemetry", {})

    logger.info("Building demand matrix", task_id=task_id)

    try:
        # Convert raw telemetry dict back to TelemetryData
        telemetry = TelemetryData(**raw_telemetry)

        builder = get_demand_matrix_builder()
        matrix = builder.build_matrix(telemetry)

        pe_count = matrix.get_pe_count()
        total_demand = matrix.get_total_demand()

        logger.info(
            "Demand matrix built",
            pe_count=pe_count,
            total_demand_gbps=f"{total_demand:.2f}",
        )

        return {
            "demand_matrix": matrix.model_dump(),
            "pe_count": pe_count,
            "total_demand_gbps": total_demand,
            "matrix_built": True,
            "stage": "build_matrix",
            "status": "building",
        }

    except Exception as e:
        logger.error("Failed to build demand matrix", error=str(e), task_id=task_id)
        return {
            "matrix_built": False,
            "stage": "build_matrix",
            "error": f"Matrix build failed: {str(e)}",
        }
