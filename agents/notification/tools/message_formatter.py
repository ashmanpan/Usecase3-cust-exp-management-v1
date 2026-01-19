"""Message Formatter - From DESIGN.md NOTIFICATION_TEMPLATES"""
from typing import Optional, Any
from datetime import datetime
import structlog

from ..schemas.notification import MessageTemplate

logger = structlog.get_logger(__name__)

# Notification templates - From DESIGN.md
NOTIFICATION_TEMPLATES = {
    "incident_detected": {
        "subject": "[{severity}] SLA Degradation Detected - {incident_id}",
        "body": """## Incident: {incident_id}

**Severity:** {severity}
**Time:** {timestamp}

### Affected Links
{degraded_links}

### Affected Services ({service_count} total)
| Service | Customer | SLA Tier |
|---------|----------|----------|
{service_table}

### Status
Protection workflow initiated. Monitoring for alternate path computation.

---
*Automated alert from Customer Experience Management System*
""",
    },
    "protection_active": {
        "subject": "[INFO] Protection Tunnel Active - {incident_id}",
        "body": """## Protection Active: {incident_id}

**Tunnel ID:** {tunnel_id}
**Type:** {te_type}
**BSID:** {binding_sid}

### Protected Services
{protected_services}

Traffic is now flowing via protection path. Monitoring for SLA recovery.
""",
    },
    "restoration_complete": {
        "subject": "[RESOLVED] Service Restored - {incident_id}",
        "body": """## Incident Resolved: {incident_id}

**Duration:** {duration_minutes} minutes
**Cutover Mode:** {cutover_mode}

All affected services have been restored to original paths.
Protection tunnel has been removed.

### Summary
- Services affected: {service_count}
- Protection tunnel: {tunnel_id} (deleted)
- Total protection time: {protection_duration}
""",
    },
    "escalation": {
        "subject": "[ESCALATION] Manual Intervention Required - {incident_id}",
        "body": """## ESCALATION: {incident_id}

**Reason:** {escalation_reason}
**Time:** {timestamp}

### Context
{context}

### Recommended Actions
{recommendations}

**Immediate attention required.**
""",
    },
    "proactive_alert": {
        "subject": "[PROACTIVE] Congestion Risk Detected - {alert_id}",
        "body": """## Proactive Alert: {alert_id}

**Time:** {timestamp}
**Predicted Utilization:** {predicted_utilization}%
**Time to Congestion:** {time_to_congestion} minutes

### At-Risk Links
{at_risk_links}

### At-Risk Services ({service_count} total)
{at_risk_services}

### Recommended Action
{recommended_action}

---
*Proactive alert from Traffic Analytics Agent*
""",
    },
}


class MessageFormatter:
    """
    Format notification messages from templates.
    """

    def __init__(self, templates: dict = None):
        self.templates = templates or NOTIFICATION_TEMPLATES

    def format_message(
        self,
        event_type: str,
        incident_id: str,
        severity: str,
        data: dict[str, Any],
    ) -> MessageTemplate:
        """
        Generate formatted message from template.
        """
        template = self.templates.get(event_type)
        if not template:
            logger.warning(f"Unknown event type: {event_type}, using default")
            template = {
                "subject": f"[{severity.upper()}] {event_type} - {incident_id}",
                "body": f"Event: {event_type}\nIncident: {incident_id}\nData: {data}",
            }

        # Prepare template variables
        vars = {
            "incident_id": incident_id,
            "alert_id": data.get("alert_id", incident_id),
            "severity": severity.upper(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "degraded_links": self._format_list(data.get("degraded_links", [])),
            "at_risk_links": self._format_list(data.get("at_risk_links", [])),
            "service_count": data.get("service_count", len(data.get("affected_services", []))),
            "service_table": self._format_service_table(data.get("affected_services", [])),
            "at_risk_services": self._format_list(data.get("at_risk_services", [])),
            "tunnel_id": data.get("tunnel_id", "N/A"),
            "te_type": data.get("te_type", "SR-MPLS"),
            "binding_sid": data.get("binding_sid", "N/A"),
            "protected_services": self._format_list(data.get("protected_services", [])),
            "duration_minutes": data.get("duration_minutes", 0),
            "cutover_mode": data.get("cutover_mode", "immediate"),
            "protection_duration": data.get("protection_duration", "N/A"),
            "escalation_reason": data.get("escalation_reason", "Unknown"),
            "context": data.get("context", "No additional context"),
            "recommendations": self._format_list(data.get("recommendations", [])),
            "predicted_utilization": f"{data.get('predicted_utilization', 0) * 100:.1f}",
            "time_to_congestion": data.get("time_to_congestion_minutes", "N/A"),
            "recommended_action": data.get("recommended_action", "Monitor"),
        }

        try:
            subject = template["subject"].format(**vars)
            body = template["body"].format(**vars)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            subject = template["subject"]
            body = template["body"]

        logger.info(
            "Message formatted",
            event_type=event_type,
            subject_length=len(subject),
            body_length=len(body),
        )

        return MessageTemplate(
            subject=subject,
            body=body,
        )

    def _format_list(self, items: list) -> str:
        """Format list as bullet points"""
        if not items:
            return "- None"
        return "\n".join(f"- {item}" for item in items)

    def _format_service_table(self, services: list) -> str:
        """Format services as markdown table rows"""
        if not services:
            return "| (none) | - | - |"

        rows = []
        for svc in services[:10]:  # Limit to 10 rows
            if isinstance(svc, dict):
                rows.append(
                    f"| {svc.get('service_id', 'N/A')} | "
                    f"{svc.get('customer', 'N/A')} | "
                    f"{svc.get('sla_tier', 'N/A')} |"
                )
            else:
                rows.append(f"| {svc} | - | - |")

        if len(services) > 10:
            rows.append(f"| ... and {len(services) - 10} more | - | - |")

        return "\n".join(rows)


# Singleton instance
_message_formatter: Optional[MessageFormatter] = None


def get_message_formatter() -> MessageFormatter:
    """Get or create message formatter singleton"""
    global _message_formatter
    if _message_formatter is None:
        _message_formatter = MessageFormatter()
    return _message_formatter
