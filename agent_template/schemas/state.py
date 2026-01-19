"""
LangGraph Workflow State Definition

This module defines the TypedDict that flows through all LangGraph nodes.
Customize per agent while maintaining common fields.
"""

from typing import Any, TypedDict, Optional
from datetime import datetime


class WorkflowState(TypedDict, total=False):
    """
    Base workflow state for all agents.

    Extend this class for agent-specific state fields.

    Common fields:
    - Task identification (task_id, incident_id)
    - Input data (input_payload, user_prompt)
    - Execution tracking (iteration_count, current_node)
    - Results (result, error)
    """

    # ============== Task Identification ==============
    task_id: str                          # Unique task identifier (from A2A)
    incident_id: Optional[str]            # Related incident ID (if applicable)
    correlation_id: Optional[str]         # For distributed tracing

    # ============== Input Data ==============
    input_payload: dict[str, Any]         # Raw input from A2A task
    user_prompt: str                      # Natural language query/description

    # ============== Execution Tracking ==============
    iteration_count: int                  # Current iteration (for loops)
    max_iterations: int                   # Maximum allowed iterations
    current_node: str                     # Currently executing node name
    started_at: str                       # ISO timestamp of start
    nodes_executed: list[str]             # List of executed node names

    # ============== Checklist Pattern (from BGP template) ==============
    checklist: list[str]                  # Full checklist of items
    remaining_checklist: list[str]        # Items still to process
    resolved_checklist: list[str]         # Successfully processed items

    # ============== Tool Execution ==============
    raw_result: Any                       # Raw tool execution results
    tool_outputs: list[dict[str, Any]]    # Collected tool outputs
    mcp_tools_used: list[str]             # Names of MCP tools called

    # ============== Analysis ==============
    analysis_result: str                  # LLM analysis of tool outputs
    evaluation: dict[str, Any]            # Evaluation chain results

    # ============== A2A Inter-Agent Communication ==============
    a2a_tasks_sent: list[dict[str, Any]]  # Tasks sent to other agents
    a2a_responses: dict[str, Any]         # Responses from other agents

    # ============== Final Results ==============
    result: dict[str, Any]                # Structured result for A2A response
    final_output: str                     # Human-readable output (report, etc.)
    error: Optional[str]                  # Error message if failed
    status: str                           # "running", "success", "failed"


# ============== Agent-Specific State Extensions ==============
# Use these as examples for extending WorkflowState per agent

class OrchestratorState(WorkflowState, total=False):
    """Extended state for Orchestrator Agent"""
    workflow_phase: str                   # Current workflow phase
    degraded_links: list[str]             # Links with SLA violations
    affected_services: list[dict]         # Services affected by degradation
    alternate_path: Optional[dict]        # Computed alternate path
    tunnel_id: Optional[str]              # Provisioned tunnel ID
    binding_sid: Optional[int]            # Binding SID for SR policy
    sla_recovered: bool                   # Whether original path recovered
    hold_timer_expiry: Optional[str]      # When hold timer expires


class EventCorrelatorState(WorkflowState, total=False):
    """Extended state for Event Correlator Agent"""
    raw_alerts: list[dict]                # Incoming raw alerts
    normalized_alerts: list[dict]         # Normalized alert format
    correlated_events: list[dict]         # Grouped/correlated events
    flap_detection: dict[str, Any]        # Flap detection state per link
    is_flapping: bool                     # Whether link is flapping
    dampen_until: Optional[str]           # Dampen alerts until this time


class PathComputationState(WorkflowState, total=False):
    """Extended state for Path Computation Agent"""
    source_pe: str                        # Source PE router
    destination_pe: str                   # Destination PE router
    constraints: dict[str, Any]           # Path constraints
    avoid_links: list[str]                # Links to avoid
    avoid_nodes: list[str]                # Nodes to avoid
    computed_path: Optional[dict]         # Computed path result
    path_validation: dict[str, Any]       # Validation results


class TunnelProvisioningState(WorkflowState, total=False):
    """Extended state for Tunnel Provisioning Agent"""
    te_type: str                          # rsvp-te, sr-mpls, srv6
    head_end: str                         # Tunnel head-end
    end_point: str                        # Tunnel end-point
    path_segments: list[str]              # Ordered path segments
    segment_sids: list[int]               # SIDs for SR
    tunnel_payload: dict[str, Any]        # CNC API payload
    provision_result: dict[str, Any]      # Provisioning result
    tunnel_status: str                    # up, down, pending


class RestorationMonitorState(WorkflowState, total=False):
    """Extended state for Restoration Monitor Agent"""
    protection_tunnel_id: str             # Active protection tunnel
    original_path: dict[str, Any]         # Original path info
    sla_metrics: dict[str, float]         # Current SLA measurements
    hold_timer_started: Optional[str]     # When hold timer started
    cutover_stage: int                    # Current cutover stage (0-4)
    cutover_weights: dict[str, int]       # ECMP weights


class TrafficAnalyticsState(WorkflowState, total=False):
    """Extended state for Traffic Analytics Agent"""
    telemetry_sources: list[str]          # Active telemetry sources
    raw_telemetry: dict[str, Any]         # Raw telemetry data
    demand_matrix: dict[str, dict]        # PE-to-PE demand matrix
    congestion_risks: list[dict]          # Predicted congestion risks
    proactive_alert: Optional[dict]       # Generated proactive alert
