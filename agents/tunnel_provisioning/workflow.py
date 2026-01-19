"""Tunnel Provisioning Workflow - From DESIGN.md"""
from typing import Any, Optional
import structlog
from langgraph.graph import StateGraph, START, END
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from agent_template.workflow import BaseWorkflow
from agent_template.tools.mcp_client import MCPToolClient
from agent_template.tools.a2a_client import A2AClient
from .schemas.state import TunnelProvisioningState
from .nodes import (detect_te_type_node, build_payload_node, create_tunnel_node, verify_tunnel_node,
                    steer_traffic_node, return_success_node, check_creation_success, check_tunnel_verified, check_can_retry)

logger = structlog.get_logger(__name__)

class TunnelProvisioningWorkflow(BaseWorkflow):
    """Tunnel Provisioning Workflow - From DESIGN.md: DETECT_TE -> BUILD -> CREATE -> VERIFY -> STEER -> RETURN"""

    def __init__(self, agent_name: str = "tunnel_provisioning", agent_version: str = "1.0.0",
                 mcp_client: Optional[MCPToolClient] = None, a2a_client: Optional[A2AClient] = None,
                 max_iterations: int = 5, stage_tools: dict[str, list[str]] = None):
        super().__init__(agent_name, agent_version, mcp_client, a2a_client, max_iterations, stage_tools)

    def get_state_class(self) -> type:
        return TunnelProvisioningState

    def get_initial_state(self, task_id: str, task_type: str, incident_id: Optional[str] = None,
                          payload: dict[str, Any] = None, correlation_id: Optional[str] = None) -> dict[str, Any]:
        base = super().get_initial_state(task_id, task_type, incident_id, payload, correlation_id)
        payload = payload or {}
        return {**base, "service_id": payload.get("service_id"), "head_end": payload.get("head_end"),
                "end_point": payload.get("end_point"), "computed_path": payload.get("computed_path", {}),
                "path_type": payload.get("path_type", "explicit"), "requested_te_type": payload.get("te_type"),
                "retry_count": 0, "creation_success": False, "tunnel_verified": False, "traffic_steered": False}

    def build_graph(self, graph: StateGraph) -> None:
        graph.add_node("detect_te_type", detect_te_type_node)
        graph.add_node("build_payload", build_payload_node)
        graph.add_node("create_tunnel", create_tunnel_node)
        graph.add_node("verify_tunnel", verify_tunnel_node)
        graph.add_node("steer_traffic", steer_traffic_node)
        graph.add_node("return_success", return_success_node)

        graph.add_edge(START, "detect_te_type")
        graph.add_edge("detect_te_type", "build_payload")
        graph.add_edge("build_payload", "create_tunnel")
        graph.add_conditional_edges("create_tunnel", check_creation_success, {"verify": "verify_tunnel", "retry": "return_success"})
        graph.add_conditional_edges("verify_tunnel", check_tunnel_verified, {"steer": "steer_traffic", "retry": "return_success"})
        graph.add_edge("steer_traffic", "return_success")
        graph.add_edge("return_success", END)
        logger.info("Tunnel Provisioning workflow graph built")
