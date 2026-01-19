"""
Dampen Node

Apply exponential backoff for flapping links.
From DESIGN.md: dampen -> detect (after delay)
"""

import asyncio
from typing import Any
from datetime import datetime, timedelta
import structlog

from ..tools.state_manager import update_incident

logger = structlog.get_logger(__name__)

# Dampen durations by retry count (exponential backoff)
DAMPEN_DELAYS = {
    0: 30,   # First dampen: 30 seconds
    1: 60,   # Second: 1 minute
    2: 120,  # Third: 2 minutes
    3: 300,  # Fourth: 5 minutes
    4: 600,  # Fifth+: 10 minutes
}


async def dampen_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Dampen Node - Apply exponential backoff for flapping links.

    Actions:
    1. Calculate dampen duration based on retry count
    2. Wait for dampen period
    3. Route back to detect

    Args:
        state: Current workflow state

    Returns:
        Updated state after dampen period
    """
    incident_id = state.get("incident_id")
    dampen_count = state.get("dampen_count", 0)

    # Calculate dampen duration
    delay_seconds = DAMPEN_DELAYS.get(dampen_count, DAMPEN_DELAYS[4])

    logger.info(
        "Entering dampen state",
        incident_id=incident_id,
        dampen_count=dampen_count,
        delay_seconds=delay_seconds,
    )

    # Update Redis with dampen info
    dampen_until = datetime.utcnow() + timedelta(seconds=delay_seconds)
    await update_incident(
        incident_id=incident_id,
        updates={
            "status": "dampening",
            "dampen_count": dampen_count + 1,
            "dampen_until": dampen_until.isoformat(),
        },
    )

    # Wait for dampen period
    # In production, this might be handled differently (e.g., scheduled task)
    await asyncio.sleep(delay_seconds)

    logger.info(
        "Dampen period complete, returning to detect",
        incident_id=incident_id,
    )

    return {
        "current_node": "dampen",
        "nodes_executed": state.get("nodes_executed", []) + ["dampen"],
        "status": "detecting",
        "dampen_count": dampen_count + 1,
        "dampen_until": None,  # Clear dampen
        "is_flapping": False,  # Reset flapping flag to recheck
    }
