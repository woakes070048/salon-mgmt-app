# Product Backlog

> Prioritized list of work items. Phase 1 items are in scope now; Phase 2 items are next after the core appointment book is production-ready.

---

## 🚧 Dev environment — pending placeholders

The dev GCP project (`salon-mgmt-app-dev`) was stood up 2026-05-15. Code, CI/CD, banner, and email gating are all working — but several integrations were left with placeholder credentials so the first deploy could complete. Each item below needs real values before the corresponding feature can be tested in dev.

- **`DEV_AUTH0_CLIENT_ID` and `DEV_AUTH0_CLIENT_SECRET`** — Auth0 SSO won't work in dev until these are set. Either create a separate Auth0 tenant for dev (cleanest) or reuse prod's tenant and whitelist the dev frontend URL as an additional callback. Set via `gh secret set` / `gh variable set`.
- **`DEV_QZ_TRAY_PRIVATE_KEY`** — QZ Tray receipt printing won't sign in dev. The same cert/key as prod can be reused (the QZ Tray cert isn't environment-sensitive). Copy from GitHub secret `QZ_TRAY_PRIVATE_KEY`.
- **`DEV_RESEND_WEBHOOK_SECRET`** — inbound email webhook signatures won't validate in dev. Only matters if you want to test the inbound email pipeline against dev. Either point Resend's webhook at the dev URL with its own signing secret, or skip — dev is fine without inbound email.
- **Cloud SQL right-sizing** — dev is currently on `db-perf-optimized-N-2` ENTERPRISE_PLUS (~$100/mo) because shared-core `db-g1-small` ENTERPRISE was rejected by both `northamerica-northeast2` and `us-central1` on instance creation. Retry shared-core periodically; once available, downsize via Terraform (`db_tier = "db-g1-small"`, `db_edition = "ENTERPRISE"`) to drop dev cost to ~$10/mo.

Everything else (Cloud SQL provisioned, migrations running in CI, env-aware DEV banner, backend `send_email()` no-op in dev, schedulers disabled in dev, `dev` branch deploy workflow) is wired up and tested.

---

## Phase 1 — Core Appointment Book

### P1-0 · App shell and home dashboard · ✅ Complete

Replace the current pattern (login → straight to appointment book) with a proper app shell that persists across all staff pages.

**Shell layout:**
- Collapsible left sidebar (or persistent top nav on mobile) with nav links
- Nav items: Appointment Book · Clients · Requests · Staff · Reports · Settings
- Active route highlighted; salon name / logo in header
- "Sign out" moved into the shell (removed from individual pages)

**Home dashboard (`/home` or `/`):**
After login, staff land on a simple dashboard showing:
- Today's appointment count (per provider)
- Pending booking requests (count + quick link)
- Quick-action buttons: "+ New Appointment", "View today's book"

**What changes:**
- New `AppShell` layout component wrapping all staff routes
- New `DashboardPage` as the post-login landing
- `App.tsx`: staff root redirects to `/home` (dashboard); appointment book moves to `/appointments`; requests to `/requests`; staff settings to `/settings/staff`
- Remove the header + sign-out button from `AppointmentBookPage` (shell handles it)
- `RequireStaff` wraps the shell, not individual routes

### P1-1 · Convert request → appointment · ✅ Complete
Staff review an incoming booking request and convert it into a confirmed appointment, mapping each requested service/provider to real catalog entries and setting the confirmed time slot.

- Backend: `POST /appointment-requests/{id}/convert` — creates `Client` (or links existing), creates `Appointment` + `AppointmentItem`(s), marks request as `converted`
- Frontend: "Convert to appointment" action in `RequestsPage` — dialog to map items to real services/providers and pick a time; navigates to appointment book on success

### P1-2 · Provider schedule versioning and historical locking · ✅ Complete

Default weekly schedules already exist in the data model, but the current implementation overwrites history when a schedule changes. This item makes the schedule system behave correctly.

**Desired behaviour:**
- Each provider has a default schedule per weekday (working/off, start time, end time)
- Changing the default schedule applies from a specified future date (default: today) forward — past dates are unaffected
- Staff can still override any individual future date via a per-date exception (already implemented via `ProviderScheduleException`)
- Past schedules and past exceptions are read-only — no editing historical records

**What needs to change:**

Backend:
- `PUT /schedules/weekly/{provider_id}`: accept an optional `effective_from` date (default: today). Instead of deleting and reinserting EPOCH rows, close the current active schedule rows (`effective_to = effective_from - 1 day`) and insert new rows with the given `effective_from`. Historical EPOCH rows are preserved.
- `POST /schedules` (per-date exception): reject requests where `exception_date` is in the past

Frontend (`StaffSchedulePage`):
- Add an "Effective from" date picker (default: today) that travels with the Save button
- Show a note: "Changes apply from [date] · historical schedules are locked"
- The per-date override on the appointment book grid already blocks past dates (the WhoIsWorking toggle) — add the same guard

No schema migration required — `ProviderSchedule.effective_from` and `effective_to` already exist.

### P1-3 · Client card · ✅ Complete

View a client's full profile directly from the appointment book — without leaving the grid.

- Contact information (name, email, phone, pronouns)
- Upcoming appointments
- Past appointments (with services, providers, prices)
- Colour formula / service notes (free-text, per-client, versioned by date)
- No-show and cancellation history (count + dates)
- General notes (free-text, staff-visible)

Accessible by clicking the client name on any appointment block on the grid. Opens as a slide-over panel (not a full page navigation).

### P1-4 · Add / remove services on an appointment · ✅ Complete
From the appointment book, staff can add new `AppointmentItem`(s) to an existing appointment, or remove items that are no longer happening — without having to delete and recreate the whole appointment.

- Add: opens the booking form pre-scoped to the existing appointment's client and date
- Remove: confirmation prompt then soft-delete (status → `cancelled`) on the item

### P1-5 · Creative login / landing page · ✅ Complete
Replace the plain login page with a branded, visually engaging entry point appropriate for a premium Toronto salon. Should work well as the public-facing first impression for guests arriving to submit a booking request.

### P1-8 · Show service times in client Appointments tab · ✅ Complete

The Appointments tab on the client profile (Clients page) shows each service with the date but not the specific start time. Add the start time to each service line so staff can see exactly when each service is/was scheduled.

- Frontend only: update `VisitHistory` in `ClientsPage.tsx` to include the `start_time` from each visit item
- Requires the backend `/clients/{id}/history` endpoint to return `start_time` per item (currently only returns `service_name`, `provider_name`, `price`)
- Backend: add `start_time: str` to the `VisitItem` model in `clients.py` and populate it from `AppointmentItem.start_time`
- Frontend: display formatted time (e.g. "9:00 AM") alongside service name and provider on each item row

### P1-7 · Delete client · ✅ Complete

Staff can soft-delete (deactivate) a client record from the Clients page. A deleted client's history is preserved for reporting but they no longer appear in search results or the client list.

- Backend: `DELETE /clients/{id}` — sets `is_active = False` on the `Client` record (soft delete); returns 204
- Frontend: "Delete client" action in the client detail panel; confirmation dialog before proceeding; removes client from the list on success
- Guard: prevent deletion if the client has any upcoming (confirmed / in-progress) appointments — return a 409 with a clear message

### P1-6 · Branding configuration · ✅ Complete
Salon owners can upload a logo and set basic brand colours. Logo appears in the app header, on the login/landing page, and in outbound emails.

- `TenantSettings` entity (or extend `Tenant`): `logo_url`, `primary_colour`, `salon_name_display`
- Logo stored in Cloud Storage
- Settings page (staff/admin only)

---

## Phase 2 — POS, Notifications, and Reporting

### P2-1 · Checkout and payment · ✅ Complete
Staff check out a client at the end of their visit and record payment.

- `Sale` + `SaleItem` entities (per the ERM in `docs/reports/reports-annotations.md`)
- Payment types: AMEX, CASH, DEBIT, E-TRANSFER, MASTERCARD, VISA
- Split payment across multiple types
- Discounts (manual override or promotion code)
- GST and PST tracked per sale (Ontario: 5% + 8%)
- Checkout initiated from the appointment block on the grid or from client card

### P2-2 · Appointment confirmation notification · ✅ Complete
When a booking request is converted to a confirmed appointment, automatically send the client a confirmation via email and/or SMS.

- Message includes: date, time, provider(s), services, salon address, cancellation policy
- Channel (email / SMS / both) configurable per tenant
- Triggered by the convert endpoint (P1-1)

### P2-3 · Appointment reminder notifications · ✅ Complete
Send the client a reminder before their appointment. Lead time is configurable (e.g., 24 h, 48 h, or a custom number of hours before the appointment start).

- `AppointmentReminder` entity already exists in the schema
- Background job (Cloud Run Job or Cloud Tasks) to evaluate and dispatch pending reminders
- Channel (email / SMS / both) configurable per tenant
- Per-appointment opt-out

### P2-3a · Cancellation notice to client

When an appointment that already has a confirmation sent is cancelled by staff, offer to send the client a cancellation notice.

- Trigger: appointment is cancelled (status → `cancelled`) and `confirmation_sent_at` is non-null on the appointment record
- UX: after the cancellation action completes, show a prompt — "A confirmation was sent for this appointment. Send a cancellation notice to [client email]?" with Send / Skip options
- Email content: appointment date, time, provider(s), services, salon contact info, and a brief apology / re-booking invite
- Backend: `POST /appointments/{id}/send-cancellation` — sends the notice via the tenant's configured email, returns 204; 404 if no confirmation was ever sent
- No new schema fields needed — `confirmation_sent_at` already indicates a confirmation was sent; the cancellation notice is fire-and-forget (no tracking field in v1)
- Out of scope for v1: SMS channel, re-booking link, per-tenant on/off toggle

### P2-4 · New booking request notification to salon · ✅ Complete
When a guest submits a booking request via the public form, notify the salon staff by email.

- Notification email includes: guest name, requested date/time, services requested, special notes
- On/off toggle in tenant settings (default: on)
- Recipient address(es) configurable in tenant settings

### P2-5 · Monthly sales report · ✅ Complete
Comprehensive sales report for any configurable date range (daily, weekly, monthly).

Full spec in `docs/reports/reports-annotations.md`. Key sections:

| Section | Content |
|---------|---------|
| Revenue | Service Sales gross, Less Discounts / Returns / Voids, Total Service Sales; same for Retail |
| Gift Certificates & Series | Separate revenue lines |
| Taxes | GST and PST independently aggregated |
| On Account | Charges vs. payments, net position |
| Payment reconciliation | Breakdown by payment type (AMEX, CASH, DEBIT, E-TRANSFER, MASTERCARD, VISA) |
| Petty Cash | Reconciled into Grand Total |

- Exportable as PDF
- Key management metric: **Payroll % of Net Sales** (target: visible on report)

### P2-6 · Show sale summary on completed appointment · ✅ Complete

Follow-up to P2-1 (deferred Q3 from `docs/specs/P2-1-checkout-payment.md`). When viewing a completed appointment in `AppointmentDetail`, show the recorded sale: totals (subtotal, GST, PST, tip, total) and the payment breakdown (e.g., "Cash $40 · Visa $33.45").

- Frontend only (backend `GET /sales/by-appointment/{id}` already exists)
- Fetch the sale when the appointment status is `completed`; render under the existing "Checked out" indicator
- Read-only view in v1 (editing/voiding deferred — see P2-1 spec Q1)

**Receipt layout:** Three zones — **Header** (logo + salon name), **Body** (date/time; per-line service/retail amounts; summary block with Services, Retail, G/C, SubTotal, GST, PST), **Footer** (client first + last name, next appointment date, salon address, phone, email). Options include "Always Email eReceipt" and a default prompt (None / Receipt / eReceipt / Invoice). Our email receipt already covers the body/footer content; this structure is reference if we add a printable/PDF receipt in a future item.

### P2-7 · Edit a completed sale (correct payment methods / splits) · ✅ Complete

Staff sometimes record the wrong payment method or a bad split (e.g., charged $50 to Visa when it was actually Mastercard). They need to correct the receipt without voiding and re-creating the sale.

- Scope of editable fields: payment lines (`payment_method`, `amount`, add/remove split lines) and per-item discount and Business Reimbursed flag
- Server-side rule: edited payments must still sum to the existing sale total (no change to totals)
- Audit trail: every payment edit writes a `SalePaymentEdit` record (who, when, before → after JSON snapshot)
- **No same-day restriction for admins** — any completed sale is editable; the original same-day constraint was relaxed during parallel-run reconciliation to support historical corrections
- Backend: `PATCH /sales/{id}/payments` and `PATCH /sales/{id}/items/{item_id}`
- Frontend: "edit" link on each line item and "edit payments" link in the sale summary; accessible on all completed sales

### P2-7a · Business Reimbursed flag on sale items · ✅ Complete

When a salon absorbs a discount (e.g., a complimentary service for a dissatisfied client), the provider should still be commissioned on the full pre-discount amount — the salon, not the provider, is eating the cost. Without this flag, the provider's commission was silently reduced by any discount.

- `is_business_reimbursed` boolean on `SaleItem` (migration `i9j0k1l2m3n4`)
- Checkbox appears at checkout when a line item has a discount > 0 or a negative unit price (reversal)
- When set: provider commission basis = `unit_price × qty` (full amount); product fee always on full amount (unchanged)
- When not set: commission basis = `line_total` (what the client paid); product fee still on full amount
- Editable post-checkout via the sale summary edit UI or the Sales admin page
- Payroll report and payroll detail both respect the flag

### P2-7b · Sales admin page · ✅ Complete

Admins need a place to search and edit historical sales without navigating the appointment book calendar month by month — especially during parallel-run reconciliation.

- Finance → Sales in the nav (replaces the dead placeholder)
- Date range + client name search; up to 500 results, newest-first
- Each row: date, client, service summary, payment methods, total; expandable to full SaleSummary with edit controls
- Backend: `GET /sales` (list with filters) and `GET /sales/{id}` (single sale by ID)
- Finance → "Daily Report" retains the existing summary report at `/reports/sales`

### P2-8 · End-of-day cash reconciliation · ✅ Complete

Cash is the one payment method that has to physically match a count at the end of the day. Staff need a flow that tracks the running cash position and supports a daily till count with variance.

**Core model:**
- A `CashReconciliation` record per tenant per business day, with: `opening_balance` (from previous close), `expected_cash`, `counted_cash`, `variance`, `deposit_amount`, `notes`, `closed_by_user_id`, `closed_at`.
- "Expected cash" = previous closing balance + (cash payments since) − (cash refunds since) − (deposits since) ± (petty cash adjustments).
- Petty cash entries (small in/out, e.g. coffee for staff, tip-out) recorded as `PettyCashEntry` rows tagged with the active reconciliation period.

**Flow:**
1. Staff opens the reconciliation page; app shows previous closing balance and cash movements since.
2. Staff records actual counted cash + any deposit going to the bank.
3. App computes variance and prompts for a note if non-zero.
4. Closing the reconciliation locks all cash payments and petty-cash entries in that period — they can no longer be edited (protects audit trail).
5. The closing balance becomes the next day's opening.

**Why this matters:** without this, the P2-5 sales report can compute "cash sales" but no one can confirm the till matches. This is the linchpin of cash control.

**UI design notes:**
1. Reconcile **all payment types** (not just cash), entering a "Counted" amount for each. Card types compared against terminal batch totals. For v1 scope to cash-only (cards are self-reconciling) but the UI should anticipate the fuller model.
2. Support a date-range picker — reconciliations should be runnable for any date, not just "today".
3. The cash denomination grid is a nice-to-have — staff count by denomination rather than entering a lump sum. Consider as an optional mode: staff enter counts of each denomination (100, 50, 20, 10, 5, 2, 1, 0.50, 0.25, 0.10, 0.05, 0.01); system multiplies and totals, showing: Total Cash Counted, Less Opening Float, Net Cash Counted, Net Cash Expected, Over/Under variance.

**Depends on:**
- P2-5 (monthly sales report) — shares the reconciliation period model and petty cash semantics.
- "Cash" payment method needs to be identifiable across tenant-defined payment methods (use `kind = 'cash'` on the `TenantPaymentMethod` row).

### P2-9 · Tip-as-cashback flow (tips are not salon revenue) · ✅ Complete

P2-1 currently models tip as part of the sale (`Sale.tip_amount`, included in `total`, payments must cover it). That's the conventional POS model but it's **wrong for Salon Lyol's actual workflow**:

- Client owes the bill amount (subtotal + tax). They tender extra cash.
- Cashier returns the overage as **cashback to the client**.
- The client physically hands that cash to the staff member as a tip.
- The tip **never touches the salon's books** — not counted as revenue, not in the cash drawer's net intake.

**What needs to change:**

1. **Sale model:** drop `tip_amount` from the sale record (or keep as a non-revenue informational field flagged "not revenue"). Sale total = subtotal − discount + GST + PST. No tip.
2. **CheckoutPanel UI:** replace the "Tip ($)" input with an **"Amount tendered" → "Change due"** pattern, like a real till. Cashier types what the client handed over (cash); UI computes change. The change goes back to the client (who may or may not pass it to staff — none of the salon's business). For card payments, this whole concept doesn't apply — card runs for bill amount only.
3. **Cash drawer math:** for a cash sale, drawer goes up by the **bill amount**, not the tendered amount. The recorded `Payment.amount` stays equal to the bill, which keeps the till tally (P2-8) honest.
4. **Tip tracking for staff:** if the salon ever wants to track tips per stylist (for tax/reporting reasons stylists might need), that's a separate side ledger keyed by appointment_item but explicitly outside the sale total. Out of scope for v1; flag for later.

**Why this matters:** treating tips as sale revenue inflates GST/PST liability (since taxes are computed on `subtotal`, but if tips were ever rolled into total they'd distort cash totals), distorts payroll-to-revenue ratios, and breaks cash reconciliation (P2-8). Get the model right before more code piles on top.

**Depends on:** revisits P2-1 (`Sale.tip_amount`, `CheckoutPanel`, `POST /sales` total computation). Should land before P2-8 since reconciliation math assumes recorded cash payments equal the cash actually retained.

### P2-10 · Tenant-defined promotions (per-service discount) · ✅ Complete

Salons run their own promotions — "Senior Tuesday", "First-time colour", "Stylist's birthday week". Promotions are configured by an admin and applied at checkout to **individual service lines**, not to the sale as a whole.

**Promotion types (v1):**
- **Percent** — e.g., 10% off the line's `unit_price`.
- **Fixed amount** — e.g., $5 off the line, regardless of price.

**Data model:**
- `TenantPromotion` table per tenant: `code`, `label`, `kind` (`percent` | `amount`), `value` (numeric — interpreted as percent or dollars based on `kind`), `is_active`, `sort_order`. Optional fields for v2: `start_date`/`end_date` for time-bounded campaigns, `service_filter` to restrict eligibility.
- `SaleItem` already has `discount_amount`; add a nullable `promotion_id` FK so reporting (P2-5 "Less Discounts" line) can attribute the discount source.

**Checkout UX:**
- Each item line gets a "Apply promotion" picker showing active promotions.
- Selecting one populates `discount_amount` server-side based on the promotion's `kind` and `value`. Staff can still type a manual discount instead — promotion picker and manual entry are alternatives, not stacked.
- The line shows the promotion label next to the discount amount so it's auditable later.

**Settings UX:** "Promotions" tab (admin), parallel to "Payment methods". Same row pattern: label, code, kind, value, active toggle.

**Out of scope for v1:** stacking multiple promotions, customer-facing codes for guest entry, threshold-based promos ("$10 off any service over $100"), per-service eligibility filters.

### P2-34 · Receipt printer + cash drawer on checkout · ✅ Committed

On checkout completion, SalonOS should print a physical receipt to the salon's Epson TM-T88V and, for cash sales, trigger a cash drawer open pulse. Receipt can also be emailed as PDF — both options are independent and can be combined.

**Hardware:** Epson TM-T88V (80mm thermal, ESC/POS). Has built-in Ethernet (10/100Base-T) — reachable on the salon's local network via TCP port 9100.

**Architecture constraint:** SalonOS runs on GCP (Cloud Run). The printer and cash drawer are local to the machine running the browser. GCP cannot reach the printer directly. The print path must go: GCP backend → browser → local bridge → printer.

**Receipt layout (matching Milano):**

```
[LYOL logo image]
Salon Lyol
1452 Yonge Street, Toronto, ON M4T 1Y5
(416) 922-0611

{date}                    {time}
--------------------------------
Services                {total}
Retail                  {total}
G/C (gift card)         {total}
SubTotal                {total}
GST                     {total}
PST                     {total}
================================
[payment method lines]

Hi {client_first_name},
Your next appointment: {next_appointment}

accounting@salonlyol.ca
www.salonlyol.ca
```

**Scope:**

Backend:
- `POST /sales/{id}/print` — fetches sale + client + next upcoming appointment, formats ESC/POS commands per layout above (logo via GS v 0, text lines, totals, footer with client name + next appt), returns 200 on success.
- `POST /sales/{id}/email-receipt` — renders the same layout as PDF and emails to the client's address on file.
- Drawer open command (`ESC p 0 25 255`) appended to print job automatically for cash sales; also available as a standalone trigger.
- Local bridge: **QZ Tray** (recommended) — Java app installed on the salon PC; browser connects via WebSocket to `wss://localhost:8181` and sends raw ESC/POS bytes; QZ Tray writes them to the printer over local TCP:9100. No polling lag, no background service to manage beyond QZ Tray itself. Alternative: lightweight Python sidecar that polls `GET /sales/pending-print` — simpler to build but adds polling lag and requires keeping a service running.

Frontend:
- Post-checkout sale summary panel: "Print receipt" button + "Email receipt" button (independent). Both can be triggered together.
- Cash sales: auto-trigger print + drawer on checkout success; show toast.
- Settings page: printer config — connection type (USB/network), IP + port for network, paper width (80mm), enable/disable auto-print, enable/disable cash drawer.

**Logo:** uploaded via Settings (not hardcoded). Stored as a tenant asset; sent to printer via ESC/POS GS v 0 raster image command.

**Email receipt:** use existing transactional email path (SendGrid/SMTP). Render receipt as PDF, attach, send to client's email on file.

**Local bridge: QZ Tray.** Java app installed once on the salon PC. Browser connects via WebSocket (`wss://localhost:8181`), sends raw ESC/POS; QZ Tray writes to printer over local TCP:9100. No open questions — ready to build.

**Phase:** P2 (POS completeness — cash transactions require a physical receipt).

### P2-35 · Extract client colour formulas and special notes from Milano · 🔴 Top Priority

The existing Milano import (`POST /admin/import-legacy`) brings in client records, appointments, and receipts but skips colour formulas and per-client service notes stored in Milano's Client Details export. These are arguably the highest-value data for stylists — losing them on migration means stylists have to rebuild notes from memory.

**What Milano exports:**
- `Client Details.txt` includes free-text fields per client: formula notes, allergy/sensitivity flags, general notes, and preferred products. These are typically in fixed-width or delimited columns alongside the client's name and code.

**What needs to change:**

Backend (`legacy_import.py`):
- Parse the formula / notes / allergy columns from `Client Details.txt` during import.
- Write formula content to `ClientNote` rows (type `formula`, dated to the import date as a best-effort timestamp, linked to the client via `client_id`).
- Write general notes to `ClientNote` rows (type `note`).
- Write allergy/sensitivity text to `Client.allergy_notes` (or a new `Client.sensitivity_notes` column if the field doesn't exist yet) — check current schema first.
- Idempotent: re-running the import should update existing formula/note rows rather than duplicate them (match on `client_id` + type + source `legacy_import`).

Frontend:
- No new UI required — the existing Client Card already displays `ClientNote` entries in the Notes tab. Verify the formula tab renders correctly after import.
- Admin import page: show a row count for formulas/notes imported in the results summary.

**Why this is top priority:** stylists depend on formula history. If it's missing at go-live, staff will distrust the system from day one. This is a one-shot data quality fix that's cheap now and expensive later (manual re-entry per client).

**Depends on:** existing Milano import infrastructure (`legacy_import.py`, `DataImportPage.tsx`, `ClientNote` model).

### P2-11 · Pay for multiple appointments together (group checkout)

Common case: a parent/guardian arrives with one or more children, each booked into separate appointments (different providers, different services, different times). The parent expects one transaction at the end, not three.

**What needs to change:**

The current model assumes one sale per appointment (`uq_sale_appointment` constraint on `sales.appointment_id`). That has to give. Cleanest approach: replace `Sale.appointment_id` with a `sale_appointments` junction (`sale_id`, `appointment_id`, unique on `(tenant_id, appointment_id)` so each appointment still has at most one sale).

Sale items already reference `appointment_item_id` — they naturally span multiple appointments under a junction model. Reporting still attributes each item to its own provider; nothing changes downstream.

**Eligibility rules (v1):**
- All grouped appointments must be **same tenant, same business day, status `in_progress`**.
- No restriction on payer identity — staff judgment, no enforced "same family" linkage. (If the salon ever wants to track household for marketing, that's `ClientHousehold` work, separate.)

**Checkout UX:**
1. Staff initiates checkout from any one of the appointments.
2. The CheckoutPanel shows a "+ Add appointment to this sale" affordance listing other in-progress same-day appointments.
3. Staff picks which to include; line items merge into one cart.
4. Single payment covers everything; on success, **all** linked appointments transition to `completed` atomically (preserves the P2-1 R3 atomicity rule, just over a set instead of one).

**Reporting impact:** P2-5 needs to count each appointment-item once (not multiply across grouped appointments). The junction model makes this natural — items are already 1:1 with appointment_items.

**Depends on:** revisits P2-1 (the `appointment_id` FK on `Sale` and the unique constraint). Pre-UAT lifecycle means we drop the column and add the junction in a single migration with no backfill drama.

### P2-12 · Retail items (catalog + checkout integration) · ✅ Complete

`RetailItem` + `RetailCategory` catalog with full CRUD (`RetailPage.tsx`). `SaleItem.kind` discriminator (`service` | `retail`). "+ Add retail item" picker in `CheckoutPanel`. Per-item GST/PST exempt flags applied at checkout.

### P2-13 · Inventory management · ✅ Complete

`RetailStockMovement` ledger (receive / sell / adjust / return). On-hand count computed on read. Checkout atomically writes `kind=sell` movements. Receive and adjust flows on the retail item detail page.

### P2-14 · Services management (top-level page)

Backend already has `Service`, `ServiceCategory`, and `ProviderServicePrice` — including processing-offset and processing-duration columns for colour-development gap time. What's missing is the staff UI: today only `GET /services` exists, so adding/editing a service requires a developer to touch the database. Blocks salon self-sufficiency before UAT.

**Backend additions:**
- `POST /services`, `PATCH /services/{id}`, `DELETE /services/{id}` (soft via `is_active=false`).
- `POST /service-categories`, `PATCH /service-categories/{id}`, `DELETE /service-categories/{id}`.
- `GET/POST/PATCH/DELETE /provider-service-prices` for the capability + per-provider override matrix. (May exist partially — verify.)

**Frontend (top-level "Services" nav entry):**
- Service catalog grouped by category: list view with name, default price, default duration, active toggle.
- Edit form covering all the fields the data model exposes: code, name, description, category, default price/cost, duration, processing offset + duration, haircut type (when relevant), pricing type (fixed/hourly), tax flags, addon flag, suggestions/notes.
- Inside the service edit view: provider matrix — which providers offer this service, with optional per-provider price + duration overrides. Adds rows to `ProviderServicePrice`.

**Out of scope for v1:** tier-based pricing across providers, time-bounded `effective_from`/`effective_to` on prices (column exists; UI defers it), service photos, online booking eligibility flags.

**Why this is the natural next step:** services are the catalogue the entire appointment book operates on. Without staff CRUD, every catalogue change is a developer task. P2-12 (Retail) reuses the same UI conventions, so building Services first establishes the pattern.

### P2-15 · Tenant time format (12h / 24h)

Each tenant chooses whether the app displays times in 12-hour (`6:00 PM`) or 24-hour (`18:00`) format. Affects every place a time is rendered: appointment book grid, appointment detail, sale summary, requests, settings, staff schedules, etc. Inputs (`<input type="time">`) honour the same setting where the browser allows it.

- `tenants.time_format`: `"12h" | "24h"`, default `"12h"`.
- Backend: expose on `GET /settings/branding` and accept on `PATCH /settings/branding`.
- Frontend: shared `formatTime(hhmm: string)` helper reading the tenant setting; replace ad-hoc `HH:mm` formatting throughout.
- Setting lives under Settings → Scheduling alongside slot granularity and operating hours.
- Display rule when 12h is active: drop leading zeros on the hour (e.g. `6:00 PM`, not `06:00 PM`).

### P2-16 · Branded email layout

All outbound emails (confirmations, welcome, password reset, future reminders) currently render as plain HTML with no consistent chrome. Wrap them in a tenant-branded layout that uses the same logo and brand colour set under Settings → Branding (P1-6).

**Shared layout (a single `app/email_layout.py` helper):**
- Header: tenant logo (`tenant.logo_url`) on a brand-coloured band, with the salon name as alt text fallback when no logo is set.
- Body slot: rendered content (existing template HTML).
- Footer: salon name + address + a small "If you weren't expecting this email…" line.
- Inline CSS only (Gmail/Outlook compatibility); brass/brand colour pulled from `tenant.brand_color`; web-safe fallback fonts; readable text colour computed from brand colour luminance (white text on dark brands, near-black on light).
- Fixed max-width container (~600px) with light cream background, mirroring the in-app aesthetic.

**Wire-up:**
- `email.py` gains a `wrap_branded(html, tenant)` helper. `send_email` callers pass the tenant (or a small `BrandingContext`) so the wrapper can inject the chrome.
- Confirmation, welcome, and password-reset templates collapse to the inner body only; the outer chrome lives in the layout.
- Settings → Email tab gains a "Send sample" button (in addition to the existing test) that previews the branded layout with a placeholder body.

**Out of scope for v1:** custom email header images per tenant, per-email-type logo overrides, dark-mode-aware emails, plain-text alternative parts (we already only send HTML).

**Depends on:** P1-6 branding (already shipped — logo URL + brand colour live on `tenants`).

### P2-17 · Rich-text email body editor

The P2-2 confirmation dialog (and any future tenant-facing email composer) currently shows the body as a read-only rendered preview. Staff don't write HTML — they need a WYSIWYG that produces email-safe HTML they can edit comfortably.

**Scope:**
- A small WYSIWYG component (Tiptap or Lexical) with a minimal toolbar: bold, italic, underline, link, bullet list, paragraph break. No headings, no images in v1 — kept tight on purpose so output stays email-client-safe.
- Output sanitized to a constrained allowlist of inline tags + attributes before persisting (`<p>`, `<strong>`, `<em>`, `<u>`, `<a href>`, `<ul>`, `<ol>`, `<li>`, `<br>`).
- Replaces the preview block in `ConfirmationDialog`; subject input stays as-is.
- Initial value comes from the existing default template (or saved draft).
- Save / Send still post the resulting HTML to the existing endpoints — no schema change.

**Out of scope for v1:** images, inline styles, custom fonts, source-HTML toggle, merge-tag insertion (e.g. `{{client.first_name}}`). Those land alongside tenant-customizable templates if/when that feature ships.

**Depends on:** P2-2 (already shipped — endpoints accept arbitrary HTML body).

### P2-18 · Tenant contact details (address, phone, hours)

`tenants` currently has `name`, `logo_url`, `brand_color`. It's missing the contact info needed to render a real footer on emails (P2-16 omits address for v1) and a public-facing "how to reach us" section on the landing page (which currently hardcodes "1452 Yonge Street").

**Schema additions on `tenants`:**
- `address_line1`, `address_line2`, `city`, `region`, `postal_code`, `country` — stored as discrete fields, not a free-text blob, so we can format per locale and link to maps.
- `phone` (E.164 string).
- `hours_summary` — a short human string like "Tue–Sat · 9–6", because per-day hours already live on `TenantOperatingHours` and don't need a second source of truth. Just a display caption.

**Wire-up:**
- Settings → Branding form gets a "Contact" section (address fields + phone + hours summary).
- Landing page reads from the tenant API (no more hardcoded address).
- Email footer (P2-16 layout) gains an address line + phone when set; falls back to name-only when blank.

**Out of scope for v1:** geo-coding, multiple locations per tenant, opening-hours overrides for holidays.

### P2-19 · Cancel-from-client-card stale grid state

When an appointment is cancelled from the client card (Clients → client → Appointments tab → Cancel), it stays rendered as blue (confirmed) on the appointment book grid until a full page reload. A manual reload shows the correct cancelled state, so the data is being persisted; only the cached grid view is stale.

**Likely fix:** the cancel mutation in `ClientsPage`'s `VisitHistory` invalidates `['client-history', clientId]` but not `['appointments', date]` — add the second invalidation (or all-dates: `['appointments']`). Same pattern that other appointment-mutating callers already follow. Verify in the browser after the patch.

**Why it matters:** day-of-day book hygiene — staff who triage a no-show via the client card will still see the appointment as live on the grid and might double-book or get confused.

---

### P2-27 · Self-service password reset ("forgot password")

Any user — staff, admin, or client (guest role) — can request a password reset link from the login page when they've forgotten their password. The reset token infrastructure (`PasswordResetToken`, `POST /auth/reset-password`, `ResetPasswordPage`) already exists; what's missing is the self-service request half.

**What needs to be built:**

Backend:
- `POST /auth/request-reset` — accepts `{ email }`, looks up any active user by email regardless of role. Generates a `PasswordResetToken` (reusing `_create_reset_token` already in `admin.py`), sends a password reset email, and always returns 204 — even when no account exists for that email (prevents account enumeration). Token expires in 1 hour (same as welcome-email tokens).
- The reset email reuses the existing branded layout (`wrap_branded`) with a single CTA: "Set your password" → `/reset-password?token=…`. Subject line: "Reset your SalonOS password".

Frontend:
- `LoginPage`: add a "Forgot password?" link below the sign-in form → navigates to `/forgot-password`.
- New `ForgotPasswordPage` (`/forgot-password`): email input + submit button. On success show a confirmation message ("If an account exists for that email, a reset link is on its way") — no redirect, same page. Matches the existing `ResetPasswordPage` visual style.
- No changes to `ResetPasswordPage` — it already handles the token-consumption half correctly.

Admin-triggered reset:
- `UsersPage`: add a "Send reset link" action to each user row (next to Edit role / Delete). Calls a new `POST /admin/users/{user_id}/send-reset` endpoint. Useful when a staff member is locked out and can't self-serve. Shows a toast on success.

**What doesn't change:** The existing welcome-email flow (admin creates user → reset link sent) is unaffected. This item only adds the self-service path.

**Depends on:** SMTP config (already in place via Settings → Email).

---

### P2-28 · Social / SSO login via Auth0 · ✅ Complete

Google SSO live via Auth0 (tenant: `salonlyol.ca.auth0.com`). Login and register pages show "Continue with Google". Apple SSO removed — requires paid Apple Developer account and not needed for this use case. Auth0 credentials injected into Cloud Run via CI; Google OAuth app registered in GCP project salon-mgmt-app-2026.

**Why Auth0 over alternatives:** OIDC-compliant (maps cleanly onto the existing JWT flow), strong FastAPI + React SDKs, social connections (Google, Apple) included on the free tier, and pricing scales predictably. Firebase Auth would be simpler to provision on GCP but pulls toward the Firebase ecosystem, which conflicts with the Cloud SQL / FastAPI stack.

**Scope:**

Backend:
- Replace `create_access_token` / `verify_password` in `app/auth.py` with Auth0 JWT verification (validate `iss`, `aud`, `exp` on the token; no local secret needed).
- `POST /auth/login` becomes a thin pass-through or is removed entirely — clients obtain tokens directly from Auth0 and present them as Bearer tokens.
- User provisioning on first login: if no `users` row exists for the Auth0 `sub`, create one with the appropriate role (`guest` for client portal, `staff` for new invitees). Tenant association still set server-side on first login based on invite or subdomain.
- `PasswordResetToken` table and `POST /auth/request-reset` (P2-27) become redundant for social-login users — password reset is Auth0's responsibility for those accounts. Keep the email/password path for tenants that prefer it.

Frontend:
- `LoginPage`: replace the email/password form with an Auth0 `loginWithRedirect` call (React SDK). Keep email/password as a fallback option (Auth0 supports both on the same tenant).
- `ResetPasswordPage` and `ForgotPasswordPage` (P2-27): only shown for email/password accounts; Auth0 handles reset for social accounts.
- `store/auth.tsx`: swap local JWT storage for Auth0 `useAuth0` hook; `getAccessTokenSilently()` replaces manual token refresh.

Multi-tenant routing:
- Auth0 supports multiple applications or a single app with metadata. Simplest approach for Phase 1: one Auth0 application, `tenant_id` stored as a custom claim on the token (set via an Auth0 Action on login). Revisit when multiple tenants need isolated login pages.

**Out of scope for v1:** SAML / enterprise SSO connections (relevant for future corporate spa/hotel tenants — Auth0 supports it but it's a paid add-on), per-tenant Auth0 organisations, magic-link email login.

**Depends on:** P2-27 (password reset) is a parallel concern — build P2-27 first so email/password accounts have a complete self-service flow before SSO is layered on top.

---

## Data Import (Migration from existing systems)

### Milano import page · ✅ Complete

`DataImportPage.tsx` + `POST /admin/import-legacy` endpoint. Accepts Milano's specific export files (Client Details.txt, Future and Past Bookings.txt, Receipt Transactions.txt, All Bookings.txt, On Account Summary.txt) and bulk-inserts clients, appointments, and receipts. Available to admins for re-runs. The structured P2-20–23 specs below (generic CSV/Excel with dry-run and deduplication for future migrations) remain open if ever needed.

---

### P2-MERGE · Duplicate merge — allow staff to choose the non-recommended card

When merging duplicate clients, the system recommends one card as the primary (based on appointment count) and highlights it with a "Primary" badge. Staff should be able to explicitly choose either card as the one to keep, not just accept the recommendation.

**Current state:**
- A "Swap primary" icon button exists on the pair card, but the "Primary" badge is tied to `recommended_primary_id` from the server — it does not update when staff swap. So after swapping, the card being kept has no badge, and the card being discarded still shows "Primary". The affordance is an icon with a tooltip title, not a prominent labelled action.

**What needs to change:**

- `ClientCard` should show the "Primary" (keep) badge based on which card is currently selected as primary, not the server's recommendation. The recommendation is a hint, not a lock.
- The swap control should be replaced (or supplemented) with a clear per-card action: "Keep this record" button on each card, or a radio-style selection. Staff should be able to see at a glance which card will survive and which will be merged in.
- The recommendation from the server (`recommended_primary_id`) can still be pre-selected as the default, but the badge should track the staff's active choice.
- No backend change needed — `POST /{primary_id}/merge` already accepts whichever ID is passed as primary.

**Why this matters:** Staff correcting import duplicates often know which record has the right contact info regardless of appointment count. The current UI misleads them into thinking the recommendation is enforced, and the unlabelled swap button is easy to miss.

---

### P2-20 · Import client data (with history and future appointments)

Bulk import client records from a CSV or Excel export of an existing salon system, including appointment history and any future bookings.

**Scope:**
- CSV/Excel upload via an admin-only import page
- Client fields: first name, last name, cell phone, email, pronouns, special instructions, VIP flag, no-show count, late cancellation count
- Appointment history: date, services, provider, price, status — imported as read-only `completed` appointment records for reporting continuity
- Future appointments: imported as `confirmed` appointments and shown on the book — staff review and adjust times/providers as needed
- Deduplication: match on (email OR phone) before creating a new client; prompt staff to confirm merge or create new when a potential match is found
- Dry-run mode: show a preview of what would be created/merged before committing

**Out of scope for v1:** colour notes import, no-show date details (just counts), payment history.

**Why this matters:** without client history, the appointment book starts cold and staff lose the institutional memory of client preferences, formulas, and no-show patterns built up over years.

### P2-21 · Import retail inventory

Bulk import the retail product catalog (and optionally opening stock counts) from a CSV/Excel export.

**Scope:**
- Fields: SKU (optional), name, description, category, default price, default cost, GST exempt flag, PST exempt flag
- Optional opening stock column — if provided, creates a `RetailStockMovement` with `kind=receive` for each row
- Duplicate detection on SKU (if provided) or name+category match
- Dry-run preview before commit

**Depends on:** P2-12 (Retail items catalog must exist first).

### P2-22 · Import staff (provider) data

Bulk import provider profiles and their default weekly schedules from a CSV/Excel export.

**Scope:**
- Fields: display name, provider type (stylist/colourist/dualist), booking order, has_appointments flag
- Optional schedule columns: Mon–Sun working flag, start time, end time (same format as the staff schedules page)
- Duplicate detection on display name (exact match, case-insensitive)

### P2-23 · Import services data

Bulk import the service catalog from a CSV/Excel export, including per-provider pricing overrides.

**Scope:**
- Fields: category, service name, code, default price, default duration (minutes), processing offset + duration (for colour), haircut type, GST/PST exempt flags, is_active
- Optional provider-price sheet: provider name, service name, price, duration override — maps to `ProviderServicePrice`
- Duplicate detection on (category + name)

**Why import order matters:** P2-22 (staff) and P2-23 (services) should be imported before P2-20 (clients + appointments) so that appointment history can correctly reference existing providers and services.

### P2-26 · User display names

Staff and admin accounts currently show only their email address on the Users page. Adding a name makes it easier to identify users at a glance and matches the way providers and clients are displayed elsewhere in the app.

**Data model:**
- Add `first_name` and `last_name` (nullable strings) to the `users` table. Both fields are optional — legacy accounts without names continue to work, falling back to showing the email only.
- Guest users already have a name via their linked `Client` record (`client_name` is already returned by `GET /admin/users`); this item covers staff and admin accounts.

**Backend:**
- Migration: add `first_name`, `last_name` columns to `users`.
- `GET /admin/users`: include `first_name`, `last_name` in the response (already returned as `client_name` for guests; staff/admin get their own name fields).
- `POST /admin/users` (create): accept optional `first_name`, `last_name`.
- `PATCH /admin/users/{id}` (edit role — P2-24): also accept `first_name`, `last_name` in the same call.

**Frontend:**
- Users page: display `{first_name} {last_name}` under the email, same as how guests show their client name today.
- Add user form: add optional First name / Last name fields.
- Edit role dialog: add First name / Last name fields alongside role.

**Out of scope:** enforcing names on existing accounts, merging with the Provider `display_name` (providers have their own name field; this is just for the login account record).

### P2-24 · Edit user role · ✅ Complete

`EditRoleDialog` in `UsersPage.tsx`; `PATCH /admin/users/{user_id}` (admin router). Role editing only; display name editing deferred to P2-26.

### P2-25 · Hard-delete user · ✅ Complete

Delete button + confirmation dialog in `UsersPage.tsx`; `DELETE /admin/users/{user_id}`. Guards against deleting self, last admin, and providers with future appointments. Cascades across 13+ tables; sale records preserved for audit.


### Login Log · ✅ Complete

Records every successful login (user, timestamp, IP). Viewable by admins under a collapsible **Users** nav group in the sidebar (`LoginLogsPage.tsx`; `login_log` table + backend router).

---

### P2-29 · Cashier tracking on sales

Every sale should record who processed the checkout — the cashier — as a distinct field from the service providers on the line items. At Salon Lyol, the person at the desk taking payment is often not the same person who performed the service.

**What to add:**
- `Sale.cashier_user_id` (FK → `users`, nullable for historical sales) — set at the time `POST /sales` is called, from the JWT of the logged-in user
- `SaleItem` already has `provider_id` for service attribution; retail items should also carry `commission_provider_id` (who earns the retail commission — currently partially modelled in `CheckoutPanel` as `commissionProviderId` but may not be persisted)

**Backend:**
- Migration: add `cashier_user_id UUID REFERENCES users(id)` to `sales`
- `POST /sales`: set `cashier_user_id = current_user.id` automatically — no client input required
- `GET /sales` + report endpoints: include `cashier_user_id` and resolved name in responses

**Frontend:**
- Sale summary (P2-6 view): show "Processed by [name]" alongside the payment breakdown
- Sales report (P2-5): add cashier column to the per-sale breakdown; allow filtering by cashier

**Why it matters:** accountability, dispute resolution, and accurate retail commission attribution when the person at the desk is different from the provider.

---

### P2-30 · Record-level audit trail (created/updated by)

Key tables should record which user created or last modified a record, not just when. Enables accountability, debugging, and audit compliance.

**Scope — tables that warrant this (priority order):**
1. `sales` — already getting `cashier_user_id` (P2-29); also add `updated_by_user_id` for payment edits
2. `appointments` — who confirmed, who last modified
3. `clients` — who created or last edited the client record
4. `colour_notes` — already has `created_by_user_id` (verify); ensure updates are attributed
5. `provider_schedules` — who last changed a provider's schedule
6. `sale_payment_edits` — already has `edited_by_user_id` (audit log pattern already in place for P2-7)

**What to add per table:**
- `created_by_user_id UUID REFERENCES users(id)` — set once on insert from JWT, never changed
- `updated_by_user_id UUID REFERENCES users(id)` — set on every mutating operation

**Implementation notes:**
- FastAPI dependency `CurrentUser` is already available in every router — pass it through to the service layer or set directly in the route handler
- For tables updated via background jobs (reminder dispatch, briefing engine): set `updated_by_user_id = NULL` — system-initiated changes are distinguished by null
- No UI changes required for v1 — this is backend + schema only; surface in audit views as needed
- Migration per table: nullable columns with no backfill required (historical records stay null)

**Out of scope for v1:** full change-history log (who changed what field from X to Y), row-level versioning. Those are a separate audit-log feature if ever needed.

---

### P2-31 · Professional product catalog + extended retail model

Extends the existing retail catalog to support **professional products** — items used by stylists during services (hair colour, peroxide, toners, bleach) that are tracked by volume rather than unit, and are not routinely sold to clients but may optionally be charged as an add-on.

**Schema changes to `retail_items`:**
- `kind`: `'retail' | 'professional'` (default `'retail'`)
- `unit_of_measure`: `'unit' | 'ml' | 'g' | 'oz'` (default `'unit'`; professional products typically `ml` or `g`)
- `available_at_checkout`: `boolean` (default `true` for retail, `false` for professional — controls whether the product appears in the checkout picker)
- `barcode`: `string | null` — UPC-A, EAN-13, or QR code value for scanner lookup

**Schema changes to `retail_stock_movements`:**
- `quantity` promoted from `integer` to `numeric(10,3)` — professional products are measured in fractional volumes (e.g., 45.5 ml of colour)

**UI — Retail page:**
- Add tabs: **Retail** (existing behaviour) · **Professional** (new)
- Professional tab: same list + edit pattern as retail, but shows unit of measure on each item and stock displayed with one decimal (e.g., "450.0 ml on hand")
- Both tabs share the same "Add item" form with `kind` pre-selected based on active tab
- `available_at_checkout` toggle on the professional item form — when on, the product appears in checkout as a chargeable add-on (e.g., "Additional colour — $X")

**Barcode field:**
- Added to the item edit form (both retail and professional) as an optional field
- Used by the scanner (P2-32) to look up products; not shown in the standard list view

**Migration:** add columns to `retail_items`; alter `retail_stock_movements.quantity` column type. Pre-populate `kind='retail'` and `unit_of_measure='unit'` on all existing rows; `available_at_checkout=true` on all existing retail rows.

---

### P2-32 · Barcode scanner — desktop

Staff scan product barcodes on desktop to speed up receiving, checkout, and inventory counting. Works with:
- **USB / Bluetooth handheld scanners** (most common in retail environments) — these behave as keyboards and inject the barcode string as fast keystroke input into whatever input is focused. A short debounce (50–100 ms) detects scan vs manual typing.
- **Browser camera scan** — for devices without a scanner; uses `@zxing/browser` to decode barcodes from the webcam feed.

**Shared `BarcodeInput` component:**
A reusable input that wraps a standard `<input type="text">` with:
- A scan icon button that opens a camera modal (uses `@zxing/browser`)
- Keystroke timing detection: if characters arrive faster than ~80 ms apart, treat as a scanner event and auto-submit on Enter (or on the scan's trailing carriage return)
- `onScan(barcode: string)` callback — caller decides what to do with the value
- Falls back gracefully to manual text entry when no barcode is available

**Integrated in three places:**

1. **Retail / Professional page — Receive stock:**
   - "Receive" button opens a receive dialog; `BarcodeInput` at the top looks up the product by `barcode` field; populates the item name and quantity field for staff to confirm; submits a `kind=receive` stock movement.

2. **CheckoutPanel — Add retail item:**
   - Replace (or augment) the existing dropdown picker with a `BarcodeInput`; scan or type barcode → product found → added to the sale as a `kind=retail` line item (or `kind=professional` if `available_at_checkout=true`).

3. **Inventory count (new flow on Retail page):**
   - "Start count" mode: staff scan products one by one; each scan adds a line to a count sheet with the product name and a quantity input; on "Submit count", creates `kind=adjust` movements for each item with a variance note "Physical count".

**Backend:**
- `GET /retail-items/by-barcode/{barcode}` — looks up an active retail or professional item by `barcode` field; returns the item or 404. Used by all three scanner flows.

---

### P2-33 · Professional product use recording (in-service)

When a stylist performs a colour service, they record which professional products they used and in what quantity. This creates accurate stock movements and can eventually inform product fee calculations per service.

**Workflow (desktop, from appointment detail):**
- On the appointment detail panel, a new "Products used" section appears for service items where the service category is colour
- Staff tap "+ Add product used" → picker showing professional products → enter quantity (in the product's UOM)
- Each entry creates a `kind=use_in_service` `RetailStockMovement` linked to the `appointment_item_id`
- Entries editable until the appointment is marked completed; read-only after

**Workflow (mobile, from PM-4 appointment detail):**
- Same "Products used" section on the mobile appointment detail
- `BarcodeInput` equivalent using the device camera (`expo-camera` with barcode scanning)
- Optimised for scanning during the service: scan product → enter ml used → save; designed for one-handed use

**Backend:**
- `POST /retail-items/{id}/use-in-service` — body: `{ appointment_item_id, quantity }`. Validates the item is `kind=professional`. Creates a signed stock movement (`quantity` negative, `kind=use_in_service`). Returns the updated on-hand count.
- `GET /appointments/{id}/products-used` — returns all `use_in_service` movements linked to items of this appointment.

**Stock movement kind addition:** add `use_in_service` to the `StockMovementKind` enum (migration required).

**Reporting:** in-service usage surfaced on the professional product detail page as a usage log (date, appointment, provider, quantity). Useful for auditing product consumption and informing reorder quantities.

**Out of scope v1:** automatic product fee recalculation based on actual usage (the current payroll fee uses `Service.default_cost` as a proxy rate — refining this to use actual scanned quantities is a future enhancement once usage data is established).

---

### P-CLEAN · ✅ Complete

All references to the previous salon software have been removed:
- Screenshots and UI reference docs deleted
- Backlog, README, ADRs, go-live checklist rewritten
- `providers.milano_code` renamed to `providers.provider_code` (migration `z1a2b3c4d5e6`)
- `clients.milano_code` renamed to `clients.legacy_id`
- ERM, reports annotations, CGI worked-examples doc cleaned
- UI label updated to "Provider code"

### P2-36 · Staff check-in / check-out · ✅ Complete

`StaffTimeEntry` model, `time_entries` router (`POST /time-entries`, `POST /time-entries/{id}/check-out`, `PATCH`, `DELETE`), dashboard clock widget, and `ManualTimeEntryDialog` for admin corrections. Payroll calculator uses summed `total_hours` when entries exist, falls back to scheduled hours otherwise.

### P2-38 · Booking inbox notification settings

Add a toggle in Settings → Email to enable/disable the staff notification email that fires when an inbound booking email is received. Currently controlled directly in the DB (`request_notifications_enabled`). Should be surfaced as a simple on/off switch so staff can manage it without a DB query.

### P2-39 · Booking inbox — show original email body

In the InboxDetailPanel, show the raw email body (`inbound_raw_body` already stored on the `AppointmentRequest` record) so staff can read what the client actually wrote before triaging.

### P2-40 · Booking inbox — AI draft response

Generate a suggested reply to the client based on the inbound email and the extracted intent. Staff can edit and send the draft directly from the detail panel via Resend. Closes the client communication loop without leaving the app.

### P2-37 · Annual / flat salary pay type for owner

When onboarding a staff member (or owner), provide an "Annual salary" pay type option in addition to Hourly and Commission. Entering an annual amount lets the system divide by the number of pay cycles per year to compute the per-period gross — no hours or commission calculation required.

**Why this matters:** The owner (JJ) currently draws a flat $6,000 per pay cycle. This is entered manually in the payroll review table each month. An annual salary config would pre-fill the amount automatically so it only needs adjustment if the draw changes.

**Implementation:**
- Add `annual_salary` to the `PayType` enum (migration required).
- When `pay_type = annual_salary`, `pay_amount` stores the annual amount. Payroll calculator divides by cycles per year (configurable per tenant, default 12 for monthly pay periods).
- Payroll report line: formatted as `Salary $X,XXX.XX` (no hours, no commission, no vacation pay unless vacation_pct > 0).
- Compensation tab in Staff Management: selecting "Annual salary" shows an "Annual amount ($)" input and a read-only "Per period ($)" display.
- Owner providers default vacation_pct = 0 when this pay type is selected (configurable).


### Docs · Update README with appointment book screenshots

Retake the appointment book screenshots to show the new sub-slot gridlines, gutter time labels at each granularity increment, and the Time Slot Indicator highlight. Replace the current screenshots in the GitHub README.

---

### DOC-1 · Quick-reference cards (go-live prerequisite)

Printable one-page PDF guides per role covering the day-one workflows. Designed for physical environments — laminated and kept at the front desk or in the staff room. Written in plain language, no jargon.

**Card A — Stylist daily workflow**
- Clock in and clock out
- View today's schedule
- Mark a client as arrived (tap the appointment → "Mark arrived")
- Viewing a client card: colour notes, service history, special instructions
- What to do if you need to add a service mid-appointment

**Card B — Front desk / checkout**
- Processing a checkout: select payment method, enter amount, handle cashback/change
- Split payment across two methods
- Applying a discount or promotion
- Editing a payment after checkout (wrong card type, bad split)
- Sending a receipt by email

**Card C — Admin daily**
- Converting a booking request to a confirmed appointment
- Running end-of-day cash till reconciliation
- Adding a petty cash entry
- Running the monthly sales report
- Running payroll for the period

**Format:** Each card is a single A4 / Letter page. Minimal prose, step-numbered, with UI element names in **bold** matching the app exactly. Produced as a PDF in `docs/user-guides/`. No dev work required — pure documentation.

**Owner:** Freddy writes first draft; Claude Code formats and edits.

---

### DOC-2 · External docs site

A hosted documentation site covering the full app for staff onboarding and ongoing reference. Linked from the app's help menu (once DOC-3 ships) and from the README.

**Recommended platform:** Notion (zero infrastructure, easy to update without code deploys, shareable link). Alternative: GitBook or a static site in `docs/site/` if ownership and version control matter more than edit speed.

**Structure:**

| Section | Topics |
|---|---|
| Getting started | Logging in, the app shell, your role |
| Appointment book | Grid navigation, status flow, adding/removing services, drag-and-drop |
| Booking requests | Guest requests, reviewing, converting, confirmation emails |
| Clients | Profile, colour notes, history, merging duplicates |
| Checkout & payments | Checkout flow, split payment, cashback, promotions, editing a sale |
| Retail | Catalog, stock movements, checkout integration |
| Reports | Sales report, transaction report, cash till, payroll detail |
| Payroll | Running payroll, time entries, commission tiers, sending to Paytrak |
| Staff management | Provider profiles, schedules, compensation settings |
| Settings | Branding, operating hours, payment methods, email, import |

**Writing approach:** Each page is task-oriented ("How to process a group checkout") not reference-oriented ("The Checkout Panel"). Screenshots from the live app. Updated by Freddy or Claude Code when features change.

**Phase 1 of docs site:** Appointment book + Checkout + Clients (the three daily-use surfaces). Remaining sections added progressively.

**Depends on:** DOC-1 (cards establish the vocabulary and task list for the site).

---

### DOC-3 · In-app contextual help

Contextual help surfaced inside the app itself, so staff don't have to leave the flow to look something up.

**Phase 1 — Tooltip layer**

Add `?` icon buttons to concepts that are non-obvious or frequently misunderstood:
- **Cashback** — "Cash returned to the client from the till. The amount you charge the client goes toward the bill; cashback is the change. Tip out separately — it doesn't touch the salon's books."
- **Business Reimbursed** — "The salon is absorbing this discount. Your commission and product fee are calculated on the full pre-discount price, not what the client paid."
- **Commission tier** — "Your commission rate steps up once net service revenue passes the threshold for the period."
- **Product fee** — "The cost of colour product deducted from your gross before commission is applied."
- **Processing offset / duration** — "The gap between applying colour and rinsing. The appointment book keeps this block free so you can take another client."

Implementation: a `<HelpTip>` component wrapping shadcn `Tooltip` with a `?` icon. No backend required. Drop it alongside existing labels where confusion is most likely.

**Phase 2 — Help page (`/help`)**

A lightweight page in the app that:
- Links to the external docs site (DOC-2) for full guides
- Lists the printable quick-reference cards (DOC-1) as downloadable PDFs
- Surfaces the 5–10 most common "how do I…" questions as inline accordions

**Phase 3 — Contextual help panel (future)**

A slide-over panel triggered from any page that surfaces the relevant docs section for the current route. Requires DOC-2 to have a documented API or embed-friendly URLs. Low priority until multi-tenant onboarding volume justifies the investment.

**Phasing:** DOC-1 → DOC-2 (Phase 1) → DOC-3 Phase 1 (tooltips) → DOC-3 Phase 2 (help page) → DOC-3 Phase 3 (panel, if ever).

---

## Phase 3 — AI / Briefing Engine

### P3-1 · Briefing Engine — core infrastructure · ✅ Bootstrapped (partial)

Foundation built alongside P3-2: `backend/briefing_engine/config.py` (`BriefingConfig` dataclass), `synthesizer.py` (Claude API call), `runner.py` (orchestrator), `delivery/file.py` (file channel), `app/routers/briefings.py` (`POST /run-briefing` endpoint), `scripts/run_briefing.py` (CLI trigger).

**Remaining for P3-3 through P3-6:**

`sources/web_search.py`
- Uses Claude API with `web_search_20250305` tool type
- Model: `claude-sonnet-4-6` (web search only available on Sonnet+)
- Called for `market`, `competitors`, `ai_features`, `industry` topic domains
- Returns a list of `SourceChunk(title, url, snippet, retrieved_at)` objects
- Query strategy: one search per topic domain, results deduplicated by URL
- Max results per query: 5; total context passed to synthesizer capped at ~4000 tokens

`sources/client_db.py`
- Called for `clients`, `appointments` topic domains
- Queries for the target audience's scope:
  - `stylist` audience: appointments for today + next 7 days for that provider, joined with client colour notes and last-visit data
  - `salon_owner` audience: all providers' appointments for today, no-show/cancellation counts for the past 30 days
  - `client` audience: that client's next appointment, loyalty point balance (future)
- Returns structured Python dicts (not ORM objects) so they can be serialised into the Jinja2 context
- Never returns PII for the wrong audience — enforces audience scoping at the query level

`sources/analytics.py`
- Called for `analytics` topic domain (salon owner audience primarily)
- Queries:
  - Revenue by week: rolling 8-week total and per-provider breakdown
  - Booking fill rate: appointments booked / available slots per provider per week
  - Retail vs service split as % of revenue (rolling 4 weeks)
  - Top 5 services by revenue (rolling 4 weeks)
- All queries use `completed_at` on `Sale` and `appointment_date` on `Appointment`
- Returns summary statistics only — no raw PII

`delivery/email.py`
- Reuses `app.email.send_email` (SMTP or Resend path, whichever is configured for the tenant)
- Wraps the synthesized markdown in a minimal HTML wrapper (no branded layout — briefings are internal/operational)
- Subject line pattern: `"SalonOS Briefing — {audience} — {date}"`
- `recipient_ids` maps to staff email addresses looked up from `User.email`

`delivery/in_app.py`
- Writes a `BriefingRecord` row (`tenant_id`, `audience`, `content_markdown`, `created_at`, `is_read`)
- New table `briefing_records` — migration required
- Frontend reads via `GET /briefings/latest?audience=stylist` (returns most recent unread, or most recent overall)
- In-app rendering: markdown → HTML via the existing Tiptap display pattern

`templates/`
- One Jinja2 `.md.j2` file per audience (already listed in CLAUDE.md)
- Variables available in all templates: `{{ date }}`, `{{ salon_name }}`, `{{ audience }}`
- `stylist.md.j2` also receives: `{{ provider_name }}`, `{{ appointments }}` (list), `{{ colour_notes }}` (dict keyed by client_id)
- `salon_owner.md.j2` also receives: `{{ revenue_summary }}`, `{{ booking_fill_rates }}`, `{{ top_services }}`
- `developer.md.j2` and `claude_code.md.j2` receive: `{{ web_results }}` (list of SourceChunks)
- Prompt templates follow the base synthesizer prompt in CLAUDE.md

---

### P3-2 · Briefing Engine — `claude_code` audience · ✅ Complete

Runs at 7 AM daily via `scripts/run_briefing.py` (trigger: `POST /run-briefing` + `INTERNAL_SECRET`). Writes to `.claude/rules/market-intelligence.md`, which Claude Code auto-loads at session start. Topics: `market`, `ai_features`, `industry`, `regulation`. Schedule: `0 7 * * *` America/Toronto via Cloud Scheduler.

**Depends on:** P3-1.

---

### P3-3 · Briefing Engine — `developer` audience (Freddy's daily briefing)

Freddy's 8 AM daily email covering salon software market moves, AI feature launches, pricing changes, and regulatory developments relevant to SalonOS.

**Topics:** `market`, `competitors`, `ai_features`, `industry`
**Delivery:** `email`
**Schedule:** `0 8 * * *` America/Toronto.

**Depends on:** P3-1.

**Backlog note:** Add a tenant-level SMTP/Resend setting for briefing email delivery — currently the sender domain (`salonlyol.ca`) must be verified in Resend before production sends can use a branded from address. Consider surfacing this in Settings → Email alongside the existing SMTP config, or as a dedicated Briefing delivery setting.

---

### P3-4 · Briefing Engine — `salon_owner` audience

Daily in-app briefing for JJ on opening the app. Revenue trends, staff performance, booking patterns, and any competitor intel surfaced by the market sources.

**Example output:** "Tuesday booking rate down 23% vs last month" · "Gumi has 3 open slots this week — consider a promotion"

**Topics:** `clients`, `appointments`, `analytics`, `market`
**Delivery:** `in_app` (dashboard widget)
**Schedule:** `event_triggered` — generated fresh each morning, displayed on dashboard load.

**Depends on:** P3-1, real appointment and sales data in production tenant.

---

### P3-5 · Briefing Engine — `stylist` audience

Per-stylist daily briefing surfaced at login or dashboard load. Covers today's client list with colour formula notes, special instructions, upcoming bookings, and any flagged no-show history.

**Example output:** "Your 2pm — Maria — balayage 8 weeks ago, Wella 9/0, sensitive scalp. Her last visit ran 15 min over — book buffer if possible."

**Topics:** `clients`, `appointments`
**Delivery:** `in_app` (dashboard, provider-scoped)
**Schedule:** `event_triggered` — generated at login for that provider's day.

**Depends on:** P3-1, colour formula / service notes data populated for real clients.

---

### P3-6 · Briefing Engine — `client` audience

Client-facing briefing delivered before their appointment: upcoming service reminder, formula preview if applicable, loyalty status, and a personalised recommendation (e.g. toner touch-up worth adding).

**Example output:** "You're due for a toner — worth adding before your cut. Your last visit was 7 weeks ago."

**Topics:** `appointments`, `products`, `loyalty`
**Delivery:** `email` or `sms` (pre-appointment, configurable lead time)
**Schedule:** `event_triggered` — triggered by appointment reminder job.

**Depends on:** P3-1, P2-3 (appointment reminders, already built — extend delivery).

---

### P3-7 · Smart booking — inbound email ingestion · ✅ Complete

Resend inbound webhook live at `POST /webhooks/email/inbound`. Gmail routing rule forwards copies of `info@salonlyol.ca` to `info@inbound.roux.salon` (Resend). Haiku intent extractor parses plain-language requests into structured `AppointmentRequest` rows with `source = 'email'`. Booking Inbox page (`/inbox`) surfaces email-sourced requests for staff triage. Confidence score and source badge shown per request.

---

### P3-8 · Smart booking — LLM explanation rendering (optional)

Replace template-built rationale strings in `explainer.py` with a Haiku call that narrates the recommendation in natural language. The scorer's component breakdown (idle penalty, preference match, packing bonus) is passed as structured context so the model narrates rather than fabricates.

**LLM use:** `claude-haiku-4-5-20251001`, max_tokens ~200, ~$0.0005/call. Only fires when a recommendation is surfaced — not in the scoring hot path.

**Note:** The template explainer already produces usable rationale strings. Only build this if the templated text feels stiff in real use at Salon Lyol. Evaluate after P3-7 is live.

**Depends on:** Scheduling engine (built), P3-7 (inbound email, to validate that rationale quality matters at volume).

### P2-27b · Self-service password change

Logged-in users can change their own password without going through the forgot-password flow.

**Backend:** `POST /auth/change-password` (requires JWT). Body: `{ current_password, new_password }`. Verify current password with `verify_password` before hashing and saving the new one. Return 400 with a clear message if current password is wrong.

**Frontend:** A "Change password" section at the bottom of the user's own profile area (or Settings → Account if that exists). Three fields: current password, new password, confirm new password. Client-side validation that new + confirm match before submitting.

**Scope:** Only lets a user change their own password. Admin resetting another user's password is already handled in UsersPage.

### P3-9 · Email bounce handling

When Resend fires an `email.bounced` or `email.complained` webhook event for an outbound email (confirmation, reminder, cancellation), mark the recipient client's email address as invalid so staff are alerted rather than silently losing messages.

**What to build:**

- Expand `POST /webhooks/email/inbound` (or a sibling route) to handle `email.bounced` and `email.complained` event types
- On bounce/complaint: look up the `to` address against `clients.email`; if matched, set a new `email_status` column (`valid` | `bounced` | `complained`) on the `clients` table
- Surface `email_status` in the client card slide-over: show a warning badge ("Email address may be invalid — last send bounced") when status is not `valid`
- Do not suppress future sends automatically — let staff decide (could be a typo they can fix)

**What to skip:** open/click tracking — not actionable enough to justify the complexity.

**Resend event shape:** `email.bounced` and `email.complained` share the same svix signature validation already in place. The `data.to` field is an array of recipient addresses.

**Migration:** add `email_status VARCHAR(20) NOT NULL DEFAULT 'valid'` to `clients`.

**Depends on:** P3-7 webhook infrastructure (shared signature validation, same endpoint pattern).

---

## Phase 3 — Platform & Integrations

### P3-10 · Booking inbox — AI-assisted email triage and reply

`info@salonlyol.ca` is the salon's general address. Clients email it for booking requests but also for general questions, product inquiries, and other issues. Staff currently monitor Gmail separately — this eliminates that swivel chair by bringing all inbound email into SalonOS with AI context on every message.

#### The current bug this also fixes

The P3-7 webhook stores every inbound email as an `AppointmentRequest`, even "thanks for the great cut!" messages. Non-booking emails should not create appointment requests. This item fixes that by making appointment request creation conditional on intent classification.

---

#### Data model

New table: **`inbound_emails`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `message_id` | TEXT | RFC 2822 Message-ID (for threading) |
| `from_address` | TEXT | |
| `from_name` | TEXT nullable | Display name if present |
| `subject` | TEXT | |
| `body_text` | TEXT | Plain text body |
| `body_html` | TEXT nullable | HTML body if present |
| `received_at` | TIMESTAMPTZ | |
| `client_id` | UUID nullable FK | Matched client if found |
| `intent` | TEXT | `booking_request` \| `general_inquiry` \| `supplier` \| `unclassified` |
| `intent_confidence` | FLOAT | 0–1 |
| `request_id` | UUID nullable FK | Set if a booking AppointmentRequest was created |
| `reply_sent_at` | TIMESTAMPTZ nullable | When staff sent a reply |
| `is_read` | BOOL | Default false |

The existing `AppointmentRequest.inbound_message_id` and `inbound_raw_body` columns (already in schema) link back to the source email.

---

#### Webhook changes

Refactor `POST /webhooks/email/inbound`:

1. **Always** persist the raw email as an `InboundEmail` row first — before any classification.
2. Run the Haiku intent classifier. It now returns one of four intents: `booking_request`, `general_inquiry`, `supplier`, `unclassified`.
3. **Only if `booking_request`**: run the existing scheduling engine and create an `AppointmentRequest`. Link via `InboundEmail.request_id`.
4. Send staff notification regardless of intent (so staff sees all emails in the app).

**LLM classification prompt** (single Haiku call, <$0.001):
```
Classify this email to a hair salon. Return JSON:
{"intent": "booking_request"|"general_inquiry"|"supplier"|"unclassified", "confidence": 0.0–1.0}
booking_request: client wants to book, reschedule, or cancel an appointment.
general_inquiry: question about services, prices, hours, products, etc.
supplier: vendor, product rep, or business solicitation.
unclassified: anything else.
Email subject: {subject}
Email body: {body[:500]}
```

---

#### Backend endpoints

- `GET /inbound-emails` — paginated list (50/page), ordered newest-first. Query params: `intent`, `is_read`, `client_id`. Returns: id, from_address, from_name, subject, received_at, intent, intent_confidence, request_id, is_read, client_id.
- `GET /inbound-emails/{id}` — full record including body_text and body_html.
- `PATCH /inbound-emails/{id}` — mark read (`is_read: true`).
- `POST /inbound-emails/{id}/reply` — send a reply from the salon's address. Body: `{ body_html, body_text }`. Sets `In-Reply-To` and `References` from `message_id`. Records `reply_sent_at`.
- `POST /inbound-emails/{id}/ai-reply` — generate a draft reply using Sonnet. Returns `{ subject, body_html, body_text }` — not sent automatically, staff edits and approves via the reply endpoint.

**AI reply prompt (Sonnet, ~$0.003/call):**
```
You are drafting a reply on behalf of {salon_name} to a client email.

Client: {client_name or "a client"} ({from_address})
{if client_id: "Client history: {last_3_visits}, {formula_notes}"}
{if intent == booking_request and recommendations: "Available slots: {top_2_recommendations}"}

Original email:
Subject: {subject}
{body_text[:1000]}

Write a warm, professional reply. If it's a booking request and slots are available,
offer the top option and ask the client to confirm. If it's a question, answer it
concisely using the salon's known details. Do not confirm bookings — offer options only.
Salon info: {address}, {phone}, {hours_summary}.
```

---

#### Frontend: Inbox page (`/inbox`)

**List view** — envelope icon in AppShell nav, badge with unread count.

Each row: sender name/email, subject, received time, intent badge (`Booking request` / `General inquiry` / `Supplier` / `Unclassified`), unread dot.

**Detail slide-over** — opens on click:
- Full email (prefer HTML render in sandboxed iframe, fallback to text)
- If `intent == booking_request` and `request_id` set: link to the appointment request ("View booking request →")
- If `intent == booking_request` and no `request_id`: "Classify as booking" button (manual override)
- Client card snippet if matched (name, last visit, upcoming appointments)
- **Reply section** at bottom:
  - "Generate AI reply" button → calls `/ai-reply`, loads draft into editor
  - Rich text editor (Tiptap, same as confirmation email editor already in the app)
  - Send button → calls `/reply`, marks read, shows confirmation

**Unread badge** in AppShell nav — same pattern as the existing new-requests badge.

---

#### Phasing

Build in this order:
1. `inbound_emails` table + migration
2. Webhook refactor (persist all, classify intent, conditional request creation)
3. Backend list/detail/read endpoints
4. Inbox page — list view + detail slide-over (read-only)
5. AI reply generation + reply send endpoint
6. Reply UI in slide-over

Steps 1–4 can ship as a unit; 5–6 are additive.

**Depends on:** P3-7 webhook (built), `send_email` with `reply_to_message_id` (built), Resend outbound configured (live).

---

### P3-11 · Public REST API (tenant-scoped)

Tenants can access their own data via a documented REST API so they can integrate SalonOS with other software, AI tools, or export pipelines without logging into the UI.

**Scope:**

- API key management: `POST /api-keys` (create), `GET /api-keys` (list), `DELETE /api-keys/{id}` (revoke). Keys are tenant-scoped, hashed on storage (same pattern as password reset tokens). Shown once on creation.
- Auth: `Authorization: Bearer <api_key>` header. A new `api_key_auth` FastAPI dependency resolves the tenant from the key.
- Read-only endpoints (Phase 1 of the API):
  - `GET /api/v1/clients` — paginated, filterable by name/email
  - `GET /api/v1/appointments` — paginated, filterable by date range and provider
  - `GET /api/v1/sales` — paginated, filterable by date range
  - `GET /api/v1/providers` — list of active providers
  - `GET /api/v1/services` — list of active services
- OpenAPI spec auto-generated (FastAPI default). Add a public docs page at `/api/docs`.
- Rate limiting: 1000 req/hour per key (use a simple Redis counter or a header-based honour system for MVP).

**Why:** Enables Freddy to pipe data to Claude, spreadsheets, or other tools without screen-scraping. Positions SalonOS as an open platform for future integrations (booking widgets, loyalty apps, AI agents).

**Phase 2 of the API** (separate backlog item): write endpoints (create appointment, update client, record sale), webhooks (appointment created/updated/completed, sale completed).

---

### P3-12 · Data export

Salon owners can download their data as CSV or JSON for backup, migration, or external analysis.

**What to build:**

- `POST /export/request` — queues an export job (background task). Body: `{ format: "csv"|"json", datasets: ["clients", "appointments", "sales", "retail"] }`. Returns a job ID.
- `GET /export/{job_id}` — poll status (`pending` | `ready` | `expired`). When ready, returns a signed download URL (GCS signed URL, valid 1 hour).
- Background task: runs the export, writes to GCS, marks job ready.
- Frontend: **Export** section in Settings → Data (new tab). Checkbox list of datasets, format toggle, "Request export" button, download link when ready.
- Exports include all tenant-scoped data only. No cross-tenant leakage.
- Files expire after 24 hours.

**Why:** Clients who generate their own data should be able to take it with them. Also useful for Freddy to pipe into analysis tools or the Briefing Engine.

**Depends on:** GCS access (already used for branding assets).

---

### P3-13 · Briefing Engine — tenant-facing dispatcher

The `developer` and `claude_code` briefings use a simple Cloud Scheduler → `POST /internal/run-briefing` pattern (one job per briefing, configs in code). This doesn't scale to multi-tenant because adding a new salon would require code changes and new scheduler jobs per tenant.

**What to build:**

- **`tenant_briefing_configs` table** — DB-backed equivalent of `BriefingConfig`. Columns: `id`, `tenant_id`, `briefing_id`, `audience`, `topic_domains` (JSONB), `delivery_channels` (JSONB), `schedule_cron`, `output_format`, `active`, `last_run_at`, `next_run_at`.
- **Dispatcher endpoint** — `POST /internal/dispatch-briefings`, protected by `X-Internal-Secret`. Queries for all active configs where `next_run_at <= NOW()`, runs each, updates `last_run_at` and `next_run_at`. Same pattern as `POST /internal/dispatch-reminders`.
- **Single Cloud Scheduler job** — fires every 15 minutes, always, regardless of tenant count. `POST /internal/dispatch-briefings`.
- **Admin API** — `GET/POST/PATCH/DELETE /admin/briefing-configs` to manage configs per tenant. Seeded with `salon_owner` + `stylist` defaults on tenant creation.
- **Retire per-briefing jobs** — once this lands, the `developer-market-daily` and `claude-code-market-daily` Cloud Scheduler jobs can be migrated or retired.

**Scope boundary:** `developer` and `claude_code` audiences are Freddy's dev tools, not tenant features — they can stay as manual/scripted or keep their own scheduler jobs indefinitely.

**Depends on:** P3-4 salon_owner audience, P3-5 stylist audience (so there's something worth dispatching at scale).

---

### P3-14 · QZ Tray signing — move to backend (pre-SaaS hardening)

**Current state (single-tenant):** The QZ Tray private key is injected into the frontend bundle at build time via a GitHub secret (`VITE_QZ_PRIVATE_KEY`). The certificate is hardcoded in `frontend/src/lib/qzTray.ts`. This works for Salon Lyol but does not scale to multi-tenant SaaS — the private key would be extractable from any tenant's browser bundle, and every new PC would need the certificate imported manually.

**What to build:**

1. **Platform RSA keypair** — generate a proper SalonOS platform keypair (replacing the QZ Tray demo cert). Store the private key in Secret Manager. The public certificate is distributed once during onboarding.

2. **Backend signing endpoint** — `POST /sales/{id}/sign-print` (or a generic `POST /qz/sign`). Accepts the `toSign` string from QZ Tray's signature challenge, signs it with the platform private key from Secret Manager, returns the base64 signature. Requires staff auth. Short-lived (the signature is only valid for the QZ Tray session).

3. **Frontend change** — replace `signData()` in `qzTray.ts` with a fetch to `POST /qz/sign`. Remove `VITE_QZ_PRIVATE_KEY` from the build entirely. The private key never touches the browser.

4. **Onboarding artifact** — a downloadable `salonos-certificate.crt` (the platform public cert) available in Settings → Printer. Staff import it into QZ Tray Site Manager once per PC. Same file for every tenant.

5. **Remove build-time injection** — strip `VITE_QZ_PRIVATE_KEY` from `frontend/Dockerfile`, `.github/workflows/deploy.yml`, and the GitHub secret.

**Signing flow (post-migration):**
```
Browser → QZ Tray challenge (toSign string)
Browser → POST /qz/sign { toSign } → Backend (Secret Manager) → { signature }
Browser → QZ Tray (signature) → prints ✓
```

**Why this matters for SaaS:** The platform cert is the same for all tenants — one import step per PC during onboarding, regardless of how many salons are on the platform. The private key is never in the browser.

**Depends on:** Multi-tenant onboarding flow. Low urgency until second tenant is onboarded.

---

### P3-15 · Tenant-configurable acknowledgements on public booking form · In progress

The legacy salon website's booking form required clients to acknowledge a waiver and a cancellation/refunds policy before submitting. The current SalonOS `RequestAppointmentDialog` has no acknowledgements at all — clients can submit a request without agreeing to any policy.

**What to build:**

1. **`tenant_acknowledgements` table**: id, tenant_id, title, body_text, link_url, link_text, is_required, display_order, is_active, created_at, updated_at.
2. **Settings → Policies admin page** to create / edit / reorder / disable acknowledgements per tenant.
3. **Public endpoint** `GET /public/tenants/{slug}/acknowledgements` returning active ones in display order.
4. **Booking dialog** fetches and renders acknowledgements between Special Notes and Submit; required ones show a red asterisk; submit blocked until all required are agreed.
5. **`AppointmentRequest.acknowledgements_agreed` JSON column** records `{acknowledgement_id: true}` per submission.
6. **Migration seeds Salon Lyol's two existing acknowledgements** (Waiver and Release, Cancellations and Refunds) matching the legacy wording.

**Out of scope:** per-client history (see P3-16).

---

### P3-16 · Per-client acknowledgement history with versioning

Once tenant acknowledgements (P3-15) are configurable, the wording or policy may change over time. For legal compliance, the salon needs to be able to prove "client X agreed to version Y of acknowledgement Z on date D" if a dispute arises.

**What to build:**

1. **Version the acknowledgement body**: add `version` int + `body_text_at_version` snapshot when text changes (or treat each text change as a new row, keeping the old one immutable).
2. **`client_acknowledgements` junction table**: id, tenant_id, client_id, acknowledgement_id, version_acknowledged, acknowledged_at, source (`booking_form` | `staff_entered` | `existing_client`).
3. **Booking form** records the version the client saw at submission time.
4. **Re-prompt logic**: when a returning client requests a booking, check the latest acknowledgement versions against what they've previously agreed to. If a required acknowledgement has been updated since their last agreement, re-prompt for that one.
5. **Client card view**: show acknowledgement history in the Client Notes / Profile tab so staff can see what was signed when.

**Depends on:** P3-15.

---

### P3-17 · Inbox/Requests bulk select + delete; show inbound email body

Today the Requests/Inbox page only lets you action one request at a time (Convert / Decline). Staff need to triage faster — especially for spam, payment notifications, and other non-booking emails that land in the inbox.

**What to build:**

1. **Checkbox per request row** plus a "Select all" master checkbox in the header. Selecting any row reveals a top action bar: "Delete (N)".
2. **Bulk delete endpoint** `POST /appointment-requests/bulk-delete { ids: [...] }` — admin-only. Soft-delete preferred (set `status='declined'` with `staff_notes='Bulk deleted by {user}'`) so audit trail is preserved.
3. **Inline preview of the inbound email body** in the request detail panel. Currently `inbound_raw_body` is collapsed; add an "Expand original email" toggle that renders the full body in monospace with a syntax-highlighted diff between the labels and values (for form emails) or raw text (for free-form). Source-of-truth viewing without leaving the app.
4. **Filter** at the top: hide payment-receipt and other auto-emails by sender pattern, with an opt-in toggle to show them.

**Why:** with smart booking now generating recommendations on inbound emails, the inbox accumulates a long tail of non-booking emails that's currently very tedious to clear.

---

### P3-18 · Drafted confirmation reply on conversion (staff and client option)

When a staff member converts a request → appointment today, the client gets the standard confirmation email automatically. But for email-sourced requests where the client wrote a freeform message, a more personal "Hi {first_name}, confirmed for {date} at {time} with {provider} — see you then!" reply is often warranted — *as a reply to their original email thread*, not a generic confirmation.

**What to build:**

1. On the Convert dialog, after "Confirm appointment" succeeds, present a follow-up modal: "Send a personal reply to the client?" with a pre-drafted reply body. Staff can edit and send, or skip.
2. The draft is generated by Haiku (same model as inbox draft-reply) using the original email + the confirmed appointment details. Tone matches the client's original message register.
3. Reply uses `Reply-To` headers so it threads correctly in the client's email client (References + In-Reply-To from the inbound email's message ID).
4. **Optional client-side preference**: in `RequestAppointmentDialog`, add a "Send me a personal reply when confirmed" checkbox (default off). When checked, conversion triggers the drafted reply automatically without staff review.
5. The personal reply is recorded on the request (`reply_sent_at`, `reply_body`) so it's visible in the request's history.

**Depends on:** existing `/appointment-requests/{id}/draft-reply` endpoint (already shipped as part of P3-10).

---

### P-DEV-1 · Dev data synthesizer (scripts/synthesize_dev_data.py)

Stand up a populated dev environment without ever touching prod data. Generates realistic synthetic clients, appointments, sales, time entries, schedules — keyed by a `--seed` for reproducibility and a `--days-back / --days-forward` window so the dev calendar stays alive over time instead of rotting into the past.

**Why:** prod→dev sync (even with anonymization) is the wrong long-term answer:

1. Small population (hundreds of clients) defeats anonymization — schedule + service + provider patterns re-identify clients independently of name/email scrubbing.
2. The moment a second tenant comes on board, "we process customer data in dev" kills B2B security reviews.
3. Sync infrastructure rots; synthesis is a single Python script.

**CLI surface (small on purpose):**

```
uv run --project backend python scripts/synthesize_dev_data.py \
  [--seed 42] \
  [--days-back 60] \
  [--days-forward 60] \
  [--wipe-all]
```

**Behaviour:**

- **Reproducibility:** same `--seed` produces the same dataset (Faker + random both seeded).
- **Date range relative to today:** appointments span `today - days_back` to `today + days_forward`. Re-running rolls the window forward so the dev calendar never goes stale.
- **Volume hardcoded:** ~150 clients, ~6 providers matching the real category mix, ~3000 appointments across the window, realistic sale + payment distributions. Don't expose flags for these; pick once and move on.
- **Idempotency by default:** synthetic rows are tagged with `is_synthetic = true` (or equivalent). Re-running wipes only synthetic rows so any real user/client you created manually for testing survives.
- **`--wipe-all` flag:** nuke everything including your own user — for full fresh state.

**Tables touched:**
- `clients` — Faker names/emails/phones, locale=`en_CA` and `fr_CA` mix, occasional French pronouns
- `service_categories` + `services` — fixed list matching Salon Lyol's actual catalogue shape (Type 1/2/2+ Haircut, Camo Colour, Full Balayage, Root Touch-Up, Blowdry, etc.) but NOT real prices/fees — picked to look plausible
- `providers` — 6 fake stylists with realistic schedules (Tue–Sat shifts)
- `provider_schedules` — Mon–Sun rows covering the window
- `appointments` + `appointment_items` — realistic durations, service mixes, occasional no-shows / late cancellations
- `sales` + `sale_items` + `payments` — realistic payment splits (cash/debit/visa mix, occasional discount, occasional BR flag)
- `staff_time_entries` — clock-in/out matching shifts, with a few manual corrections
- A few `client_colour_notes` and `clients.special_instructions` — generated from a small template list, not copied from anything real

**What the synthesizer does NOT do:**
- Inbound emails / appointment requests — out of scope v1. When you need to test inbound flow, paste a real form email into the webhook by hand.
- Acknowledgements history, briefing engine outputs, recommendation log — generated on demand by the feature itself, no need to seed.

**Bug-repro pattern when you actually need real-shape data:** for a one-off prod bug, copy the single affected `inbound_raw_body` / sale / appointment row into a test fixture by hand. Twice a year, takes 10 min, doesn't require infrastructure.

**Phase:** post-parallel-run (don't build this weekend). When dev needs to look populated for testing or demo, run the synthesizer instead of considering prod sync.

---

### P3-19 · Client-facing service catalogue — visibility flag + dropdown overflow

Two related problems with the service picker in the public booking dialog (`RequestAppointmentDialog`):

1. **Internal-only services are shown to clients.** Items like "Business Reimbursement", "Redo", "Additional styling", "Fringe/Bang Cut" (add-on), "Heat Tool Finish" (add-on), "Treatments 1", "Olaplex" (often an add-on) appear in the dropdown. Clients should only see top-level bookable services (Type 1/2/2+ Haircut, Camo Colour, Full Balayage, Root Touch-Up, Color Full Color, Blowdry, Special Updo, etc.). Add-ons and internal services should be staff-only.

2. **Dropdown overflow / horizontal truncation.** Long names like "Business Reimbursement", "MK Hair Botox (with home care)", "MK Hair Botox (without...)" run off the right edge of the popover and get clipped.

**What to build:**

1. **`Service.is_client_bookable` boolean column** (default `true` for top-level services, `false` for add-ons / internal). Migration backfills based on existing service naming.
2. **Settings → Services UI** gets a "Client-bookable" toggle per service. Staff can curate which appear on the public form.
3. **Public booking form** filters services by `is_client_bookable = true`.
4. **Staff-side flows** (ConvertRequestPanel, BookingForm) continue to show everything — internal services are still bookable by staff.
5. **Dropdown overflow fix**: switch the service `SelectContent` to allow text wrapping or truncate with ellipsis + full name on hover. Increase the popover width to fit common service names.

**Why:** clients are picking services they shouldn't (creating noise in the inbox and confusion at confirmation time), and the truncated display makes some services look broken.

---

## Parallel Run Reconciliation Tasks

### PR-1 · Sales reconciliation — WALK_IN retail gap · ✅ Complete

Fixed in `legacy_import.py` (commit `003685e`): WALK_IN receipts are now imported as completed sales linked to a "Walk-In" placeholder client, with no appointment record. Import re-run confirmed by Freddy (2026-05-09).

### PR-2 · Payroll reconciliation · ✅ Complete

Figures reconcile between SalonOS and Milano for the parallel run period. Confirmed by Freddy (2026-05-09). Depends on PR-1 (complete).

---

## Payment Processor Reconciliation

End-of-day reconciliation between SalonOS-recorded payments and processor settlement data. Supports two operating models that coexist within the same tenant:

**Airgapped model (Salon Lyol today):** A physical terminal (TD Merchant / Clover) handles all card processing. Staff record payment type in SalonOS checkout manually — VISA, MASTERCARD, DEBIT, CASH, etc. SalonOS never touches card data. At end of day, the owner reads batch totals off the terminal paper printout and enters them into SalonOS. SalonOS compares against its own totals and surfaces variances. Cash is counted separately (P2-8 already handles this).

**Integrated model (ecommerce, future in-person):** SalonOS initiates or captures the payment directly (Stripe for online orders). The payment intent ID is stored and reconciliation against Stripe settlements is automatic — no manual entry needed.

**v1 priority:** Batch-level entry from the paper printout — same concept as the cash till, just for card methods. This replaces the manual spreadsheet/paper comparison the owner does today.

**v2:** Transaction-level matching via Clover API (once Salon Lyol migrates from TD) and Stripe API (for ecommerce). Enables individual transaction matching and automatic chargeback identification — not needed to replace the current workflow.

---

### PROC-1 · Processor account configuration

Tenant configures which payment processors they use and how SalonOS payment methods map to them.

**Settings → Payment Processors tab (new):**
- List of processor accounts, each with:
  - Processor type: `Clover` | `Stripe` | `TD Merchant` | `Square` | `Other`
  - Label (e.g., "Clover — in-person", "Stripe — online store")
  - Merchant / account ID (for reference; required for API sync in v2)
  - Operating model: `airgapped` | `integrated`
  - Active toggle
- Payment method mapping: which SalonOS payment methods this processor covers (e.g., VISA + MASTERCARD + DEBIT → Clover; cash is not mapped to any processor)

**Data model:**
- `ProcessorAccount`: `id`, `tenant_id`, `processor` (enum), `label`, `merchant_id`, `model` (`airgapped` | `integrated`), `is_active`
- `ProcessorPaymentMethodMap`: `processor_account_id`, `payment_method_id`

---

### PROC-2 · End-of-day batch entry (airgapped model — v1)

Staff enters the totals from the terminal's paper batch printout. SalonOS compares against its own recorded totals and shows variances. Same concept as the cash till (P2-8).

**UI — Reconciliation page (`/reports/processor-reconciliation`):**
- Date selector (defaults to today) + processor account selector
- For the selected date and processor, show a simple entry form:

| Card type | Terminal total (enter) | SalonOS total (computed) | Variance |
|-----------|----------------------|--------------------------|----------|
| VISA      | $___                 | $240.00                  | —        |
| Mastercard| $___                 | $185.50                  | —        |
| Debit     | $___                 | $310.25                  | —        |
| **Total** |                      | $735.75                  |          |

- Optional: **Fees** field — total merchant fees from the paper report (batch fee or estimated from rate)
- "Save" stores the entry; variance cells populate and highlight non-zero values in amber/red
- Net revenue = SalonOS card total − fees (shown once fees are entered)

**Data model:**
- `ProcessorBatchEntry`: `id`, `tenant_id`, `processor_account_id`, `entry_date`, `entered_by_user_id`, `total_fee_amount` (nullable), `notes`, `created_at`
- `ProcessorBatchEntryLine`: `id`, `batch_entry_id`, `payment_method_id`, `terminal_amount`, `salonos_amount` (snapshot at entry time), `variance`

**History:** last 30 days of entries shown below the form (same pattern as the cash till history).

**API:**
- `POST /processor-reconciliation` — create or replace the entry for `(processor_account_id, entry_date)`. Idempotent: re-submitting the same date/processor replaces the previous entry and its lines atomically (delete old lines, insert new). Returns the full entry with computed variances.
- `GET /processor-reconciliation?processor_account_id={id}&date_from={d}&date_to={d}` — list entries for the history view and PROC-3 report.
- `GET /processor-reconciliation/summary?date={d}` — returns SalonOS totals per payment method for the given date, pre-computed from `Sale` + `Payment` records. Used to populate the "SalonOS total" column before staff enters terminal figures.

**Business rules:**
- `salonos_amount` on each line = sum of `Payment.amount` for that `payment_method_id` across all sales with `completed_at` on `entry_date` (using the tenant's local timezone).
- `variance` = `terminal_amount − salonos_amount`. Positive means the terminal shows more than SalonOS; negative means SalonOS shows more than the terminal.
- Only payment methods mapped to the selected processor (via `ProcessorPaymentMethodMap`) appear as lines.
- Cash is never a processor line — cash reconciliation is handled by P2-8 (`CashReconciliation`).

---

### PROC-3 · Reconciliation report and net revenue

Unified view of card settlement vs. SalonOS totals, and merchant fee impact on reported revenue.

**Reconciliation report (extends `/reports/processor-reconciliation`):**
- Date range selector
- Per-processor account: terminal total · SalonOS total · variance · fees · net
- Flags any day with a non-zero variance
- Export to CSV

**Sales report integration (updates P2-5):**
- New "Processor fees" section at the bottom of the sales report:
  - Per-processor: gross card sales · fees entered · net card sales
  - Cash: gross (no fee)
  - **Net revenue after fees**
- Payroll % shown against both gross and net: `Payroll % of Gross Sales` and `Payroll % of Net Revenue`
- If no batch entry exists for a period: "No settlement on file — enter terminal totals to see net revenue"

**API:**
- `GET /reports/processor-reconciliation?date_from={d}&date_to={d}` — returns per-processor summary: `{ processor_label, gross_salonos, gross_terminal, variance, total_fees, net }` for each active processor account, plus a grand total row. Variance and net are null if no batch entry exists for a day.
- CSV export: same shape, streamed as `text/csv`.

---

### PROC-4 · Stripe settlement sync (integrated model — API)

For tenants using Stripe (ecommerce, Phase 6), reconciliation is automatic — no manual entry.

- Nightly Cloud Scheduler job pulls Stripe `BalanceTransaction` objects for the previous day
- Creates a `ProcessorBatchEntry` automatically with fee data from `BalanceTransaction.fee`
- Matched to `orders.stripe_payment_intent_id` — discrepancies only surface for disputes/chargebacks
- Feeds directly into the PROC-3 net revenue report

**Depends on:** Phase 6 ecommerce (E-4).

---

### PROC-5 · Clover API sync (airgapped → automated, v2)

Replaces manual batch entry for Clover-equipped tenants with a nightly automatic pull.

- Clover REST API: `GET /v3/merchants/{mId}/payments` filtered by date
- Creates `ProcessorBatchEntry` + per-method lines automatically from settled transaction data
- Fee data from Clover API per transaction, aggregated to batch level
- Once live, manual entry is no longer needed — staff can still override if the API data looks wrong

**Context:** The TD → Fiserv/Clover migration (announced July 2025, closing late fiscal 2025) moves Salon Lyol's terminal to Clover. This endpoint becomes available once that migration completes. TD itself has no public settlements API, which is why v1 uses manual entry.

**Depends on:** PROC-1; Clover API credentials in Secret Manager.

---

## Phase 4 — Provider Mobile App (iOS + Android)

React Native + Expo app for individual providers. Consumes the existing SalonOS backend API. Designed for the day-to-day workflow of a stylist — not a replacement for the staff web app, which remains the surface for admin, payroll, settings, and reports.

**Stack:** React Native · Expo (managed workflow) · TypeScript · EAS Build

**Scope boundary:** Admin functions (settings, payroll, user management, reports) remain desktop-only.

**Auth:** Same JWT backend. Login screen calls `POST /auth/login`; token stored in `expo-secure-store`. The `provider_id` returned by `/me` drives all provider-scoped queries.

**Navigation:** bottom tab bar — Schedule · Clients · Clock · More

---

### PM-1 · App shell, auth, and schedule view

**Auth:**
- Login screen: email + password → `POST /auth/login`. Token in `expo-secure-store`; validated on cold launch via `GET /auth/me`.

**Schedule screen (home tab):**
- Appointment list for the logged-in provider, defaulting to today
- Date strip at top for navigating to other days (forward and back)
- Each row: client name, services, start time, status badge
- Tap → Appointment detail screen
- Pull-to-refresh; salon-closed indicator

**Appointment detail screen:**
- Client name, services, time, status
- Quick actions: Client Arrived (→ in-progress), Send Estimate (PM-8), Checkout (PM-5), Cancel
- Link to client card (PM-7)

---

### PM-2 · Create and modify bookings

Provider creates a new appointment or requests a change to an existing one from their phone. Same conflict detection as desktop.

**Create appointment:**
- From Schedule tab: "+ New" → pick client (search or recent), service(s), date/time
- Conflict check against existing appointments
- Creates a confirmed appointment directly (not a request — providers have authority)
- `POST /appointments` (existing endpoint)

**Modify existing appointment:**
- From appointment detail: "Reschedule" → date/time picker; "Edit services" → add/remove items
- Uses existing `PATCH /appointments/{id}` and item endpoints
- Conflict check on reschedule

**Out of scope for mobile v1:** multi-provider appointments, drag-and-drop rescheduling, converting requests. Those stay desktop.

---

### PM-3 · Provider clock in / clock out

- Large **Clock In** / **Clock Out** button on the Clock tab, current status and today's elapsed time
- Clock in: `POST /time-entries`; clock out: `POST /time-entries/{id}/check-out`
- Admin corrections and history remain desktop-only

**Depends on:** P2-36 (complete).

---

### PM-4 · Client arrived

Provider marks a client as arrived (appointment → `in_progress`) from their phone, avoiding the need to touch the desktop app mid-service.

- "Client Arrived" action on the appointment detail screen
- Calls `PATCH /appointments/{id}` with `status: in_progress` (existing endpoint)
- Updates the status badge on the schedule list immediately (optimistic update)

---

### PM-5 · Checkout + payment request

Provider checks out a client and optionally sends a payment request for non-cash, non-card transactions.

**Checkout flow:**
- Single appointment only (group checkout stays desktop)
- Service items pre-populated; prices editable
- GST + PST computed; payment method picker (tenant-configured methods)
- Submit → `POST /sales`; appointment transitions to `completed`
- Out of scope for mobile v1: retail items, promotions, cashback, void/edit

**Payment request (new feature):**
- After checkout (or before, as a pre-payment request): "Send payment request" button
- Sends the client an email listing the total and the tenant's configured payment instructions
- No card processing — PCI-clean by design; the tenant specifies whatever methods they want (e-transfer, PayPal, Interac, etc.)

**Backend additions:**
- `TenantPaymentMethod` gets an optional `request_instructions` text field (e.g., "Send to info@salonlyol.ca, memo: your name")
- `POST /appointments/{id}/send-payment-request` — emails the client a formatted payment request using the appointment's service items and prices; uses enabled payment methods that have `request_instructions` set. Returns 204.
- Email template: "Hi [client], here's a summary of your visit on [date]…" → itemised list → total → "To pay: [method 1 instructions] · [method 2 instructions]"
- Settings: payment methods form gains a "Payment request instructions" field (optional). Any method with instructions populated appears in payment request emails.

---

### PM-6 · One-off schedule change request

Provider requests a day off, a late start, an early finish, or a vacation block. Admin reviews and applies the exception on desktop.

**Provider flow:**
- "Request time off" from the More tab → pick type: Full day off / Late start / Early finish / Vacation block
- Select date (or date range for vacation)
- Optional notes (e.g. "doctor's appointment", "ski trip")
- Submit → stored as a `ScheduleChangeRequest` record, email notification sent to admin

**Admin flow (desktop):**
- New "Change requests" section on the Staff Management page → Time tab
- Lists pending requests with provider, type, dates, notes
- "Approve" applies the corresponding `ProviderScheduleException`(s) automatically and marks the request approved
- "Decline" marks it declined; optionally sends a reply note to the provider

**Data model (new):**
- `schedule_change_requests`: `id`, `tenant_id`, `provider_id`, `request_type` (`day_off` | `late_start` | `early_finish` | `vacation`), `start_date`, `end_date` (nullable for single-day), `start_time` / `end_time` (for late/early), `notes`, `status` (`pending` | `approved` | `declined`), `admin_notes`, `created_at`, `reviewed_at`, `reviewed_by_user_id`

**Backend endpoints:**
- `POST /schedule-change-requests` — provider submits; triggers admin email notification
- `GET /schedule-change-requests` — list (admin sees all, provider sees own)
- `POST /schedule-change-requests/{id}/approve` — admin approves; auto-creates `ProviderScheduleException`(s)
- `POST /schedule-change-requests/{id}/decline` — admin declines with optional note

---

### PM-7 · Client card (mobile)

Provider views a client's notes and history from their phone.

- Accessible from appointment detail (tap client name) or from a Clients search tab
- **Colour formula notes:** read + edit — the primary reason a provider needs this mid-service
- **Special instructions:** displayed prominently (allergies, preferences)
- Visit history: past appointments with services, providers, dates (read-only)
- Contact info and no-show / late-cancel counts (read-only)
- Editing contact details stays desktop-only

**API:** `/clients/{id}`, `/clients/{id}/history`, `/clients/{id}/colour-notes` — all existing.

---

### PM-8 · Send appointment estimate

Provider sends the client a pre-visit summary with estimated duration and cost before or at the start of the appointment.

- "Send estimate" action on the appointment detail screen
- Auto-populates from the appointment's services: each service with provider, estimated duration, and price
- Provider can edit prices and add a note before sending
- Sends an email to the client: "Here's an estimate for your upcoming appointment on [date]…" → itemised services → total estimate → "Prices are estimates and may vary slightly."
- No client confirmation required — informational only

**Backend:**
- `POST /appointments/{id}/send-estimate` — generates and sends the estimate email; returns 204
- Uses the existing `send_email` infrastructure and branded layout
- No new schema fields — appointment items already carry service name, provider name, duration, and price

---

### PM-9 · Barcode scanning (mobile)

Native barcode scanning using `expo-camera` with `onBarcodeScanned`. Surfaces in three places within the mobile app, mirroring the desktop scanner (P2-32) but using the device camera natively.

**Receive stock:**
- From the More tab → Inventory → "Receive shipment": scan product barcode → confirm item name → enter quantity → submits `kind=receive` stock movement
- Works for both retail and professional items

**Checkout — add retail/professional item to sale:**
- In the PM-5 checkout flow: scan icon in the items section → camera opens → scan barcode → matching product added to the sale
- Replaces/augments the manual product picker on mobile

**Professional product use recording (extends P2-33):**
- From the appointment detail (after client arrived): "Products used" section
- Scan barcode → enter quantity in UOM (ml, g, unit) → saves a `kind=use_in_service` movement linked to the appointment item
- Designed for one-handed use during a service: quick scan + quantity entry, no navigation needed
- Uses the same `POST /retail-items/{id}/use-in-service` endpoint as desktop (P2-33)

**Inventory count:**
- From More tab → Inventory → "Count": scan + enter counted quantity for each item; submit creates `kind=adjust` movements

**Depends on:** P2-31 (barcode field on products), P2-32 (shared backend lookup endpoint `GET /retail-items/by-barcode/{barcode}`), P2-33 (use-in-service endpoint).

---

### PM-10 · App Store + Play Store submission

- EAS Build for production iOS + Android builds via GitHub Actions
- Apple App Store: App Store Connect listing, TestFlight first
- Google Play: internal track → production rollout
- App name: **SalonOS** for multi-tenant; **Salon Lyol** for single-tenant beta
- Privacy policy required (push notification permission, if added later)

**Phasing:** TestFlight / internal Play track after Salon Lyol UAT on mobile.

(Renumbered from PM-9 to accommodate PM-9 barcode scanning.)

---

### P4-1 · QuickBooks Online integration

Automate the daily bookkeeping journal entries from SalonOS into QuickBooks Online, replacing the need for a bookkeeper to manually transcribe Milano Daily Sales Reports.

**What gets pushed to QBO:**

- **Daily sales journal entry** — for each business day, one journal entry:
  - Dr. Merchant account — VISA (net of processing fees)
  - Dr. Merchant account — DEBIT
  - Dr. Merchant account — AMEX
  - Dr. Cash in drawer (CASH payments)
  - Dr. Accounts Receivable (On Account sales)
  - Dr. Gift Card Liability (gift card sales)
  - Cr. Service Revenue
  - Cr. Retail Revenue
  - Cr. GST Payable
  - Cr. PST/QST Payable
- **Petty cash entries** — each petty cash disbursement recorded in SalonOS becomes a QBO expense
- **Account payment received** — when a client pays their on-account balance, debit cash/card and credit Accounts Receivable

**What stays outside SalonOS:**
- Merchant processing fee reconciliation (handled by QBO bank feeds from your processor)
- Bank statement reconciliation (QBO bank feeds)
- HST remittances, T4s, year-end adjustments (accountant)

**Implementation:**

1. **QBO OAuth setup** — Settings → Integrations → Connect QuickBooks. Standard OAuth 2.0 flow; store refresh token in Secret Manager.
2. **Chart of Accounts mapping** — one-time setup screen where staff maps SalonOS categories (Service Revenue, GST Payable, etc.) to existing QBO account IDs. Stored in a `qbo_account_mapping` table.
3. **Nightly sync job** — Cloud Scheduler → `POST /internal/sync-qbo` — queries completed sales for the previous business day, builds journal entries, pushes via QBO API.
4. **Manual backfill** — a date-range trigger to backfill historical months.
5. **Sync log** — every push logged with QBO transaction ID, status, and any errors surfaced in a Settings → Integrations page.

**QBO API notes:**
- Use QuickBooks Online API (not Desktop) — REST, well-documented, OAuth 2.0
- Journal entries: `POST /v3/company/{companyId}/journalentry`
- Sandbox available for testing without touching real QBO data
- Rate limit: 500 requests/minute, more than sufficient for nightly batch

**Prerequisites:**
- Payment type breakdown working for all months (in progress)
- On Account payment type live (done)
- Petty cash module live (done)
- Chart of accounts discussion with bookkeeper before go-live to confirm account names/IDs

**Phase:** P4 — after SalonOS is in production at Salon Lyol. Set up in parallel with go-live so the first live day's data flows automatically.

---

## Phase 5 — SaaS Go-to-Market

Public commercialization of SalonOS / Roux as a multi-tenant SaaS for salons beyond Salon Lyol. Triggered once Salon Lyol is stable in production and the second tenant is realistic.

### P5-1 · Marketing website for SalonOS / Roux

A standalone marketing site that lives separately from the app. Purpose: convert curious salon owners into trial signups or sales conversations.

**Domain strategy:** `roux.salon` (or `joinroux.com`) for the marketing site; the app continues to live at `app.roux.salon` or per-tenant subdomains. Both Cloudflare-managed; already-registered domains in the memory pool.

**Pages (v1 scope):**

- **Home** — hero ("Software for salons that actually understands how salons work"), three-pane value prop (correct multi-provider booking · AI-first briefings · transparent pricing), social proof spot (logo bar / quote when one exists), CTA to demo or trial.
- **Product** — feature deep-dives with screenshots: appointment book grid, smart booking recommendations, briefing engine, POS + reporting, payroll. Each section is its own anchor.
- **Pricing** — single page with tiers. Probably one tier with per-location pricing + percentage-free transactions (the "displacement story" from CLAUDE.md). Real numbers; not "contact us." Include a comparison table vs Boulevard / Mangomint / Fresha.
- **Why Roux** — the narrative behind the product. Built by an industry insider (Salon Lyol owner), correct multi-provider sequencing (the thing every other tool gets wrong), AI integration that's actually useful not gimmicky.
- **Demo / Get started** — embedded Cal.com or Calendly booking for a live demo. Self-serve trial signup form below (collects salon name, owner email, expected location count, current software).
- **Blog / Field notes** — empty at launch, scaffolded. Reuse the briefing engine output (`developer` audience) as the seed content stream — daily market intel becomes weekly blog posts about the salon software landscape.

**Stack — keep it simple:**

- **Astro** for the marketing site (static site generator, MDX content, fast). Hosted on Cloudflare Pages — free, auto-deploys from a separate `roux-site` GitHub repo. CDN-cached globally; sub-100ms TTFB.
- **Content in MDX** so blog posts and feature pages are just files. No CMS dependency v1.
- **Forms (demo signup, trial signup)** post to a SalonOS backend endpoint (`POST /api/marketing/lead`) so leads land in the same place as everything else — eventually a `marketing_leads` table the briefing engine can surface as a "new leads this week" item in your daily briefing.
- **Analytics:** Plausible (privacy-preserving) or self-hosted Umami. Not GA4.
- **A/B testing:** out of scope for v1.

**SEO considerations:**

- Long-tail keywords for now: "multi-provider salon booking software," "salon software that handles colour processing," "Boulevard alternative." Don't bother fighting for "salon software" — too competitive, displacement messaging works better.
- Schema.org `SoftwareApplication` markup on the homepage and pricing page.
- Submit sitemap to Google Search Console once live.

**v2+ (not blocking launch):**

- Customer case studies (need 2-3 paying customers first)
- ROI calculator (input current spend + missed-call rate, output projected savings — the Zenoti playbook)
- Interactive product tour (Storylane / Arcade)
- Webinars / live demo signup flows
- Partner program (referral commissions for stylists who recommend Roux)

**Why a separate repo:** the app and the marketing site evolve on different cadences and have different stacks. Splitting them keeps the app deploy clean and lets the site iterate independently (a copy tweak shouldn't trigger an API rebuild).

**Depends on:** Salon Lyol being stable in production (i.e., the "this software exists and works" claim is true). Realistic start date: 2–4 weeks post-parallel-run.

---

## Phase 6 — Retail Ecommerce

Public-facing online store for retail products. Clients browse the salon's retail catalog, add items to cart, and pay online via Stripe. Fulfillment is either in-salon pickup or shipping. No card data ever touches SalonOS servers — Stripe handles PCI compliance (SAQ A).

**Depends on:** P2-12 (retail catalog) and P2-13 (inventory) — both complete.

**Stack additions:** Stripe Payment Intents API · Stripe webhooks · Stripe Elements (frontend) · shipping carrier API (Canada Post / Purolator, v1 can be manual tracking entry)

---

### E-1 · Storefront settings

Tenant configures and enables their online store before it goes live.

**Settings → Ecommerce tab (new):**
- Enable / disable storefront toggle (storefront is hidden at `/shop` while disabled)
- Pickup address (pre-populated from tenant contact details, editable)
- Stripe account connection: "Connect Stripe" OAuth flow; stores `stripe_account_id` in Secret Manager
- Shipping rates: list of rates with label, amount, and optional free-shipping threshold (e.g. "Standard — $12.00 · Free over $75")
- Per-item "available online" flag: products not flagged are excluded from the storefront even if active in the catalog

**Data model:**
- `TenantEcommerceSettings`: `tenant_id` PK, `enabled`, `stripe_account_id` (encrypted), `pickup_enabled`, `pickup_instructions`
- `ShippingRate`: `id`, `tenant_id`, `label`, `amount`, `free_threshold` (nullable), `is_active`, `sort_order`
- `RetailItem` gains `available_online` boolean (default false — opt-in per item)

---

### E-2 · Public storefront

Client-facing product catalog at `/shop` on the existing frontend. No login required to browse; account or guest checkout at purchase.

**Storefront pages:**
- `/shop` — product grid, filterable by category; search
- `/shop/[item-id]` — product detail: name, description, price, stock status (in stock / low stock / out of stock), photos (if set), "Add to cart"
- Out of stock items shown but "Add to cart" disabled

**Stock display rules:**
- In stock: on-hand > 3
- Low stock: on-hand 1–3
- Out of stock: on-hand ≤ 0

**API:** new `GET /shop/products` (public, no auth) — returns active + `available_online` retail items with on-hand counts. No auth token required.

---

### E-3 · Shopping cart and checkout flow

Client builds a cart and completes purchase.

**Cart:**
- Persisted in `localStorage` (no server-side cart in v1)
- Item count badge in storefront nav
- Cart page: line items, quantities (editable), subtotal, estimated tax, total

**Checkout:**
1. **Fulfillment choice:** Pickup at salon (address shown) or Ship to address
2. **Shipping address form** (if shipping): name, address, city, province, postal, country
3. **Shipping rate selector** (if shipping): picks from tenant-configured rates; free threshold applied automatically
4. **Order summary:** items, subtotal, shipping, GST, PST, total
5. **Payment:** Stripe Elements card form (card data goes directly to Stripe; SalonOS never sees it)
6. **Place order** → creates `Order` record with `status: pending`, creates Stripe Payment Intent, confirms payment

**Guest vs account:**
- Guest checkout: name + email required (for order confirmation); no SalonOS account needed
- Logged-in client: pre-populated from account, order appears in order history

**Tax:** GST (5%) applied to all items; PST (8%) applied unless item is `is_pst_exempt`. For v1 this applies regardless of shipping destination — note as a known limitation (cross-provincial tax treatment deferred).

---

### E-4 · Stripe payment integration

**Payment flow:**
1. Client submits checkout → `POST /shop/orders` creates `Order` + calls Stripe `PaymentIntents.create` → returns `client_secret` to frontend
2. Frontend confirms payment using Stripe Elements + `client_secret`
3. Stripe fires `payment_intent.succeeded` webhook → `POST /webhooks/stripe` updates `Order.status` to `confirmed` and decrements inventory
4. Order confirmation email sent to client; new order notification sent to staff

**Stripe webhook events handled:**
- `payment_intent.succeeded` → confirm order, decrement stock, send emails
- `payment_intent.payment_failed` → mark order `payment_failed`, notify client
- `charge.refunded` → mark order `refunded`, restore stock

**Backend:**
- `POST /shop/orders` — public endpoint; validates cart against current catalog + stock; creates order + payment intent
- `POST /webhooks/stripe` — Stripe signature verified; handles the above events
- `stripe_payment_intent_id` and `stripe_payment_status` stored on `Order`

---

### E-5 · Shipping

**Staff workflow:**
- Order detail shows shipping address and current tracking status
- "Mark shipped" action: enter tracking number + carrier → `Order.status` → `shipped`; client receives shipping notification email with tracking info

**Client experience:**
- Order confirmation email: order summary + fulfillment type
- Shipping notification email: tracking number + carrier link

**v1 scope:** manual tracking entry by staff. No carrier API integration — staff enters tracking number after generating label outside SalonOS. Carrier API (Canada Post, Purolator, etc.) is a v2 enhancement.

---

### E-6 · Order management (staff)

Staff process and fulfil incoming orders from a new Orders page.

**Orders page (`/orders`, new nav entry under Finance):**
- List with filter by status: All · Pending payment · Confirmed · Processing · Ready / Shipped · Delivered · Cancelled
- Each row: order number, client name, date, items count, total, fulfillment type, status badge
- Tap/click → order detail

**Order detail:**
- Items, quantities, prices, totals
- Client info (name, email, phone if account)
- Fulfillment: pickup instructions or shipping address + tracking entry
- Status action buttons: Confirm → Processing → Ready for Pickup (or Shipped) → Delivered
- Cancel order (triggers Stripe refund via `POST /shop/orders/{id}/cancel`)
- Print packing slip

**Data model:**
```
orders: id, tenant_id, client_id (nullable), guest_name, guest_email,
        order_number (human-readable, e.g. SL-0042), status, fulfillment_type,
        subtotal, shipping_cost, gst_amount, pst_amount, total,
        stripe_payment_intent_id, stripe_payment_status, notes,
        created_at, updated_at

order_items: id, tenant_id, order_id, retail_item_id, description,
             quantity, unit_price, line_total, is_gst_exempt, is_pst_exempt

order_shipping_address: id, order_id, recipient_name, address_line1,
                        address_line2, city, region, postal_code, country,
                        tracking_number, carrier, shipped_at
```

---

### E-7 · Order notifications

**Client emails:**
- Order confirmation (on `payment_intent.succeeded`): order summary, fulfillment instructions, order number
- Shipping notification (on "Mark shipped"): tracking number, carrier, estimated delivery if available
- Cancellation / refund confirmation

**Staff notifications:**
- New order email to configured recipients (same setting as booking request notifications)
- In-app badge on the Orders nav item for unprocessed orders (same pattern as pending requests badge)

All emails use the existing branded layout (`wrap_branded`).

---

### E-8 · Inventory integration

Stock is reserved on order placement and decremented on payment confirmation. Cancellations restore stock.

- On `POST /shop/orders`: write `kind=reserve` `RetailStockMovement` for each item — reduces available quantity but is visually distinct from a sale
- On `payment_intent.succeeded`: convert reserve movements to `kind=sell`
- On order cancellation / `charge.refunded`: write `kind=return` movements to restore stock
- "Reserve" movements excluded from the sales report (they're not revenue until paid)
- On-hand display on the storefront uses available stock = on_hand − reserved

**Why reserve rather than decrement immediately:** prevents overselling during the payment window without requiring a cart server.

---

### E-9 · Client order history

Logged-in clients can see past online orders.

- New "Orders" tab in the client portal (wherever the client-facing account page lives)
- List: order number, date, items, total, status
- Detail: same as above, read-only
- Guest orders are not linked to an account (guest email only); account matching deferred to v2

**API:** `GET /shop/orders/mine` — returns orders where `client_id` matches the logged-in user's linked client record.

### P-PAYROLL-1 · Product fee effective-date history ⚠️ HIGH PRIORITY (parallel run) · In progress

**The problem:** The payroll report always uses the *current* catalog product fee. A fee change made after a pay period closes will retroactively affect that period's report. Example: Olaplex 10% fee was added after April 15 but showed up in the March 16 – April 15 payroll run, causing a $3.50 discrepancy vs. Milano.

**Business rule:** Fee decisions are finalized within the current pay period. After the period closes they are non-restateable.

**What to build:**

- Add `effective_from` (date, not null, default today) to the `services` table (migration).
- Create a `service_fee_history` table: `service_id`, `effective_from`, `product_fee`, `is_cost_percent`, `created_by_user_id`, `created_at`. Populated by a trigger or application-side hook whenever `services.product_fee` or `services.is_cost_percent` changes.
- Update `_calc_payroll_line` to join against `service_fee_history` using the fee row where `effective_from <= period_end` (most recent per service). Falls back to current value if no history row exists.
- Services page: show fee change history per service (last 5 changes with dates).

**Migration strategy:**
- The migration adds `effective_from date NOT NULL DEFAULT CURRENT_DATE` to `services`.
- It also creates `service_fee_history` and seeds one row per service from the current `product_fee` + `is_cost_percent` values, with `effective_from = '2000-01-01'` (sentinel meaning "always applied before any explicit change"). This ensures existing payroll queries immediately return a result and never fall back to nothing.
- No backfill of true historical changes is needed — the workaround (manual sale item edit) has already corrected the specific discrepancies found during the parallel run.

**API:**
- `GET /services/{id}/fee-history` — returns last 10 fee rows ordered by `effective_from DESC`: `{ effective_from, product_fee, is_cost_percent, changed_by }`.
- Fee history is written automatically server-side on `PATCH /services/{id}` whenever `product_fee` or `is_cost_percent` changes — no separate endpoint needed.

**Payroll calculator change:**
```python
# In _calc_payroll_line, replace direct service.product_fee access with:
fee_row = (
    session.execute(
        select(ServiceFeeHistory)
        .where(ServiceFeeHistory.service_id == service_id)
        .where(ServiceFeeHistory.effective_from <= period_end)
        .order_by(ServiceFeeHistory.effective_from.desc())
        .limit(1)
    )
).scalar_one_or_none()
product_fee = fee_row.product_fee if fee_row else service.product_fee
is_cost_percent = fee_row.is_cost_percent if fee_row else service.is_cost_percent
```

**Workaround until built:** Manually zero the product fee on the affected sale item via the Sales edit UI. The sale audit log records the change.

**Depends on:** None — standalone.

### P-PERF-1 · Service Performance Report (per-provider) · Dev complete

A stylist performance review — modeled on the legacy Milano "Service Performance Report" but trimmed to the sections Freddy actually uses. Owner-facing on the Reports tab, one report per provider per date range.

**Sections (MVP):**
- Service breakdown table: service name, total sales, count, average price, % of sales, % of count.
- Retail summary: total retail sales, count, average.
- Receipt analysis: # receipts, # clients serviced, avg/receipt, items/receipt.
- Ratios: % service of total, % retail of total, % retail of service.

Deliberately *not* in MVP (skipped from the Milano report):
- Performance stats (per Hour / Day / Week / Month) — covered by other dashboards.
- Booking utilization (Scheduled / Blocked / Available / Booked / Remaining) — needs scheduling integration; later.
- Client type breakdown (NEW / REG / WLK) — requires a definition of "new" relative to a period; later.
- Commission information block — already lives in [PayrollDetailPage](frontend/src/pages/PayrollDetailPage.tsx).

**Backend:** `GET /reports/service-performance?provider_id=...&start=...&end=...` returning service rows + summary aggregates. Same auth/pattern as `/reports/payroll-detail`. Filters `Sale.status == completed`, `SaleItem.provider_id == provider_id`, `Sale.completed_at` in `[start, end]`.

**Frontend:** `ServicePerformanceReportPage.tsx` linked from ReportsPage, mirroring PayrollDetailPage's date-range + provider picker. Print CSS so the in-app view doubles as the printable report.

**Phase 2 (after MVP UAT):** server-side PDF via WeasyPrint.

**Phase 3:** scheduled monthly email through the Briefing Engine (`salon_owner` audience).

**Depends on:** None — standalone.
