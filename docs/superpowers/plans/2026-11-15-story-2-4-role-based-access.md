# Story 2.4 — Role-based access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (CORE-heavy story: checkpoints after each task, per CLAUDE.md §4). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each Role can do only what the FR-10 table allows: the backend answers 403 for a forbidden action and changes nothing, and the app hides what a Role may not use.

**Architecture:** The FR-10 table lives once, in `accounts/permissions.py`, as a map `Permission → allowed Roles`. Services call one helper, `require_roles(actor, permission)`, which raises `Forbidden` (403). Other modules reach it through the `accounts/service.py` front door (re-export, like `clean_email`). The app does not copy the table: `GET /me` and log-in also return the Actor's `permissions`, and the frontend shows nav items and pages from that list.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, pytest + testcontainers (Python 3.14); Next.js 16, React, Vitest, openapi-typescript.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 2.4: Role-based access". Also: PRD FR-10 table and FR-11 (`prds/prd-seva-desk-2026-11-01/prd.md`), ARCHITECTURE-SPINE AD-2, AD-4, AD-5, EXPERIENCE.md screen table + "Forbidden action" row. Review of this plan: 13 gaps found and fixed (2026-11-15).

## Global Constraints

- FR-10 table (verbatim): Manage Services, Working Hours, and team = Owner. Use the Inbox and approve Bookings = Owner, Staff. See own assigned Bookings = Owner, Staff, Technician. See the Dashboard = Owner, Staff.
- "A request for a forbidden action returns 403 and changes nothing."
- One `require_roles` helper on an `Actor` (AR-7). Role checks happen in the backend only (AD-5); the frontend only hides.
- A forbidden page shows exactly: `You don't have access to this page.` (UX-DR27)
- A 403 must not reveal whether a record exists: the role check runs BEFORE any lookup by id. Cross-Business reads by an allowed Role stay 404 (FR-11).
- Other modules import `accounts` only through `service.py` / `dependencies.py` (AD-2, import-linter in `backend/pyproject.toml`).
- `frontend/openapi.json` and `src/api/schema.d.ts` must match the backend (CI `git diff --exit-code`).
- Branch: `story/2-4-role-based-access`. PR body ends with `Closes #11`.

## Review Focus

1. **Multi-role Users** (Staff + Technician): they get the UNION of their Roles' rights, and are NOT limited to own Bookings. → Task 1 tests all 7 non-empty Role sets.
2. **Empty Role set:** the `Actor` model allows `roles=set()` (only the database forbids it). It must get no access. → Task 1 test.
3. **A late role check:** a future service writes first and checks the Role after. The 403 must still change nothing (the request's transaction rolls back, `core/db.py:45`). → Task 2 "late" probe test.
4. **Role changed while logged in:** the new Role applies on the next request (`resolve_session` reads the membership every request). → Task 2 test.
5. **Direct URL to a sub-page** (`/app/inbox/123`) for a Technician: shows the no-access message inside the normal shell. → Task 4 test.

Notes for later stories (do not build now):
- Owner-only settings pages (Stories 2.5, 3.1–3.3) must add a row to `canOpen` in `access.ts`; unlisted paths are open to any logged-in User.
- Buttons inside pages (Booking sheet, Customer detail) need the permissions in the page. Today they live in the layout's local state. Those stories add a way to share them.
- New Owner-only actions with no FR-10 row (e.g. delete Customer) add their own `Permission` row and update `EXPECTED`.
- The tab title on the no-access page stays the page's own title (e.g. "Inbox · SevaDesk"). Accepted.

---

### Task 0: Start the story (no code)

- [ ] Show the Story Map (CLAUDE.md §2) and get the User's prediction.
- [ ] `git switch -c story/2-4-role-based-access` from an up-to-date `main`.
- [ ] Check Docker Desktop runs (integration tests need it).

---

### Task 1: The FR-10 table, `require_roles`, and the Bookings rule (CORE) — checkpoint after

**Files:**
- Create: `backend/app/modules/accounts/permissions.py`
- Modify: `backend/app/modules/accounts/schemas.py` (add `Permission` next to `Role`)
- Modify: `backend/app/modules/accounts/service.py` (re-export, like `clean_email` at line 20)
- Modify: `backend/app/core/errors.py` (add `Forbidden` next to `NotFound`)
- Test: `backend/tests/unit/test_permissions.py`

**Interfaces:**
- Produces:
  - `class Forbidden(AppError)` in `app.core.errors`: code `"forbidden"`, message `"You don't have access to this."`, status 403.
  - `class Permission(StrEnum)` in `schemas.py`: `MANAGE_SETUP = "manage_setup"`, `USE_INBOX_AND_BOOKINGS = "use_inbox_and_bookings"`, `SEE_OWN_BOOKINGS = "see_own_bookings"`, `SEE_DASHBOARD = "see_dashboard"`. Docstring: one member per FR-10 row; a later action with no row adds its own member.
  - In `permissions.py` (imports from `schemas.py` only, never the other way):
    - `ALLOWED_ROLES: dict[Permission, frozenset[Role]]` — the FR-10 table, one comment per row.
    - `def permissions_for(roles: set[Role]) -> list[Permission]` — in enum order.
    - `def require_roles(actor: Actor, permission: Permission) -> None` — raises `Forbidden` when `actor.roles` and `ALLOWED_ROLES[permission]` share no Role.
    - `def assigned_bookings_filter(actor: Actor) -> uuid.UUID | None` — returns `actor.membership_id` when the Actor lacks `USE_INBOX_AND_BOOKINGS` (read from the table, not a second role list); else `None` (sees all, because they approve Bookings). Docstring: the bookings module filters `technician_membership_id == <value>` when not `None`.
  - `service.py` re-exports: `from app.modules.accounts.permissions import assigned_bookings_filter as assigned_bookings_filter` (same for `permissions_for`, `require_roles`), with one comment.

- [ ] **Step 1: Write the failing tests.** Build Actors with random UUIDs. `ALL_ROLE_SETS` = the 7 non-empty subsets of `Role` (`itertools.combinations`).

```python
EXPECTED = {  # FR-10, copied from the PRD table
    Permission.MANAGE_SETUP: {Role.OWNER},
    Permission.USE_INBOX_AND_BOOKINGS: {Role.OWNER, Role.STAFF},
    Permission.SEE_OWN_BOOKINGS: {Role.OWNER, Role.STAFF, Role.TECHNICIAN},
    Permission.SEE_DASHBOARD: {Role.OWNER, Role.STAFF},
}

def test_table_matches_fr10():
    assert {p: set(r) for p, r in ALLOWED_ROLES.items()} == EXPECTED

@pytest.mark.parametrize("permission", list(Permission))
@pytest.mark.parametrize("roles", ALL_ROLE_SETS)
def test_require_roles_allows_or_forbids(permission, roles):
    actor = make_actor(roles)
    if roles & EXPECTED[permission]:
        require_roles(actor, permission)          # no error
    else:
        with pytest.raises(Forbidden):
            require_roles(actor, permission)

@pytest.mark.parametrize("permission", list(Permission))
def test_empty_roles_get_nothing(permission):
    with pytest.raises(Forbidden):
        require_roles(make_actor(set()), permission)
    assert permissions_for(set()) == []

def test_permissions_for_technician_only():
    assert permissions_for({Role.TECHNICIAN}) == [Permission.SEE_OWN_BOOKINGS]

def test_permissions_for_staff_and_technician_is_union():
    assert permissions_for({Role.STAFF, Role.TECHNICIAN}) == [
        Permission.USE_INBOX_AND_BOOKINGS, Permission.SEE_OWN_BOOKINGS, Permission.SEE_DASHBOARD]

def test_technician_only_sees_own_bookings():
    actor = make_actor({Role.TECHNICIAN})
    assert assigned_bookings_filter(actor) == actor.membership_id

@pytest.mark.parametrize("roles", [{Role.OWNER, Role.TECHNICIAN}, {Role.STAFF}, {Role.STAFF, Role.TECHNICIAN}])
def test_owner_or_staff_sees_all_bookings(roles):
    assert assigned_bookings_filter(make_actor(roles)) is None

def test_forbidden_error_shape():
    err = Forbidden()
    assert (err.status_code, err.code, err.message) == (403, "forbidden", "You don't have access to this.")
```

- [ ] **Step 2: Run** `cd backend; uv run pytest tests/unit/test_permissions.py -q` → FAIL (import error).
- [ ] **Step 3: Implement** as in Interfaces. Use the `AppError` attribute names that `NotFound` already uses.
- [ ] **Step 4: Run** the same command → PASS. Then `uv run lint-imports` → all contracts kept.
- [ ] **Step 5: Commit** `feat(accounts): FR-10 permission table and require_roles (story 2.4)`

---

### Task 2: 403 end to end, and it changes nothing (CORE) — checkpoint after

**Files:**
- Modify: `backend/tests/integration/probe_app.py` (three probe routes; move `probe_client` here from `test_tenant_routes.py`)
- Modify: `backend/tests/integration/test_tenant_routes.py` (import `probe_client` from `probe_app`)
- Modify: `backend/tests/integration/conftest.py` (helper `set_owner_roles`)
- Modify: `backend/tests/integration/test_tenant_isolation.py:49-56` (`check_me` uses `set_owner_roles` instead of its inline `update`)
- Test: `backend/tests/integration/test_role_access.py` (no file-level marker)

**Interfaces:**
- Consumes: `require_roles`, `Permission` via `app.modules.accounts.service` (Task 1); `ActorDep`, `SessionDep`, `MembershipRepository`; `assert_not_found`, `membership_of`, `membership_is_active` from conftest.
- Produces (test-only):
  - `def probe_client(owner: TestClient, **kwargs) -> TestClient` in `probe_app.py` (moved, unchanged).
  - `GET /probe/permissions/{permission}` → `require_roles(actor, permission)`, returns `{"ok": "yes"}`.
  - `POST /probe/team/{membership_id}/deactivate` (204) → `require_roles(actor, MANAGE_SETUP)` FIRST, then `get_or_raise` and `row.is_active = False`.
  - `POST /probe/team/{membership_id}/deactivate-late` (204) → `get_or_raise`, `row.is_active = False`, `session.flush()` (the UPDATE reaches the database), THEN `require_roles(actor, MANAGE_SETUP)`. Comment: proves the rollback, not the order.
  - `def set_owner_roles(business_id: uuid.UUID, roles: list[str]) -> None` in conftest — direct database update of that Business's one membership.

- [ ] **Step 1: Write the failing tests:**
  - `test_allowed_role_gets_200` — Staff (`set_owner_roles(["staff"])`) GETs `use_inbox_and_bookings` → 200.
  - `test_forbidden_role_gets_403_envelope` — Technician GETs `manage_setup` → 403, body `{"error": {"code": "forbidden", "message": "You don't have access to this."}}`.
  - `test_multi_role_gets_union` — `["staff", "technician"]` GETs `see_dashboard` → 200 and `manage_setup` → 403.
  - `test_forbidden_write_changes_nothing` — Technician POSTs `deactivate` on own membership → 403; `membership_is_active` still `True`.
  - `test_late_check_still_changes_nothing` — Technician POSTs `deactivate-late` on own membership → 403; `membership_is_active` still `True`.
  - `test_403_does_not_reveal_records` — Technician POSTs `deactivate` for (a) own id, (b) another Business's id, (c) `uuid.uuid7()` → all three the same 403 body.
  - `test_owner_write_is_allowed` — default Owner roles; POST `deactivate` → 204; membership now inactive.
  - `test_new_roles_apply_on_next_request` — Owner GETs `manage_setup` → 200; `set_owner_roles(["staff"])`; same client → 403.
  - `@pytest.mark.isolation` on this one only: `test_other_business_record_is_404_for_owner` — Owner A POSTs `deactivate` for Business B's membership id → `assert_not_found`; B's membership still active.
- [ ] **Step 2: Run** `cd backend; uv run pytest tests/integration/test_role_access.py -q` → FAIL (routes missing).
- [ ] **Step 3: Implement** the probe routes, move `probe_client`, add `set_owner_roles`, update `check_me`.
- [ ] **Step 4: Run** `uv run pytest tests/integration/test_role_access.py tests/integration/test_tenant_routes.py tests/integration/test_tenant_isolation.py -q` → PASS.
- [ ] **Step 5: Commit** `test: FR-10 answers 403 over HTTP and changes nothing (story 2.4)`

---

### Task 3: `/me` and log-in return `permissions` (STANDARD)

**Files:**
- Modify: `backend/app/modules/accounts/schemas.py` (`MeResponse`), `router.py` (lines 30 and 42)
- Modify: `backend/tests/integration/test_login.py:53`
- Test: new `/me` test in `backend/tests/integration/test_role_access.py`
- Regenerate (BOILERPLATE): `frontend/openapi.json`, `frontend/src/api/schema.d.ts`

**Interfaces:**
- Consumes: `permissions_for` via `service` (Task 1); `set_owner_roles` (Task 2).
- Produces: `MeResponse` = `{"roles": list[Role], "permissions": list[Permission]}`. Built in one place: `def _me(roles: set[Role]) -> MeResponse` in `router.py`, returning `MeResponse(roles=sorted(roles), permissions=service.permissions_for(roles))`. Both `log_in` and `get_me` use it. No method on `MeResponse` (that would be a circular import).

- [ ] **Step 1: Change / add the tests:**
  - `test_login.py:53`: body is `{"roles": ["owner", "technician"], "permissions": ["manage_setup", "use_inbox_and_bookings", "see_own_bookings", "see_dashboard"]}`.
  - `test_me_lists_only_own_permissions` — `set_owner_roles(["technician"])`; GET `/api/v1/me` → `{"roles": ["technician"], "permissions": ["see_own_bookings"]}`.
- [ ] **Step 2: Run** them → FAIL (no `permissions` key).
- [ ] **Step 3: Implement** `_me` and use it in both routes.
- [ ] **Step 4: Run** `uv run pytest tests/integration/test_login.py tests/integration/test_role_access.py -q` → PASS. Then regenerate: `uv run python -m app.export_openapi ../frontend/openapi.json`, `cd ../frontend; npm run gen:api`.
- [ ] **Step 5: Commit** `feat(accounts): /me and log-in return the Actor's permissions (story 2.4)`

---

### Task 4: The app hides what a Role may not do (STANDARD)

**Files:**
- Create: `frontend/src/lib/access.ts`, `frontend/src/lib/access.test.ts`
- Create: `frontend/src/components/NoAccess.tsx`
- Modify: `frontend/src/lib/nav.ts`, `nav.test.ts`, `lib/auth.ts`, `auth.test.ts`, `components/AppShell.tsx`, `AppShell.test.tsx`, `components/LoginForm.tsx`, `LoginForm.test.tsx`, `app/app/layout.tsx`, `app/app/layout.test.tsx`
- No change: `SignupForm.tsx` (sign-up always makes an Owner, so `/app` stays right).

**Interfaces:**
- Consumes: `components["schemas"]["Permission"]` from `@/api/schema` (Task 3).
- Produces (in `access.ts`):
  - `export type Permission = components["schemas"]["Permission"]`
  - `export function isUnder(pathname: string, href: string): boolean` — `"/app"` matches exactly; any other `href` matches itself and its sub-pages. Moved from `AppShell.isCurrent`; `AppShell` uses it.
  - `export function canOpen(pathname: string, permissions: Permission[]): boolean` — one table: `/app` needs `see_dashboard`; `/app/inbox` (and sub-pages) needs `use_inbox_and_bookings`. Every other path is open to any logged-in User. Comment: Owner-only settings pages add their row in their own stories.
  - `navItems(permissions: Permission[])` = the four items filtered by `canOpen(item.href, permissions)`, same order as today.
  - `landingPath(permissions: Permission[])` → `"/app"` if it includes `see_dashboard`, else `"/app/calendar"`.
  - `AppShell` prop `roles` renamed to `permissions`.
  - `NoAccess`: `<main>` with `<h1>You don't have access to this page.</h1>`, same classes as other pages.
  - `layout.tsx` stores `data.permissions`, reads `usePathname()`, renders `canOpen(pathname, permissions) ? children : <NoAccess />` inside `AppShell` (the nav stays).

- [ ] **Step 1: Write the failing tests:**
  - `access.test.ts`: Technician-only (`["see_own_bookings"]`) cannot open `/app`, `/app/inbox`, `/app/inbox/123`; can open `/app/calendar`, `/app/more`. Staff (`use_inbox_and_bookings, see_own_bookings, see_dashboard`) can open all four. `isUnder("/app/inbox/1", "/app") === false`.
  - `nav.test.ts`, `auth.test.ts`: same expectations as today, written with permissions.
  - `layout.test.tsx`: make the pathname a `vi.hoisted` variable each test sets; add `permissions` to the `beforeEach` mock (`{ roles: ["owner", "technician"], permissions: [all four] }`). New: Technician-only on `/app/inbox` → heading `You don't have access to this page.` shows, the child does not, the nav still shows Calendar. Owner on `/app/inbox` → child shows.
  - `AppShell.test.tsx:11,25`: pass `permissions` instead of `roles`.
  - `LoginForm.test.tsx:35`: response with `permissions: ["see_own_bookings"]` → goes to `/app/calendar`.
- [ ] **Step 2: Run** `cd frontend; npm test` → FAIL.
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run** `npm test; npm run lint; npm run typecheck` → all PASS.
- [ ] **Step 5: Commit** `feat(app): hide forbidden nav and pages per permission (story 2.4)`

---

### Task 5: Full CI check (BOILERPLATE)

- [ ] From the repo root: `uv run --project backend ruff check .` and `uv run --project backend ruff format --check .` → clean.
- [ ] In `backend/`: `uv run lint-imports`, `uv run pytest -m isolation`, `uv run pytest --cov` (≥ 80%) → PASS.
- [ ] In `backend/`: `uv run python -m app.export_openapi ../frontend/openapi.json`; in `frontend/`: `npm run gen:api`; then `git diff --exit-code -- frontend/openapi.json frontend/src/api/schema.d.ts` → no diff.
- [ ] In `frontend/`: `npm test`, `npm run lint`, `npm run typecheck` → PASS.

---

### Task 6: Learning steps, docs, PR

- [ ] Understanding Gate (CLAUDE.md §5): 3 questions — one "why" (e.g. why 403 here but 404 for another Business), one "data flow" (cookie → Actor → `require_roles` → 403), one "what breaks if…" (e.g. the role check ran after the lookup). Log wrong-twice answers in `docs/learning/gaps.md`.
- [ ] Hands-on task (CLAUDE.md §6, 5–15 min, the User does it by hand): add one test to `test_permissions.py` that proves a Staff-only Actor cannot `MANAGE_SETUP` but can `SEE_DASHBOARD`. Review it after.
- [ ] Write `docs/learning/2-4.md` (what, why, concept: authorization vs authentication, 403 vs 404, key files).
- [ ] Add to `docs/learning/glossary.md`: authorization, permission, 403 Forbidden, union of Roles.
- [ ] Set `2-4-role-based-access: done` in `_bmad-output/implementation-artifacts/sprint-status.yaml` in this PR.
- [ ] Commit `docs(learning): Story 2.4 notes, glossary, status done`; open the PR with `Closes #11`.
