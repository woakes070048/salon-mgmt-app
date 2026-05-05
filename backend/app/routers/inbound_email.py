"""Inbound email webhook — receives Resend email.received events and converts
them into AppointmentRequest rows via the intent extractor.

Route: POST /webhooks/email/inbound
Auth:  No JWT. HMAC-SHA256 signature validated against Resend svix headers.
       If resend_webhook_secret is empty (dev mode), validation is skipped.

Flow:
  1. Validate signature & timestamp
  2. Match recipient to a tenant via booking_email
  3. Match sender to a client via email
  4. Extract booking intent (Haiku tool-use)
  5. Persist AppointmentRequest + AppointmentRequestItem rows
  6. Optionally run scheduling engine if services + date are resolved
  7. Send staff notification email
  8. Return 200 always (Resend retries on non-2xx)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.appointment import (
    AppointmentRequest,
    AppointmentRequestItem,
    AppointmentRequestStatus,
    AppointmentSource,
)
from app.models.client import Client
from app.models.scheduling import RecommendationLog
from app.models.tenant import Tenant
from app.request_notification import send_request_notification
from app.scheduling.engine import recommend
from app.scheduling.intent import extract_intent
from app.scheduling.resolver import load_provider_list, load_service_catalogue
from app.scheduling.types import EngineRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/email", tags=["webhooks"])

# Resend replay window: reject events older than 5 minutes
_MAX_TIMESTAMP_AGE_SECONDS = 300


# ── Signature validation ──────────────────────────────────────────────────────


def _validate_signature(
    raw_body: bytes,
    svix_id: str | None,
    svix_timestamp: str | None,
    svix_signature: str | None,
) -> bool:
    """Validate Resend's svix-style HMAC-SHA256 webhook signature.

    Returns True if valid (or if resend_webhook_secret is empty — dev mode).
    Returns False if the signature is invalid or the timestamp is too old.
    """
    secret = settings.resend_webhook_secret
    if not secret:
        # Dev mode — skip validation
        return True

    if not svix_id or not svix_timestamp or not svix_signature:
        logger.warning("Inbound email: missing svix headers")
        return False

    # Reject replays
    try:
        ts = int(svix_timestamp)
    except (ValueError, TypeError):
        logger.warning("Inbound email: invalid svix-timestamp %r", svix_timestamp)
        return False

    now = int(time.time())
    if abs(now - ts) > _MAX_TIMESTAMP_AGE_SECONDS:
        logger.warning("Inbound email: svix-timestamp %d is too old (now=%d)", ts, now)
        return False

    # Signed payload: "{id}.{timestamp}.{body}"
    signed_payload = f"{svix_id}.{svix_timestamp}.".encode() + raw_body

    # Resend secrets are base64-encoded after a "whsec_" prefix
    raw_secret = secret
    if raw_secret.startswith("whsec_"):
        raw_secret = raw_secret[len("whsec_"):]
    try:
        secret_bytes = base64.b64decode(raw_secret)
    except Exception:
        secret_bytes = raw_secret.encode()

    expected = hmac.new(secret_bytes, signed_payload, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode()

    # svix-signature may contain multiple comma-separated "v1,<sig>" values
    for part in svix_signature.split(" "):
        part = part.strip()
        if part.startswith("v1,"):
            candidate = part[3:]
            if hmac.compare_digest(candidate, expected_b64):
                return True

    logger.warning("Inbound email: signature mismatch")
    return False


# ── Address parsing helpers ───────────────────────────────────────────────────


def _extract_email_address(raw: str) -> str:
    """Extract bare email address from 'Name <addr>' or 'addr' strings."""
    raw = raw.strip()
    match = re.search(r"<([^>]+)>", raw)
    if match:
        return match.group(1).strip().lower()
    return raw.lower()


def _parse_display_name(raw: str) -> tuple[str, str]:
    """Return (first_name, last_name) from a display name like 'Jane Doe'.

    Falls back to (raw_string, '') if no space found, or ('', '') if empty.
    """
    raw = raw.strip()
    # Strip angle-bracket portion if present
    bracket_match = re.match(r"^(.*?)\s*<[^>]+>$", raw)
    if bracket_match:
        raw = bracket_match.group(1).strip()

    if not raw:
        return ("", "")
    parts = raw.split(None, 1)
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1])


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/inbound")
async def receive_inbound_email(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    svix_id: Annotated[str | None, Header(alias="svix-id")] = None,
    svix_timestamp: Annotated[str | None, Header(alias="svix-timestamp")] = None,
    svix_signature: Annotated[str | None, Header(alias="svix-signature")] = None,
) -> Response:
    """Receive and process an inbound email from Resend.

    Always returns 200 — failures are logged and stored as low-confidence
    requests for staff review. Returning non-2xx would cause Resend to retry.
    """
    raw_body = await request.body()

    # Validate signature
    if not _validate_signature(raw_body, svix_id, svix_timestamp, svix_signature):
        # Return 200 anyway — a 4xx would expose implementation details and
        # Resend would retry. We log the rejection above.
        return Response(
            content=json.dumps({"status": "rejected", "reason": "invalid_signature"}),
            media_type="application/json",
            status_code=200,
        )

    # Parse JSON payload
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Inbound email: could not parse JSON body")
        return Response(
            content=json.dumps({"status": "ignored", "reason": "unparseable_body"}),
            media_type="application/json",
        )

    # We only handle email.received events
    event_type = payload.get("type")
    if event_type != "email.received":
        return Response(
            content=json.dumps({"status": "ignored", "reason": "not_email_received"}),
            media_type="application/json",
        )

    data = payload.get("data", {})
    from_raw: str = data.get("from", "")
    to_list: list[str] = data.get("to", [])
    subject: str = data.get("subject", "")
    body_text: str = data.get("text", "") or ""
    message_id: str = data.get("message_id", "")

    # Use plain text body; fall back to stripping HTML if only html is present
    if not body_text:
        html_body: str = data.get("html", "") or ""
        body_text = re.sub(r"<[^>]+>", " ", html_body)
        body_text = re.sub(r"\s+", " ", body_text).strip()

    from_email = _extract_email_address(from_raw)

    # ── Find tenant by booking_email ──────────────────────────────────────────
    tenants = (await db.execute(select(Tenant).where(Tenant.is_active == True))).scalars().all()  # noqa: E712

    to_emails_lower = [_extract_email_address(addr) for addr in to_list]

    matched_tenant: Tenant | None = None
    for tenant in tenants:
        if not tenant.booking_email:
            continue
        tenant_booking_email = tenant.booking_email.strip().lower()
        if tenant_booking_email in to_emails_lower:
            matched_tenant = tenant
            break

    if matched_tenant is None:
        # Not addressed to any of our booking inboxes — ignore silently
        logger.debug("Inbound email: no tenant matched for to=%s", to_list)
        return Response(
            content=json.dumps({"status": "ignored", "reason": "no_tenant_match"}),
            media_type="application/json",
        )

    tenant_id = matched_tenant.id

    # ── Match sender to client ────────────────────────────────────────────────
    matched_client: Client | None = None
    if from_email:
        matched_client = (
            await db.execute(
                select(Client).where(
                    Client.tenant_id == tenant_id,
                    Client.email == from_email,
                    Client.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()

    # ── Load service catalogue and provider list ──────────────────────────────
    service_catalogue = await load_service_catalogue(db, tenant_id)
    provider_list = await load_provider_list(db, tenant_id)

    # ── Extract intent ────────────────────────────────────────────────────────
    intent = await extract_intent(
        from_address=from_raw,
        subject=subject,
        body=body_text,
        service_catalogue=service_catalogue,
        provider_list=provider_list,
    )

    confidence = intent.confidence

    # ── Derive name fields ────────────────────────────────────────────────────
    if matched_client:
        first_name = matched_client.first_name
        last_name = matched_client.last_name
        phone = matched_client.cell_phone or matched_client.home_phone or matched_client.work_phone or ""
        client_id: uuid.UUID | None = matched_client.id
    else:
        first_name, last_name = _parse_display_name(from_raw)
        phone = ""
        client_id = None

    # ── Desired date ──────────────────────────────────────────────────────────
    if intent.desired_date is not None:
        desired_dt = datetime(
            intent.desired_date.year,
            intent.desired_date.month,
            intent.desired_date.day,
        )
    else:
        # Default: one week from today
        fallback_date = date.today() + timedelta(days=7)
        desired_dt = datetime(fallback_date.year, fallback_date.month, fallback_date.day)

    # ── Build special_note ────────────────────────────────────────────────────
    confidence_tag = f"[Parsed from email, confidence: {confidence:.0%}]"
    if intent.special_note:
        special_note = f"{intent.special_note}\n\n{confidence_tag}"
    else:
        special_note = confidence_tag

    # ── Persist AppointmentRequest ────────────────────────────────────────────
    req = AppointmentRequest(
        tenant_id=tenant_id,
        submitted_by_user_id=None,
        client_id=client_id,
        first_name=first_name or "Unknown",
        last_name=last_name or "",
        email=from_email,
        phone=phone,
        desired_date=desired_dt,
        desired_time_note=intent.desired_time_note,
        source=AppointmentSource.email,
        special_note=special_note,
        waiver_acknowledged=False,
        cancellation_policy_acknowledged=False,
        status=AppointmentRequestStatus.new,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(req)
    await db.flush()  # obtain req.id

    # ── Persist AppointmentRequestItem rows ───────────────────────────────────
    for seq, svc in enumerate(intent.services, start=1):
        db.add(
            AppointmentRequestItem(
                tenant_id=tenant_id,
                request_id=req.id,
                sequence=seq,
                service_name=svc.service_name or "(unknown service)",
                preferred_provider_name=svc.preferred_provider_name or "",
            )
        )

    await db.flush()

    # ── Run scheduling engine (best-effort) ───────────────────────────────────
    resolved_services = [
        (svc.service_id, svc.preferred_provider_id)
        for svc in intent.services
        if svc.service_id is not None
    ]

    if resolved_services and intent.desired_date is not None:
        try:
            engine_request = EngineRequest(
                tenant_id=tenant_id,
                target_date=intent.desired_date,
                services=resolved_services,
            )
            recommendations = await recommend(db, engine_request, top_n=3)

            recs_json = [
                {
                    "items": [
                        {
                            "service_id": str(item.service_id),
                            "service_name": item.service_name,
                            "provider_id": str(item.provider_id),
                            "provider_name": item.provider_name,
                            "start_minutes": item.start_minutes,
                            "end_minutes": item.end_minutes,
                            "duration_minutes": item.duration_minutes,
                        }
                        for item in rec.items
                    ],
                    "score": rec.score,
                    "rationale": rec.rationale,
                    "requires_consent": rec.requires_consent,
                }
                for rec in recommendations
            ]

            log_entry = RecommendationLog(
                tenant_id=tenant_id,
                request_id=req.id,
                email_message_id=message_id or None,
                recommendations_json={"recommendations": recs_json},
            )
            db.add(log_entry)
            await db.flush()

        except Exception:
            logger.warning(
                "Inbound email: scheduling engine failed for request %s (tenant %s)",
                req.id,
                tenant_id,
                exc_info=True,
            )

    # ── Commit everything in one transaction ──────────────────────────────────
    await db.commit()
    await db.refresh(req)

    # ── Send staff notification (best-effort, after commit) ───────────────────
    await send_request_notification(db, tenant_id, req)

    logger.info(
        "Inbound email processed: request_id=%s tenant=%s from=%s confidence=%.0f%%",
        req.id,
        tenant_id,
        from_email,
        confidence * 100,
    )

    return Response(
        content=json.dumps({
            "status": "accepted",
            "request_id": str(req.id),
            "confidence": confidence,
        }),
        media_type="application/json",
    )
