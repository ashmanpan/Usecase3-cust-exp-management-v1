"""Restoration Monitor Workflow - From DESIGN.md"""
from typing import Any, Optional
import asyncio
import structlog
from langgraph.graph import StateGraph, START, END
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from agent_template.workflow import BaseWorkflow
from agent_template.tools.mcp_client import MCPToolClient
from agent_template.tools.a2a_client import A2AClient
from .schemas.state import RestorationMonitorState
from .nodes import (
    poll_sla_node,
    check_recovery_node,
    start_timer_node,
    wait_timer_node,
    verify_stability_node,
    cutover_traffic_node,
    cleanup_tunnel_node,
    return_restored_node,
    check_recovered,
    check_timer_expired,
    check_stable,
    check_cutover_complete,
)

logger = structlog.get_logger(__name__)


async def wait_poll_node(state: dict[str, Any]) -> dict[str, Any]:
    """Wait between poll cycles (30 seconds)"""
    await asyncio.sleep(30)
    return {"iteration": state.get("iteration", 0) + 1}


async def reset_timer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Reset timer state to restart hold timer process"""
    logger.info(
        "Resetting timer state for re-verification",
        incident_id=state.get("incident_id"),
    )
    return {
        "timer_started": False,
        "timer_expired": False,
        "timer_id": None,
        "sla_recovered": False,
        "stability_verified": False,
    }


async def timeout_node(state: dict[str, Any]) -> dict[str, Any]:
    """Handle monitoring timeout"""
    logger.warning(
        "Restoration monitoring timed out",
        incident_id=state.get("incident_id"),
        poll_count=state.get("poll_count", 0),
    )
    return {
        "error": "Monitoring timeout - max poll attempts reached",
        "status": "failed",
    }


class RestorationMonitorWorkflow(BaseWorkflow):
    """
    Restoration Monitor Workflow - From DESIGN.md
    Flow: POLL_SLA -> CHECK_RECOVERY -> START_TIMER -> WAIT_TIMER ->
          VERIFY_STABILITY -> CUTOVER_TRAFFIC -> CLEANUP_TUNNEL -> RETURN_RESTORED
    """

    def __init__(
        self,
        agent_name: str = "restoration_monitor",
        agent_version: str = "1.0.0",
        mcp_client: Optional[MCPToolClient] = None,
        a2a_client: Optional[A2AClient] = None,
        max_iterations: int = 100,
        stage_tools: dict[str, list[str]] = None,
    ):
        super().__init__(
            agent_name,
            agent_version,
            mcp_client,
            a2a_client,
            max_iterations,
            stage_tools,
        )

    def get_state_class(self) -> type:
        return RestorationMonitorState

    def get_initial_state(
        self,
        task_id: str,
        task_type: str,
        incident_id: Optional[str] = None,
        payload: dict[str, Any] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        base = super().get_initial_state(task_id, task_type, incident_id, payload, correlation_id)
        payload = payload or {}

        # Extract original path from payload
        original_path = payload.get("original_path", {})

        return {
            **base,
            # Restoration context from request
            "protection_tunnel_id": payload.get("protection_tunnel_id"),
            "original_path_source": original_path.get("source"),
            "original_path_dest": original_path.get("dest"),
            "sla_tier": payload.get("sla_tier", "silver"),
            "cutover_mode": payload.get("cutover_mode", "immediate"),
            # SLA monitoring state
            "current_metrics": None,
            "sla_recovered": False,
            "recovery_time": None,
            # Hold timer state
            "timer_id": None,
            "timer_started": False,
            "timer_expired": False,
            "timer_cancelled": False,
            # Stability verification
            "stability_checks": 0,
            "stability_verified": False,
            "last_stability_check": None,
            # Cutover state
            "cutover_started": False,
            "cutover_complete": False,
            "current_cutover_stage": 0,
            "cutover_stages_completed": [],
            # Cleanup state
            "tunnel_deleted": False,
            "bsid_released": None,
            # Workflow tracking
            "poll_count": 0,
            "max_poll_attempts": 100,
            "iteration": 0,
            "stage": "init",
            "status": "pending",
            "error": None,
            # Timing
            "protection_start_time": payload.get("protection_start_time"),
            "total_protection_duration_seconds": None,
            # Result
            "result": None,
        }

    def build_graph(self, graph: StateGraph) -> None:
        """Build the restoration monitor workflow graph - From DESIGN.md"""

        # Add all nodes
        graph.add_node("poll_sla", poll_sla_node)
        graph.add_node("check_recovery", check_recovery_node)
        graph.add_node("wait_poll", wait_poll_node)
        graph.add_node("start_timer", start_timer_node)
        graph.add_node("wait_timer", wait_timer_node)
        graph.add_node("verify_stability", verify_stability_node)
        graph.add_node("reset_timer", reset_timer_node)
        graph.add_node("cutover_traffic", cutover_traffic_node)
        graph.add_node("cleanup_tunnel", cleanup_tunnel_node)
        graph.add_node("return_restored", return_restored_node)
        graph.add_node("timeout", timeout_node)

        # Entry point
        graph.add_edge(START, "poll_sla")

        # After poll -> check recovery
        graph.add_edge("poll_sla", "check_recovery")

        # After check recovery -> start timer (if recovered) or wait and poll again
        graph.add_conditional_edges(
            "check_recovery",
            check_recovered,
            {"start_timer": "start_timer", "wait_poll": "wait_poll"},
        )

        # Wait poll -> back to poll
        graph.add_edge("wait_poll", "poll_sla")

        # After start timer -> wait for timer
        graph.add_edge("start_timer", "wait_timer")

        # After wait timer -> verify stability (if expired) or continue waiting or poll (if cancelled)
        graph.add_conditional_edges(
            "wait_timer",
            check_timer_expired,
            {"verify": "verify_stability", "wait_timer": "wait_timer", "poll": "poll_sla"},
        )

        # After verify stability -> cutover (if stable) or reset timer
        graph.add_conditional_edges(
            "verify_stability",
            check_stable,
            {"cutover": "cutover_traffic", "reset_timer": "reset_timer"},
        )

        # After reset timer -> back to poll
        graph.add_edge("reset_timer", "poll_sla")

        # After cutover -> cleanup (if complete) or back to verify
        graph.add_conditional_edges(
            "cutover_traffic",
            check_cutover_complete,
            {"cleanup": "cleanup_tunnel", "verify": "verify_stability"},
        )

        # After cleanup -> return restored
        graph.add_edge("cleanup_tunnel", "return_restored")

        # Timeout -> return restored (with error)
        graph.add_edge("timeout", "return_restored")

        # End
        graph.add_edge("return_restored", END)

        logger.info("Restoration Monitor workflow graph built")
