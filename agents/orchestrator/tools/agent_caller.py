"""
Agent Caller Tool

Tool for calling other agents via A2A protocol.
Based on DESIGN.md - Tool 1: Call Agent via A2A
"""

from typing import Any, Optional
import structlog

from agent_template.tools.a2a_client import A2AClient, get_a2a_client

logger = structlog.get_logger(__name__)


class AgentCallerTool:
    """
    Tool for calling other agents via A2A protocol.

    From DESIGN.md:
    - agent_name: event_correlator, service_impact, path_computation, etc.
    - task_type: correlate_alert, assess_impact, compute_path, etc.
    - payload: Task-specific data
    """

    def __init__(self, a2a_client: Optional[A2AClient] = None):
        """
        Initialize agent caller.

        Args:
            a2a_client: A2A client instance (uses singleton if not provided)
        """
        self.client = a2a_client or get_a2a_client()

    async def call(
        self,
        agent_name: str,
        task_type: str,
        payload: dict[str, Any],
        incident_id: Optional[str] = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Call another agent via A2A.

        Args:
            agent_name: Target agent name
            task_type: Type of task to request
            payload: Task payload
            incident_id: Related incident ID
            timeout: Request timeout in seconds

        Returns:
            Dict with success, result, error fields
        """
        logger.info(
            "Calling agent via A2A",
            agent_name=agent_name,
            task_type=task_type,
            incident_id=incident_id,
        )

        try:
            response = await self.client.send_task(
                agent_name=agent_name,
                task_type=task_type,
                payload=payload,
                incident_id=incident_id,
                timeout=timeout,
            )

            # Check response status
            if response.status.state == "completed":
                logger.info(
                    "Agent call successful",
                    agent_name=agent_name,
                    task_type=task_type,
                )
                return {
                    "success": True,
                    "result": response.result,
                    "error": None,
                }
            else:
                logger.warning(
                    "Agent call returned non-completed status",
                    agent_name=agent_name,
                    status=response.status.state,
                )
                return {
                    "success": False,
                    "result": response.result,
                    "error": response.error or response.status.message,
                }

        except Exception as e:
            logger.exception(
                "Agent call failed",
                agent_name=agent_name,
                task_type=task_type,
            )
            return {
                "success": False,
                "result": None,
                "error": str(e),
            }


# Convenience function
async def call_agent(
    agent_name: str,
    task_type: str,
    payload: dict[str, Any],
    incident_id: Optional[str] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Call another agent via A2A (convenience function).

    Args:
        agent_name: Target agent name
        task_type: Type of task to request
        payload: Task payload
        incident_id: Related incident ID
        timeout: Request timeout

    Returns:
        Dict with success, result, error fields
    """
    caller = AgentCallerTool()
    return await caller.call(
        agent_name=agent_name,
        task_type=task_type,
        payload=payload,
        incident_id=incident_id,
        timeout=timeout,
    )
