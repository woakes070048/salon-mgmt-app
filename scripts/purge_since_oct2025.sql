-- Purge imported sales, appointments, and client records since October 1, 2025
-- so they can be reloaded from fresh Milano exports.
--
-- Run the preview SELECTs first. When counts look right, run the DELETE block.
-- Everything is wrapped in a transaction — ROLLBACK if anything looks wrong.
--
-- Clients are NOT deleted; they are updated in-place on re-import.
-- Only records dated >= 2025-10-01 are removed.

-- ── 1. Preview counts (run first) ────────────────────────────────────────────

SELECT COUNT(*)   AS sales_to_delete
FROM   sales
WHERE  completed_at >= '2025-10-01'
  AND  tenant_id = (SELECT id FROM tenants WHERE slug = 'salon-lyol');

SELECT COUNT(*)   AS appointments_to_delete
FROM   appointments
WHERE  appointment_date >= '2025-10-01'
  AND  tenant_id = (SELECT id FROM tenants WHERE slug = 'salon-lyol');

-- ── 2. Delete (run after verifying counts above) ──────────────────────────────

BEGIN;

DO $$
DECLARE
  tid UUID := (SELECT id FROM tenants WHERE slug = 'salon-lyol');
BEGIN

  -- Sales and their dependent rows
  DELETE FROM sale_payment_edits
  WHERE  sale_id IN (
    SELECT id FROM sales
    WHERE  completed_at >= '2025-10-01' AND tenant_id = tid
  );

  DELETE FROM sale_payments
  WHERE  sale_id IN (
    SELECT id FROM sales
    WHERE  completed_at >= '2025-10-01' AND tenant_id = tid
  );

  DELETE FROM sale_items
  WHERE  sale_id IN (
    SELECT id FROM sales
    WHERE  completed_at >= '2025-10-01' AND tenant_id = tid
  );

  DELETE FROM sale_appointments
  WHERE  sale_id IN (
    SELECT id FROM sales
    WHERE  completed_at >= '2025-10-01' AND tenant_id = tid
  );

  DELETE FROM sales
  WHERE  completed_at >= '2025-10-01' AND tenant_id = tid;

  -- Appointments and their dependent rows
  DELETE FROM appointment_reminders
  WHERE  appointment_id IN (
    SELECT id FROM appointments
    WHERE  appointment_date >= '2025-10-01' AND tenant_id = tid
  );

  DELETE FROM appointment_items
  WHERE  appointment_id IN (
    SELECT id FROM appointments
    WHERE  appointment_date >= '2025-10-01' AND tenant_id = tid
  );

  -- sale_appointments may also reference these appointments
  DELETE FROM sale_appointments
  WHERE  appointment_id IN (
    SELECT id FROM appointments
    WHERE  appointment_date >= '2025-10-01' AND tenant_id = tid
  );

  DELETE FROM appointments
  WHERE  appointment_date >= '2025-10-01' AND tenant_id = tid;

  RAISE NOTICE 'Done. Review row counts then COMMIT or ROLLBACK.';
END;
$$;

-- Check what remains before committing
SELECT 'sales remaining'        AS table_name, COUNT(*) FROM sales        WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'salon-lyol')
UNION ALL
SELECT 'appointments remaining',                          COUNT(*) FROM appointments WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'salon-lyol');

-- COMMIT;   -- uncomment when satisfied
-- ROLLBACK; -- uncomment to undo
