"""Select Channels Node - From DESIGN.md select_channels"""
from typing import Any
import structlog

logger = structlog.get_logger(__name__)

# SLA tier channel configuration - From DESIGN.md
SLA_TIER_CONFIG = {
    "platinum": {
        "notification_channels": ["webex", "servicenow", "email"],
        "email_recipients": ["noc-critical@example.com", "sre-oncall@example.com"],
        "webex_space": "platinum-alerts",
        "servicenow_assignment": "Network Operations - Critical",
    },
    "gold": {
        "notification_channels": ["webex", "servicenow", "email"],
        "email_recipients": ["noc@example.com"],
        "webex_space": "gold-alerts",
        "servicenow_assignment": "Network Operations",
    },
    "silver": {
        "notification_channels": ["webex", "email"],
        "email_recipients": ["network-alerts@example.com"],
        "webex_space": "silver-alerts",
        "servicenow_assignment": "Network Operations",
    },
    "bronze": {
        "notification_channels": ["email"],
        "email_recipients": ["network-alerts@example.com"],
        "webex_space": "",
        "servicenow_assignment": "",
    },
}


async def select_channels_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Determine channels based on SLA tier.
    From DESIGN.md: select_channels determines channels based on SLA tier and event type.
    """
    sla_tier = state.get("sla_tier", "silver")
    event_type = state.get("event_type", "incident_detected")

    logger.info(
        "Selecting notification channels",
        sla_tier=sla_tier,
        event_type=event_type,
    )

    # Get base channels for SLA tier
    tier_config = SLA_TIER_CONFIG.get(sla_tier, SLA_TIER_CONFIG["silver"])
    base_channels = list(tier_config["notification_channels"])

    # Add ServiceNow for incidents and escalations - From DESIGN.md
    if event_type in ["incident_detected", "escalation"]:
        if "servicenow" not in base_channels:
            base_channels.append("servicenow")

    logger.info(
        "Channels selected",
        channels=base_channels,
        sla_tier=sla_tier,
    )

    return {
        "selected_channels": base_channels,
        "webex_space": tier_config.get("webex_space", ""),
        "servicenow_assignment": tier_config.get("servicenow_assignment", "Network Operations"),
        "email_recipients": tier_config.get("email_recipients", []),
        "stage": "select_channels",
        "status": "selecting",
    }
