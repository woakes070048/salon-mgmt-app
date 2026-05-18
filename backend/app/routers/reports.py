import uuid  # noqa
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import StaffUser
from app.models.payment_method import TenantPaymentMethod
from app.models.provider import Provider
from app.models.cash_reconciliation import CashReconciliation, PettyCashEntry
from app.models.sale import Payment, Sale, SaleItem, SaleItemKind, SaleStatus

router = APIRouter(prefix="/reports", tags=["reports"])


def _d(val: Decimal | None) -> str:
    return str(val or Decimal("0"))


# ── GET /reports/monthly ──────────────────────────────────────────────────────

class ProviderRow(BaseModel):
    provider_name: str
    total: str
    sale_count: int


class PaymentMethodRow(BaseModel):
    label: str
    gross: str
    cashback: str
    net: str


class DayRow(BaseModel):
    date: str        # "YYYY-MM-DD"
    sale_count: int
    total: str


class MonthlyReport(BaseModel):
    year: int
    month: int
    sale_count: int
    subtotal: str
    discount_total: str
    gst_amount: str
    pst_amount: str
    total: str
    service_gross: str
    service_discount: str
    service_total: str
    retail_gross: str
    retail_discount: str
    retail_total: str
    retail_returns: str
    gift_card_total: str
    on_account_sales: str
    on_account_payments: str
    petty_cash_total: str
    by_provider: list[ProviderRow]
    by_payment_method: list[PaymentMethodRow]
    by_day: list[DayRow]


@router.get("/monthly", response_model=MonthlyReport)
async def monthly_report(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
) -> MonthlyReport:
    tid = current_user.tenant_id
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    _, last_day = monthrange(year, month)
    end_month = month + 1 if month < 12 else 1
    end_year = year if month < 12 else year + 1
    end = datetime(end_year, end_month, 1, tzinfo=timezone.utc)

    completed = (
        Sale.tenant_id == tid,
        Sale.status == SaleStatus.completed,
        Sale.completed_at >= start,
        Sale.completed_at < end,
    )

    # ── Overall totals ────────────────────────────────────────────────────────
    totals_row = (
        await db.execute(
            select(
                func.count(Sale.id),
                func.coalesce(func.sum(Sale.subtotal), 0),
                func.coalesce(func.sum(Sale.discount_total), 0),
                func.coalesce(func.sum(Sale.gst_amount), 0),
                func.coalesce(func.sum(Sale.pst_amount), 0),
                func.coalesce(func.sum(Sale.total), 0),
            ).where(*completed)
        )
    ).one()
    sale_count, subtotal, discount_total, gst, pst, total = totals_row

    # ── Service vs retail split (net line_total + gross + discount per stream) ─
    # Milano retail returns have both unit_price and quantity negative, making
    # line_total positive. Correct by negating when quantity < 0.
    _signed_lt = case(
        (SaleItem.quantity < 0, -func.abs(SaleItem.line_total)),
        else_=SaleItem.line_total,
    )
    _signed_gross = case(
        (SaleItem.quantity < 0, -func.abs(SaleItem.unit_price * SaleItem.quantity)),
        else_=SaleItem.unit_price * SaleItem.quantity,
    )
    _is_gift_card = or_(
        func.lower(SaleItem.description).contains("gift card"),
        func.lower(SaleItem.description).contains("gift certificate"),
        func.lower(SaleItem.description).contains("gift card/certificate"),
    )
    kind_rows = (
        await db.execute(
            select(
                SaleItem.kind,
                func.coalesce(func.sum(_signed_lt), 0),
                func.coalesce(func.sum(_signed_gross), 0),
                func.coalesce(func.sum(SaleItem.discount_amount * SaleItem.quantity), 0),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*completed, ~_is_gift_card)
            .group_by(SaleItem.kind)
        )
    ).all()
    service_total = service_gross = service_discount = Decimal("0")
    retail_total = retail_gross = retail_discount = Decimal("0")
    for kind, net, gross, disc in kind_rows:
        if kind == SaleItemKind.service:
            service_total = Decimal(str(net))
            service_gross = Decimal(str(gross))
            service_discount = Decimal(str(disc))
        else:
            retail_total = Decimal(str(net))
            retail_gross = Decimal(str(gross))
            retail_discount = Decimal(str(disc))

    # ── Petty cash disbursed in the period ────────────────────────────────────
    petty_cash_total = Decimal(str(
        (
            await db.execute(
                select(func.coalesce(func.sum(PettyCashEntry.amount), 0))
                .join(CashReconciliation, CashReconciliation.id == PettyCashEntry.reconciliation_id)
                .where(
                    CashReconciliation.tenant_id == tid,
                    CashReconciliation.business_date >= date(year, month, 1),
                    CashReconciliation.business_date <= date(year, month, last_day),
                )
            )
        ).scalar() or 0
    ))

    # ── Retail returns (items with negative quantity — returned product + tax) ─────
    # Milano encodes returns with both unit_price and quantity negative, so
    # line_total ends up positive. The returned amount includes tax (customer gets
    # back what they paid), so we sum abs(line_total) × (1 + GST + PST) per item,
    # weighted by the item's proportional share of the sale's actual tax.
    return_rows = (
        await db.execute(
            select(
                func.abs(SaleItem.line_total).label("product"),
                Sale.subtotal.label("sale_sub"),
                Sale.gst_amount.label("sale_gst"),
                Sale.pst_amount.label("sale_pst"),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                *completed,
                SaleItem.kind == SaleItemKind.retail,
                SaleItem.quantity < 0,
                ~_is_gift_card,
            )
        )
    ).all()
    retail_returns = Decimal("0")
    for rr in return_rows:
        product = Decimal(str(rr.product))
        sub = Decimal(str(rr.sale_sub)) if rr.sale_sub else Decimal("1")
        pct = product / sub if sub else Decimal("0")
        tax = pct * (Decimal(str(rr.sale_gst)) + Decimal(str(rr.sale_pst)))
        retail_returns += product + tax

    # ── Gift card sales (retail items whose description mentions gift/g.c.) ────
    gift_card_total = Decimal(str(
        (
            await db.execute(
                select(func.coalesce(func.sum(SaleItem.line_total), 0))
                .join(Sale, Sale.id == SaleItem.sale_id)
                .where(
                    *completed,
                    or_(
                        func.lower(SaleItem.description).contains("gift card"),
                        func.lower(SaleItem.description).contains("gift certificate"),
                        func.lower(SaleItem.description).contains("gift card/certificate"),
                    ),
                )
            )
        ).scalar() or 0
    ))

    # ── On account sales (payments made via on_account payment method) ───────────
    on_account_sales = Decimal(str(
        (
            await db.execute(
                select(func.coalesce(func.sum(Payment.amount), 0))
                .join(Sale, Sale.id == Payment.sale_id)
                .join(TenantPaymentMethod, TenantPaymentMethod.id == Payment.payment_method_id)
                .where(
                    *completed,
                    TenantPaymentMethod.kind == "on_account",
                )
            )
        ).scalar() or 0
    ))
    # On account payments received: needs a dedicated ledger — placeholder for now
    on_account_payments = Decimal("0")

    # ── By provider (service items only) ─────────────────────────────────────
    provider_rows = (
        await db.execute(
            select(
                Provider.display_name,
                func.coalesce(func.sum(SaleItem.line_total), 0),
                func.count(func.distinct(Sale.id)),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Provider, Provider.id == SaleItem.provider_id)
            .where(*completed, SaleItem.kind == SaleItemKind.service)
            .group_by(Provider.id, Provider.display_name)
            .order_by(func.sum(SaleItem.line_total).desc())
        )
    ).all()

    # ── By payment method ─────────────────────────────────────────────────────
    # Prefer historical (Milano) data for periods where all payments are "unknown".
    # This backfills the payment breakdown for months before SalonOS went live.
    payment_rows = (
        await db.execute(
            select(
                TenantPaymentMethod.label,
                func.coalesce(func.sum(Payment.amount), 0),
                func.coalesce(func.sum(Payment.cashback_amount), 0),
            )
            .join(Sale, Sale.id == Payment.sale_id)
            .join(TenantPaymentMethod, TenantPaymentMethod.id == Payment.payment_method_id)
            .where(*completed)
            .group_by(TenantPaymentMethod.id, TenantPaymentMethod.label)
            .order_by(func.sum(Payment.amount).desc())
        )
    ).all()

    # If every payment is "unknown" (imported historical data), fall back to
    # the historical_payment_summary table if it has data for this period.
    # Special labels ON_ACCOUNT_SALES / ON_ACCOUNT_PAYMENTS are routed to
    # the on_account fields, not the payment method list.
    all_unknown = all(r[0].lower() in ("unknown", "on account") for r in payment_rows)
    if all_unknown:
        from sqlalchemy import text as _sql
        hist_rows = (await db.execute(
            _sql("SELECT label, amount FROM historical_payment_summary "
                 "WHERE tenant_id = :tid AND year = :y AND month = :m "
                 "ORDER BY amount DESC"),
            {"tid": tid, "y": year, "m": month},
        )).fetchall()
        if hist_rows:
            payment_rows = [
                (r.label, r.amount, 0) for r in hist_rows
                if r.label not in ("ON_ACCOUNT_SALES", "ON_ACCOUNT_PAYMENTS")
            ]
            # Override on_account figures from historical data
            for r in hist_rows:
                if r.label == "ON_ACCOUNT_SALES":
                    on_account_sales = Decimal(str(r.amount))
                elif r.label == "ON_ACCOUNT_PAYMENTS":
                    on_account_payments = Decimal(str(r.amount))

    # ── By day ────────────────────────────────────────────────────────────────
    day_rows = (
        await db.execute(
            select(
                func.date(Sale.completed_at).label("day"),
                func.count(Sale.id),
                func.coalesce(func.sum(Sale.total), 0),
            )
            .where(*completed)
            .group_by(func.date(Sale.completed_at))
            .order_by(func.date(Sale.completed_at))
        )
    ).all()

    # Use item-level total for "before tax" so service + retail + gift_card adds up correctly
    before_tax = service_total + retail_total

    return MonthlyReport(
        year=year,
        month=month,
        sale_count=sale_count,
        subtotal=_d(before_tax),
        discount_total=_d(discount_total),
        gst_amount=_d(gst),
        pst_amount=_d(pst),
        total=_d(total),
        service_gross=_d(service_gross),
        service_discount=_d(service_discount),
        service_total=_d(service_total),
        retail_gross=_d(retail_gross),
        retail_discount=_d(retail_discount),
        retail_total=_d(retail_total),
        retail_returns=_d(retail_returns),
        gift_card_total=_d(gift_card_total),
        on_account_sales=_d(on_account_sales),
        on_account_payments=_d(on_account_payments),
        petty_cash_total=_d(petty_cash_total),
        by_provider=[
            ProviderRow(provider_name=name, total=_d(amt), sale_count=cnt)
            for name, amt, cnt in provider_rows
        ],
        by_payment_method=[
            PaymentMethodRow(
                label=label,
                gross=_d(gross),
                cashback=_d(cb),
                net=_d(Decimal(str(gross)) - Decimal(str(cb))),
            )
            for label, gross, cb in payment_rows
        ],
        by_day=[
            DayRow(date=str(day), sale_count=cnt, total=_d(amt))
            for day, cnt, amt in day_rows
        ],
    )


# ── GET /reports/petty-cash ───────────────────────────────────────────────────

class PettyCashEntryRow(BaseModel):
    date: str
    description: str
    amount: str


class PettyCashReport(BaseModel):
    year: int
    month: int
    entries: list[PettyCashEntryRow]
    total: str


@router.get("/petty-cash", response_model=PettyCashReport)
async def petty_cash_report(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
) -> PettyCashReport:
    tid = current_user.tenant_id
    _, last_day = monthrange(year, month)

    rows = (
        await db.execute(
            select(
                CashReconciliation.business_date,
                PettyCashEntry.description,
                PettyCashEntry.amount,
            )
            .join(PettyCashEntry, PettyCashEntry.reconciliation_id == CashReconciliation.id)
            .where(
                CashReconciliation.tenant_id == tid,
                CashReconciliation.business_date >= date(year, month, 1),
                CashReconciliation.business_date <= date(year, month, last_day),
            )
            .order_by(CashReconciliation.business_date, PettyCashEntry.created_at)
        )
    ).all()

    entries = [
        PettyCashEntryRow(date=str(biz_date), description=desc, amount=_d(amt))
        for biz_date, desc, amt in rows
    ]
    total = sum((Decimal(e.amount) for e in entries), Decimal("0"))

    return PettyCashReport(year=year, month=month, entries=entries, total=_d(total))


# ── Transaction detail report ─────────────────────────────────────────────────

class TransactionLineItem(BaseModel):
    sale_id: str
    sale_date: str            # YYYY-MM-DD
    client_name: str
    provider_name: str | None
    kind: str                 # service | retail
    description: str
    quantity: int
    unit_price: str
    discount: str
    line_total: str
    # Sale-level totals — only populated on the last item of each sale
    gst: str | None = None
    pst: str | None = None
    sale_total: str | None = None


class TransactionReport(BaseModel):
    period_start: str
    period_end: str
    items: list[TransactionLineItem]
    grand_total: str


@router.get("/transactions", response_model=TransactionReport)
async def transaction_report(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
) -> TransactionReport:
    from app.models.client import Client
    from sqlalchemy import and_, outerjoin

    tid = current_user.tenant_id
    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

    rows = (await db.execute(
        select(
            Sale.id,
            Sale.completed_at,
            Sale.gst_amount,
            Sale.pst_amount,
            Sale.total,
            Client.first_name,
            Client.last_name,
            SaleItem.sequence,
            SaleItem.kind,
            SaleItem.description,
            SaleItem.quantity,
            SaleItem.unit_price,
            SaleItem.discount_amount,
            SaleItem.line_total,
            SaleItem.provider_id,
        )
        .join(Client, Client.id == Sale.client_id)
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .where(
            Sale.tenant_id == tid,
            Sale.status == SaleStatus.completed,
            Sale.completed_at >= start_dt,
            Sale.completed_at <= end_dt,
        )
        .order_by(Sale.completed_at, Sale.id, SaleItem.sequence)
    )).all()

    # Load provider names
    provider_ids = {r.provider_id for r in rows if r.provider_id}
    provider_names: dict[uuid.UUID, str] = {}
    if provider_ids:
        prows = (await db.execute(
            select(Provider.id, Provider.display_name)
            .where(Provider.id.in_(provider_ids))
        )).all()
        provider_names = {p.id: p.display_name for p in prows}

    # Group by sale to mark last item with tax totals
    from collections import defaultdict
    sale_items: dict[str, list] = defaultdict(list)
    sale_meta: dict[str, dict] = {}
    for r in rows:
        sid = str(r.id)
        sale_items[sid].append(r)
        sale_meta[sid] = {
            "gst": r.gst_amount,
            "pst": r.pst_amount,
            "total": r.total,
        }

    items: list[TransactionLineItem] = []
    grand_total = Decimal("0")
    for sid, sale_rows in sale_items.items():
        meta = sale_meta[sid]
        grand_total += Decimal(str(meta["total"]))
        for i, r in enumerate(sale_rows):
            is_last = i == len(sale_rows) - 1
            client_name = f"{r.first_name} {r.last_name}".strip()
            provider = provider_names.get(r.provider_id) if r.provider_id else None
            items.append(TransactionLineItem(
                sale_id=sid[-8:].upper(),
                sale_date=r.completed_at.strftime("%Y-%m-%d"),
                client_name=client_name,
                provider_name=provider,
                kind=r.kind.value if hasattr(r.kind, "value") else str(r.kind),
                description=r.description,
                quantity=int(r.quantity or 1),
                unit_price=_d(r.unit_price),
                discount=_d(r.discount_amount),
                line_total=_d(r.line_total),
                gst=_d(meta["gst"]) if is_last else None,
                pst=_d(meta["pst"]) if is_last else None,
                sale_total=_d(meta["total"]) if is_last else None,
            ))

    return TransactionReport(
        period_start=start,
        period_end=end,
        items=items,
        grand_total=_d(grand_total),
    )


# ── Payroll detail report ─────────────────────────────────────────────────────

class PayrollServiceRow(BaseModel):
    date: str
    client_name: str
    service_name: str
    # Nullable: a sale_item can resolve a service via Path B (si.service_id)
    # without its category join matching — happens when a service was created
    # with a stale category_id or the row was orphaned by a backfill. The
    # response should still render; frontend displays "—" for None.
    category: str | None
    is_colour: bool
    gross_amount: str       # what was charged
    product_fee: str        # deducted from gross before commission
    net_amount: str         # gross - product_fee

class PayrollRetailRow(BaseModel):
    date: str
    client_name: str
    description: str
    amount: str

class PayrollDetailReport(BaseModel):
    provider_id: str
    provider_name: str
    period_start: str
    period_end: str
    pay_type: str | None
    pay_basis: str
    # Service breakdown
    service_rows: list[PayrollServiceRow]
    styling_gross: str
    styling_fees: str
    colour_gross: str
    colour_fees: str
    net_service_revenue: str
    commission_rate_pct: str
    commission_on_services: str
    # Retail
    retail_rows: list[PayrollRetailRow]
    retail_gross: str
    retail_commission_pct: str
    retail_commission: str
    # Totals
    vacation_pct: str
    gross_before_vacation: str
    vacation_pay: str
    gross_pay: str


@router.get("/payroll-detail", response_model=PayrollDetailReport)
async def payroll_detail_report(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider_id: str = Query(...),
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
) -> PayrollDetailReport:
    # Wrap the whole handler so unhandled exceptions are surfaced via the
    # HTTPException detail field instead of an opaque 500 "Internal Server
    # Error". Lets the frontend display the real Python exception in the UI,
    # which is much faster to diagnose than digging through Cloud Run logs.
    # TODO once root cause for P-PERF-RECONCILE regressions is fixed, evaluate
    # whether to keep this or scope to a global handler.
    try:
        return await _payroll_detail_report_impl(
            current_user=current_user, db=db,
            provider_id=provider_id, start=start, end=end,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        from fastapi import HTTPException as _HE
        raise _HE(
            status_code=500,
            detail=f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}",
        )


async def _payroll_detail_report_impl(
    current_user,
    db,
    provider_id: str,
    start: str,
    end: str,
) -> PayrollDetailReport:
    from datetime import date as _date
    from decimal import Decimal as D
    from app.models.client import Client
    from app.models.appointment import AppointmentItem
    from app.models.service import Service, ServiceCategory, ServiceFeeHistory
    from app.models.provider_service_price import ProviderServicePrice
    from app.models.schedule import ProviderSchedule, ProviderScheduleException
    from sqlalchemy import cast, orm
    from sqlalchemy.types import Date as SADate
    ServiceViaAppt = orm.aliased(Service, flat=True)
    ServiceViaSaleItem = orm.aliased(Service, flat=True)
    CatViaAppt = orm.aliased(ServiceCategory, flat=True)
    CatViaSaleItem = orm.aliased(ServiceCategory, flat=True)

    tid = current_user.tenant_id
    pid = uuid.UUID(provider_id)
    period_start = _date.fromisoformat(start)
    period_end = _date.fromisoformat(end)

    # Load provider
    p = (await db.execute(select(Provider).where(Provider.id == pid, Provider.tenant_id == tid))).scalar_one_or_none()
    if not p:
        from fastapi import HTTPException as _HE
        raise _HE(status_code=404, detail="Provider not found")

    # PSP overrides
    psp_rows = (await db.execute(
        select(ProviderServicePrice.service_id, ProviderServicePrice.price)
        .where(ProviderServicePrice.provider_id == pid, ProviderServicePrice.tenant_id == tid)
    )).all()
    psp_price_map = {str(r.service_id): float(r.price) for r in psp_rows}

    # ── Individual service transactions ───────────────────────────────────────
    # P-PAYROLL-1: read product fee from history table at period_end so
    # historical payroll detail isn't retroactively distorted.
    fee_subq = (
        select(
            ServiceFeeHistory.service_id.label("svc_id"),
            ServiceFeeHistory.product_fee.label("hist_fee"),
            ServiceFeeHistory.is_cost_percent.label("hist_is_pct"),
        )
        .where(
            ServiceFeeHistory.tenant_id == tid,
            ServiceFeeHistory.effective_from <= period_end,
        )
        .order_by(
            ServiceFeeHistory.service_id,
            ServiceFeeHistory.effective_from.desc(),
            ServiceFeeHistory.created_at.desc(),
        )
        .distinct(ServiceFeeHistory.service_id)
        .subquery()
    )

    # Two outer-join paths to resolve the service for each sale item:
    #   Path A: via appointment_item (booked services)
    #   Path B: via sale_items.service_id directly (basket add-ons, group overflow)
    # Using raw SQL to avoid SQLAlchemy aliased-join edge cases with coalesce.
    svc_txn_rows = (await db.execute(text("""
        SELECT
            s.completed_at,
            c.first_name, c.last_name,
            si.line_total, si.unit_price, si.quantity, si.is_business_reimbursed,
            COALESCE(sva.name, svs.name)                                    AS service_name,
            COALESCE(sva.id,   svs.id)                                      AS service_id,
            COALESCE(fh.hist_fee,  sva.default_cost,  svs.default_cost)    AS default_cost,
            COALESCE(sva.default_price, svs.default_price)                  AS default_price,
            COALESCE(fh.hist_is_pct, sva.is_cost_percent, svs.is_cost_percent) AS is_cost_percent,
            COALESCE(cva.name, cvs.name)                                    AS cat_name
        FROM sale_items si
        JOIN sales s       ON s.id  = si.sale_id
        JOIN clients c     ON c.id  = s.client_id
        LEFT JOIN appointment_items ai ON ai.id  = si.appointment_item_id
        LEFT JOIN services sva         ON sva.id = ai.service_id
        LEFT JOIN service_categories cva ON cva.id = sva.category_id
        LEFT JOIN services svs         ON svs.id = si.service_id
        LEFT JOIN service_categories cvs ON cvs.id = svs.category_id
        LEFT JOIN (
            SELECT DISTINCT ON (service_id) service_id,
                   product_fee  AS hist_fee,
                   is_cost_percent AS hist_is_pct
            FROM service_fee_history
            WHERE tenant_id = :tid
              AND effective_from <= :period_end
            ORDER BY service_id, effective_from DESC, created_at DESC
        ) fh ON fh.service_id = COALESCE(sva.id, svs.id)
        WHERE si.tenant_id   = :tid
          AND si.provider_id = :pid
          AND si.kind        = 'service'
          AND s.status       = 'completed'
          AND s.completed_at::date >= :period_start
          AND s.completed_at::date <= :period_end
          AND COALESCE(sva.id, svs.id) IS NOT NULL
        ORDER BY s.completed_at, COALESCE(sva.name, svs.name)
    """), {"tid": tid, "pid": pid, "period_start": period_start, "period_end": period_end}
    )).all()

    styling_gross = D("0"); styling_fees = D("0")
    colour_gross = D("0"); colour_fees = D("0")
    service_rows: list[PayrollServiceRow] = []

    for r in svc_txn_rows:
        is_col = bool(r.is_cost_percent)
        default_cost = D(str(float(r.default_cost or 0)))
        qty = D(str(int(r.quantity or 1)))
        full_amount = D(str(r.unit_price)) * qty
        line_total = D(str(r.line_total))
        is_br = bool(r.is_business_reimbursed)

        commission_basis = full_amount if is_br else line_total

        if is_col:
            fee = full_amount * default_cost / D("100")
            colour_gross += commission_basis; colour_fees += fee
        else:
            fee = default_cost * qty
            styling_gross += commission_basis; styling_fees += fee

        service_rows.append(PayrollServiceRow(
            date=r.completed_at.strftime("%Y-%m-%d"),
            client_name=f"{r.first_name} {r.last_name}".strip(),
            service_name=r.service_name,
            category=r.cat_name,
            is_colour=is_col,
            gross_amount=_d(commission_basis),
            product_fee=_d(fee),
            net_amount=_d(commission_basis - fee),
        ))

    net_service_revenue = styling_gross + colour_gross - styling_fees - colour_fees

    # Commission tier
    tiers = p.commission_tiers or []
    applied_tier = None
    for t in sorted(tiers, key=lambda x: x.get("monthly_threshold", 0)):
        if float(net_service_revenue) >= t.get("monthly_threshold", 0):
            applied_tier = t
    rate_pct = D(str(applied_tier["rate_pct"])) if applied_tier else D("0")
    commission_on_services = net_service_revenue * rate_pct / D("100")

    # ── Retail transactions from this provider's sales ────────────────────────
    provider_sale_ids_q = (
        select(SaleItem.sale_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            SaleItem.tenant_id == tid, SaleItem.provider_id == pid,
            SaleItem.kind == SaleItemKind.service,
            Sale.status == SaleStatus.completed,
            cast(Sale.completed_at, SADate) >= period_start,
            cast(Sale.completed_at, SADate) <= period_end,
        ).distinct()
    )
    retail_txn_rows = (await db.execute(
        select(
            Sale.completed_at,
            Client.first_name, Client.last_name,
            SaleItem.description, SaleItem.line_total, SaleItem.quantity,
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Client, Client.id == Sale.client_id)
        .where(
            SaleItem.tenant_id == tid,
            SaleItem.kind == SaleItemKind.retail,
            SaleItem.provider_id == pid,
            cast(Sale.completed_at, SADate) >= period_start,
            cast(Sale.completed_at, SADate) <= period_end,
            ~func.lower(SaleItem.description).contains("gift card"),
            ~func.lower(SaleItem.description).contains("gift certificate"),
            ~func.lower(SaleItem.description).contains("gift card/certificate"),
        )
        .order_by(Sale.completed_at)
    )).all()

    retail_gross = D("0")
    retail_rows: list[PayrollRetailRow] = []
    for r in retail_txn_rows:
        # Returns have quantity < 0 but positive line_total (Milano encoding).
        signed = D(str(r.line_total)) if r.quantity >= 0 else -abs(D(str(r.line_total)))
        retail_gross += signed
        retail_rows.append(PayrollRetailRow(
            date=r.completed_at.strftime("%Y-%m-%d"),
            client_name=f"{r.first_name} {r.last_name}".strip(),
            description=r.description,
            amount=_d(signed),
        ))

    retail_pct = D(str(p.retail_commission_pct or 0))
    retail_commission = retail_gross * retail_pct / D("100")

    # Pay basis + gross pay
    pay_type_val = p.pay_type.value if p.pay_type else None
    vac_pct = D(str(p.vacation_pct or 0))
    hourly_min = D(str(p.hourly_minimum or 0))
    total_commission = commission_on_services + retail_commission

    if pay_type_val == "salary":
        gross_before_vac = D(str(p.pay_amount or 0)) / D("12")
        pay_basis = "salary"
    elif pay_type_val == "commission":
        # Calculate scheduled hours for floor check (simplified)
        gross_before_vac = total_commission
        pay_basis = "commission"
    elif pay_type_val == "hourly":
        gross_before_vac = D("0")  # hours × rate — needs time entries
        pay_basis = "hourly"
    else:
        gross_before_vac = D("0")
        pay_basis = "n/a"

    vac_pay = gross_before_vac * vac_pct / D("100")
    gross_pay = gross_before_vac + vac_pay

    return PayrollDetailReport(
        provider_id=str(pid),
        provider_name=p.display_name or f"{p.first_name} {p.last_name}",
        period_start=start,
        period_end=end,
        pay_type=pay_type_val,
        pay_basis=pay_basis,
        service_rows=service_rows,
        styling_gross=_d(styling_gross),
        styling_fees=_d(styling_fees),
        colour_gross=_d(colour_gross),
        colour_fees=_d(colour_fees),
        net_service_revenue=_d(net_service_revenue),
        commission_rate_pct=_d(rate_pct),
        commission_on_services=_d(commission_on_services),
        retail_rows=retail_rows,
        retail_gross=_d(retail_gross),
        retail_commission_pct=_d(retail_pct),
        retail_commission=_d(retail_commission),
        vacation_pct=_d(vac_pct),
        gross_before_vacation=_d(gross_before_vac),
        vacation_pay=_d(vac_pay),
        gross_pay=_d(gross_pay),
    )


# ── GET /reports/service-performance ──────────────────────────────────────────
# P-PERF-1: per-provider service performance for owner review.
# Modelled on Milano's "Service Performance Report" — service mix, retail
# summary, receipt analysis. No commission info (lives in PayrollDetail).

class ServicePerformanceServiceRow(BaseModel):
    service_name: str
    total_sales: str        # sum of line_total (gross — pre product-fee)
    product_fee: str        # sum of allocated product fee per service
    net_sales: str          # total_sales − product_fee
    sales_count: int        # sum of quantity (returns subtract)
    average_price: str      # total_sales / sales_count (0 if count == 0)
    pct_of_sales: str       # total_sales / total_service_sales * 100
    pct_of_count: str       # sales_count / total_service_count * 100


class ServicePerformanceReport(BaseModel):
    provider_id: str
    provider_name: str
    period_start: str
    period_end: str
    # Per-service breakdown (sorted by total_sales desc). Items whose
    # sale_item couldn't be linked to a Service row appear as
    # "(Unmapped) <description>" so the owner can reconcile counts.
    service_rows: list[ServicePerformanceServiceRow]
    # Totals
    total_service_sales: str
    total_service_fees: str         # sum of product fees across all services
    total_net_service_sales: str    # total_service_sales − total_service_fees
    total_service_count: int
    average_service_price: str
    total_retail_sales: str
    total_retail_count: int
    average_retail_price: str
    total_sales: str        # service + retail
    # Ratios (percent)
    pct_service_of_total: str
    pct_retail_of_total: str
    pct_retail_of_service: str
    # Receipt analysis
    receipt_count: int
    clients_serviced: int
    avg_per_receipt: str
    items_per_receipt: str


@router.get("/service-performance", response_model=ServicePerformanceReport)
async def service_performance_report(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider_id: str = Query(...),
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
) -> ServicePerformanceReport:
    from datetime import date as _date
    from decimal import Decimal as D
    from app.models.client import Client
    from sqlalchemy import cast, text as _text
    from sqlalchemy.types import Date as SADate
    from fastapi import HTTPException

    tid = current_user.tenant_id
    pid = uuid.UUID(provider_id)
    period_start = _date.fromisoformat(start)
    period_end = _date.fromisoformat(end)

    p = (await db.execute(
        select(Provider).where(Provider.id == pid, Provider.tenant_id == tid)
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Milano-imported returns: quantity < 0 but line_total > 0. Flip the sign on
    # line_total when quantity is negative so returns net against sales.
    signed_line_total = case(
        (SaleItem.quantity < 0, -func.abs(SaleItem.line_total)),
        else_=SaleItem.line_total,
    )

    # Dual-path service resolution (matches payroll-detail in this file):
    #   Path A: sale_items.appointment_item_id → appointment_items.service_id → services
    #   Path B: sale_items.service_id → services   (basket add-ons, group overflow)
    # Items with no link on either path are surfaced as "(Unmapped) <desc>"
    # so the owner can see which Milano descriptions never matched the catalog.
    #
    # Product fee is resolved from service_fee_history at period_end so historical
    # runs aren't retroactively distorted by present-day fee changes (P-PAYROLL-1
    # uses the same pattern).
    svc_rows = (await db.execute(_text("""
        WITH resolved AS (
            SELECT
                COALESCE(sva.name, svs.name, '(Unmapped) ' || si.description) AS service_name,
                COALESCE(fh.hist_fee, sva.default_cost, svs.default_cost, 0)  AS fee_value,
                COALESCE(fh.hist_is_pct, sva.is_cost_percent, svs.is_cost_percent, false) AS fee_is_pct,
                si.quantity,
                CASE WHEN si.quantity < 0 THEN -ABS(si.line_total) ELSE si.line_total END AS signed_total
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            LEFT JOIN appointment_items ai ON ai.id = si.appointment_item_id
            LEFT JOIN services sva ON sva.id = ai.service_id
            LEFT JOIN services svs ON svs.id = si.service_id
            LEFT JOIN (
                SELECT DISTINCT ON (service_id) service_id,
                       product_fee     AS hist_fee,
                       is_cost_percent AS hist_is_pct
                FROM service_fee_history
                WHERE tenant_id = :tid AND effective_from <= :period_end
                ORDER BY service_id, effective_from DESC, created_at DESC
            ) fh ON fh.service_id = COALESCE(sva.id, svs.id)
            WHERE si.tenant_id   = :tid
              AND si.provider_id = :pid
              AND si.kind        = 'service'
              AND s.status       = 'completed'
              AND s.completed_at::date >= :period_start
              AND s.completed_at::date <= :period_end
        )
        SELECT
            service_name,
            SUM(signed_total) AS total_sales,
            SUM(quantity)     AS sales_count,
            SUM(
                CASE
                    WHEN fee_is_pct THEN signed_total * fee_value / 100
                    ELSE fee_value * quantity
                END
            ) AS product_fee
        FROM resolved
        GROUP BY service_name
    """), {"tid": tid, "pid": pid,
           "period_start": period_start, "period_end": period_end}
    )).all()

    total_service = D("0")
    total_fees = D("0")
    total_count = 0
    for r in svc_rows:
        total_service += D(str(r.total_sales))
        total_fees += D(str(r.product_fee))
        total_count += int(r.sales_count)

    service_rows: list[ServicePerformanceServiceRow] = []
    for r in svc_rows:
        total = D(str(r.total_sales))
        fee = D(str(r.product_fee))
        net = total - fee
        cnt = int(r.sales_count)
        avg = total / D(cnt) if cnt else D("0")
        pct_sales = (total / total_service * D("100")) if total_service else D("0")
        pct_count = (D(cnt) / D(total_count) * D("100")) if total_count else D("0")
        service_rows.append(ServicePerformanceServiceRow(
            service_name=r.service_name,
            total_sales=_d(total.quantize(D("0.01"))),
            product_fee=_d(fee.quantize(D("0.01"))),
            net_sales=_d(net.quantize(D("0.01"))),
            sales_count=cnt,
            average_price=_d(avg.quantize(D("0.01"))),
            pct_of_sales=_d(pct_sales.quantize(D("0.1"))),
            pct_of_count=_d(pct_count.quantize(D("0.1"))),
        ))
    service_rows.sort(key=lambda x: float(x.total_sales), reverse=True)

    # Retail totals from this provider's retail sale items.
    retail_row = (await db.execute(
        select(
            func.coalesce(func.sum(signed_line_total), 0).label("total"),
            func.coalesce(func.sum(SaleItem.quantity), 0).label("count"),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            SaleItem.tenant_id == tid,
            SaleItem.provider_id == pid,
            SaleItem.kind == SaleItemKind.retail,
            Sale.status == SaleStatus.completed,
            cast(Sale.completed_at, SADate) >= period_start,
            cast(Sale.completed_at, SADate) <= period_end,
            ~func.lower(SaleItem.description).contains("gift card"),
            ~func.lower(SaleItem.description).contains("gift certificate"),
        )
    )).one()
    total_retail = D(str(retail_row.total))
    retail_count = int(retail_row.count)

    grand_total = total_service + total_retail
    avg_service = (total_service / D(total_count)) if total_count else D("0")
    avg_retail = (total_retail / D(retail_count)) if retail_count else D("0")
    pct_svc = (total_service / grand_total * D("100")) if grand_total else D("0")
    pct_ret = (total_retail / grand_total * D("100")) if grand_total else D("0")
    pct_ret_svc = (total_retail / total_service * D("100")) if total_service else D("0")

    # Receipt analysis — count distinct sales and distinct clients on this
    # provider's completed service work in the period. Plus item count for
    # items/receipt = (service_count + retail_count) / receipt_count.
    sale_stats = (await db.execute(
        select(
            func.count(func.distinct(Sale.id)).label("receipts"),
            func.count(func.distinct(Sale.client_id)).label("clients"),
        )
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .where(
            SaleItem.tenant_id == tid,
            SaleItem.provider_id == pid,
            SaleItem.kind == SaleItemKind.service,
            Sale.status == SaleStatus.completed,
            cast(Sale.completed_at, SADate) >= period_start,
            cast(Sale.completed_at, SADate) <= period_end,
        )
    )).one()
    receipt_count = int(sale_stats.receipts)
    clients_serviced = int(sale_stats.clients)
    avg_per_receipt = (grand_total / D(receipt_count)) if receipt_count else D("0")
    items_per_receipt = (
        D(total_count + retail_count) / D(receipt_count) if receipt_count else D("0")
    )

    return ServicePerformanceReport(
        provider_id=str(pid),
        provider_name=p.display_name or f"{p.first_name} {p.last_name}",
        period_start=start,
        period_end=end,
        service_rows=service_rows,
        total_service_sales=_d(total_service.quantize(D("0.01"))),
        total_service_fees=_d(total_fees.quantize(D("0.01"))),
        total_net_service_sales=_d((total_service - total_fees).quantize(D("0.01"))),
        total_service_count=total_count,
        average_service_price=_d(avg_service.quantize(D("0.01"))),
        total_retail_sales=_d(total_retail.quantize(D("0.01"))),
        total_retail_count=retail_count,
        average_retail_price=_d(avg_retail.quantize(D("0.01"))),
        total_sales=_d(grand_total.quantize(D("0.01"))),
        pct_service_of_total=_d(pct_svc.quantize(D("0.1"))),
        pct_retail_of_total=_d(pct_ret.quantize(D("0.1"))),
        pct_retail_of_service=_d(pct_ret_svc.quantize(D("0.1"))),
        receipt_count=receipt_count,
        clients_serviced=clients_serviced,
        avg_per_receipt=_d(avg_per_receipt.quantize(D("0.01"))),
        items_per_receipt=_d(items_per_receipt.quantize(D("0.01"))),
    )
