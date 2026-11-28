# Story 5.2 — Create a Booking for a phone-in Customer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (CLAUDE.md: native build in this session). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Owner or Staff member creates a `confirmed` Booking for a phone-in Customer (name + phone) or from an open Conversation, and two people can never take the last free Slot at the same time.

**Architecture:** `bookings` owns the one write path, `create_confirmed`. It takes a Postgres transaction-level advisory lock for the Business first, then recounts the free Slots (the same code that lists them), then checks the Technician. `inbox` owns both entry flows: it calls `bookings.take_capacity_lock` BEFORE it reads or writes its own rows (find-or-create the Customer by phone), then calls `bookings.create_confirmed`. A small `BookingSheet` in the frontend uses these routes from the Calendar page and from a Conversation.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres 18 (`pg_advisory_xact_lock`, `hashtext`), pytest + Testcontainers, threads for the race tests, Next.js + vitest.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 5.2: Create a Booking for a phone-in Customer". Rules: FR-25, FR-27, AR-2, AR-4, AR-10, AR-14, AR-23, UX-DR29 (same file). AD-9, AD-13 and AD-15 in `_bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md` (lines ~121–170).

## Global Constraints

- Backend tests run in WSL: `wsl --cd "/mnt/c/Books/DataSense Community/Seva Desk/backend" uv run pytest ...`. Frontend runs in Windows PowerShell: `npx vitest run ...`, `npm run typecheck`, `npm run lint`. Commit with Windows git.
- `bookings` never imports `inbox`. `inbox` uses `bookings` only through `bookings/service.py` and `bookings/schemas.py` (AR-2; add an import-linter contract).
- Services never commit; the request owns the one transaction (AD-15).
- The capacity lock is `pg_advisory_xact_lock(BOOKINGS_LOCK_NAMESPACE, hashtext(business_id::text))`, transaction-level only, never session-level (AD-9). It is the FIRST lock a capacity write takes, and in the inbox flows it comes before any read of `customers` or `conversations`.
- Only `accounts` says who is an active Technician (AR-7).
- Name and phone are personal data: never in trace events, logs, or error messages (AD-13).
- Times: `timestamptz` UTC; requests must send timezone-aware datetimes (AR-5). Money: `price_paise` from the Service (AR-5).
- Definition of Done "traces visible": a new write adds one trace event with no personal data (pattern: `trace.get_current_span().add_event(...)` in `inbox/service.py`).
- Error messages for Pydantic validators use `PydanticCustomError` (as in `accounts/emails.py:17`), never a bare `ValueError` (Pydantic prefixes it with "Value error, ").

## Decisions this plan makes

- **`bookings.service_id` is added now, NOT NULL**, with a composite FK to `services`. Why: a Booking is "for a Service"; the Calendar (5.4) shows its name; the price and duration come from it. The table has no rows anywhere yet (no write path existed), so NOT NULL is safe.
- **`customers.name` and `customers.phone` are added now, both nullable** (chat Customers have neither yet). `UNIQUE (business_id, phone)`: NULLs never clash.
- **Phone rule:** a valid Indian mobile number (PRD FR-16). Remove spaces, `-`, `(`, `)`. Then match ASCII digits only (`[0-9]`, never `\d`: `\d` also matches Devanagari digits, and one phone could be stored two ways): 10 digits starting 6–9, with an optional `+91`, `91`, or `0` in front. Store as `+91XXXXXXXXXX`. Anything else → 422 on `customer_phone`, message "Enter a valid Indian mobile number.".
- **Name rule:** strip; 1–100 characters; refuse Cc/Cs characters with the same check as `SendMessageIn` (`inbox/schemas.py:18-22`; reuse it, do not copy it). Message "Enter the customer's name.".
- **Found by phone → use that Customer as it is** (keep its stored name).
- **"A free Slot" = one of the Slots `list_free_slots` would show now** for that Service (grid, open hours, not past, within 7 days, capacity). The recount reuses that code. Not in the list → `SlotUnavailable`.
- **Technician choice:** none given + exactly 1 active Technician → that one. None given + 2 or more → 422 `technician_membership_id` "Pick a Technician.". Given but not an active Technician of THIS Business → 422 "Pick an active Technician.". Given and already has an overlapping confirmed Booking → `TechnicianBusy`.
- **Errors:** `SlotUnavailable` 409 `slot_unavailable` "This time is no longer free. Pick another time." · `TechnicianBusy` 409 `technician_busy` "This Technician already has a job at this time. Pick another Technician or time." · 422 field errors use the normal envelope (`validation_error`, "Some fields need fixing.").
- **Double submit:** no idempotency key. A second identical POST meets the recount and gets `slot_unavailable` (one Technician) or `technician_busy`; never a second Booking. A test pins this.
- **Booking from a Conversation in any state** (agent, handoff, closed) is allowed. The spec puts no limit on it. The Conversation state does not change.
- **Lock namespace:** `BOOKINGS_LOCK_NAMESPACE = 1001` (any fixed int; it keeps our lock apart from other advisory locks).
- **Routes:** `POST /api/v1/inbox/phone-bookings` (phone-in), `POST /api/v1/inbox/conversations/{conversation_id}/bookings` (from a chat), `GET /api/v1/bookings/options` (form facts: active Services + active Technicians, for Owner AND Staff; the Settings Services list is Owner-only). All need `USE_INBOX_AND_BOOKINGS`.
- **Staff see Technician emails** in the picker (Users have no names yet). They are team mates of the same Business; the full team list stays Owner-only.
- **Trace event:** `booking.created` with only `{"state": "confirmed", "from_conversation": bool}`.
- **Known gap, owned by Story 5.5 (stated, not fixed here):** after this story, Delete Customer fails (500, FK violation) for a chat Customer who has a Booking, because `bookings.delete_for_customer` does not exist yet (`inbox/service.py:400`). 5.5 builds it. In 5.5 the capacity lock must come BEFORE `customers.lock` in `delete_customer`, or it deadlocks with this story's from-chat flow. This story updates the comment at `inbox/service.py:400` to say so, and the PR text lists the gap.
- **Frontend is in scope** (the AC's "no picker is shown"): one `BookingSheet`. Out of scope: the Customer's Chat Page showing the confirmed time (Epic 6), Calendar views (5.4), cancel/complete (5.3), delete (5.5), Customer names in Inbox rows.

## Review Focus

1. **Two phone-ins with the same NEW phone at the same moment.** Expected: both 201, one Customer row (no unique-violation 500). → Task 4 `test_same_new_phone_at_once_makes_one_customer`.
2. **Double submit** (the form is tapped twice). Expected: one Booking; the second gets 409. → Task 4 `test_second_identical_post_does_not_double_book`.
3. **A time that is not a real Slot** (off the 30-min grid, a closed day, past, beyond 7 days). Expected: `SlotUnavailable`, nothing saved. → Task 2 `test_time_off_the_grid_is_unavailable`.
4. **The same phone typed different ways, or with Devanagari digits.** Expected: one Customer; non-ASCII digits refused. → Task 4 unit `test_normalize_phone` and `test_phone_formats_find_one_customer`.
5. **A time without a timezone** (`2026-11-30T10:00:00`). Expected: 422, not a guess. → Task 4 `test_naive_time_is_refused`.

---

## File map

| File | Tag | Job |
|---|---|---|
| `backend/migrations/versions/0012_booking_service_and_customer_phone.py` | BOILERPLATE | new columns, FK, unique |
| `backend/app/modules/bookings/models.py` | CORE | `service_id` |
| `backend/app/modules/inbox/models.py` | STANDARD | `Customer.name`, `Customer.phone` |
| `backend/app/modules/bookings/repository.py` | CORE | `take_capacity_lock`, `technician_busy` |
| `backend/app/modules/bookings/service.py` | CORE | `take_capacity_lock`, `create_confirmed`, `booking_options`, errors |
| `backend/app/modules/bookings/schemas.py` | STANDARD | `NewBooking`, `BookingOut`, `BookingOptionsOut` |
| `backend/app/modules/bookings/router.py` | STANDARD | `GET /options` |
| `backend/app/modules/accounts/service.py`, `repository.py`, `schemas.py` | STANDARD | `active_technicians` (ids + emails) |
| `backend/app/modules/inbox/service.py` | CORE | `create_phone_booking`, `create_conversation_booking`; the 5.5 comment |
| `backend/app/modules/inbox/schemas.py` | STANDARD | `normalize_phone`, name check, `PhoneBookingIn`, `ConversationBookingIn` |
| `backend/app/modules/inbox/repository.py` | STANDARD | `CustomerRepository.find_by_phone` |
| `backend/app/modules/inbox/router.py` | STANDARD | two POST routes |
| `backend/pyproject.toml` | BOILERPLATE | contract "inbox uses bookings only through its front door" |
| `backend/tests/integration/booking_helpers.py` | STANDARD | shared clock fixture, `make_shop`, `book` for 5.2 tests |
| `backend/tests/integration/test_tenant_isolation.py` | STANDARD | 3 new checks |
| `frontend/src/lib/time.ts` (+ test) | STANDARD | `formatSlot` |
| `frontend/src/components/BookingSheet.tsx` (+ test) | STANDARD | the form |
| `frontend/src/components/NewBookingButton.tsx` | BOILERPLATE | client wrapper for the Calendar page |
| `frontend/src/app/app/calendar/page.tsx`, `frontend/src/components/ConversationView.tsx` (+ its test) | BOILERPLATE | place the buttons |
| `frontend/openapi.json`, `frontend/src/api/schema.d.ts` | BOILERPLATE | regenerated |

---

### Task 1: New columns (CORE)

**Files:**
- Create: `backend/migrations/versions/0012_booking_service_and_customer_phone.py`
- Modify: `backend/app/modules/bookings/models.py`, `backend/app/modules/inbox/models.py`, every test helper that inserts a `Booking` directly (`grep -rn "Booking(" backend/tests`; at least `_book` in `test_free_slots.py`): give it a real `service_id`.
- Test: `backend/tests/integration/test_bookings_table.py`, `backend/tests/integration/test_inbox_tables.py`

**Interfaces:**
- Produces: `Booking.service_id: Mapped[uuid.UUID]` (NOT NULL), FK `fk_bookings_business_id_services` `(business_id, service_id) → services(business_id, id)`. `Customer.name: Mapped[str | None]`, `Customer.phone: Mapped[str | None]`, `UniqueConstraint("business_id", "phone")` named `uq_customers_business_id_phone`.

- [ ] **Step 1: Write the failing tests**
  - `test_booking_needs_a_service`: insert a Booking with `service_id=None` → `IntegrityError`.
  - `test_booking_cannot_point_at_another_business_service`: Business A Booking with Business B's `service_id` → `IntegrityError`.
  - `test_phone_is_unique_per_business`: two Customers, same Business, same phone → `IntegrityError`; same phone in two Businesses → both saved; two Customers with `phone=None` → both saved.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_bookings_table.py tests/integration/test_inbox_tables.py -v` → FAIL (no such column).
- [ ] **Step 3: Write migration 0012** (`down_revision = "0011"`; `add_column` + `create_foreign_key` + `create_unique_constraint`; downgrade drops them in reverse). Add the columns and constraints to the two models, with comments on why.
- [ ] **Step 4: Run** the two files, `test_migrations.py`, `test_tenant_schema.py`, `test_free_slots.py` → PASS.
- [ ] **Step 5: Commit** `feat(bookings): add service_id to bookings and name/phone to customers (story 5.2)`

---

### Task 2: `create_confirmed`: the recount and the Technician (CORE) — checkpoint after

**Files:**
- Create: `backend/tests/integration/booking_helpers.py`
- Modify: `backend/app/modules/bookings/service.py`, `repository.py`, `schemas.py`; `backend/tests/integration/test_free_slots.py` (use the shared helpers)
- Test: `backend/tests/integration/test_create_booking.py` (calls the front door directly)

**Test helpers (fix first, because `membership_of` raises once a Business has 2 members, and `fixed_clock` is autouse only inside `test_free_slots.py`):**
- Move to `booking_helpers.py`: `NOW`, `TZ`, `MON_10`, `HOUR`, a `fixed_clock` fixture (each test file that needs it imports it by name or lists it in `pytestmark = pytest.mark.usefixtures("fixed_clock")`), `make_shop(sign_up_owner) -> (client, business_id, service_id)`, and `book(business_id, service_id, start, state, technician_id, expires_at=None, customer_id=None) -> uuid.UUID` (commits; makes a Customer when none is given; returns the Booking id).
- Actors come from `owner_actor(business_id)` (`test_inbox_reply.py:30`, move it to `booking_helpers.py` or `conftest.py`) or from an `invite_member` `Member`, never from `membership_of` in a 2-member Business.

**Interfaces:**
- Consumes: `business_service.get_active_service`, `accounts_service.active_technician_ids`, `free_slots` (5.1).
- Produces:
  - `class NewBooking(BaseModel)`: `customer_id: UUID`, `conversation_id: UUID | None`, `service_id: UUID`, `starts_at: AwareDatetime`, `technician_membership_id: UUID | None`.
  - `class BookingOut(BaseModel)`: `booking_id`, `state`, `starts_at`, `ends_at`, `service_id`, `customer_id`, `conversation_id`, `technician_membership_id`, `price_paise`.
  - `create_confirmed(session: Session, actor: Actor, data: NewBooking) -> BookingOut` in `bookings/service.py`.
  - `class SlotUnavailable(AppError)`, `class TechnicianBusy(AppError)` in `bookings/service.py` (codes and texts: see Decisions).
  - `BookingRepository.technician_busy(technician_id: UUID, start: datetime, end: datetime) -> bool` (overlapping `confirmed` Bookings of that Technician; half-open overlap like `slots._overlaps`).
- Refactor first: move the body of `list_free_slots` after the Role check into `_free_slots(session, service: ServiceOut, now) -> list[SlotOut]`, so the list and the recount use ONE code path.

Order inside `create_confirmed`: Role check → active Service (404) → recount: `starts_at` must equal the `start` of one of `_free_slots(...)` → choose Technician → `technician_busy` → `add(Booking(state="confirmed", ends_at=starts_at + duration, price_paise=service.price_paise, expires_at=None, ...))` → trace event `booking.created`.

- [ ] **Step 1: Write the failing tests** (each one line on its behaviour before you write it):
  - `test_saves_a_confirmed_booking`: one-Technician shop, `MON_10`, no Technician given → `state == "confirmed"`, Technician = the Owner's membership, `ends_at == MON_10 + 1h`, `price_paise == SERVICE price`, `conversation_id is None`; and `MON_10` is gone from `list_free_slots`.
  - `test_full_slot_is_unavailable`: `book(MON_10, "confirmed")` first → `SlotUnavailable`.
  - `test_live_request_takes_capacity`: `book(MON_10, "requested", expires_at=NOW + 1h)` → `SlotUnavailable`.
  - `test_time_off_the_grid_is_unavailable`: `MON_10 + 10 min`, a Sunday 10:00, a time before `NOW`, and `NOW + 8 days` → `SlotUnavailable` each; no Booking saved.
  - `test_two_technicians_need_a_pick`: invite a second Technician (`invite_member`) → no Technician given → `AppError` 422 with field `technician_membership_id`.
  - `test_inactive_technician_is_refused`: a deactivated member's id → 422 "Pick an active Technician.".
  - `test_busy_technician_is_refused`: two Technicians, Technician X has a confirmed Booking at `MON_10`, book X again at `MON_10` → `TechnicianBusy` (capacity is still free: 1 of 2).
  - `test_technician_only_user_is_forbidden`: actor roles `{TECHNICIAN}` → `Forbidden`.
  - `test_other_business_service_is_not_found` → `NotFound`.
  - `test_booking_created_trace_event`: with the `spans` fixture (pattern: `test_inbox_reply.py:284`), one `booking.created` event with exactly the attributes `state`, `from_conversation`.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_create_booking.py -v` → FAIL (`create_confirmed` missing).
- [ ] **Step 3: Implement** the helpers move, the refactor, the schemas, the errors, `technician_busy`, and `create_confirmed`. No lock yet (Task 3 adds it, test-first).
- [ ] **Step 4: Run** the file and `test_free_slots.py` → PASS.
- [ ] **Step 5: Commit** `feat(bookings): create a confirmed Booking with recount and Technician check (story 5.2)`
- [ ] **CHECKPOINT:** stop; explain the recount and the Technician rule to the user.

---

### Task 3: The capacity lock (CORE) — checkpoint after

**Files:**
- Modify: `backend/app/modules/bookings/repository.py`, `service.py`
- Test: `backend/tests/integration/test_booking_race.py`

**Interfaces:**
- Produces: `BOOKINGS_LOCK_NAMESPACE = 1001`; `BookingRepository.take_capacity_lock() -> None` (executes `select(func.pg_advisory_xact_lock(BOOKINGS_LOCK_NAMESPACE, func.hashtext(str(current_business_id()))))`); front door `take_capacity_lock(session: Session) -> None` in `bookings/service.py`. `create_confirmed` calls it right after the Role check, before any read. Taking it twice in one transaction is fine (Postgres stacks it; both release at commit).

**Race-test rules (so the test really goes red without the lock):**
- Make every Customer in its own COMMITTED transaction before the race starts.
- Session 1: `Session(get_engine())`, `begin()`, `tenant_scope`, call `create_confirmed`, do NOT commit yet.
- The thread: `with Session(get_engine()) as s, s.begin(), tenant_scope(business_id):` (its own scope inside the thread: context vars do not cross threads), call `create_confirmed`; leaving the `with` commits a success. Store the result or the exception.
- Wait with the existing pattern (`test_inbox_delete_customer.py:137-170`): `thread.join(1)`, then assert `thread.is_alive()` (it waits on the lock). Then commit session 1 and `thread.join(10)`.

- [ ] **Step 1: Write the failing tests** (one-Technician shop, `MON_10`):
  - `test_two_people_book_the_last_slot_one_wins`: asserts: the thread was alive (waiting) before session 1 committed; then it got `SlotUnavailable`; exactly 1 `confirmed` Booking at `MON_10` in the database.
  - `test_lock_is_per_business`: Business A's session 1 holds its Booking uncommitted; a thread books Business B's `MON_10`; `thread.join(2)` while A is still open → the thread already finished with success (a global lock key would make it wait). Then commit A. Both Bookings exist.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_booking_race.py -v` → the first test FAILS (the thread is not waiting, and 2 Bookings are saved: no lock, so both recounts see 0). The second passes already; that is expected (it guards the key choice in Step 3).
- [ ] **Step 3: Implement** `take_capacity_lock` and call it first in `create_confirmed`. Comment why `xact` (released at commit/rollback, can never leak) and why first (AD-15).
- [ ] **Step 4: Run** the file 3 times in a row and `test_create_booking.py` → PASS every time.
- [ ] **Step 5: Commit** `feat(bookings): take the per-Business capacity lock before the recount (story 5.2, AD-9)`
- [ ] **CHECKPOINT:** stop; walk the user through the two-session timeline.

---

### Task 4: The inbox flows, routes, and their isolation checks (CORE) — checkpoint after

**Files:**
- Modify: `backend/app/modules/inbox/service.py` (also the comment at line ~400: see "Known gap"), `schemas.py`, `repository.py`, `router.py`, `backend/pyproject.toml`, `backend/tests/integration/test_tenant_isolation.py`
- Test: `backend/tests/unit/test_inbox_schemas.py`, `backend/tests/integration/test_phone_booking.py`, `backend/tests/integration/test_phone_booking_lock_order.py`

**Interfaces:**
- Consumes: `bookings_service.take_capacity_lock`, `bookings_service.create_confirmed`, `NewBooking`, `BookingOut`.
- Produces:
  - `normalize_phone(raw: str) -> str` in `inbox/schemas.py` (rule: see Decisions; raises `PydanticCustomError("phone_invalid", "Enter a valid Indian mobile number.")`).
  - `PhoneBookingIn`: `customer_name: str` (name rule: see Decisions), `customer_phone: str` (validated by `normalize_phone`), `service_id: UUID`, `starts_at: AwareDatetime`, `technician_membership_id: UUID | None = None`.
  - `ConversationBookingIn`: the same without the two customer fields.
  - `CustomerRepository.find_by_phone(phone: str) -> Customer | None`.
  - `create_phone_booking(session, actor, data: PhoneBookingIn) -> BookingOut` and `create_conversation_booking(session, actor, conversation_id: UUID, data: ConversationBookingIn) -> BookingOut` in `inbox/service.py`. Order in both: Role check → `bookings_service.take_capacity_lock` → own reads/writes (find-or-create Customer / `get_or_raise` the Conversation) → `create_confirmed`. No trace event with name or phone.
  - Routes (201, `operation_id`s `create_phone_booking`, `create_conversation_booking`, responses 401/403/404/409/422).
  - import-linter contract: `inbox` imports from `app.modules.bookings` only `service` and `schemas`.

- [ ] **Step 1: Write the failing tests**
  - Unit `test_normalize_phone`: `"98765 43210"`, `"+91-98765-43210"`, `"09876543210"`, `"919876543210"` → `"+919876543210"`; `"12345"`, `"5876543210"`, `"+1 9876543210"`, `"९८७६५४३२१०"` (Devanagari digits) → error.
  - Unit `test_customer_name_rules`: `"  Asha  "` → `"Asha"`; `""`, `"   "`, 101 characters, and `"As\x00ha"` → error.
  - `test_phone_in_booking_is_confirmed_without_conversation` (HTTP, Owner): 201, `state == "confirmed"`, `conversation_id is None`; a Customer row has that name and `+91…` phone.
  - `test_phone_formats_find_one_customer`: book twice (two Slots) with two spellings of one phone → same `customer_id`, one Customer row.
  - `test_found_customer_keeps_its_name`: second booking with the same phone and another name → the Customer's name is still the first one.
  - `test_same_new_phone_at_once_makes_one_customer`: two threads (the Task 3 pattern), same new phone, two different Slots → both 201, one Customer row.
  - `test_second_identical_post_does_not_double_book`: the same POST twice → first 201, second 409; one Booking.
  - `test_booking_from_a_conversation`: a chat Conversation (use the existing chat send helper) → 201, `conversation_id` and `customer_id` are that Conversation's; its state did not change.
  - `test_staff_can_book` and `test_technician_only_gets_403`.
  - `test_taken_slot_gives_409`: body `error.code == "slot_unavailable"` and the exact message from Decisions.
  - `test_bad_phone_gives_422_on_the_field`: field `customer_phone`, message exactly "Enter a valid Indian mobile number." (no "Value error, ").
  - `test_naive_time_is_refused` (422).
  - Lock order (AR-23) `test_phone_in_takes_the_capacity_lock_before_touching_customers`: record statements with `event.listen(get_engine(), "before_cursor_execute", ...)` during the POST, and `event.remove` it in a `finally`. Assert the first `pg_advisory_xact_lock` statement comes before the first statement that mentions `customers` (the SELECT and the INSERT). Comment the bug it prevents: if the lookup ran before the lock, two phone-ins with one new phone both find nothing, and the second INSERT hits the unique rule (a 500).
  - Isolation checks (added to `ISOLATION_CHECKS`): A's phone-in with B's `service_id` → 404, B has no new Booking; A's phone-in with B's Technician id → 422, nothing saved; A's phone-in with a phone that one of B's Customers has → A gets its own new Customer, B's row unchanged; A's conversation booking with B's `conversation_id` → 404, B has no new Booking.
- [ ] **Step 2: Run** them → FAIL.
- [ ] **Step 3: Implement** schemas, repository method, the two service functions, the routes, the contract, and the 5.5 comment.
- [ ] **Step 4: Run** the three files, `test_tenant_isolation.py`, and `uv run lint-imports` → PASS.
- [ ] **Step 5: Commit** `feat(inbox): phone-in and from-chat Bookings, capacity lock first (story 5.2, AD-15)`
- [ ] **CHECKPOINT:** stop; explain the lock-order test.

---

### Task 5: Form facts route (STANDARD)

**Files:**
- Modify: `backend/app/modules/accounts/repository.py`, `service.py`, `schemas.py`; `backend/app/modules/bookings/service.py`, `schemas.py`, `router.py`; `backend/tests/integration/test_tenant_isolation.py`; `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (regenerate with `app.export_openapi` and the project's existing type-generation script)
- Test: `backend/tests/integration/test_create_booking.py` (options tests), `test_tenant_isolation.py`

**Interfaces:**
- Produces: `TechnicianOut(membership_id: UUID, email: str)` in `accounts/schemas.py`; `accounts_service.active_technicians(session) -> list[TechnicianOut]`, with the SAME filter and order as `active_technician_ids` (one shared query in the repository, so "active Technician" is still defined once). `BookingOptionsOut(services: list[ServiceOut], technicians: list[TechnicianOut])`; `bookings_service.booking_options(session, actor) -> BookingOptionsOut`; `GET /api/v1/bookings/options` (`operation_id="get_booking_options"`).

- [ ] **Step 1: Write the failing tests**: `test_options_list_active_services_and_technicians` (an inactive Service and a deactivated member are left out; Staff gets 200; Technician-only gets 403). Isolation check: A's options show none of B's Services or Technicians.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; regenerate the OpenAPI file and TS types.
- [ ] **Step 4: Run** the whole backend suite `uv run pytest` and `uv run lint-imports` → PASS.
- [ ] **Step 5: Commit** `feat(bookings): booking form options (story 5.2)`

---

### Task 6: `BookingSheet` (STANDARD)

**Files:**
- Create: `frontend/src/components/BookingSheet.tsx`, `frontend/src/components/BookingSheet.test.tsx`, `frontend/src/components/NewBookingButton.tsx`
- Modify: `frontend/src/lib/time.ts` + `frontend/src/lib/time.test.ts` (`formatSlot`), `frontend/src/app/app/calendar/page.tsx` (renders `<NewBookingButton />`; the page stays a server component because it exports `metadata`), `frontend/src/components/ConversationView.tsx` ("Book" button next to `CustomerSheet`), `frontend/src/components/ConversationView.test.tsx` (only if its `api` mock needs the new calls)

**Interfaces:**
- Consumes: `GET /api/v1/bookings/options`, `GET /api/v1/bookings/slots`, the two POST routes; existing `Sheet`, `Button`, `Input`, `Label`, `useLoad`, `errorsForFields`, `lib/money.ts`, `usePermissions`.
- Produces:
  - `formatSlot(iso: string, timeZone: string): string` in `lib/time.ts`, e.g. `"Mon 30 Nov, 10:00 am"` in the Business timezone (en-IN).
  - `BookingSheet({ conversationId }: { conversationId?: string })`. Shows only with permission `use_inbox_and_bookings`. The trigger button opens the sheet; options and Slots load only while it is open (like `CustomerSheet`), so pages that render it do not fetch on mount.
  - Fields: name + phone (only without `conversationId`); Service as a native `<select>`; Slot as a native `<select>` (loads after a Service is chosen, labels from `formatSlot` with the response's `timezone`); Technician `<select>` only when `technicians.length > 1` (UX-DR29), labels = emails.
  - Submit: `aria-disabled` while a request is in flight (a second tap does nothing). Success: the text "Booked: {Service}, {formatSlot}." 409: show the server message and reload the Slots. 422: field errors next to fields via `errorsForFields`.
  - `NewBookingButton`: a `"use client"` wrapper that renders `<BookingSheet />`.

- [ ] **Step 1: Write the failing tests** (mock `api` like `CustomerSheet.test.tsx`): `formatSlot shows the Business time`; `no Technician picker with one Technician`; `Technician picker with two`; `phone-in posts name, phone, service, slot`; `from a chat posts to the conversation route without name and phone`; `taken Slot shows the message and reloads Slots`; `bad phone shows the field error`; `a second tap while saving sends one request`; `nothing loads until the sheet opens`.
- [ ] **Step 2: Run** `npx vitest run src/components/BookingSheet.test.tsx src/lib/time.test.ts` → FAIL.
- [ ] **Step 3: Implement** `formatSlot`, the component, `NewBookingButton`, and place the two buttons.
- [ ] **Step 4: Run** `npx vitest run`, `npm run typecheck`, `npm run lint` → PASS.
- [ ] **Step 5: Commit** `feat(frontend): BookingSheet for phone-in and from-chat Bookings (story 5.2)`

---

### Finish

- [ ] Set `5-2-create-a-booking-for-a-phone-in-customer: done` in `_bmad-output/implementation-artifacts/sprint-status.yaml` on this branch.
- [ ] Whole-branch review by an Opus subagent; fix findings (each bug fix with a regression test).
- [ ] Open the PR (`Closes #23`). The PR text lists the known gap (Delete Customer with a Booking → 5.5). Then `docs/agents/after-story.md`.
