"""
Sales — checkout / payment.

POST /sales                              — create + complete a Sale for an in_progress appointment
GET  /sales/by-appointment/{appt_id}     — get the completed Sale for an appointment (404 if none)

See docs/specs/P2-1-checkout-payment.md for the rule list and acceptance tests.
"""
import json
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import StaffUser
from app.email import email_cfg_from_row, send_email
from app.models.appointment import Appointment, AppointmentItem, AppointmentStatus
from app.models.client import Client
from app.models.email_config import TenantEmailConfig
from app.models.payment_method import PaymentMethodKind, TenantPaymentMethod
from app.models.printer import TenantPrinterConfig
from app.models.promotion import TenantPromotion
from app.models.provider import Provider
from app.models.retail import RetailItem, RetailStockMovement, StockMovementKind
from app.models.sale import (
    Payment,
    Sale,
    SaleAppointment,
    SaleItem,
    SaleItemKind,
    SalePaymentEdit,
    SaleStatus,
)
from app.models.service import Service, ServiceCategory
from app.models.tenant import Tenant

router = APIRouter(prefix="/sales", tags=["sales"])

GST_RATE = Decimal("0.05")
PST_RATE = Decimal("0.08")


def _money(value: Decimal | float | int | str) -> Decimal:
    """Normalise to 2-decimal Decimal with half-up rounding."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Request/response models ──────────────────────────────────────────────────

class SaleItemIn(BaseModel):
    # Exactly one of appointment_item_id or retail_item_id must be set
    appointment_item_id: str | None = None
    retail_item_id: str | None = None
    commission_provider_id: str | None = None  # which provider earns retail commission
    quantity: int = 1          # for retail items; always 1 for service items
    unit_price: Decimal
    discount_amount: Decimal = Decimal("0")
    promotion_id: str | None = None
    is_business_reimbursed: bool = False  # discount absorbed by salon; provider commissioned on full amount
    # Tax flags (passed from frontend; validated against retail item on backend for retail lines)
    is_gst_exempt: bool = False
    is_pst_exempt: bool = False


class PaymentIn(BaseModel):
    payment_method_id: str
    amount: Decimal
    cashback_amount: Decimal = Decimal("0")


class SaleIn(BaseModel):
    appointment_ids: list[str] = Field(min_length=1)
    notes: str | None = None
    items: list[SaleItemIn] = Field(min_length=1)
    payments: list[PaymentIn] = Field(min_length=1)


class SaleItemOut(BaseModel):
    id: str
    kind: str
    description: str
    provider_id: str | None
    provider_name: str | None
    sequence: int
    quantity: int
    unit_price: str
    discount_amount: str
    line_total: str
    is_business_reimbursed: bool
    promotion_id: str | None
    promotion_label: str | None
    product_fee: str | None  # service items only; None for retail


class PaymentOut(BaseModel):
    id: str
    payment_method_id: str
    payment_method_code: str
    payment_method_label: str
    amount: str
    cashback_amount: str


class SaleOut(BaseModel):
    id: str
    appointment_ids: list[str]
    client_id: str
    subtotal: str
    discount_total: str
    gst_amount: str
    pst_amount: str
    total: str
    status: str
    completed_at: datetime | None
    notes: str | None
    is_editable: bool
    items: list[SaleItemOut]
    payments: list[PaymentOut]


async def _enrich_items(
    items: list[SaleItem],
    db: AsyncSession,
) -> dict[uuid.UUID, tuple[str | None, str | None]]:
    """Return {item_id: (provider_name, product_fee_str)} for each item."""
    result: dict[uuid.UUID, tuple[str | None, str | None]] = {}

    provider_ids = {it.provider_id for it in items if it.provider_id}
    providers_by_id: dict[uuid.UUID, str] = {}
    if provider_ids:
        rows = (await db.execute(
            select(Provider.id, Provider.display_name).where(Provider.id.in_(provider_ids))
        )).all()
        providers_by_id = {r.id: r.display_name for r in rows}

    appt_item_ids = {it.appointment_item_id for it in items if it.appointment_item_id}
    fee_by_appt_item: dict[uuid.UUID, str] = {}
    if appt_item_ids:
        svc_rows = (await db.execute(
            select(
                AppointmentItem.id.label("appt_item_id"),
                Service.default_cost.label("default_cost"),
                ServiceCategory.name.label("cat_name"),
            )
            .join(Service, Service.id == AppointmentItem.service_id)
            .join(ServiceCategory, ServiceCategory.id == Service.category_id)
            .where(AppointmentItem.id.in_(appt_item_ids))
        )).all()
        for row in svc_rows:
            cat = (row.cat_name or "").lower()
            is_colour = "colour" in cat or "color" in cat or "colouring" in cat
            default_cost = Decimal(str(float(row.default_cost or 0)))
            fee_by_appt_item[row.appt_item_id] = (is_colour, default_cost)

    for it in items:
        pname = providers_by_id.get(it.provider_id) if it.provider_id else None
        product_fee: str | None = None
        if it.appointment_item_id and it.appointment_item_id in fee_by_appt_item:
            is_colour, default_cost = fee_by_appt_item[it.appointment_item_id]
            full_amount = Decimal(str(it.unit_price)) * Decimal(str(it.quantity))
            if is_colour:
                fee = full_amount * default_cost / Decimal("100")
            else:
                fee = default_cost * Decimal(str(it.quantity))
            product_fee = str(_money(fee)) if fee > 0 else None
        result[it.id] = (pname, product_fee)

    return result


def _serialize(
    sale: Sale,
    appointment_ids: list[str],
    items: list[SaleItem],
    payments: list[Payment],
    methods_by_id: dict[uuid.UUID, TenantPaymentMethod],
    promos_by_id: dict[uuid.UUID, TenantPromotion] | None = None,
    enrichment: dict[uuid.UUID, tuple[str | None, str | None]] | None = None,
) -> SaleOut:
    pb = promos_by_id or {}
    return SaleOut(
        id=str(sale.id),
        appointment_ids=appointment_ids,
        client_id=str(sale.client_id),
        subtotal=str(sale.subtotal),
        discount_total=str(sale.discount_total),
        gst_amount=str(sale.gst_amount),
        pst_amount=str(sale.pst_amount),
        total=str(sale.total),
        status=sale.status.value,
        completed_at=sale.completed_at,
        notes=sale.notes,
        is_editable=(
            sale.status == SaleStatus.completed
            and sale.completed_at is not None
            and sale.completed_at.date() == datetime.now(timezone.utc).date()
        ),
        items=[
            SaleItemOut(
                id=str(it.id),
                kind=it.kind.value,
                description=it.description,
                provider_id=str(it.provider_id) if it.provider_id else None,
                provider_name=(enrichment or {}).get(it.id, (None, None))[0],
                sequence=it.sequence,
                quantity=it.quantity,
                unit_price=str(it.unit_price),
                discount_amount=str(it.discount_amount),
                line_total=str(it.line_total),
                is_business_reimbursed=it.is_business_reimbursed,
                promotion_id=str(it.promotion_id) if it.promotion_id else None,
                promotion_label=pb[it.promotion_id].label if it.promotion_id and it.promotion_id in pb else None,
                product_fee=(enrichment or {}).get(it.id, (None, None))[1],
            )
            for it in items
        ],
        payments=[
            PaymentOut(
                id=str(p.id),
                payment_method_id=str(p.payment_method_id),
                payment_method_code=methods_by_id[p.payment_method_id].code,
                payment_method_label=methods_by_id[p.payment_method_id].label,
                amount=str(p.amount),
                cashback_amount=str(p.cashback_amount),
            )
            for p in payments
        ],
    )


# ── POST /sales ──────────────────────────────────────────────────────────────

@router.post("", response_model=SaleOut, status_code=status.HTTP_201_CREATED)
async def create_sale(
    body: SaleIn,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleOut:
    tid = current_user.tenant_id
    appt_uuids = [uuid.UUID(aid) for aid in body.appointment_ids]

    # Load all appointments
    appts = (
        await db.execute(
            select(Appointment).where(
                Appointment.id.in_(appt_uuids),
                Appointment.tenant_id == tid,
            )
        )
    ).scalars().all()
    if len(appts) != len(appt_uuids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more appointments not found")

    # R1 — all must be in_progress
    non_progress = [a for a in appts if a.status != AppointmentStatus.in_progress]
    if non_progress:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All appointments must be in progress to check out",
        )

    # R1b — all must be on the same business date
    dates = {a.appointment_date.date() for a in appts}
    if len(dates) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All appointments must be on the same business day",
        )

    # R2 — none may already have a completed sale (join through junction)
    existing = (
        await db.execute(
            select(SaleAppointment).where(
                SaleAppointment.appointment_id.in_(appt_uuids),
            ).join(Sale, Sale.id == SaleAppointment.sale_id).where(
                Sale.status == SaleStatus.completed,
            )
        )
    ).scalars().all()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="One or more appointments already have a completed sale")

    # Separate service vs retail items
    service_item_ids = [it.appointment_item_id for it in body.items if it.appointment_item_id]
    retail_item_ids_in = [it.retail_item_id for it in body.items if it.retail_item_id]

    # Load all appointment items across all appointments; validate R8
    appt_items = (
        await db.execute(
            select(AppointmentItem).where(
                AppointmentItem.appointment_id.in_(appt_uuids),
                AppointmentItem.tenant_id == tid,
            )
        )
    ).scalars().all()
    appt_item_map = {str(ai.id): ai for ai in appt_items}

    if set(service_item_ids) != set(appt_item_map.keys()):  # R8
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Sale must include exactly all service items across the selected appointments",
        )

    # Load retail items
    retail_item_map: dict[str, RetailItem] = {}
    if retail_item_ids_in:
        retail_rows = (
            await db.execute(
                select(RetailItem).where(
                    RetailItem.id.in_([uuid.UUID(rid) for rid in retail_item_ids_in]),
                    RetailItem.tenant_id == tid,
                )
            )
        ).scalars().all()
        retail_item_map = {str(r.id): r for r in retail_rows}

    # Validate per-line discount and price
    for in_item in body.items:
        if in_item.unit_price < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unit_price must be ≥ 0")
        if in_item.discount_amount < 0 or in_item.discount_amount > in_item.unit_price:  # R10
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="discount_amount must be between 0 and unit_price",
            )

    # Compute totals server-side with per-item tax flags (R11–R16). No tip — see P2-9.
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    gst_taxable = Decimal("0")
    pst_taxable = Decimal("0")
    line_records: list[tuple[SaleItemIn, Decimal]] = []

    for in_item in body.items:
        qty = max(1, in_item.quantity)
        unit = _money(in_item.unit_price)
        disc = _money(in_item.discount_amount)
        line_total = _money((unit - disc) * qty)
        subtotal += line_total
        discount_total += _money(disc * qty)
        # Retail: use item's own tax flags. Service: always taxable.
        if in_item.retail_item_id and in_item.retail_item_id in retail_item_map:
            ri = retail_item_map[in_item.retail_item_id]
            if not ri.is_gst_exempt:
                gst_taxable += line_total
            if not ri.is_pst_exempt:
                pst_taxable += line_total
        else:
            # Service items always taxable
            gst_taxable += line_total
            pst_taxable += line_total
        line_records.append((in_item, line_total))

    subtotal = _money(subtotal)
    discount_total = _money(discount_total)
    gst = _money(gst_taxable * GST_RATE)
    pst = _money(pst_taxable * PST_RATE)
    total = _money(subtotal + gst + pst)

    # R18 — (amount − cashback) summed across all payments must equal sale total.
    # Cashback is cash returned to the client out of the till; only the
    # post-cashback portion counts toward the bill. See P2-9 in docs/backlog.md.
    for p in body.payments:
        if p.amount <= 0:  # R19
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each payment amount must be > 0",
            )
        if p.cashback_amount < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="cashback_amount must be ≥ 0",
            )
        if p.cashback_amount > p.amount:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="cashback_amount cannot exceed payment amount",
            )

    applied_total = _money(sum((p.amount - p.cashback_amount for p in body.payments), Decimal("0")))
    if applied_total != total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Payments after cashback ({applied_total}) must equal sale total ({total})",
        )

    # Validate payment methods belong to this tenant and are active.
    method_uuids = {uuid.UUID(p.payment_method_id) for p in body.payments}
    methods = (
        await db.execute(
            select(TenantPaymentMethod).where(
                TenantPaymentMethod.tenant_id == tid,
                TenantPaymentMethod.id.in_(method_uuids),
            )
        )
    ).scalars().all()
    methods_by_id = {m.id: m for m in methods}
    if len(methods_by_id) != len(method_uuids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="One or more payment_method_id values are invalid for this tenant",
        )
    inactive = [m.label for m in methods if not m.is_active]
    if inactive:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Inactive payment method(s): {', '.join(inactive)}",
        )

    # Persist (R3 — atomic with appointment status)
    primary_appt = appts[0]
    sale = Sale(
        tenant_id=tid,
        client_id=primary_appt.client_id,
        subtotal=subtotal,
        discount_total=discount_total,
        gst_amount=gst,
        pst_amount=pst,
        total=total,
        status=SaleStatus.completed,
        completed_at=datetime.now(timezone.utc),
        completed_by_user_id=current_user.id,
        notes=body.notes,
    )
    db.add(sale)
    await db.flush()

    # Create junction rows linking each appointment to this sale
    for appt in appts:
        db.add(SaleAppointment(
            tenant_id=tid,
            sale_id=sale.id,
            appointment_id=appt.id,
        ))

    # Lookup service names for description snapshot
    service_ids = {ai.service_id for ai in appt_items}
    services = (
        await db.execute(select(Service).where(Service.id.in_(service_ids)))
    ).scalars().all()
    service_names = {s.id: s.name for s in services}

    # Validate promotion IDs if supplied
    promo_ids = {uuid.UUID(it.promotion_id) for it in body.items if it.promotion_id}
    promos_by_id: dict[uuid.UUID, TenantPromotion] = {}
    if promo_ids:
        promos = (
            await db.execute(
                select(TenantPromotion).where(
                    TenantPromotion.id.in_(promo_ids),
                    TenantPromotion.tenant_id == tid,
                )
            )
        ).scalars().all()
        promos_by_id = {p.id: p for p in promos}

    sale_items: list[SaleItem] = []
    seq = 1
    for in_item, line_total in line_records:
        promo_uuid = uuid.UUID(in_item.promotion_id) if in_item.promotion_id else None

        qty = max(1, in_item.quantity)
        if in_item.appointment_item_id:
            ai = appt_item_map[in_item.appointment_item_id]
            si = SaleItem(
                tenant_id=tid,
                sale_id=sale.id,
                kind=SaleItemKind.service,
                appointment_item_id=ai.id,
                description=service_names.get(ai.service_id, "Service"),
                provider_id=ai.provider_id,
                promotion_id=promo_uuid if promo_uuid and promo_uuid in promos_by_id else None,
                sequence=seq,
                quantity=1,
                unit_price=_money(in_item.unit_price),
                discount_amount=_money(in_item.discount_amount),
                line_total=line_total,
                is_business_reimbursed=in_item.is_business_reimbursed,
            )
        else:
            ri = retail_item_map.get(in_item.retail_item_id or "")
            desc = ri.name if ri else "Retail item"
            if qty > 1:
                desc = f"{desc} ×{qty}"
            si = SaleItem(
                tenant_id=tid,
                sale_id=sale.id,
                kind=SaleItemKind.retail,
                retail_item_id=uuid.UUID(in_item.retail_item_id) if in_item.retail_item_id else None,
                retail_item_name=ri.name if ri else "Retail item",
                description=desc,
                provider_id=uuid.UUID(in_item.commission_provider_id) if in_item.commission_provider_id else None,
                promotion_id=promo_uuid if promo_uuid and promo_uuid in promos_by_id else None,
                sequence=seq,
                quantity=qty,
                unit_price=_money(in_item.unit_price),
                discount_amount=_money(in_item.discount_amount),
                line_total=line_total,
                is_business_reimbursed=in_item.is_business_reimbursed,
            )
        db.add(si)
        sale_items.append(si)
        seq += 1

    # Write sell movements for retail lines (atomic with the sale)
    await db.flush()  # ensure si.id is populated
    for si in sale_items:
        if si.kind == SaleItemKind.retail and si.retail_item_id is not None:
            db.add(RetailStockMovement(
                tenant_id=tid,
                retail_item_id=si.retail_item_id,
                kind=StockMovementKind.sell,
                quantity=-si.quantity,
                sale_item_id=si.id,
                created_by_user_id=current_user.id,
            ))

    sale_payments: list[Payment] = []
    for in_pay in body.payments:
        sp = Payment(
            tenant_id=tid,
            sale_id=sale.id,
            payment_method_id=uuid.UUID(in_pay.payment_method_id),
            amount=_money(in_pay.amount),
            cashback_amount=_money(in_pay.cashback_amount),
        )
        db.add(sp)
        sale_payments.append(sp)

    # Transition all appointments to completed atomically
    for appt in appts:
        appt.status = AppointmentStatus.completed

    # Adjust client.account_balance for any on-account payments.
    # On account = client owes the salon → balance decreases (more negative).
    on_account_total = _money(sum(
        sp.amount
        for sp in sale_payments
        if methods_by_id[sp.payment_method_id].kind == PaymentMethodKind.on_account
    ))
    if on_account_total > 0 and primary_appt.client_id:
        client = await db.get(Client, primary_appt.client_id)
        if client:
            client.account_balance = (client.account_balance or Decimal("0")) - on_account_total

    await db.commit()
    await db.refresh(sale)
    return _serialize(sale, [str(a.id) for a in appts], sale_items, sale_payments, methods_by_id, promos_by_id)


# ── GET /sales ───────────────────────────────────────────────────────────────

class SaleListItem(BaseModel):
    id: str
    client_id: str
    client_name: str
    completed_at: datetime | None
    total: str
    item_descriptions: list[str]
    payment_labels: list[str]


@router.get("", response_model=list[SaleListItem])
async def list_sales(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    date_from: date | None = None,
    date_to: date | None = None,
    client_search: str | None = None,
) -> list[SaleListItem]:
    tid = current_user.tenant_id
    q = (
        select(Sale, Client)
        .join(Client, Client.id == Sale.client_id)
        .where(Sale.tenant_id == tid, Sale.status == SaleStatus.completed)
    )
    if date_from:
        q = q.where(func.date(Sale.completed_at) >= date_from)
    if date_to:
        q = q.where(func.date(Sale.completed_at) <= date_to)
    if client_search:
        term = f"%{client_search}%"
        q = q.where(
            or_(Client.first_name.ilike(term), Client.last_name.ilike(term))
        )
    q = q.order_by(Sale.completed_at.desc()).limit(500)

    rows = (await db.execute(q)).all()
    if not rows:
        return []

    sale_ids = [r.Sale.id for r in rows]

    items_rows = (await db.execute(
        select(SaleItem.sale_id, SaleItem.description)
        .where(SaleItem.sale_id.in_(sale_ids))
        .order_by(SaleItem.sale_id, SaleItem.sequence)
    )).all()
    items_by_sale: dict[uuid.UUID, list[str]] = {}
    for r in items_rows:
        items_by_sale.setdefault(r.sale_id, []).append(r.description)

    payment_rows = (await db.execute(
        select(Payment.sale_id, TenantPaymentMethod.label)
        .join(TenantPaymentMethod, TenantPaymentMethod.id == Payment.payment_method_id)
        .where(Payment.sale_id.in_(sale_ids))
    )).all()
    payments_by_sale: dict[uuid.UUID, list[str]] = {}
    for r in payment_rows:
        payments_by_sale.setdefault(r.sale_id, []).append(r.label)

    return [
        SaleListItem(
            id=str(r.Sale.id),
            client_id=str(r.Sale.client_id),
            client_name=f"{r.Client.first_name} {r.Client.last_name}".strip(),
            completed_at=r.Sale.completed_at,
            total=str(r.Sale.total),
            item_descriptions=items_by_sale.get(r.Sale.id, []),
            payment_labels=list(dict.fromkeys(payments_by_sale.get(r.Sale.id, []))),
        )
        for r in rows
    ]


# ── GET /sales/{sale_id} ─────────────────────────────────────────────────────

@router.get("/{sale_id}", response_model=SaleOut)
async def get_sale(
    sale_id: str,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleOut:
    tid = current_user.tenant_id
    sale = (await db.execute(
        select(Sale).where(Sale.id == uuid.UUID(sale_id), Sale.tenant_id == tid,
                           Sale.status == SaleStatus.completed)
    )).scalar_one_or_none()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    all_junctions = (await db.execute(
        select(SaleAppointment).where(SaleAppointment.sale_id == sale.id)
    )).scalars().all()
    appt_ids = [str(j.appointment_id) for j in all_junctions]

    items = (await db.execute(
        select(SaleItem).where(SaleItem.sale_id == sale.id).order_by(SaleItem.sequence)
    )).scalars().all()
    payments = (await db.execute(
        select(Payment).where(Payment.sale_id == sale.id)
    )).scalars().all()
    method_ids = {p.payment_method_id for p in payments}
    methods = (await db.execute(
        select(TenantPaymentMethod).where(TenantPaymentMethod.id.in_(method_ids))
    )).scalars().all() if method_ids else []
    methods_by_id = {m.id: m for m in methods}
    enrichment = await _enrich_items(list(items), db)
    return _serialize(sale, appt_ids, list(items), list(payments), methods_by_id, enrichment=enrichment)


# ── GET /sales/by-appointment/{appointment_id} ────────────────────────────────

@router.get("/by-appointment/{appointment_id}", response_model=SaleOut)
async def get_sale_by_appointment(
    appointment_id: str,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleOut:
    tid = current_user.tenant_id
    junction = (
        await db.execute(
            select(SaleAppointment).where(
                SaleAppointment.appointment_id == uuid.UUID(appointment_id),
            )
        )
    ).scalar_one_or_none()
    if junction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No sale for this appointment")

    sale = (
        await db.execute(
            select(Sale).where(Sale.id == junction.sale_id, Sale.tenant_id == tid, Sale.status == SaleStatus.completed)
        )
    ).scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No sale for this appointment")

    # All appointment_ids linked to this sale
    all_junctions = (
        await db.execute(select(SaleAppointment).where(SaleAppointment.sale_id == sale.id))
    ).scalars().all()
    appt_ids = [str(j.appointment_id) for j in all_junctions]

    items = (await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id).order_by(SaleItem.sequence))).scalars().all()
    payments = (await db.execute(select(Payment).where(Payment.sale_id == sale.id))).scalars().all()
    method_ids = {p.payment_method_id for p in payments}
    methods = (
        await db.execute(select(TenantPaymentMethod).where(TenantPaymentMethod.id.in_(method_ids)))
    ).scalars().all() if method_ids else []
    methods_by_id = {m.id: m for m in methods}
    enrichment = await _enrich_items(list(items), db)
    return _serialize(sale, appt_ids, list(items), list(payments), methods_by_id, enrichment=enrichment)


# ── POST /sales/{sale_id}/send-receipt ────────────────────────────────────────

class SendReceiptIn(BaseModel):
    to: str  # recipient email


@router.post("/{sale_id}/send-receipt", status_code=status.HTTP_204_NO_CONTENT)
async def send_receipt(
    sale_id: str,
    body: SendReceiptIn,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    tid = current_user.tenant_id

    sale = (
        await db.execute(
            select(Sale).where(Sale.id == uuid.UUID(sale_id), Sale.tenant_id == tid)
        )
    ).scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")

    items = (
        await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id).order_by(SaleItem.sequence))
    ).scalars().all()

    payments = (
        await db.execute(select(Payment).where(Payment.sale_id == sale.id))
    ).scalars().all()
    method_ids = {p.payment_method_id for p in payments}
    methods = (
        await db.execute(select(TenantPaymentMethod).where(TenantPaymentMethod.id.in_(method_ids)))
    ).scalars().all() if method_ids else []
    methods_by_id = {m.id: m for m in methods}

    tenant = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()

    cfg_row = (
        await db.execute(select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tid))
    ).scalar_one_or_none()
    if cfg_row is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Email not configured — set up SMTP in Settings → Email first")

    smtp = email_cfg_from_row(cfg_row)

    client = await db.get(Client, sale.client_id) if sale.client_id else None
    next_appt = await _next_appointment_str(sale.client_id, tid, db) if sale.client_id else None

    items_html = "".join(
        f"<tr><td style='padding:4px 0;'>{it.description}</td>"
        f"<td style='padding:4px 0;text-align:right;'>${it.line_total}</td></tr>"
        for it in items
    )
    payments_html = "".join(
        f"<tr><td style='padding:4px 0;color:#555;'>{methods_by_id[p.payment_method_id].label}</td>"
        f"<td style='padding:4px 0;text-align:right;'>${p.amount}</td></tr>"
        for p in payments if p.payment_method_id in methods_by_id
    )
    sale_date = sale.completed_at.strftime("%B %d, %Y") if sale.completed_at else ""

    greeting = f"<p>Hi {client.first_name},</p>" if client else ""
    next_appt_html = (
        f"<p style='margin:16px 0;color:#555;'>Your next appointment:<br>"
        f"<strong>{next_appt}</strong></p>"
    ) if next_appt else ""

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
      <h2 style="margin-top:0;">{tenant.name}</h2>
      <p style="color:#555;margin-top:0;">{sale_date}</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
        {items_html}
        <tr><td colspan="2" style="border-top:1px solid #eee;padding:4px 0;"></td></tr>
        <tr><td style="padding:4px 0;color:#555;">Subtotal</td>
            <td style="padding:4px 0;text-align:right;">${sale.subtotal}</td></tr>
        <tr><td style="padding:4px 0;color:#555;">GST (5%)</td>
            <td style="padding:4px 0;text-align:right;">${sale.gst_amount}</td></tr>
        <tr><td style="padding:4px 0;color:#555;">PST (8%)</td>
            <td style="padding:4px 0;text-align:right;">${sale.pst_amount}</td></tr>
        <tr style="font-weight:600;">
            <td style="padding:8px 0;border-top:1px solid #eee;">Total</td>
            <td style="padding:8px 0;border-top:1px solid #eee;text-align:right;">${sale.total}</td></tr>
      </table>
      <p style="color:#555;font-size:14px;">Paid by:</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
        {payments_html}
      </table>
      {greeting}
      {next_appt_html}
      <p style="color:#aaa;font-size:12px;">Thank you for visiting {tenant.name}.</p>
    </div>"""

    try:
        await send_email(smtp, body.to, f"Your receipt from {tenant.name}", html)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── PATCH /sales/{sale_id}/payments ──────────────────────────────────────────

class EditPaymentIn(BaseModel):
    payment_method_id: str
    amount: Decimal
    cashback_amount: Decimal = Decimal("0")


class EditPaymentsIn(BaseModel):
    payments: list[EditPaymentIn] = Field(min_length=1)


@router.patch("/{sale_id}/payments", response_model=SaleOut)
async def edit_sale_payments(
    sale_id: str,
    body: EditPaymentsIn,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleOut:
    tid = current_user.tenant_id

    sale = (
        await db.execute(
            select(Sale).where(Sale.id == uuid.UUID(sale_id), Sale.tenant_id == tid)
        )
    ).scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")
    if sale.status != SaleStatus.completed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Only completed sales can have their payments edited")
    if sale.completed_at is None or sale.completed_at.date() != datetime.now(timezone.utc).date():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Payments can only be edited on the day the sale was completed")

    # Validate payment methods belong to this tenant
    method_ids = [uuid.UUID(p.payment_method_id) for p in body.payments]
    methods = (
        await db.execute(
            select(TenantPaymentMethod).where(
                TenantPaymentMethod.id.in_(method_ids),
                TenantPaymentMethod.tenant_id == tid,
            )
        )
    ).scalars().all()
    if len(methods) != len(set(method_ids)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="One or more payment methods are invalid")
    methods_by_id = {m.id: m for m in methods}

    # Validate amounts
    for p in body.payments:
        if p.cashback_amount < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="cashback_amount must be ≥ 0")
        if p.cashback_amount > p.amount:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="cashback_amount cannot exceed payment amount")

    applied = _money(sum(p.amount - p.cashback_amount for p in body.payments))
    if applied != sale.total:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Payments after cashback ({applied}) must equal sale total ({sale.total})")

    # Snapshot existing payments for audit log
    existing_payments = (
        await db.execute(select(Payment).where(Payment.sale_id == sale.id))
    ).scalars().all()
    before_json = json.dumps([
        {"payment_method_id": str(p.payment_method_id),
         "amount": str(p.amount),
         "cashback_amount": str(p.cashback_amount)}
        for p in existing_payments
    ])

    # Replace payment rows atomically
    await db.execute(delete(Payment).where(Payment.sale_id == sale.id))
    new_payments = [
        Payment(
            tenant_id=tid,
            sale_id=sale.id,
            payment_method_id=uuid.UUID(p.payment_method_id),
            amount=_money(p.amount),
            cashback_amount=_money(p.cashback_amount),
        )
        for p in body.payments
    ]
    db.add_all(new_payments)

    after_json = json.dumps([
        {"payment_method_id": str(p.payment_method_id),
         "amount": str(p.amount),
         "cashback_amount": str(p.cashback_amount)}
        for p in body.payments
    ])

    db.add(SalePaymentEdit(
        tenant_id=tid,
        sale_id=sale.id,
        edited_by_user_id=current_user.id,
        edited_at=datetime.now(timezone.utc),
        before_json=before_json,
        after_json=after_json,
    ))

    await db.commit()
    await db.refresh(sale)

    all_junctions = (
        await db.execute(select(SaleAppointment).where(SaleAppointment.sale_id == sale.id))
    ).scalars().all()
    appt_ids = [str(j.appointment_id) for j in all_junctions]

    items = (
        await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id).order_by(SaleItem.sequence))
    ).scalars().all()
    refreshed_payments = (
        await db.execute(select(Payment).where(Payment.sale_id == sale.id))
    ).scalars().all()

    return _serialize(sale, appt_ids, list(items), list(refreshed_payments), methods_by_id)


# ── PATCH /sales/{sale_id}/items/{item_id} ────────────────────────────────────

class SaleItemPatch(BaseModel):
    discount_amount: Decimal | None = None
    is_business_reimbursed: bool | None = None


@router.patch("/{sale_id}/items/{item_id}", response_model=SaleOut)
async def patch_sale_item(
    sale_id: str,
    item_id: str,
    body: SaleItemPatch,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleOut:
    """Edit discount and/or business-reimbursed flag on a completed sale item."""
    tid = current_user.tenant_id

    sale = (await db.execute(
        select(Sale).where(Sale.id == uuid.UUID(sale_id), Sale.tenant_id == tid,
                           Sale.status == SaleStatus.completed)
    )).scalar_one_or_none()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    item = (await db.execute(
        select(SaleItem).where(SaleItem.id == uuid.UUID(item_id), SaleItem.sale_id == sale.id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Sale item not found")

    old_line_total = item.line_total

    if body.discount_amount is not None:
        item.discount_amount = _money(body.discount_amount)
        # Recalculate line total: (unit_price - discount) × quantity
        item.line_total = _money(
            max(Decimal("0"), item.unit_price - item.discount_amount) * item.quantity
        )

    if body.is_business_reimbursed is not None:
        item.is_business_reimbursed = body.is_business_reimbursed

    # Adjust sale subtotal and total for the line_total change
    delta = item.line_total - old_line_total
    if delta != 0:
        sale.subtotal = _money(sale.subtotal + delta)
        sale.total = _money(sale.total + delta)

    sale.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sale)

    items = (await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))).scalars().all()
    payments = (await db.execute(select(Payment).where(Payment.sale_id == sale.id))).scalars().all()
    method_ids = {p.payment_method_id for p in payments}
    methods = (await db.execute(
        select(TenantPaymentMethod).where(TenantPaymentMethod.id.in_(method_ids))
    )).scalars().all()
    methods_by_id = {m.id: m for m in methods}
    appt_ids = [str(r.appointment_id) for r in (await db.execute(
        select(SaleAppointment).where(SaleAppointment.sale_id == sale.id)
    )).scalars().all()]

    return _serialize(sale, appt_ids, list(items), list(payments), methods_by_id)


# ── Helpers shared by receipt-data and send-receipt ──────────────────────────

async def _next_appointment_str(
    client_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> str | None:
    """Return 'Tuesday, May 20 at 2:00 PM' for the client's next upcoming appointment."""
    from datetime import date as ddate
    row = (await db.execute(
        select(Appointment, AppointmentItem, Service)
        .join(AppointmentItem, AppointmentItem.appointment_id == Appointment.id)
        .join(Service, Service.id == AppointmentItem.service_id)
        .where(
            Appointment.client_id == client_id,
            Appointment.tenant_id == tenant_id,
            Appointment.status.in_([AppointmentStatus.requested, AppointmentStatus.confirmed]),
            Appointment.appointment_date >= ddate.today(),
        )
        .order_by(Appointment.appointment_date.asc(), AppointmentItem.start_time.asc())
        .limit(1)
    )).first()
    if not row:
        return None
    appt, ai, svc = row
    appt_date = appt.appointment_date.strftime("%A, %B %-d")
    start_dt = ai.start_time
    if start_dt:
        hour = start_dt.hour
        minute = start_dt.minute
        ampm = "AM" if hour < 12 else "PM"
        h12 = hour % 12 or 12
        time_str = f"{h12}:{minute:02d} {ampm}"
        return f"{appt_date} at {time_str}"
    return appt_date


# ── GET /sales/{sale_id}/receipt-data ────────────────────────────────────────

class ReceiptItemOut(BaseModel):
    description: str
    quantity: int
    line_total: str


class ReceiptPaymentOut(BaseModel):
    label: str
    amount: str
    is_cash: bool


class ReceiptDataOut(BaseModel):
    sale_id: str
    completed_at: str
    salon_name: str
    address: str | None
    phone: str | None
    booking_email: str | None
    website: str | None
    receipt_logo_url: str | None
    client_first_name: str | None
    next_appointment: str | None
    items: list[ReceiptItemOut]
    subtotal: str
    gst_amount: str
    pst_amount: str
    total: str
    payments: list[ReceiptPaymentOut]
    printer_name: str
    cash_drawer_enabled: bool
    auto_print_on_cash: bool
    has_cash_payment: bool


@router.get("/{sale_id}/receipt-data", response_model=ReceiptDataOut)
async def get_receipt_data(
    sale_id: str,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReceiptDataOut:
    tid = current_user.tenant_id

    sale = (await db.execute(
        select(Sale).where(Sale.id == uuid.UUID(sale_id), Sale.tenant_id == tid,
                           Sale.status == SaleStatus.completed)
    )).scalar_one_or_none()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    items = (await db.execute(
        select(SaleItem).where(SaleItem.sale_id == sale.id).order_by(SaleItem.sequence)
    )).scalars().all()

    payments = (await db.execute(
        select(Payment).where(Payment.sale_id == sale.id)
    )).scalars().all()
    method_ids = {p.payment_method_id for p in payments}
    methods = (await db.execute(
        select(TenantPaymentMethod).where(TenantPaymentMethod.id.in_(method_ids))
    )).scalars().all() if method_ids else []
    methods_by_id = {m.id: m for m in methods}

    tenant = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()

    client = await db.get(Client, sale.client_id) if sale.client_id else None

    printer_cfg = (await db.execute(
        select(TenantPrinterConfig).where(TenantPrinterConfig.tenant_id == tid)
    )).scalar_one_or_none()

    address_parts = [
        tenant.address_line1, tenant.address_line2,
        f"{tenant.city}, {tenant.region} {tenant.postal_code}".strip(", ") if tenant.city else None,
    ]
    address = ", ".join(p for p in address_parts if p) or None

    next_appt = await _next_appointment_str(sale.client_id, tid, db) if sale.client_id else None

    cash_method_ids = {
        m.id for m in methods if m.kind == PaymentMethodKind.cash
    }
    has_cash = any(p.payment_method_id in cash_method_ids for p in payments)

    completed_str = sale.completed_at.strftime("%m/%d/%Y    %H:%M") if sale.completed_at else ""

    return ReceiptDataOut(
        sale_id=str(sale.id),
        completed_at=completed_str,
        salon_name=tenant.name,
        address=address,
        phone=tenant.phone,
        booking_email=tenant.booking_email,
        website=tenant.website,
        receipt_logo_url=printer_cfg.receipt_logo_url if printer_cfg else None,
        client_first_name=client.first_name if client else None,
        next_appointment=next_appt,
        items=[
            ReceiptItemOut(
                description=it.description,
                quantity=it.quantity,
                line_total=str(it.line_total),
            )
            for it in items
        ],
        subtotal=str(sale.subtotal),
        gst_amount=str(sale.gst_amount),
        pst_amount=str(sale.pst_amount),
        total=str(sale.total),
        payments=[
            ReceiptPaymentOut(
                label=(
                    methods_by_id[p.payment_method_id].label
                    if p.payment_method_id in methods_by_id else "Payment"
                ),
                amount=str(p.amount),
                is_cash=p.payment_method_id in cash_method_ids,
            )
            for p in payments
        ],
        printer_name=printer_cfg.printer_name if printer_cfg else "EPSON TM-T88V Receipt",
        cash_drawer_enabled=printer_cfg.cash_drawer_enabled if printer_cfg else False,
        auto_print_on_cash=printer_cfg.auto_print_on_cash if printer_cfg else False,
        has_cash_payment=has_cash,
    )
