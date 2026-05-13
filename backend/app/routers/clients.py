import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select, desc, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from app.database import get_db
from app.deps import CurrentUser
from app.i18n import SUPPORTED_LANGUAGES
from app.models.client import Client, ClientColourNote, ClientHousehold
from app.models.appointment import Appointment, AppointmentItem, AppointmentStatus
from app.models.user import User
from app.models.provider import Provider
from app.models.service import Service
from app.models.sale import Sale

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientOut(BaseModel):
    id: str
    first_name: str
    last_name: str
    pronouns: str | None
    cell_phone: str | None
    email: str | None
    special_instructions: str | None
    no_show_count: int
    late_cancellation_count: int
    is_vip: bool
    language_preference: str
    preferred_provider_id: str | None
    preferred_provider_name: str | None

    model_config = {"from_attributes": True}


def _client_out(c: Client, provider_name: str | None = None) -> "ClientOut":
    return ClientOut(
        id=str(c.id),
        first_name=c.first_name,
        last_name=c.last_name,
        pronouns=c.pronouns,
        cell_phone=c.cell_phone,
        email=c.email,
        special_instructions=c.special_instructions,
        no_show_count=c.no_show_count,
        late_cancellation_count=c.late_cancellation_count,
        is_vip=c.is_vip,
        language_preference=c.language_preference,
        preferred_provider_id=str(c.preferred_provider_id) if c.preferred_provider_id else None,
        preferred_provider_name=provider_name,
    )


@router.get("", response_model=list[ClientOut])
async def search_clients(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query("", description="Search by name, phone, or email"),
    limit: int = Query(20, le=100),
) -> list[ClientOut]:
    stmt = select(Client).where(
        Client.tenant_id == current_user.tenant_id,
        Client.is_active == True,  # noqa: E712
    )
    if q.strip():
        term = f"%{q.strip()}%"
        full_name = func.concat(Client.first_name, ' ', Client.last_name)
        last_first = func.concat(Client.last_name, ', ', Client.first_name)
        stmt = stmt.where(
            or_(
                Client.first_name.ilike(term),
                Client.last_name.ilike(term),
                full_name.ilike(term),
                last_first.ilike(term),
                Client.cell_phone.ilike(term),
                Client.email.ilike(term),
            )
        )
    stmt = stmt.order_by(Client.last_name, Client.first_name).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    prov_ids = {c.preferred_provider_id for c in rows if c.preferred_provider_id}
    prov_names: dict[uuid.UUID, str] = {}
    if prov_ids:
        prov_rows = (await db.execute(
            select(Provider.id, Provider.display_name).where(Provider.id.in_(prov_ids))
        )).all()
        prov_names = {r.id: r.display_name for r in prov_rows}
    return [_client_out(c, prov_names.get(c.preferred_provider_id)) for c in rows]


@router.get("/check-duplicates", response_model=list[ClientOut])
async def check_duplicates(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    email: str = Query(""),
    phone: str = Query(""),
) -> list[ClientOut]:
    if not email.strip() and not phone.strip():
        return []
    conditions = []
    if email.strip():
        conditions.append(Client.email == email.strip())
    if phone.strip():
        conditions.append(Client.cell_phone == phone.strip())
    rows = (
        await db.execute(
            select(Client).where(
                Client.tenant_id == current_user.tenant_id,
                Client.is_active == True,  # noqa: E712
                or_(*conditions),
            ).order_by(Client.last_name, Client.first_name)
        )
    ).scalars().all()
    return [_client_out(c) for c in rows]


class ClientDetail(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str | None
    cell_phone: str | None
    pronouns: str | None
    special_instructions: str | None
    no_show_count: int
    late_cancellation_count: int
    is_vip: bool
    appointment_count: int
    household_id: str | None

    model_config = {"from_attributes": True}


class DuplicatePairOut(BaseModel):
    reason: str          # "email" | "phone" | "name"
    client_a: ClientDetail
    client_b: ClientDetail
    recommended_primary_id: str


def _client_detail(c: Client, appt_count: int) -> ClientDetail:
    return ClientDetail(
        id=str(c.id),
        first_name=c.first_name,
        last_name=c.last_name,
        email=c.email,
        cell_phone=c.cell_phone,
        pronouns=c.pronouns,
        special_instructions=c.special_instructions,
        no_show_count=c.no_show_count,
        late_cancellation_count=c.late_cancellation_count,
        is_vip=c.is_vip,
        appointment_count=appt_count,
        household_id=str(c.household_id) if c.household_id else None,
    )


@router.get("/duplicate-pairs", response_model=list[DuplicatePairOut])
async def get_duplicate_pairs(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DuplicatePairOut]:
    tid = current_user.tenant_id

    clients = (await db.execute(
        select(Client).where(Client.tenant_id == tid, Client.is_active == True)  # noqa: E712
    )).scalars().all()

    # Appointment counts per client
    count_rows = (await db.execute(
        select(Appointment.client_id, func.count(Appointment.id).label("cnt"))
        .where(Appointment.tenant_id == tid)
        .group_by(Appointment.client_id)
    )).all()
    counts: dict[uuid.UUID, int] = {r.client_id: r.cnt for r in count_rows}

    def detail(c: Client) -> ClientDetail:
        return _client_detail(c, counts.get(c.id, 0))

    # Build lookup maps
    email_map: dict[str, list[Client]] = {}
    phone_map: dict[str, list[Client]] = {}
    name_map: dict[str, list[Client]] = {}

    for c in clients:
        if c.email:
            key = c.email.lower().strip()
            email_map.setdefault(key, []).append(c)
        if c.cell_phone:
            key = "".join(ch for ch in c.cell_phone if ch.isdigit())
            if key:
                phone_map.setdefault(key, []).append(c)
        name_key = f"{c.first_name.lower().strip()}|{c.last_name.lower().strip()}"
        name_map.setdefault(name_key, []).append(c)

    seen_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    pairs: list[DuplicatePairOut] = []

    def _add_pairs(groups: dict[str, list[Client]], reason: str) -> None:
        for group in groups.values():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    key = (min(a.id, b.id), max(a.id, b.id))
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    cnt_a = counts.get(a.id, 0)
                    cnt_b = counts.get(b.id, 0)
                    rec = str(a.id) if cnt_a >= cnt_b else str(b.id)
                    # Put recommended (more history) as client_a
                    primary, secondary = (a, b) if cnt_a >= cnt_b else (b, a)
                    pairs.append(DuplicatePairOut(
                        reason=reason,
                        client_a=detail(primary),
                        client_b=detail(secondary),
                        recommended_primary_id=rec,
                    ))

    _add_pairs(email_map, "email")
    _add_pairs(phone_map, "phone")
    _add_pairs(name_map, "name")

    return pairs


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientOut:
    row = (
        await db.execute(
            select(Client).where(
                Client.id == uuid.UUID(client_id),
                Client.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return _client_out(row)


class ClientCreate(BaseModel):
    first_name: str
    last_name: str
    cell_phone: str | None = None
    email: str | None = None
    special_instructions: str | None = None


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientOut:
    tid = current_user.tenant_id
    # Generate a simple sequential-style code
    count = (await db.execute(
        select(Client).where(Client.tenant_id == tid)
    )).scalars()
    client_code = f"C{str(uuid.uuid4())[:8].upper()}"

    client = Client(
        tenant_id=tid,
        client_code=client_code,
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        cell_phone=body.cell_phone,
        email=body.email,
        special_instructions=body.special_instructions,
        country="CA",
        is_vip=False,
        is_active=True,
        no_show_count=0,
        late_cancellation_count=0,
        account_balance=0,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return _client_out(client)


class ClientUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    cell_phone: str | None = None
    language_preference: str | None = None
    preferred_provider_id: str | None = None
    clear_preferred_provider: bool = False


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: str,
    body: ClientUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientOut:
    row = (
        await db.execute(
            select(Client).where(
                Client.id == uuid.UUID(client_id),
                Client.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    if body.first_name is not None:
        row.first_name = body.first_name.strip()
    if body.last_name is not None:
        row.last_name = body.last_name.strip()
    if body.email is not None:
        row.email = body.email.strip() or None
    if body.cell_phone is not None:
        row.cell_phone = body.cell_phone.strip() or None
    if body.language_preference is not None:
        if body.language_preference not in SUPPORTED_LANGUAGES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"language_preference must be one of {SUPPORTED_LANGUAGES}",
            )
        row.language_preference = body.language_preference
    if body.clear_preferred_provider:
        row.preferred_provider_id = None
    elif body.preferred_provider_id is not None:
        prov = (await db.execute(
            select(Provider).where(
                Provider.id == uuid.UUID(body.preferred_provider_id),
                Provider.tenant_id == current_user.tenant_id,
            )
        )).scalar_one_or_none()
        if prov is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
        row.preferred_provider_id = prov.id
    await db.commit()
    await db.refresh(row)
    prov_name: str | None = None
    if row.preferred_provider_id:
        p = await db.get(Provider, row.preferred_provider_id)
        prov_name = p.display_name if p else None
    return _client_out(row, prov_name)


class ClientNotesUpdate(BaseModel):
    special_instructions: str | None


@router.patch("/{client_id}/notes", response_model=ClientOut)
async def update_client_notes(
    client_id: str,
    body: ClientNotesUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientOut:
    row = (
        await db.execute(
            select(Client).where(
                Client.id == uuid.UUID(client_id),
                Client.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    row.special_instructions = body.special_instructions
    await db.commit()
    await db.refresh(row)
    return _client_out(row)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    row = (
        await db.execute(
            select(Client).where(
                Client.id == uuid.UUID(client_id),
                Client.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    upcoming = (
        await db.execute(
            select(Appointment).where(
                Appointment.client_id == row.id,
                Appointment.tenant_id == current_user.tenant_id,
                Appointment.status.in_([AppointmentStatus.confirmed, AppointmentStatus.in_progress]),
                Appointment.appointment_date >= date.today(),
            )
        )
    ).scalars().first()
    if upcoming:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client has upcoming appointments and cannot be deleted",
        )

    row.is_active = False
    if row.user_id:
        linked_user = (
            await db.execute(select(User).where(User.id == row.user_id))
        ).scalar_one_or_none()
        if linked_user:
            linked_user.is_active = False
    await db.commit()


class VisitItem(BaseModel):
    service_name: str
    provider_name: str
    start_time: str  # ISO datetime string
    price: float


class VisitOut(BaseModel):
    appointment_id: str
    date: str
    status: str
    items: list[VisitItem]


@router.get("/{client_id}/history", response_model=list[VisitOut])
async def client_history(
    client_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[VisitOut]:
    client = (
        await db.execute(
            select(Client).where(
                Client.id == uuid.UUID(client_id),
                Client.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    appts = (
        await db.execute(
            select(Appointment)
            .where(
                Appointment.client_id == client.id,
                Appointment.tenant_id == current_user.tenant_id,
            )
            .order_by(desc(Appointment.appointment_date))
        )
    ).scalars().all()

    visits: list[VisitOut] = []
    for appt in appts:
        items_rows = (
            await db.execute(
                select(AppointmentItem, Service, Provider)
                .join(Service, AppointmentItem.service_id == Service.id)
                .join(Provider, AppointmentItem.provider_id == Provider.id)
                .where(AppointmentItem.appointment_id == appt.id)
                .order_by(AppointmentItem.sequence)
            )
        ).all()

        visits.append(VisitOut(
            appointment_id=str(appt.id),
            date=appt.appointment_date.strftime("%Y-%m-%d"),
            status=appt.status.value,
            items=[
                VisitItem(
                    service_name=svc.name,
                    provider_name=prov.display_name,
                    start_time=item.start_time.isoformat(),
                    price=float(item.price),
                )
                for item, svc, prov in items_rows
            ],
        ))
    return visits


# ── Colour notes ──────────────────────────────────────────────────────────────

class ColourNoteOut(BaseModel):
    id: str
    note_date: str
    note_text: str
    created_at: str

    model_config = {"from_attributes": True}


class ColourNoteCreate(BaseModel):
    note_date: date
    note_text: str


async def _get_client_or_404(client_id: str, tenant_id: uuid.UUID, db: AsyncSession) -> Client:
    client = (
        await db.execute(
            select(Client).where(
                Client.id == uuid.UUID(client_id),
                Client.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


@router.get("/{client_id}/colour-notes", response_model=list[ColourNoteOut])
async def list_colour_notes(
    client_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ColourNoteOut]:
    await _get_client_or_404(client_id, current_user.tenant_id, db)
    rows = (
        await db.execute(
            select(ClientColourNote)
            .where(
                ClientColourNote.client_id == uuid.UUID(client_id),
                ClientColourNote.tenant_id == current_user.tenant_id,
            )
            .order_by(desc(ClientColourNote.note_date), desc(ClientColourNote.created_at))
        )
    ).scalars().all()
    return [
        ColourNoteOut(
            id=str(r.id),
            note_date=r.note_date.strftime("%Y-%m-%d"),
            note_text=r.note_text,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.post("/{client_id}/colour-notes", response_model=ColourNoteOut, status_code=status.HTTP_201_CREATED)
async def create_colour_note(
    client_id: str,
    body: ColourNoteCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ColourNoteOut:
    await _get_client_or_404(client_id, current_user.tenant_id, db)
    note = ClientColourNote(
        tenant_id=current_user.tenant_id,
        client_id=uuid.UUID(client_id),
        created_by_user_id=current_user.id,
        note_date=body.note_date,
        note_text=body.note_text.strip(),
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return ColourNoteOut(
        id=str(note.id),
        note_date=note.note_date.strftime("%Y-%m-%d"),
        note_text=note.note_text,
        created_at=note.created_at.isoformat(),
    )


# ── Client cleanup: duplicate detection ──────────────────────────────────────

# ── Client merge ──────────────────────────────────────────────────────────────

class MergeBody(BaseModel):
    source_id: str


@router.post("/{primary_id}/merge", response_model=ClientDetail)
async def merge_clients(
    primary_id: str,
    body: MergeBody,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientDetail:
    tid = current_user.tenant_id
    pid = uuid.UUID(primary_id)
    sid = uuid.UUID(body.source_id)

    if pid == sid:
        raise HTTPException(status_code=400, detail="Cannot merge a client with itself")

    primary = (await db.execute(
        select(Client).where(Client.id == pid, Client.tenant_id == tid)
    )).scalar_one_or_none()
    source = (await db.execute(
        select(Client).where(Client.id == sid, Client.tenant_id == tid, Client.is_active == True)  # noqa: E712
    )).scalar_one_or_none()

    if not primary or not source:
        raise HTTPException(status_code=404, detail="Client not found")

    # Re-point appointments, colour notes, and sales
    await db.execute(
        update(Appointment)
        .where(Appointment.client_id == sid, Appointment.tenant_id == tid)
        .values(client_id=pid)
    )
    await db.execute(
        update(ClientColourNote)
        .where(ClientColourNote.client_id == sid, ClientColourNote.tenant_id == tid)
        .values(client_id=pid)
    )
    await db.execute(
        update(Sale)
        .where(Sale.client_id == sid, Sale.tenant_id == tid)
        .values(client_id=pid)
    )

    # Copy missing contact fields from source → primary
    for field in ("email", "cell_phone", "home_phone", "work_phone",
                  "address_line", "city", "province", "postal_code",
                  "special_instructions", "pronouns", "photo_url"):
        if not getattr(primary, field) and getattr(source, field):
            setattr(primary, field, getattr(source, field))

    # Sum counters
    primary.no_show_count += source.no_show_count
    primary.late_cancellation_count += source.late_cancellation_count

    # Transfer household if primary has none
    if not primary.household_id and source.household_id:
        primary.household_id = source.household_id

    # Soft-delete source
    source.is_active = False

    await db.commit()
    await db.refresh(primary)

    from sqlalchemy import func as sqlfunc
    new_count = (await db.execute(
        select(sqlfunc.count(Appointment.id))
        .where(Appointment.client_id == pid, Appointment.tenant_id == tid)
    )).scalar_one()

    return _client_detail(primary, new_count)


# ── Household membership ──────────────────────────────────────────────────────

class HouseholdPatch(BaseModel):
    household_id: str | None


@router.patch("/{client_id}/household", response_model=ClientDetail)
async def set_household(
    client_id: str,
    body: HouseholdPatch,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientDetail:
    tid = current_user.tenant_id
    client = (await db.execute(
        select(Client).where(Client.id == uuid.UUID(client_id), Client.tenant_id == tid)
    )).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if body.household_id:
        hh = (await db.execute(
            select(ClientHousehold).where(
                ClientHousehold.id == uuid.UUID(body.household_id),
                ClientHousehold.tenant_id == tid,
            )
        )).scalar_one_or_none()
        if not hh:
            raise HTTPException(status_code=404, detail="Household not found")
        client.household_id = hh.id
    else:
        client.household_id = None

    await db.commit()
    await db.refresh(client)
    cnt = (await db.execute(
        select(func.count(Appointment.id))
        .where(Appointment.client_id == client.id, Appointment.tenant_id == tid)
    )).scalar_one()
    return _client_detail(client, cnt)
