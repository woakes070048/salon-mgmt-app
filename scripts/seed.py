"""
Seed Salon Lyol initial data.
Run from repo root: uv --project backend run python scripts/seed.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from datetime import date, time as dtime
from urllib.parse import quote_plus
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.tenant import Tenant
from app.models.department import Department
from app.models.provider import Provider, ProviderType, OnlineBookingVisibility
from app.models.service import ServiceCategory, Service, PricingType
from app.models.provider_service_price import ProviderServicePrice
from app.models.schedule import TenantOperatingHours, ProviderSchedule
from app.models.retail import RetailItem
from app.models.user import User, UserRole
from app.auth import hash_password
from app.models.promotion import TenantPromotion, PromotionKind
from app.models.i18n import ServiceCategoryTranslation, ServiceTranslation

# ── French translations ───────────────────────────────────────────────────────
_CAT_FR: dict[str, str] = {
    "Styling":    "Coiffure",
    "Colouring":  "Coloration",
    "Extensions": "Extensions",
}

_SVC_FR: dict[str, str] = {
    "BLD":    "Brushing",
    "ST1":    "Coupe de cheveux type 1",
    "ST2":    "Coupe de cheveux type 2",
    "ST2P":   "Coupe de cheveux type 2+",
    "FRG":    "Coupe de frange",
    "HTF":    "Finition aux outils chauffants",
    "UPD":    "Chignon spécial",
    "BOT":    "Botox capillaire (avec soins à domicile)",
    "BOTNHC": "Botox capillaire (sans soins à domicile)",
    "BOTEXP": "Botox capillaire express",
    "MLB":    "Traitement Milbon",
    "MLBA":   "Traitement Milbon (supplément)",
    "CCAMO":  "Couleur camouflage",
    "RTO":    "Retouche de racines",
    "RTOB":   "Retouche de racines (décoloration/éclaircissement)",
    "ACC":    "Mèches accent",
    "PHL":    "Mèches partielles",
    "FHL":    "Mèches complètes",
    "BLT":    "Retouche balayage",
    "BLY":    "Balayage complet",
    "CFC":    "Couleur complète",
    "CCR":    "Correction de couleur",
    "CVC":    "Couleur vive",
    "TNR":    "Tonique/Brillance",
    "TNRA":   "Tonique/Brillance (supplément)",
    "REF":    "Rafraîchissement des pointes",
    "MDO":    "Détox des métaux/Olaplex (supplément)",
    "EXF":    "Extensions – Fusion",
    "EXM":    "Extensions – Microperle",
    "EXT":    "Extensions – Adhésives",
    "EXW":    "Extensions – Trame",
}

# Mirror the connection logic from app/database.py so the seed works both
# locally (TCP to localhost) and on Cloud Run (Unix socket via Cloud SQL).
if settings.cloud_sql_instance:
    _socket_dir = f"/cloudsql/{settings.cloud_sql_instance}"
    _url = (
        f"postgresql+asyncpg://{settings.db_user}:{quote_plus(settings.db_password)}"
        f"@/{settings.db_name}"
    )
    _connect_args: dict = {"host": _socket_dir}
else:
    _url = settings.database_url
    _connect_args = {"ssl": False} if ("127.0.0.1" in _url or "localhost" in _url) else {}
engine = create_async_engine(_url, connect_args=_connect_args)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed():
    async with SessionLocal() as db:

        # ── Tenant ──────────────────────────────────────────────────────────
        existing = await db.execute(select(Tenant).where(Tenant.slug == "salon-lyol"))
        tenant = existing.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name="Salon Lyol", slug="salon-lyol", is_active=True)
            db.add(tenant)
            await db.flush()
            print(f"Created tenant: {tenant.id}")
        else:
            print(f"Tenant already exists: {tenant.id}")

        # Backfill / refresh contact details (idempotent)
        if tenant.address_line1 is None:
            tenant.address_line1 = "1452 Yonge Street"
        if tenant.city is None:
            tenant.city = "Toronto"
        if tenant.region is None:
            tenant.region = "ON"
        if tenant.country is None:
            tenant.country = "CA"
        if tenant.phone is None:
            tenant.phone = "416-922-0511"
        if tenant.hours_summary is None:
            tenant.hours_summary = "Tue–Sat · by appointment"

        tid = tenant.id

        # ── Departments ─────────────────────────────────────────────────────
        dept_data = [
            dict(code="STYLING", name="Styling", has_appointments=True, makes_appointments=True),
            dict(code="COLOUR", name="Colour", has_appointments=True, makes_appointments=True),
            dict(code="RECEPTION", name="Reception", can_be_cashier=True, makes_appointments=True, has_appointments=False),
        ]
        depts = {}
        for d in dept_data:
            existing = await db.execute(
                select(Department).where(Department.tenant_id == tid, Department.code == d["code"])
            )
            dept = existing.scalar_one_or_none()
            if dept is None:
                dept = Department(tenant_id=tid, **d)
                db.add(dept)
                await db.flush()
            depts[d["code"]] = dept
        print(f"Departments: {list(depts.keys())}")

        # ── Providers ────────────────────────────────────────────────────────
        provider_data = [
            dict(first_name="Jini", last_name="Jung", display_name="JJ", provider_code="JJ",
                 provider_type=ProviderType.dualist, is_owner=True, booking_order=1,
                 has_appointments=True, makes_appointments=True, can_be_cashier=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="STYLING"),
            dict(first_name="Antonella", last_name="Cumbo", display_name="Antonella", provider_code="ANTONELLA",
                 provider_type=ProviderType.dualist, booking_order=2,
                 has_appointments=True, makes_appointments=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="STYLING"),
            dict(first_name="Ryan", last_name="", display_name="Ryan", provider_code="RYAN",
                 provider_type=ProviderType.dualist, booking_order=9,
                 has_appointments=True, makes_appointments=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="STYLING"),
            dict(first_name="Gumi", last_name="", display_name="Gumi", provider_code="GUMI",
                 provider_type=ProviderType.dualist, booking_order=10,
                 has_appointments=True, makes_appointments=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="STYLING"),
            dict(first_name="Sarah", last_name="", display_name="Sarah", provider_code="SARAH",
                 provider_type=ProviderType.dualist, booking_order=3,
                 has_appointments=True, makes_appointments=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="COLOUR"),
            dict(first_name="Joanne", last_name="", display_name="Joanne", provider_code="JOANNE",
                 provider_type=ProviderType.colourist, booking_order=4,
                 has_appointments=True, makes_appointments=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="COLOUR"),
            dict(first_name="Becky", last_name="", display_name="Becky", provider_code="BECKY",
                 provider_type=ProviderType.stylist, booking_order=5,
                 has_appointments=True, makes_appointments=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="STYLING"),
            dict(first_name="Olga", last_name="", display_name="Olga", provider_code="OLGA",
                 provider_type=ProviderType.dualist, booking_order=6,
                 has_appointments=True, makes_appointments=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="STYLING"),
            dict(first_name="Mayumi", last_name="", display_name="Mayumi", provider_code="MAYUMI",
                 provider_type=ProviderType.dualist, booking_order=7,
                 has_appointments=True, makes_appointments=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="COLOUR"),
            dict(first_name="Asami", last_name="", display_name="Asami", provider_code="ASAMI",
                 provider_type=ProviderType.stylist, booking_order=8,
                 has_appointments=True, makes_appointments=True,
                 online_booking_visibility=OnlineBookingVisibility.available_to_all,
                 department_code="STYLING"),
        ]
        providers = {}
        for p in provider_data:
            dept_code = p.pop("department_code")
            existing = await db.execute(
                select(Provider).where(Provider.tenant_id == tid, Provider.provider_code == p["provider_code"])
            )
            provider = existing.scalar_one_or_none()
            if provider is None:
                provider = Provider(
                    tenant_id=tid,
                    department_id=depts[dept_code].id,
                    **p,
                )
                db.add(provider)
                await db.flush()
            else:
                provider.provider_type = p["provider_type"]
            providers[p["provider_code"]] = provider
        print(f"Providers: {list(providers.keys())}")

        # ── Service Categories ───────────────────────────────────────────────
        cat_data = [
            dict(name="Styling", display_order=1),
            dict(name="Colouring", display_order=2),
            dict(name="Extensions", display_order=3),
        ]
        cats = {}
        for c in cat_data:
            existing = await db.execute(
                select(ServiceCategory).where(ServiceCategory.tenant_id == tid, ServiceCategory.name == c["name"])
            )
            cat = existing.scalar_one_or_none()
            if cat is None:
                cat = ServiceCategory(tenant_id=tid, **c)
                db.add(cat)
                await db.flush()
            cats[c["name"]] = cat

        # ── Service category translations (en + fr) ──────────────────────────
        for en_name, cat in cats.items():
            for lang, tr_name in [("en", en_name), ("fr", _CAT_FR.get(en_name, en_name))]:
                existing_tr = await db.execute(
                    select(ServiceCategoryTranslation).where(
                        ServiceCategoryTranslation.category_id == cat.id,
                        ServiceCategoryTranslation.language == lang,
                    )
                )
                tr = existing_tr.scalar_one_or_none()
                if tr is None:
                    db.add(ServiceCategoryTranslation(
                        tenant_id=tid, category_id=cat.id, language=lang, name=tr_name,
                    ))
                else:
                    tr.name = tr_name
        await db.flush()

        # ── Services ─────────────────────────────────────────────────────────
        service_data = [
            # Styling
            dict(category="Styling", service_code="BLD", name="Blowdry", duration_minutes=60, default_price=60),
            dict(category="Styling", service_code="ST1", name="Type 1 Haircut", duration_minutes=45, default_price=65),
            dict(category="Styling", service_code="ST2", name="Type 2 Haircut", duration_minutes=60, default_price=100),
            dict(category="Styling", service_code="ST2P", name="Type 2+ Haircut", duration_minutes=75, default_price=130),
            dict(category="Styling", service_code="FRG", name="Fringe/Bang Cut", duration_minutes=15, default_price=20, ),
            dict(category="Styling", service_code="HTF", name="Heat Tool Finish", duration_minutes=15, default_price=10, ),
            dict(category="Styling", service_code="UPD", name="Special Updo", duration_minutes=90, default_price=145),
            dict(category="Styling", service_code="BOT", name="Hair Botox (with home care)", duration_minutes=180, default_price=400),
            dict(category="Styling", service_code="BOTNHC", name="Hair Botox (without home care)", duration_minutes=180, default_price=350),
            dict(category="Styling", service_code="BOTEXP", name="Hair Botox Express", duration_minutes=90, default_price=150),
            dict(category="Styling", service_code="MLB", name="Milbon Treatment", duration_minutes=60, default_price=100),
            dict(category="Styling", service_code="MLBA", name="Milbon Treatment (add-on)", duration_minutes=30, default_price=65, ),
            # Colouring
            dict(category="Colouring", service_code="CCAMO", name="Camo Colour", duration_minutes=50, default_price=50,
                 processing_offset_minutes=20, processing_duration_minutes=30),
            dict(category="Colouring", service_code="RTO", name="Root Touch-Up", duration_minutes=90, default_price=90,
                 processing_offset_minutes=15, processing_duration_minutes=35),
            dict(category="Colouring", service_code="RTOB", name="Root Touch-Up (bleach/high lift)", duration_minutes=105, default_price=100,
                 processing_offset_minutes=15, processing_duration_minutes=45),
            dict(category="Colouring", service_code="ACC", name="Accent Highlights", duration_minutes=90, default_price=110,
                 processing_offset_minutes=45, processing_duration_minutes=30),
            dict(category="Colouring", service_code="PHL", name="Partial Highlights", duration_minutes=120, default_price=140,
                 processing_offset_minutes=60, processing_duration_minutes=35),
            dict(category="Colouring", service_code="FHL", name="Full Highlights", duration_minutes=150, default_price=180,
                 processing_offset_minutes=80, processing_duration_minutes=35),
            dict(category="Colouring", service_code="BLT", name="Balayage Touch-Up", duration_minutes=150, default_price=200,
                 processing_offset_minutes=90, processing_duration_minutes=40),
            dict(category="Colouring", service_code="BLY", name="Full Balayage", duration_minutes=180, default_price=250,
                 processing_offset_minutes=100, processing_duration_minutes=45),
            dict(category="Colouring", service_code="CFC", name="Color Full Color", duration_minutes=90, default_price=140,
                 processing_offset_minutes=15, processing_duration_minutes=40),
            dict(category="Colouring", service_code="CCR", name="Colour Correction", duration_minutes=240, default_price=100,
                 pricing_type=PricingType.hourly),
            dict(category="Colouring", service_code="CVC", name="Vivid Color", duration_minutes=90, default_price=100,
                 processing_offset_minutes=15, processing_duration_minutes=40),
            dict(category="Colouring", service_code="TNR", name="Toner/Gloss", duration_minutes=45, default_price=85,
                 processing_offset_minutes=5, processing_duration_minutes=20),
            dict(category="Colouring", service_code="TNRA", name="Toner/Gloss (add-on)", duration_minutes=30, default_price=50,
                 processing_offset_minutes=5, processing_duration_minutes=20),
            dict(category="Colouring", service_code="REF", name="Refreshing Ends", duration_minutes=30, default_price=50),
            dict(category="Colouring", service_code="MDO", name="Metal Detox/Olaplex (add-on)", duration_minutes=15, default_price=35, ),
            # Extensions
            dict(category="Extensions", service_code="EXF", name="Extensions - Fusion", duration_minutes=270, default_price=400, requires_prior_consultation=True),
            dict(category="Extensions", service_code="EXM", name="Extensions - Microbead", duration_minutes=270, default_price=400, requires_prior_consultation=True),
            dict(category="Extensions", service_code="EXT", name="Extensions - Tape-In", duration_minutes=150, default_price=250, requires_prior_consultation=True),
            dict(category="Extensions", service_code="EXW", name="Extensions - Weft", duration_minutes=150, default_price=250, requires_prior_consultation=True),
        ]
        services = {}
        for s in service_data:
            cat_name = s.pop("category")
            existing = await db.execute(
                select(Service).where(Service.tenant_id == tid, Service.service_code == s["service_code"])
            )
            svc = existing.scalar_one_or_none()
            if svc is None:
                svc = Service(
                    tenant_id=tid,
                    category_id=cats[cat_name].id,
                    is_active=True,
                    **s,
                )
                db.add(svc)
                await db.flush()
            else:
                if svc.default_price != s.get("default_price"):
                    svc.default_price = s.get("default_price")
            services[s["service_code"]] = svc

        # ── Service translations (en + fr) ───────────────────────────────────
        for svc_code, svc in services.items():
            for lang, tr_name in [("en", svc.name), ("fr", _SVC_FR.get(svc_code, svc.name))]:
                existing_tr = await db.execute(
                    select(ServiceTranslation).where(
                        ServiceTranslation.service_id == svc.id,
                        ServiceTranslation.language == lang,
                    )
                )
                tr = existing_tr.scalar_one_or_none()
                if tr is None:
                    db.add(ServiceTranslation(
                        tenant_id=tid, service_id=svc.id, language=lang, name=tr_name,
                    ))
                else:
                    tr.name = tr_name
        await db.flush()
        print(f"Services: {len(services)} created/existing")

        # ── Operating Hours ──────────────────────────────────────────────────
        hours_data = [
            dict(day_of_week=0, is_open=False),                                     # Monday   — closed
            dict(day_of_week=1, is_open=True, open_time="09:00", close_time="18:00"),  # Tuesday  (last out 18:00)
            dict(day_of_week=2, is_open=True, open_time="09:00", close_time="20:00"),  # Wednesday (last out 20:00)
            dict(day_of_week=3, is_open=True, open_time="09:00", close_time="20:00"),  # Thursday  (last out 20:00)
            dict(day_of_week=4, is_open=True, open_time="09:00", close_time="18:00"),  # Friday   (last out 18:00)
            dict(day_of_week=5, is_open=True, open_time="09:00", close_time="17:00"),  # Saturday
            dict(day_of_week=6, is_open=False),                                     # Sunday   — closed
        ]
        for h in hours_data:
            existing = await db.execute(
                select(TenantOperatingHours).where(
                    TenantOperatingHours.tenant_id == tid,
                    TenantOperatingHours.day_of_week == h["day_of_week"]
                )
            )
            ot = h.get("open_time")
            ct = h.get("close_time")
            rec = existing.scalar_one_or_none()
            if rec is None:
                rec = TenantOperatingHours(tenant_id=tid, day_of_week=h["day_of_week"])
                db.add(rec)
            rec.is_open = h["is_open"]
            rec.open_time = dtime.fromisoformat(ot) if ot else None
            rec.close_time = dtime.fromisoformat(ct) if ct else None
        print("Operating hours seeded")

        # ── Provider Weekly Schedules ────────────────────────────────────────
        # day_of_week: 0=Mon 1=Tue 2=Wed 3=Thu 4=Fri 5=Sat 6=Sun (ISO)
        # Values: list of (start, end) tuples per block, or [] for day off.
        # Source: docs/seed-data/provider-schedules.md
        EPOCH = date(2000, 1, 1)
        T = dtime  # shorthand

        OFF = []
        PROVIDER_SCHEDULES: dict[str, dict[int, list]] = {
            #            Mon   Tue                           Wed                          Thu                          Fri                          Sat                        Sun
            "ASAMI":   {0: OFF, 1: [(T(9,0),  T(18,0))],  2: [(T(11,0),T(20,0))],    3: [(T(9,0),  T(18,0))],    4: OFF,                      5: [(T(9,0), T(17,0))],   6: OFF},
            "GUMI":    {0: OFF, 1: [(T(9,0),  T(18,0))],  2: [(T(11,0),T(20,0))],    3: [(T(9,0),  T(18,0))],    4: [(T(9,0),  T(18,0))],    5: [(T(9,0), T(17,0))],   6: OFF},
            "JJ":      {0: OFF, 1: [(T(9,0),  T(18,0))],  2: [(T(9,0), T(20,0))],    3: [(T(9,0),  T(20,0))],    4: [(T(9,0),  T(18,0))],    5: [(T(9,0), T(17,0))],   6: OFF},
            "JOANNE":  {0: OFF, 1: [(T(9,0),  T(17,0))],  2: [(T(9,0), T(16,0))],    3: [(T(11,0), T(19,0))],    4: [(T(9,0),  T(17,0))],    5: [(T(9,0), T(17,0))],   6: OFF},
            "MAYUMI":  {0: OFF, 1: [(T(10,0), T(18,0))],  2: OFF,                     3: [(T(10,0), T(20,0))],    4: [(T(10,0), T(18,0))],    5: [(T(9,0), T(17,0))],   6: OFF},
            "OLGA":    {0: OFF, 1: [(T(9,0),  T(17,0))],  2: [(T(11,0),T(20,0))],    3: OFF,                      4: [(T(10,0), T(18,0))],    5: [(T(9,0), T(17,0))],   6: OFF},
            "RYAN":    {0: OFF, 1: [(T(9,0),  T(18,0))],  2: [(T(11,0),T(20,0))],    3: OFF,                      4: [(T(9,0),  T(18,0))],    5: [(T(9,0), T(17,0))],   6: OFF},
            "SARAH":   {0: OFF, 1: [(T(9,0),  T(16,30))], 2: [(T(9,0), T(16,30))],   3: [(T(11,0), T(19,0))],    4: OFF,                      5: [(T(9,0), T(17,0))],   6: OFF},
            # Maternity leave — all days off
            "ANTONELLA": {dow: OFF for dow in range(7)},
            "BECKY":     {dow: OFF for dow in range(7)},
        }

        for provider_code, schedule in PROVIDER_SCHEDULES.items():
            provider = providers.get(provider_code)
            if provider is None:
                continue
            # Delete and recreate so re-runs apply updated schedules
            await db.execute(
                delete(ProviderSchedule).where(
                    ProviderSchedule.tenant_id == tid,
                    ProviderSchedule.provider_id == provider.id,
                )
            )
            for dow, blocks in schedule.items():
                if not blocks:
                    db.add(ProviderSchedule(
                        tenant_id=tid, provider_id=provider.id,
                        day_of_week=dow, block=1, is_working=False,
                        start_time=None, end_time=None,
                        effective_from=EPOCH, effective_to=None,
                    ))
                else:
                    for block_num, (start, end) in enumerate(blocks, 1):
                        db.add(ProviderSchedule(
                            tenant_id=tid, provider_id=provider.id,
                            day_of_week=dow, block=block_num, is_working=True,
                            start_time=start, end_time=end,
                            effective_from=EPOCH, effective_to=None,
                        ))
        print("Provider weekly schedules seeded")

        # ── Provider Service Prices ──────────────────────────────────────────
        # Source: docs/seed-data/Service Price List.xls (system of record, 2026-04-28).
        # Google Sheet used as supplement for colour services where XLS has no
        # per-provider row (meaning all charge the service default price).
        #
        # Omissions / unknowns:
        #   CCAMO  Camo Colour       — no per-provider entries in XLS
        #   BOTNHC / BOTEXP          — new services added from XLS; no per-provider rows
        #   "Additional colour $25"  — XLS code CAC, no equivalent service in catalog
        #   Becky, Antonella         — on maternity leave, not in XLS
        #
        # Skipped (no standard price):
        #   JJ:   colour services    — not listed in XLS (by request)
        #   JJ:   BOT                — "by request" per Google Sheet, not in XLS per-provider
        #   RYAN: UPD                — $0 in XLS (deleted below if previously seeded)
        PSP_DATA: list[tuple[str, str, float]] = [
            # ── JJ (styling only) ─────────────────────────────────────────
            ("JJ", "BLD",  70),
            ("JJ", "ST1",  80),
            ("JJ", "ST2",  125),
            ("JJ", "ST2P", 150),
            ("JJ", "UPD",  200),   # XLS: SUD/JJ = 200 (Google Sheet said "by request")
            ("JJ", "HTF",  10),
            ("JJ", "FRG",  20),
            ("JJ", "MLB",  100),
            ("JJ", "MLBA", 65),

            # ── Gumi (dualist) ─────────────────────────────────────────────
            ("GUMI", "BLD",  60),
            ("GUMI", "ST1",  65),
            ("GUMI", "ST2",  100),
            ("GUMI", "ST2P", 125),
            ("GUMI", "UPD",  150),
            ("GUMI", "HTF",  10),
            ("GUMI", "FRG",  20),
            ("GUMI", "MLB",  100),
            ("GUMI", "MLBA", 65),
            ("GUMI", "BOT",  400),
            ("GUMI", "RTO",  90),
            ("GUMI", "RTOB", 100),
            ("GUMI", "ACC",  100),
            ("GUMI", "PHL",  130),
            ("GUMI", "FHL",  170),
            ("GUMI", "BLT",  190),
            ("GUMI", "BLY",  240),
            ("GUMI", "CCR",  100),
            ("GUMI", "TNR",  85),
            ("GUMI", "REF",  50),
            ("GUMI", "TNRA", 50),
            ("GUMI", "MDO",  35),

            # ── Asami (stylist) ────────────────────────────────────────────
            ("ASAMI", "BLD",  55),
            ("ASAMI", "ST1",  60),
            ("ASAMI", "ST2",  90),
            ("ASAMI", "ST2P", 115),
            ("ASAMI", "UPD",  140),  # XLS: SUD/ASAMI = 140 (Google Sheet said "n/a")
            ("ASAMI", "HTF",  10),
            ("ASAMI", "FRG",  20),
            ("ASAMI", "MLB",  100),
            ("ASAMI", "MLBA", 65),
            ("ASAMI", "BOT",  400),

            # ── Mayumi (dualist) ───────────────────────────────────────────
            ("MAYUMI", "BLD",  55),
            ("MAYUMI", "ST1",  55),
            ("MAYUMI", "ST2",  90),
            ("MAYUMI", "ST2P", 115),
            ("MAYUMI", "UPD",  140),
            ("MAYUMI", "HTF",  10),
            ("MAYUMI", "FRG",  20),
            ("MAYUMI", "MLB",  100),
            ("MAYUMI", "MLBA", 65),
            ("MAYUMI", "BOT",  400),
            ("MAYUMI", "RTO",  90),
            ("MAYUMI", "RTOB", 100),
            ("MAYUMI", "ACC",  100),
            ("MAYUMI", "PHL",  130),
            ("MAYUMI", "FHL",  170),
            ("MAYUMI", "BLT",  190),
            ("MAYUMI", "BLY",  240),
            ("MAYUMI", "CCR",  100),
            ("MAYUMI", "TNR",  85),
            ("MAYUMI", "REF",  50),
            ("MAYUMI", "TNRA", 50),
            ("MAYUMI", "MDO",  35),

            # ── Olga (dualist) ─────────────────────────────────────────────
            ("OLGA", "BLD",  55),
            ("OLGA", "ST1",  55),
            ("OLGA", "ST2",  90),
            ("OLGA", "ST2P", 115),
            ("OLGA", "UPD",  140),
            ("OLGA", "HTF",  10),
            ("OLGA", "FRG",  20),
            ("OLGA", "MLB",  100),
            ("OLGA", "MLBA", 65),
            ("OLGA", "BOT",  400),
            ("OLGA", "RTO",  90),
            ("OLGA", "RTOB", 100),
            ("OLGA", "ACC",  100),
            ("OLGA", "PHL",  130),
            ("OLGA", "FHL",  170),
            ("OLGA", "BLT",  190),
            ("OLGA", "BLY",  240),
            ("OLGA", "CCR",  100),
            ("OLGA", "TNR",  85),
            ("OLGA", "REF",  50),
            ("OLGA", "TNRA", 50),
            ("OLGA", "MDO",  35),

            # ── Ryan (dualist — no Updo, see deletion below) ───────────────
            ("RYAN", "BLD",  60),
            ("RYAN", "ST1",  65),
            ("RYAN", "ST2",  100),
            ("RYAN", "ST2P", 125),
            ("RYAN", "HTF",  10),
            ("RYAN", "FRG",  20),
            ("RYAN", "MLB",  100),
            ("RYAN", "MLBA", 65),
            ("RYAN", "BOT",  400),
            ("RYAN", "RTO",  90),
            ("RYAN", "RTOB", 100),
            ("RYAN", "ACC",  100),
            ("RYAN", "PHL",  130),
            ("RYAN", "FHL",  170),
            ("RYAN", "BLT",  190),
            ("RYAN", "BLY",  240),
            ("RYAN", "CCR",  100),
            ("RYAN", "TNR",  85),
            ("RYAN", "REF",  50),
            ("RYAN", "TNRA", 50),
            ("RYAN", "MDO",  35),

            # ── Joanne (colourist) ─────────────────────────────────────────
            ("JOANNE", "BLD",  50),    # XLS: SBD/JOANNE = 50 (not in Google Sheet)
            ("JOANNE", "RTO",  90),
            ("JOANNE", "RTOB", 100),
            ("JOANNE", "ACC",  120),   # XLS: CAHL/JOANNE = 120
            ("JOANNE", "PHL",  150),   # XLS: CPHHL/JOANNE = 150
            ("JOANNE", "FHL",  190),   # XLS: CFHHL/JOANNE = 190
            ("JOANNE", "BLT",  210),   # XLS: CBT/JOANNE = 210
            ("JOANNE", "BLY",  260),   # XLS: CB/JOANNE = 260
            ("JOANNE", "CCR",  120),   # XLS: CCO default + Google Sheet Joanne=120/hr
            ("JOANNE", "TNR",  85),
            ("JOANNE", "MLB",  100),
            ("JOANNE", "BOT",  400),
            ("JOANNE", "REF",  50),
            ("JOANNE", "TNRA", 50),
            ("JOANNE", "MLBA", 65),
            ("JOANNE", "MDO",  35),

            # ── Sarah (dualist, mainly colour) ─────────────────────────────
            ("SARAH", "BLD",  50),     # XLS: SBD/SARAH = 50 (not in Google Sheet)
            ("SARAH", "ST2",  90),     # XLS: ST2H/SARAH = 90 (not in Google Sheet)
            ("SARAH", "ST2P", 115),    # XLS: ST2H+/SARAH = 115 (not in Google Sheet)
            ("SARAH", "RTO",  90),     # XLS: CRTU/SARAH = 90
            ("SARAH", "RTOB", 100),
            ("SARAH", "ACC",  100),
            ("SARAH", "PHL",  130),
            ("SARAH", "FHL",  170),
            ("SARAH", "BLT",  190),    # XLS: CBT/SARAH = 190
            ("SARAH", "BLY",  240),    # XLS: CB/SARAH = 240
            ("SARAH", "CVC",  100),    # XLS: CVC/SARAH = 100 (new service)
            ("SARAH", "CCR",  100),
            ("SARAH", "TNR",  85),
            ("SARAH", "MLB",  100),
            ("SARAH", "BOT",  400),
            ("SARAH", "REF",  50),
            ("SARAH", "TNRA", 50),
            ("SARAH", "MLBA", 65),
            ("SARAH", "MDO",  35),
        ]

        # Delete PSPs that should not exist per the XLS system of record.
        # Ryan's Updo was previously seeded from Google Sheet ($150) but XLS has $0.
        ryan = providers.get("RYAN")
        upd_svc = services.get("UPD")
        if ryan and upd_svc:
            await db.execute(
                delete(ProviderServicePrice).where(
                    ProviderServicePrice.tenant_id == tid,
                    ProviderServicePrice.provider_id == ryan.id,
                    ProviderServicePrice.service_id == upd_svc.id,
                )
            )

        psp_count = 0
        for provider_code, svc_code, price in PSP_DATA:
            prov = providers.get(provider_code)
            svc  = services.get(svc_code)
            if prov is None or svc is None:
                print(f"  WARN: skipping PSP ({provider_code}, {svc_code}) — not found")
                continue
            existing_psp = (
                await db.execute(
                    select(ProviderServicePrice).where(
                        ProviderServicePrice.tenant_id == tid,
                        ProviderServicePrice.provider_id == prov.id,
                        ProviderServicePrice.service_id == svc.id,
                    )
                )
            ).scalar_one_or_none()
            if existing_psp is None:
                db.add(ProviderServicePrice(
                    tenant_id=tid,
                    provider_id=prov.id,
                    service_id=svc.id,
                    price=price,
                    effective_from=date(2000, 1, 1),
                    is_active=True,
                ))
                psp_count += 1
            elif float(existing_psp.price) != price:
                existing_psp.price = price
                psp_count += 1
        print(f"Provider service prices: {psp_count} created/updated")

        # ── Retail Products ──────────────────────────────────────────────────
        # Source: docs/seed-data/Retail Product Listing.xls
        # Upsert on SKU; updates price/cost/active if changed.
        # brand stored in description for staff reference (no brand column in model).
        RETAIL_DATA = [
            dict(sku='AGTOUSLTEX142', name='AG Tousled Texture 142g', brand='AG', default_price=32.0, default_cost=15.6, is_active=True),
            dict(sku='FIG7', name='flat iron G7', brand=None, default_price=150.0, default_cost=None, is_active=True),
            dict(sku='GHD DRYER', name='ghd helios dryer', brand=None, default_price=350.0, default_cost=None, is_active=True),
            dict(sku='KMML150ML', name='KM Motion lotion 150ml', brand='KM', default_price=39.0, default_cost=23.0, is_active=True),
            dict(sku='LPMDADP500ML', name='MD Anti-deposit protector 500ml', brand='LOREAL', default_price=55.0, default_cost=26.20, is_active=False),
            dict(sku='LPMDI50ML', name='metal detox oil 50ml', brand='LOREAL', default_price=50.0, default_cost=26.01, is_active=True),
            dict(sku='LPMDLAMM100ML', name='MD leave-in Anti-Metal Moisture 100ml', brand='LOREAL', default_price=48.0, default_cost=27.0, is_active=True),
            dict(sku='LPMDM75ML', name='metal detox mask 75ml', brand='LOREAL', default_price=14.8, default_cost=7.2, is_active=False),
            dict(sku='LPMDMASK250ML', name='metal detox mask 250ml', brand='LOREAL', default_price=59.0, default_cost=27.15, is_active=True),
            dict(sku='LPMDS500ML', name='metal detox shampoo 500ml', brand='LOREAL', default_price=57.0, default_cost=34.2, is_active=False),
            dict(sku='LPMDSH300ML', name='metal detox shampoo 300ml', brand='LOREAL', default_price=43.0, default_cost=23.7, is_active=True),
            dict(sku='LPSADENSER9O', name='SA Denser hair 90ml', brand='LOREAL', default_price=74.0, default_cost=37.26, is_active=True),
            dict(sku='LPSADP500ML', name='SA dermo-purifier shampoo 500ml', brand='LOREAL', default_price=57.0, default_cost=33.0, is_active=True),
            dict(sku='LPSADRSES500ML', name='SA dermo regulator shampoo 500ml', brand='LOREAL', default_price=57.0, default_cost=33.0, is_active=True),
            dict(sku='LPSADS500ML', name='SA densifying shampoo 500ml', brand='LOREAL', default_price=57.0, default_cost=33.0, is_active=True),
            dict(sku='LPSAIS200ML', name='SA intense Soother 200ml', brand='LOREAL', default_price=45.0, default_cost=23.4, is_active=True),
            dict(sku='LPTA6F250ML', name='TA 6-Fix pure 250ml', brand='LOREAL', default_price=37.0, default_cost=18.49, is_active=True),
            dict(sku='LPTAAI1190ML', name='LP TA All in 1 Performer 190ml', brand='LOREAL', default_price=38.0, default_cost=22.8, is_active=True),
            dict(sku='LPTABT150ML', name='TA Bouncy and Tender 150ml', brand='LOREAL', default_price=37.0, default_cost=19.66, is_active=True),
            dict(sku='LPTABW150ML', name='TA beach waves 150ml', brand='LOREAL', default_price=37.0, default_cost=19.11, is_active=True),
            dict(sku='LPTAC150ML', name='TA Constructor 150ml', brand='LOREAL', default_price=37.0, default_cost=16.2, is_active=True),
            dict(sku='LPTAD100ML', name='LP depolish 100ml', brand='LOREAL', default_price=37.0, default_cost=16.17, is_active=True),
            dict(sku='LPTADM100ML', name='TA Density Material 100ml', brand='LOREAL', default_price=37.0, default_cost=16.32, is_active=True),
            dict(sku='LPTAEL6289G', name='LP TA Extreme Lacquer 289g', brand='LOREAL', default_price=37.0, default_cost=22.2, is_active=True),
            dict(sku='LPTAES150ML', name='TA extreme splash 150ml', brand='LOREAL', default_price=37.0, default_cost=16.25, is_active=True),
            dict(sku='LPTAFB150ML', name='LP TA Flex Blowdry 150ml', brand='LOREAL', default_price=38.0, default_cost=22.8, is_active=True),
            dict(sku='LPTAFCB200ML', name='LP TA Flex curl bounce 200ml', brand='LOREAL', default_price=38.0, default_cost=22.8, is_active=True),
            dict(sku='LPTAFD200ML', name='TA Fix Design 200ml', brand='LOREAL', default_price=37.0, default_cost=17.26, is_active=True),
            dict(sku='LPTAFI3289GAFP', name='TA Fix Infinium 3 289g', brand='LOREAL', default_price=38.0, default_cost=18.46, is_active=True),
            dict(sku='LPTAFI4289G', name='TA Fix Infinium 4 289g', brand='LOREAL', default_price=38.0, default_cost=18.56, is_active=True),
            dict(sku='LPTAFIP75ML', name='TA Fix Polish 75ml', brand='LOREAL', default_price=37.0, default_cost=16.0, is_active=True),
            dict(sku='LPTAFM200ML', name='TA fix max 200ml', brand='LOREAL', default_price=37.0, default_cost=16.5, is_active=True),
            dict(sku='LPTAFP75ML', name='LP TA Fix Paste 75ml', brand='LOREAL', default_price=37.0, default_cost=22.2, is_active=True),
            dict(sku='LPTAFVE250ML', name='TA full volume extra 250ml', brand='LOREAL', default_price=38.0, default_cost=15.5, is_active=True),
            dict(sku='LPTALC150ML', name='TA Liss Control 150ml', brand='LOREAL', default_price=37.0, default_cost=15.0, is_active=True),
            dict(sku='LPTALCP150ML', name='TA Liss Control Plus 150ml', brand='LOREAL', default_price=37.0, default_cost=19.80, is_active=True),
            dict(sku='LPTAMDUST200M', name='TA morning Dust 200ml', brand='LOREAL', default_price=37.0, default_cost=18.78, is_active=True),
            dict(sku='LPTAP190ML', name='TA Pli 190ml', brand='LOREAL', default_price=38.0, default_cost=17.36, is_active=True),
            dict(sku='LPTARING150ML', name='TA ringlight 150ml', brand='LOREAL', default_price=37.0, default_cost=17.34, is_active=True),
            dict(sku='LPTASD7', name='TA SuperDust 7g', brand='LOREAL', default_price=37.0, default_cost=18.67, is_active=True),
            dict(sku='LPTASQ200ML', name='TA spiral queen 200ml', brand='LOREAL', default_price=37.0, default_cost=17.78, is_active=True),
            dict(sku='LPTASW150ML', name='TA siren waves 150ml', brand='LOREAL', default_price=37.0, default_cost=19.04, is_active=True),
            dict(sku='LPTATFTGEL150', name='TA TransFormer gel 150ml', brand='LOREAL', default_price=37.0, default_cost=20.10, is_active=True),
            dict(sku='LPTATFTL150ML', name='TA TransFormer liqui 150ml', brand='LOREAL', default_price=37.0, default_cost=19.63, is_active=True),
            dict(sku='LPTAWEB150ML', name='TA web 150ml', brand='LOREAL', default_price=37.0, default_cost=19.8, is_active=True),
            dict(sku='MADSH200ML', name='Milbon Anti-frizz shampoo 200ml', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MADT200G', name='Milbon Anti-frizz treatment 200g', brand='MILBON', default_price=59.0, default_cost=28.0, is_active=True),
            dict(sku='MAHBO120ML', name='Milbon Anti-Frizz Oil 120ml', brand='MILBON', default_price=59.0, default_cost=28.0, is_active=True),
            dict(sku='MBPNVSH200ML', name='Milbon Blonde + Nourish Violet shampoo 200ml', brand='MILBON', default_price=46.0, default_cost=22.0, is_active=True),
            dict(sku='MBPNVT200G', name='Milbon Blonde + Nourish Violet treatment 200g', brand='MILBON', default_price=64.0, default_cost=31.0, is_active=True),
            dict(sku='MCSBPO50ML', name='Milbon CS Brilliant polishing oil 50ml', brand='MILBON', default_price=52.0, default_cost=26.0, is_active=True),
            dict(sku='MCSDTS4300ML', name='Milbon Dry Texturizing Spray 300g', brand='MILBON', default_price=52.0, default_cost=24.0, is_active=True),
            dict(sku='MCSESHH10300ML', name='Milbon Extra Strong Hairspray 300ml', brand='MILBON', default_price=52.0, default_cost=24.0, is_active=True),
            dict(sku='MCSMTP60G', name='Milbon Matte Paste 60g', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MCSMW3100G', name='Milbon Molding Wax 3 100g', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MCSMW5100G', name='Milbon CS molding wax 5 100g', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MCSMW7100G', name='Milbon CS molding wax 7 100g', brand='MILBON', default_price=42.0, default_cost=None, is_active=True),
            dict(sku='MCSRDS160G', name='Milbon Dry Shampoo 160g', brand='MILBON', default_price=54.0, default_cost=26.0, is_active=True),
            dict(sku='MCSSHH7300ML', name='Milbon Strong Hold Hair Spray 300ml', brand='MILBON', default_price=52.0, default_cost=24.0, is_active=True),
            dict(sku='MCSSTC360G', name='Milbon Satin Texturizing Cream 60g', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MCSTM4190ML', name='Milbon Thickening Mist 190ml', brand='MILBON', default_price=47.0, default_cost=22.5, is_active=True),
            dict(sku='MCSTSM3190ML', name='Milbon Texturizing Sea Mist 190ml', brand='MILBON', default_price=47.0, default_cost=22.5, is_active=True),
            dict(sku='MCSWDC1120G', name='Milbon Wave Defining Cream 120g', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MCSWEM4200G', name='Milbon Wave Enhancing Mousse 200g', brand='MILBON', default_price=50.0, default_cost=24.0, is_active=True),
            dict(sku='MCSWSGC5150G', name='Milbon Wet Shine Gel Cream 5 150g', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MCSWSGC8150G', name='Milbon Wet Shine Gel Cream 8 150g', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MFBF200G', name='Milbon Froth Blowout Foam 200g', brand='MILBON', default_price=60.0, default_cost=30.0, is_active=True),
            dict(sku='MGBH', name='Milbon Gift Bag Heat', brand='MILBON', default_price=84.8, default_cost=None, is_active=True),
            dict(sku='MGBR', name='Milbon Gift Bag Regular', brand='MILBON', default_price=76.8, default_cost=None, is_active=True),
            dict(sku='MGBRE', name='Milbon Gift Bag ReAwaken', brand='MILBON', default_price=91.2, default_cost=None, is_active=True),
            dict(sku='MISCRETAIL', name='misc retail', brand=None, default_price=0.0, default_cost=None, is_active=True),
            dict(sku='MKAO50ML', name='MK Argan Oil 50ml', brand='MK', default_price=49.9, default_cost=24.95, is_active=True),
            dict(sku='MKFBD150ML', name='MK Fast Blow-Dry 150ml', brand='MK', default_price=65.9, default_cost=29.95, is_active=True),
            dict(sku='MKFE50ML', name='MK Frizz Ease 50ml', brand='MK', default_price=47.9, default_cost=23.95, is_active=True),
            dict(sku='MKHM75ML', name='MK Hydro Mist 75ml', brand='MK', default_price=27.9, default_cost=None, is_active=True),
            dict(sku='MKLI300ML', name='MK Leave-in 300ml', brand='MK', default_price=43.9, default_cost=21.95, is_active=True),
            dict(sku='MKRC300ML', name='MK replenishing conditioner 300ml', brand='MK', default_price=37.9, default_cost=18.95, is_active=True),
            dict(sku='MKRS300ML', name='MK replenishing shampoo 300ml', brand='MK', default_price=37.9, default_cost=18.95, is_active=True),
            dict(sku='MKSC300ML', name='MK silver conditioner 300ml', brand='MK', default_price=37.9, default_cost=17.95, is_active=True),
            dict(sku='MKSS300ML', name='MK Silver Shampoo 300ml', brand='MK', default_price=37.9, default_cost=17.95, is_active=True),
            dict(sku='MKTM200ML', name='MK treatment mask 200ml', brand='MK', default_price=47.9, default_cost=21.95, is_active=True),
            dict(sku='MMRSH200ML', name='Milbon Moisture Replenishing Shampoo 200ml', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MMRT255G', name='Milbon Moisture Replenishing Treatment 200g', brand='MILBON', default_price=58.0, default_cost=28.0, is_active=True),
            dict(sku='MMWRM120ML', name='Milbon Weightless replenishing mist 120ml', brand='MILBON', default_price=59.0, default_cost=28.0, is_active=True),
            dict(sku='MPFP100G', name='Milbon Puff Finishing Paste 100g', brand='MILBON', default_price=56.0, default_cost=28.0, is_active=True),
            dict(sku='MRHHPM120ML', name='Milbon Repair heat protective mist 120ml', brand='MILBON', default_price=62.0, default_cost=30.0, is_active=True),
            dict(sku='MRHHPS200ML', name='Milbon Repair heat protective shampoo 200ml', brand='MILBON', default_price=46.0, default_cost=22.0, is_active=True),
            dict(sku='MRHHPT200G', name='Milbon Repair heat protective treatment 200g', brand='MILBON', default_price=64.0, default_cost=31.0, is_active=True),
            dict(sku='MRRBPC120G', name='Milbon Repair Primer Coarse 120g', brand='MILBON', default_price=59.0, default_cost=28.0, is_active=True),
            dict(sku='MRRBPF120G', name='Milbon Repair Primer Fine 120g', brand='MILBON', default_price=59.0, default_cost=28.0, is_active=True),
            dict(sku='MRRP120ML', name='Milbon Reawaken Renewing Primer 120ml', brand='MILBON', default_price=62.0, default_cost=30.0, is_active=True),
            dict(sku='MRRS200ML', name='Milbon Repair Restorative shampoo 200ml', brand='MILBON', default_price=44.0, default_cost=20.0, is_active=True),
            dict(sku='MRRSH200ML', name='Milbon Reawaken Renewing Shampoo 200ml', brand='MILBON', default_price=50.0, default_cost=24.0, is_active=True),
            dict(sku='MRRT200G', name='Milbon Repair Restorative treatment 200g', brand='MILBON', default_price=60.0, default_cost=28.0, is_active=True),
            dict(sku='MRRT_200G', name='Milbon Reawaken Renewing Treatment 200ml', brand='MILBON', default_price=68.0, default_cost=33.0, is_active=True),
            dict(sku='MRSROS150G', name='Milbon Shine Renewing Oil Shampoo 150g', brand='MILBON', default_price=62.0, default_cost=30.0, is_active=True),
            dict(sku='MSLBOF120ML', name='Milbon Smooth Oil fine 120ml', brand='MILBON', default_price=59.0, default_cost=28.0, is_active=True),
            dict(sku='MSLSOC120ML', name='Milbon Smooth Oil Coarse 120ml', brand='MILBON', default_price=59.0, default_cost=28.0, is_active=True),
            dict(sku='MSSSC200ML', name='Milbon Smooth Shampoo Coarse 200ml', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MSSSF200ML', name='Milbon Smooth Shampoo Fine 200ml', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MSSSM200', name='Milbon Smooth Shampoo Medium 200ml', brand='MILBON', default_price=42.0, default_cost=20.0, is_active=True),
            dict(sku='MSSTC200G', name='Milbon Smooth treatment Coarse 200g', brand='MILBON', default_price=58.0, default_cost=28.0, is_active=True),
            dict(sku='MSSTF200G', name='Milbon Smooth treatment Fine 200g', brand='MILBON', default_price=58.0, default_cost=28.0, is_active=True),
            dict(sku='MSSTM200G', name='Milbon Smooth treatment Medium 200g', brand='MILBON', default_price=58.0, default_cost=28.0, is_active=True),
            dict(sku='MVTC100G', name='Milbon Velvet Texture Cream 100g', brand='MILBON', default_price=56.0, default_cost=28.0, is_active=True),
            dict(sku='O3100ML', name='Olaplex 3 repair & strengthen 100ml', brand='OLAPLEX', default_price=40.5, default_cost=18.9, is_active=True),
            dict(sku='O4CSH250LM', name='Olaplex 4 clarifying shampoo 250ml', brand='OLAPLEX', default_price=40.5, default_cost=20.25, is_active=True),
            dict(sku='O4DSH178G', name='Olaplex dry shampoo 4 178g', brand='OLAPLEX', default_price=40.5, default_cost=20.25, is_active=True),
            dict(sku='O4PSH250', name='Olaplex shampoo 4 purple 250ml', brand='OLAPLEX', default_price=40.5, default_cost=20.25, is_active=True),
            dict(sku='O4SH250ML', name='Olaplex 4 shampoo 250ml', brand='OLAPLEX', default_price=40.5, default_cost=18.9, is_active=True),
            dict(sku='O5CON250ML', name='Olaplex 5 conditioner 250ml', brand='OLAPLEX', default_price=40.5, default_cost=18.9, is_active=True),
            dict(sku='O5COND2L', name='Olaplex 5 conditioner 2L', brand='OLAPLEX', default_price=0.0, default_cost=81.0, is_active=True),
            dict(sku='O6100ML', name='Olaplex 6 bond smoother 100ml', brand='OLAPLEX', default_price=40.5, default_cost=18.9, is_active=True),
            dict(sku='O7BO30ML', name='Olaplex 7 bonding oil 30ml', brand='OLAPLEX', default_price=40.5, default_cost=18.9, is_active=True),
            dict(sku='O8100ML', name='Olaplex 8 bond intense moisture mask 100ml', brand='OLAPLEX', default_price=40.5, default_cost=18.9, is_active=True),
            dict(sku='O990ML', name='Olaplex 9 bond protector 90ml', brand='OLAPLEX', default_price=40.5, default_cost=18.9, is_active=True),
            dict(sku='OG15', name='Olivia Garden barrel brush 15mm', brand='MISC', default_price=27.0, default_cost=13.5, is_active=True),
            dict(sku='OG20', name='Olivia Garden ceramic+Ion 20mm', brand='MISC', default_price=27.0, default_cost=13.5, is_active=True),
            dict(sku='OG25', name='Olivia Garden barrel brush 25mm', brand='MISC', default_price=27.98, default_cost=13.99, is_active=True),
            dict(sku='OGFB', name='Olivia Garden flat brush', brand='MISC', default_price=20.0, default_cost=11.0, is_active=True),
            dict(sku='OGSPEEDLX 35M', name='Olivia Garden brush speed 35mm', brand='MISC', default_price=33.18, default_cost=14.1, is_active=True),
            dict(sku='OGSPEEDXL45MM', name='Olivia Garden brush speed 45mm', brand='MISC', default_price=39.9, default_cost=19.95, is_active=True),
            dict(sku='OGSPEEDXL55MM', name='Olivia Garden brush speedxl 55mm', brand='MISC', default_price=40.98, default_cost=20.49, is_active=True),
            dict(sku='POCF200ML', name='Pureology color fanatic 200ml', brand='PUREOLOGY', default_price=49.5, default_cost=19.8, is_active=True),
            dict(sku='POCFM200ML', name='Pureology colour fanatic mask 200ml', brand='PUREOLOGY', default_price=36.0, default_cost=20.4, is_active=True),
            dict(sku='POHCON250ML', name='Pureology hydrate conditioner 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=23.99, is_active=True),
            dict(sku='POHGCO50ML', name='Pureology Glow Catcher Oil 50ml', brand='PUREOLOGY', default_price=55.0, default_cost=33.0, is_active=True),
            dict(sku='POHM200ML', name='Pureology hydrate mask 200ml', brand='PUREOLOGY', default_price=42.0, default_cost=25.2, is_active=True),
            dict(sku='POHSCON250ML', name='Pureology hydrate sheer conditioner 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=26.73, is_active=True),
            dict(sku='POHSH250ML', name='Pureology hydrate shampoo 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=22.2, is_active=True),
            dict(sku='POHSSH250ML', name='Pureology Hydrate sheer shampoo 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=27.0, is_active=True),
            dict(sku='POLH312G', name='Pureology Lock it down hair spray 312g', brand='PUREOLOGY', default_price=42.0, default_cost=25.2, is_active=True),
            dict(sku='PONWCON250ML', name='Pureology Nano Works conditioner 250ml', brand='PUREOLOGY', default_price=56.0, default_cost=33.58, is_active=True),
            dict(sku='PONWSH250ML', name='Pureology Nano Works shampoo 250ml', brand='PUREOLOGY', default_price=55.0, default_cost=32.42, is_active=True),
            dict(sku='POORM294G', name='Pureology Root mousse 294g', brand='PUREOLOGY', default_price=46.0, default_cost=25.2, is_active=True),
            dict(sku='POPVCON250ML', name='Pureology pure volume conditioner 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=26.14, is_active=True),
            dict(sku='POPVSH250ML', name='Pureology Pure Volume shampoo 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=25.68, is_active=True),
            dict(sku='POSCBBMF145ML', name='Pureology SCBB miracle filler 145ml', brand='PUREOLOGY', default_price=34.0, default_cost=20.35, is_active=True),
            dict(sku='POSCBCON250ML', name='Pureology Strength Cure Blonde conditioner 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=23.63, is_active=True),
            dict(sku='POSCBSH250ML', name='Pureology Strength Cure Blonde shampoo 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=24.7, is_active=True),
            dict(sku='POSCCON250ML', name='Pureology strength cure conditioner 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=27.0, is_active=True),
            dict(sku='POSCM200ML', name='Pureology strength cure mask 200ml', brand='PUREOLOGY', default_price=42.0, default_cost=25.2, is_active=True),
            dict(sku='POSCSH1000', name='Pureology strength cure shampoo 1L', brand='PUREOLOGY', default_price=99.0, default_cost=57.24, is_active=True),
            dict(sku='POSCSH250ML', name='Pureology strength cure shampoo 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=26.92, is_active=True),
            dict(sku='POSPC250ML', name='Pureology Smooth Perfection conditioner 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=24.57, is_active=True),
            dict(sku='POSPL195ML', name='Pureology smooth perfection lotion 195ml', brand='PUREOLOGY', default_price=38.0, default_cost=22.8, is_active=True),
            dict(sku='POSPSH1000', name='Pureology smooth perfection shampoo 1L', brand='PUREOLOGY', default_price=99.0, default_cost=55.8, is_active=True),
            dict(sku='POSPSH250ML', name='Pureology Smooth Perfection shampoo 250ml', brand='PUREOLOGY', default_price=50.0, default_cost=21.6, is_active=True),
            dict(sku='POWVM238G', name='Pureology weightless volume mousse 238g', brand='PUREOLOGY', default_price=46.0, default_cost=25.2, is_active=True),
        ]

        retail_count = 0
        for r in RETAIL_DATA:
            brand = r.pop('brand')
            description = f"Brand: {brand}" if brand else None
            existing_item = (
                await db.execute(
                    select(RetailItem).where(
                        RetailItem.tenant_id == tid,
                        RetailItem.sku == r['sku'],
                    )
                )
            ).scalar_one_or_none()
            if existing_item is None:
                db.add(RetailItem(
                    tenant_id=tid,
                    description=description,
                    **r,
                ))
                retail_count += 1
            else:
                changed = False
                if float(existing_item.default_price) != r['default_price']:
                    existing_item.default_price = r['default_price']
                    changed = True
                if existing_item.is_active != r['is_active']:
                    existing_item.is_active = r['is_active']
                    changed = True
                if changed:
                    retail_count += 1
        print(f"Retail items: {retail_count} created/updated")

        # ── Promotions ───────────────────────────────────────────────────────
        # Source: docs/seed-data/Promotion List.xls
        # Upsert on code; sort_order follows list order.
        PROMO_DATA = [
            dict(code='DC $5',        label='DISCOUNT $5',         kind='amount',  value=5.0,   is_active=True),
            dict(code='DC $10',       label='DISCOUNT $10',        kind='amount',  value=10.0,  is_active=True),
            dict(code='DC $15',       label='DISCOUNT $15',        kind='amount',  value=15.0,  is_active=True),
            dict(code='DC $20',       label='DISCOUNT $20',        kind='amount',  value=20.0,  is_active=True),
            dict(code='DC $25',       label='DISCOUNT $25',        kind='amount',  value=25.0,  is_active=True),
            dict(code='DC $30',       label='DISCOUNT $30',        kind='amount',  value=30.0,  is_active=True),
            dict(code='DC $35',       label='DISCOUNT $35',        kind='amount',  value=35.0,  is_active=True),
            dict(code='DC $40',       label='DISCOUNT $40',        kind='amount',  value=40.0,  is_active=True),
            dict(code='DC $45',       label='DISCOUNT $45',        kind='amount',  value=45.0,  is_active=True),
            dict(code='DC $50',       label='DISCOUNT $50',        kind='amount',  value=50.0,  is_active=True),
            dict(code='DC $55',       label='DISCOUNT $55',        kind='amount',  value=55.0,  is_active=True),
            dict(code='DC $60',       label='DISCOUNT $60',        kind='amount',  value=60.0,  is_active=True),
            dict(code='REFERRAL $10', label='REFERRAL $10',        kind='amount',  value=10.0,  is_active=True),
            dict(code='REFERRAL $20', label='REFERRAL $20',        kind='amount',  value=20.0,  is_active=True),
            dict(code='REFILL 25%',   label='REFILL 25%',          kind='percent', value=25.0,  is_active=False),
            dict(code='STAFF D/C',    label='STAFF PRODUCT D/C',   kind='percent', value=37.0,  is_active=True),
            dict(code='VIP 5%',       label='VIP 5%',              kind='percent', value=5.0,   is_active=True),
            dict(code='VIP 10%',      label='VIP 10%',             kind='percent', value=10.0,  is_active=True),
            dict(code='VIP 15%',      label='VIP 15%',             kind='percent', value=15.0,  is_active=True),
            dict(code='VIP 20%',      label='VIP 20%',             kind='percent', value=20.0,  is_active=True),
            dict(code='VIP 25%',      label='VIP 25%',             kind='percent', value=25.0,  is_active=True),
            dict(code='VIP 30%',      label='VIP 30%',             kind='percent', value=30.0,  is_active=True),
            dict(code='VIP 50%',      label='VIP 50%',             kind='percent', value=50.0,  is_active=True),
            dict(code='VIP 100%',     label='VIP 100%',            kind='percent', value=100.0, is_active=True),
        ]

        promo_count = 0
        for sort_order, p in enumerate(PROMO_DATA):
            existing_promo = (
                await db.execute(
                    select(TenantPromotion).where(
                        TenantPromotion.tenant_id == tid,
                        TenantPromotion.code == p['code'],
                    )
                )
            ).scalar_one_or_none()
            kind_enum = PromotionKind.percent if p['kind'] == 'percent' else PromotionKind.amount
            if existing_promo is None:
                db.add(TenantPromotion(
                    tenant_id=tid,
                    code=p['code'],
                    label=p['label'],
                    kind=kind_enum,
                    value=p['value'],
                    is_active=p['is_active'],
                    sort_order=sort_order,
                ))
                promo_count += 1
            else:
                changed = False
                if existing_promo.is_active != p['is_active']:
                    existing_promo.is_active = p['is_active']
                    changed = True
                if float(existing_promo.value) != p['value']:
                    existing_promo.value = p['value']
                    changed = True
                if changed:
                    promo_count += 1
        print(f"Promotions: {promo_count} created/updated")

        # ── Admin user ───────────────────────────────────────────────────────
        # Created once; never overwrites an existing account.
        # Password sourced from ADMIN_PASSWORD env var so it never lands in code.
        admin_email = "frederick.ferguson@gmail.com"
        admin_pw = os.environ.get("ADMIN_PASSWORD", "")
        existing_admin = (
            await db.execute(select(User).where(User.tenant_id == tid, User.email == admin_email))
        ).scalar_one_or_none()
        if existing_admin is None and admin_pw:
            db.add(User(
                tenant_id=tid,
                email=admin_email,
                password_hash=hash_password(admin_pw),
                role=UserRole.tenant_admin,
                is_active=True,
                first_name="Freddy",
                last_name="Ferguson",
            ))
            print(f"Created admin user: {admin_email}")
        elif existing_admin is None:
            print(f"WARNING: admin user {admin_email} not found and ADMIN_PASSWORD not set — skipping")
        else:
            print(f"Admin user already exists: {admin_email}")

        await db.commit()
        print("\nSeed complete.")
        print(f"  Tenant ID : {tenant.id}")
        print()
        print("NOTE — needs owner input:")
        print("  CCAMO  Camo Colour        — in catalog, no per-provider pricing in XLS")
        print("  BOTNHC / BOTEXP           — new services added; durations need review")
        print("  CAC 'Additional colour'   — in XLS at $25, no service code in catalog yet")
        print("  CVC Vivid Color           — seeded for Sarah only; other providers unknown")


if __name__ == "__main__":
    asyncio.run(seed())
