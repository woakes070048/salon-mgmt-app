import uuid
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
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
    kind_rows = (
        await db.execute(
            select(
                SaleItem.kind,
                func.coalesce(func.sum(SaleItem.line_total), 0),
                func.coalesce(func.sum(SaleItem.unit_price * SaleItem.quantity), 0),
                func.coalesce(func.sum(SaleItem.discount_amount * SaleItem.quantity), 0),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*completed)
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

    # ── Retail returns (negative retail line_totals — returned product) ──────────
    retail_returns = Decimal(str(abs(
        (
            await db.execute(
                select(func.coalesce(func.sum(SaleItem.line_total), 0))
                .join(Sale, Sale.id == SaleItem.sale_id)
                .where(
                    *completed,
                    SaleItem.kind == SaleItemKind.retail,
                    SaleItem.line_total < 0,
                )
            )
        ).scalar() or 0
    )))

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
