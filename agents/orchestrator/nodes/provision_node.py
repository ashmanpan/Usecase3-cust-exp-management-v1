"""
Provision Node

Call Tunnel Provisioning Agent to create protection tunnel.
From DESIGN.md: provision -> steer | escalate
"""

from typing import Any
import structlog

from ..tools.agent_caller import call_agent
from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)


async def provision_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Provision Node - Call Tunnel Provisioning Agent.

    Actions:
    1. Call Tunnel Provisioning Agent with computed path
    2. If successful, get tunnel_id and binding_sid
    3. If failed, check retry count and escalate if exceeded

    Args:
        state: Current workflow state

    Returns:
        Updated state with provisioned tunnel info
    """
    incident_id = state.get("incident_id")
    alternate_path = state.get("alternate_path", {})
    primary_service = state.get("primary_service", {})
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    logger.info(
        "Running provision node",
        incident_id=incident_id,
        retry_count=retry_count,
    )

    # Determine TE type from path or service
    te_type = alternate_path.get("path_type") or primary_service.get("current_path_type", "sr-mpls")

    # Call Tunnel Provisioning Agent
    provision_result = await call_agent(
        agent_name="tunnel_provisioning",
        task_type="provision_tunnel",
        payload={
            "incident_id": incident_id,
            "service_id": primary_service.get("service_id"),
            "te_type": te_type,
            "head_end": primary_service.get("source_pe"),
            "end_point": primary_service.get("destination_pe"),
            "computed_path": alternate_path,
            "path_type": "explicit",
        },
        incident_id=incident_id,
        timeout=60.0,
    )

    # Track A2A call
    a2a_tasks = state.get("a2a_tasks_sent", [])
    a2a_tasks.append({
        "agent": "tunnel_provisioning",
        "task_type": "provision_tunnel",
        "success": provision_result.get("success"),
    })

    updates = {
        "current_node": "provision",
        "nodes_executed": state.get("nodes_executed", []) + ["provision"],
        "a2a_tasks_sent": a2a_tasks,
    }

    if provision_result.get("success"):
        result = provision_result.get("result", {})
        provision_success = result.get("success", False)

        updates["a2a_responses"] = {
            **state.get("a2a_responses", {}),
            "tunnel_provisioning": result,
        }

        if provision_success:
            tunnel_id = result.get("tunnel_id")
            binding_sid = result.get("binding_sid")

            updates["tunnel_id"] = tunnel_id
            updates["binding_sid"] = binding_sid
            updates["te_type"] = result.get("te_type", te_type)
            updates["status"] = "steering"

            # Update Redis
            await update_incident(
                incident_id=incident_id,
                updates={
                    "status": "steering",
                    "tunnel_id": tunnel_id,
                    "binding_sid": binding_sid,
                    "te_type": result.get("te_type", te_type),
                },
            )

            logger.info(
                "Tunnel provisioned successfully",
                incident_id=incident_id,
                tunnel_id=tunnel_id,
                binding_sid=binding_sid,
            )
        else:
            # Provision failed, check retry count
            new_retry_count = retry_count + 1
            updates["retry_count"] = new_retry_count
            updates["provision_error"] = result.get("error")

            if new_retry_count >= max_retries:
                logger.error(
                    "Tunnel provision failed, max retries exceeded",
                    incident_id=incident_id,
                    retry_count=new_retry_count,
                )
                updates["status"] = "escalated"
                updates["escalate_reason"] = "tunnel_provision_failed_3x"

                await update_incident(
                    incident_id=incident_id,
                    updates={
                        "status": "escalated",
                        "escalate_reason": "tunnel_provision_failed_3x",
                    },
                )
            else:
                logger.warning(
                    "Tunnel provision failed, will retry",
                    incident_id=incident_id,
                    retry_count=new_retry_count,
                    error=result.get("error"),
                )
                # Stay in provisioning to retry
                updates["status"] = "provisioning"
    else:
        logger.error(
            "Tunnel Provisioning Agent call failed",
            incident_id=incident_id,
            error=provision_result.get("error"),
        )
        updates["error_message"] = provision_result.get("error")

        # Increment retry count
        new_retry_count = retry_count + 1
        updates["retry_count"] = new_retry_count

        if new_retry_count >= max_retries:
            updates["status"] = "escalated"
            updates["escalate_reason"] = "tunnel_provision_failed_3x"
        else:
            updates["status"] = "provisioning"

    return updates
