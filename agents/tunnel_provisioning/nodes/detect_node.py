"""Detect TE Type Node - From DESIGN.md"""
from typing import Any
import structlog
from ..tools.te_detector import get_te_detector

logger = structlog.get_logger(__name__)

async def detect_te_type_node(state: dict[str, Any]) -> dict[str, Any]:
    """Detect appropriate TE technology based on service config - From DESIGN.md"""
    incident_id = state.get("incident_id")
    requested_te_type = state.get("requested_te_type")
    computed_path = state.get("computed_path", {})

    logger.info("Detecting TE type", incident_id=incident_id)
    detector = get_te_detector()
    te_type = detector.detect(requested_te_type, computed_path)

    logger.info("TE type detected", incident_id=incident_id, te_type=te_type)
    return {
        "current_node": "detect_te_type",
        "nodes_executed": state.get("nodes_executed", []) + ["detect_te_type"],
        "detected_te_type": te_type,
    }
