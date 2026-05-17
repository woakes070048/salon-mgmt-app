import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.config import settings
from app.database import get_db
from app.deps import AdminUser
from app.legacy_import import import_clients, import_bookings, import_receipts, import_past_unreceipted_bookings, import_on_account_balances
from app.models.user import LoginLog
from app.email import AnyEmailConfig, email_cfg_from_row, send_email, send_password_reset_email, send_welcome_email
from app.models.appointment import Appointment, AppointmentItem, AppointmentRequest, AppointmentStatus
from app.models.client import Client
from app.models.email_config import TenantEmailConfig
from app.models.provider import Provider
from app.models.tenant import Tenant
from app.models.user import PasswordResetToken, User, UserRole

router = APIRouter(prefix="/admin", tags=["admin"])

RESET_TOKEN_EXPIRES_HOURS = 72
ALLOWED_MANAGED_ROLES = {UserRole.tenant_admin, UserRole.staff}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_email_cfg(tenant_id: uuid.UUID, db: AsyncSession) -> AnyEmailConfig:
    row = (
        await db.execute(
            select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email not configured — set up email in Settings → Email first",
        )
    return email_cfg_from_row(row)


async def _user_out(user: User, db: AsyncSession) -> "UserOut":
    client = (
        await db.execute(
            select(Client).where(
                Client.user_id == user.id,
                Client.is_active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
        client_name=f"{client.first_name} {client.last_name}" if client else None,
        first_name=user.first_name,
        last_name=user.last_name,
        language_preference=user.language_preference,
    )


async def _create_reset_token(user_id: uuid.UUID, db: AsyncSession) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user_id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_EXPIRES_HOURS),
    ))
    return raw


# ── Users ─────────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    client_name: str | None
    first_name: str | None
    last_name: str | None
    language_preference: str


@router.get("/users", response_model=list[UserOut])
async def list_users(
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserOut]:
    users = (
        await db.execute(
            select(User)
            .where(User.tenant_id == current_user.tenant_id)
            .order_by(User.role, User.email)
        )
    ).scalars().all()
    return [await _user_out(u, db) for u in users]


class UserCreate(BaseModel):
    email: EmailStr
    role: str
    send_welcome: bool = True
    first_name: str | None = None
    last_name: str | None = None


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    try:
        role = UserRole(body.role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role")
    if role not in ALLOWED_MANAGED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    existing = (
        await db.execute(
            select(User).where(
                User.tenant_id == current_user.tenant_id,
                User.email == body.email,
            )
        )
    ).scalar_one_or_none()

    if existing is not None and existing.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    smtp_cfg = None
    if body.send_welcome:
        smtp_cfg = await _get_email_cfg(current_user.tenant_id, db)

    if existing is not None:
        existing.is_active = True
        existing.role = role
        if body.first_name is not None:
            existing.first_name = body.first_name
        if body.last_name is not None:
            existing.last_name = body.last_name
        user = existing
    else:
        user = User(
            tenant_id=current_user.tenant_id,
            email=body.email,
            password_hash=hash_password(secrets.token_hex(32)),
            role=role,
            is_active=True,
            first_name=body.first_name,
            last_name=body.last_name,
        )
        db.add(user)
    await db.flush()

    reset_link = None
    if body.send_welcome and smtp_cfg:
        raw = await _create_reset_token(user.id, db)
        reset_link = f"{settings.frontend_url}/reset-password?token={raw}"

    await db.commit()
    await db.refresh(user)

    if reset_link and smtp_cfg:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
        ).scalar_one()
        await send_welcome_email(smtp_cfg, tenant, user.email, reset_link)

    return await _user_out(user, db)


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_preference: str | None = None


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    user = (
        await db.execute(
            select(User).where(
                User.id == uuid.UUID(user_id),
                User.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.role is not None:
        try:
            role = UserRole(body.role)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid role")
        if role not in ALLOWED_MANAGED_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = role

    if body.is_active is not None:
        if not body.is_active and user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        user.is_active = body.is_active

    if body.first_name is not None:
        user.first_name = body.first_name
    if body.last_name is not None:
        user.last_name = body.last_name
    if body.language_preference is not None:
        user.language_preference = body.language_preference

    await db.commit()
    await db.refresh(user)
    return await _user_out(user, db)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    tid = current_user.tenant_id
    user = (
        await db.execute(
            select(User).where(User.id == uuid.UUID(user_id), User.tenant_id == tid)
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Guard: cannot remove the last active admin
    if user.role in (UserRole.tenant_admin,):
        admin_count = (
            await db.execute(
                select(User).where(
                    User.tenant_id == tid,
                    User.role == UserRole.tenant_admin,
                    User.is_active == True,  # noqa: E712
                    User.id != user.id,
                )
            )
        ).scalars().all()
        if not admin_count:
            raise HTTPException(status_code=409, detail="Cannot delete the last active admin")

    # Guard: provider with future confirmed/in-progress appointments
    provider = (
        await db.execute(select(Provider).where(Provider.user_id == user.id))
    ).scalar_one_or_none()
    if provider is not None:
        from datetime import date
        future_appts = (
            await db.execute(
                select(AppointmentItem).where(
                    AppointmentItem.provider_id == provider.id,
                    AppointmentItem.tenant_id == tid,
                ).join(Appointment, Appointment.id == AppointmentItem.appointment_id).where(
                    Appointment.appointment_date >= datetime.combine(date.today(), datetime.min.time()),
                    Appointment.status.in_([AppointmentStatus.confirmed, AppointmentStatus.in_progress]),
                )
            )
        ).scalars().all()
        if future_appts:
            raise HTTPException(status_code=409,
                                detail="Cannot delete a provider with upcoming appointments — cancel them first")

    # Null every FK that references this user before deleting.
    # Wrapped in one try/except so any constraint violation surfaces as a
    # readable 409 instead of dropping the asyncpg connection ("Failed to fetch").
    from app.models.sale import Sale, SalePaymentEdit
    from app.models.retail import RetailStockMovement
    from app.models.cash_reconciliation import CashReconciliation, PettyCashEntry
    from app.models.time_block import TimeBlock
    from app.models.client import ClientColourNote

    try:
        await db.execute(update(Appointment)
            .where(Appointment.created_by_user_id == user.id).values(created_by_user_id=None))
        await db.execute(update(Appointment)
            .where(Appointment.confirmation_sent_by_user_id == user.id).values(confirmation_sent_by_user_id=None))
        await db.execute(update(AppointmentRequest)
            .where(AppointmentRequest.submitted_by_user_id == user.id).values(submitted_by_user_id=None))
        await db.execute(update(AppointmentRequest)
            .where(AppointmentRequest.reviewed_by_user_id == user.id).values(reviewed_by_user_id=None))
        await db.execute(update(Client)
            .where(Client.user_id == user.id).values(user_id=None))
        await db.execute(update(Provider)
            .where(Provider.user_id == user.id).values(user_id=None))
        await db.execute(update(SalePaymentEdit)
            .where(SalePaymentEdit.edited_by_user_id == user.id).values(edited_by_user_id=None))
        await db.execute(update(RetailStockMovement)
            .where(RetailStockMovement.created_by_user_id == user.id).values(created_by_user_id=None))
        await db.execute(update(PettyCashEntry)
            .where(PettyCashEntry.created_by_user_id == user.id).values(created_by_user_id=None))
        await db.execute(update(CashReconciliation)
            .where(CashReconciliation.closed_by_user_id == user.id).values(closed_by_user_id=None))
        await db.execute(update(Sale)
            .where(Sale.completed_by_user_id == user.id).values(completed_by_user_id=None))
        await db.execute(update(TimeBlock)
            .where(TimeBlock.created_by_user_id == user.id).values(created_by_user_id=None))
        await db.execute(update(ClientColourNote)
            .where(ClientColourNote.created_by_user_id == user.id).values(created_by_user_id=None))

        await db.execute(delete(LoginLog).where(LoginLog.user_id == user.id))

        tokens = (
            await db.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
        ).scalars().all()
        for t in tokens:
            await db.delete(t)

        await db.flush()
        await db.delete(user)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete user — constraint: {exc}",
        )


@router.post("/users/{user_id}/send-welcome", status_code=status.HTTP_204_NO_CONTENT)
async def resend_welcome(
    user_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    smtp_cfg = await _get_email_cfg(current_user.tenant_id, db)
    user = (
        await db.execute(
            select(User).where(
                User.id == uuid.UUID(user_id),
                User.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    raw = await _create_reset_token(user.id, db)
    await db.commit()
    reset_link = f"{settings.frontend_url}/reset-password?token={raw}"
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one()
    await send_welcome_email(smtp_cfg, tenant, user.email, reset_link)


@router.post("/users/{user_id}/send-reset", status_code=status.HTTP_204_NO_CONTENT)
async def send_reset_link(
    user_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    smtp_cfg = await _get_email_cfg(current_user.tenant_id, db)
    user = (
        await db.execute(
            select(User).where(
                User.id == uuid.UUID(user_id),
                User.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    raw = await _create_reset_token(user.id, db)
    await db.commit()
    reset_link = f"{settings.frontend_url}/reset-password?token={raw}"
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one()
    await send_password_reset_email(smtp_cfg, tenant, user.email, reset_link)


# ── Email config ──────────────────────────────────────────────────────────────

class EmailConfigOut(BaseModel):
    is_configured: bool
    send_mode: str  # 'smtp' | 'resend_api'
    # Resend API fields
    resend_api_key_set: bool
    # SMTP fields
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password_set: bool
    smtp_use_tls: bool
    from_address: str
    accounting_from_address: str | None


class EmailConfigSave(BaseModel):
    send_mode: str = "smtp"
    accounting_from_address: str | None = None
    # Resend API fields
    resend_api_key: str | None = None
    # SMTP fields
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    from_address: str


def _email_config_out(row: TenantEmailConfig) -> EmailConfigOut:
    return EmailConfigOut(
        is_configured=True,
        send_mode=row.send_mode or "smtp",
        resend_api_key_set=bool(row.resend_api_key),
        smtp_host=row.smtp_host or "",
        smtp_port=row.smtp_port,
        smtp_username=row.smtp_username or "",
        smtp_password_set=bool(row.smtp_password),
        smtp_use_tls=row.smtp_use_tls,
        from_address=row.from_address,
        accounting_from_address=row.accounting_from_address,
    )


_EMPTY_EMAIL_CONFIG = EmailConfigOut(
    is_configured=False,
    send_mode="smtp",
    resend_api_key_set=False,
    smtp_host="",
    smtp_port=587,
    smtp_username="",
    smtp_password_set=False,
    smtp_use_tls=True,
    from_address="",
    accounting_from_address=None,
)


@router.get("/email-config", response_model=EmailConfigOut)
async def get_email_config(
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmailConfigOut:
    row = (
        await db.execute(
            select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()
    return _email_config_out(row) if row else _EMPTY_EMAIL_CONFIG


@router.put("/email-config", response_model=EmailConfigOut)
async def save_email_config(
    body: EmailConfigSave,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmailConfigOut:
    row = (
        await db.execute(
            select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()

    if row is None:
        if body.send_mode == "resend_api" and not body.resend_api_key:
            raise HTTPException(status_code=400, detail="Resend API key is required")
        if body.send_mode == "smtp" and not body.smtp_password:
            raise HTTPException(status_code=400, detail="Password is required for initial setup")
        row = TenantEmailConfig(
            tenant_id=current_user.tenant_id,
            send_mode=body.send_mode,
            resend_api_key=body.resend_api_key,
            smtp_host=body.smtp_host.strip() or None,
            smtp_port=body.smtp_port,
            smtp_username=body.smtp_username.strip() or None,
            smtp_password=body.smtp_password,
            smtp_use_tls=body.smtp_use_tls,
            from_address=body.from_address.strip(),
        )
        db.add(row)
    else:
        row.send_mode = body.send_mode
        if body.resend_api_key:
            row.resend_api_key = body.resend_api_key
        row.smtp_host = body.smtp_host.strip() or None
        row.smtp_port = body.smtp_port
        row.smtp_username = body.smtp_username.strip() or None
        if body.smtp_password:
            row.smtp_password = body.smtp_password
        row.smtp_use_tls = body.smtp_use_tls
        row.from_address = body.from_address.strip()
    row.accounting_from_address = body.accounting_from_address.strip() if body.accounting_from_address else None

    await db.commit()
    await db.refresh(row)
    return _email_config_out(row)


class TestEmailBody(BaseModel):
    to: EmailStr


@router.post("/email-config/test", status_code=status.HTTP_204_NO_CONTENT)
async def test_email_config(
    body: TestEmailBody,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    from app.email_layout import wrap_branded
    smtp_cfg = await _get_email_cfg(current_user.tenant_id, db)
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one()
    inner = """\
<h2 style="margin:0 0 16px 0;font-family:Georgia,'Times New Roman',serif;font-weight:400;">
  SMTP test
</h2>
<p style="margin:0;">
  Your SMTP configuration is working. This is also a preview of the
  branded layout used for confirmations, welcomes, and password resets.
</p>"""
    subject = f"{tenant.name} — SMTP test"
    try:
        await send_email(smtp_cfg, body.to, subject, wrap_branded(inner, tenant, subject=subject))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── Payroll config ────────────────────────────────────────────────────────────

class PayrollConfigOut(BaseModel):
    provider_name: str | None
    provider_email: str | None
    client_id: str | None
    signature: str | None
    footer: str | None


class PayrollConfigSave(BaseModel):
    provider_name: str | None = None
    provider_email: str | None = None
    client_id: str | None = None
    signature: str | None = None
    footer: str | None = None


def _payroll_config_out(row: "TenantPayrollConfig") -> PayrollConfigOut:
    return PayrollConfigOut(
        provider_name=row.provider_name,
        provider_email=row.provider_email,
        client_id=row.client_id,
        signature=row.signature,
        footer=row.footer,
    )

_EMPTY_PAYROLL_CONFIG = PayrollConfigOut(
    provider_name=None, provider_email=None, client_id=None, signature=None, footer=None,
)


@router.get("/payroll-config", response_model=PayrollConfigOut)
async def get_payroll_config(
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PayrollConfigOut:
    from app.models.payroll_config import TenantPayrollConfig
    row = (
        await db.execute(
            select(TenantPayrollConfig).where(TenantPayrollConfig.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()
    return _payroll_config_out(row) if row else _EMPTY_PAYROLL_CONFIG


@router.put("/payroll-config", response_model=PayrollConfigOut)
async def save_payroll_config(
    body: PayrollConfigSave,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PayrollConfigOut:
    from app.models.payroll_config import TenantPayrollConfig
    row = (
        await db.execute(
            select(TenantPayrollConfig).where(TenantPayrollConfig.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()

    if row is None:
        row = TenantPayrollConfig(tenant_id=current_user.tenant_id)
        db.add(row)

    row.provider_name = body.provider_name.strip() if body.provider_name else None
    row.provider_email = body.provider_email.strip() if body.provider_email else None
    row.client_id = body.client_id.strip() if body.client_id else None
    row.signature = body.signature.strip() if body.signature else None
    row.footer = body.footer.strip() if body.footer else None

    await db.commit()
    await db.refresh(row)
    return _payroll_config_out(row)


# ── Legacy data import ────────────────────────────────────────────────────────

@router.post("/import-legacy")
async def import_legacy_data(
    clients_csv: UploadFile,
    all_bookings_csv: UploadFile,
    receipts_csv: UploadFile,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
    current_bookings_csv: UploadFile | None = None,
    on_account_csv: UploadFile | None = None,
) -> dict:
    """
    Import legacy CSV data. Safe to run multiple times — all functions are idempotent.
      clients_csv          → Client Details.txt
      all_bookings_csv     → Future and Past Bookings.txt
      receipts_csv         → Receipt Transactions.txt
      current_bookings_csv → All Bookings.txt (optional)
      on_account_csv       → On Account Summary.txt (optional)
    Order: clients → receipts (completed appts) → past unreceipted → future bookings.
    """
    import traceback
    clients_content = await clients_csv.read()
    bookings_content = await all_bookings_csv.read()
    receipts_content = await receipts_csv.read()
    current_bookings_content = await current_bookings_csv.read() if current_bookings_csv else None
    on_account_content = await on_account_csv.read() if on_account_csv else None

    result: dict = {}
    try:
        result["clients"]          = await import_clients(db, current_user.tenant_id, clients_content)
        result["receipts"]         = await import_receipts(db, current_user.tenant_id, receipts_content, bookings_content)
        result["past_unreceipted"] = await import_past_unreceipted_bookings(db, current_user.tenant_id, bookings_content)
        result["future_bookings"]  = await import_bookings(db, current_user.tenant_id, bookings_content, future_only=True)
        if current_bookings_content:
            result["current_bookings"] = await import_bookings(db, current_user.tenant_id, current_bookings_content, future_only=True)
        if on_account_content:
            result["on_account"] = await import_on_account_balances(db, current_user.tenant_id, on_account_content)
    except Exception:
        result["error"] = traceback.format_exc()
    return result



# ── Login log ─────────────────────────────────────────────────────────────────

class LoginLogOut(BaseModel):
    id: str
    email: str
    role: str
    logged_in_at: str


@router.get("/login-logs", response_model=list[LoginLogOut])
async def get_login_logs(
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
    limit: int = 500,
) -> list[LoginLogOut]:
    from sqlalchemy import text as _text
    rows = (await db.execute(
        _text(
            "SELECT l.id, l.email, u.role, l.created_at"
            " FROM login_logs l"
            " JOIN users u ON u.id = l.user_id"
            " WHERE l.tenant_id = :tid"
            " ORDER BY l.created_at DESC"
            " LIMIT :limit"
        ),
        {"tid": current_user.tenant_id, "limit": limit},
    )).fetchall()
    return [
        LoginLogOut(
            id=str(r.id),
            email=r.email,
            role=r.role,
            logged_in_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


# ── Zero-appointment client cleanup ──────────────────────────────────────────

class ZeroApptClientSample(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str | None
    cell_phone: str | None


class ZeroApptPreviewOut(BaseModel):
    count: int
    sample: list[ZeroApptClientSample]


async def _zero_appt_client_ids(tenant_id: uuid.UUID, db: AsyncSession) -> list[uuid.UUID]:
    from sqlalchemy import func as _func
    booked = (await db.execute(
        select(Appointment.client_id).where(Appointment.tenant_id == tenant_id).distinct()
    )).scalars().all()
    booked_set = set(booked)
    all_clients = (await db.execute(
        select(Client).where(Client.tenant_id == tenant_id, Client.is_active == True)  # noqa: E712
    )).scalars().all()
    return [c.id for c in all_clients if c.id not in booked_set]


@router.get("/cleanup/zero-appointment-clients", response_model=ZeroApptPreviewOut)
async def preview_zero_appt_clients(
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> ZeroApptPreviewOut:
    ids = await _zero_appt_client_ids(current_user.tenant_id, db)
    if not ids:
        return ZeroApptPreviewOut(count=0, sample=[])
    clients = (await db.execute(
        select(Client).where(Client.id.in_(ids[:10]))
    )).scalars().all()
    return ZeroApptPreviewOut(
        count=len(ids),
        sample=[
            ZeroApptClientSample(
                id=str(c.id),
                first_name=c.first_name,
                last_name=c.last_name,
                email=c.email,
                cell_phone=c.cell_phone,
            )
            for c in clients
        ],
    )


@router.delete("/cleanup/zero-appointment-clients")
async def delete_zero_appt_clients(
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sqlalchemy import delete as _delete
    ids = await _zero_appt_client_ids(current_user.tenant_id, db)
    if not ids:
        return {"deleted": 0}
    await db.execute(_delete(Client).where(Client.id.in_(ids)))
    await db.commit()
    return {"deleted": len(ids)}


# ── Historical payment summary ────────────────────────────────────────────────

class HistoricalPaymentRow(BaseModel):
    label: str
    amount: float

class HistoricalPaymentIn(BaseModel):
    year: int
    month: int
    rows: list[HistoricalPaymentRow]
    source: str = "milano"

class HistoricalPaymentOut(BaseModel):
    year: int
    month: int
    label: str
    amount: float
    source: str


@router.put("/historical-payments")
async def upsert_historical_payments(
    body: HistoricalPaymentIn,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upsert monthly payment type totals from an external source (e.g. Milano).
    Replaces all rows for the given year/month if they exist."""
    from sqlalchemy import text as _text
    tid = current_user.tenant_id

    # Delete existing rows for this period
    await db.execute(
        _text("DELETE FROM historical_payment_summary WHERE tenant_id = :tid AND year = :y AND month = :m"),
        {"tid": tid, "y": body.year, "m": body.month},
    )

    # Insert new rows
    for row in body.rows:
        await db.execute(
            _text("""
                INSERT INTO historical_payment_summary
                    (tenant_id, year, month, label, amount, source, created_at, updated_at)
                VALUES (:tid, :y, :m, :label, :amount, :source, NOW(), NOW())
            """),
            {"tid": tid, "y": body.year, "m": body.month,
             "label": row.label, "amount": row.amount, "source": body.source},
        )

    await db.commit()
    return {"saved": len(body.rows), "year": body.year, "month": body.month}


@router.get("/historical-payments")
async def list_historical_payments(
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> list[HistoricalPaymentOut]:
    from sqlalchemy import text as _text
    rows = (await db.execute(
        _text("""
            SELECT year, month, label, amount, source
            FROM historical_payment_summary
            WHERE tenant_id = :tid
            ORDER BY year, month, label
        """),
        {"tid": current_user.tenant_id},
    )).fetchall()
    return [
        HistoricalPaymentOut(year=r.year, month=r.month, label=r.label,
                             amount=float(r.amount), source=r.source)
        for r in rows
    ]


# ── Diagnostic: explain why sale_items don't show up in payroll/perf reports ──
# Used to chase down the "Sarah's data ends May 6 even though receipts are in
# the DB" issue. Returns per-(date, provider, has_appt_item_id) counts so we
# can tell whether the data is missing, mis-attributed, or orphaned from
# appointment_items (which the report inner-joins).

@router.get("/diagnose/sales-summary")
async def diagnose_sales_summary(
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
    start: str = "2026-05-07",
    end: str = "2026-05-13",
) -> dict:
    from sqlalchemy import text as _text
    from datetime import date as _date
    import traceback

    tid = current_user.tenant_id
    start_d = _date.fromisoformat(start)
    end_d = _date.fromisoformat(end)

    try:
        rows = (await db.execute(
            _text("""
                SELECT
                    s.completed_at::date          AS day,
                    COALESCE(p.display_name, '<NO PROVIDER>') AS provider,
                    si.provider_id IS NULL        AS provider_is_null,
                    si.appointment_item_id IS NULL AS appt_item_id_is_null,
                    si.kind::text                 AS kind,
                    COUNT(*)                      AS items
                FROM sale_items si
                JOIN sales s ON s.id = si.sale_id
                LEFT JOIN providers p ON p.id = si.provider_id
                WHERE si.tenant_id = :tid
                  AND s.completed_at::date BETWEEN :start_d AND :end_d
                  AND s.status::text = 'completed'
                GROUP BY 1, 2, 3, 4, 5
                ORDER BY 1, 2, 5
            """),
            {"tid": tid, "start_d": start_d, "end_d": end_d},
        )).fetchall()
    except Exception as e:
        return {
            "range": {"start": start, "end": end},
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "providers": [],
            "items": [],
        }

    providers = (await db.execute(
        _text("SELECT id, display_name FROM providers WHERE tenant_id = :tid ORDER BY display_name"),
        {"tid": tid},
    )).fetchall()

    return {
        "range": {"start": start, "end": end},
        "providers": [
            {"id": str(r.id), "display_name": r.display_name} for r in providers
        ],
        "items": [
            {
                "day": r.day.isoformat() if r.day else None,
                "provider": r.provider,
                "provider_is_null": bool(r.provider_is_null),
                "appt_item_id_is_null": bool(r.appt_item_id_is_null),
                "kind": str(r.kind),
                "items": int(r.items),
            }
            for r in rows
        ],
    }


# ── Backfill: link orphaned service sale_items to appointment_items ───────────
# Companion to the legacy_import P-IMPORT-LINK fix. For each completed sale_item
# of kind='service' with appointment_item_id IS NULL, walk sale_appointments to
# the linked appointment, then match by (provider_id, service_id) — FIFO — and
# fall back to (service_id) alone if the staff column on the receipt didn't
# match the booked provider.

@router.post("/diagnose/backfill-sale-item-links")
async def backfill_sale_item_links(current_user: AdminUser, db: AsyncSession = Depends(get_db)) -> dict:
    from sqlalchemy import text as _text

    tid = current_user.tenant_id

    orphans = (await db.execute(
        _text("""
            SELECT si.id AS si_id, si.provider_id AS si_prov, si.description AS si_desc,
                   sa.appointment_id AS appt_id
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            JOIN sale_appointments sa ON sa.sale_id = si.sale_id
            WHERE si.tenant_id = :tid
              AND si.kind::text = 'service'
              AND si.appointment_item_id IS NULL
              AND s.status::text = 'completed'
            ORDER BY sa.appointment_id, si.sequence
        """),
        {"tid": tid},
    )).fetchall()

    if not orphans:
        return {"orphans_found": 0, "linked": 0, "unmatched": 0}

    # Group orphans by appointment so we can consume each appointment_item once.
    by_appt: dict[uuid.UUID, list] = {}
    for o in orphans:
        by_appt.setdefault(o.appt_id, []).append(o)

    # Resolve service descriptions on the orphan sale_items to a service_id via
    # services.name (case-insensitive). The importer snapshots the service name
    # into sale_items.description at create time.
    svc_rows = (await db.execute(
        _text("SELECT id, name FROM services WHERE tenant_id = :tid"),
        {"tid": tid},
    )).fetchall()
    svc_id_by_name: dict[str, uuid.UUID] = {r.name.strip().lower(): r.id for r in svc_rows}

    linked = 0
    unmatched = 0

    for appt_id, group in by_appt.items():
        ai_rows = (await db.execute(
            _text("SELECT id, service_id, provider_id FROM appointment_items"
                  " WHERE appointment_id = :id ORDER BY sequence"),
            {"id": appt_id},
        )).fetchall()
        ai_pool: dict[tuple, list[uuid.UUID]] = {}
        svc_only_pool: dict[uuid.UUID, list[uuid.UUID]] = {}
        for r in ai_rows:
            ai_pool.setdefault((r.provider_id, r.service_id), []).append(r.id)
            svc_only_pool.setdefault(r.service_id, []).append(r.id)

        for o in group:
            svc_id = svc_id_by_name.get((o.si_desc or "").strip().lower())
            if not svc_id:
                unmatched += 1
                continue
            key = (o.si_prov, svc_id)
            ai_id = None
            if key in ai_pool and ai_pool[key]:
                ai_id = ai_pool[key].pop(0)
                svc_only_pool.get(svc_id, []).remove(ai_id)
            elif svc_id in svc_only_pool and svc_only_pool[svc_id]:
                ai_id = svc_only_pool[svc_id].pop(0)
                for v in ai_pool.values():
                    if ai_id in v:
                        v.remove(ai_id)
                        break
            if ai_id is None:
                unmatched += 1
                continue
            await db.execute(
                _text("UPDATE sale_items SET appointment_item_id = :ai, updated_at = NOW()"
                      " WHERE id = :si"),
                {"ai": ai_id, "si": o.si_id},
            )
            linked += 1

    await db.commit()

    return {"orphans_found": len(orphans), "linked": linked, "unmatched": unmatched}


# ── Backfill: set sale_items.service_id from Milano description ──────────────
# When the legacy CSV importer runs, it tries to resolve each sale_item's
# description to a service_id via RECEIPT_SERVICE_MAP. If the service didn't
# exist in the catalog at import time, sale_items.service_id was left NULL and
# the description sits there as a dangling pointer. Adding the service to the
# catalog later doesn't retroactively link those rows.
#
# This endpoint re-runs that resolution against the *current* catalog so any
# now-mapped descriptions get their service_id populated. Idempotent: items
# already linked are skipped; descriptions still unmappable are reported back
# with counts so the owner can see what's missing.
#
# Used by: owner clicks button after adding a missing service (e.g. Olaplex)
# that Milano had been billing but wasn't yet in the SalonOS catalog.

@router.post("/diagnose/backfill-sale-item-service-ids")
async def backfill_sale_item_service_ids(
    current_user: AdminUser, db: AsyncSession = Depends(get_db)
) -> dict:
    from sqlalchemy import text as _text
    from app.legacy_import import RECEIPT_SERVICE_MAP

    tid = current_user.tenant_id

    # Current catalog keyed by service_code (case-insensitive)
    svc_rows = (await db.execute(
        _text("SELECT id, service_code FROM services WHERE tenant_id = :tid"),
        {"tid": tid},
    )).fetchall()
    svc_id_by_code: dict[str, uuid.UUID] = {
        (r.service_code or "").strip().lower(): r.id for r in svc_rows
    }

    # Orphans: service-kind sale_items with NULL service_id on completed sales.
    orphans = (await db.execute(
        _text("""
            SELECT si.id, si.description
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            WHERE si.tenant_id = :tid
              AND si.kind::text = 'service'
              AND si.service_id IS NULL
              AND s.status::text = 'completed'
        """),
        {"tid": tid},
    )).fetchall()

    linked = 0
    unmapped_descs: dict[str, int] = {}
    missing_codes: dict[str, int] = {}

    for o in orphans:
        desc_key = (o.description or "").strip().lower()
        if not desc_key:
            unmapped_descs[o.description or ""] = unmapped_descs.get(o.description or "", 0) + 1
            continue
        code = RECEIPT_SERVICE_MAP.get(desc_key)
        if not code:
            # Description not known to the importer's map at all.
            unmapped_descs[o.description] = unmapped_descs.get(o.description, 0) + 1
            continue
        svc_id = svc_id_by_code.get(code.lower())
        if not svc_id:
            # Map knows the description but catalog still lacks the service.
            missing_codes[code] = missing_codes.get(code, 0) + 1
            continue
        await db.execute(
            _text("UPDATE sale_items SET service_id = :sid, updated_at = NOW()"
                  " WHERE id = :id"),
            {"sid": svc_id, "id": o.id},
        )
        linked += 1

    await db.commit()

    return {
        "orphans_found": len(orphans),
        "linked": linked,
        # Descriptions the importer doesn't know how to map at all.
        # Fix: add the description (case-insensitive) → service_code to
        # RECEIPT_SERVICE_MAP in legacy_import.py.
        "unmapped_descriptions": [
            {"description": d, "count": c}
            for d, c in sorted(unmapped_descs.items(), key=lambda x: -x[1])
        ],
        # service_codes that the importer maps to but aren't in the catalog.
        # Fix: create the service in /services with this code.
        "missing_service_codes": [
            {"service_code": c, "count": n}
            for c, n in sorted(missing_codes.items(), key=lambda x: -x[1])
        ],
    }
