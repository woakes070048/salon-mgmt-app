"""Entity resolver for the inbound email booking flow.

Loads the service catalogue (with aliases) and active provider list from the DB,
and resolves raw name strings to UUIDs using case-insensitive matching with a
simple similarity fallback.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider import Provider
from app.models.scheduling import ServiceAlias
from app.models.service import Service


# ── Catalogue loaders ─────────────────────────────────────────────────────────


async def load_service_catalogue(db: AsyncSession, tenant_id: uuid.UUID) -> list[dict]:
    """Return [{id, name, aliases: [str]}] for all active services in the tenant."""
    svc_rows = (
        await db.execute(
            select(Service).where(
                Service.tenant_id == tenant_id,
                Service.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    if not svc_rows:
        return []

    svc_ids = [s.id for s in svc_rows]
    alias_rows = (
        await db.execute(
            select(ServiceAlias).where(
                ServiceAlias.tenant_id == tenant_id,
                ServiceAlias.service_id.in_(svc_ids),
            )
        )
    ).scalars().all()

    aliases_by_service: dict[uuid.UUID, list[str]] = {}
    for alias in alias_rows:
        aliases_by_service.setdefault(alias.service_id, []).append(alias.alias)

    return [
        {
            "id": str(s.id),
            "name": s.name,
            "aliases": aliases_by_service.get(s.id, []),
        }
        for s in svc_rows
    ]


async def load_provider_list(db: AsyncSession, tenant_id: uuid.UUID) -> list[dict]:
    """Return [{id, display_name}] for all active providers in the tenant."""
    rows = (
        await db.execute(
            select(Provider).where(
                Provider.tenant_id == tenant_id,
                Provider.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    return [{"id": str(p.id), "display_name": p.display_name} for p in rows]


# ── Resolvers ─────────────────────────────────────────────────────────────────


async def resolve_service(
    db: AsyncSession, tenant_id: uuid.UUID, name: str
) -> uuid.UUID | None:
    """Resolve a raw service name string to a service UUID.

    Tries, in order:
    1. Exact case-insensitive match on service.name
    2. Exact case-insensitive match on any service_alias.alias
    3. Prefix match (name starts with the search term or vice versa)

    Returns None if no match found.
    """
    if not name or not name.strip():
        return None

    normalised = name.strip().lower()

    # 1. Exact match on service name
    row = (
        await db.execute(
            select(Service).where(
                Service.tenant_id == tenant_id,
                Service.is_active == True,  # noqa: E712
                func.lower(Service.name) == normalised,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row.id

    # 2. Exact match on alias
    alias_row = (
        await db.execute(
            select(ServiceAlias).where(
                ServiceAlias.tenant_id == tenant_id,
                func.lower(ServiceAlias.alias) == normalised,
            )
        )
    ).scalar_one_or_none()
    if alias_row is not None:
        return alias_row.service_id

    # 3. Prefix / contains match on service name
    services = (
        await db.execute(
            select(Service).where(
                Service.tenant_id == tenant_id,
                Service.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    best: uuid.UUID | None = None
    best_len = 0
    for svc in services:
        svc_lower = svc.name.lower()
        if normalised in svc_lower or svc_lower in normalised:
            match_len = min(len(normalised), len(svc_lower))
            if match_len > best_len:
                best_len = match_len
                best = svc.id

    return best


async def resolve_provider(
    db: AsyncSession, tenant_id: uuid.UUID, name: str
) -> uuid.UUID | None:
    """Resolve a raw provider name string to a provider UUID.

    Case-insensitive exact match on display_name, with a contains fallback.
    Returns None if no match found.
    """
    if not name or not name.strip():
        return None

    normalised = name.strip().lower()

    # Exact match
    row = (
        await db.execute(
            select(Provider).where(
                Provider.tenant_id == tenant_id,
                Provider.is_active == True,  # noqa: E712
                func.lower(Provider.display_name) == normalised,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row.id

    # Contains match
    providers = (
        await db.execute(
            select(Provider).where(
                Provider.tenant_id == tenant_id,
                Provider.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    for prov in providers:
        if normalised in prov.display_name.lower() or prov.display_name.lower() in normalised:
            return prov.id

    return None
