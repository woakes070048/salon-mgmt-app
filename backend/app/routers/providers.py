import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import AdminUser, CurrentUser
from app.models.provider import EIRateType, OnlineBookingVisibility, PayType, Provider, ProviderType

router = APIRouter(prefix="/providers", tags=["providers"])


# ── Shared response models ────────────────────────────────────────────────────

class ProviderOut(BaseModel):
    id: str
    display_name: str
    provider_type: str
    booking_order: int
    has_appointments: bool
    makes_appointments: bool = True

    model_config = {"from_attributes": True}


class ProviderDetail(BaseModel):
    id: str
    user_id: str | None

    # Identity
    first_name: str
    last_name: str
    display_name: str
    provider_code: str | None
    provider_type: str
    job_title: str | None
    is_owner: bool
    is_active: bool

    # Personal
    sex: str | None
    address_line: str | None
    city: str | None
    province: str | None
    postal_code: str | None
    personal_email: str | None
    home_phone: str | None
    cell_phone: str | None
    other_phone: str | None
    birthday: date | None
    notes: str | None
    provider_photo_url: str | None

    # Employment
    hire_date: date | None
    first_day_worked: date | None
    certification: str | None
    sin_set: bool

    # Compensation
    pay_type: str | None
    pay_amount: float | None
    hourly_minimum: float | None
    vacation_pct: float | None
    retail_commission_pct: float | None
    commission_tiers: list | None

    # Banking (account masked in response)
    bank_institution_no: str | None
    bank_transit_no: str | None
    bank_account_masked: str | None

    # Tax
    cpp_exempt: bool | None
    ei_exempt: bool | None
    ei_rate_type: str | None
    province_of_taxation: str | None
    wcb_csst_exempt: bool | None
    td1_federal_credit: float | None
    td1_provincial_credit: float | None

    # Booking
    can_be_cashier: bool
    makes_appointments: bool
    has_appointments: bool
    booking_order: int
    online_booking_visibility: str


def _mask_account(raw: str | None) -> str | None:
    if not raw:
        return None
    return "****" + raw[-4:] if len(raw) > 4 else "****"


def _detail(p: Provider) -> ProviderDetail:
    return ProviderDetail(
        id=str(p.id),
        user_id=str(p.user_id) if p.user_id else None,
        first_name=p.first_name,
        last_name=p.last_name,
        display_name=p.display_name,
        provider_code=p.provider_code,
        provider_type=p.provider_type.value,
        job_title=p.job_title,
        is_owner=p.is_owner,
        is_active=p.is_active,
        sex=p.sex,
        address_line=p.address_line,
        city=p.city,
        province=p.province,
        postal_code=p.postal_code,
        personal_email=p.personal_email,
        home_phone=p.home_phone,
        cell_phone=p.cell_phone,
        other_phone=p.other_phone,
        birthday=p.birthday,
        notes=p.notes,
        provider_photo_url=p.provider_photo_url,
        hire_date=p.hire_date,
        first_day_worked=p.first_day_worked,
        certification=p.certification,
        sin_set=bool(p.sin_encrypted),
        pay_type=p.pay_type.value if p.pay_type else None,
        pay_amount=float(p.pay_amount) if p.pay_amount is not None else None,
        hourly_minimum=float(p.hourly_minimum) if p.hourly_minimum is not None else None,
        vacation_pct=float(p.vacation_pct) if p.vacation_pct is not None else None,
        retail_commission_pct=float(p.retail_commission_pct) if p.retail_commission_pct is not None else None,
        commission_tiers=p.commission_tiers if p.commission_tiers else None,
        bank_institution_no=p.bank_institution_no,
        bank_transit_no=p.bank_transit_no,
        bank_account_masked=_mask_account(p.bank_account_encrypted),
        cpp_exempt=p.cpp_exempt,
        ei_exempt=p.ei_exempt,
        ei_rate_type=p.ei_rate_type.value if p.ei_rate_type else None,
        province_of_taxation=p.province_of_taxation,
        wcb_csst_exempt=p.wcb_csst_exempt,
        td1_federal_credit=float(p.td1_federal_credit) if p.td1_federal_credit is not None else None,
        td1_provincial_credit=float(p.td1_provincial_credit) if p.td1_provincial_credit is not None else None,
        can_be_cashier=p.can_be_cashier,
        makes_appointments=p.makes_appointments,
        has_appointments=p.has_appointments,
        booking_order=p.booking_order,
        online_booking_visibility=p.online_booking_visibility.value,
    )


# ── GET /providers — public list (all staff) ──────────────────────────────────

@router.get("", response_model=list[ProviderOut])
async def list_providers(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProviderOut]:
    result = await db.execute(
        select(Provider)
        .where(
            Provider.tenant_id == current_user.tenant_id,
            Provider.is_active == True,  # noqa: E712
        )
        .order_by(Provider.booking_order)
    )
    providers = result.scalars().all()
    return [
        ProviderOut(
            id=str(p.id),
            display_name=p.display_name,
            provider_type=p.provider_type.value,
            booking_order=p.booking_order,
            has_appointments=p.has_appointments,
            makes_appointments=p.makes_appointments,
        )
        for p in providers
    ]


# ── GET /providers/all — admin list including inactive ────────────────────────

@router.get("/all", response_model=list[ProviderDetail])
async def list_all_providers(
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProviderDetail]:
    providers = (
        await db.execute(
            select(Provider)
            .where(Provider.tenant_id == current_user.tenant_id)
            .order_by(Provider.booking_order, Provider.display_name)
        )
    ).scalars().all()
    return [_detail(p) for p in providers]


# ── Payroll report helpers ────────────────────────────────────────────────────

class ProviderPayrollLine(BaseModel):
    provider_id: str
    first_name: str
    last_name: str
    display_name: str
    is_owner: bool
    booking_order: int
    pay_type: str | None
    pay_basis: str        # "commission" | "hourly" | "salary" | "n/a"
    scheduled_hours: float
    actual_hours: float        # sum of checked-out time entries; 0 if none recorded
    hours_source: str          # "actual" | "scheduled"
    payroll_hours: float       # whichever is used for the floor calculation
    hourly_minimum: float | None
    hourly_floor_amount: float
    service_commission: float
    retail_revenue: float
    retail_commission: float
    vacation_pct: float
    gross_before_vacation: float
    vacation_pay: float
    gross_pay: float
    # Detailed breakdown — populated for the single-provider payroll view
    styling_revenue: float = 0.0
    styling_item_count: int = 0
    colour_revenue: float = 0.0
    colour_item_count: int = 0
    gross_service_revenue: float = 0.0
    styling_product_fee: float = 0.0
    colour_product_fee: float = 0.0
    total_product_fees: float = 0.0
    net_service_revenue: float = 0.0
    commission_tier_applied: "CommissionTierOut | None" = None


async def _calc_payroll_line(
    p: "Provider",
    period_start: "date",
    period_end: "date",
    db: "AsyncSession",
    tid: "uuid.UUID",
) -> ProviderPayrollLine:
    import calendar as cal_mod
    from datetime import timedelta
    from decimal import Decimal as D
    from sqlalchemy import func, cast, Date as SADate
    from app.models.appointment import AppointmentItem
    from app.models.sale import Sale, SaleItem, SaleItemKind, SaleStatus
    from app.models.service import Service, ServiceCategory
    from app.models.provider_service_price import ProviderServicePrice
    from app.models.schedule import ProviderSchedule, ProviderScheduleException

    pid = p.id

    # ── Provider-specific price overrides (most recent active per service) ───
    psp_rows = (
        await db.execute(
            select(ProviderServicePrice.service_id, ProviderServicePrice.price)
            .where(
                ProviderServicePrice.provider_id == pid,
                ProviderServicePrice.tenant_id == tid,
                ProviderServicePrice.is_active == True,
            )
            .order_by(ProviderServicePrice.effective_from.desc())
        )
    ).all()
    psp_price_map: dict[str, float] = {}
    for r in psp_rows:
        sid = str(r.service_id)
        if sid not in psp_price_map:
            psp_price_map[sid] = float(r.price)

    # ── Service revenue ───────────────────────────────────────────────────────
    service_rows = (
        await db.execute(
            select(
                SaleItem.line_total,
                ServiceCategory.name.label("cat_name"),
                Service.id.label("service_id"),
                Service.default_cost.label("default_cost"),
                Service.default_price.label("default_price"),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(AppointmentItem, AppointmentItem.id == SaleItem.appointment_item_id)
            .join(Service, Service.id == AppointmentItem.service_id)
            .join(ServiceCategory, ServiceCategory.id == Service.category_id)
            .where(
                SaleItem.tenant_id == tid,
                SaleItem.provider_id == pid,
                SaleItem.kind == SaleItemKind.service,
                Sale.status == SaleStatus.completed,
                cast(Sale.completed_at, SADate) >= period_start,
                cast(Sale.completed_at, SADate) <= period_end,
            )
        )
    ).all()

    styling_revenue = D("0")
    styling_count = 0
    styling_fee = D("0")
    colour_revenue = D("0")
    colour_count = 0
    colour_fee = D("0")

    for row in service_rows:
        cat = (row.cat_name or "").lower()
        is_colour = "colour" in cat or "color" in cat or "colouring" in cat
        sid = str(row.service_id)
        effective_price = D(str(psp_price_map.get(sid, float(row.default_price or 0))))
        default_cost = D(str(float(row.default_cost or 0)))

        if is_colour:
            colour_revenue += row.line_total
            colour_count += 1
            # default_cost is a % of the provider's standard price for this service
            colour_fee += effective_price * default_cost / D("100")
        else:
            styling_revenue += row.line_total
            styling_count += 1
            # default_cost is a flat dollar amount per service item
            styling_fee += default_cost

    gross_service_revenue = styling_revenue + colour_revenue

    # ── Product fees ─────────────────────────────────────────────────────────
    total_product_fees = styling_fee + colour_fee
    net_service_revenue = gross_service_revenue - total_product_fees

    # ── Commission tier ───────────────────────────────────────────────────────
    tiers = p.commission_tiers or []
    applied_tier = None
    net_float = float(net_service_revenue)
    for t in sorted(tiers, key=lambda x: x.get("monthly_threshold", 0)):
        if net_float >= t.get("monthly_threshold", 0):
            applied_tier = t
    rate_pct = D(str(applied_tier["rate_pct"])) if applied_tier else D("0")
    commission_on_services = net_service_revenue * rate_pct / D("100")

    # ── Retail revenue ────────────────────────────────────────────────────────
    # Commission goes only to the provider directly attributed on each retail
    # item (sale_items.provider_id) — NOT to every provider who shared the
    # appointment. This matches Milano: the Staff column on each receipt line
    # determines who earns the retail commission.
    retail_total = (
        await db.execute(
            select(func.coalesce(func.sum(SaleItem.line_total), D("0")))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                SaleItem.tenant_id == tid,
                SaleItem.kind == SaleItemKind.retail,
                SaleItem.provider_id == pid,
                Sale.status == SaleStatus.completed,
                cast(Sale.completed_at, SADate) >= period_start,
                cast(Sale.completed_at, SADate) <= period_end,
            )
        )
    ).scalar() or D("0")
    retail_revenue = D(str(retail_total))
    retail_pct = D(str(p.retail_commission_pct or 0))
    retail_commission = retail_revenue * retail_pct / D("100")

    total_commission_pay = commission_on_services + retail_commission

    # ── Scheduled hours ───────────────────────────────────────────────────────
    from datetime import timedelta as td
    all_schedules = (
        await db.execute(
            select(ProviderSchedule).where(
                ProviderSchedule.tenant_id == tid,
                ProviderSchedule.provider_id == pid,
                ProviderSchedule.effective_from <= period_end,
            )
        )
    ).scalars().all()

    all_exceptions = (
        await db.execute(
            select(ProviderScheduleException).where(
                ProviderScheduleException.tenant_id == tid,
                ProviderScheduleException.provider_id == pid,
                ProviderScheduleException.exception_date >= period_start,
                ProviderScheduleException.exception_date <= period_end,
            )
        )
    ).scalars().all()
    exc_map = {str(e.exception_date): e for e in all_exceptions}

    sched_map: dict[int, ProviderSchedule] = {}
    for row in sorted(all_schedules, key=lambda x: x.effective_from):
        if row.effective_to is None or row.effective_to >= period_start:
            sched_map[row.day_of_week] = row

    def _hours(start, end) -> float:
        if not start or not end:
            return 0.0
        from datetime import datetime as _dt
        s = _dt.combine(period_start, start)
        e = _dt.combine(period_start, end)
        return max(0.0, (e - s).total_seconds() / 3600)

    scheduled_hours = 0.0
    cur = period_start
    while cur <= period_end:
        exc = exc_map.get(str(cur))
        if exc is not None:
            if exc.is_working:
                scheduled_hours += _hours(exc.start_time, exc.end_time)
        else:
            srow = sched_map.get(cur.weekday())
            if srow and srow.is_working:
                scheduled_hours += _hours(srow.start_time, srow.end_time)
        cur += td(days=1)

    # ── Actual hours from time entries ────────────────────────────────────────
    from app.models.staff_time_entry import StaffTimeEntry
    entry_rows = (
        await db.execute(
            select(StaffTimeEntry).where(
                StaffTimeEntry.tenant_id == tid,
                StaffTimeEntry.provider_id == pid,
                StaffTimeEntry.date >= period_start,
                StaffTimeEntry.date <= period_end,
                StaffTimeEntry.check_out_at.isnot(None),
            )
        )
    ).scalars().all()
    actual_hours = sum(
        (e.check_out_at - e.check_in_at).total_seconds() / 3600
        for e in entry_rows
    )
    actual_hours = round(actual_hours, 2)
    has_entries = len(entry_rows) > 0
    payroll_hours = actual_hours if has_entries else scheduled_hours
    hours_source = "actual" if has_entries else "scheduled"

    # ── Pay basis ─────────────────────────────────────────────────────────────
    hourly_min = float(p.hourly_minimum or 0)
    hourly_floor = round(payroll_hours * hourly_min, 2)
    vacation_pct_val = float(p.vacation_pct or 0)
    pay_type_val = p.pay_type.value if p.pay_type else None

    if pay_type_val == "commission":
        pay_basis = "commission" if float(total_commission_pay) >= hourly_floor else "hourly"
        gross_before_vac = float(total_commission_pay) if pay_basis == "commission" else hourly_floor
    elif pay_type_val == "hourly":
        pay_basis = "hourly"
        gross_before_vac = hourly_floor
    elif pay_type_val == "salary":
        pay_basis = "salary"
        gross_before_vac = round(float(p.pay_amount or 0) / 12, 2)
    else:
        pay_basis = "n/a"
        gross_before_vac = 0.0

    vacation_pay = round(gross_before_vac * vacation_pct_val / 100, 2)
    gross_pay = round(gross_before_vac + vacation_pay, 2)

    return ProviderPayrollLine(
        provider_id=str(p.id),
        first_name=p.first_name,
        last_name=p.last_name,
        display_name=p.display_name,
        is_owner=p.is_owner,
        booking_order=p.booking_order,
        pay_type=pay_type_val,
        pay_basis=pay_basis,
        scheduled_hours=round(scheduled_hours, 2),
        actual_hours=actual_hours,
        hours_source=hours_source,
        payroll_hours=round(payroll_hours, 2),
        hourly_minimum=hourly_min if hourly_min else None,
        hourly_floor_amount=hourly_floor,
        service_commission=round(float(commission_on_services), 2),
        retail_revenue=round(float(retail_revenue), 2),
        retail_commission=round(float(retail_commission), 2),
        vacation_pct=vacation_pct_val,
        gross_before_vacation=round(gross_before_vac, 2),
        vacation_pay=vacation_pay,
        gross_pay=gross_pay,
        styling_revenue=round(float(styling_revenue), 2),
        styling_item_count=styling_count,
        colour_revenue=round(float(colour_revenue), 2),
        colour_item_count=colour_count,
        gross_service_revenue=round(float(gross_service_revenue), 2),
        styling_product_fee=round(float(styling_fee), 2),
        colour_product_fee=round(float(colour_fee), 2),
        total_product_fees=round(float(total_product_fees), 2),
        net_service_revenue=round(float(net_service_revenue), 2),
        commission_tier_applied=CommissionTierOut(**applied_tier) if applied_tier else None,
    )


class PayrollReportOut(BaseModel):
    period_start: date
    period_end: date
    lines: list[ProviderPayrollLine]


# ── GET /providers/payroll-report ─────────────────────────────────────────────

@router.get("/payroll-report", response_model=PayrollReportOut)
async def get_payroll_report(
    period_start: date,
    period_end: date,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PayrollReportOut:
    tid = current_user.tenant_id
    providers = (
        await db.execute(
            select(Provider)
            .where(Provider.tenant_id == tid, Provider.is_active == True)  # noqa: E712
            .order_by(Provider.is_owner.desc(), Provider.booking_order)
        )
    ).scalars().all()

    lines = []
    for p in providers:
        line = await _calc_payroll_line(p, period_start, period_end, db, tid)
        lines.append(line)

    return PayrollReportOut(period_start=period_start, period_end=period_end, lines=lines)


# ── POST /providers/payroll-report/send-email ─────────────────────────────────

class SendPayrollEmailBody(BaseModel):
    to_email: str
    subject: str
    body_text: str   # plain text; backend wraps in simple HTML


@router.post("/payroll-report/send-email", status_code=status.HTTP_204_NO_CONTENT)
async def send_payroll_email(
    body: SendPayrollEmailBody,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    from app.email import AnyEmailConfig, email_cfg_from_row, send_email
    from app.models.email_config import TenantEmailConfig

    row = (
        await db.execute(
            select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email not configured — set up email in Settings → Email first",
        )
    cfg = email_cfg_from_row(row)
    # Use accounting address as the From when configured
    if row.accounting_from_address:
        import dataclasses
        cfg = dataclasses.replace(cfg, from_address=row.accounting_from_address)

    # Wrap plain text in minimal HTML (preserve line breaks)
    lines_html = "<br>".join(
        f"<b>{ln}</b>" if ln.startswith("@") else ln
        for ln in body.body_text.replace("&", "&amp;").replace("<", "&lt;").splitlines()
    )
    html = f'<div style="font-family:sans-serif;font-size:14px;line-height:1.6;max-width:600px">{lines_html}</div>'

    try:
        await send_email(cfg, body.to_email, body.subject, html)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── GET /providers/{id} ───────────────────────────────────────────────────────

@router.get("/{provider_id}", response_model=ProviderDetail)
async def get_provider(
    provider_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderDetail:
    p = (
        await db.execute(
            select(Provider).where(
                Provider.id == uuid.UUID(provider_id),
                Provider.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _detail(p)


# ── POST /providers ───────────────────────────────────────────────────────────

class ProviderCreate(BaseModel):
    first_name: str
    last_name: str
    display_name: str
    provider_type: str
    job_title: str | None = None
    provider_code: str | None = None
    is_owner: bool = False
    booking_order: int = 0
    has_appointments: bool = True
    makes_appointments: bool = False
    can_be_cashier: bool = False
    online_booking_visibility: str = "not_available"
    sex: str | None = None
    personal_email: str | None = None
    cell_phone: str | None = None
    home_phone: str | None = None
    other_phone: str | None = None
    address_line: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    birthday: date | None = None
    notes: str | None = None
    hire_date: date | None = None
    first_day_worked: date | None = None
    certification: str | None = None
    pay_type: str | None = None
    pay_amount: float | None = None
    hourly_minimum: float | None = None
    vacation_pct: float | None = 4.0
    retail_commission_pct: float | None = 10.0
    commission_tiers: list | None = None
    bank_institution_no: str | None = None
    bank_transit_no: str | None = None
    bank_account_no: str | None = None
    cpp_exempt: bool | None = None
    ei_exempt: bool | None = None
    ei_rate_type: str | None = None
    province_of_taxation: str | None = None
    wcb_csst_exempt: bool | None = None
    td1_federal_credit: float | None = None
    td1_provincial_credit: float | None = None
    user_id: str | None = None
    sin: str | None = None


@router.post("", response_model=ProviderDetail, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: ProviderCreate,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderDetail:
    try:
        provider_type = ProviderType(body.provider_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider_type")

    pay_type = None
    if body.pay_type:
        try:
            pay_type = PayType(body.pay_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid pay_type")

    ei_rate_type = None
    if body.ei_rate_type:
        try:
            ei_rate_type = EIRateType(body.ei_rate_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ei_rate_type")

    obv = OnlineBookingVisibility.not_available
    if body.online_booking_visibility:
        try:
            obv = OnlineBookingVisibility(body.online_booking_visibility)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid online_booking_visibility")

    p = Provider(
        tenant_id=current_user.tenant_id,
        user_id=uuid.UUID(body.user_id) if body.user_id else None,
        first_name=body.first_name,
        last_name=body.last_name,
        display_name=body.display_name,
        provider_code=body.provider_code,
        provider_type=provider_type,
        job_title=body.job_title,
        is_owner=body.is_owner,
        is_active=True,
        booking_order=body.booking_order,
        has_appointments=body.has_appointments,
        makes_appointments=body.makes_appointments,
        can_be_cashier=body.can_be_cashier,
        online_booking_visibility=obv,
        sex=body.sex,
        personal_email=body.personal_email,
        cell_phone=body.cell_phone,
        home_phone=body.home_phone,
        other_phone=body.other_phone,
        address_line=body.address_line,
        city=body.city,
        province=body.province,
        postal_code=body.postal_code,
        birthday=body.birthday,
        notes=body.notes,
        hire_date=body.hire_date,
        first_day_worked=body.first_day_worked,
        certification=body.certification,
        sin_encrypted=body.sin,
        pay_type=pay_type,
        pay_amount=body.pay_amount,
        hourly_minimum=body.hourly_minimum,
        vacation_pct=body.vacation_pct,
        retail_commission_pct=body.retail_commission_pct,
        commission_tiers=body.commission_tiers,
        bank_institution_no=body.bank_institution_no,
        bank_transit_no=body.bank_transit_no,
        bank_account_encrypted=body.bank_account_no,
        cpp_exempt=body.cpp_exempt,
        ei_exempt=body.ei_exempt,
        ei_rate_type=ei_rate_type,
        province_of_taxation=body.province_of_taxation,
        wcb_csst_exempt=body.wcb_csst_exempt,
        td1_federal_credit=body.td1_federal_credit,
        td1_provincial_credit=body.td1_provincial_credit,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _detail(p)


# ── PATCH /providers/{id} ─────────────────────────────────────────────────────

class ProviderUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    provider_type: str | None = None
    job_title: str | None = None
    provider_code: str | None = None
    is_owner: bool | None = None
    is_active: bool | None = None
    booking_order: int | None = None
    has_appointments: bool | None = None
    makes_appointments: bool | None = None
    can_be_cashier: bool | None = None
    online_booking_visibility: str | None = None
    provider_photo_url: str | None = None
    sex: str | None = None
    personal_email: str | None = None
    cell_phone: str | None = None
    home_phone: str | None = None
    other_phone: str | None = None
    address_line: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    birthday: date | None = None
    notes: str | None = None
    hire_date: date | None = None
    first_day_worked: date | None = None
    certification: str | None = None
    pay_type: str | None = None
    pay_amount: float | None = None
    hourly_minimum: float | None = None
    vacation_pct: float | None = None
    retail_commission_pct: float | None = None
    commission_tiers: list | None = None
    bank_institution_no: str | None = None
    bank_transit_no: str | None = None
    bank_account_no: str | None = None
    cpp_exempt: bool | None = None
    ei_exempt: bool | None = None
    ei_rate_type: str | None = None
    province_of_taxation: str | None = None
    wcb_csst_exempt: bool | None = None
    td1_federal_credit: float | None = None
    td1_provincial_credit: float | None = None
    user_id: str | None = None
    sin: str | None = None


@router.patch("/{provider_id}", response_model=ProviderDetail)
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderDetail:
    p = (
        await db.execute(
            select(Provider).where(
                Provider.id == uuid.UUID(provider_id),
                Provider.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    if body.first_name is not None:
        p.first_name = body.first_name
    if body.last_name is not None:
        p.last_name = body.last_name
    if body.display_name is not None:
        p.display_name = body.display_name
    if body.provider_type is not None:
        try:
            p.provider_type = ProviderType(body.provider_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid provider_type")
    if body.job_title is not None:
        p.job_title = body.job_title
    if body.provider_code is not None:
        p.provider_code = body.provider_code
    if body.is_owner is not None:
        p.is_owner = body.is_owner
    if body.is_active is not None:
        p.is_active = body.is_active
    if body.booking_order is not None:
        p.booking_order = body.booking_order
    if body.has_appointments is not None:
        p.has_appointments = body.has_appointments
    if body.makes_appointments is not None:
        p.makes_appointments = body.makes_appointments
    if body.can_be_cashier is not None:
        p.can_be_cashier = body.can_be_cashier
    if body.online_booking_visibility is not None:
        try:
            p.online_booking_visibility = OnlineBookingVisibility(body.online_booking_visibility)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid online_booking_visibility")
    if body.sex is not None:
        p.sex = body.sex
    if body.personal_email is not None:
        p.personal_email = body.personal_email
    if body.cell_phone is not None:
        p.cell_phone = body.cell_phone
    if body.home_phone is not None:
        p.home_phone = body.home_phone
    if body.other_phone is not None:
        p.other_phone = body.other_phone
    if body.address_line is not None:
        p.address_line = body.address_line
    if body.city is not None:
        p.city = body.city
    if body.province is not None:
        p.province = body.province
    if body.postal_code is not None:
        p.postal_code = body.postal_code
    if body.birthday is not None:
        p.birthday = body.birthday
    if body.notes is not None:
        p.notes = body.notes
    if body.provider_photo_url is not None:
        p.provider_photo_url = body.provider_photo_url
    if body.hire_date is not None:
        p.hire_date = body.hire_date
    if body.first_day_worked is not None:
        p.first_day_worked = body.first_day_worked
    if body.certification is not None:
        p.certification = body.certification
    if body.sin is not None:
        p.sin_encrypted = body.sin
    if body.pay_type is not None:
        if body.pay_type == "":
            p.pay_type = None  # explicitly clear — N.A.
        else:
            try:
                p.pay_type = PayType(body.pay_type)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid pay_type")
    if body.pay_amount is not None:
        p.pay_amount = body.pay_amount
    if body.hourly_minimum is not None:
        p.hourly_minimum = body.hourly_minimum
    if body.vacation_pct is not None:
        p.vacation_pct = body.vacation_pct
    if body.retail_commission_pct is not None:
        p.retail_commission_pct = body.retail_commission_pct
    if body.commission_tiers is not None:
        p.commission_tiers = body.commission_tiers
    if body.bank_institution_no is not None:
        p.bank_institution_no = body.bank_institution_no
    if body.bank_transit_no is not None:
        p.bank_transit_no = body.bank_transit_no
    if body.bank_account_no is not None:
        p.bank_account_encrypted = body.bank_account_no
    if body.cpp_exempt is not None:
        p.cpp_exempt = body.cpp_exempt
    if body.ei_exempt is not None:
        p.ei_exempt = body.ei_exempt
    if body.ei_rate_type is not None:
        try:
            p.ei_rate_type = EIRateType(body.ei_rate_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ei_rate_type")
    if body.province_of_taxation is not None:
        p.province_of_taxation = body.province_of_taxation
    if body.wcb_csst_exempt is not None:
        p.wcb_csst_exempt = body.wcb_csst_exempt
    if body.td1_federal_credit is not None:
        p.td1_federal_credit = body.td1_federal_credit
    if body.td1_provincial_credit is not None:
        p.td1_provincial_credit = body.td1_provincial_credit
    if body.user_id is not None:
        p.user_id = uuid.UUID(body.user_id) if body.user_id else None

    await db.commit()
    await db.refresh(p)
    return _detail(p)


# ── DELETE /providers/{id} — deactivate ───────────────────────────────────────

@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_provider(
    provider_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    from datetime import datetime
    from app.models.appointment import Appointment, AppointmentItem, AppointmentStatus

    p = (
        await db.execute(
            select(Provider).where(
                Provider.id == uuid.UUID(provider_id),
                Provider.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    future_appts = (
        await db.execute(
            select(AppointmentItem).where(
                AppointmentItem.provider_id == p.id,
                AppointmentItem.tenant_id == current_user.tenant_id,
            ).join(Appointment, Appointment.id == AppointmentItem.appointment_id).where(
                Appointment.appointment_date >= datetime.combine(date.today(), datetime.min.time()),
                Appointment.status.in_([AppointmentStatus.confirmed, AppointmentStatus.in_progress]),
            )
        )
    ).scalars().all()
    if future_appts:
        raise HTTPException(
            status_code=409,
            detail="Cannot deactivate a provider with upcoming confirmed appointments — cancel them first",
        )

    p.is_active = False
    await db.commit()


# ── GET /providers/{id}/payroll ───────────────────────────────────────────────

class CommissionTierOut(BaseModel):
    monthly_threshold: float
    rate_pct: float


class PayrollOut(BaseModel):
    provider_id: str
    display_name: str
    year: int
    month: int
    pay_type: str | None

    # Hours
    scheduled_hours: float
    actual_hours: float
    hours_source: str   # "actual" | "scheduled"
    payroll_hours: float

    # Service revenue breakdown
    styling_revenue: float
    styling_item_count: int
    colour_revenue: float
    colour_item_count: int
    other_service_revenue: float
    gross_service_revenue: float

    # Product fees
    styling_product_fee: float
    colour_product_fee: float
    total_product_fees: float
    net_service_revenue: float

    # Commission
    commission_tier_applied: CommissionTierOut | None
    commission_on_services: float

    # Retail
    retail_revenue: float
    retail_commission: float

    # Pay comparison
    total_commission_pay: float
    hourly_minimum: float | None
    hourly_floor_amount: float

    pay_basis: str  # "commission" | "hourly" | "n/a"
    gross_before_vacation: float
    vacation_pct: float
    vacation_pay: float
    gross_pay: float


@router.get("/{provider_id}/payroll", response_model=PayrollOut)
async def get_payroll(
    provider_id: str,
    year: int,
    month: int,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PayrollOut:
    import calendar
    from decimal import Decimal as D

    tid = current_user.tenant_id
    pid = uuid.UUID(provider_id)

    p = (
        await db.execute(
            select(Provider).where(Provider.id == pid, Provider.tenant_id == tid)
        )
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    period_start = date(year, month, 1)
    period_end = date(year, month, calendar.monthrange(year, month)[1])
    line = await _calc_payroll_line(p, period_start, period_end, db, tid)

    return PayrollOut(
        provider_id=line.provider_id,
        display_name=p.display_name,
        year=year,
        month=month,
        pay_type=line.pay_type,
        scheduled_hours=line.scheduled_hours,
        actual_hours=line.actual_hours,
        hours_source=line.hours_source,
        payroll_hours=line.payroll_hours,
        styling_revenue=line.styling_revenue,
        styling_item_count=line.styling_item_count,
        colour_revenue=line.colour_revenue,
        colour_item_count=line.colour_item_count,
        other_service_revenue=0.0,
        gross_service_revenue=line.gross_service_revenue,
        styling_product_fee=line.styling_product_fee,
        colour_product_fee=line.colour_product_fee,
        total_product_fees=line.total_product_fees,
        net_service_revenue=line.net_service_revenue,
        commission_tier_applied=line.commission_tier_applied,
        commission_on_services=line.service_commission,
        retail_revenue=line.retail_revenue,
        retail_commission=line.retail_commission,
        total_commission_pay=line.service_commission + line.retail_commission,
        hourly_minimum=line.hourly_minimum,
        hourly_floor_amount=line.hourly_floor_amount,
        pay_basis=line.pay_basis,
        gross_before_vacation=line.gross_before_vacation,
        vacation_pct=line.vacation_pct,
        vacation_pay=line.vacation_pay,
        gross_pay=line.gross_pay,
    )
