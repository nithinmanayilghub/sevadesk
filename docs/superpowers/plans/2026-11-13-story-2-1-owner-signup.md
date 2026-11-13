# Story 2.1 — Owner signs up and creates a Business — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (CLAUDE.md: CORE-heavy story → inline with checkpoints). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A visitor on `/signup` enters a business name, email, and password, and the backend creates a Business, a User, and an Owner+Technician membership in one transaction.

**Architecture:** Two new backend modules. `business` owns the sign-up flow and the `businesses` table; it calls the `accounts` front door (`service.py`), which owns `users`, `sessions`, and `memberships`. `core` gets tenant context (`tenant_scope`, audited `system_scope`) and the tenant-scoped base repository. The frontend gets shadcn/ui with the DESIGN.md tokens and one form page. The backend is the only owner of validation rules; its error envelope lists bad fields.

**Tech Stack:** FastAPI, SQLAlchemy 2.1, Alembic, pwdlib[argon2] 0.3.1, Postgres 18 (Testcontainers), Next.js 16, Tailwind 4, shadcn/ui, Vitest.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → Story 2.1 (lines 432–464); rules AD-1–AD-5, AD-14, AD-15 in `_bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md`; tokens in `_bmad-output/planning-artifacts/ux-designs/ux-seva-desk-2026-11-01/DESIGN.md`.

## Global Constraints

- Branch `story/2-1-owner-signup`. GitHub issue #8. PR flow: push → `gh pr create` → green → `gh pr merge --merge --delete-branch`. Sprint-status `done` is committed inside the PR.
- Password rule (user decision): 12 to 128 characters, no composition rules, never stripped.
- Business name: stripped, 1 to 100 characters. Email: stripped + lowercased, at most 254 characters, simple shape check `^[^@\s]+@[^@\s]+\.[^@\s]+$`.
- Validation lives in the backend only (user decision). Error envelope: `{"error": {"code", "message"}}`, plus `"fields": [{"field", "message"}]` **only when there are field errors** (existing 503 tests stay unchanged).
- Route: `POST /api/v1/signup`, `operation_id="sign_up"`, 201 on success.
- Roles on the new membership: `{owner, technician}`. Allowed roles: `owner | staff | technician`.
- Every table: UUIDv7 primary key (`uuid.uuid7`), `created_at timestamptz` default `now()`.
- Password stored only as an Argon2id hash (`$argon2id$…`).
- Services never commit (AD-15). `accounts` never imports `business` (AD-2). Repository methods never take `business_id` (AD-3).
- No data-fetching library in the frontend (AR-3). Tap targets ≥ 44px. Labels ≥ 12px. Body weight 400.
- Pin every new dependency to an exact version.
- No sessions or log-in in this story (Story 2.2). The `sessions` table is only created.

## Review Focus

1. Same email, different case or spaces (`" Owner@Shop.COM "` vs `owner@shop.com`) → second sign-up gets 409. Test in Task 4.
2. Business name of only spaces → "Enter your business name." Test in Task 4.
3. A password of 12 Hindi characters is accepted; spaces at the ends are kept. Test in Task 4.
4. A crash after the Business row is written leaves no Business behind (rollback). Test in Task 4.
5. Double-click on submit → the button is disabled while the request runs. Test in Task 6.

Also covered (from the Opus plan review, 2026-11-13): two sign-ups with the same email at the same moment → the unique index refuses the second, and `create_owner` turns that into a 409 (Task 4). A crash never logs the email or the hash (`hide_parameters=True`, Task 1).

Re-deferred to Story 2.3 (the isolation-test story rewrites the test fixtures anyway): conftest refactor (`with TestClient`, clear caches + dispose in teardown), 404 → envelope, 503 listed in OpenAPI responses, closing the cached Redis client in a lifespan.

---

### Task 0: Learning steps before coding [no code]

- [ ] **Step 1:** End of Epic 1 — the user explains the whole system in 5 sentences, using `docs/learning/architecture-map.md`. Then commit that file: `docs(learning): architecture map at end of Epic 1`.
- [ ] **Step 2:** Start of Epic 2 — quiz 2 items from `docs/learning/gaps.md` (pick the heartbeat TTL and the `traceparent` items). Update their Status column.
- [ ] **Step 3:** Story Map + predict question (done in chat on 2026-11-13; the re-ask about Story 2.5 is still open).
- [ ] **Step 4:** Create branch `story/2-1-owner-signup`; add label `in-progress` to issue #8.
- [ ] **Rule for all tasks:** before each CORE test, tell the user in one line what behaviour it checks.

### Task 1: Tenant context in `core` [CORE]

**Files:**
- Create: `backend/app/core/tenancy.py`
- Modify: `backend/app/core/db.py` (naming convention inside `class Base`; `hide_parameters=True` in `create_engine`)
- Test: `backend/tests/unit/test_tenancy.py`, `backend/tests/unit/test_db_engine.py`

**Interfaces:**
- Produces:
  - `SYSTEM_SCOPE_CALLERS: frozenset[str] = frozenset({"signup"})`
  - `class TenantContextMissing(RuntimeError)`, `class SystemScopeRequired(RuntimeError)`
  - `current_business_id() -> uuid.UUID` (raises `TenantContextMissing`)
  - `tenant_scope(business_id: uuid.UUID)` — context manager; restores the old value on exit (use `ContextVar` + token reset)
  - `system_scope(caller: str)` — context manager; `ValueError` if `caller` not in the allow-list; logs INFO `"system_scope entered"` with `extra={"caller": caller}` (no email, no PII)
  - `require_system_scope() -> None` (raises `SystemScopeRequired`)
  - `NAMING_CONVENTION` in `db.py`: `{"ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_N_name)s", "ck": "ck_%(table_name)s_%(constraint_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s", "pk": "pk_%(table_name)s"}`, declared **inside** the class: `class Base(DeclarativeBase): metadata = MetaData(naming_convention=NAMING_CONVENTION)` (never reassigned later)
  - `get_engine()` adds `hide_parameters=True`, so a SQL error text never carries the email or the password hash into logs

- [ ] **Step 1: Write failing tests** in `test_tenancy.py`:
  - `test_current_business_id_raises_outside_scope` → `pytest.raises(TenantContextMissing)`
  - `test_tenant_scope_sets_and_restores` → inside A: `== A`; nested B: `== B`; back to `== A`; after exit raises
  - `test_system_scope_refuses_unknown_caller` → `pytest.raises(ValueError)` for `"hacker"`
  - `test_require_system_scope_only_inside` → raises outside; passes inside `system_scope("signup")`; raises again after exit
  - `test_system_scope_writes_audit_log` → `caplog` has a record with `caller == "signup"`
  - in `test_db_engine.py`: `test_engine_hides_sql_parameters` → `get_engine().hide_parameters is True`
  - `test_base_uses_naming_convention` → `Base.metadata.naming_convention["uq"] == "uq_%(table_name)s_%(column_0_N_name)s"`
- [ ] **Step 2: Run** `cd backend && uv run pytest tests/unit/test_tenancy.py -v` → FAIL (module not found)
- [ ] **Step 3: Implement** `tenancy.py` and the naming convention.
- [ ] **Step 4: Run** the same command → PASS; `uv run pytest tests/unit -q` → all pass
- [ ] **Step 5: Commit** `feat(core): tenant context and audited system scope (story 2.1)`

### Task 2: Tables, migration, and the tenant base repository [CORE]

**Files:**
- Create: `backend/app/core/repository.py`, `backend/app/modules/__init__.py`, `backend/app/modules/accounts/{__init__,models,repository}.py`, `backend/app/modules/business/{__init__,models,repository}.py`, `backend/migrations/versions/0003_accounts_and_business.py`
- Modify: `backend/migrations/env.py` (import both models modules), `backend/tests/integration/test_hello.py` and `test_migrations.py` (new table set)
- Test: `backend/tests/integration/test_tenant_repository.py`

**Interfaces:**
- Consumes: `current_business_id()`, `require_system_scope()` from Task 1.
- Produces:
  - `core/repository.py`: `class TenantModel(Base)` (`__abstract__ = True`; `business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"))` — string FK, so `core` imports no module); `class TenantRepository[ModelT: TenantModel]` with class attr `model`, `__init__(self, session: Session)`, `_select() -> Select` (adds `business_id == current_business_id()`), `get(id: uuid.UUID) -> ModelT | None`, `add(row: ModelT) -> ModelT` (always overwrites `row.business_id` with the current one, `session.add`, `flush`).
  - `business/models.py`: `Business` — `businesses(id, name text not null, created_at)`.
  - **Every `add()` in every repository ends with `session.flush()`.** The `uuid.uuid7` default fills `id` only at flush, so without it `business.id` and `user.id` are `None`.
  - `business/repository.py`: `BusinessRepository(session).add(name: str) -> Business` (global table, plain class).
  - `accounts/models.py`: `User` — `users(id, email text unique not null, password_hash text not null, created_at)`; `UserSession` — `sessions(id, user_id FK users not null, token_hash text unique not null, created_at, last_seen_at timestamptz not null default now())`; `Membership(TenantModel)` — `memberships(id, business_id, user_id FK users UNIQUE not null, roles text[] not null, is_active bool not null default true, created_at)`, `UniqueConstraint("business_id", "id")`, `CheckConstraint("cardinality(roles) > 0 AND roles <@ ARRAY['owner','staff','technician']::text[]", name="roles_valid")`.
  - `accounts/repository.py`: `UserRepository(session)` with `email_exists(email: str) -> bool` (calls `require_system_scope()` first) and `add(email: str, password_hash: str) -> User`; `MembershipRepository(TenantRepository[Membership])` with `model = Membership`.
  - Migration `0003` (down_revision `"0002"`) creates the four tables in FK order; downgrade drops them in reverse. Hand-written `op.create_table` does **not** apply the naming convention, so name every constraint explicitly with the convention's names: `pk_businesses`, `pk_users`, `uq_users_email`, `pk_sessions`, `fk_sessions_user_id_users`, `uq_sessions_token_hash`, `pk_memberships`, `fk_memberships_business_id_businesses`, `fk_memberships_user_id_users`, `uq_memberships_user_id`, `uq_memberships_business_id_id`, `ck_memberships_roles_valid`. Task 4 relies on the name `uq_users_email`. (`app_meta` keeps its Postgres default names from 0001; leave it.)

- [ ] **Step 1: Write failing tests** in `test_tenant_repository.py` (use the `client` fixture for a migrated DB; make rows with `Session(get_engine())`, unique emails via `uuid4().hex`):
  - `test_migration_creates_the_four_tables` → table names ⊇ `{businesses, users, sessions, memberships}`
  - `test_new_rows_get_uuidv7_ids` → inside the test, add one Business, one User, one Membership through their repositories, and one `UserSession` with `session.add` + `flush`; assert `row.id.version == 7` for each of the four
  - `test_membership_get_hides_other_business` → membership made in A; `get(id)` inside `tenant_scope(B)` is `None`, inside A is the row
  - `test_add_without_tenant_raises` → `TenantContextMissing`
  - `test_add_overwrites_business_id` → row built with `business_id=B` and added in A's scope has `business_id == A`
  - `test_database_refuses_bad_roles` → `roles=[]` and `roles=["admin"]` → `IntegrityError`
  - `test_one_business_per_user` → second membership for the same user → `IntegrityError`
  - `test_email_exists_needs_system_scope` → `SystemScopeRequired` outside; `True/False` inside `system_scope("signup")`
  - Update `test_hello.py::test_migration_creates_only_app_meta` and `test_migrations.py` expected sets to `{alembic_version, app_meta, businesses, users, sessions, memberships}`.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_tenant_repository.py -v` (Docker Desktop on, compose stack down) → FAIL
- [ ] **Step 3: Implement** models, repositories, migration, env.py imports.
- [ ] **Step 4: Run** `uv run pytest tests/integration -q` → PASS (incl. downgrade-to-base test)
- [ ] **Step 5: Commit** `feat(accounts,business): tables, migration 0003, tenant base repository (story 2.1)`

### Task 3: Field errors in the envelope [STANDARD]

**Files:**
- Modify: `backend/app/core/errors.py`
- Test: `backend/tests/unit/test_errors.py`

**Interfaces:**
- Produces:
  - Pydantic models for OpenAPI: `FieldError(field: str, message: str)`, `ErrorBody(code: str, message: str, fields: list[FieldError] | None = None)`, `ErrorEnvelope(error: ErrorBody)`.
  - `AppError(code, message, status_code, fields: list[FieldError] | None = None)`; the envelope includes `"fields"` only when not `None`.
  - A `RequestValidationError` handler: 422, code `"validation_error"`, message `"Some fields need fixing."`, `fields` from each error whose `loc` is `("body", <name>)`: message `"This field is required."` when `type == "missing"`, else the error's `msg`. Errors with other `loc` add no field. **When the list is empty, the `fields` key is left out** (same rule as `AppError`).
  - A handler for any other `Exception`: 500, `{"error": {"code": "internal_error", "message": "Something went wrong. Please try again."}}`. The error is still logged (with the traceback) by the existing request middleware; the body never shows it.

- [ ] **Step 1: Write failing tests** (tiny app with a `POST /t` taking a model with `name: str`):
  - `test_validation_error_uses_envelope_with_fields` → body `{}` → 422, `{"error": {"code": "validation_error", "message": "Some fields need fixing.", "fields": [{"field": "name", "message": "This field is required."}]}}`
  - `test_invalid_json_gives_envelope_without_fields` → raw body `"{"` → 422, code `validation_error`, and `"fields" not in body["error"]`
  - `test_unexpected_error_gives_500_envelope` → a route that raises `RuntimeError("secret detail")`; `TestClient(app, raise_server_exceptions=False)` → 500, code `internal_error`, and `"secret detail"` not in the response text
  - `test_app_error_with_fields` → raised `AppError(..., fields=[FieldError(field="email", message="x")])` → fields in JSON
  - existing `test_errors.py` test stays unchanged and passes (no `fields` key)
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_errors.py -v` → FAIL
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/unit -q` → PASS
- [ ] **Step 5: Commit** `feat(core): validation errors in the error envelope (story 2.1)`

### Task 4: The sign-up flow and endpoint [CORE]

**Files:**
- Create: `backend/app/modules/accounts/{schemas,service}.py`, `backend/app/modules/business/{schemas,service,router}.py`
- Modify: `backend/app/main.py` (include router), `backend/pyproject.toml` (`pwdlib[argon2]==0.3.1`; import-linter contracts below), `backend/uv.lock`, `frontend/openapi.json`, `frontend/src/api/schema.d.ts`
- Test: `backend/tests/integration/test_signup.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `accounts/schemas.py`: `class Role(StrEnum)`: `OWNER="owner"`, `STAFF="staff"`, `TECHNICIAN="technician"`; `OwnerCreated(BaseModel)`: `user_id: UUID`, `membership_id: UUID`, `roles: set[Role]`.
  - `accounts/service.py` (the front door): `class EmailTaken(AppError)` → 409, code `"email_taken"`, message `"An account with this email already exists."`, `fields=[FieldError(field="email", message="An account with this email already exists.")]`; `hash_password(plain: str) -> str` (pwdlib `PasswordHash((Argon2Hasher(),))`); `create_owner(session, email: str, password: str) -> OwnerCreated` — must run inside `tenant_scope` (set by the caller). In this order: (1) `with system_scope("signup"):` around **only** the `email_exists` lookup (AD-3: the allow-listed lookup lives in `accounts`); raise `EmailTaken` if taken; (2) `hash_password`; (3) add the user — if the flush raises `IntegrityError` whose `exc.orig.diag.constraint_name == "uq_users_email"` (the race), raise `EmailTaken` instead; re-raise any other `IntegrityError`; (4) add the membership with `{owner, technician}`.
  - `business/schemas.py`: `SignupRequest(business_name: str, email: str, password: str)` with `field_validator`s that raise `PydanticCustomError` with these exact messages: name empty after strip → `"Enter your business name."`, name > 100 → `"Use at most 100 characters."`; bad email → `"Enter a valid email address."`; password < 12 → `"Use at least 12 characters."`, > 128 → `"Use at most 128 characters."`. `SignupResponse(business_id: UUID, business_name: str)`.
  - `business/service.py`: `sign_up(session, request: SignupRequest) -> SignupResponse` — add the Business (global table, needs no scope), then `with tenant_scope(business.id): accounts_service.create_owner(...)`. The tenant id is server-derived: this transaction just created it. Import style is fixed: `from app.modules.accounts import service as accounts_service`, and every call goes through `accounts_service.<name>` (so tests can monkeypatch it). No commit.
  - `business/router.py`: `POST /api/v1/signup`, `status_code=201`, `operation_id="sign_up"`, `responses={409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}}`.
  - `pyproject.toml` contracts:
    ```toml
    [[tool.importlinter.contracts]]
    name = "module layers: business -> accounts -> core"
    type = "layers"
    layers = ["app.modules.business", "app.modules.accounts", "app.core"]

    [[tool.importlinter.contracts]]
    name = "business uses accounts only through its front door"
    type = "forbidden"
    source_modules = ["app.modules.business"]
    forbidden_modules = ["app.modules.accounts.models", "app.modules.accounts.repository"]
    ```

- [ ] **Step 1: Write failing tests** in `test_signup.py` (helper `email()` returns a unique address):
  - `test_signup_creates_business_user_and_owner_membership` → 201; body has `business_id` and `business_name`; DB: one business with that id and name; user email lowercased; membership `business_id` matches, roles `{"owner","technician"}`, `is_active` true
  - `test_password_is_stored_only_as_argon2id_hash` → `password_hash.startswith("$argon2id$")` and the plain password is not in it
  - `test_taken_email_returns_409_and_creates_nothing` → sign up `a@x.com`, then `" A@X.com "` → 409, code `email_taken`, `fields[0]["field"] == "email"`; after both calls, the business, user, and membership counts each went up by exactly 1
  - `test_email_race_returns_409` → monkeypatch `UserRepository.email_exists` to return `False`; sign up a taken email → 409 `email_taken` (the unique index catches it), counts unchanged
  - `test_invalid_input_lists_each_field` → `{"business_name": "   ", "email": "nope", "password": "short"}` → 422; fields == the three fields with the exact messages above
  - `test_twelve_hindi_characters_are_a_valid_password` → `"क" * 12` (exactly 12 characters) → 201; and a password with end spaces verifies with `PasswordHash` only when the spaces are kept
  - `test_crash_mid_signup_leaves_nothing` → monkeypatch `app.modules.accounts.service.create_owner` to raise `RuntimeError`; `TestClient(app, raise_server_exceptions=False)` → 500 with code `internal_error`; business count unchanged
  - `test_failed_commit_gives_500_and_saves_nothing` (first write-path test, deferred from 1.2) → monkeypatch `sqlalchemy.orm.SessionTransaction.commit` to raise `RuntimeError`; valid sign-up → 500 `internal_error`; after removing the patch, business count unchanged
  - `test_openapi_lists_signup_with_envelope_errors` → path `/api/v1/signup` has `post` with responses `201`, `409`, `422`
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_signup.py -v` → FAIL
- [ ] **Step 3: Implement.** `uv add 'pwdlib[argon2]==0.3.1'` (check it resolves; if 0.3.1 is not on PyPI, stop and report).
- [ ] **Step 4: Run** `uv run pytest --cov -q` → PASS, coverage ≥ 80; `uv run lint-imports` → all contracts kept; `uv run ruff check .. && uv run ruff format --check ..` → clean
- [ ] **Step 5: Regenerate the API types:** `uv run python -m app.export_openapi ../frontend/openapi.json`, then `cd ../frontend && npm run gen:api`.
- [ ] **Step 6: Commit** `feat(business): POST /api/v1/signup creates Business, User, membership (story 2.1)`

### Task 5: Frontend foundation — shadcn/ui and brand tokens [BOILERPLATE/STANDARD]

**Files:**
- Create (by `npx shadcn@<exact> init` then `add button input label`): `frontend/components.json`, `frontend/src/lib/utils.ts`, `frontend/src/components/ui/{button,input,label}.tsx`; `frontend/src/package-rules.test.ts`
- Modify: `frontend/src/app/globals.css`, `frontend/src/app/layout.tsx`, `frontend/package.json` (+ lock; exact versions)

**Interfaces:**
- Produces: `Button`, `Input`, `Label` from `@/components/ui/*`; `cn()` from `@/lib/utils`; Tailwind utilities `bg-brand`, `text-brand`, `bg-brand-soft`, `text-status-requested`, `text-status-handoff`, `h-tap`/`min-h-tap` (44px), `px-page-x`, `lg:px-page-x-lg`, `max-w-app`, `rounded-section`.

Decisions:
- DESIGN.md `accent` (emerald) becomes `--brand`, `--brand-foreground`, `--brand-soft`, because shadcn already uses `--accent` for neutral hover backgrounds. All other DESIGN.md colors map to the shadcn variable of the same name; light values in `:root`, dark values in `@media (prefers-color-scheme: dark) { :root { … } }`.
- Dark mode follows the device: `@custom-variant dark (@media (prefers-color-scheme: dark));`. Story 2.6 adds the manual switch.
- Radii in `@theme inline`: `--radius-sm: 8px; --radius-md: 12px; --radius-lg: 16px; --radius-xl: 24px; --radius-section: 40px`.
- Spacing: `--spacing-tap: 44px; --spacing-page-x: 16px; --spacing-page-x-lg: 32px; --container-app: 1280px`.
- Dark body background: `linear-gradient(to bottom, #09090B, #000000)`.
- Error color: set shadcn's `--destructive` to DESIGN.md `status-handoff` (`#B91C1C` light, `#F87171` dark). shadcn's default red is about 4.35:1 on `#F4F4F5`, below the 4.5:1 floor. Field error text uses `text-destructive`.
- Fonts: `next/font/google` — `Inter({ subsets: ["latin"], variable: "--font-inter" })`, `Noto_Sans_Devanagari({ subsets: ["devanagari"], weight: ["400", "600", "700"], variable: "--font-devanagari", preload: false })`. `--font-sans: var(--font-inter), var(--font-devanagari), system-ui, sans-serif`. `preload: false` + the subset's `unicode-range` means the Devanagari file downloads only when Hindi text appears.
- Button: default and only text size `h-11` (44px), `rounded-full`; icon size `size-11`. Remove smaller sizes. Input: `h-11 rounded-md`. Keep shadcn's `focus-visible` ring.

- [ ] **Step 1: Write failing test** `package-rules.test.ts`: `test("no data-fetching library is installed")` → read `package.json`; none of `["swr", "@tanstack/react-query", "react-query", "axios", "ky", "@apollo/client", "urql"]` in `dependencies` or `devDependencies`; `openapi-fetch` is in `dependencies`. Also `test("ui components exist")` → `import { Button } from "@/components/ui/button"` resolves.
- [ ] **Step 2: Run** `cd frontend && npm test` → FAIL (button missing)
- [ ] **Step 3: Run shadcn init/add.** Rules, because this project runs Tailwind through the `@tailwindcss/turbopack` loader in `next.config.ts`, not PostCSS:
  - Run `npm view shadcn version` once; use that exact version for every call: `npx shadcn@<version> init` and `npx shadcn@<version> add button input label`. Use the non-interactive flags that `--help` lists (defaults, base color zinc, no prompts). Write the version into the commit message.
  - If init creates `postcss.config.*`, delete it. Do not change `next.config.ts`.
  - In `globals.css`, keep one `@import "tailwindcss"`. Replace shadcn's `@custom-variant dark (&:is(.dark *))` with the media-query variant above. Replace its oklch values with the DESIGN.md hex values.
  - In `package.json`, remove every `^` or `~` that init added (expected: `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `tw-animate-css`, one Radix package); then `npm install` to update the lock.
  - Then apply the decisions above.
- [ ] **Step 4: Run** `npm test && npm run lint && npm run typecheck && npm run build` → all pass; `HelloCard` tests still pass
- [ ] **Step 5: Commit** `feat(frontend): shadcn/ui with DESIGN.md tokens and fonts (story 2.1)`

### Task 6: The `/signup` page [STANDARD]

**Files:**
- Create: `frontend/src/app/signup/page.tsx`, `frontend/src/components/SignupForm.tsx`, `frontend/src/components/SignupForm.test.tsx`

**Interfaces:**
- Consumes: `api.POST("/api/v1/signup", { body })` (generated types from Task 4); `Button`, `Input`, `Label` (Task 5).
- Produces: `SignupForm` (client component). Page title `"Sign up · SevaDesk"`, heading `"Create your SevaDesk Business"`.

Behaviour:
- Fields in this order: `business_name` "Business name", `email` "Email" (`type="email"`, `autoComplete="email"`), `password` "Password" (`type="password"`, `autoComplete="new-password"`, always-visible hint "At least 12 characters."). `<form noValidate>`, so only the backend's messages show.
- Submit button "Create my Business"; while the request runs it says "Creating…" and is disabled.
- On error with `error.fields?.length > 0`: each message shows in text under its field (`id` linked by `aria-describedby`), the input gets `aria-invalid="true"`, focus moves to the first field (in the order above) that has an error. Old errors clear on each submit.
- On error without fields, or a network failure: a `role="alert"` line with `error.message`, else `"Something went wrong. Please try again."`.
- On 201: the form is replaced by a `role="status"` message: `Your Business “{business_name}” is ready.` (Story 2.2 adds log-in and the redirect.)

- [ ] **Step 1: Write failing tests** (mock `api.POST` like `HelloCard.test.tsx`):
  - `"every control has a text label"` → `getByLabelText` for the three fields; `getByRole("button", { name: "Create my Business" })`
  - `"sends the three fields to the sign-up endpoint"` → called with `("/api/v1/signup", { body: { business_name, email, password } })`
  - `"shows the success message"`
  - `"shows field errors next to fields and focuses the first one"` → 422 with email + password errors → email input `aria-invalid="true"`, its description has the message, `document.activeElement` is the email input
  - `"shows a taken email next to the email field"` → 409 envelope
  - `"shows a general error when the network fails"` → `role="alert"` text
  - `"disables the button while the request runs"` → pending promise → button disabled with "Creating…"
- [ ] **Step 2: Run** `npm test` → FAIL
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npm test && npm run lint && npm run typecheck` → PASS
- [ ] **Step 5: Commit** `feat(frontend): /signup page with field errors (story 2.1)`

### Task 7: Live check, learning notes, PR [STANDARD]

**Files:**
- Create: `docs/learning/2-1.md`
- Modify: `docs/learning/glossary.md`, `_bmad-output/implementation-artifacts/sprint-status.yaml` (`2-1…: done`, `epic-2: in-progress`)

- [ ] **Step 1: Live check** with `docker compose up --build` in `infra/compose`, then in the browser at `http://localhost/signup`:
  - sign up → success message; same email again → error under Email; all-empty submit → three errors, focus on the first
  - Tab through the form → a visible focus ring on every control
  - Chrome DevTools → Lighthouse → Accessibility on `/signup` in light and dark mode → no contrast or label failures (shows an error state too)
  - OS dark mode on → dark tokens and gradient
  - `psql`: one `businesses` row, `users.password_hash` starts with `$argon2id$`, `memberships.roles = {owner,technician}`
  - local Grafana: the `POST /api/v1/signup` trace shows the INSERTs
- [ ] **Step 2: Full suite** (stack down): `cd backend && uv run pytest --cov -q`, `cd frontend && npm test` → PASS
- [ ] **Step 3: Write** `docs/learning/2-1.md` (what, why, concept: tenant context + one-transaction sign-up, key files) and glossary terms: tenant, ContextVar, Argon2id, salt, rollback, design token, `unicode-range`, import-linter layers.
- [ ] **Step 4: Opus final review** of the whole branch; fix findings.
- [ ] **Step 5: Understanding Gate + hands-on task** (CLAUDE.md §5–6).
- [ ] **Step 6: Commit, push, PR** with `Closes #8`; merge when green.
