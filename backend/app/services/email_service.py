import asyncio
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from fastapi import HTTPException, status
from loguru import logger

from app.config import settings


class EmailService:
    """
    Email notification and verification service.
    Handles location verification OTPs and access code recovery.
    Uses standard SMTP if configured, with graceful developer fallback in dev mode.
    """

    @property
    def smtp_host(self) -> str:
        return getattr(settings, "SMTP_HOST", None) or os.getenv("SMTP_HOST", "smtp.gmail.com")

    @property
    def smtp_port(self) -> int:
        return int(getattr(settings, "SMTP_PORT", None) or os.getenv("SMTP_PORT", "587"))

    @property
    def smtp_user(self) -> Optional[str]:
        return getattr(settings, "SMTP_USER", None) or os.getenv("SMTP_USER")

    @property
    def smtp_password(self) -> Optional[str]:
        pwd = getattr(settings, "SMTP_PASSWORD", None) or os.getenv("SMTP_PASSWORD")
        if pwd:
            return pwd.replace(" ", "").strip()
        return None

    @property
    def smtp_from(self) -> str:
        return getattr(settings, "SMTP_FROM", None) or os.getenv("SMTP_FROM", "BYC AI Command Center <buildyourcode.tech@gmail.com>")

    @property
    def smtp_tls(self) -> bool:
        val = getattr(settings, "SMTP_TLS", None)
        if val is not None:
            return bool(val)
        return os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes")

    @property
    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    async def send_verification_email(
        self,
        to_email: str,
        code: str,
        location_name: str,
        festival_name: Optional[str] = None,
        purpose: str = "CREATE_LOCATION",
    ) -> bool:
        """
        Sends verification / recovery email containing Location (and optional Festival) context.
        """
        if purpose == "RESET_ACCESS_CODE":
            subject = f"BYC AI Command Center — Access Code Recovery ({location_name})"
            action_desc = "reset your location access code"
        else:
            subject = f"BYC AI Command Center — Location Verification ({location_name})"
            action_desc = "verify and create the location"

        festival_context = f"\nFestival:\n{festival_name}\n" if festival_name else ""

        body_text = (
            f"BYC AI Command Center\n\n"
            f"Location:\n{location_name}\n"
            f"{festival_context}\n"
            f"Your verification code is:\n\n"
            f"{code}\n\n"
            f"Enter this code in BYC AI Command Center to {action_desc}.\n"
            f"This code will expire in 10 minutes.\n\n"
            f"If you did not request this code, please ignore this email."
        )

        # If SMTP is configured, send via SMTP in a background worker thread
        if self.is_configured:
            try:
                await asyncio.to_thread(self._send_smtp_sync, to_email, subject, body_text)
                logger.info(f"[EmailService] Verification email sent to {to_email} for location '{location_name}'")
                return True
            except Exception as e:
                logger.error(f"[EmailService] Failed to send email via SMTP to {to_email}: {e}")
                if settings.APP_ENV == "production":
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Failed to dispatch verification email. Please check mail server connectivity.",
                    )
                # In development, fall through to dev log fallback

        # If SMTP is not configured:
        if settings.APP_ENV == "production":
            logger.critical(
                f"[SECURITY] Production email service is NOT configured! Cannot send OTP to {to_email}."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Production email service is not configured. Please set SMTP credentials in the server environment.",
            )

        # Development Fallback: clearly log the code for testing
        logger.warning(
            f"\n"
            f"================================================================================\n"
            f"  [DEV ONLY — EMAIL VERIFICATION DISPATCH]\n"
            f"  To:       {to_email}\n"
            f"  Subject:  {subject}\n"
            f"  Location: {location_name}\n"
            f"  OTP Code: >>> {code} <<<\n"
            f"  Valid:    10 minutes\n"
            f"================================================================================"
        )
        return True

    def _send_smtp_sync(self, to_email: str, subject: str, body_text: str):
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_from
        msg["To"] = to_email

        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
            if self.smtp_tls:
                server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.smtp_from, [to_email], msg.as_string())


email_service = EmailService()
