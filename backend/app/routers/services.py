"""
Services catalog.

GET    /services                   — list (active only) — used by booking forms
GET    /services/all               — list including inactive — used by management page
GET    /services/{id}              — full detail with all translations — used by management page
POST   /services                   — create (admin)
PATCH  /services/{id}              — update (admin)
DELETE /services/{id}              — soft delete (admin) — sets is_active=false
"""
import re
import uuid
from datetime import date as ddate
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import AdminUser, CurrentUser, ResolvedLanguage
from app.models.i18n import ServiceCategoryTranslation, ServiceTranslation
from app.models.service import PricingType, Service, ServiceCategory, ServiceFeeHistory

router = APIRouter(prefix="/services", tags=["services"])


# ── Shared translation payload ────────────────────────────────────────────────

class ServiceTranslationData(BaseModel):
    name: str | None = None
    description: str | None = None
    suggestions: str | None = None


# ── List shape (used by booking pickers) ─────────────────────────────────────

class ServiceOut(BaseModel):
    id: str
    service_code: str
    name: str
    category_name: str
    duration_minutes: int
    default_price: float | None
    pricing_type: str


@router.get("", response_model=list[ServiceOut])
async def list_services(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    language: ResolvedLanguage,
) -> list[ServiceOut]:
    rows = (
        await db.execute(
            select(Service, ServiceCategory, ServiceTranslation, ServiceCategoryTranslation)
            .join(ServiceCategory, Service.category_id == ServiceCategory.id)
            .outerjoin(ServiceTranslation, and_(
                ServiceTranslation.service_id == Service.id,
                ServiceTranslation.language == language,
            ))
            .outerjoin(ServiceCategoryTranslation, and_(
                ServiceCategoryTranslation.category_id == ServiceCategory.id,
                ServiceCategoryTranslation.language == language,
            ))
            .where(
                Service.tenant_id == current_user.tenant_id,
                Service.is_active == True,  # noqa: E712
            )
            .order_by(ServiceCategory.display_order, Service.display_order, Service.name)
        )
    ).all()

    return [
        ServiceOut(
            id=str(svc.id),
            service_code=svc.service_code,
            name=tr.name if tr else svc.name,
            category_name=cat_tr.name if cat_tr else cat.name,
            duration_minutes=svc.duration_minutes,
            default_price=float(svc.default_price) if svc.default_price is not None else None,
            pricing_type=svc.pricing_type.value,
        )
        for svc, cat, tr, cat_tr in rows
    ]


# ── Full detail shape (used by management page) ───────────────────────────────

class ServiceDetailOut(BaseModel):
    id: str
    category_id: str
    category_name: str
    service_code: str
    name: str
    description: str | None
    pricing_type: str
    default_price: str | None
    default_cost: str | None
    is_cost_percent: bool
    duration_minutes: int
    processing_offset_minutes: int
    processing_duration_minutes: int
    requires_prior_consultation: bool
    suggestions: str | None
    is_active: bool
    display_order: int
    translations: dict[str, ServiceTranslationData] = {}


def _to_detail(
    svc: Service,
    cat: ServiceCategory,
    tr: ServiceTranslation | None = None,
    cat_tr: ServiceCategoryTranslation | None = None,
    all_translations: dict[str, ServiceTranslationData] | None = None,
) -> ServiceDetailOut:
    return ServiceDetailOut(
        id=str(svc.id),
        category_id=str(svc.category_id),
        category_name=cat_tr.name if cat_tr else cat.name,
        service_code=svc.service_code,
        name=tr.name if tr else svc.name,
        description=tr.description if tr else svc.description,
        pricing_type=svc.pricing_type.value,
        default_price=str(svc.default_price) if svc.default_price is not None else None,
        default_cost=str(svc.default_cost) if svc.default_cost is not None else None,
        is_cost_percent=svc.is_cost_percent,
        duration_minutes=svc.duration_minutes,
        processing_offset_minutes=svc.processing_offset_minutes,
        processing_duration_minutes=svc.processing_duration_minutes,
        requires_prior_consultation=svc.requires_prior_consultation,
        suggestions=tr.suggestions if tr else svc.suggestions,
        is_active=svc.is_active,
        display_order=svc.display_order,
        translations=all_translations or {},
    )


async def _load_translations(service_id: uuid.UUID, db: AsyncSession) -> dict[str, ServiceTranslationData]:
    rows = (
        await db.execute(
            select(ServiceTranslation).where(ServiceTranslation.service_id == service_id)
        )
    ).scalars().all()
    return {
        row.language: ServiceTranslationData(
            name=row.name, description=row.description, suggestions=row.suggestions
        )
        for row in rows
    }


@router.get("/all", response_model=list[ServiceDetailOut])
async def list_services_full(
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    language: ResolvedLanguage,
) -> list[ServiceDetailOut]:
    rows = (
        await db.execute(
            select(Service, ServiceCategory, ServiceTranslation, ServiceCategoryTranslation)
            .join(ServiceCategory, Service.category_id == ServiceCategory.id)
            .outerjoin(ServiceTranslation, and_(
                ServiceTranslation.service_id == Service.id,
                ServiceTranslation.language == language,
            ))
            .outerjoin(ServiceCategoryTranslation, and_(
                ServiceCategoryTranslation.category_id == ServiceCategory.id,
                ServiceCategoryTranslation.language == language,
            ))
            .where(Service.tenant_id == current_user.tenant_id)
            .order_by(ServiceCategory.display_order, Service.display_order, Service.name)
        )
    ).all()
    return [_to_detail(svc, cat, tr, cat_tr) for svc, cat, tr, cat_tr in rows]


async def _load_with_category(
    service_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession, language: str
) -> tuple[Service, ServiceCategory, ServiceTranslation | None, ServiceCategoryTranslation | None]:
    row = (
        await db.execute(
            select(Service, ServiceCategory, ServiceTranslation, ServiceCategoryTranslation)
            .join(ServiceCategory, Service.category_id == ServiceCategory.id)
            .outerjoin(ServiceTranslation, and_(
                ServiceTranslation.service_id == Service.id,
                ServiceTranslation.language == language,
            ))
            .outerjoin(ServiceCategoryTranslation, and_(
                ServiceCategoryTranslation.category_id == ServiceCategory.id,
                ServiceCategoryTranslation.language == language,
            ))
            .where(Service.id == service_id, Service.tenant_id == tenant_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return row[0], row[1], row[2], row[3]


@router.get("/{service_id}", response_model=ServiceDetailOut)
async def get_service(
    service_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    language: ResolvedLanguage,
) -> ServiceDetailOut:
    svc, cat, tr, cat_tr = await _load_with_category(
        uuid.UUID(service_id), current_user.tenant_id, db, language
    )
    all_tr = await _load_translations(svc.id, db)
    return _to_detail(svc, cat, tr, cat_tr, all_tr)


# ── Create / update / delete ──────────────────────────────────────────────────

class ServiceIn(BaseModel):
    category_id: str
    service_code: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    pricing_type: PricingType = PricingType.fixed
    default_price: float | None = None
    default_cost: float | None = None
    is_cost_percent: bool = False
    duration_minutes: int = Field(default=60, ge=5)
    processing_offset_minutes: int = 0
    processing_duration_minutes: int = 0
    requires_prior_consultation: bool = False
    suggestions: str | None = None
    is_active: bool = True
    display_order: int = 0
    translations: dict[str, ServiceTranslationData] | None = None


class ServicePatch(BaseModel):
    category_id: str | None = None
    service_code: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    pricing_type: PricingType | None = None
    default_price: float | None = None
    default_cost: float | None = None
    is_cost_percent: bool | None = None
    duration_minutes: int | None = Field(default=None, ge=5)
    processing_offset_minutes: int | None = None
    processing_duration_minutes: int | None = None
    requires_prior_consultation: bool | None = None
    suggestions: str | None = None
    is_active: bool | None = None
    display_order: int | None = None
    translations: dict[str, ServiceTranslationData] | None = None


def _slugify_code(name: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    return s[:50] or 'service'


async def _upsert_translation(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    service_id: uuid.UUID,
    language: str,
    data: ServiceTranslationData,
    canonical_name: str,
) -> None:
    existing = (
        await db.execute(
            select(ServiceTranslation).where(
                ServiceTranslation.service_id == service_id,
                ServiceTranslation.language == language,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(ServiceTranslation(
            tenant_id=tenant_id,
            service_id=service_id,
            language=language,
            name=data.name if data.name is not None else canonical_name,
            description=data.description,
            suggestions=data.suggestions,
        ))
    else:
        if data.name is not None:
            existing.name = data.name
        if data.description is not None:
            existing.description = data.description
        if data.suggestions is not None:
            existing.suggestions = data.suggestions


@router.post("", response_model=ServiceDetailOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    body: ServiceIn,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    language: ResolvedLanguage,
) -> ServiceDetailOut:
    tid = current_user.tenant_id

    cat = (
        await db.execute(
            select(ServiceCategory).where(
                ServiceCategory.id == uuid.UUID(body.category_id),
                ServiceCategory.tenant_id == tid,
            )
        )
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid category_id")

    svc = Service(
        tenant_id=tid,
        category_id=cat.id,
        service_code=body.service_code or _slugify_code(body.name),
        name=body.name,
        description=body.description,
        pricing_type=body.pricing_type,
        default_price=body.default_price,
        default_cost=body.default_cost,
        is_cost_percent=body.is_cost_percent,
        duration_minutes=body.duration_minutes,
        processing_offset_minutes=body.processing_offset_minutes,
        processing_duration_minutes=body.processing_duration_minutes,
        requires_prior_consultation=body.requires_prior_consultation,
        suggestions=body.suggestions,
        is_active=body.is_active,
        display_order=body.display_order,
    )
    db.add(svc)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A service with that code already exists")

    # Seed initial fee history row so payroll lookups always find a value
    db.add(ServiceFeeHistory(
        tenant_id=tid,
        service_id=svc.id,
        effective_from=ddate.today(),
        product_fee=svc.default_cost,
        is_cost_percent=svc.is_cost_percent,
        created_by_user_id=current_user.id,
    ))

    # Seed English translation from canonical fields
    extra = (body.translations or {}).get("en", ServiceTranslationData())
    await _upsert_translation(db, tid, svc.id, "en", ServiceTranslationData(
        name=extra.name or body.name,
        description=extra.description or body.description,
        suggestions=extra.suggestions or body.suggestions,
    ), body.name)

    # Write any additional language translations provided at creation time
    for lang, tr_data in (body.translations or {}).items():
        if lang != "en":
            await _upsert_translation(db, tid, svc.id, lang, tr_data, body.name)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A service with that code already exists")

    await db.refresh(svc)
    svc, cat, tr, cat_tr = await _load_with_category(svc.id, tid, db, language)
    all_tr = await _load_translations(svc.id, db)
    return _to_detail(svc, cat, tr, cat_tr, all_tr)


@router.patch("/{service_id}", response_model=ServiceDetailOut)
async def update_service(
    service_id: str,
    body: ServicePatch,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    language: ResolvedLanguage,
) -> ServiceDetailOut:
    tid = current_user.tenant_id
    svc, _, _, _ = await _load_with_category(uuid.UUID(service_id), tid, db, language)

    # Snapshot pre-patch fee values so we can detect a change and write history
    prev_default_cost = svc.default_cost
    prev_is_cost_percent = svc.is_cost_percent

    canonical_fields = {f for f in body.model_fields_set if f != "translations" and f != "category_id"}
    for field in canonical_fields:
        value = getattr(body, field)
        setattr(svc, field, value)

    # If product_fee or is_cost_percent changed, append a new history row.
    # effective_from = today; payroll lookups for periods ending before today
    # will continue to use the prior row (correct historical behaviour).
    fee_changed = (
        ("default_cost" in body.model_fields_set and svc.default_cost != prev_default_cost)
        or ("is_cost_percent" in body.model_fields_set and svc.is_cost_percent != prev_is_cost_percent)
    )
    if fee_changed:
        db.add(ServiceFeeHistory(
            tenant_id=tid,
            service_id=svc.id,
            effective_from=ddate.today(),
            product_fee=svc.default_cost,
            is_cost_percent=svc.is_cost_percent,
            created_by_user_id=current_user.id,
        ))

    if "category_id" in body.model_fields_set and body.category_id is not None:
        cat = (
            await db.execute(
                select(ServiceCategory).where(
                    ServiceCategory.id == uuid.UUID(body.category_id),
                    ServiceCategory.tenant_id == tid,
                )
            )
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid category_id")
        svc.category_id = cat.id

    # Keep en translation row in sync with canonical name/description/suggestions
    en_sync = ServiceTranslationData(
        name=body.name if "name" in body.model_fields_set else None,
        description=body.description if "description" in body.model_fields_set else None,
        suggestions=body.suggestions if "suggestions" in body.model_fields_set else None,
    )
    if any(v is not None for v in [en_sync.name, en_sync.description, en_sync.suggestions]):
        await _upsert_translation(db, tid, svc.id, "en", en_sync, svc.name)

    # Apply explicit translation updates for any language
    for lang, tr_data in (body.translations or {}).items():
        await _upsert_translation(db, tid, svc.id, lang, tr_data, svc.name)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A service with that code already exists")

    await db.refresh(svc)
    svc, cat, tr, cat_tr = await _load_with_category(svc.id, tid, db, language)
    all_tr = await _load_translations(svc.id, db)
    return _to_detail(svc, cat, tr, cat_tr, all_tr)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_service(
    service_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    row = (
        await db.execute(
            select(Service).where(
                Service.id == uuid.UUID(service_id),
                Service.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    row.is_active = False
    await db.commit()


# ── Fee history (P-PAYROLL-1) ────────────────────────────────────────────────


class FeeHistoryRow(BaseModel):
    effective_from: str
    product_fee: str | None
    is_cost_percent: bool
    changed_by_user_id: str | None


@router.get("/{service_id}/fee-history", response_model=list[FeeHistoryRow])
async def get_service_fee_history(
    service_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FeeHistoryRow]:
    """Return the last 10 fee changes for a service, most recent first."""
    rows = (await db.execute(
        select(ServiceFeeHistory)
        .where(
            ServiceFeeHistory.service_id == uuid.UUID(service_id),
            ServiceFeeHistory.tenant_id == current_user.tenant_id,
        )
        .order_by(ServiceFeeHistory.effective_from.desc(),
                  ServiceFeeHistory.created_at.desc())
        .limit(10)
    )).scalars().all()
    return [
        FeeHistoryRow(
            effective_from=r.effective_from.isoformat(),
            product_fee=str(r.product_fee) if r.product_fee is not None else None,
            is_cost_percent=r.is_cost_percent,
            changed_by_user_id=str(r.created_by_user_id) if r.created_by_user_id else None,
        )
        for r in rows
    ]
