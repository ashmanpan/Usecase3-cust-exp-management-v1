"""ServiceNow Client - From DESIGN.md ServiceNowClient"""
import os
from typing import Optional, Literal
import httpx
import structlog

from ..schemas.notification import (
    CreateSNOWIncidentInput,
    CreateSNOWIncidentOutput,
    UpdateSNOWIncidentInput,
    UpdateSNOWIncidentOutput,
)

logger = structlog.get_logger(__name__)

# Severity mapping
SEVERITY_MAP = {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
}


class ServiceNowClient:
    """
    ServiceNow incident management client.
    From DESIGN.md ServiceNowClient
    """

    def __init__(
        self,
        instance_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.instance_url = instance_url or os.getenv("SNOW_INSTANCE_URL", "https://example.service-now.com")
        self.username = username or os.getenv("SNOW_USERNAME")
        self.password = password or os.getenv("SNOW_PASSWORD")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            auth = (self.username, self.password) if self.username and self.password else None
            ca_cert = os.getenv("CA_CERT_PATH")
            verify = ca_cert if ca_cert else True
            self._client = httpx.AsyncClient(
                base_url=self.instance_url,
                timeout=30,
                auth=auth,
                verify=verify,
            )
        return self._client

    async def create_incident(
        self,
        short_description: str,
        description: str,
        severity: Literal["critical", "high", "medium", "low"],
        assignment_group: str,
    ) -> CreateSNOWIncidentOutput:
        """
        Create ServiceNow incident.
        From DESIGN.md ServiceNowClient.create_incident()
        """
        logger.info(
            "Creating ServiceNow incident",
            severity=severity,
            assignment_group=assignment_group,
        )

        if not self.username or not self.password:
            logger.warning("ServiceNow credentials not configured — cannot create incident")
            return CreateSNOWIncidentOutput(
                success=False,
                incident_number=None,
                error="ServiceNow credentials not configured",
            )

        try:
            client = await self._get_client()

            impact = SEVERITY_MAP.get(severity, 3)
            urgency = SEVERITY_MAP.get(severity, 3)

            payload = {
                "short_description": short_description,
                "description": description,
                "impact": impact,
                "urgency": urgency,
                "assignment_group": assignment_group,
                "category": "Network",
                "subcategory": "Traffic Engineering",
            }

            response = await client.post(
                "/api/now/table/incident",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            incident_number = data.get("result", {}).get("number")

            logger.info("ServiceNow incident created", incident_number=incident_number)

            return CreateSNOWIncidentOutput(
                success=True,
                incident_number=incident_number,
            )

        except httpx.HTTPError as e:
            logger.error("ServiceNow API create failed", error=str(e))
            return CreateSNOWIncidentOutput(
                success=False,
                incident_number=None,
                error=f"ServiceNow API error: {e}",
            )

    async def update_incident(
        self,
        incident_number: str,
        work_notes: str,
        state: Optional[int] = None,
    ) -> UpdateSNOWIncidentOutput:
        """
        Update ServiceNow incident.
        From DESIGN.md ServiceNowClient.update_incident()
        """
        logger.info(
            "Updating ServiceNow incident",
            incident_number=incident_number,
            state=state,
        )

        if not self.username or not self.password:
            logger.warning("ServiceNow credentials not configured — cannot update incident")
            return UpdateSNOWIncidentOutput(success=False, error="ServiceNow credentials not configured")

        try:
            client = await self._get_client()

            # First get sys_id from incident number
            query_response = await client.get(
                "/api/now/table/incident",
                params={"sysparm_query": f"number={incident_number}"},
            )
            query_response.raise_for_status()

            results = query_response.json().get("result", [])
            if not results:
                return UpdateSNOWIncidentOutput(
                    success=False,
                    error=f"Incident {incident_number} not found",
                )

            sys_id = results[0].get("sys_id")

            # Update the incident
            payload = {"work_notes": work_notes}
            if state:
                payload["state"] = state

            response = await client.put(
                f"/api/now/table/incident/{sys_id}",
                json=payload,
            )
            response.raise_for_status()

            logger.info("ServiceNow incident updated", incident_number=incident_number)
            return UpdateSNOWIncidentOutput(success=True)

        except httpx.HTTPError as e:
            logger.error("ServiceNow API update failed", error=str(e))
            return UpdateSNOWIncidentOutput(success=False, error=f"ServiceNow API error: {e}")

    async def resolve_incident(
        self,
        incident_number: str,
        resolution_notes: str,
    ) -> UpdateSNOWIncidentOutput:
        """Resolve (close) a ServiceNow incident"""
        return await self.update_incident(
            incident_number=incident_number,
            work_notes=f"Resolved: {resolution_notes}",
            state=6,  # Resolved
        )

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_servicenow_client: Optional[ServiceNowClient] = None


def get_servicenow_client(
    instance_url: Optional[str] = None,
) -> ServiceNowClient:
    """Get or create ServiceNow client singleton"""
    global _servicenow_client
    if _servicenow_client is None:
        _servicenow_client = ServiceNowClient(instance_url=instance_url)
    return _servicenow_client
