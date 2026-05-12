import json as _json
import uuid
from datetime import datetime, timezone
from typing import Annotated

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import CurrentUser, StaffUser
from app.email import email_cfg_from_row, send_email
from app.email_layout import wrap_branded
from app.models.appointment import (
    Appointment,
    AppointmentItem,
    AppointmentItemStatus,
    AppointmentRequest,
    AppointmentRequestItem,
    AppointmentRequestStatus,
    AppointmentSource,
    AppointmentStatus,
)
from app.models.client import Client
from app.models.email_config import TenantEmailConfig
from app.models.provider import Provider
from app.models.scheduling import RecommendationLog
from app.models.i18n import ServiceTranslation
from app.models.service import Service
from app.models.tenant import Tenant
from app.models.user import UserRole
from app.reminder_dispatcher import schedule_reminder
from app.request_notification import send_request_notification

router = APIRouter(prefix="/appointment-requests", tags=["appointment-requests"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class RequestItemIn(BaseModel):
    service_name: str
    preferred_provider_name: str
    sequence: int = 1


class AppointmentRequestIn(BaseModel):
    desired_date: str  # YYYY-MM-DD
    desired_time_note: str | None = None
    special_note: str | None = None
    items: list[RequestItemIn]


class RequestItemOut(BaseModel):
    id: str
    sequence: int
    service_name: str
    preferred_provider_name: str
    service_id: str | None = None


class AppointmentRequestOut(BaseModel):
    id: str
    status: str
    source: str
    desired_date: str
    desired_time_note: str | None
    special_note: str | None
    submitted_at: str
    staff_notes: str | None
    items: list[RequestItemOut]
    first_name: str
    last_name: str
    email: str
    phone: str | None
    client_id: str | None
    inbound_raw_body: str | None = None


class RequestReview(BaseModel):
    status: AppointmentRequestStatus
    staff_notes: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _load_request_out(req: AppointmentRequest, db: AsyncSession) -> AppointmentRequestOut:
    items = (
        await db.execute(
            select(AppointmentRequestItem)
            .where(AppointmentRequestItem.request_id == req.id)
            .order_by(AppointmentRequestItem.sequence)
        )
    ).scalars().all()

    # Prefer the direct client FK (set for email-sourced requests), then fall
    # back to resolving via the guest user account (online form submissions).
    client_id: str | None = str(req.client_id) if req.client_id else None
    if not client_id and req.submitted_by_user_id:
        linked_client = (
            await db.execute(
                select(Client).where(
                    Client.user_id == req.submitted_by_user_id,
                    Client.tenant_id == req.tenant_id,
                    Client.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if linked_client:
            client_id = str(linked_client.id)

    # Resolve service names → IDs. Match against both the canonical English name and
    # any stored translations, since the booking form sends whatever the user saw
    # (which may be a translated name if they use the French UI).
    service_names = [i.service_name for i in items]
    service_id_by_name: dict[str, str] = {}
    if service_names:
        svc_rows = (await db.execute(
            select(Service.id, Service.name)
            .where(Service.tenant_id == req.tenant_id, Service.name.in_(service_names))
        )).all()
        service_id_by_name = {r.name: str(r.id) for r in svc_rows}

        # Fill in any names that didn't match via translations
        unresolved = [n for n in service_names if n not in service_id_by_name]
        if unresolved:
            tr_rows = (await db.execute(
                select(Service.id, ServiceTranslation.name)
                .join(ServiceTranslation, ServiceTranslation.service_id == Service.id)
                .where(Service.tenant_id == req.tenant_id, ServiceTranslation.name.in_(unresolved))
            )).all()
            for r in tr_rows:
                service_id_by_name[r.name] = str(r.id)

    return AppointmentRequestOut(
        id=str(req.id),
        status=req.status.value,
        source=req.source.value,
        desired_date=req.desired_date.strftime("%Y-%m-%d"),
        desired_time_note=req.desired_time_note,
        special_note=req.special_note,
        submitted_at=req.submitted_at.isoformat(),
        staff_notes=req.staff_notes,
        first_name=req.first_name,
        last_name=req.last_name,
        email=req.email,
        phone=req.phone or None,
        client_id=client_id,
        inbound_raw_body=req.inbound_raw_body,
        items=[
            RequestItemOut(
                id=str(i.id),
                sequence=i.sequence,
                service_name=i.service_name,
                preferred_provider_name=i.preferred_provider_name,
                service_id=service_id_by_name.get(i.service_name),
            )
            for i in items
        ],
    )


async def _get_guest_client(user_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> Client:
    client = (
        await db.execute(
            select(Client).where(
                Client.user_id == user_id,
                Client.tenant_id == tenant_id,
                Client.is_active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No client profile found for this account")
    return client


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("", response_model=AppointmentRequestOut, status_code=status.HTTP_201_CREATED)
async def create_request(
    body: AppointmentRequestIn,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentRequestOut:
    if current_user.role not in (UserRole.guest,):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only guest accounts can submit appointment requests",
        )

    if not body.items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one service required")

    client = await _get_guest_client(current_user.id, current_user.tenant_id, db)

    desired_date = datetime.strptime(body.desired_date, "%Y-%m-%d")

    req = AppointmentRequest(
        tenant_id=current_user.tenant_id,
        submitted_by_user_id=current_user.id,
        first_name=client.first_name,
        last_name=client.last_name,
        email=client.email or current_user.email,
        phone=client.cell_phone or "",
        desired_date=desired_date,
        desired_time_note=body.desired_time_note,
        source=AppointmentSource.online_form,
        special_note=body.special_note,
        waiver_acknowledged=False,
        cancellation_policy_acknowledged=False,
        status=AppointmentRequestStatus.new,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(req)
    await db.flush()

    for item_in in body.items:
        db.add(AppointmentRequestItem(
            tenant_id=current_user.tenant_id,
            request_id=req.id,
            sequence=item_in.sequence,
            service_name=item_in.service_name,
            preferred_provider_name=item_in.preferred_provider_name,
        ))

    await db.commit()
    await db.refresh(req)

    # Best-effort notification to salon staff. Never blocks the response.
    await send_request_notification(db, current_user.tenant_id, req)

    return await _load_request_out(req, db)


@router.get("", response_model=list[AppointmentRequestOut])
async def list_requests(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request_status: str | None = Query(None, alias="status"),
) -> list[AppointmentRequestOut]:
    q = select(AppointmentRequest).where(
        AppointmentRequest.tenant_id == current_user.tenant_id
    )

    if current_user.role == UserRole.guest:
        # Guests only see their own requests
        q = q.where(AppointmentRequest.submitted_by_user_id == current_user.id)
    elif current_user.role not in (UserRole.staff, UserRole.tenant_admin, UserRole.super_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    if request_status:
        try:
            q = q.where(AppointmentRequest.status == AppointmentRequestStatus(request_status))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid status: {request_status}")

    q = q.order_by(AppointmentRequest.submitted_at.desc())
    requests = (await db.execute(q)).scalars().all()
    return [await _load_request_out(r, db) for r in requests]


@router.get("/{request_id}", response_model=AppointmentRequestOut)
async def get_request(
    request_id: str,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentRequestOut:
    row = (
        await db.execute(
            select(AppointmentRequest).where(
                AppointmentRequest.id == uuid.UUID(request_id),
                AppointmentRequest.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return await _load_request_out(row, db)


class ConvertItemIn(BaseModel):
    request_item_id: str
    service_id: str
    provider_id: str
    second_provider_id: str | None = None
    sequence: int = 1
    start_time: datetime
    duration_minutes: int
    price: float
    notes: str | None = None


class ConvertRequestIn(BaseModel):
    client_id: str | None = None  # None = create new client from request data
    appointment_date: str  # YYYY-MM-DD
    notes: str | None = None
    items: list[ConvertItemIn]


class ConvertOut(BaseModel):
    appointment_id: str
    appointment_date: str


@router.post("/{request_id}/convert", response_model=ConvertOut, status_code=status.HTTP_201_CREATED)
async def convert_request(
    request_id: str,
    body: ConvertRequestIn,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConvertOut:
    tid = current_user.tenant_id

    req = (
        await db.execute(
            select(AppointmentRequest).where(
                AppointmentRequest.id == uuid.UUID(request_id),
                AppointmentRequest.tenant_id == tid,
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if req.status == AppointmentRequestStatus.converted:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Request already converted")
    if req.status == AppointmentRequestStatus.declined:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot convert a declined request")
    if not body.items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one item required")

    if body.client_id:
        client = (
            await db.execute(
                select(Client).where(
                    Client.id == uuid.UUID(body.client_id),
                    Client.tenant_id == tid,
                    Client.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if client is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    else:
        client_code = f"C{str(uuid.uuid4())[:8].upper()}"
        client = Client(
            tenant_id=tid,
            client_code=client_code,
            first_name=req.first_name,
            last_name=req.last_name,
            email=req.email,
            cell_phone=req.phone or None,
            country="CA",
            is_vip=False,
            is_active=True,
            no_show_count=0,
            late_cancellation_count=0,
            account_balance=0,
        )
        db.add(client)
        await db.flush()

    appt_date = datetime.strptime(body.appointment_date, "%Y-%m-%d")

    appt = Appointment(
        tenant_id=tid,
        client_id=client.id,
        request_id=req.id,
        created_by_user_id=current_user.id,
        appointment_date=appt_date,
        source=AppointmentSource.online_form,
        status=AppointmentStatus.confirmed,
        notes=body.notes,
    )
    db.add(appt)
    await db.flush()

    for item_in in body.items:
        provider = (
            await db.execute(
                select(Provider).where(
                    Provider.id == uuid.UUID(item_in.provider_id),
                    Provider.tenant_id == tid,
                )
            )
        ).scalar_one_or_none()
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Provider {item_in.provider_id} not found")

        service = (
            await db.execute(
                select(Service).where(
                    Service.id == uuid.UUID(item_in.service_id),
                    Service.tenant_id == tid,
                )
            )
        ).scalar_one_or_none()
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Service {item_in.service_id} not found")

        second_provider_id = None
        if item_in.second_provider_id:
            sp = (
                await db.execute(
                    select(Provider).where(
                        Provider.id == uuid.UUID(item_in.second_provider_id),
                        Provider.tenant_id == tid,
                    )
                )
            ).scalar_one_or_none()
            if sp is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Second provider not found")
            second_provider_id = sp.id

        start_time = item_in.start_time.replace(tzinfo=None)

        appt_item = AppointmentItem(
            tenant_id=tid,
            appointment_id=appt.id,
            service_id=service.id,
            provider_id=provider.id,
            second_provider_id=second_provider_id,
            sequence=item_in.sequence,
            start_time=start_time,
            duration_minutes=item_in.duration_minutes,
            price=item_in.price,
            price_is_locked=True,
            status=AppointmentItemStatus.pending,
            notes=item_in.notes,
        )
        db.add(appt_item)
        await db.flush()

        req_item = (
            await db.execute(
                select(AppointmentRequestItem).where(
                    AppointmentRequestItem.id == uuid.UUID(item_in.request_item_id),
                    AppointmentRequestItem.request_id == req.id,
                )
            )
        ).scalar_one_or_none()
        if req_item:
            req_item.converted_to_item_id = appt_item.id

    req.status = AppointmentRequestStatus.converted
    req.converted_to_appointment_id = appt.id
    req.reviewed_by_user_id = current_user.id
    req.reviewed_at = datetime.now(timezone.utc)

    await db.commit()

    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one_or_none()
    if tenant:
        await schedule_reminder(appt, tenant, db)
        await db.commit()

    return ConvertOut(
        appointment_id=str(appt.id),
        appointment_date=body.appointment_date,
    )


# ── Stored recommendations ────────────────────────────────────────────────────


class RecommendationLogOut(BaseModel):
    recommendations: list[dict]
    created_at: str | None


@router.get("/{request_id}/recommendations", response_model=RecommendationLogOut)
async def get_request_recommendations(
    request_id: str,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecommendationLogOut:
    req = (
        await db.execute(
            select(AppointmentRequest).where(
                AppointmentRequest.id == uuid.UUID(request_id),
                AppointmentRequest.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    log_row = (
        await db.execute(
            select(RecommendationLog)
            .where(
                RecommendationLog.tenant_id == current_user.tenant_id,
                RecommendationLog.request_id == req.id,
            )
            .order_by(RecommendationLog.created_at.desc())
        )
    ).scalar_one_or_none()

    if log_row is None:
        return RecommendationLogOut(recommendations=[], created_at=None)

    return RecommendationLogOut(
        recommendations=log_row.recommendations_json.get("recommendations", []),
        created_at=log_row.created_at.isoformat(),
    )


# ── Reply draft / send ────────────────────────────────────────────────────────


def _minutes_to_hhmm(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def _plain_to_html(text: str) -> str:
    paragraphs = text.strip().split("\n\n")
    return "\n".join(
        f"<p style='margin:0 0 12px 0;'>{para.replace(chr(10), '<br>')}</p>"
        for para in paragraphs
    )


class DraftReplyIn(BaseModel):
    chosen_recommendation_index: int


class DraftReplyOut(BaseModel):
    subject: str
    body: str


class SendReplyIn(BaseModel):
    subject: str
    body: str
    chosen_recommendation_index: int | None = None


@router.post("/{request_id}/draft-reply", response_model=DraftReplyOut)
async def draft_reply(
    request_id: str,
    body: DraftReplyIn,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DraftReplyOut:
    tid = current_user.tenant_id

    req = (
        await db.execute(
            select(AppointmentRequest).where(
                AppointmentRequest.id == uuid.UUID(request_id),
                AppointmentRequest.tenant_id == tid,
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    log_row = (
        await db.execute(
            select(RecommendationLog)
            .where(
                RecommendationLog.tenant_id == tid,
                RecommendationLog.request_id == req.id,
            )
            .order_by(RecommendationLog.created_at.desc())
        )
    ).scalar_one_or_none()
    if log_row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No recommendations found for this request",
        )

    recs = log_row.recommendations_json.get("recommendations", [])
    idx = body.chosen_recommendation_index
    if idx < 0 or idx >= len(recs):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Recommendation index {idx} out of range (have {len(recs)})",
        )

    chosen = recs[idx]
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()

    appt_date = req.desired_date.strftime("%A, %B %-d, %Y")
    slot_lines = [
        f"  • {item['service_name']} — {_minutes_to_hhmm(item['start_minutes'])} to "
        f"{_minutes_to_hhmm(item['end_minutes'])} with {item['provider_name']} ({item['duration_minutes']} min)"
        for item in chosen["items"]
    ]
    slot_description = f"Date: {appt_date}\nServices:\n" + "\n".join(slot_lines)
    if chosen.get("requires_consent"):
        slot_description += "\n(Note: this slot requires stylist schedule adjustment — pending their confirmation)"

    original_message = req.inbound_raw_body or "(request submitted via online form — no original email)"

    system = (
        f"You are a booking assistant for {tenant.name}, a hair salon. "
        "Draft a warm, professional reply email to a client about their appointment request. "
        "Be concise — 3 to 5 short paragraphs. Write in plain text with no markdown formatting. "
        'Output a JSON object with exactly two string keys: "subject" and "body".'
    )
    user_content = (
        f"Client name: {req.first_name} {req.last_name}\n\n"
        f"Their original message:\n{original_message}\n\n"
        f"The slot we are offering:\n{slot_description}\n\n"
        "Draft a reply proposing this slot and asking the client to reply to confirm. "
        f"Sign off with {tenant.name}."
    )

    ai_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await ai_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    try:
        parsed = _json.loads(raw)
        draft_subject = str(parsed["subject"])
        draft_body = str(parsed["body"])
    except Exception:
        draft_subject = f"Re: Your appointment request — {tenant.name}"
        draft_body = raw

    return DraftReplyOut(subject=draft_subject, body=draft_body)


@router.post("/{request_id}/send-reply", status_code=status.HTTP_204_NO_CONTENT)
async def send_reply(
    request_id: str,
    body: SendReplyIn,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    tid = current_user.tenant_id

    req = (
        await db.execute(
            select(AppointmentRequest).where(
                AppointmentRequest.id == uuid.UUID(request_id),
                AppointmentRequest.tenant_id == tid,
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if not req.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request has no client email address",
        )

    cfg_row = (
        await db.execute(
            select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tid)
        )
    ).scalar_one_or_none()
    if cfg_row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email is not configured — add SMTP or Resend settings in Settings → Email",
        )

    tenant = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()

    html = wrap_branded(_plain_to_html(body.body), tenant, subject=body.subject)
    cfg = email_cfg_from_row(cfg_row)

    await send_email(
        cfg,
        to=req.email,
        subject=body.subject,
        html=html,
        reply_to_message_id=req.inbound_message_id,
    )

    if body.chosen_recommendation_index is not None:
        log_row = (
            await db.execute(
                select(RecommendationLog)
                .where(
                    RecommendationLog.tenant_id == tid,
                    RecommendationLog.request_id == req.id,
                )
                .order_by(RecommendationLog.created_at.desc())
            )
        ).scalar_one_or_none()
        if log_row is not None:
            log_row.chosen_index = body.chosen_recommendation_index

    await db.commit()


@router.patch("/{request_id}", response_model=AppointmentRequestOut)
async def review_request(
    request_id: str,
    body: RequestReview,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentRequestOut:
    req = (
        await db.execute(
            select(AppointmentRequest).where(
                AppointmentRequest.id == uuid.UUID(request_id),
                AppointmentRequest.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    req.status = body.status
    if body.staff_notes is not None:
        req.staff_notes = body.staff_notes
    req.reviewed_by_user_id = current_user.id
    req.reviewed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(req)
    return await _load_request_out(req, db)
