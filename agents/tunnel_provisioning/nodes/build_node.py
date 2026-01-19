"""Build Payload Node - From DESIGN.md"""
from typing import Any
from uuid import uuid4
import structlog
from ..tools.bsid_allocator import get_bsid_allocator

logger = structlog.get_logger(__name__)

async def build_payload_node(state: dict[str, Any]) -> dict[str, Any]:
    """Construct CNC API payload for tunnel creation - From DESIGN.md"""
    incident_id = state.get("incident_id")
    head_end = state.get("head_end")
    end_point = state.get("end_point")
    te_type = state.get("detected_te_type", "sr-mpls")
    computed_path = state.get("computed_path", {})
    path_type = state.get("path_type", "explicit")

    logger.info("Building tunnel payload", incident_id=incident_id, te_type=te_type)

    # Allocate BSID
    bsid_allocator = get_bsid_allocator()
    try:
        if te_type in ["sr-mpls", "srv6"]:
            binding_sid = await bsid_allocator.allocate_mpls_bsid(head_end)
        else:
            binding_sid = None
    except Exception as e:
        logger.warning("BSID allocation failed, using default", error=str(e))
        binding_sid = 24001

    # Generate color
    color = int(uuid4().int % 1000) + 100

    # Build payload
    payload = {
        "te_type": te_type,
        "head_end": head_end,
        "end_point": end_point,
        "path_name": f"protection-{incident_id}",
        "color": color,
        "binding_sid": binding_sid,
        "path_type": path_type,
        "optimization_objective": "delay",
        "protected": True,
    }

    if path_type == "explicit" and computed_path.get("segment_sids"):
        payload["segment_sids"] = computed_path.get("segment_sids")
        payload["explicit_hops"] = [{"hop": {"node-ipv4-address": seg}, "step": i+1} for i, seg in enumerate(computed_path.get("segments", []))]

    logger.info("Payload built", incident_id=incident_id, color=color, binding_sid=binding_sid)
    return {
        "current_node": "build_payload",
        "nodes_executed": state.get("nodes_executed", []) + ["build_payload"],
        "tunnel_payload": payload,
        "binding_sid": binding_sid,
        "color": color,
    }
