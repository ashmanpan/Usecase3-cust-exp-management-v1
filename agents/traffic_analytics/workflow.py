"""Traffic Analytics Workflow - From DESIGN.md"""
from typing import Any, Optional
import structlog
from langgraph.graph import StateGraph, START, END
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from agent_template.workflow import BaseWorkflow
from agent_template.tools.mcp_client import MCPToolClient
from agent_template.tools.a2a_client import A2AClient
from .schemas.state import TrafficAnalyticsState
from .nodes import (
    collect_telemetry_node,
    build_matrix_node,
    predict_congestion_node,
    analyze_risk_node,
    emit_proactive_alert_node,
    store_metrics_node,
    warn_node,
    return_analytics_node,
    check_congestion_level,
    check_risk_level,
)

logger = structlog.get_logger(__name__)


class TrafficAnalyticsWorkflow(BaseWorkflow):
    """
    Traffic Analytics Workflow - From DESIGN.md
    Flow: COLLECT_TELEMETRY -> BUILD_MATRIX -> PREDICT_CONGESTION ->
          [< 70%: STORE_METRICS] | [>= 70%: ANALYZE_RISK -> EMIT_ALERT | WARN | LOG]
    """

    def __init__(
        self,
        agent_name: str = "traffic_analytics",
        agent_version: str = "1.0.0",
        mcp_client: Optional[MCPToolClient] = None,
        a2a_client: Optional[A2AClient] = None,
        max_iterations: int = 10,
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
        return TrafficAnalyticsState

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

        return {
            **base,
            # Telemetry collection state
            "telemetry_sources": payload.get("sources", ["sr-pm", "mdt", "netflow"]),
            "telemetry_window_minutes": payload.get("window_minutes", 5),
            "telemetry_collected": False,
            "raw_telemetry": None,
            "collection_time_ms": 0,
            # Demand matrix state
            "demand_matrix": None,
            "pe_count": 0,
            "total_demand_gbps": 0.0,
            "matrix_built": False,
            # Congestion prediction state
            "congestion_risks": [],
            "high_risk_count": 0,
            "medium_risk_count": 0,
            "low_risk_count": 0,
            "max_utilization": 0.0,
            "prediction_complete": False,
            # Risk analysis state
            "risk_level": "low",
            "at_risk_links": [],
            "at_risk_services": [],
            "highest_sla_tier": None,
            "time_to_congestion_minutes": None,
            "recommended_action": None,
            # Alert emission state
            "proactive_alert_emitted": False,
            "alert_id": None,
            "sent_to_orchestrator": False,
            # Metrics storage state
            "metrics_stored": False,
            # Workflow tracking
            "iteration": 0,
            "stage": "init",
            "status": "pending",
            "error": None,
            # Result
            "result": None,
        }

    def build_graph(self, graph: StateGraph) -> None:
        """Build the traffic analytics workflow graph - From DESIGN.md"""

        # Add all nodes
        graph.add_node("collect_telemetry", collect_telemetry_node)
        graph.add_node("build_matrix", build_matrix_node)
        graph.add_node("predict_congestion", predict_congestion_node)
        graph.add_node("analyze_risk", analyze_risk_node)
        graph.add_node("emit_proactive_alert", emit_proactive_alert_node)
        graph.add_node("store_metrics", store_metrics_node)
        graph.add_node("warn", warn_node)
        graph.add_node("return_analytics", return_analytics_node)

        # Entry point
        graph.add_edge(START, "collect_telemetry")

        # Linear flow: collect -> build -> predict
        graph.add_edge("collect_telemetry", "build_matrix")
        graph.add_edge("build_matrix", "predict_congestion")

        # After prediction: branch based on congestion level
        # From DESIGN.md: < 70% -> store, >= 70% -> analyze
        graph.add_conditional_edges(
            "predict_congestion",
            check_congestion_level,
            {"analyze": "analyze_risk", "store": "store_metrics"},
        )

        # After risk analysis: branch based on risk level
        # From DESIGN.md: high -> alert, medium -> warn, low -> log
        graph.add_conditional_edges(
            "analyze_risk",
            check_risk_level,
            {"alert": "emit_proactive_alert", "warn": "warn", "log": "store_metrics"},
        )

        # After alert -> store metrics
        graph.add_edge("emit_proactive_alert", "store_metrics")

        # After warn -> store metrics
        graph.add_edge("warn", "store_metrics")

        # After store -> return
        graph.add_edge("store_metrics", "return_analytics")

        # End
        graph.add_edge("return_analytics", END)

        logger.info("Traffic Analytics workflow graph built")
