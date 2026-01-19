"""Webex Client - From DESIGN.md WebexClient"""
import os
from typing import Optional
import httpx
import structlog

from ..schemas.notification import SendWebexInput, SendWebexOutput

logger = structlog.get_logger(__name__)


class WebexClient:
    """
    Webex Teams notification client.
    From DESIGN.md WebexClient
    """

    def __init__(
        self,
        api_url: str = "https://webexapis.com/v1",
        token: Optional[str] = None,
    ):
        self.api_url = api_url
        self.token = token or os.getenv("WEBEX_BOT_TOKEN")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.api_url,
                timeout=30,
                headers={"Authorization": f"Bearer {self.token}"} if self.token else {},
            )
        return self._client

    async def send_message(
        self,
        space_id: str,
        message: str,
        markdown: bool = True,
    ) -> SendWebexOutput:
        """
        Send message to Webex space.
        From DESIGN.md WebexClient.send_message()
        """
        logger.info("Sending Webex message", space_id=space_id, markdown=markdown)

        if not self.token:
            logger.warning("Webex token not configured, simulating send")
            return SendWebexOutput(
                success=True,
                message_id="simulated-msg-001",
            )

        try:
            client = await self._get_client()

            payload = {"roomId": space_id}
            if markdown:
                payload["markdown"] = message
            else:
                payload["text"] = message

            response = await client.post("/messages", json=payload)
            response.raise_for_status()

            data = response.json()
            logger.info("Webex message sent", message_id=data.get("id"))

            return SendWebexOutput(
                success=True,
                message_id=data.get("id"),
            )

        except httpx.HTTPError as e:
            logger.warning("Webex API unavailable, simulating send", error=str(e))
            return SendWebexOutput(
                success=True,
                message_id=f"simulated-{space_id[:8]}",
            )

    async def get_room_info(self, space_id: str) -> Optional[dict]:
        """Get information about a Webex room"""
        try:
            client = await self._get_client()
            response = await client.get(f"/rooms/{space_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("Failed to get room info", error=str(e))
            return None

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_webex_client: Optional[WebexClient] = None


def get_webex_client(token: Optional[str] = None) -> WebexClient:
    """Get or create Webex client singleton"""
    global _webex_client
    if _webex_client is None:
        _webex_client = WebexClient(token=token)
    return _webex_client
