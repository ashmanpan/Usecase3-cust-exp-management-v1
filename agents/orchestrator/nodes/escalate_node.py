"""
Escalate Node

LLM-based analysis for edge cases and escalation.
From DESIGN.md: escalate -> close | manual intervention
"""

from typing import Any
import structlog

from agent_template.chains.llm_factory import get_llm
from langchain_core.messages import HumanMessage

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)

# LLM triggers from DESIGN.md
LLM_TRIGGERS = [
    "no_alternate_path",
    "cascading_failure",
    "tunnel_provision_failed_3x",
    "conflicting_constraints",
    "unknown_te_type",
]

ESCALATE_PROMPT = """You are a network operations expert analyzing an incident that requires escalation.

Incident ID: {incident_id}
Escalation Reason: {escalate_reason}

Current State:
- Degraded Links: {degraded_links}
- Affected Services: {affected_services_count} services
- Severity: {severity}
- Retry Count: {retry_count}

Error Message: {error_message}

Available Options:
1. MANUAL_INTERVENTION - Escalate to NOC team for manual resolution
2. RETRY_DIFFERENT_PATH - Try computing path with relaxed constraints
3. GRACEFUL_DEGRADATION - Accept degraded state, notify customers
4. CLOSE_NO_ACTION - Close incident with no further action

Based on the situation, provide:
1. Your recommended action (one of the options above)
2. Brief reasoning (1-2 sentences)
3. Confidence level (low, medium, high)

Respond in this format:
DECISION: <option>
REASONING: <your reasoning>
CONFIDENCE: <level>
"""


async def escalate_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Escalate Node - LLM-based analysis for edge cases.

    Actions:
    1. Use LLM to analyze the situation
    2. Recommend action based on context
    3. Notify about escalation
    4. Route to close or manual intervention

    Args:
        state: Current workflow state

    Returns:
        Updated state with escalation decision
    """
    incident_id = state.get("incident_id")
    escalate_reason = state.get("escalate_reason", "unknown")
    error_message = state.get("error_message", "")

    logger.info(
        "Running escalate node",
        incident_id=incident_id,
        escalate_reason=escalate_reason,
    )

    # Check if this is an LLM trigger
    use_llm = escalate_reason in LLM_TRIGGERS

    llm_reasoning = None
    recommended_action = "MANUAL_INTERVENTION"
    confidence = "medium"

    if use_llm:
        try:
            llm = get_llm()

            prompt = ESCALATE_PROMPT.format(
                incident_id=incident_id,
                escalate_reason=escalate_reason,
                degraded_links=state.get("degraded_links", []),
                affected_services_count=len(state.get("affected_services", [])),
                severity=state.get("severity", "unknown"),
                retry_count=state.get("retry_count", 0),
                error_message=error_message,
            )

            response = await llm.ainvoke([HumanMessage(content=prompt)])
            response_text = response.content if hasattr(response, "content") else str(response)

            # Parse LLM response
            lines = response_text.strip().split("\n")
            for line in lines:
                if line.startswith("DECISION:"):
                    recommended_action = line.replace("DECISION:", "").strip()
                elif line.startswith("REASONING:"):
                    llm_reasoning = line.replace("REASONING:", "").strip()
                elif line.startswith("CONFIDENCE:"):
                    confidence = line.replace("CONFIDENCE:", "").strip().lower()

            logger.info(
                "LLM escalation analysis complete",
                incident_id=incident_id,
                recommended_action=recommended_action,
                confidence=confidence,
            )

        except Exception as e:
            logger.exception(
                "LLM analysis failed, defaulting to manual intervention",
                incident_id=incident_id,
            )
            llm_reasoning = f"LLM analysis failed: {str(e)}"

    # Notify about escalation
    notify_result = await call_agent(
        agent_name="notification",
        task_type="send_notification",
        payload={
            "incident_id": incident_id,
            "event_type": "incident_escalated",
            "severity": "critical",
            "data": {
                "escalate_reason": escalate_reason,
                "recommended_action": recommended_action,
                "llm_reasoning": llm_reasoning,
                "confidence": confidence,
                "affected_services": len(state.get("affected_services", [])),
            },
        },
        incident_id=incident_id,
        timeout=10.0,
    )

    # Log escalation event
    audit_result = await call_agent(
        agent_name="audit",
        task_type="log_event",
        payload={
            "incident_id": incident_id,
            "event_type": "incident_escalated",
            "data": {
                "escalate_reason": escalate_reason,
                "recommended_action": recommended_action,
                "llm_reasoning": llm_reasoning,
                "confidence": confidence,
            },
            "previous_state": state.get("status"),
            "new_state": "escalated",
        },
        incident_id=incident_id,
        timeout=10.0,
    )

    # Track A2A calls
    a2a_tasks = state.get("a2a_tasks_sent", [])
    a2a_tasks.extend([
        {
            "agent": "notification",
            "task_type": "send_notification",
            "success": notify_result.get("success"),
        },
        {
            "agent": "audit",
            "task_type": "log_event",
            "success": audit_result.get("success"),
        },
    ])

    # Update Redis
    await update_incident(
        incident_id=incident_id,
        updates={
            "status": "escalated",
            "escalate_reason": escalate_reason,
            "recommended_action": recommended_action,
            "llm_reasoning": llm_reasoning,
            "confidence": confidence,
        },
    )

    return {
        "current_node": "escalate",
        "nodes_executed": state.get("nodes_executed", []) + ["escalate"],
        "status": "escalated",
        "escalate_reason": escalate_reason,
        "recommended_action": recommended_action,
        "llm_reasoning": llm_reasoning,
        "confidence": confidence,
        "a2a_tasks_sent": a2a_tasks,
    }
