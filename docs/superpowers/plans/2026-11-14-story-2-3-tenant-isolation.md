# Story 2.3 — Tenant isolation is tested on every pull request — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (CLAUDE.md: CORE-heavy story → inline with checkpoints). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, on every PR, that no Business can read or change another Business's data, and make the code and the database refuse it by default.

**Architecture:** Four guards, each owned by one place. (1) `accounts/dependencies.py`: `ActorDep` now runs every logged-in route inside `tenant_scope(actor.business_id)`, so the base repository works in routes. (2) `core`: one `NotFound` error and `TenantRepository.get_or_raise()`, so "another Business's id" is always a 404. (3) A tenant-isolation test suite that reads the OpenAPI schema and fails when an endpoint has no isolation entry. (4) Static and schema guards: Ruff bans `text()` / `TextClause` outside `core`; a schema rule function demands `UNIQUE (business_id, id)` and composite foreign keys on every tenant table.

**Tech Stack:** FastAPI 0.162, Starlette 1.10, anyio 4.16, SQLAlchemy 2.1.6, Postgres 18 (Testcontainers), Ruff 0.17.1 (`TID251` banned-api), pytest markers.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → Story 2.3 (lines 501–529); AD-3 in `_bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md:69-74`; FR-11 and NFR-1 in `_bmad-output/planning-artifacts/prds/prd-seva-desk-2026-11-01/prd.md`.

**Plan review:** Opus critique on 2026-11-14 (19 findings, all applied by user decision). D1 was verified in the installed library source: the async-generator dependency enters and exits in the request's own task (`fastapi/dependencies/utils.py` ~L623, `fastapi/routing.py:146-152`), and anyio copies the context into the sync route's thread (`anyio/_backends/_asyncio.py:2771`).

## Decisions (confirmed 2026-11-14)

| # | Topic | Decision | Why |
|---|---|---|---|
| D1 | Where tenant scope is set for routes | `ActorDep = Annotated[Actor, Depends(actor_in_tenant_scope, scope="function")]`. `actor_in_tenant_scope` is an **async** generator that depends on the sync `get_actor` and enters `tenant_scope`. | A sync dependency runs in a worker thread, so its context var never reaches the route. An async one runs in the request's task; anyio copies that context into the route's thread. `scope="function"` ends the tenant scope before `BackgroundTasks` run (jobs get their tenant from the payload, AD-3). |
| D2 | 404 rule | `core.errors.NotFound` (`not_found`, 404, "We could not find that.") + `TenantRepository.get_or_raise(id)`. | One place owns "missing or another Business's → 404". |
| D3 | No by-id endpoint exists yet | Prove D1 + D2 with a **test-only** FastAPI app (probe routes). No production endpoint. | "Build only the current story." |
| D4 | Endpoint list | Every route must be in exactly one dict: `NO_TENANT_DATA` (with a reason) or `ISOLATION_CHECKS` (with a check). A route that uses `ActorDep` or has a `{path param}` must be in `ISOLATION_CHECKS`. The 5 exempt endpoints today: hello, health, health/worker, signup, login. | A new endpoint fails the suite; a tenant endpoint cannot be excused with a reason. |
| D5 | `text()` ban | Ruff `TID251` bans `sqlalchemy.text`, `sqlalchemy.sql.text`, `sqlalchemy.sql.expression.text`, `sqlalchemy.TextClause`, `sqlalchemy.sql.elements.TextClause`, `sqlalchemy.sql.expression.TextClause`. Exempt: `backend/app/core/**`, `backend/tests/**`, `backend/migrations/**`. | Installed tool; runs in the lint job. Verified with ruff 0.17.1: catches aliases, `sa.text`, `sqlalchemy.sql` imports; the core ignore works from the repo root. |
| D6 | Composite FK rule | One function `tenant_schema_violations(inspector) -> list[str]`, run against the real DB and proven red on a deliberately bad table. | Today no tenant table links to another; the rule must still be shown to bite. |
| D7 | CI | A step `Tenant isolation suite (FR-11)` runs `pytest -m isolation` before the full run in the `test` job. Main's branch protection already requires `test` (with `enforce_admins`), so a failure blocks the merge. The isolation tests run twice; that is accepted. | The step is visible in the job log. `-m isolation` with 0 tests exits 5, so it cannot pass empty. |

## Global Constraints

- Branch `story/2-3-tenant-isolation` (created in Task 0). GitHub issue #10. PR flow: push → `gh pr create` (`Closes #10`) → green → Understanding Gate → `gh pr merge --merge --delete-branch`. Sprint-status `done` is committed inside the PR.
- **Backend commands run in WSL.** `BE` means `wsl -e bash -lc 'cd "/mnt/c/Books/DataSense Community/Seva Desk/backend" && <command>'`.
- Cross-Business access by id → **404 with the `not_found` envelope**, never 403, and nothing changes (FR-11). A bare Starlette 404 (`{"detail": "Not Found"}`) does **not** count.
- Repository methods never take a `business_id` parameter (AD-3).
- Global tables: `alembic_version`, `app_meta`, `businesses`, `users`, `sessions`. Every other table is a tenant table.
- `core` imports no module (import-linter). No new dependencies (no pyyaml). Services never commit (AD-15).
- No production endpoint is added, so `frontend/openapi.json` does not change.
- Every isolation test file has `pytestmark = pytest.mark.isolation`.

## Review Focus

1. A route outside the schema (`include_in_schema=False`, `app.mount`, `add_route`) skips the list → the suite checks every entry of `app.routes`. Test in Task 3.
2. A tenant endpoint is put in `NO_TENANT_DATA` → a dependency-tree walk forbids it. Test in Task 3.
3. A cross-Business write returns 404 **and** the row is unchanged, while the same write on the own Business does change it. Test in Task 2.
4. A tenant repository method gets a `business_id` parameter → a recursive subclass scan finds it. Test in Task 4.
5. Tenant scope is still set after the dependency exits → a unit test drives the generator and checks it. Test in Task 1.

Not covered (list in the PR):
- `Connection.exec_driver_sql()` also runs raw SQL; Ruff cannot ban a method.
- The base repository adds the filter only through `_select()`. A subclass `update()`/`delete()` or a bare `select(Model)` gets no filter; only `get`/`get_or_raise`/`add` are tested.
- Background jobs (NFR-1) and the Redis key rule (`purpose:business_id:…`): none is tenant-scoped yet.
- Postgres Row-Level Security stays post-MVP (spine line 354).

---

### Task 0: Branch and Story Map (learning step)

- [ ] **Step 1:** `git checkout -b story/2-3-tenant-isolation`; commit this plan: `docs(plan): Story 2.3 tenant isolation plan`.
- [ ] **Step 2:** Show the Story Map (≤ 5 bullets, CLAUDE.md §2) and ask the user one prediction question. Wait for the answer.

### Task 1: Logged-in routes run inside tenant scope (CORE)

**Files:**
- Modify: `backend/app/modules/accounts/dependencies.py`
- Modify: `backend/tests/integration/conftest.py` (fixture `sign_up_owner`)
- Create: `backend/tests/integration/probe_app.py` (test-only app; Task 2 adds routes)
- Create: `backend/tests/integration/test_tenant_routes.py` (`pytestmark = pytest.mark.isolation`)
- Create: `backend/tests/unit/test_actor_tenant_scope.py` (`pytestmark = pytest.mark.isolation`)

**Interfaces:**
- Produces: `async def actor_in_tenant_scope(actor: Annotated[Actor, Depends(get_actor)]) -> AsyncIterator[Actor]` — `with tenant_scope(actor.business_id): yield actor`. `ActorDep` as in D1. `get_actor` is unchanged. Comment the `async` and `scope="function"` choices in 3–4 lines.
- Produces (conftest): fixture `sign_up_owner(make_client)` → a function `() -> tuple[TestClient, uuid.UUID]`. Each call builds a new client, posts `/api/v1/signup` with a unique email, asserts 201, and returns `(client, uuid.UUID(body["business_id"]))`.
- Produces (`probe_app.py`): `build_probe_app() -> FastAPI` — `FastAPI()` + `register_error_handlers`, with:
  - `GET /probe/business` (sync, `actor: ActorDep`) → `{"business_id": str(current_business_id())}`.
  - `GET /probe/no-actor` (sync, no `ActorDep`) → calls `current_business_id()`; with `TestClient(..., raise_server_exceptions=False)` it must answer 500.
- Produces (`test_tenant_routes.py`): `probe_client(owner: TestClient) -> TestClient` — `TestClient(build_probe_app(), base_url="https://testserver", headers={"Origin": "https://testserver"}, cookies=owner.cookies)`.

- [ ] **Step 1: Write the failing tests** (behaviour: a logged-in route sees its own Business; no route gets a Business without `ActorDep`; the scope ends when the dependency exits)

```python
# test_tenant_routes.py
def test_logged_in_route_runs_in_own_business(sign_up_owner):
    owner, business_id = sign_up_owner()
    response = probe_client(owner).get("/probe/business")
    assert response.status_code == 200
    assert response.json() == {"business_id": str(business_id)}

def test_two_owners_each_see_their_own_business(sign_up_owner):
    (a, a_id), (b, b_id) = sign_up_owner(), sign_up_owner()
    assert probe_client(a).get("/probe/business").json()["business_id"] == str(a_id)
    assert probe_client(b).get("/probe/business").json()["business_id"] == str(b_id)

def test_route_without_actor_has_no_business(sign_up_owner):
    owner, _ = sign_up_owner()  # a valid cookie is not enough: only ActorDep sets the scope
    client = TestClient(build_probe_app(), base_url="https://testserver",
                        cookies=owner.cookies, raise_server_exceptions=False)
    assert client.get("/probe/no-actor").status_code == 500

def test_probe_without_cookie_is_401(make_client):
    response = TestClient(build_probe_app(), base_url="https://testserver").get("/probe/business")
    assert response.status_code == 401

# test_actor_tenant_scope.py (unit, no DB)
def test_scope_is_set_inside_and_cleared_after():
    actor = Actor(user_id=uuid.uuid7(), membership_id=uuid.uuid7(), business_id=uuid.uuid7(), roles={"owner"})
    async def drive():
        gen = actor_in_tenant_scope(actor)
        assert await anext(gen) is actor
        assert current_business_id() == actor.business_id
        await gen.aclose()
        with pytest.raises(TenantContextMissing):
            current_business_id()
    asyncio.run(drive())
```

- [ ] **Step 2: Run, expect FAIL** — `BE uv run pytest tests/integration/test_tenant_routes.py tests/unit/test_actor_tenant_scope.py -v`. The two "own business" tests fail: TestClient re-raises `TenantContextMissing` from the route. The unit test fails with `ImportError: actor_in_tenant_scope`.
- [ ] **Step 3: Implement** `actor_in_tenant_scope` and the new `ActorDep`.
- [ ] **Step 4: Run the files, then the whole backend suite** — `BE uv run pytest -q` → all PASS (`/me` still works).
- [ ] **Step 5: Commit** — `feat(accounts): run logged-in routes inside the tenant scope (story 2.3)`

### Task 2: Another Business's id is a 404 and changes nothing (CORE)

**Files:**
- Modify: `backend/app/core/errors.py` (add `NotFound`)
- Modify: `backend/app/core/repository.py` (add `get_or_raise`)
- Modify: `backend/tests/integration/probe_app.py` (two by-id routes)
- Modify: `backend/tests/integration/conftest.py` (`assert_not_found`, `membership_of`, `membership_is_active`)
- Modify: `backend/tests/integration/test_tenant_routes.py`, `backend/tests/integration/test_tenant_repository.py` (add `pytestmark = pytest.mark.isolation` there too)

**Interfaces:**
- Produces: `class NotFound(AppError)` — `NotFound()` → `code="not_found"`, `message="We could not find that."`, `status_code=404`.
- Produces: `TenantRepository.get_or_raise(self, id: uuid.UUID) -> ModelT` — `get(id)` or raise `NotFound()`.
- Produces (probe, written in **Step 1**, they are test code): `GET /probe/memberships/{membership_id}` → `{"id": str(row.id)}` via `MembershipRepository(session).get_or_raise`; `POST /probe/memberships/{membership_id}/deactivate` → `get_or_raise`, then `row.is_active = False`, status 204. Both take `session: SessionDep, actor: ActorDep`.
- Produces (conftest, plain functions, imported as `from tests.integration.conftest import …` or exposed as fixtures):
  - `assert_not_found(response) -> None` — `status_code == 404` and `json() == {"error": {"code": "not_found", "message": "We could not find that."}}`. Every 404 check in this story and every future isolation check uses it.
  - `membership_of(business_id) -> uuid.UUID` and `membership_is_active(business_id) -> bool` — a raw `Session(get_engine())` with `select(Membership…).where(Membership.business_id == business_id)`. No `session_lookup`, no `system_scope`.

- [ ] **Step 1: Write the probe routes and the failing tests**

```python
# test_tenant_repository.py — import NotFound inside the test, so the other tests still collect
def test_get_or_raise_hides_other_business(session):
    from app.core.errors import NotFound
    ...  # membership_b in Business B
    with tenant_scope(business_a), pytest.raises(NotFound) as caught:
        MembershipRepository(session).get_or_raise(membership_b.id)
    assert caught.value.status_code == 404

# test_tenant_routes.py
def test_read_own_record_by_id_is_200(sign_up_owner):
    a, a_id = sign_up_owner()
    response = probe_client(a).get(f"/probe/memberships/{membership_of(a_id)}")
    assert response.json() == {"id": str(membership_of(a_id))}

def test_read_other_business_by_id_is_404(sign_up_owner):
    (a, _), (b, b_id) = sign_up_owner(), sign_up_owner()
    assert_not_found(probe_client(a).get(f"/probe/memberships/{membership_of(b_id)}"))

def test_write_own_record_changes_it(sign_up_owner):
    # Positive control: the probe write really writes.
    a, a_id = sign_up_owner()
    assert probe_client(a).post(f"/probe/memberships/{membership_of(a_id)}/deactivate").status_code == 204
    assert membership_is_active(a_id) is False

def test_write_other_business_by_id_is_404_and_changes_nothing(sign_up_owner):
    (a, _), (b, b_id) = sign_up_owner(), sign_up_owner()
    assert_not_found(probe_client(a).post(f"/probe/memberships/{membership_of(b_id)}/deactivate"))
    assert membership_is_active(b_id) is True
    assert b.get("/api/v1/me").status_code == 200
```

- [ ] **Step 2: Run, expect FAIL for the right reason** — the probe routes raise `AttributeError: get_or_raise` (re-raised by TestClient); the repository test fails on `ImportError: NotFound`. No test is green because of a routing 404 (`assert_not_found` checks the envelope).
- [ ] **Step 3: Implement** `NotFound` and `get_or_raise`.
- [ ] **Step 4: Run** — `BE uv run pytest tests/integration/test_tenant_routes.py tests/integration/test_tenant_repository.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat(core): NotFound and get_or_raise make another Business's id a 404 (story 2.3)`

### Task 3: The isolation suite covers every endpoint (CORE)

**Files:**
- Create: `backend/tests/integration/test_tenant_isolation.py` (`pytestmark = pytest.mark.isolation`)
- Modify: `backend/pyproject.toml` (`[tool.pytest.ini_options]`: `markers = ["isolation: tenant-isolation suite (FR-11)"]`, `addopts = "--strict-markers"`)

**Interfaces:**
- Produces: `HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}`; `api_operations(schema: dict) -> set[tuple[str, str]]` — `(METHOD, path)` for each key in `HTTP_METHODS` under `schema["paths"]`.
- Produces: `unlisted(operations: set[tuple[str, str]]) -> set[tuple[str, str]]` — `operations - (NO_TENANT_DATA.keys() | ISOLATION_CHECKS.keys())`.
- Produces: `needs_isolation_check(route: APIRoute) -> bool` — `True` if the path has a `{param}`, or if `actor_in_tenant_scope` is anywhere in the dependency tree (walk `route.dependant.dependencies` recursively, compare `dep.call`).
- Produces: `FRAMEWORK_PATHS = {"/api/openapi.json", "/api/docs", "/docs/oauth2-redirect", "/redoc"}` — the only non-`APIRoute` entries allowed. **As built:** FastAPI 0.162 wraps included routers in `_IncludedRouter`, so `app.routes` holds no `APIRoute`s; the suite walks `fastapi.routing.iter_route_contexts(app.routes)` (the public helper `get_openapi` uses).
- Produces: `NO_TENANT_DATA: dict[tuple[str, str], str]` — `("GET", "/api/v1/hello")`, `("GET", "/api/health")`, `("GET", "/api/health/worker")`, `("POST", "/api/v1/signup")`, `("POST", "/api/v1/login")`, each with a one-line reason.
- Produces: `ISOLATION_CHECKS: dict[tuple[str, str], Callable[[TwoOwners], None]]`:
  - `("GET", "/api/v1/me")`: first set B's membership `roles = ["owner"]` with a direct UPDATE (A keeps `owner, technician` from sign-up). Then A's `/me` roles == `["owner", "technician"]` (sorted) and B's == `["owner"]`. A mix-up would show.
  - `("POST", "/api/v1/logout")`: A logs out → A's `/me` is 401, B's `/me` is still 200.
- Produces: `@dataclass TwoOwners(a: TestClient, a_business_id: uuid.UUID, b: TestClient, b_business_id: uuid.UUID)`; fixture `two_owners(sign_up_owner)`.
- Header comment: how to add a new endpoint (a check that calls it as A with B's ids, uses `assert_not_found`, and proves B's row unchanged; or a reason in `NO_TENANT_DATA` only if `needs_isolation_check` is false).

- [ ] **Step 1: Write the tests**

```python
def test_every_endpoint_is_listed_once():
    assert not (NO_TENANT_DATA.keys() & ISOLATION_CHECKS.keys()), "listed twice"
    ops = api_operations(app.openapi())
    assert unlisted(ops) == set(), "new endpoint with no isolation check"
    assert (NO_TENANT_DATA.keys() | ISOLATION_CHECKS.keys()) - ops == set(), "listed endpoint no longer exists"

def test_unlisted_catches_a_new_endpoint():
    schema = {"paths": {"/api/v1/services/{service_id}": {"get": {}, "parameters": []}}}
    assert unlisted(api_operations(schema)) == {("GET", "/api/v1/services/{service_id}")}

def test_no_route_is_hidden_from_the_schema():
    routes = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes |= {(m, route.path) for m in route.methods}
        else:
            assert route.path in FRAMEWORK_PATHS, f"unexpected non-API route {route.path}"
    assert routes == api_operations(app.openapi())

def test_tenant_endpoints_are_not_excused():
    for route in app.routes:
        if isinstance(route, APIRoute) and needs_isolation_check(route):
            for m in route.methods:
                assert (m, route.path) in ISOLATION_CHECKS, f"{m} {route.path} needs an isolation check"

@pytest.mark.parametrize("operation", sorted(ISOLATION_CHECKS), ids=" ".join)
def test_cross_business_access_fails(operation, two_owners):
    ISOLATION_CHECKS[operation](two_owners)
```

- [ ] **Step 2: Prove the guards bite** — (a) leave `("POST", "/api/v1/logout")` out of both dicts → `test_every_endpoint_is_listed_once` fails naming it; (b) move `("GET", "/api/v1/me")` into `NO_TENANT_DATA` → `test_tenant_endpoints_are_not_excused` fails; (c) skip the roles UPDATE and make A's check read B's `/me` → the `/me` check fails. Undo all three.
- [ ] **Step 3: Run** — `BE uv run pytest -m isolation -v` → PASS; `BE uv run pytest -q` → PASS (strict markers break nothing).
- [ ] **Step 4: Commit** — `test: tenant-isolation suite lists every API endpoint (story 2.3)`

### Task 4: Database and repository guards (CORE)

**Files:**
- Create: `backend/tests/integration/test_tenant_schema.py` (`pytestmark = pytest.mark.isolation`)
- Create: `backend/tests/unit/test_tenant_repository_rules.py` (`pytestmark = pytest.mark.isolation`)
- Modify: `backend/app/core/repository.py` (header comment: the composite-FK rule for new tenant tables)

**Interfaces:**
- Produces (in `test_tenant_schema.py`): `GLOBAL_TABLES = {"alembic_version", "app_meta", "businesses", "users", "sessions"}`; `tenant_schema_violations(inspector) -> list[str]` — for the `public` schema:
  - a table that is not in `GLOBAL_TABLES` and has no FK `business_id → businesses.id` → "neither global nor tenant";
  - a tenant table without a unique constraint whose columns are `{"business_id", "id"}` → "missing UNIQUE (business_id, id)";
  - an FK whose `referred_table` is a tenant table, unless the pairs `zip(constrained_columns, referred_columns)` contain `("business_id", "business_id")` and `set(referred_columns) == {"business_id", "id"}` → "link to <table> is not composite".
- Produces (in `test_tenant_repository_rules.py`): `all_subclasses(cls) -> set[type]` (recursive); module import by `pkgutil.walk_packages(app.modules.__path__, "app.modules.")` + `importlib.import_module` (not `import app.main`: it starts telemetry).

- [ ] **Step 1: Write the tests**

```python
# test_tenant_schema.py — each test uses one connection inside conn.begin() and rolls back
def test_real_schema_follows_the_tenant_rules(migrated_db):
    with get_engine().connect() as conn:
        assert tenant_schema_violations(inspect(conn)) == []

def test_rules_catch_a_bad_tenant_table(migrated_db):
    with get_engine().connect() as conn, conn.begin() as tx:
        # A real table in public (not TEMP: the inspector reads only public).
        conn.execute(text("CREATE TABLE bad_notes (id uuid PRIMARY KEY, "
                          "business_id uuid REFERENCES businesses(id), "
                          "membership_id uuid REFERENCES memberships(id))"))
        violations = tenant_schema_violations(inspect(conn))
        tx.rollback()
    assert any("bad_notes" in v and "UNIQUE" in v for v in violations)
    assert any("bad_notes" in v and "not composite" in v for v in violations)

def test_database_refuses_a_link_to_another_business(migrated_db):
    # Reflect memberships into the scratch MetaData, so the composite FK can resolve.
    with get_engine().connect() as conn, conn.begin() as tx:
        md = MetaData(); Table("memberships", md, autoload_with=conn)
        notes = Table("good_notes", md, Column("id", Uuid, primary_key=True),
                      Column("business_id", Uuid), Column("membership_id", Uuid),
                      ForeignKeyConstraint(["business_id", "membership_id"],
                                           ["memberships.business_id", "memberships.id"]))
        notes.create(conn)
        # ... make Business A and B with one membership each on this connection
        conn.execute(notes.insert().values(id=uuid.uuid7(), business_id=a_id, membership_id=a_membership))  # works
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(notes.insert().values(id=uuid.uuid7(), business_id=a_id, membership_id=b_membership))
        tx.rollback()

# test_tenant_repository_rules.py
def test_no_tenant_repository_method_takes_business_id():
    for info in pkgutil.walk_packages(app.modules.__path__, "app.modules."):
        importlib.import_module(info.name)
    repos = all_subclasses(TenantRepository)
    assert MembershipRepository in repos  # the scan cannot pass empty
    for repo in repos:
        for name, fn in inspect.getmembers(repo, inspect.isfunction):
            assert "business_id" not in inspect.signature(fn).parameters, f"{repo.__name__}.{name}"
```

- [ ] **Step 2: Prove they bite** — (a) change `good_notes` to a single-column FK `["membership_id"] → ["memberships.id"]` → the refusal test fails (no IntegrityError); (b) add a scratch method `def find(self, business_id)` to `MembershipRepository` → the unit test fails. Undo both. (`test_rules_catch_a_bad_tenant_table` is the red proof for the schema rules.)
- [ ] **Step 3: Run** — `BE uv run pytest tests/integration/test_tenant_schema.py tests/unit/test_tenant_repository_rules.py -v` → PASS.
- [ ] **Step 4: Commit** — `test: schema and repository guards for tenant tables (story 2.3)`

### Task 5: CI checks — `text()` ban and the isolation step (STANDARD)

**Files:**
- Modify: `ruff.toml`
- Modify: `.github/workflows/ci.yml` (test job)
- Modify: `backend/tests/unit/test_ci_workflow.py`

**Interfaces:**
- `ruff.toml`: add `"TID251"` (only this rule, not `"TID"`) to `select`; `[lint.flake8-tidy-imports.banned-api]` with the six paths from D5, each `msg = "Raw SQL skips the tenant filter. Use it only in app/core (AD-3)."`; `[lint.per-file-ignores]` `"backend/app/core/**" = ["TID251"]`, `"backend/tests/**" = ["TID251"]`, `"backend/migrations/**" = ["TID251"]`.
- `ci.yml` test job, before `Backend tests (coverage gate)`: step `name: Tenant isolation suite (FR-11)`, `working-directory: backend`, `run: uv run pytest -m isolation`.

- [ ] **Step 1: Write the failing test** `test_ci_runs_the_isolation_suite` with the existing text helper `_job_block("test")` (no YAML library): the block contains `Tenant isolation suite (FR-11)` and `uv run pytest -m isolation`, and `block.index("Tenant isolation suite (FR-11)") < block.index("Backend tests (coverage gate)")`.
- [ ] **Step 2: Run, expect FAIL** (`ValueError`/assert: step missing); edit `ci.yml` → PASS.
- [ ] **Step 3: Edit `ruff.toml`.** Prove it: a scratch `backend/app/modules/business/_scratch.py` with `from sqlalchemy import text as t` and a second line `from sqlalchemy import TextClause` → `BE uv run ruff check ..` reports two `TID251`. Delete the scratch file → clean; `app/core/health.py` is not flagged.
- [ ] **Step 4: Full local gate** — `BE uv run ruff check .. && uv run ruff format --check .. && uv run lint-imports && uv run pytest -m isolation && uv run pytest --cov` → all PASS, coverage ≥ 80%.
- [ ] **Step 5: Commit** — `ci: ban raw SQL outside core; run the isolation suite as its own step (story 2.3)`

### Task 6: Learning notes, PR, Understanding Gate, merge

**Files:**
- Create: `docs/learning/2-3.md`
- Modify: `docs/learning/glossary.md` (tenant isolation suite, composite foreign key, banned API, context copy into a thread pool, 404-not-403, positive control)
- Modify: `_bmad-output/implementation-artifacts/sprint-status.yaml` (`2-3-…: done`, `last_updated`)

- [ ] **Step 1:** Write the notes and glossary lines (short, plain words). Commit `docs(learning): Story 2.3 notes, glossary, status done`.
- [ ] **Step 2:** Push; `gh pr create` with `Closes #10`, the "Not covered" list from Review Focus, the 2.2 deferred item this story closes (`get_actor` sync → tenant scope), and AC5 proof: branch protection on `main` requires the `test` job (with `enforce_admins`), and that job runs the isolation step.
- [ ] **Step 3:** Wait for CI green on the PR (the `test` job; the isolation step is in its log).
- [ ] **Step 4: Understanding Gate** (CLAUDE.md §5) — 3 questions, one at a time, each with the doc path + section to read first: one "why", one "how does data flow", one "what breaks if…". Log wrong answers in `docs/learning/gaps.md`.
- [ ] **Step 5: Hands-on task** (CLAUDE.md §6) — give one 5–15 minute change for the user to make by hand; review it.
- [ ] **Step 6:** `gh pr merge --merge --delete-branch`; close #10; update the resume-point memory; remind the user to `/clear`.
