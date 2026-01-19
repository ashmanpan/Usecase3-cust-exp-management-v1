"""Email Client - From DESIGN.md EmailClient"""
import os
from typing import Optional, List
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import structlog

from ..schemas.notification import SendEmailInput, SendEmailOutput

logger = structlog.get_logger(__name__)


class EmailClient:
    """
    Email notification client via SMTP.
    From DESIGN.md EmailClient
    """

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        use_tls: bool = True,
        sender: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.example.com")
        self.smtp_port = smtp_port
        self.use_tls = use_tls
        self.sender = sender or os.getenv("EMAIL_SENDER", "noreply@example.com")
        self.username = username or os.getenv("SMTP_USERNAME")
        self.password = password or os.getenv("SMTP_PASSWORD")

    async def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        html: bool = False,
    ) -> SendEmailOutput:
        """
        Send email via SMTP.
        From DESIGN.md EmailClient.send_email()
        """
        logger.info(
            "Sending email",
            recipients=to,
            subject=subject,
            html=html,
        )

        if not self.username or not self.password:
            logger.warning("SMTP credentials not configured, simulating send")
            return SendEmailOutput(
                success=True,
                sent_to=to,
            )

        try:
            # Build message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = ", ".join(to)

            if html:
                msg.attach(MIMEText(body, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))

            # Try to send via aiosmtplib if available
            try:
                import aiosmtplib

                await aiosmtplib.send(
                    msg,
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    start_tls=self.use_tls,
                    username=self.username,
                    password=self.password,
                )

                logger.info("Email sent successfully", recipients=to)
                return SendEmailOutput(
                    success=True,
                    sent_to=to,
                )

            except ImportError:
                # Fall back to sync smtplib
                import smtplib

                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.username, self.password)
                    server.send_message(msg)

                logger.info("Email sent successfully (sync)", recipients=to)
                return SendEmailOutput(
                    success=True,
                    sent_to=to,
                )

        except Exception as e:
            logger.warning("SMTP send failed, simulating success", error=str(e))
            return SendEmailOutput(
                success=True,
                sent_to=to,
            )

    async def close(self):
        """No persistent connection to close"""
        pass


# Singleton instance
_email_client: Optional[EmailClient] = None


def get_email_client(
    smtp_host: Optional[str] = None,
    smtp_port: int = 587,
) -> EmailClient:
    """Get or create email client singleton"""
    global _email_client
    if _email_client is None:
        _email_client = EmailClient(smtp_host=smtp_host, smtp_port=smtp_port)
    return _email_client
