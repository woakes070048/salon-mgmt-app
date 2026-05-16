"""
One-time import of legacy Salon Lyol data.

Called from the POST /admin/import-legacy endpoint and scripts/run_import.py.
All functions are idempotent — safe to re-run.
"""

import csv
import io
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Booking service code → DB service_code
# ---------------------------------------------------------------------------
SERVICE_CODE_MAP: dict[str, str] = {
    "ST1H":    "st1h",
    "ST2H":    "st2h",
    "ST2H+":   "ST2P",
    "SBD":     "sbd",
    "CRTU":    "crtu",
    "CRTUB":   "crtub",
    "CPHHL":   "cphhl",
    "CFHHL":   "cfhhl",
    "CAHL":    "cahl",
    "CTAO":    "ctao",
    "CTSA":    "ctsa",
    "CB":      "cb",
    "CBT":     "cbt",
    "CCAMO":   "CCAMO",
    "CFC":     "CFC",
    "CVC":     "CVC",
    "CRE":     "cre",
    "MTAO":    "mtao",
    "MTSA":    "mtsa",
    "OLAPLEX": "olaplex",
    "METAL":   "metal",
    "FRINGE":  "fringe",
    "HBWHC":   "hbwhc",
    "HBWOHC":  "hbwohc",
    "HBE":     "hbe",
    "CON":     "con",
    "CAC":     "cac",
    "SHTF":    "shtf",
    "SAS":     "sas",
    "SBD5+1":  "sbd",      # Blowdry bundle → Blowdry
    "SUD":     "sud",
    "EXT":     "EXT",      # Hair Extensions
    "CCO":     "cco",
    "TRE 1":   "tre1",
    "REDO":    "redo",
    "PERM":    "PERM",
}

# ---------------------------------------------------------------------------
# Receipt description → DB service_code  (lowercase key for case-insensitive match)
# Descriptions not in this map are treated as retail sale items.
# ---------------------------------------------------------------------------
RECEIPT_SERVICE_MAP: dict[str, str] = {
    "type 1 haircut":                   "st1h",
    "type 2 haircut":                   "st2h",
    "type 2+ haircut":                  "ST2P",
    "blowdry":                          "sbd",
    "root touch-up":                    "crtu",
    "root touch-up(bleach/highlift)":   "crtub",
    "partial head highlights":          "cphhl",
    "full head highlights":             "cfhhl",
    "accent high lights(under 15foi":   "ACC",
    "toner add-on":                     "ctao",
    "toner/gloss stand alone":          "ctsa",
    "consultation":                     "con",
    "additional colour":                "cac",
    "balayage full":                    "cb",
    "balayage touch-up":                "cbt",
    "camo color":                       "CCAMO",
    "color full color":                 "CFC",
    "vivid color":                      "CVC",
    "refreshing ends":                  "cre",
    "milbon treatment add-on":          "mtao",
    "milbon treatment stand alone":     "mtsa",
    "olaplex":                          "olaplex",
    "metal detox":                      "metal",
    "fringe cut":                       "fringe",
    "mk hair botox with home care":     "hbwhc",
    "mk hairbotox without homecare":    "hbwohc",
    "hair extensions":                  "EXT",
    "color correction":                 "cco",
    "updo":                             "sud",
    "special updo":                     "sud",
    "heat tool finish":                 "shtf",
    "treatments 1":                     "tre1",
    "additonal styling":                "sas",
    # These are service-like but have no catalog entry — kept as service kind
    # so they don't inflate retail revenue in reports
    "perm":                             "PERM",
    "redo":                             None,
    "color additional":                 None,
    "bdb reimbursement by house":       None,
    "blow dry bundle 5+1":              "sbd",
}

# Descriptions that are services even though they have no service_code mapping.
# Anything else is retail.
_SERVICE_DESCS: set[str] = set(RECEIPT_SERVICE_MAP.keys())


def _is_service(description: str) -> bool:
    return description.lower() in _SERVICE_DESCS


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _read_csv(content: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(content.decode("latin-1"))))


def _clean_phone(raw: str) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw.strip())
    if len(digits) < 7 or digits == "4160000000":
        return None
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == "1":
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return raw.strip()


def _clean_email(raw: str) -> str | None:
    v = (raw or "").strip()
    if "@" not in v or "." not in v.split("@")[-1]:
        return None
    return v.lower()


def _parse_name(full: str) -> tuple[str, str]:
    parts = full.strip().split(None, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


def _parse_dt(date_str: str, time_str: str) -> datetime:
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d %I:%M:%S %p"):
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {date_str!r} {time_str!r}")


def _parse_date_noon(date_str: str) -> datetime:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(hour=12)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str!r}")


# ---------------------------------------------------------------------------
# DB lookup helpers
# ---------------------------------------------------------------------------

async def _load_providers(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    rows = (await db.execute(
        text("SELECT id, display_name FROM providers WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )).fetchall()
    return {r.display_name.upper(): r.id for r in rows if r.display_name}


async def _load_service_detail(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, dict]:
    rows = (await db.execute(
        text("SELECT id, service_code, default_price, duration_minutes "
             "FROM services WHERE tenant_id = :tid AND is_active = true"),
        {"tid": tenant_id},
    )).fetchall()
    return {
        r.service_code.lower(): {"id": r.id, "price": float(r.default_price or 0), "duration": r.duration_minutes}
        for r in rows
    }


async def _load_client_map(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    rows = (await db.execute(
        text("SELECT id, legacy_id FROM clients WHERE tenant_id = :tid AND legacy_id IS NOT NULL"),
        {"tid": tenant_id},
    )).fetchall()
    return {r.legacy_id: r.id for r in rows}


async def _ensure_house_provider(
    db: AsyncSession, tenant_id: uuid.UUID, provider_map: dict[str, uuid.UUID]
) -> uuid.UUID:
    """Return the HOUSE provider id, creating it if needed."""
    if "HOUSE" in provider_map:
        return provider_map["HOUSE"]
    new_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO providers (id, tenant_id, first_name, last_name, display_name,"
            " provider_type, is_owner, is_active,"
            " can_be_cashier, makes_appointments, has_appointments, booking_order,"
            " online_booking_visibility, created_at, updated_at)"
            " VALUES (:id, :tid, 'House', 'Account', 'HOUSE',"
            " 'stylist', false, false,"
            " false, false, false, 99,"
            " 'not_available', NOW(), NOW())"
        ),
        {"id": new_id, "tid": tenant_id},
    )
    provider_map["HOUSE"] = new_id
    return new_id


async def _ensure_walk_in_client(
    db: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID:
    """Return a placeholder client for walk-in cash sales, creating it if needed."""
    row = (await db.execute(
        text("SELECT id FROM clients WHERE tenant_id = :tid AND legacy_id = 'WALK_IN' LIMIT 1"),
        {"tid": tenant_id},
    )).fetchone()
    if row:
        return row.id
    new_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO clients (id, tenant_id, first_name, last_name, is_active,"
            " legacy_id, created_at, updated_at)"
            " VALUES (:id, :tid, 'Walk-In', 'Client', true, 'WALK_IN', NOW(), NOW())"
        ),
        {"id": new_id, "tid": tenant_id},
    )
    return new_id


async def _ensure_unknown_payment_method(
    db: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID:
    """Return the 'unknown' payment method id, creating it if needed."""
    row = (await db.execute(
        text("SELECT id FROM tenant_payment_methods WHERE tenant_id = :tid AND code = 'unknown'"),
        {"tid": tenant_id},
    )).fetchone()
    if row:
        return row.id
    new_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO tenant_payment_methods (id, tenant_id, code, label, kind,"
            " is_active, sort_order, created_at, updated_at)"
            " VALUES (:id, :tid, 'unknown', 'Unknown', 'other', true, 99, NOW(), NOW())"
        ),
        {"id": new_id, "tid": tenant_id},
    )
    return new_id


# ---------------------------------------------------------------------------
# Client import
# ---------------------------------------------------------------------------

async def import_clients(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    content: bytes,
) -> dict:
    rows = _read_csv(content)
    provider_map = await _load_providers(db, tenant_id)

    # Load all existing legacy_ids in one query
    existing_ids: dict[str, uuid.UUID] = {
        r.legacy_id: r.id
        for r in (await db.execute(
            text("SELECT id, legacy_id FROM clients WHERE tenant_id = :tid AND legacy_id IS NOT NULL"),
            {"tid": tenant_id},
        )).fetchall()
    }

    to_insert = []
    to_update = []
    skipped = 0

    for row in rows:
        code = (row.get("Code") or "").strip().lstrip("|")[:20]
        name = (row.get("Name") or "").strip()
        if not code or not name:
            skipped += 1
            continue
        first_name, last_name = _parse_name(name)
        email = _clean_email(row.get("Email") or "")
        cell = _clean_phone(row.get("Cell Phone") or "")
        staff = (row.get("Staff") or "").strip().upper()
        preferred_provider_id = provider_map.get(staff) if staff else None
        params = {"fn": first_name, "ln": last_name, "email": email,
                  "cell": cell, "ppid": preferred_provider_id}
        if code in existing_ids:
            to_update.append({**params, "id": existing_ids[code], "tid": tenant_id})
        else:
            to_insert.append({**params, "id": uuid.uuid4(), "tid": tenant_id, "code": code})

    # Batch insert in chunks of 500
    CHUNK = 500
    for i in range(0, len(to_insert), CHUNK):
        chunk = to_insert[i:i + CHUNK]
        await db.execute(
            text(
                "INSERT INTO clients (id, tenant_id, client_code, legacy_id,"
                " first_name, last_name, email, cell_phone, preferred_provider_id,"
                " country, is_active, is_vip, no_show_count, late_cancellation_count,"
                " account_balance, created_at, updated_at)"
                " VALUES (:id, :tid, :code, :code, :fn, :ln, :email, :cell, :ppid,"
                " 'CA', true, false, 0, 0, 0, NOW(), NOW())"
            ),
            chunk,
        )

    # Batch update
    for i in range(0, len(to_update), CHUNK):
        chunk = to_update[i:i + CHUNK]
        await db.execute(
            text(
                "UPDATE clients SET first_name = :fn, last_name = :ln, email = :email,"
                " cell_phone = :cell, preferred_provider_id = :ppid, updated_at = NOW()"
                " WHERE id = :id AND tenant_id = :tid"
            ),
            chunk,
        )

    await db.commit()
    return {"created": len(to_insert), "updated": len(to_update), "skipped": skipped}


# ---------------------------------------------------------------------------
# Future booking import  (All Bookings.txt or Future and Past Bookings.txt)
# ---------------------------------------------------------------------------

async def import_bookings(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    content: bytes,
    future_only: bool = True,
) -> dict:
    rows = _read_csv(content)
    today = datetime.now()

    if future_only:
        def _safe_future(r: dict) -> bool:
            try:
                return bool(r.get("Date")) and datetime.strptime(r["Date"].strip(), "%m/%d/%Y") >= today
            except (ValueError, AttributeError):
                return False
        rows = [r for r in rows if _safe_future(r)]

    provider_map = await _load_providers(db, tenant_id)
    service_detail = await _load_service_detail(db, tenant_id)
    client_map = await _load_client_map(db, tenant_id)

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        code = (row.get("Code") or "").strip()
        date_str = (row.get("Date") or "").strip()
        if code and date_str:
            groups[(code, date_str)].append(row)
    for key in groups:
        groups[key].sort(key=lambda r: r.get("TimeInt") or r.get("Time") or "")

    created = skipped_existing = skipped_no_client = skipped_no_service = skipped_no_provider = 0
    unmapped: set[str] = set()

    for (client_code, date_str), items in groups.items():
        client_id = client_map.get(client_code)
        if not client_id:
            skipped_no_client += 1
            continue

        try:
            appt_dt = _parse_dt(date_str, items[0]["Time"])
        except (ValueError, KeyError):
            skipped_no_client += 1
            continue

        existing = (await db.execute(
            text("SELECT id FROM appointments"
                 " WHERE tenant_id = :tid AND client_id = :cid AND appointment_date = :dt"),
            {"tid": tenant_id, "cid": client_id, "dt": appt_dt},
        )).fetchone()
        if existing:
            skipped_existing += 1
            continue

        resolved = []
        skip_group = False
        for seq, item in enumerate(items, start=1):
            legacy_svc = (item.get("Service") or "").strip()
            db_code = SERVICE_CODE_MAP.get(legacy_svc) or SERVICE_CODE_MAP.get(legacy_svc.upper())
            svc = service_detail.get(db_code.lower()) if db_code else None
            if not svc:
                unmapped.add(legacy_svc)
                skip_group = True
                break
            staff = (item.get("Staff") or "").strip().upper()
            provider_id = provider_map.get(staff)
            if not provider_id:
                skipped_no_provider += 1
                skip_group = True
                break
            try:
                item_dt = _parse_dt(date_str, item["Time"])
            except (ValueError, KeyError):
                skip_group = True
                break
            resolved.append({"seq": seq, "service_id": svc["id"], "provider_id": provider_id,
                              "start_time": item_dt, "duration": svc["duration"], "price": svc["price"]})

        if skip_group or not resolved:
            skipped_no_service += 1
            continue

        appt_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO appointments (id, tenant_id, client_id, appointment_date,"
                 " source, status, confirmation_status, is_recurring, created_at, updated_at)"
                 " VALUES (:id, :tid, :cid, :dt,"
                 " 'staff_entered', 'confirmed', 'not_sent', false, NOW(), NOW())"),
            {"id": appt_id, "tid": tenant_id, "cid": client_id, "dt": appt_dt},
        )
        for ri in resolved:
            await db.execute(
                text("INSERT INTO appointment_items (id, tenant_id, appointment_id,"
                     " service_id, provider_id, sequence, start_time, duration_minutes, price,"
                     " price_is_locked, status, created_at, updated_at)"
                     " VALUES (:id, :tid, :appt_id, :svc_id, :prov_id, :seq, :st, :dur, :price,"
                     " true, 'pending', NOW(), NOW())"),
                {"id": uuid.uuid4(), "tid": tenant_id, "appt_id": appt_id,
                 "svc_id": ri["service_id"], "prov_id": ri["provider_id"],
                 "seq": ri["seq"], "st": ri["start_time"],
                 "dur": ri["duration"], "price": ri["price"]},
            )
        created += 1

    await db.commit()
    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_no_client": skipped_no_client,
        "skipped_no_service": skipped_no_service,
        "skipped_no_provider": skipped_no_provider,
        "unmapped_service_codes": sorted(unmapped),
    }


# ---------------------------------------------------------------------------
# Receipt Transactions import  (completed appointments + sales)
# ---------------------------------------------------------------------------

async def import_receipts(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    receipts_content: bytes,
    bookings_content: bytes,
) -> dict:
    receipt_rows = _read_csv(receipts_content)
    booking_rows = _read_csv(bookings_content)

    provider_map = await _load_providers(db, tenant_id)
    service_detail = await _load_service_detail(db, tenant_id)
    client_map = await _load_client_map(db, tenant_id)

    house_id = await _ensure_house_provider(db, tenant_id, provider_map)
    unknown_pm_id = await _ensure_unknown_payment_method(db, tenant_id)
    walk_in_client_id = await _ensure_walk_in_client(db, tenant_id)

    # Build booking time lookup: (client_code, date_str) → earliest Time string
    booking_time: dict[tuple[str, str], str] = {}
    booking_time_int: dict[tuple[str, str], int] = {}
    for r in booking_rows:
        code = (r.get("Code") or "").strip()
        date = (r.get("Date") or "").strip()
        time_str = (r.get("Time") or "").strip()
        if not code or not date or not time_str:
            continue
        try:
            ti = int(r.get("TimeInt") or 9999)
        except (ValueError, TypeError):
            ti = 9999
        key = (code, date)
        if ti < booking_time_int.get(key, 9999):
            booking_time[key] = time_str
            booking_time_int[key] = ti
        elif key not in booking_time:
            booking_time[key] = time_str
            booking_time_int[key] = ti

    # Group receipt rows by receipt number
    receipt_groups: dict[str, list[dict]] = defaultdict(list)
    for r in receipt_rows:
        rnum = (r.get("Receipt") or "").strip()
        if rnum:
            receipt_groups[rnum].append(r)

    created = updated = skipped_existing = skipped_no_client = walk_in_created = errors = 0

    for receipt_num, items in receipt_groups.items():
        client_code = (items[0].get("Client") or "").strip()
        date_str = (items[0].get("Date") or "").strip()
        note_key = f"legacy_receipt:{receipt_num}"
        is_walk_in = client_code == "WALK_IN"

        if is_walk_in:
            # WALK_IN receipts have no client — create a sale-only record (no appointment).
            # Dedup: skip if a sale with this receipt note already exists.
            existing_walk_in_sale = (await db.execute(
                text("SELECT id FROM sales WHERE tenant_id = :tid AND notes = :note"),
                {"tid": tenant_id, "note": note_key},
            )).fetchone()
            if existing_walk_in_sale:
                skipped_existing += 1
                continue

            try:
                appt_dt = _parse_date_noon(date_str)
            except ValueError:
                errors += 1
                continue

            subtotal = sum(float(r.get("Amount") or 0) for r in items)
            gst_total = sum(float(r.get("GST") or 0) for r in items)
            pst_total = sum(float(r.get("PST") or 0) for r in items)
            total = subtotal + gst_total + pst_total
            completed_at = appt_dt.replace(tzinfo=timezone.utc)

            sale_id = uuid.uuid4()
            await db.execute(
                text("INSERT INTO sales (id, tenant_id, client_id, subtotal, discount_total,"
                     " gst_amount, pst_amount, total, status, notes, completed_at,"
                     " created_at, updated_at)"
                     " VALUES (:id, :tid, :cid, :sub, 0, :gst, :pst, :total,"
                     " 'completed', :note, :cat, NOW(), NOW())"),
                {"id": sale_id, "tid": tenant_id, "cid": walk_in_client_id,
                 "sub": Decimal(str(round(subtotal, 2))),
                 "gst": Decimal(str(round(gst_total, 2))),
                 "pst": Decimal(str(round(pst_total, 2))),
                 "total": Decimal(str(round(total, 2))),
                 "note": note_key, "cat": completed_at},
            )

            for idx, item in enumerate(items):
                desc = (item.get("Description") or "").strip()
                staff = (item.get("Staff") or "").strip().upper()
                amount = float(item.get("Amount") or 0)
                qty = int(item.get("Quantity") or 1)
                kind = "service" if _is_service(desc) else "retail"
                provider_id = provider_map.get(staff) if staff else None
                # Milano exports Amount as the LINE TOTAL (subtotal), not unit price.
                # GST = Amount × 5% confirms this for all qty>1 records.
                line_total = Decimal(str(round(amount, 2)))
                unit_price = Decimal(str(round(amount / qty, 4))) if qty > 1 else line_total
                await db.execute(
                    text("INSERT INTO sale_items (id, tenant_id, sale_id, appointment_item_id,"
                         " description, provider_id, kind, sequence, quantity,"
                         " unit_price, discount_amount, line_total, created_at, updated_at)"
                         " VALUES (:id, :tid, :sale_id, NULL,"
                         " :desc, :prov_id, :kind, :seq, :qty,"
                         " :unit_price, 0, :line_total, NOW(), NOW())"),
                    {"id": uuid.uuid4(), "tid": tenant_id, "sale_id": sale_id,
                     "desc": desc, "prov_id": provider_id,
                     "kind": kind, "seq": idx + 1, "qty": qty,
                     "unit_price": unit_price,
                     "line_total": line_total},
                )

            await db.execute(
                text("INSERT INTO sale_payments (id, tenant_id, sale_id, payment_method_id,"
                     " amount, cashback_amount, created_at, updated_at)"
                     " VALUES (:id, :tid, :sale_id, :pm_id, :amount, 0, NOW(), NOW())"),
                {"id": uuid.uuid4(), "tid": tenant_id,
                 "sale_id": sale_id, "pm_id": unknown_pm_id,
                 "amount": Decimal(str(round(total, 2)))},
            )
            walk_in_created += 1

            if walk_in_created % 200 == 0:
                await db.commit()
            continue

        client_id = client_map.get(client_code)
        if not client_id:
            skipped_no_client += 1
            continue

        # Appointment time: use booking record if available, else noon
        bk_time = booking_time.get((client_code, date_str))
        try:
            appt_dt = (_parse_dt(date_str, bk_time) if bk_time
                       else _parse_date_noon(date_str))
        except ValueError:
            appt_dt = _parse_date_noon(date_str)
        date_only = appt_dt.date()

        # Dedup: check if this receipt was already imported
        existing_receipt_appt = (await db.execute(
            text("SELECT id FROM appointments WHERE tenant_id = :tid AND notes = :note"),
            {"tid": tenant_id, "note": note_key},
        )).fetchone()

        if existing_receipt_appt:
            # If there's also an un-processed confirmed appointment for the same client/date,
            # this is a leftover duplicate from a previous import run. Clean it up so we
            # can re-process the receipt against the correct appointment.
            confirmed_dup = (await db.execute(
                text("SELECT id FROM appointments"
                     " WHERE tenant_id = :tid AND client_id = :cid"
                     " AND appointment_date::date = :date"
                     " AND status NOT IN ('completed', 'cancelled')"),
                {"tid": tenant_id, "cid": client_id, "date": date_only},
            )).fetchone()
            if not confirmed_dup:
                skipped_existing += 1
                continue
            # Delete the old receipt-created appointment and its sale so we can re-import
            dup_id = existing_receipt_appt.id
            sale_row = (await db.execute(
                text("SELECT sale_id FROM sale_appointments WHERE appointment_id = :id"),
                {"id": dup_id},
            )).fetchone()
            if sale_row:
                sid = sale_row.sale_id
                await db.execute(text("DELETE FROM sale_payments WHERE sale_id = :id"), {"id": sid})
                await db.execute(text("DELETE FROM sale_items WHERE sale_id = :id"), {"id": sid})
                await db.execute(text("DELETE FROM sale_appointments WHERE sale_id = :id"), {"id": sid})
                await db.execute(text("DELETE FROM sales WHERE id = :id"), {"id": sid})
            await db.execute(text("DELETE FROM appointment_items WHERE appointment_id = :id"), {"id": dup_id})
            await db.execute(text("DELETE FROM appointments WHERE id = :id"), {"id": dup_id})
            # Fall through to process the receipt against the confirmed appointment

        # Prefer updating an existing confirmed/pending appointment over creating a new one
        existing_appt = (await db.execute(
            text("SELECT id FROM appointments"
                 " WHERE tenant_id = :tid AND client_id = :cid"
                 " AND appointment_date::date = :date"
                 " AND status NOT IN ('completed', 'cancelled')"),
            {"tid": tenant_id, "cid": client_id, "date": date_only},
        )).fetchone()
        use_existing = existing_appt is not None

        # Totals
        subtotal = sum(float(r.get("Amount") or 0) for r in items)
        gst_total = sum(float(r.get("GST") or 0) for r in items)
        pst_total = sum(float(r.get("PST") or 0) for r in items)
        total = subtotal + gst_total + pst_total
        completed_at = appt_dt.replace(tzinfo=timezone.utc)

        receipt_item_to_appt_item: dict[int, uuid.UUID] = {}

        if use_existing:
            appt_id = existing_appt.id
            await db.execute(
                text("UPDATE appointments SET status = 'completed', notes = :note, updated_at = NOW()"
                     " WHERE id = :id"),
                {"note": note_key, "id": appt_id},
            )
            await db.execute(
                text("UPDATE appointment_items SET status = 'completed', updated_at = NOW()"
                     " WHERE appointment_id = :id"),
                {"id": appt_id},
            )

            # Match each service receipt line to one of the existing appointment_items
            # so the resulting sale_items can carry appointment_item_id. Without this
            # link, per-provider reports (Payroll, Service Performance) inner-join
            # through appointment_items and silently drop the row. See P-IMPORT-LINK.
            existing_ai_rows = (await db.execute(
                text("SELECT id, service_id, provider_id, sequence FROM appointment_items"
                     " WHERE appointment_id = :id ORDER BY sequence"),
                {"id": appt_id},
            )).fetchall()
            # Pool keyed by (provider_id, service_id) → consumable list of ai_ids in
            # sequence order. Duplicates (e.g. two haircuts by Sarah) are matched FIFO.
            ai_pool: dict[tuple, list[uuid.UUID]] = {}
            for r in existing_ai_rows:
                ai_pool.setdefault((r.provider_id, r.service_id), []).append(r.id)
            # Fallback pool keyed by service_id alone, for receipts where the staff
            # column doesn't match the booked provider (mistakes happen).
            svc_only_pool: dict[uuid.UUID, list[uuid.UUID]] = {}
            for r in existing_ai_rows:
                svc_only_pool.setdefault(r.service_id, []).append(r.id)

            for idx, item in enumerate(items):
                desc = (item.get("Description") or "").strip()
                if not _is_service(desc):
                    continue
                db_code = RECEIPT_SERVICE_MAP.get(desc.lower())
                svc = service_detail.get(db_code.lower()) if db_code else None
                if not svc:
                    continue
                staff = (item.get("Staff") or "").strip().upper()
                receipt_prov = provider_map.get(staff) if staff else None
                svc_id = svc["id"]
                key = (receipt_prov, svc_id)
                if key in ai_pool and ai_pool[key]:
                    ai_id = ai_pool[key].pop(0)
                    # Also remove from the service-only fallback so it isn't reused.
                    svc_only_pool.get(svc_id, []).remove(ai_id)
                elif svc_id in svc_only_pool and svc_only_pool[svc_id]:
                    ai_id = svc_only_pool[svc_id].pop(0)
                    # Remove from the (prov, svc) pool too if present under any key.
                    for v in ai_pool.values():
                        if ai_id in v:
                            v.remove(ai_id)
                            break
                else:
                    continue
                receipt_item_to_appt_item[idx] = ai_id

            updated += 1
        else:
            # No prior booking record — create a new completed appointment (historical data)
            appt_id = uuid.uuid4()
            await db.execute(
                text("INSERT INTO appointments (id, tenant_id, client_id, appointment_date,"
                     " source, status, confirmation_status, is_recurring, notes, created_at, updated_at)"
                     " VALUES (:id, :tid, :cid, :dt,"
                     " 'staff_entered', 'completed', 'skipped', false, :note, NOW(), NOW())"),
                {"id": appt_id, "tid": tenant_id, "cid": client_id,
                 "dt": appt_dt, "note": note_key},
            )
            appt_item_seq = 1
            for idx, item in enumerate(items):
                desc = (item.get("Description") or "").strip()
                staff = (item.get("Staff") or "").strip().upper()
                amount = float(item.get("Amount") or 0)
                if not _is_service(desc):
                    continue
                db_code = RECEIPT_SERVICE_MAP.get(desc.lower())
                svc = service_detail.get(db_code.lower()) if db_code else None
                provider_id = provider_map.get(staff) if staff else house_id
                if not provider_id:
                    provider_id = house_id
                if svc:
                    ai_id = uuid.uuid4()
                    await db.execute(
                        text("INSERT INTO appointment_items (id, tenant_id, appointment_id,"
                             " service_id, provider_id, sequence, start_time, duration_minutes,"
                             " price, price_is_locked, status, created_at, updated_at)"
                             " VALUES (:id, :tid, :appt_id, :svc_id, :prov_id, :seq, :st, :dur,"
                             " :price, true, 'completed', NOW(), NOW())"),
                        {"id": ai_id, "tid": tenant_id, "appt_id": appt_id,
                         "svc_id": svc["id"], "prov_id": provider_id,
                         "seq": appt_item_seq, "st": appt_dt,
                         "dur": svc["duration"], "price": amount},
                    )
                    receipt_item_to_appt_item[idx] = ai_id
                    appt_item_seq += 1
            created += 1

        # Create sale
        sale_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO sales (id, tenant_id, client_id, subtotal, discount_total,"
                 " gst_amount, pst_amount, total, status, completed_at, created_at, updated_at)"
                 " VALUES (:id, :tid, :cid, :sub, 0, :gst, :pst, :total,"
                 " 'completed', :cat, NOW(), NOW())"),
            {"id": sale_id, "tid": tenant_id, "cid": client_id,
             "sub": Decimal(str(round(subtotal, 2))),
             "gst": Decimal(str(round(gst_total, 2))),
             "pst": Decimal(str(round(pst_total, 2))),
             "total": Decimal(str(round(total, 2))),
             "cat": completed_at},
        )

        # Create sale items
        for idx, item in enumerate(items):
            desc = (item.get("Description") or "").strip()
            staff = (item.get("Staff") or "").strip().upper()
            amount = float(item.get("Amount") or 0)
            qty = int(item.get("Quantity") or 1)
            kind = "service" if _is_service(desc) else "retail"
            provider_id = provider_map.get(staff) if staff else None
            # Linked for both branches: new-appointment path populates the dict at
            # insert time; use_existing path populates it via best-effort matching
            # against existing appointment_items above (P-IMPORT-LINK).
            ai_id = receipt_item_to_appt_item.get(idx)
            # Milano exports Amount as the LINE TOTAL, not unit price (confirmed by GST pattern).
            line_total = Decimal(str(round(amount, 2)))
            unit_price = Decimal(str(round(amount / qty, 4))) if qty > 1 else line_total

            await db.execute(
                text("INSERT INTO sale_items (id, tenant_id, sale_id, appointment_item_id,"
                     " description, provider_id, kind, sequence, quantity,"
                     " unit_price, discount_amount, line_total, created_at, updated_at)"
                     " VALUES (:id, :tid, :sale_id, :ai_id,"
                     " :desc, :prov_id, :kind, :seq, :qty,"
                     " :unit_price, 0, :line_total, NOW(), NOW())"),
                {"id": uuid.uuid4(), "tid": tenant_id, "sale_id": sale_id,
                 "ai_id": ai_id, "desc": desc, "prov_id": provider_id,
                 "kind": kind, "seq": idx + 1, "qty": qty,
                 "unit_price": unit_price,
                 "line_total": line_total},
            )

        # Link sale → appointment
        await db.execute(
            text("INSERT INTO sale_appointments (id, tenant_id, sale_id, appointment_id,"
                 " created_at, updated_at)"
                 " VALUES (:id, :tid, :sale_id, :appt_id, NOW(), NOW())"),
            {"id": uuid.uuid4(), "tid": tenant_id,
             "sale_id": sale_id, "appt_id": appt_id},
        )

        # Single payment for the full receipt total
        await db.execute(
            text("INSERT INTO sale_payments (id, tenant_id, sale_id, payment_method_id,"
                 " amount, cashback_amount, created_at, updated_at)"
                 " VALUES (:id, :tid, :sale_id, :pm_id, :amount, 0, NOW(), NOW())"),
            {"id": uuid.uuid4(), "tid": tenant_id,
             "sale_id": sale_id, "pm_id": unknown_pm_id,
             "amount": Decimal(str(round(total, 2)))},
        )

        # Commit in batches of 200 to avoid huge transactions
        if (created + updated) % 200 == 0:
            await db.commit()

    await db.commit()
    return {
        "created": created,
        "updated": updated,
        "walk_in_created": walk_in_created,
        "skipped_existing": skipped_existing,
        "skipped_no_client": skipped_no_client,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Past bookings with no receipt  (confirmed, client never arrived)
# ---------------------------------------------------------------------------

async def import_past_unreceipted_bookings(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    content: bytes,
) -> dict:
    """
    Import past bookings that have no receipt transaction — confirmed appointments
    where the client never arrived (no-show or cancellation, unknown which).
    """
    rows = _read_csv(content)
    today = datetime.now()

    def _safe_past(r: dict) -> bool:
        try:
            return bool(r.get("Date")) and datetime.strptime(r["Date"].strip(), "%m/%d/%Y") < today
        except (ValueError, AttributeError):
            return False

    past_rows = [r for r in rows if _safe_past(r)]

    provider_map = await _load_providers(db, tenant_id)
    service_detail = await _load_service_detail(db, tenant_id)
    client_map = await _load_client_map(db, tenant_id)

    # Load existing appointment dates per client to detect already-imported
    # (receipts were imported first so these are already in the DB)
    existing_keys: set[tuple[uuid.UUID, str]] = set()
    appt_rows = (await db.execute(
        text("SELECT client_id, appointment_date::text FROM appointments WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )).fetchall()
    for r in appt_rows:
        # Store as (client_id, date string YYYY-MM-DD)
        existing_keys.add((r.client_id, str(r.appointment_date)[:10]))

    # Group by (client_code, date)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in past_rows:
        code = (row.get("Code") or "").strip()
        date_str = (row.get("Date") or "").strip()
        if code and date_str:
            groups[(code, date_str)].append(row)
    for key in groups:
        groups[key].sort(key=lambda r: r.get("TimeInt") or r.get("Time") or "")

    created = skipped_existing = skipped_no_client = skipped_no_service = 0

    for (client_code, date_str), items in groups.items():
        client_id = client_map.get(client_code)
        if not client_id:
            skipped_no_client += 1
            continue

        # Skip if a receipt already created an appointment on this date for this client
        date_ymd = datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y-%m-%d")
        if (client_id, date_ymd) in existing_keys:
            skipped_existing += 1
            continue

        try:
            appt_dt = _parse_dt(date_str, items[0]["Time"])
        except (ValueError, KeyError):
            skipped_no_client += 1
            continue

        resolved = []
        skip_group = False
        for seq, item in enumerate(items, start=1):
            legacy_svc = (item.get("Service") or "").strip()
            db_code = SERVICE_CODE_MAP.get(legacy_svc) or SERVICE_CODE_MAP.get(legacy_svc.upper())
            svc = service_detail.get(db_code.lower()) if db_code else None
            if not svc:
                skip_group = True
                break
            staff = (item.get("Staff") or "").strip().upper()
            provider_id = provider_map.get(staff)
            if not provider_id:
                skip_group = True
                break
            try:
                item_dt = _parse_dt(date_str, item["Time"])
            except (ValueError, KeyError):
                skip_group = True
                break
            resolved.append({"seq": seq, "service_id": svc["id"], "provider_id": provider_id,
                              "start_time": item_dt, "duration": svc["duration"], "price": svc["price"]})

        if skip_group or not resolved:
            skipped_no_service += 1
            continue

        appt_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO appointments (id, tenant_id, client_id, appointment_date,"
                 " source, status, confirmation_status, is_recurring, created_at, updated_at)"
                 " VALUES (:id, :tid, :cid, :dt,"
                 " 'staff_entered', 'confirmed', 'skipped', false, NOW(), NOW())"),
            {"id": appt_id, "tid": tenant_id, "cid": client_id, "dt": appt_dt},
        )
        for ri in resolved:
            await db.execute(
                text("INSERT INTO appointment_items (id, tenant_id, appointment_id,"
                     " service_id, provider_id, sequence, start_time, duration_minutes,"
                     " price, price_is_locked, status, created_at, updated_at)"
                     " VALUES (:id, :tid, :appt_id, :svc_id, :prov_id, :seq, :st, :dur, :price,"
                     " true, 'pending', NOW(), NOW())"),
                {"id": uuid.uuid4(), "tid": tenant_id, "appt_id": appt_id,
                 "svc_id": ri["service_id"], "prov_id": ri["provider_id"],
                 "seq": ri["seq"], "st": ri["start_time"],
                 "dur": ri["duration"], "price": ri["price"]},
            )
        created += 1
        existing_keys.add((client_id, date_ymd))

    await db.commit()
    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_no_client": skipped_no_client,
        "skipped_no_service": skipped_no_service,
    }


# ---------------------------------------------------------------------------
# On Account Summary import  (client account balances)
# ---------------------------------------------------------------------------

async def import_on_account_balances(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    content: bytes,
) -> dict:
    rows = _read_csv(content)
    updated = skipped = 0

    for row in rows:
        code = (row.get("ClientCode") or "").strip().lstrip("|")
        if not code:
            skipped += 1
            continue
        try:
            debit = Decimal((row.get("Debit") or "0").strip().replace(",", "") or "0")
            credit = Decimal((row.get("Credit") or "0").strip().replace(",", "") or "0")
        except Exception:
            skipped += 1
            continue
        # positive = client has credit (salon owes them), negative = client owes salon
        balance = credit - debit
        result = await db.execute(
            text(
                "UPDATE clients SET account_balance = :bal, updated_at = NOW()"
                " WHERE tenant_id = :tid AND legacy_id = :code"
            ),
            {"bal": float(balance), "tid": tenant_id, "code": code},
        )
        if result.rowcount:
            updated += 1
        else:
            skipped += 1

    await db.commit()
    return {"updated": updated, "skipped": skipped}
