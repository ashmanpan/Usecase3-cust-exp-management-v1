"""Notification Agent State Schema - From DESIGN.md"""
from typing import TypedDict, Optional, List, Any, Literal


class NotificationState(TypedDict, total=False):
    """
    LangGraph state for Notification workflow.
    From DESIGN.md: SELECT_CHANNELS -> FORMAT_MESSAGE -> SEND_PARALLEL -> LOG_RESULTS
    """
    # Task identification
    task_id: str
    task_type: str
    incident_id: Optional[str]
    correlation_id: Optional[str]

    # Notification request
    event_type: Literal[
        "incident_detected",
        "protection_active",
        "restoration_complete",
        "escalation",
        "proactive_alert"
    ]
    severity: Literal["critical", "high", "medium", "low"]
    sla_tier: str
    notification_data: dict[str, Any]

    # Channel selection state
    selected_channels: List[str]
    webex_space: Optional[str]
    servicenow_assignment: Optional[str]
    email_recipients: List[str]

    # Message formatting state
    message_subject: Optional[str]
    message_body: Optional[str]
    message_formatted: bool

    # Send state per channel
    webex_sent: bool
    webex_message_id: Optional[str]
    servicenow_sent: bool
    servicenow_ticket: Optional[str]
    email_sent: bool
    email_sent_to: List[str]

    # Results
    channels_attempted: List[str]
    channels_succeeded: List[str]
    channels_failed: List[str]
    channel_results: List[dict[str, Any]]

    # Workflow tracking
    iteration: int
    stage: str
    status: Literal["pending", "selecting", "formatting", "sending", "logging", "completed", "failed"]
    error: Optional[str]

    # Result
    result: Optional[dict[str, Any]]
