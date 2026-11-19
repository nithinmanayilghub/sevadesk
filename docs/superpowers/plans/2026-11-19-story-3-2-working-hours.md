# Story 3.2 — Set Working Hours and Closed Days Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, per CLAUDE.md §4: build in this session, stop after each CORE task, one Opus whole-branch review at the end). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On Settings → Working Hours, the Owner sets each weekday as closed or open (one start and one end time), and adds or removes single closed dates (holidays). A closed date wins over the weekly hours.

**Architecture:** The `business` module owns two new tenant tables, `working_hours` (one row per OPEN weekday) and `closed_days` (one row per closed date), and a new `businesses.timezone` column (default `Asia/Kolkata`). Hours are wall-clock times in the Business timezone (`time`, not `timestamptz`: they are not moments). Five Owner-only routes in `business/router.py`. The front door `business.service.hours_on(session, day)` answers "open hours on this date, or None" for the slot math in Epic 4. The frontend gets `lib/time.ts` (UX-DR4 formatting) and a page at `/app/settings/hours`.

**Tech Stack:** FastAPI, Pydantic 2.14, SQLAlchemy 2.1, Alembic, pytest + testcontainers; Next.js 16, React 19, Tailwind 4, Vitest, openapi-typescript.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 3.2: Set Working Hours and closed days" (line 648). Also FR-13 (`prd.md:164`), AR-5 (`epics.md:98`), UX-DR4 (`epics.md:133`), UX-DR25 (skeletons), UX-DR33 (field errors), EXPERIENCE.md:41 (route `/app/settings/hours`, Owner, from "More") and :56 (12-hour "am/pm", dates "Tue, 4 Nov", Business timezone), ARCHITECTURE-SPINE.md:30 (`business` owns working hours) and :212 (time convention).

**Review history:** an Opus plan review (2026-11-19) found 4 major and 8 minor gaps; all 12 are fixed below (marked `[R#]`).

## Global Constraints

- Tables `working_hours` and `closed_days`, owned by `business`. Tenant tables: `business_id`, UUIDv7 `id`, `UNIQUE (business_id, id)` (checked by `test_tenant_schema.py`).
- `working_hours`: `weekday smallint` 0 = Monday … 6 = Sunday (Python `date.weekday()`), `start_time time`, `end_time time`. `UNIQUE (business_id, weekday)`. CHECK `weekday BETWEEN 0 AND 6`, CHECK `end_time > start_time`. A closed weekday has NO row.
- `closed_days`: `day date`. `UNIQUE (business_id, day)`.
- `businesses.timezone`: `text NOT NULL`, default `'Asia/Kolkata'` in BOTH the migration and the model (`mapped_column(Text, server_default="Asia/Kolkata")`) `[R3]`. Not editable in this story. Nothing checks that models and migrations match, so both are written by hand with care.
- One time range per day. No overnight ranges (end must be after start, so the latest end is 23:59).
- A valid time: `HH:MM` or `HH:MM:SS`, 24-hour, with `tzinfo is None and second == 0 and microsecond == 0` `[R4]`. `"10:00:00"` and `"10:00"` are the same time, so a GET value can be sent back unchanged.
- Role: `Permission.MANAGE_SETUP` (Owner only) on every new route, checked FIRST.
- Field error copy, verbatim (field names are dotted paths, e.g. `monday.end_time`):
  - start missing: `Enter a start time.` · end missing: `Enter an end time.`
  - any time that is not a valid time (bad text, `"9:00"`, `"24:00"`, `""`, seconds, microseconds, a UTC offset): `Use a time like 10:00.` `[R4]`
  - end not after start (on `<day>.end_time`): `End time must be after the start time.`
  - closed date missing, empty, not a plain `YYYY-MM-DD` date (e.g. `"2026-12-25T00:00"`): `Pick a date.` `[R4]` · in the past (Business timezone): `Pick today or a later date.` · already closed: `This date is already closed.`
- Display (UX-DR4): times `10:00 am – 6:00 pm` (lowercase am/pm, en dash with spaces, no leading zero on the hour); dates `Fri, 25 Dec`.
- Route `/app/settings/hours`, label `Working Hours`, `needs: "manage_setup"`, in `PAGES` right AFTER Services.
- Every new route is listed in `tests/integration/test_tenant_isolation.py` `ISOLATION_CHECKS`, or CI fails.
- `frontend/openapi.json` and `src/api/schema.d.ts` regenerated in WSL in the SAME commit as the routes (CI runs `git diff --exit-code`).
- Backend commands run in WSL: `wsl --cd "C:\Books\DataSense Community\Seva Desk\backend" -e bash -lc "uv run …"`. Frontend tests in Windows PowerShell (`npx vitest run …`). Docker Desktop must run.
- Branch `story/3-2-working-hours`. PR body ends with `Closes #15`.

## Decisions made in this plan

- **The week is one object keyed by day name** (`{"monday": {...} | null, …, "sunday": …}`), `null` = closed. Every day key is required. Errors then land on `monday.end_time`, which the page maps straight to that day's row.
- **The "end after start" check is a `@field_validator("end_time")`, not a model validator** `[R1]`. It reads `info.data.get("start_time")`. A model validator would put the error on `tuesday` (verified), not `tuesday.end_time`. Each field validator first checks "valid time" (naive, whole minute), so a refused start time is missing from `info.data` and the comparison is skipped: no naive-vs-aware `TypeError` (500).
- **Time and date parse errors get our own copy** `[R4]`. Time fields are taken as `str | None` and parsed by one helper `_parse_time(text) -> time` (regex `^([01]\d|2[0-3]):[0-5]\d(:00)?$`, then `time.fromisoformat`), so every bad input gets `Use a time like 10:00.`. The closed date is taken as `str | None` and parsed with regex `^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat` (a `ValueError`, e.g. `2026-02-30`, also gives `Pick a date.`). The OpenAPI type of these input fields is then `string`, which is what the browser inputs send anyway. Outputs stay typed `time` / `date`.
- **`PUT /api/v1/working-hours` replaces the whole week in one transaction** `[R2]`: first ONE Core statement `delete(WorkingHours).where(WorkingHours.business_id == current_business_id())` (the house pattern, `accounts/repository.py:58-63`), then `add_all` + `flush`. NOT `session.delete(row)` per row: in one flush SQLAlchemy sends the INSERTs before the DELETEs, and the `UNIQUE (business_id, weekday)` rule breaks (verified). The tenant filter is written by hand here, so a comment says so and `check_replace_working_hours` guards it.
- **Two saves at once are serialised** `[R8]`: `replace_working_hours` and `add_closed_day` first lock the Business row (`BusinessRepository.get_current(for_update=True)` → `SELECT … FOR UPDATE`). The second request waits for the first one, then runs cleanly. As a second guard, an `IntegrityError` on `uq_closed_days_business_id_day` is also turned into the 422 `This date is already closed.`.
- **Closed weekday = no row.** So "no Working Hours exist" (Story 3.3 checklist, UX-DR20) is simply "no rows".
- **`core/errors.py` learns nested field names** `[R9]`. Today it drops any error whose `loc` is deeper than `("body", "x")` (verified). New rule: `loc[0] == "body"` and `loc[1]` is a `str` → field = `".".join(map(str, loc[1:]))` (a path can hold list positions, e.g. `roles.0`). Broken JSON (`("body", <int>)`) is still skipped. Side effect: an invite with an unknown Role now reports field `roles.0` instead of dropping it; no test or form depends on the old behaviour (checked).
- **Times are `time` (wall clock), not `timestamptz`.** "10:00 every Monday" is not one moment, so AR-5's "UTC where a moment is stored" does not apply. The Business timezone says how to read them; Epic 4 slot math turns them into real moments.
- **"Today" lives in one helper** `[R6]`: `service._today(business: Business) -> date` = `datetime.now(ZoneInfo(business.timezone)).date()`. Past dates are refused, and `GET /closed-days` lists only today onward. Tests monkeypatch `_today` to a fixed date, so no test can flip at midnight IST.
- **Add `tzdata==2026.6` to backend dependencies** `[R12]` (already in `uv.lock` through `python-dateutil`; now a direct pin). `python:3.14-slim` may lack `/usr/share/zoneinfo`; `zoneinfo` then falls back to `tzdata`. Run `uv add` in WSL.
- **A duplicate closed date is checked in `service.py` first** (422 next to `day`), under the Business lock.
- **Closed days can be removed** (`DELETE /api/v1/closed-days/{closed_day_id}`, 204). Without it a wrong holiday blocks bookings forever.
- **One output type for an open day** `[R7]`: `OpenHours(start_time: time, end_time: time)`, both required. The week response uses `OpenHours | None` per day, and the front door `hours_on(session, day: date) -> OpenHours | None` returns it (no Role check; Epic 4 calls it inside a tenant scope). The input type `DayIn` (strings) is separate. Note for Epic 4: slot math will also need the Business timezone through a front door; not built now.
- **Formatting is written by hand in `lib/time.ts`**, not `Intl`: the AC fixes exact text, and `Intl` output can differ between browsers and Node.
- **The date input has no `min`** `[R11]`: the browser's timezone can differ from the Business timezone, so the backend's rule decides.
- **Not in this story:** editing the timezone, split shifts (lunch break), overnight hours, date ranges for holidays, a past-holidays history view.

## Review Focus

1. **End time equal to start (10:00–10:00) or before it** → 422 `End time must be after the start time.` on that day's `end_time` only; nothing saved. → Task 2 `test_end_not_after_start_is_refused_next_to_that_day`.
2. **The Owner saves the week a second time** → 200, the new week replaces the old one, no 500. → Task 2 `test_saving_again_replaces_the_week` `[R2]`.
3. **A bad time (`"9:00"`, `"24:00"`, `""`, `"bad"`, `"10:00:30"`, `"10:00:00.5"`, `"10:00+05:30"`)** → 422 `Use a time like 10:00.`, never a 500 or Pydantic's generic text. → Task 2 `test_bad_time_refused` `[R4]`.
4. **The Owner ticks "Open" but leaves a time box empty** → the page sends `null`, the backend answers `Enter a start time.` / `Enter an end time.` under that day. → Task 2 `test_missing_times_on_open_day`, Task 4 `an empty time box sends null`.
5. **Close a date twice, a past date, or a bad date** → 422 next to `day`; the list keeps one row. → Task 3 `test_duplicate_closed_day_refused`, `test_past_closed_day_refused`, `test_bad_closed_day_refused`.
6. **Owner A deletes Owner B's closed day by id** → 404, and B's row stays. → Task 3 isolation check `check_delete_closed_day`.

---

### Task 0: Start the story (no code)

- [ ] Show the Story Map (CLAUDE.md §2) and get the user's prediction.
- [ ] `git switch main && git pull && git switch -c story/3-2-working-hours`. `gh issue edit 15 --add-label in-progress`.
- [ ] `_bmad-output/implementation-artifacts/sprint-status.yaml`: `3-2-set-working-hours-and-closed-days: in-progress`. Commit `docs: Story 3.2 in progress`.

### Task 1: Tables + timezone column (CORE: data model, multi-tenancy) — checkpoint after

**Files:**
- Modify: `backend/app/modules/business/models.py` (add `Business.timezone`, `WorkingHours`, `ClosedDay`)
- Create: `backend/migrations/versions/0007_working_hours.py`
- Modify: `backend/pyproject.toml`, `backend/uv.lock` (`tzdata==2026.6`)
- Create: `backend/tests/integration/test_working_hours_table.py`
- Modify: `backend/tests/integration/test_migrations.py` (table set gains `working_hours`, `closed_days`)

**Interfaces:**
- Produces: `Business.timezone: Mapped[str] = mapped_column(Text, server_default="Asia/Kolkata")`; `WorkingHours(TenantModel)` with `id, business_id, weekday: Mapped[int] = mapped_column(SmallInteger), start_time: time, end_time: time`; `ClosedDay(TenantModel)` with `id, business_id, day: date`. Constraint names: `uq_working_hours_business_id_id`, `uq_working_hours_business_id_weekday`, `ck_working_hours_weekday_valid`, `ck_working_hours_end_after_start`, `uq_closed_days_business_id_id`, `uq_closed_days_business_id_day`.

- [ ] **Step 1: Write the failing tests** in `test_working_hours_table.py`, same style as `test_services_table.py` (each insert in its own session):
  - `test_new_business_timezone_is_asia_kolkata`: after `sign_up_owner()` (which goes through the ORM, so it also proves `[R3]`), `session.get(Business, business_id).timezone == "Asia/Kolkata"`.
  - `test_database_refuses_end_not_after_start` (parametrize `(10:00, 10:00)`, `(18:00, 10:00)`): `IntegrityError` matching `ck_working_hours_end_after_start`.
  - `test_database_refuses_bad_weekday` (parametrize `-1`, `7`): matches `ck_working_hours_weekday_valid`.
  - `test_database_refuses_two_rows_for_one_weekday`: matches `uq_working_hours_business_id_weekday`.
  - `test_database_refuses_same_closed_day_twice`: matches `uq_closed_days_business_id_day`.
  - `test_two_businesses_may_close_the_same_day`: two owners, same date, both inserts succeed.
  - In `test_migrations.py`, add `"working_hours"` and `"closed_days"` to the expected table set.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_working_hours_table.py tests/integration/test_migrations.py -v` → FAIL (import error / missing tables).
- [ ] **Step 3: Implement** the models and migration `0007` (`down_revision = "0006"`): `add_column` `businesses.timezone` (`sa.Text`, `server_default="Asia/Kolkata"`, `nullable=False`), the two `create_table`s (`weekday` as `sa.SmallInteger`) with the constraint names above written by hand, as in 0006. `downgrade` drops both tables and the column. In WSL: `uv add tzdata==2026.6`.
- [ ] **Step 4: Run** the same tests plus `tests/integration/test_tenant_schema.py` and `tests/integration/test_signup.py` → PASS.
- [ ] **Step 5: Commit** `feat(business): working_hours and closed_days tables, Business timezone`.
- [ ] **Checkpoint:** explain the two tables, "closed weekday = no row", and why `time` and not `timestamptz`.

### Task 2: Weekly hours API + nested field errors (CORE: auth, multi-tenancy, validation) — checkpoint after `[R10]`

**Files:**
- Modify: `backend/app/core/errors.py` (`_field_errors`), `backend/tests/unit/test_errors.py`
- Modify: `backend/app/modules/business/schemas.py`, `repository.py`, `service.py`, `router.py`
- Create: `backend/tests/integration/test_working_hours.py`
- Modify: `backend/tests/integration/test_tenant_isolation.py`
- Regenerate: `frontend/openapi.json`, `frontend/src/api/schema.d.ts`

**Interfaces:**
- Consumes: Task 1 models.
- Produces (schemas): `_parse_time(text: str) -> time` (raises `PydanticCustomError("time_invalid", "Use a time like 10:00.")`). `DayIn(start_time: str | None, end_time: str | None)` — both `Field(default=None, validate_default=True)`; `start_time` validator: None → `Enter a start time.`, else `_parse_time`; `end_time` validator: None → `Enter an end time.`, else `_parse_time`, then if `info.data.get("start_time")` exists and end ≤ start → `End time must be after the start time.`. `WeekIn` with required fields `monday … sunday: DayIn | None`. `OpenHours(start_time: time, end_time: time)`. `WorkingHoursOut` with `timezone: str` and `monday … sunday: OpenHours | None`. `WEEKDAYS = ("monday", …, "sunday")` (index = `weekday`).
- Produces (routes, `MANAGE_SETUP`): `GET /api/v1/working-hours` (`get_working_hours` → `WorkingHoursOut`), `PUT /api/v1/working-hours` (`replace_working_hours`, body `WeekIn` → `WorkingHoursOut`).
- Produces (repository): `BusinessRepository.get_current(for_update: bool = False) -> Business`; `WorkingHoursRepository.list_week() -> list[WorkingHours]`, `.replace_week(rows: list[WorkingHours]) -> None` (Core delete first, then `add_all` with `business_id` set, then `flush`), `.for_weekday(weekday: int) -> WorkingHours | None`.

- [ ] **Step 1: Nested field errors (red → green).** In `test_errors.py` add `test_nested_body_field_is_named_by_dotted_path` (fails at `("body", "monday", "end_time")` → field `"monday.end_time"`) and `test_list_position_in_path_is_kept` (`("body", "roles", 0)` → field `"roles.0"`). Keep the broken-JSON test green. Run → FAIL. Change `_field_errors` (rule in Decisions). Run → PASS.
- [ ] **Step 2: Write the failing API tests** in `test_working_hours.py` (`OPEN = {"start_time": "10:00", "end_time": "18:00"}`; `WEEK` = Mon–Sat `OPEN`, Sunday `None`):
  - `test_new_business_has_no_hours`: GET → every day `None`, `timezone == "Asia/Kolkata"`.
  - `test_owner_saves_week_and_reads_it_back`: PUT `WEEK` → 200; GET days equal `{"start_time": "10:00:00", "end_time": "18:00:00"}` for Mon–Sat, Sunday `None`.
  - `test_saving_again_replaces_the_week`: PUT `WEEK` → 200, then PUT with Monday `None` → 200 (no 500), Monday `None`, one DB row fewer. Then PUT the GET response's days back unchanged → 200 (round trip of `"10:00:00"`).
  - `test_end_not_after_start_is_refused_next_to_that_day` (parametrize `10:00/10:00`, `18:00/10:00` on Tuesday) → fields `{"tuesday.end_time": "End time must be after the start time."}`; GET unchanged.
  - `test_missing_times_on_open_day`: Wednesday `{}` → `{"wednesday.start_time": "Enter a start time.", "wednesday.end_time": "Enter an end time."}`.
  - `test_bad_time_refused` (parametrize `"9:00"`, `"24:00"`, `""`, `"bad"`, `"10:60"`, `"10:00:30"`, `"10:00:00.5"`, `"10:00+05:30"` as Monday's start) → exactly `{"monday.start_time": "Use a time like 10:00."}` (no end-time error, no 500).
  - `test_missing_day_key_refused`: body without `"sunday"` → field `sunday` present.
  - `test_staff_and_technician_get_403_on_hours_routes` (parametrize roles as in `test_services.py`): GET and PUT → 403 `FORBIDDEN_BODY`; Owner's week unchanged.
  - `test_logged_out_caller_gets_401`: GET → 401.
- [ ] **Step 3: Write the failing isolation checks** in `test_tenant_isolation.py`, added to `ISOLATION_CHECKS`: `check_get_working_hours` (B saves `WEEK` first; A's GET shows every day `None`), `check_replace_working_hours` (B saves `WEEK`; A PUTs another week; B's GET unchanged).
- [ ] **Step 4: Run** `uv run pytest tests/integration/test_working_hours.py tests/integration/test_tenant_isolation.py -v` → FAIL.
- [ ] **Step 5: Implement** schemas, repositories, service (`get_working_hours`, `replace_working_hours`: Role check first, then `get_current(for_update=True)`, then `replace_week`), routes with `responses=` 401/403/422.
- [ ] **Step 6: Run** `uv run pytest` (whole backend) and `uv run ruff check . && uv run lint-imports` → PASS.
- [ ] **Step 7: Regenerate API types** (WSL: `uv run python -m app.export_openapi ../frontend/openapi.json`; then `npm run gen:api` in `frontend`).
- [ ] **Step 8: Commit** `feat(business): weekly working hours API`.
- [ ] **Checkpoint:** walk through PUT → schema (field validators) → service (Role check, lock) → repository (Core delete, then insert), and the dotted-field change in `core`.

### Task 3: Closed days API + `hours_on` front door (CORE: multi-tenancy, time zones) — checkpoint after `[R10]`

**Files:**
- Modify: `backend/app/modules/business/schemas.py`, `repository.py`, `service.py`, `router.py`
- Modify: `backend/tests/integration/test_working_hours.py`, `test_tenant_isolation.py`
- Regenerate: `frontend/openapi.json`, `frontend/src/api/schema.d.ts`

**Interfaces:**
- Consumes: Task 2 `OpenHours`, `WEEKDAYS`, `BusinessRepository.get_current`, `WorkingHoursRepository.for_weekday`.
- Produces (schemas): `ClosedDayIn(day: str | None = Field(default=None, validate_default=True))` → validator returns a `date` (None, empty, wrong shape, or impossible date → `Pick a date.`). `ClosedDayOut(closed_day_id: UUID, day: date)`. `ClosedDayList(closed_days: list[ClosedDayOut])` (soonest first).
- Produces (routes, `MANAGE_SETUP`): `GET /api/v1/closed-days` (`list_closed_days` → `ClosedDayList`), `POST /api/v1/closed-days` (`add_closed_day`, 201 → `ClosedDayOut`), `DELETE /api/v1/closed-days/{closed_day_id}` (`remove_closed_day`, 204).
- Produces (service): `_today(business: Business) -> date`; `hours_on(session: Session, day: date) -> OpenHours | None` — `None` if `day` is a closed date or its weekday has no row.
- Produces (repository): `ClosedDayRepository.list_from(day: date) -> list[ClosedDay]` (ordered by `day`), `.exists(day: date) -> bool`, `.remove(row: ClosedDay) -> None`.

- [ ] **Step 1: Write the failing tests** in `test_working_hours.py`. A fixture `fixed_today` monkeypatches `business_service._today` to return `date(2026, 12, 1)` (a Tuesday) `[R6]`; dates below are relative to it:
  - `test_owner_adds_lists_and_removes_closed_day`: POST `2026-12-25` → 201; list `== [created]`; DELETE → 204; list `== []`.
  - `test_past_closed_day_refused`: `2026-11-30` → `{"day": "Pick today or a later date."}`; `2026-12-01` (today) → 201.
  - `test_past_rows_are_not_listed` `[R5]`: insert a `ClosedDay` for `2026-11-20` directly in the DB; GET lists only future rows.
  - `test_duplicate_closed_day_refused` → `{"day": "This date is already closed."}`; list has one row.
  - `test_bad_closed_day_refused` (parametrize missing key, `None`, `""`, `"2026-12-25T00:00"`, `"2026-02-30"`, `"25-12-2026"`) → `{"day": "Pick a date."}`.
  - `test_closed_days_listed_soonest_first`.
  - `test_today_uses_business_timezone`: without the monkeypatch, `_today(business)` equals `datetime.now(ZoneInfo("Asia/Kolkata")).date()` (a unit check of the helper).
  - `test_hours_on_uses_weekly_hours_and_closed_days` (inside `tenant_scope`): after PUT `WEEK`: Monday `2026-12-07` → `OpenHours(10:00, 18:00)`; Sunday `2026-12-06` → `None`; after closing `2026-12-07` → `None`.
  - Extend the 403 test to all 5 routes; `test_role_check_runs_before_lookup` (Staff DELETE of a random UUID → 403); `test_unknown_closed_day_id_is_404`; 401 test also GETs `/closed-days`.
- [ ] **Step 2: Write the failing isolation checks:** `check_list_closed_days` (B adds a day first; A's list is empty), `check_add_closed_day` (row's `business_id == owners.a_business_id`; B's list empty), `check_delete_closed_day` (A deletes B's id → 404; B's row stays).
- [ ] **Step 3: Run** → FAIL.
- [ ] **Step 4: Implement.** `add_closed_day`: Role check, `get_current(for_update=True)`, past check against `_today`, `exists` check, `add`; catch `IntegrityError` on `uq_closed_days_business_id_day` → same 422 `[R8]`. Field errors raise `AppError(code="validation_error", message="Some fields need fixing.", status_code=422, fields=[FieldError(field="day", …)])`. `remove_closed_day`: Role check, `get_or_raise`, `remove`.
- [ ] **Step 5: Run** whole backend suite, ruff, lint-imports → PASS. **Step 6:** regenerate API types. **Step 7: Commit** `feat(business): closed days API and hours_on front door`.
- [ ] **Checkpoint:** explain `hours_on` (closed date wins) and why "today" depends on the Business timezone.

### Task 4: Time and date helpers (STANDARD)

**Files:** Create `frontend/src/lib/time.ts`, `frontend/src/lib/time.test.ts`

**Interfaces:**
- Produces: `formatTime(value: string): string` (takes `"HH:MM"` or `"HH:MM:SS"`), `formatTimeRange(start: string, end: string): string`, `formatDate(isoDate: string): string` (takes `"YYYY-MM-DD"`), `toTimeInput(value: string | null): string` (`"10:00:00"` → `"10:00"`, `null` → `""`).

- [ ] **Step 1: Failing tests:** `formatTime("00:00")` → `"12:00 am"`; `"09:05:00"` → `"9:05 am"`; `"12:00"` → `"12:00 pm"`; `"18:00:00"` → `"6:00 pm"`; `"23:59"` → `"11:59 pm"`. `formatTimeRange("10:00:00", "18:00:00")` → `"10:00 am – 6:00 pm"`. `formatDate("2026-12-25")` → `"Fri, 25 Dec"`; `formatDate("2026-11-04")` → `"Wed, 4 Nov"`. `toTimeInput("10:00:00")` → `"10:00"`, `toTimeInput(null)` → `""`.
- [ ] **Step 2: Run** `npx vitest run src/lib/time.test.ts` → FAIL.
- [ ] **Step 3: Implement** by hand: split on `:`; `formatDate` builds `new Date(Date.UTC(y, m - 1, d))` and reads `getUTCDay()` / `getUTCMonth()` from fixed name arrays, so the viewer's own timezone can never shift the date.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(app): time and date formatting helpers`.

### Task 5: Settings → Working Hours page (STANDARD)

**Files:**
- Create: `frontend/src/components/WorkingHoursForm.tsx` + `.test.tsx`
- Create: `frontend/src/components/ClosedDaysSettings.tsx` + `.test.tsx`
- Create: `frontend/src/app/app/settings/hours/page.tsx` (title `Working Hours · SevaDesk`, `<h1>Working Hours</h1>`, renders both components)
- Modify: `frontend/src/lib/pages.ts` (row after Services), `frontend/src/lib/pages.test.ts`

**Interfaces:**
- Consumes: Task 2–3 routes and types (`WeekIn`, `WorkingHoursOut`, `ClosedDayOut`); Task 4 helpers.

- [ ] **Step 1: Failing tests** (mock `api` the way `ServicesSettings.test.tsx` does; change time and date inputs with `fireEvent.change`, as the other tests do `[R11]`):
  - `WorkingHoursForm`:
    - shows a skeleton (`aria-busy`, label `Loading`) until the week arrives (UX-DR25) `[R11]`;
    - shows 7 rows Monday…Sunday; an open day shows an "Open" checkbox ticked, two time inputs, and the text `10:00 am – 6:00 pm`; a closed day shows `Closed` and no time inputs;
    - shows `Times are in Asia/Kolkata.`;
    - ticking "Open" on a closed day shows two EMPTY time boxes `[R11]`;
    - Save sends the full week with closed days as `null`; **an empty time box sends null**;
    - a 422 shows `End time must be after the start time.` under Tuesday's row, and focus moves to the FIRST error in screen order (Monday→Sunday, start before end) `[R11]`;
    - a 422 field with no dot (e.g. `sunday`) shows its message in the general alert at the top `[R11]`;
    - Save is sent once while saving; a load failure shows `Could not load. Please try again.` with "Try again".
  - `ClosedDaysSettings`:
    - shows a skeleton until the list arrives `[R11]`;
    - lists dates as `Fri, 25 Dec`, each with `Remove` (aria-label `Remove Fri, 25 Dec`); an empty list shows `No closed days.`;
    - the date input has no `min` attribute `[R11]`;
    - Add sends `{day: "<input value>"}`; an empty box sends `{day: null}`; a 422 shows the `day` message under the date input;
    - Remove sends DELETE, reloads, and focus moves to the date input (the row is gone) `[R11]`.
  - `pages.test.ts`: CHANGE the existing assertion at `pages.test.ts:81` to `["Services", "Working Hours", "Team", "Appearance"]` (and its test name) `[R11]`; add "the Working Hours link needs manage_setup", like the Services one.
- [ ] **Step 2: Run** `npx vitest run src/components/WorkingHoursForm.test.tsx src/components/ClosedDaysSettings.test.tsx src/lib/pages.test.ts` → FAIL.
- [ ] **Step 3: Implement.** Follow `ServicesSettings` / `ServiceForm`: backend owns rules, buttons are never `disabled` while saving (ignore clicks, set `aria-busy`), inputs `min-h-11`, `<input type="time">` and `<input type="date">`. Map a field `tuesday.end_time` to that day's row by splitting on `.`; a field with no dot goes to the general alert.
- [ ] **Step 4: Run** the full frontend suite, `npm run lint`, `npm run typecheck` → PASS.
- [ ] **Step 5: Commit** `feat(app): Settings → Working Hours page`.

### Task 6: Verify, review, PR

- [ ] Full backend suite (WSL) and frontend suite (Windows) green; `run` the app and check the page by hand at phone width.
- [ ] One Opus whole-branch review (superpowers:requesting-code-review); fix findings, each bug fix with a regression test.
- [ ] Set `3-2-set-working-hours-and-closed-days: done` in `sprint-status.yaml` on the branch.
- [ ] Push, open PR (body ends `Closes #15`), wait for 4 green checks.
- [ ] Then `docs/agents/after-story.md` (Understanding Gate, hands-on task, learning notes).
