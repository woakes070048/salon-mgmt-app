"""Backfill service_id on sale_items for the current fiscal year (Oct 1 2025 onward).

Two passes:
  1. Items with appointment_item_id — copy service_id from the appointment item.
  2. Items without appointment_item_id — resolve via description → RECEIPT_SERVICE_MAP → service_code.

Safe to re-run; uses UPDATE ... WHERE service_id IS NULL so already-set rows are skipped.
"""
import asyncio
from datetime import date
from sqlalchemy import text
from app.database import AsyncSessionLocal

FISCAL_START = date(2025, 10, 1)


async def main() -> None:
    async with AsyncSessionLocal() as db:

        # ── Pass 1: items with appointment_item_id ────────────────────────────
        r1 = await db.execute(text("""
            UPDATE sale_items si
            SET service_id = ai.service_id, updated_at = NOW()
            FROM appointment_items ai
            WHERE si.appointment_item_id = ai.id
              AND si.service_id IS NULL
              AND si.kind = 'service'
              AND EXISTS (
                SELECT 1 FROM sales s
                WHERE s.id = si.sale_id
                  AND s.completed_at >= :fiscal_start
              )
        """), {"fiscal_start": FISCAL_START})
        print(f"Pass 1 (via appointment_item): {r1.rowcount} rows updated")

        # ── Pass 2: items without appointment_item_id — description lookup ────
        # Build description → service_id map from the services table using
        # the same RECEIPT_SERVICE_MAP used by the import.
        from app.legacy_import import RECEIPT_SERVICE_MAP

        svc_rows = (await db.execute(text(
            "SELECT id, service_code FROM services WHERE is_active = true"
        ))).fetchall()
        code_to_id = {r.service_code.lower(): str(r.id) for r in svc_rows}

        desc_to_svc_id: dict[str, str] = {}
        for desc_lower, code in RECEIPT_SERVICE_MAP.items():
            if code and code.lower() in code_to_id:
                desc_to_svc_id[desc_lower] = code_to_id[code.lower()]

        total_pass2 = 0
        for desc_lower, svc_id in desc_to_svc_id.items():
            r2 = await db.execute(text("""
                UPDATE sale_items si
                SET service_id = :svc_id, updated_at = NOW()
                FROM sales s
                WHERE si.sale_id = s.id
                  AND si.appointment_item_id IS NULL
                  AND si.service_id IS NULL
                  AND si.kind = 'service'
                  AND LOWER(si.description) = :desc
                  AND s.completed_at >= :fiscal_start
            """), {"svc_id": svc_id, "desc": desc_lower, "fiscal_start": FISCAL_START})
            if r2.rowcount:
                print(f"  '{desc_lower}' → {r2.rowcount} rows")
            total_pass2 += r2.rowcount

        print(f"Pass 2 (via description): {total_pass2} rows updated")

        await db.commit()

        # ── Summary ────────────────────────────────────────────────────────────
        remaining = (await db.execute(text("""
            SELECT COUNT(*) FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            WHERE si.kind = 'service'
              AND si.service_id IS NULL
              AND s.completed_at >= :fiscal_start
        """), {"fiscal_start": FISCAL_START})).scalar()
        print(f"\nRemaining unresolved service items: {remaining}")
        if remaining:
            print("These are services not in RECEIPT_SERVICE_MAP (e.g. BDB Reimbursement, Redo).")


if __name__ == "__main__":
    asyncio.run(main())
