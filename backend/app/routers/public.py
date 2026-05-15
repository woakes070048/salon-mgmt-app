"""Unauthenticated, public-safe endpoints.

Used by the landing page (and potentially other guest-facing surfaces) to
fetch the salon's public info — name, contact, branding — without
requiring a session. Only fields safe for the open internet are exposed.

Phase 1 / single-tenant: returns the first active tenant. Once multi-tenancy
is live, this will accept a `?slug=` query param and route accordingly.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.acknowledgement import TenantAcknowledgement
from app.models.tenant import Tenant

router = APIRouter(prefix="/public", tags=["public"])


class PublicTenantInfo(BaseModel):
    name: str
    logo_url: str | None
    brand_color: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    region: str | None
    postal_code: str | None
    country: str | None
    phone: str | None
    hours_summary: str | None


@router.get("/tenant-info", response_model=PublicTenantInfo)
async def get_public_tenant_info(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PublicTenantInfo:
    tenant = (
        await db.execute(
            select(Tenant).where(Tenant.is_active == True).order_by(Tenant.created_at)  # noqa: E712
        )
    ).scalars().first()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No tenant configured")
    return PublicTenantInfo(
        name=tenant.name,
        logo_url=tenant.logo_url,
        brand_color=tenant.brand_color,
        address_line1=tenant.address_line1,
        address_line2=tenant.address_line2,
        city=tenant.city,
        region=tenant.region,
        postal_code=tenant.postal_code,
        country=tenant.country,
        phone=tenant.phone,
        hours_summary=tenant.hours_summary,
    )


class PublicAcknowledgement(BaseModel):
    id: str
    title: str
    body_text: str
    link_url: str | None
    link_text: str | None
    is_required: bool


@router.get("/acknowledgements", response_model=list[PublicAcknowledgement])
async def get_public_acknowledgements(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PublicAcknowledgement]:
    """Active acknowledgements for the booking form, ordered for display.

    Phase 1: returns the first active tenant's acknowledgements. Once multi-
    tenancy is live this will take a `?slug=` param.
    """
    tenant = (
        await db.execute(
            select(Tenant).where(Tenant.is_active == True).order_by(Tenant.created_at)  # noqa: E712
        )
    ).scalars().first()
    if tenant is None:
        return []
    rows = (await db.execute(
        select(TenantAcknowledgement)
        .where(
            TenantAcknowledgement.tenant_id == tenant.id,
            TenantAcknowledgement.is_active == True,  # noqa: E712
        )
        .order_by(TenantAcknowledgement.display_order.asc(),
                  TenantAcknowledgement.created_at.asc())
    )).scalars().all()
    return [
        PublicAcknowledgement(
            id=str(a.id),
            title=a.title,
            body_text=a.body_text,
            link_url=a.link_url,
            link_text=a.link_text,
            is_required=a.is_required,
        )
        for a in rows
    ]
