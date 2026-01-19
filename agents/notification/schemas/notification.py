"""Notification Data Schemas - From DESIGN.md"""
from typing import Optional, List, Literal, Any
from datetime import datetime
from pydantic import BaseModel, Field


class NotificationRequest(BaseModel):
    """Notification request - From DESIGN.md A2A Task Schema"""
    incident_id: str
    event_type: Literal[
        "incident_detected",
        "protection_active",
        "restoration_complete",
        "escalation",
        "proactive_alert"
    ]
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    sla_tier: str = "silver"
    data: dict[str, Any] = Field(default_factory=dict)


class ChannelResult(BaseModel):
    """Result of sending to a channel"""
    channel: str
    success: bool
    message_id: Optional[str] = None
    ticket_number: Optional[str] = None
    recipients: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    sent_at: datetime = Field(default_factory=datetime.now)


class NotificationResponse(BaseModel):
    """Notification response - From DESIGN.md A2A Task Schema"""
    incident_id: str
    event_type: str
    channels_attempted: List[str] = Field(default_factory=list)
    channels_succeeded: List[str] = Field(default_factory=list)
    channels_failed: List[str] = Field(default_factory=list)
    servicenow_ticket: Optional[str] = None
    webex_message_id: Optional[str] = None
    email_recipients: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class MessageTemplate(BaseModel):
    """Message template for notifications"""
    subject: str
    body: str
    html_body: Optional[str] = None


class SendWebexInput(BaseModel):
    """Input for Webex send - From DESIGN.md Tool 1"""
    space_id: str
    message: str
    markdown: bool = True


class SendWebexOutput(BaseModel):
    """Output from Webex send"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class CreateSNOWIncidentInput(BaseModel):
    """Input for ServiceNow incident creation - From DESIGN.md Tool 2"""
    short_description: str
    description: str
    severity: Literal["critical", "high", "medium", "low"]
    assignment_group: str


class CreateSNOWIncidentOutput(BaseModel):
    """Output from ServiceNow incident creation"""
    success: bool
    incident_number: Optional[str] = None
    error: Optional[str] = None


class UpdateSNOWIncidentInput(BaseModel):
    """Input for ServiceNow incident update"""
    incident_number: str
    work_notes: str
    state: Optional[int] = None  # 6=Resolved, 7=Closed


class UpdateSNOWIncidentOutput(BaseModel):
    """Output from ServiceNow incident update"""
    success: bool
    error: Optional[str] = None


class SendEmailInput(BaseModel):
    """Input for email send - From DESIGN.md Tool 3"""
    recipients: List[str]
    subject: str
    body: str
    html: bool = False


class SendEmailOutput(BaseModel):
    """Output from email send"""
    success: bool
    sent_to: List[str] = Field(default_factory=list)
    error: Optional[str] = None
