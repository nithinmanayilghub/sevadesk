# Story 5.1 — Calculate free Slots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (CLAUDE.md: native build in this session). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `bookings` module owns a `bookings` table and lists the free Slots of one Service for the next 7 days, through `GET /api/v1/bookings/slots`.

**Architecture:** `bookings` sits between `inbox` and `business` in the layer order. A pure function (`slots.py`, no database) does the Slot math. The service gathers its inputs through front doors: Working Hours and the Service from `business`, the active-Technician count from `accounts`, and the live Bookings from its own repository. One repository function holds the "expired on read" rule.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres 18, pytest + Testcontainers, `zoneinfo`.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 5.1: Calculate free Slots" (line ~889). Rules: AR-1, AR-5, AR-6, AR-7, AR-14, AR-24, FR-10, FR-17 in the same file (lines ~94–125), and AD-9 in `_bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md`.

## Global Constraints

- Backend tests run in WSL: `wsl --cd "/mnt/c/Books/DataSense Community/Seva Desk/backend" uv run pytest ...`.
- Frontend commands run in Windows PowerShell.
- `bookings` never imports `inbox`. It stores `customer_id` and `conversation_id` as plain ids (spine, "No cycles").
- `bookings` uses `business` and `accounts` only through `service.py` / `dependencies.py` (AR-2).
- Only `accounts.service.active_technician_ids` says who is an active Technician (AR-7).
- Times are `timestamptz` UTC in the database. Slot math uses the Business timezone (AR-5).
- Money is integer `price_paise` (AR-5).
- Tenant table rules: `UNIQUE (business_id, id)` and composite foreign keys (AR-6).
- Fixed constants (AR-24): `SLOT_STEP_MINUTES = 30`, `SLOT_DAYS = 7`. Slot length = the Service's `duration_minutes` (no separate constant).
- No write path, no advisory lock in this story. Story 5.2 adds the lock with the first write.

## Decisions this plan makes (from the spec's open points)

- **Slot length = the Service duration, not a constant.** The AC says "Slot length and step are fixed constants" (AR-24), but FR-17 says a Slot must "fit the Service duration". One fixed length would offer a 60-min Slot for a 2-hour job. So only the step (`SLOT_STEP_MINUTES = 30`) and the window (`SLOT_DAYS = 7`) are constants. (Recorded after the code review of PR #72.)
- **Slot step 30 min.** Start times are Working-Hours start, +30, +60, … A Slot fits only if `start + duration <= close`.
- **Window:** 7 Business-local dates: today (Business clock) to today + 6.
- **Past starts are not free.** A Slot with `start < now` is dropped (today's morning, after the shop opened).
- **Overlap:** Booking `[b_start, b_end)` overlaps Slot `[s, e)` when `b_start < e and b_end > s`. Touching ends do not overlap.
- **Live Booking:** `state = 'confirmed'`, or `state = 'requested' AND expires_at > now`.
- **`technician_membership_id` is nullable.** A `requested` Booking (Epic 6) has no Technician yet. A CHECK requires it for `confirmed`, `completed`, `cancelled`.
- **Endpoint:** `GET /api/v1/bookings/slots?service_id=<uuid>` → `FreeSlotsOut`. Permission `USE_INBOX_AND_BOOKINGS`. Unknown, inactive, or foreign Service → our 404.

## Review Focus

1. **The Business clock is past midnight but UTC is not** (e.g. 00:30 IST = 19:00 UTC the day before). "Today" must be the Business date. → Task 2 test `test_today_is_the_business_date_after_midnight`.
2. **Slots earlier today, before "now".** They must not show. → Task 2 test `test_slots_before_now_are_dropped`.
3. **No active Technician** (Owner removed the Technician Role). Expected: no Slots, no crash, no divide error. → Task 2 test `test_no_technicians_means_no_slots`.
4. **A Booking that only touches a Slot edge** (ends 11:00, Slot starts 11:00). Expected: the Slot stays free. → Task 2 test `test_touching_booking_does_not_block`.
5. **Cancelled / completed / declined Bookings and another Business's Bookings.** They must not take capacity. → Task 3 test `test_only_live_bookings_of_this_business_count`.

---

## File map

| File | Tag | Job |
|---|---|---|
| `backend/app/modules/bookings/__init__.py` | BOILERPLATE | package marker |
| `backend/app/modules/bookings/models.py` | CORE | `Booking` table, states |
| `backend/migrations/versions/0011_bookings.py` | BOILERPLATE | creates the table |
| `backend/migrations/env.py` | BOILERPLATE | registers the model |
| `backend/pyproject.toml` | STANDARD | import-linter layers + front-door contracts |
| `backend/app/modules/bookings/slots.py` | CORE | pure Slot math + constants |
| `backend/app/modules/bookings/repository.py` | CORE | `is_live` rule, live Bookings in a range |
| `backend/app/modules/bookings/schemas.py` | STANDARD | `SlotOut`, `FreeSlotsOut` |
| `backend/app/modules/bookings/service.py` | CORE | `list_free_slots` front door |
| `backend/app/modules/business/service.py` | STANDARD | `get_active_service`, `business_timezone` |
| `backend/app/modules/bookings/router.py` | STANDARD | the HTTP route |
| `backend/app/main.py` | BOILERPLATE | include router |
| `frontend/openapi.json`, `frontend/src/api/schema.d.ts` | BOILERPLATE | regenerated |

---

### Task 1: The `bookings` table (CORE)

**Files:**
- Create: `backend/app/modules/bookings/__init__.py`, `backend/app/modules/bookings/models.py`, `backend/migrations/versions/0011_bookings.py`
- Modify: `backend/migrations/env.py` (import `app.modules.bookings.models`), `backend/pyproject.toml` (import-linter), `backend/tests/integration/test_migrations.py` (add `"bookings"` to the table set)
- Test: `backend/tests/integration/test_bookings_table.py`

**Interfaces:**
- Produces: `Booking(TenantModel)` with columns `id: UUID (uuid7)`, `state: str`, `starts_at: datetime`, `ends_at: datetime`, `customer_id: UUID`, `conversation_id: UUID | None`, `technician_membership_id: UUID | None`, `price_paise: int`, `expires_at: datetime | None`, `created_at: datetime`. Constants `BOOKING_STATES = ("requested", "confirmed", "declined", "expired", "completed", "cancelled")`.

Constraints (names follow 0009 style, written by hand in the migration; CHECK texts copied, not imported):
- `pk_bookings`, `fk_bookings_business_id_businesses`, `uq_bookings_business_id_id`
- `fk_bookings_business_id_customers`: `(business_id, customer_id) → customers(business_id, id)`
- `fk_bookings_business_id_conversations`: `(business_id, conversation_id) → conversations(business_id, id)` (NULL skips the check)
- `fk_bookings_business_id_memberships`: `(business_id, technician_membership_id) → memberships(business_id, id)`
- `ck_bookings_state_valid`: `state IN (...)` the six states
- `ck_bookings_ends_after_starts`: `ends_at > starts_at`
- `ck_bookings_price_valid`: `price_paise > 0`
- `ck_bookings_request_has_expiry`: `state <> 'requested' OR expires_at IS NOT NULL`
- `ck_bookings_technician_when_confirmed`: `state NOT IN ('confirmed','completed','cancelled') OR technician_membership_id IS NOT NULL`
- Index `ix_bookings_business_id_starts_at` on `(business_id, starts_at)` (the Slot query reads a time range).

import-linter (`pyproject.toml`):
- Layers become `["app.modules.inbox", "app.modules.bookings", "app.modules.business", "app.modules.accounts", "app.core"]`.
- Add two `forbidden` contracts, copied from the `business` one: "bookings uses business only through its front door" (forbid `business.models/repository/router/chat_slug`) and "bookings uses accounts only through its front door" (forbid `accounts.models/repository/router/team/team_router`), both `allow_indirect_imports = true`.

- [ ] **Step 1: Write the failing tests** in `test_bookings_table.py` (mark `pytestmark = pytest.mark.isolation`; insert rows with a plain `Session(get_engine())`, like `test_tenant_schema.py`):
  - `test_booking_row_saves` — a `confirmed` Booking with a customer and the Owner's membership saves; `id` is set.
  - `test_customer_of_another_business_is_refused` — A's Booking with B's `customer_id` → `IntegrityError`.
  - `test_requested_needs_expiry` — `state="requested", expires_at=None` → `IntegrityError`.
  - `test_confirmed_needs_technician` — `state="confirmed", technician_membership_id=None` → `IntegrityError`.
  - `test_end_must_be_after_start` — `ends_at == starts_at` → `IntegrityError`.
  - Add `"bookings"` to the set in `test_migrations.py::test_migrations_downgrade_to_base_and_back`.
- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/integration/test_bookings_table.py tests/integration/test_migrations.py -v` → import error / missing table.
- [ ] **Step 3: Implement** `models.py`, migration `0011` (`down_revision = "0010"`, downgrade drops the table), `env.py` import, `pyproject.toml` contracts.
- [ ] **Step 4: Run, expect PASS** — the same command, plus `uv run pytest tests/integration/test_tenant_schema.py -v` (the schema guard must accept the new table) and `uv run lint-imports`.
- [ ] **Step 5: Commit** — `feat(bookings): bookings table with composite keys (story 5.1)`.
- [ ] **CHECKPOINT** (CORE task): stop, show the model, let the user explain one CHECK.

---

### Task 2: Pure Slot math (CORE)

**Files:**
- Create: `backend/app/modules/bookings/slots.py`, `backend/app/modules/bookings/schemas.py`
- Test: `backend/tests/unit/test_slots.py`

**Interfaces:**
- Consumes: `OpenHours` from `app.modules.business.schemas` (`start_time: time`, `end_time: time`).
- Produces:
  - `schemas.SlotOut(BaseModel)`: `start: datetime`, `end: datetime` (UTC, aware).
  - `schemas.FreeSlotsOut(BaseModel)`: `timezone: str`, `slots: list[SlotOut]` (earliest first).
  - `slots.SLOT_STEP_MINUTES = 30`, `slots.SLOT_DAYS = 7`.
  - `slots.window_days(today: date) -> list[date]` — `SLOT_DAYS` dates from `today`.
  - `slots.free_slots(*, hours_by_day: dict[date, OpenHours | None], duration: timedelta, busy: list[tuple[datetime, datetime]], technicians: int, tz: ZoneInfo, now: datetime) -> list[SlotOut]`

Approach: for each day in date order, skip `None`; build local start/close with `datetime.combine(day, t, tzinfo=tz)`; step by 30 min while `start + duration <= close`; drop `start < now`; count `busy` items that overlap (`b_start < end and b_end > start`); keep the Slot when `count < technicians`. Return UTC (`.astimezone(UTC)`).

Test data: tz `Asia/Kolkata`, Monday `2026-11-30`, hours 10:00–12:00, duration 60 min, `now` = `2026-11-29 00:00 IST`. Helper `ist(day, "HH:MM") -> datetime` in the test file.

- [ ] **Step 1: Write the failing tests** (say each behaviour in one line before writing it):
  - `test_open_day_gives_every_fitting_start` — 1 tech, no busy → starts `10:00, 10:30, 11:00` (11:30 does not fit).
  - `test_closed_day_gives_no_slots` — `hours_by_day = {monday: None}` → `[]`.
  - `test_slot_at_end_of_working_hours` — last Slot is `11:00–12:00`; ends exactly at close.
  - `test_one_technician_fully_booked` — 1 tech, busy `10:00–12:00` → `[]`.
  - `test_two_technicians_one_free` — 2 techs, busy `10:00–12:00` once → all three starts still free; busy twice → `[]`.
  - `test_touching_booking_does_not_block` — 1 tech, busy `10:00–11:00` → only `11:00`.
  - `test_no_technicians_means_no_slots` — `technicians=0` → `[]`.
  - `test_slots_before_now_are_dropped` — `now = ist(monday, "10:15")` → starts `10:30, 11:00`.
  - `test_today_is_the_business_date_after_midnight` — `window_days` of the Business date: `now = 2026-11-29 19:00 UTC` (= 30 Nov 00:30 IST); `datetime.now`-free: the test asserts `window_days(now.astimezone(tz).date())[0] == date(2026, 11, 30)` and has length 7.
  - `test_slots_are_utc` — `10:00 IST` comes back as `04:30 UTC`.
- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_slots.py -v` → `ModuleNotFoundError`.
- [ ] **Step 3: Implement** `schemas.py` and `slots.py`, with comments that explain the overlap rule and why "count < technicians".
- [ ] **Step 4: Run, expect PASS** — the same command.
- [ ] **Step 5: Commit** — `feat(bookings): pure free-Slot math (story 5.1)`.
- [ ] **CHECKPOINT** (CORE task).

---

### Task 3: Live Bookings and the `list_free_slots` front door (CORE)

**Files:**
- Create: `backend/app/modules/bookings/repository.py`, `backend/app/modules/bookings/service.py`
- Modify: `backend/app/modules/business/service.py` (two small front-door functions)
- Test: `backend/tests/integration/test_free_slots.py`

**Interfaces:**
- Consumes: `slots.free_slots`, `slots.window_days`, `SLOT_DAYS`; `business_service.hours_on(session, day) -> OpenHours | None`; `accounts_service.active_technician_ids(session) -> list[UUID]`; `accounts_service.require_roles(actor, Permission.USE_INBOX_AND_BOOKINGS)`.
- Produces:
  - `business_service.get_active_service(session: Session, service_id: UUID) -> ServiceOut` — raises `NotFound` when missing, inactive, or another Business's (tenant filter).
  - `business_service.business_timezone(session: Session) -> str` — the current Business's timezone.
  - `bookings.repository.is_live(now: datetime) -> ColumnElement[bool]` — THE one "expired on read" rule: `state == 'confirmed' OR (state == 'requested' AND expires_at > now)`. Every count uses it (AR-14). Comment says so.
  - `BookingRepository(TenantRepository[Booking]).live_between(start: datetime, end: datetime, now: datetime) -> list[tuple[datetime, datetime]]` — `(starts_at, ends_at)` of live Bookings with `starts_at < end AND ends_at > start`.
  - `bookings.service._now() -> datetime` — UTC now; the one clock, so tests replace it.
  - `bookings.service.list_free_slots(session: Session, actor: Actor, service_id: UUID) -> FreeSlotsOut` — `require_roles` first; then Service, tz, days, `hours_by_day`, busy for the whole window, Technician count; calls `free_slots`.

Test setup: `sign_up_owner()` gives a Business with 1 Technician (the Owner). Add the Service and a Monday-to-Saturday 10:00–18:00 week through the API (reuse `SERVICE`, `HOURS_WEEK` from `test_tenant_isolation`). Freeze `bookings_service._now` with `monkeypatch` to `2026-11-29 18:30 UTC` (= Mon 30 Nov 00:00 IST). Helper `_book(business_id, membership_id, start, end, state, expires_at=None)` inserts a customer + Booking with a direct Session inside `tenant_scope(business_id)`. Call the service through `client.get("/api/v1/bookings/slots", ...)` only after Task 4; here call `list_free_slots` directly with an `Actor` built from the Owner (`session` from `Session(get_engine())` inside `tenant_scope`).

- [ ] **Step 1: Write the failing tests**:
  - `test_expired_request_frees_capacity` — a `requested` Booking Mon 10:00–11:00 with `expires_at` 1 h before `now` → Mon 10:00 IST is free; the same with `expires_at` 1 h after `now` → Mon 10:00 is not free.
  - `test_confirmed_booking_takes_capacity` — confirmed Mon 10:00–11:00 → Mon 10:00 and 10:30 not free, 11:00 free.
  - `test_only_live_bookings_of_this_business_count` — `cancelled`, `completed`, `declined` Bookings on Mon 10:00, and a confirmed one in Business B at the same time → Mon 10:00 is free for A.
  - `test_closed_day_has_no_slots` — add closed day Tue 1 Dec through the API → no Slot on that date (in IST).
  - `test_window_is_seven_business_days` — no Slot before Mon 30 Nov IST or on/after Mon 7 Dec IST; Sunday (no hours) has none.
  - `test_inactive_service_is_not_found` — `NotFound` for an inactive Service id.
- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/integration/test_free_slots.py -v`.
- [ ] **Step 3: Implement** the two business functions, `repository.py`, `service.py`.
- [ ] **Step 4: Run, expect PASS** — the same command, plus `uv run pytest tests/integration/test_services.py tests/integration/test_working_hours.py -q` and `uv run lint-imports`.
- [ ] **Step 5: Commit** — `feat(bookings): list free Slots with the live-Booking rule (story 5.1)`.
- [ ] **CHECKPOINT** (CORE task).

---

### Task 4: The free-Slots endpoint (STANDARD)

**Files:**
- Create: `backend/app/modules/bookings/router.py`
- Modify: `backend/app/main.py`, `backend/tests/integration/test_tenant_isolation.py`, `frontend/openapi.json`, `frontend/src/api/schema.d.ts`, `_bmad-output/implementation-artifacts/sprint-status.yaml`
- Test: `backend/tests/integration/test_free_slots.py` (add API tests)

**Interfaces:**
- Consumes: `bookings.service.list_free_slots`; `ActorDep`, `SessionDep`, `ErrorEnvelope`.
- Produces: `GET /api/v1/bookings/slots`, `operation_id="list_free_slots"`, query `service_id: uuid.UUID`, `responses={401, 403, 404, 422: _ERROR}`, returns `FreeSlotsOut`.

- [ ] **Step 1: Write the failing tests**:
  - `test_owner_gets_free_slots` — 200; `body["timezone"] == "Asia/Kolkata"`; first Slot `start == "2026-11-30T04:30:00Z"` (Mon 10:00 IST).
  - `test_staff_gets_free_slots` — `set_owner_roles(business_id, ["staff"])` → 200 (the Business then has 0 Technicians → `slots == []`).
  - `test_technician_only_gets_403` — `set_owner_roles(business_id, ["technician"])` → 403 with the forbidden envelope.
  - `test_logged_out_gets_401`.
  - In `test_tenant_isolation.py`: `check_list_free_slots(owners)` — B adds a Service; A asks with B's `service_id` → `assert_not_found`. Register it under `("GET", "/api/v1/bookings/slots")`.
- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/integration/test_free_slots.py tests/integration/test_tenant_isolation.py -v` (404 route / unlisted endpoint).
- [ ] **Step 3: Implement** `router.py`, include it in `main.py`.
- [ ] **Step 4: Run, expect PASS** — the same command.
- [ ] **Step 5: Regenerate the API types** — WSL: `uv run python -m app.export_openapi ../frontend/openapi.json`; PowerShell in `frontend`: `npm run gen:api`, then `npm run typecheck`.
- [ ] **Step 6: Set sprint-status** — `epic-4: done`, `epic-5: in-progress`, `5-1-calculate-free-slots: done` (main is protected; status goes in the story PR).
- [ ] **Step 7: Full proof** — WSL: `uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest --cov` (about 10–14 min; coverage gate 80%).
- [ ] **Step 8: Commit** — `feat(bookings): GET /api/v1/bookings/slots endpoint (story 5.1)`.

After Task 4: one whole-branch review by an Opus subagent, then `docs/agents/after-story.md`.
