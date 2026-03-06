"""
Escalate Node

LLM-based analysis for edge cases and escalation.
From DESIGN.md: escalate -> close | manual intervention
"""

import os
from typing import Any
import structlog

from agent_template.chains.llm_factory import get_llm
from langchain_core.messages import HumanMessage

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident
from ..tools.io_notifier import notify_phase_change, notify_error

# Import notification clients for direct team escalation (GAP 13)
# These live in the notification agent; use lazy import to avoid circular deps
def _get_webex_client():
    from agents.notification.tools.webex_client import get_webex_client
    return get_webex_client()

def _get_email_client():
    from agents.notification.tools.email_client import get_email_client
    return get_email_client()

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


async def _route_escalation_to_teams(state: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    GAP 13: Route escalation to the correct specialist team based on escalation_reason.

    - "no_path_found"          -> Optical team (Webex room + email)
    - "provision_failed" /
      "steer_failed"           -> CNC product team (Webex room)

    Returns:
        (escalation_sent, escalation_channels)
    """
    escalation_reason = state.get("escalation_reason", state.get("escalate_reason", "unknown"))
    incident_id = state.get("incident_id", "unknown")
    degraded_links = state.get("degraded_links", [])
    te_type = state.get("te_type", "unknown")
    affected_vrfs = state.get("affected_vrfs", state.get("affected_services", []))
    premium_services = state.get("premium_affected_services", [])

    escalation_channels: list[str] = []
    escalation_sent = False

    if escalation_reason == "no_path_found":
        # --- Optical team escalation ---
        optical_room = os.getenv("OPTICAL_TEAM_WEBEX_ROOM", "")
        optical_email = os.getenv("OPTICAL_TEAM_EMAIL", "")

        webex_msg = (
            f"\U0001f534 No alternate path found for incident {incident_id}. "
            f"Degraded links: {degraded_links}. "
            f"Optical team action required: check optical path health and consider rerouting. "
            f"Impacted premium VRFs: {affected_vrfs}"
        )

        if optical_room:
            try:
                webex = _get_webex_client()
                result = await webex.send_message(space_id=optical_room, message=webex_msg)
                if result.success:
                    escalation_channels.append("optical_webex")
                    escalation_sent = True
                    logger.info(
                        "Optical team Webex escalation sent",
                        incident_id=incident_id,
                        room=optical_room,
                    )
                else:
                    logger.error(
                        "Optical team Webex send failed",
                        incident_id=incident_id,
                        error=result.error,
                    )
            except Exception:
                logger.exception(
                    "Unexpected error sending optical Webex escalation",
                    incident_id=incident_id,
                )
        else:
            logger.warning(
                "Escalation Webex room not configured",
                team="optical",
                env_var="OPTICAL_TEAM_WEBEX_ROOM",
                incident_id=incident_id,
            )
            logger.info(
                "Optical escalation details (Webex skipped)",
                incident_id=incident_id,
                escalation_reason=escalation_reason,
                degraded_links=degraded_links,
                affected_vrfs=affected_vrfs,
            )

        if optical_email:
            try:
                email = _get_email_client()
                email_result = await email.send_email(
                    to=[optical_email],
                    subject=f"[ACTION REQUIRED] No alternate path for incident {incident_id}",
                    body=(
                        f"No alternate path found for incident {incident_id}.\n\n"
                        f"Degraded links: {degraded_links}\n"
                        f"Impacted premium VRFs: {affected_vrfs}\n"
                        f"Premium affected services: {premium_services}\n\n"
                        f"Please check optical path health and consider rerouting."
                    ),
                )
                if email_result.success:
                    escalation_channels.append("email")
                    escalation_sent = True
                    logger.info(
                        "Optical team email escalation sent",
                        incident_id=incident_id,
                        email=optical_email,
                    )
                else:
                    logger.error(
                        "Optical team email send failed",
                        incident_id=incident_id,
                        error=email_result.error,
                    )
            except Exception:
                logger.exception(
                    "Unexpected error sending optical email escalation",
                    incident_id=incident_id,
                )
        else:
            logger.warning(
                "Optical team email not configured",
                env_var="OPTICAL_TEAM_EMAIL",
                incident_id=incident_id,
            )

    elif escalation_reason in ("provision_failed", "steer_failed"):
        # --- CNC product team escalation ---
        cnc_room = os.getenv("CNC_TEAM_WEBEX_ROOM", "")

        webex_msg = (
            f"\u26a0\ufe0f CNC API issue for incident {incident_id}. "
            f"Reason: {escalation_reason}. "
            f"Please check CNC/NSO tunnel provisioning. "
            f"Incident details: degraded={degraded_links}, te_type={te_type}"
        )

        if cnc_room:
            try:
                webex = _get_webex_client()
                result = await webex.send_message(space_id=cnc_room, message=webex_msg)
                if result.success:
                    escalation_channels.append("cnc_webex")
                    escalation_sent = True
                    logger.info(
                        "CNC product team Webex escalation sent",
                        incident_id=incident_id,
                        room=cnc_room,
                        escalation_reason=escalation_reason,
                    )
                else:
                    logger.error(
                        "CNC product team Webex send failed",
                        incident_id=incident_id,
                        error=result.error,
                    )
            except Exception:
                logger.exception(
                    "Unexpected error sending CNC Webex escalation",
                    incident_id=incident_id,
                )
        else:
            logger.warning(
                "Escalation Webex room not configured",
                team="cnc_product",
                env_var="CNC_TEAM_WEBEX_ROOM",
                incident_id=incident_id,
            )
            logger.info(
                "CNC escalation details (Webex skipped)",
                incident_id=incident_id,
                escalation_reason=escalation_reason,
                degraded_links=degraded_links,
                te_type=te_type,
            )

    else:
        logger.info(
            "No specialist team routing for escalation_reason",
            incident_id=incident_id,
            escalation_reason=escalation_reason,
        )

    return escalation_sent, escalation_channels


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

    # Notify IO Agent about escalation
    await notify_phase_change(
        incident_id=incident_id,
        status="escalated",
        message=f"Incident escalated: {escalate_reason}",
        details={"escalate_reason": escalate_reason, "error_message": error_message},
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

    # GAP 13: Route escalation to optical team or CNC product team
    escalation_sent, escalation_channels = await _route_escalation_to_teams(state)

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
        # GAP 13: specialist team escalation tracking
        "escalation_sent": escalation_sent,
        "escalation_channels": escalation_channels,
    }
