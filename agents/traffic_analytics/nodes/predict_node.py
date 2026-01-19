"""Predict Congestion Node - From DESIGN.md predict_congestion"""
from typing import Any
import structlog

from ..schemas.analytics import DemandMatrix
from ..tools.congestion_predictor import get_congestion_predictor

logger = structlog.get_logger(__name__)


async def predict_congestion_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze link utilization vs capacity.
    From DESIGN.md: predict_congestion analyzes links for congestion risk.
    """
    task_id = state.get("task_id")
    demand_matrix_dict = state.get("demand_matrix", {})

    logger.info("Predicting congestion", task_id=task_id)

    try:
        # Convert dict back to DemandMatrix
        demand_matrix = DemandMatrix(**demand_matrix_dict)

        predictor = get_congestion_predictor()
        risks = await predictor.predict(demand_matrix)

        # Count risk levels
        high_risk = sum(1 for r in risks if r.risk_level == "high")
        medium_risk = sum(1 for r in risks if r.risk_level == "medium")
        low_risk = sum(1 for r in risks if r.risk_level == "low")
        max_util = max((r.projected_utilization for r in risks), default=0.0)

        logger.info(
            "Congestion prediction complete",
            high_risk_count=high_risk,
            medium_risk_count=medium_risk,
            max_utilization=f"{max_util:.1%}",
        )

        return {
            "congestion_risks": [r.model_dump() for r in risks],
            "high_risk_count": high_risk,
            "medium_risk_count": medium_risk,
            "low_risk_count": low_risk,
            "max_utilization": max_util,
            "prediction_complete": True,
            "stage": "predict_congestion",
            "status": "predicting",
        }

    except Exception as e:
        logger.error("Failed to predict congestion", error=str(e), task_id=task_id)
        return {
            "prediction_complete": False,
            "stage": "predict_congestion",
            "error": f"Congestion prediction failed: {str(e)}",
        }
