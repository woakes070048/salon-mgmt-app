import uuid
from datetime import time as dtime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import status as http_status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import AdminUser, StaffUser
from app.i18n import SUPPORTED_LANGUAGES
from app.models.acknowledgement import TenantAcknowledgement
from app.models.printer import TenantPrinterConfig
from app.models.schedule import TenantOperatingHours
from app.models.tenant import Tenant

router = APIRouter(prefix="/settings", tags=["settings"])


VALID_SLOT_MINUTES = {5, 10, 15, 20, 30}
VALID_TIME_FORMATS = {"12h", "24h"}


CONTACT_FIELDS = (
    "address_line1", "address_line2", "city", "region",
    "postal_code", "country", "phone", "hours_summary", "website", "hst_number",
    "booking_inbound_address",
)


class BrandingOut(BaseModel):
    salon_name: str
    logo_url: str | None
    brand_color: str | None
    slot_minutes: int
    time_format: str
    default_language: str
    supported_languages: list[str]
    address_line1: str | None
    address_line2: str | None
    city: str | None
    region: str | None
    postal_code: str | None
    country: str | None
    phone: str | None
    hours_summary: str | None
    website: str | None
    hst_number: str | None
    booking_inbound_address: str | None


class BrandingPatch(BaseModel):
    salon_name: str | None = None
    logo_url: str | None = None
    brand_color: str | None = None
    slot_minutes: int | None = None
    time_format: str | None = None
    default_language: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    phone: str | None = None
    hours_summary: str | None = None
    website: str | None = None
    hst_number: str | None = None
    booking_inbound_address: str | None = None


async def _get_tenant(tenant_id: uuid.UUID, db: AsyncSession) -> Tenant:
    return (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one()


def _branding_out(tenant: Tenant) -> BrandingOut:
    return BrandingOut(
        salon_name=tenant.name,
        logo_url=tenant.logo_url,
        brand_color=tenant.brand_color,
        slot_minutes=tenant.slot_minutes,
        time_format=tenant.time_format,
        default_language=tenant.default_language,
        supported_languages=SUPPORTED_LANGUAGES,
        address_line1=tenant.address_line1,
        address_line2=tenant.address_line2,
        city=tenant.city,
        region=tenant.region,
        postal_code=tenant.postal_code,
        country=tenant.country,
        phone=tenant.phone,
        hours_summary=tenant.hours_summary,
        website=tenant.website,
        hst_number=tenant.hst_number,
        booking_inbound_address=tenant.booking_inbound_address,
    )


@router.get("/branding", response_model=BrandingOut)
async def get_branding(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandingOut:
    tenant = await _get_tenant(current_user.tenant_id, db)
    return _branding_out(tenant)


@router.patch("/branding", response_model=BrandingOut)
async def update_branding(
    body: BrandingPatch,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandingOut:
    tenant = await _get_tenant(current_user.tenant_id, db)
    for field in body.model_fields_set:
        value = getattr(body, field)
        if field == 'salon_name':
            if not value or not value.strip():
                raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail="Salon name cannot be blank")
            tenant.name = value.strip()
        elif field == 'slot_minutes':
            if value not in VALID_SLOT_MINUTES:
                raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail=f"slot_minutes must be one of {sorted(VALID_SLOT_MINUTES)}")
            tenant.slot_minutes = value
        elif field == 'time_format':
            if value not in VALID_TIME_FORMATS:
                raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail="time_format must be '12h' or '24h'")
            tenant.time_format = value
        elif field == 'default_language':
            if value not in SUPPORTED_LANGUAGES:
                raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail=f"default_language must be one of {SUPPORTED_LANGUAGES}")
            tenant.default_language = value
        elif field in CONTACT_FIELDS:
            cleaned = value.strip() if isinstance(value, str) else value
            setattr(tenant, field, cleaned or None)
        else:
            setattr(tenant, field, value or None)
    await db.commit()
    await db.refresh(tenant)
    return _branding_out(tenant)


# ── Operating hours ──────────────────────────────────────────────────────────


class OperatingHoursDay(BaseModel):
    day_of_week: int  # 0=Mon … 6=Sun
    is_open: bool
    open_time: str | None  # "HH:MM"
    close_time: str | None

    @field_validator("day_of_week")
    @classmethod
    def _dow_in_range(cls, v: int) -> int:
        if v < 0 or v > 6:
            raise ValueError("day_of_week must be 0..6")
        return v


class OperatingHoursUpdate(BaseModel):
    days: list[OperatingHoursDay]


def _fmt_time(t: dtime | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def _parse_time(v: str | None) -> dtime | None:
    return dtime.fromisoformat(v) if v else None


@router.get("/operating-hours", response_model=list[OperatingHoursDay])
async def get_operating_hours(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OperatingHoursDay]:
    tid = current_user.tenant_id
    rows = (
        await db.execute(
            select(TenantOperatingHours).where(TenantOperatingHours.tenant_id == tid)
        )
    ).scalars().all()
    by_dow = {r.day_of_week: r for r in rows}
    return [
        OperatingHoursDay(
            day_of_week=dow,
            is_open=by_dow[dow].is_open if dow in by_dow else False,
            open_time=_fmt_time(by_dow[dow].open_time) if dow in by_dow else None,
            close_time=_fmt_time(by_dow[dow].close_time) if dow in by_dow else None,
        )
        for dow in range(7)
    ]


@router.put("/operating-hours", response_model=list[OperatingHoursDay])
async def set_operating_hours(
    body: OperatingHoursUpdate,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OperatingHoursDay]:
    tid = current_user.tenant_id

    seen: set[int] = set()
    for d in body.days:
        if d.day_of_week in seen:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"duplicate day_of_week {d.day_of_week}",
            )
        seen.add(d.day_of_week)
        if d.is_open:
            if not d.open_time or not d.close_time:
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"open_time and close_time required when day {d.day_of_week} is open",
                )
            if _parse_time(d.open_time) >= _parse_time(d.close_time):
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"open_time must be before close_time on day {d.day_of_week}",
                )

    existing = (
        await db.execute(
            select(TenantOperatingHours).where(TenantOperatingHours.tenant_id == tid)
        )
    ).scalars().all()
    by_dow = {r.day_of_week: r for r in existing}

    for d in body.days:
        rec = by_dow.get(d.day_of_week)
        if rec is None:
            rec = TenantOperatingHours(tenant_id=tid, day_of_week=d.day_of_week)
            db.add(rec)
        rec.is_open = d.is_open
        rec.open_time = _parse_time(d.open_time) if d.is_open else None
        rec.close_time = _parse_time(d.close_time) if d.is_open else None

    await db.commit()
    return await get_operating_hours(current_user, db)


# ── Request notifications ────────────────────────────────────────────────────


class RequestNotificationsOut(BaseModel):
    enabled: bool
    recipients: list[str]
    reminder_enabled: bool
    reminder_lead_hours: int
    reminder_send_time: str


class RequestNotificationsPatch(BaseModel):
    enabled: bool | None = None
    recipients: list[str] | None = None
    reminder_enabled: bool | None = None
    reminder_lead_hours: int | None = None
    reminder_send_time: str | None = None


def _split_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [r.strip() for r in raw.split(",") if r.strip()]


def _join_recipients(items: list[str]) -> str | None:
    cleaned = [r.strip() for r in items if r and r.strip()]
    return ",".join(cleaned) if cleaned else None


@router.get("/notifications", response_model=RequestNotificationsOut)
async def get_request_notifications(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RequestNotificationsOut:
    tenant = await _get_tenant(current_user.tenant_id, db)
    return RequestNotificationsOut(
        enabled=tenant.request_notifications_enabled,
        recipients=_split_recipients(tenant.request_notification_recipients),
        reminder_enabled=tenant.reminder_enabled,
        reminder_lead_hours=tenant.reminder_lead_hours,
        reminder_send_time=tenant.reminder_send_time,
    )


@router.patch("/notifications", response_model=RequestNotificationsOut)
async def update_request_notifications(
    body: RequestNotificationsPatch,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RequestNotificationsOut:
    tenant = await _get_tenant(current_user.tenant_id, db)
    if body.enabled is not None:
        tenant.request_notifications_enabled = body.enabled
    if body.recipients is not None:
        # Light shape validation — anything containing "@" is acceptable here;
        # real address validation happens at the SMTP layer.
        for r in body.recipients:
            if "@" not in r:
                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"'{r}' doesn't look like an email address",
                )
        tenant.request_notification_recipients = _join_recipients(body.recipients)
    if body.reminder_enabled is not None:
        tenant.reminder_enabled = body.reminder_enabled
    if body.reminder_lead_hours is not None:
        if body.reminder_lead_hours < 1:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="reminder_lead_hours must be at least 1",
            )
        tenant.reminder_lead_hours = body.reminder_lead_hours
    if body.reminder_send_time is not None:
        import re
        if not re.match(r"^\d{2}:\d{2}$", body.reminder_send_time):
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="reminder_send_time must be HH:MM",
            )
        tenant.reminder_send_time = body.reminder_send_time
    await db.commit()
    await db.refresh(tenant)
    return RequestNotificationsOut(
        enabled=tenant.request_notifications_enabled,
        recipients=_split_recipients(tenant.request_notification_recipients),
        reminder_enabled=tenant.reminder_enabled,
        reminder_lead_hours=tenant.reminder_lead_hours,
        reminder_send_time=tenant.reminder_send_time,
    )


# ── Printer config ────────────────────────────────────────────────────────────


class PrinterConfigOut(BaseModel):
    printer_name: str
    printer_host: str | None
    printer_port: int
    paper_width: int
    auto_print_on_cash: bool
    cash_drawer_enabled: bool
    print_merchant_copy: bool
    receipt_logo_url: str | None


class PrinterConfigPatch(BaseModel):
    printer_name: str | None = None
    printer_host: str | None = None
    printer_port: int | None = None
    paper_width: int | None = None
    auto_print_on_cash: bool | None = None
    cash_drawer_enabled: bool | None = None
    print_merchant_copy: bool | None = None


async def _get_or_create_printer_cfg(tenant_id: uuid.UUID, db: AsyncSession) -> TenantPrinterConfig:
    cfg = (
        await db.execute(select(TenantPrinterConfig).where(TenantPrinterConfig.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if cfg is None:
        cfg = TenantPrinterConfig(tenant_id=tenant_id)
        db.add(cfg)
        await db.flush()
    return cfg


def _printer_out(cfg: TenantPrinterConfig) -> PrinterConfigOut:
    return PrinterConfigOut(
        printer_name=cfg.printer_name,
        printer_host=cfg.printer_host,
        printer_port=cfg.printer_port,
        paper_width=cfg.paper_width,
        auto_print_on_cash=cfg.auto_print_on_cash,
        cash_drawer_enabled=cfg.cash_drawer_enabled,
        print_merchant_copy=cfg.print_merchant_copy,
        receipt_logo_url=cfg.receipt_logo_url,
    )


@router.get("/printer", response_model=PrinterConfigOut)
async def get_printer_config(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterConfigOut:
    cfg = await _get_or_create_printer_cfg(current_user.tenant_id, db)
    await db.commit()
    return _printer_out(cfg)


@router.patch("/printer", response_model=PrinterConfigOut)
async def update_printer_config(
    body: PrinterConfigPatch,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterConfigOut:
    cfg = await _get_or_create_printer_cfg(current_user.tenant_id, db)
    for field in body.model_fields_set:
        value = getattr(body, field)
        if field == "printer_port" and value is not None and not (1 <= value <= 65535):
            raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="printer_port must be 1–65535")
        if field == "paper_width" and value is not None and value not in (58, 80):
            raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="paper_width must be 58 or 80")
        setattr(cfg, field, value)
    await db.commit()
    await db.refresh(cfg)
    return _printer_out(cfg)


@router.post("/printer/logo", response_model=PrinterConfigOut)
async def upload_printer_logo(
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> PrinterConfigOut:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="File must be an image")
    if not settings.assets_gcs_bucket:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Asset storage not configured (ASSETS_GCS_BUCKET)")

    import io

    from google.cloud import storage as gcs

    data = await file.read()
    ext = (file.filename or "logo.png").rsplit(".", 1)[-1].lower()
    blob_name = f"tenants/{current_user.tenant_id}/receipt_logo.{ext}"

    client = gcs.Client()
    bucket = client.bucket(settings.assets_gcs_bucket)
    blob = bucket.blob(blob_name)
    blob.upload_from_file(io.BytesIO(data), content_type=file.content_type)
    blob.make_public()
    logo_url = blob.public_url

    cfg = await _get_or_create_printer_cfg(current_user.tenant_id, db)
    cfg.receipt_logo_url = logo_url
    await db.commit()
    await db.refresh(cfg)
    return _printer_out(cfg)


# ── Acknowledgements (tenant policies shown on public booking form) ──────────


class AcknowledgementOut(BaseModel):
    id: str
    title: str
    body_text: str
    link_url: str | None
    link_text: str | None
    is_required: bool
    display_order: int
    is_active: bool


class AcknowledgementCreate(BaseModel):
    title: str
    body_text: str
    link_url: str | None = None
    link_text: str | None = None
    is_required: bool = True
    display_order: int = 0
    is_active: bool = True


class AcknowledgementPatch(BaseModel):
    title: str | None = None
    body_text: str | None = None
    link_url: str | None = None
    link_text: str | None = None
    is_required: bool | None = None
    display_order: int | None = None
    is_active: bool | None = None


def _ack_out(a: TenantAcknowledgement) -> AcknowledgementOut:
    return AcknowledgementOut(
        id=str(a.id),
        title=a.title,
        body_text=a.body_text,
        link_url=a.link_url,
        link_text=a.link_text,
        is_required=a.is_required,
        display_order=a.display_order,
        is_active=a.is_active,
    )


@router.get("/acknowledgements", response_model=list[AcknowledgementOut])
async def list_acknowledgements(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AcknowledgementOut]:
    rows = (await db.execute(
        select(TenantAcknowledgement)
        .where(TenantAcknowledgement.tenant_id == current_user.tenant_id)
        .order_by(TenantAcknowledgement.display_order.asc(),
                  TenantAcknowledgement.created_at.asc())
    )).scalars().all()
    return [_ack_out(a) for a in rows]


@router.post("/acknowledgements", response_model=AcknowledgementOut,
             status_code=http_status.HTTP_201_CREATED)
async def create_acknowledgement(
    body: AcknowledgementCreate,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AcknowledgementOut:
    ack = TenantAcknowledgement(
        tenant_id=current_user.tenant_id,
        title=body.title.strip(),
        body_text=body.body_text.strip(),
        link_url=body.link_url.strip() if body.link_url else None,
        link_text=body.link_text.strip() if body.link_text else None,
        is_required=body.is_required,
        display_order=body.display_order,
        is_active=body.is_active,
    )
    db.add(ack)
    await db.commit()
    await db.refresh(ack)
    return _ack_out(ack)


@router.patch("/acknowledgements/{ack_id}", response_model=AcknowledgementOut)
async def update_acknowledgement(
    ack_id: str,
    body: AcknowledgementPatch,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AcknowledgementOut:
    ack = (await db.execute(
        select(TenantAcknowledgement).where(
            TenantAcknowledgement.id == uuid.UUID(ack_id),
            TenantAcknowledgement.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if ack is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND,
                            detail="Acknowledgement not found")
    for field in body.model_fields_set:
        value = getattr(body, field)
        if isinstance(value, str):
            value = value.strip() or None if field in ("link_url", "link_text") else value.strip()
        setattr(ack, field, value)
    await db.commit()
    await db.refresh(ack)
    return _ack_out(ack)


@router.delete("/acknowledgements/{ack_id}",
               status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_acknowledgement(
    ack_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    ack = (await db.execute(
        select(TenantAcknowledgement).where(
            TenantAcknowledgement.id == uuid.UUID(ack_id),
            TenantAcknowledgement.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if ack is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND,
                            detail="Acknowledgement not found")
    await db.delete(ack)
    await db.commit()
