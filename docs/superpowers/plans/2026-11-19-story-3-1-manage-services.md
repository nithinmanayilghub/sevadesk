# Story 3.1 — Manage Services with Prices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, per CLAUDE.md §4: build in this session, stop after each CORE task, one Opus whole-branch review at the end). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On Settings → Services, the Owner adds, edits, deactivates, and reactivates Services (name, duration 30–480 min, required Price). Prices are stored as integer paise and shown with Indian grouping (₹1,499, ₹1,00,000).

**Architecture:** The `business` module owns a new tenant table `services` (AR-1). Its repository extends the `core` `TenantRepository`, so the tenant filter is automatic (AR-6). Three Owner-only routes live in `business/router.py`: list, create, replace (`PUT`). Deactivate = a `PUT` with `is_active: false`; there is no delete. One input schema (`ServiceIn`) serves create and replace, so "save" and "activate" pass the same rules (FR-12). The front door `business.service.list_active_services()` gives later stories (Chat Page, Agent) only active Services. The frontend gets `lib/money.ts` (paise ↔ rupees) and a Services page registered in `lib/pages.ts`.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, pytest + testcontainers; Next.js 16, React 19, Tailwind 4, Vitest, openapi-typescript.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 3.1: Manage Services with Prices" (line 618). Also FR-12 (`prd.md:159`), AR-1 / AR-5 / AR-6 (`epics.md:94-101`), UX-DR4 (`epics.md:133`), UX-DR33 (`epics.md:170`), EXPERIENCE.md line 40 (route `/app/settings/services`, Owner, from "More") and line 55 ("from ₹X"), ARCHITECTURE-SPINE.md line 30 (`business` owns services + prices) and line 213 (money = integer `*_paise`, never floats).

## Global Constraints

- Table `services`, owned by `business`. Tenant table: `business_id`, `UNIQUE (business_id, id)`, UUIDv7 `id`.
- Money: integer column `price_paise`. Never floats. The API sends and receives paise.
- Duration: integer minutes, 30 to 480 inclusive.
- Price: required, 1 paise to 10,00,00,000 paise (₹10,00,000). The cap keeps the value well inside Postgres `integer` (max 2,147,483,647).
- Number fields are `StrictInt`: JSON `true`, `"60"` and `60.0` are refused.
- No delete. Deactivate sets `is_active = false`. A deactivated Service is not returned by `list_active_services`.
- Role: `Permission.MANAGE_SETUP` (Owner only) for every Services route, checked FIRST (before any read).
- Field error copy, verbatim:
  - name empty (or contains `\x00`): `Enter a name for the Service.` · name > 100 chars: `Use at most 100 characters.`
  - duration missing: `Enter a duration in minutes.` · out of range: `Use 30 to 480 minutes.`
  - price missing: `Enter a Price in rupees, for example 499.` · ≤ 0: `Enter a Price above ₹0.` · too big: `Use at most ₹10,00,000.`
- Money display: Indian grouping, `₹` sign, no decimals for whole rupees (`₹1,499`, `₹1,00,000`); two decimals otherwise (`₹499.50`).
- Route `/app/settings/services`, label `Services`, `needs: "manage_setup"`, listed in `PAGES` BEFORE Team.
- Every new route is listed in `tests/integration/test_tenant_isolation.py` `ISOLATION_CHECKS`, or CI fails.
- `frontend/openapi.json` and `src/api/schema.d.ts` are regenerated in WSL (CI runs `git diff --exit-code`), in the SAME commit as the routes.
- Backend commands run in WSL: `wsl --cd "C:\Books\DataSense Community\Seva Desk\backend" -e bash -lc "uv run pytest …"`. Docker Desktop must run.
- Branch `story/3-1-manage-services`. PR body ends with `Closes #14`.

## Decisions made in this plan

- **`PUT` (replace the whole Service) instead of `PATCH`.** The edit form and the Deactivate button both have the full row, so they send all fields. One schema, one set of rules, no "left out means keep" logic. It also makes "activate" run the same Price check as "save" (FR-12).
- **Every `ServiceIn` field is required, `is_active` too.** A full replace must not quietly turn a Service back on. The add form sends `is_active: true`.
- **Routes go in `business/router.py` and logic in `business/service.py`.** `service.py` is the front door; the Chat Page and the Agent will call `list_active_services` there later. No new file pair like `team.py` / `team_router.py`: the module is still small.
- **`price_paise` and `duration_minutes` are `StrictInt | None` with `Field(default=None, validate_default=True)`.** So an empty field (sent as `null`, or left out) gets our own message next to the field, not the generic "This field is required." (Verified in the real venv: both cases give the custom message at loc `("price_paise",)`.)
- **The frontend turns bad Price or Duration text into `null`.** Then the backend answers with its own message. The backend stays the one owner of every rule.
- **`GET /api/v1/services` returns `{"services": [...]}`**, the same shape as `TeamResponse`, so fields can be added later without breaking the frontend. Owner-only for now: only the Owner's settings page uses it. Later stories read Services through the front door, not this route.
- **"from ₹X" is for Customers and the Agent** (EXPERIENCE.md:55, FR-12). The Owner's own price list on Settings shows the plain Price (`₹1,499`): it is the Owner's data, not an offer.
- **The 30 / 480 / 100000000 numbers live in `models.py` constants.** The model's CHECK text is built from them with an f-string; `schemas.py` imports them. The migration keeps plain numbers on purpose: a migration is a frozen snapshot and must not change when code changes.
- **Row buttons are never `disabled` while a change runs.** A disabled button drops keyboard focus to `<body>` (the Story 2.6 bug, fixed in `92339c6`). Clicks are ignored while busy and the list gets `aria-busy`, as in `AppearanceSettings`.
- **Not in this story:** unique Service names, sorting, delete, durations in hours ("1 h 30 min"), "Load more" paging.

## Review Focus

1. **The Owner clears the Price while editing** → `422` with `Enter a Price in rupees, for example 499.` on `price_paise`, and the saved row is unchanged. → Task 2 test `test_edit_without_price_is_refused_and_keeps_old_row`.
2. **The Owner types `1,499` or `499.50` or `abc` in Price, or leaves Duration blank** → paise `149900`, `49950`, `null`; duration `null`. → Task 3 `rupeesToPaise` tests, Task 4 `an empty duration sends null`.
3. **A Price above the Postgres limit (`2**31`, `10**15`)** → `422` `Use at most ₹10,00,000.`, never a `500`. → Task 2 test `test_price_above_cap_is_refused`.
4. **The Owner double-clicks "Add Service"** → only one POST goes out. → Task 4 test `add is sent once while saving`.
5. **Owner A sends Owner B's `service_id`** → `404`, and B's row is unchanged. → Task 2 isolation check `check_replace_service`.

---

### Task 0: Start the story (no code)

- [ ] Show the Story Map (CLAUDE.md §2) and get the user's prediction.
- [ ] `git switch -c story/3-1-manage-services` from an up-to-date `main`. `gh issue edit 14 --add-label in-progress`.
- [ ] `_bmad-output/implementation-artifacts/sprint-status.yaml`: `epic-3: in-progress`, `3-1-manage-services-with-prices: in-progress`.
- [ ] Commit this plan, `docs/learning/gaps.md` (Epic 3 quiz results) and `sprint-status.yaml`: `docs: Story 3.1 plan, status in-progress`.

---

### Task 1: The `services` table (CORE: data model, multi-tenancy) — checkpoint after

**Files:**
- Modify: `backend/app/modules/business/models.py` (add `Service` and constants)
- Create: `backend/migrations/versions/0006_services.py`
- Modify: `backend/tests/integration/test_migrations.py` (add `"services"` to the table set)
- Test: `backend/tests/integration/test_services_table.py` (new)

**Interfaces:**
- Produces: constants in `models.py`: `MIN_DURATION = 30`, `MAX_DURATION = 480`, `MAX_PRICE_PAISE = 100_000_000`.
- Produces: `class Service(TenantModel)`, `__tablename__ = "services"`, columns `id: uuid.UUID` (pk, `default=uuid.uuid7`), `name: str` (`Text`), `duration_minutes: int`, `price_paise: int`, `is_active: bool` (`server_default="true"`), `created_at` (timestamptz, `server_default=func.now()`). `__table_args__`: `UniqueConstraint("business_id", "id")`, `CheckConstraint(f"duration_minutes BETWEEN {MIN_DURATION} AND {MAX_DURATION}", name="duration_valid")`, `CheckConstraint(f"price_paise > 0 AND price_paise <= {MAX_PRICE_PAISE}", name="price_valid")`. The naming convention in `core/db.py` turns these into `ck_services_duration_valid` / `ck_services_price_valid`.
- Migration `0006` (down_revision `"0005"`): `op.create_table("services", …)` with plain numbers and hand-written names `pk_services`, `fk_services_business_id_businesses`, `uq_services_business_id_id`, `ck_services_duration_valid`, `ck_services_price_valid` (as in 0004). Downgrade: `op.drop_table("services")`.

- [ ] **Step 1: Write the failing tests** in `test_services_table.py`. Each test signs up an Owner. Each bad insert uses its OWN `Session(get_engine())` (a failed INSERT spoils the session until rollback), as in `test_tenant_schema.py`. Helper `insert(business_id, **fields)` builds `Service(business_id=…, name="Fan repair", duration_minutes=60, price_paise=49900, **fields)`, adds, commits.
  - `test_service_is_saved_active_with_integer_paise`: read back: `is_active is True`, `price_paise == 49900`, `type(price_paise) is int`.
  - `test_database_refuses_bad_duration`: parametrize `29`, `481` → `IntegrityError`.
  - `test_database_refuses_bad_price`: parametrize `0`, `100_000_001` → `IntegrityError`.
  - `test_database_refuses_missing_price`: `price_paise=None` → `IntegrityError` (NOT NULL).
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_services_table.py -v` → FAIL (`ImportError: Service`).
- [ ] **Step 3: Add** the constants, `Service`, and migration `0006`. Add `"services"` to the set in `test_migrations.py`.
- [ ] **Step 4: Run** `uv run pytest tests/integration/test_services_table.py tests/integration/test_migrations.py tests/integration/test_tenant_schema.py -v` → PASS. (`test_tenant_schema` proves `services` follows the tenant rules without changes.)
- [ ] **Step 5: Commit** `feat(business): services table with price_paise (story 3.1)`.
- [ ] **CHECKPOINT:** stop. Explain the table and the two CHECK guards. Wait for the user.

---

### Task 2: Services API + isolation suite + API types (CORE: auth, multi-tenancy, validation) — checkpoint after

**Files:**
- Modify: `backend/app/modules/business/schemas.py` (add `ServiceIn`, `ServiceOut`, `ServiceList`)
- Modify: `backend/app/modules/business/repository.py` (add `ServiceRepository`)
- Modify: `backend/app/modules/business/service.py` (add 4 functions)
- Modify: `backend/app/modules/business/router.py` (add 3 routes)
- Modify: `backend/tests/integration/test_tenant_isolation.py` (3 checks)
- Modify (generated): `frontend/openapi.json`, `frontend/src/api/schema.d.ts`
- Test: `backend/tests/integration/test_services.py` (new)

**Interfaces:**
- Consumes: `Service`, `MIN_DURATION`, `MAX_DURATION`, `MAX_PRICE_PAISE` (Task 1); `MAX_NAME` (already in `business/schemas.py`). `accounts_service.require_roles(actor, Permission.MANAGE_SETUP)`; `Actor`, `Permission` from `app.modules.accounts.schemas`; `ActorDep` from `app.modules.accounts.dependencies` (all allowed by import-linter).
- Produces (schemas):
  - `class ServiceIn(BaseModel)`: `name: str`; `duration_minutes: StrictInt | None = Field(default=None, validate_default=True)`; `price_paise: StrictInt | None = Field(default=None, validate_default=True)`; `is_active: bool` (required, no default). Validators raise `PydanticCustomError` with the Global Constraints copy. `name` is stripped; empty or containing `\x00` → the empty-name message; longer than `MAX_NAME` → the long-name message.
  - `class ServiceOut(BaseModel)`: `service_id: uuid.UUID`, `name: str`, `duration_minutes: int`, `price_paise: int`, `is_active: bool`.
  - `class ServiceList(BaseModel)`: `services: list[ServiceOut]` (oldest first).
- Produces (repository): `class ServiceRepository(TenantRepository[Service])` with `model = Service`, `list_all() -> list[Service]` (`order_by(Service.created_at, Service.id)`), `list_active() -> list[Service]` (same order, `is_active` only). Both start from `self._select()`.
- Produces (front door, `business/service.py`):
  - `list_services(session, actor: Actor) -> ServiceList`
  - `create_service(session, actor: Actor, data: ServiceIn) -> ServiceOut`
  - `replace_service(session, actor: Actor, service_id: uuid.UUID, data: ServiceIn) -> ServiceOut` (role check, then `get_or_raise`, then set all four fields, then `session.flush()`)
  - `list_active_services(session) -> list[ServiceOut]` (no Actor, no role check: the caller already has a tenant scope; for the Chat Page and Agent later)
- Produces (routes; error model `ErrorEnvelope`):
  - `GET /api/v1/services`, `operation_id="list_services"`, `responses` 401/403 → `ServiceList`
  - `POST /api/v1/services`, `status_code=201`, `operation_id="create_service"`, 401/403/422 → `ServiceOut`
  - `PUT /api/v1/services/{service_id}`, `operation_id="replace_service"`, 401/403/404/422 → `ServiceOut`

- [ ] **Step 1: Write the failing tests** in `test_services.py`. Local helpers (not in conftest): `FORBIDDEN_BODY = {"error": {"code": "forbidden", "message": "You don't have access to this."}}`; `FAN = {"name": "Fan repair", "duration_minutes": 60, "price_paise": 49900, "is_active": True}`; `field_errors(response) -> dict[str, str]` maps `error.fields` to `{field: message}`; `services(client) -> list[dict]` returns `GET …["services"]`.
  - `test_owner_adds_a_service_saved_active` — Behaviour: POST saves an active Service with paise. `201`; body == `{**FAN, "service_id": <any>}`; `services()` lists exactly it.
  - `test_missing_price_is_refused_next_to_the_field` — POST without `price_paise`, and with `price_paise: None`: `422`, `field_errors == {"price_paise": "Enter a Price in rupees, for example 499."}`; `services()` is `[]`.
  - `test_duration_outside_30_to_480_is_refused` — parametrize `29`, `481` → `{"duration_minutes": "Use 30 to 480 minutes."}`. `30` and `480` → `201`. Missing → `"Enter a duration in minutes."`.
  - `test_price_zero_is_refused` → `"Enter a Price above ₹0."`.
  - `test_price_above_cap_is_refused` — parametrize `100_000_001`, `2**31`, `10**15` → `422` `"Use at most ₹10,00,000."`; `100_000_000` → `201`.
  - `test_non_integer_numbers_are_refused` — parametrize `price_paise` = `True`, `"499"`, `499.0` → `422` with a `price_paise` field error; `services()` is `[]`.
  - `test_blank_long_or_nul_name_is_refused` — `"   "` and `"Fan\x00"` → `"Enter a name for the Service."`; `"x" * 101` → `"Use at most 100 characters."`.
  - `test_missing_is_active_is_refused` — PUT `FAN` without `is_active` → `422` with an `is_active` field error; the row is unchanged.
  - `test_owner_edits_a_service` — PUT new name / duration / price: `200`; body and `services()` show the new values.
  - `test_edit_without_price_is_refused_and_keeps_old_row` — PUT `{**FAN, "price_paise": None}`: `422` with the Price message; `services()` still shows `49900`.
  - `test_deactivated_service_is_no_longer_offered` — Behaviour: deactivate hides it from the front door. PUT `{**FAN, "is_active": False}` → `200`; `services()` still lists it with `is_active False`; in `tenant_scope(business_id)`, `business_service.list_active_services(session)` is `[]`. PUT `{**FAN, "is_active": True}` → it is back in `list_active_services`.
  - `test_activating_without_price_is_refused` — deactivate first; PUT `{**FAN, "price_paise": None, "is_active": True}` → `422` on `price_paise`; the row still reads `is_active False`.
  - `test_staff_and_technician_get_403_on_service_routes` — parametrize roles `["staff"]`, `["technician"]`, `["staff", "technician"]`: use `invite_member`; GET, POST, and PUT (to the Owner's real `service_id`) → `403` with `FORBIDDEN_BODY`; the Owner's row is unchanged and no new row exists.
  - `test_role_check_runs_before_lookup` — a Staff PUT to a random `uuid.uuid4()` → `403`, not `404`.
  - `test_logged_out_caller_gets_401` — a fresh `make_client()` GET / POST → `401`.
  - `test_unknown_service_id_is_404` — Owner PUT to `uuid.uuid4()` → `assert_not_found`.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_services.py -v` → FAIL (`404` on `/api/v1/services`).
- [ ] **Step 3: Implement** the schemas, repository, front door, and routes listed above.
- [ ] **Step 4: Run** `uv run pytest tests/integration/test_services.py -v` → PASS. Then `uv run lint-imports` → contracts kept.
- [ ] **Step 5: Run** `uv run pytest tests/integration/test_tenant_isolation.py -v` → FAIL: `test_every_endpoint_is_listed_once` names the three new routes (a true red step: the suite catches new routes).
- [ ] **Step 6: Add three checks** to `ISOLATION_CHECKS`:
  - `("GET", "/api/v1/services"): check_list_services` — A and B each POST one Service; A's list holds only A's `service_id`.
  - `("POST", "/api/v1/services"): check_create_service` — A POSTs; a direct DB read shows the row's `business_id == a_business_id`; B's list is `[]`.
  - `("PUT", "/api/v1/services/{service_id}"): check_replace_service` — B POSTs a Service; A PUTs a valid body to B's id → `assert_not_found`; B's list shows the old values.
- [ ] **Step 7: Run** `uv run pytest -m isolation -v` → PASS.
- [ ] **Step 8: Regenerate types** in WSL: `uv run python -m app.export_openapi ../frontend/openapi.json`, then in `frontend/`: `npm run gen:api`. Check `schema.d.ts` has `ServiceIn`, `ServiceOut`, `ServiceList`.
- [ ] **Step 9: Commit** (routes, isolation checks and generated types together, so CI is green at this commit) `feat(business): Owner-only Services API (story 3.1)`.
- [ ] **CHECKPOINT:** stop. Walk the request path: cookie → `ActorDep` → role check → repository tenant filter → flush. Wait for the user.

---

### Task 3: Money helpers (STANDARD)

**Files:**
- Create: `frontend/src/lib/money.ts`
- Test: `frontend/src/lib/money.test.ts`

**Interfaces:**
- Produces: `formatRupees(paise: number): string`, `paiseToRupeesText(paise: number): string`, `rupeesToPaise(text: string): number | null`.
- `formatRupees` uses `Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: d, maximumFractionDigits: d })` with `d = paise % 100 === 0 ? 0 : 2`. (Verified on Node 24: `₹1,499`, `₹1,00,000`, `₹499.50`.)
- `paiseToRupeesText`: the text for an input box, with no sign and no commas: `"1499"`, `"499.50"`. It fills the edit form.
- `rupeesToPaise`: remove commas, spaces, and a leading `₹`; accept only `/^\d+(\.\d{1,2})?$/`; return `Math.round(Number(clean) * 100)`; anything else (empty too) → `null`.

- [ ] **Step 1: Write the failing tests:**
  - `formatRupees(149900)` → `"₹1,499"`; `formatRupees(10000000)` → `"₹1,00,000"`; `formatRupees(49950)` → `"₹499.50"`; `formatRupees(100)` → `"₹1"`.
  - `paiseToRupeesText(149900)` → `"1499"`; `paiseToRupeesText(49950)` → `"499.50"`.
  - `rupeesToPaise("499")` → `49900`; `"1,499"` → `149900`; `"₹1,499"` → `149900`; `" 499.50 "` → `49950`; `"0.1"` → `10`; `""` → `null`; `"abc"` → `null`; `"4.999"` → `null`; `"-5"` → `null`.
  - Round trip: for `149900` and `49950`, `rupeesToPaise(paiseToRupeesText(p)) === p`.
- [ ] **Step 2: Run** `npx vitest run src/lib/money.test.ts` → FAIL (no module).
- [ ] **Step 3: Implement** the three functions.
- [ ] **Step 4: Run** the test → PASS.
- [ ] **Step 5: Commit** `feat(app): money helpers with Indian grouping (story 3.1)`.

---

### Task 4: Settings → Services page (STANDARD)

**Files:**
- Modify: `frontend/src/lib/pages.ts` (one row)
- Modify: `frontend/src/lib/pages.test.ts` (line 80-82 pins the settings link list)
- Modify: `frontend/src/components/SettingsLinks.test.tsx` (Owner sees Services)
- Create: `frontend/src/app/app/settings/services/page.tsx`
- Create: `frontend/src/components/ServiceForm.tsx`, `frontend/src/components/ServicesSettings.tsx`
- Test: `frontend/src/components/ServiceForm.test.tsx`, `frontend/src/components/ServicesSettings.test.tsx`

**Interfaces:**
- Consumes: `api.GET("/api/v1/services")` (→ `{ services }`), `api.POST("/api/v1/services", { body })`, `api.PUT("/api/v1/services/{service_id}", { params: { path: { service_id } }, body })`; `formatRupees`, `paiseToRupeesText`, `rupeesToPaise` (Task 3).
- `PAGES` row: `{ href: "/app/settings/services", label: "Services", place: "settings", needs: "manage_setup" }`, before Team.
- `page.tsx`: same shape as the Team page; `metadata.title = "Services · SevaDesk"`; `<h1>Services</h1>`; renders `<ServicesSettings />`.
- `ServiceForm` props: `{ initial?: ServiceOut; onSaved: () => void; onCancel?: () => void }`.
  - No `initial` = add mode: POST with `is_active: true`, heading `Add a Service`, button `Add Service`, fields cleared after a save.
  - With `initial` = edit mode: fields filled with `name`, `String(duration_minutes)`, `paiseToRupeesText(price_paise)`; PUT with `is_active: initial.is_active`; button `Save`, plus `Cancel`. On open, focus moves to the Name input.
  - Every element id is built from React `useId()` (e.g. `${id}-name`, `${id}-name-error`), so the add form and an open edit form never share an id.
  - Fields, in order: `Name` (`name`), `Duration (minutes)` (`duration_minutes`, `inputMode="numeric"`), `Price (₹)` (`price_paise`, `inputMode="decimal"`).
  - Body: `name`; `duration_minutes` = `/^\d+$/.test(text.trim()) ? Number(text) : null` (a blank box must be `null`, not `Number("") = 0`); `price_paise` = `rupeesToPaise(text)`.
  - Field errors from `error.fields` show under each field (`aria-invalid`, `aria-describedby`); focus moves to the first field with an error (the `SignupForm` pattern, UX-DR33). Other errors: `Something went wrong. Please try again.` in `role="alert"`.
  - While busy: the submit is ignored and the button text is `Saving…` (the button itself may be `disabled`: focus stays in the form on the fields; only row actions must not be disabled).
- `ServicesSettings`:
  - Loads the list (skeleton while loading; `Could not load. Please try again.` + `Try again` on failure, as `TeamSettings`). Empty list: `No Services yet. Add your first one below.`
  - Each row: name, `formatRupees(price_paise)`, `{duration_minutes} min`, the text `Inactive` when not active, buttons `Edit` (aria-label `Edit {name}`) and `Deactivate` / `Activate` (aria-label `Deactivate {name}` / `Activate {name}`).
  - Edit swaps the row for `<ServiceForm initial=…>`. On Save or Cancel, focus goes back to that row's Edit button.
  - Deactivate / Activate sends PUT with the row's own fields and the flipped `is_active`. One change at a time: while it runs, further row clicks are ignored and the list has `aria-busy="true"`. The buttons are NOT `disabled` (Story 2.6 focus bug).
  - If a row change fails: `role="alert"` with `fields[0].message ?? error.message ?? "Something went wrong. Please try again."` (the `TeamSettings` pattern).
  - After any save, reload the list. The add form sits under the list.

- [ ] **Step 1: Write the failing tests** (mock `@/api/client` as in `TeamSettings.test.tsx`):
  - pages.test.ts: change the pinned list to `["Services", "Team", "Appearance"]`; `/app/settings/services` is in `settingsLinks(["manage_setup"])` and not in `settingsLinks([])`.
  - SettingsLinks.test.tsx: the Owner sees a `Services` link to `/app/settings/services`.
  - ServiceForm: `add sends paise and whole minutes` — type `Fan repair`, `60`, `1,499`; POST body `{ name: "Fan repair", duration_minutes: 60, price_paise: 149900, is_active: true }`; `onSaved` called.
  - ServiceForm: `an empty duration sends null` — Duration blank → POST body has `duration_minutes: null`.
  - ServiceForm: `a Price error shows next to the field and gets focus` — POST returns `{ error: { error: { code: "validation_error", message: "Some fields need fixing.", fields: [{ field: "price_paise", message: "Enter a Price in rupees, for example 499." }] } } }`; the text shows; the Price input has focus and `aria-invalid="true"`.
  - ServiceForm: `add is sent once while saving` — POST never resolves; click `Add Service` twice; POST called once; button shows `Saving…`.
  - ServiceForm: `edit with no changes sends the same values` — `initial` = `{ price_paise: 49950, duration_minutes: 60, is_active: false, … }`; click `Save`; PUT body `{ name, duration_minutes: 60, price_paise: 49950, is_active: false }`.
  - ServicesSettings: `rows show Indian-grouped Prices` — GET returns a Service with `price_paise: 10000000`; `₹1,00,000` and `60 min` show.
  - ServicesSettings: `Deactivate sends the full row with is_active false` — PUT body `{ name, duration_minutes, price_paise, is_active: false }`, then GET is called again.
  - ServicesSettings: `a failed Deactivate shows an alert` — PUT returns an error envelope → its message shows in `role="alert"`.
  - ServicesSettings: `editing keeps ids unique` — open Edit while the add form shows; `getAllByLabelText("Name")` has length 2 and each label points at a different input (`getByLabelText` inside each form via `within`).
  - ServicesSettings: `an empty list says No Services yet`.
- [ ] **Step 2: Run** `npx vitest run src/components/ServiceForm.test.tsx src/components/ServicesSettings.test.tsx src/lib/pages.test.ts src/components/SettingsLinks.test.tsx` → FAIL.
- [ ] **Step 3: Implement** the row, page, and two components.
- [ ] **Step 4: Run** `npm test`, `npm run lint`, `npm run typecheck` → all PASS (the page-file test in `pages.test.ts` sees the new row).
- [ ] **Step 5: Commit** `feat(app): Settings → Services page (story 3.1)`.

---

### Task 5: Verify, review, PR

- [ ] Full backend run in WSL: `uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest --cov` → all PASS, coverage ≥ 80%.
- [ ] Frontend: `npm test && npm run lint && npm run typecheck && npm run build` → PASS.
- [ ] Manual check (run skill / docker compose): as Owner, add `Fan repair`, 60, `1,499` → row shows `₹1,499`; clear Price on edit → message under Price; deactivate → `Inactive`; reactivate → active again; log in as Staff → no Services link, and `/app/settings/services` shows "No access".
- [ ] Definition of Done "traces visible" (`project-seed.md:98`): the `POST /api/v1/services` server span shows in the local trace viewer.
- [ ] One Opus subagent reviews the whole branch (CLAUDE.md §4). Fix findings with a regression test each.
- [ ] `sprint-status.yaml`: `3-1-manage-services-with-prices: review`. Push, open PR; body ends with `Closes #14`.
- [ ] Then read `docs/agents/after-story.md` (Understanding Gate, hands-on task, learning notes).
