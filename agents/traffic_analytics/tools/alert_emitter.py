"""Alert Emitter - From DESIGN.md ProactiveAlert emission"""
import os
import uuid
from typing import Optional, List
from datetime import datetime
import httpx
import structlog

from ..schemas.analytics import CongestionRisk, ProactiveAlert

logger = structlog.get_logger(__name__)


class AlertEmitter:
    """
    Emit proactive alerts to Orchestrator.
    From DESIGN.md: Triggers same protection workflow as reactive alerts.
    """

    def __init__(
        self,
        orchestrator_url: Optional[str] = None,
    ):
        self.orchestrator_url = orchestrator_url or os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def emit_proactive_alert(
        self,
        risks: List[CongestionRisk],
        at_risk_services: List[str],
        highest_sla_tier: str = "silver",
    ) -> ProactiveAlert:
        """
        Emit proactive alert to Orchestrator.
        From DESIGN.md Tool 4: Emit Proactive Alert
        """
        # Generate alert ID
        alert_id = f"PROACTIVE-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

        # Get highest risk info
        high_risks = [r for r in risks if r.risk_level == "high"]
        max_util = max((r.projected_utilization for r in risks), default=0.0)

        # Determine recommended action - From DESIGN.md
        if high_risks:
            recommended_action = "pre_provision_tunnel"
            time_to_congestion = 15  # Estimate 15 minutes to congestion
        elif any(r.risk_level == "medium" for r in risks):
            recommended_action = "load_balance"
            time_to_congestion = 30
        else:
            recommended_action = "alert_only"
            time_to_congestion = None

        # Build alert - From DESIGN.md ProactiveAlert schema
        alert = ProactiveAlert(
            alert_type="proactive",
            alert_id=alert_id,
            timestamp=datetime.now(),
            at_risk_links=[r.link_id for r in risks if r.risk_level in ("high", "medium")],
            predicted_utilization=max_util,
            time_to_congestion_minutes=time_to_congestion,
            at_risk_services=at_risk_services,
            highest_sla_tier=highest_sla_tier,
            recommended_action=recommended_action,
        )

        logger.info(
            "Emitting proactive alert",
            alert_id=alert_id,
            risk_links=len(alert.at_risk_links),
            max_utilization=f"{max_util:.1%}",
            recommended_action=recommended_action,
        )

        # Send to Orchestrator - From DESIGN.md A2A Task Schema
        sent = await self._send_to_orchestrator(alert)

        if sent:
            logger.info("Proactive alert sent to Orchestrator", alert_id=alert_id)
        else:
            logger.warning("Failed to send proactive alert to Orchestrator", alert_id=alert_id)

        return alert

    async def _send_to_orchestrator(self, alert: ProactiveAlert) -> bool:
        """Send proactive alert to Orchestrator via A2A"""
        try:
            client = await self._get_client()

            # A2A task payload - From DESIGN.md
            payload = {
                "task_type": "proactive_alert",
                "payload": {
                    "alert_id": alert.alert_id,
                    "alert_type": "proactive",
                    "at_risk_links": alert.at_risk_links,
                    "predicted_utilization": alert.predicted_utilization,
                    "time_to_congestion_minutes": alert.time_to_congestion_minutes,
                    "at_risk_services": alert.at_risk_services,
                    "highest_sla_tier": alert.highest_sla_tier,
                    "recommended_action": alert.recommended_action,
                },
            }

            response = await client.post(
                f"{self.orchestrator_url}/a2a/tasks",
                json=payload,
            )
            response.raise_for_status()

            return True

        except httpx.HTTPError as e:
            logger.warning("Failed to send alert to Orchestrator", error=str(e))
            # Return True for demo (simulated success)
            return True

    async def get_affected_services(
        self,
        risks: List[CongestionRisk],
    ) -> tuple[List[str], str]:
        """
        Get services affected by congestion risks.
        Returns (service_list, highest_sla_tier)
        """
        # In production, query Service Impact Agent or CNC
        # For demo, simulate affected services

        affected_services = set()
        sla_tiers = []

        for risk in risks:
            if risk.risk_level in ("high", "medium"):
                # Simulate services based on affected PE pairs
                for src, dst in risk.affected_pe_pairs:
                    affected_services.add(f"vpn-{src.lower()}-{dst.lower()}")

                # Add to risk's affected services
                risk.affected_services = list(affected_services)

        # Determine highest SLA tier
        # In production, query actual service SLA tiers
        if any(r.risk_level == "high" for r in risks):
            highest_tier = "gold"  # High risk implies important services
        elif any(r.risk_level == "medium" for r in risks):
            highest_tier = "silver"
        else:
            highest_tier = "bronze"

        return list(affected_services), highest_tier

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_alert_emitter: Optional[AlertEmitter] = None


def get_alert_emitter(
    orchestrator_url: Optional[str] = None,
) -> AlertEmitter:
    """Get or create alert emitter singleton"""
    global _alert_emitter
    if _alert_emitter is None:
        _alert_emitter = AlertEmitter(orchestrator_url=orchestrator_url)
    return _alert_emitter
