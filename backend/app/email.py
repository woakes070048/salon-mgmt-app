import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any, Union

import httpx

if TYPE_CHECKING:
    from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_address: str


@dataclass
class ResendApiConfig:
    api_key: str
    from_address: str


AnyEmailConfig = Union[SmtpConfig, ResendApiConfig]


def email_cfg_from_row(row: Any) -> AnyEmailConfig:
    """Build the right config object from a TenantEmailConfig ORM row."""
    if getattr(row, "send_mode", "smtp") == "resend_api":
        return ResendApiConfig(
            api_key=row.resend_api_key or "",
            from_address=row.from_address,
        )
    return SmtpConfig(
        host=row.smtp_host or "",
        port=row.smtp_port or 587,
        username=row.smtp_username or "",
        password=row.smtp_password or "",
        use_tls=row.smtp_use_tls if row.smtp_use_tls is not None else True,
        from_address=row.from_address,
    )


def _send_sync(cfg: SmtpConfig, to: str, subject: str, html: str, reply_to_message_id: str | None = None) -> None:
    if not cfg.host:
        raise RuntimeError("SMTP host is not configured — fill in all fields and click Save first")
    if not cfg.username:
        raise RuntimeError("SMTP username is not configured")
    if not cfg.password:
        raise RuntimeError("SMTP password is not configured")
    if not cfg.from_address:
        raise RuntimeError("From address is not configured")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.from_address
    msg["To"] = to
    if reply_to_message_id:
        mid = reply_to_message_id if reply_to_message_id.startswith("<") else f"<{reply_to_message_id}>"
        msg["In-Reply-To"] = mid
        msg["References"] = mid
    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    try:
        if cfg.use_tls:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.login(cfg.username, cfg.password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP_SSL(cfg.host, cfg.port, context=context, timeout=15) as smtp:
                smtp.login(cfg.username, cfg.password)
                smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(f"Authentication failed — check username and app password. ({e.smtp_code}: {e.smtp_error.decode()})")
    except smtplib.SMTPServerDisconnected as e:
        raise RuntimeError(f"SMTP connection dropped — try again or check your SMTP settings. ({e})")
    except smtplib.SMTPConnectError as e:
        raise RuntimeError(f"Could not connect to {cfg.host}:{cfg.port}. ({e})")
    except smtplib.SMTPException as e:
        raise RuntimeError(f"SMTP error: {e}")
    except OSError as e:
        raise RuntimeError(f"Connection error to {cfg.host}:{cfg.port} — {e}")


async def _send_via_resend(cfg: ResendApiConfig, to: str, subject: str, html: str, reply_to_message_id: str | None = None) -> None:
    if not cfg.api_key:
        raise RuntimeError("Resend API key is not configured — enter it in Settings → Email")
    if not cfg.from_address:
        raise RuntimeError("From address is not configured")
    payload: dict = {"from": cfg.from_address, "to": [to], "subject": subject, "html": html}
    if reply_to_message_id:
        mid = reply_to_message_id if reply_to_message_id.startswith("<") else f"<{reply_to_message_id}>"
        payload["headers"] = {"In-Reply-To": mid, "References": mid}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={"Authorization": f"Bearer {cfg.api_key}"},
        )
    if resp.status_code not in (200, 201):
        try:
            msg = resp.json().get("message") or resp.text
        except Exception:
            msg = resp.text
        raise RuntimeError(f"Resend API error ({resp.status_code}): {msg}")


async def send_email(
    cfg: AnyEmailConfig,
    to: str,
    subject: str,
    html: str,
    retries: int = 3,
    reply_to_message_id: str | None = None,
) -> None:
    # Dev guard: never send real emails from a dev environment. The dev
    # GCP project is configured with ENVIRONMENT=dev so any accidental
    # send is short-circuited here.
    from app.config import settings as _settings
    if (_settings.environment or "").lower() == "dev":
        logger.info(
            "[dev guard] send_email suppressed — would have sent to=%r subject=%r",
            to, subject,
        )
        return

    if isinstance(cfg, ResendApiConfig):
        await _send_via_resend(cfg, to, subject, html, reply_to_message_id=reply_to_message_id)
        return
    # SMTP path — retry on transient connection drops
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            await asyncio.to_thread(_send_sync, cfg, to, subject, html, reply_to_message_id)
            return
        except RuntimeError as e:
            last_err = e
            if "connection dropped" not in str(e).lower() or attempt == retries - 1:
                raise
            logger.warning("SMTP connection dropped on attempt %d, retrying…", attempt + 1)
            await asyncio.sleep(2)
    if last_err:
        raise last_err


def _cta_button(href: str, label: str, brand_color: str | None) -> str:
    # Brand-aware CTA button. Computed text colour for legibility against the brand.
    from app.email_layout import _readable_text_on, DEFAULT_BRAND  # local to avoid cycles
    bg = brand_color or DEFAULT_BRAND
    fg = _readable_text_on(bg)
    return (
        f'<a href="{href}" '
        f'style="display:inline-block;background:{bg};color:{fg};padding:12px 28px;'
        f'border-radius:4px;text-decoration:none;font-weight:600;letter-spacing:0.04em;">'
        f'{label}</a>'
    )


async def send_welcome_email(cfg: AnyEmailConfig, tenant: "Tenant", to: str, reset_link: str) -> None:
    from app.email_layout import wrap_branded
    salon_name = tenant.name
    cta = _cta_button(reset_link, "Set my password", tenant.brand_color)
    inner = f"""\
<h2 style="margin:0 0 16px 0;font-family:Georgia,'Times New Roman',serif;font-weight:400;">
  Welcome to {salon_name}
</h2>
<p style="margin:0 0 16px 0;">
  Your staff account has been created. Click below to set your password and get started.
</p>
<p style="margin:24px 0;">{cta}</p>
<p style="margin:24px 0 0 0;color:#6b6b6b;font-size:13px;">
  This link expires in 72 hours.
</p>"""
    subject = f"Welcome to {salon_name} — Set your password"
    await send_email(cfg, to, subject, wrap_branded(inner, tenant, subject=subject))


async def send_password_reset_email(cfg: AnyEmailConfig, tenant: "Tenant", to: str, reset_link: str) -> None:
    from app.email_layout import wrap_branded
    salon_name = tenant.name
    cta = _cta_button(reset_link, "Reset my password", tenant.brand_color)
    inner = f"""\
<h2 style="margin:0 0 16px 0;font-family:Georgia,'Times New Roman',serif;font-weight:400;">
  Reset your password
</h2>
<p style="margin:0 0 16px 0;">
  Click below to reset your {salon_name} password.
</p>
<p style="margin:24px 0;">{cta}</p>
<p style="margin:24px 0 0 0;color:#6b6b6b;font-size:13px;">
  This link expires in 72 hours. If you didn't request this, you can ignore it.
</p>"""
    subject = f"Reset your {salon_name} password"
    await send_email(cfg, to, subject, wrap_branded(inner, tenant, subject=subject))
