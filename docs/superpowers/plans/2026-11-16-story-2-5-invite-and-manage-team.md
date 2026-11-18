# Story 2.5 — Invite team members and manage the team Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (CORE-heavy story: checkpoints after each CORE task, per CLAUDE.md §4). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Owner creates a single-use, 7-day invite link with one or more Roles; the invited person opens `/invite/{token}`, sets a password, and is logged in; on Settings → Team the Owner changes Roles and deactivates members.

**Architecture:** `accounts` owns the new tenant table `invites` (only a SHA-256 hash of the token is stored, like sessions). Owner actions live in a new `accounts/team.py` + `accounts/team_router.py`; each one calls `require_roles(actor, MANAGE_SETUP)` first. Invite accept has no session, so it finds the invite in an audited `system_scope("invite_accept")`, locks the row (`SELECT … FOR UPDATE`), then creates the User + membership inside `tenant_scope(invite.business_id)`. The token travels only in POST bodies, never in an API path, because request logs record the path (`core/telemetry.py:227`); the OpenTelemetry Collector rewrites `/invite/<token>` to `/invite/:token` in every span (name and `url.path`), so traces never hold the token either (changed during Task 8, see there). The frontend reads permissions from a small React context, shows a "Team" link on More for Owners, and has two new pages.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, pytest + testcontainers (Python 3.14); Next.js 16, React 19, Vitest, openapi-typescript; Caddy.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 2.5: Invite team members and manage the team". Also: PRD FR-7, FR-9, FR-10, FR-11, NFR-5; ARCHITECTURE-SPINE AD-2, AD-3 (system_scope allow-list includes invite-accept), AD-4, AD-5, AD-15; EXPERIENCE.md screen table rows "Accept invite" and "Settings → Team", "Solo Owner" note, state patterns. Plan reviewed by Opus (high effort) on 2026-11-16: 14 gaps found, all fixed below.

## Global Constraints

- Invite link: works once, expires after 7 days (FR-9). SevaDesk sends no email. The Owner copies the link.
- `invites` is a tenant table owned by `accounts`; it stores only a hash of the token. It must pass `tests/integration/test_tenant_schema.py` (UNIQUE `(business_id, id)`).
- Memberships are deactivated, never deleted (AD-4). Deactivation deletes that User's sessions at once (AD-5).
- Only `accounts` computes "active Technicians" (AR-7): one function, `active_technician_ids`.
- Team page copy, verbatim: `Just you for now` when the Owner is the only active Technician (UX-DR29).
- Used / expired / unknown invite: one message, verbatim `This invite is no longer valid.` Nothing is created.
- Every Owner action checks the Role FIRST (before any lookup by id). Cross-Business ids answer 404 (FR-11).
- Every new API route is listed in `tests/integration/test_tenant_isolation.py` (`ISOLATION_CHECKS` or `NO_TENANT_DATA`), or CI fails.
- The raw invite token never appears in an API path, a log line, or a trace span name.
- New `system_scope` caller name: `"invite_accept"` (added to `SYSTEM_SCOPE_CALLERS`).
- Password rules for accept = sign-up rules: 12–128 characters, messages `Use at least 12 characters.` / `Use at most 128 characters.`
- Token fields in request bodies: `max_length=64` (a real token is 43 characters).
- Other modules import `accounts` only through `service.py` / `dependencies.py` (import-linter). `service.py` never imports `team.py` (no import cycle).
- `frontend/openapi.json` and `src/api/schema.d.ts` must match the backend (CI `git diff --exit-code`). Regenerate in WSL only (Windows may write CRLF line ends).
- Branch: `story/2-5-invite-team-members`. PR body ends with `Closes #12`.

## Decisions made in this plan (User approved 2026-11-16)

- **Owner Role cannot be given or removed** through invites or the Team page (MVP: one Owner). The DB check on `invites.roles` allows only `staff` / `technician`. The Owner can turn their own Technician Role on and off.
- **An Owner cannot deactivate themself** (else nobody can manage the Business).
- **Reactivate is allowed** (`is_active: true`). Reason: one User has one membership for life (unique `user_id`), so a wrong deactivation would lock that email out forever. Same code path, about 2 lines.
- **Email already has an account** → accept answers 409 `An account with this email already exists.` and the invite stays unused. No check at invite time. (Reason corrected after the review: such a check would not hide much, because the Owner can open their own link and see the 409, and sign-up already shows the same thing. The real limit is that nobody verifies an email address yet; that is a later story.)
- **No rate limit on preview/accept:** the token is 32 random bytes, so guessing is impossible; the length cap stops huge inputs.
- **No list of pending invites** and no "cancel invite". Not in the story. Note for later.

## Review Focus

1. **Two taps on "Join" at the same moment** (or two people with one link): only one account is made; the second waits for the row lock and gets `This invite is no longer valid.` → Task 4 lock test (deterministic).
2. **Invited email already has an account** (any Business): 409, no User, no membership, invite still unused. → Task 4 test.
3. **Owner breaks their own access**: removes own Owner Role, gives Owner to someone, or deactivates self → 422, nothing changes. → Task 5 tests.
4. **Owner of Business A edits or lists Business B's members** → 404 / no B data (FR-11). → Task 5 isolation checks in `test_tenant_isolation.py`.
5. **Deactivated member is still logged in on another phone** → their next request is 401, and log-in fails. Their request that is already running gets 401 or finishes, never a 500. → Task 5 tests.

Notes for later stories (do not build now): pending-invite list / cancel. In `conftest.py`, `set_owner_roles` changes ALL memberships of a Business, and `membership_of` / `membership_is_active` use `.one()`: **never use them in a test after `invite_member`** — use the ids `invite_member` and `GET /api/v1/team` return.

---

### Task 0: Start the story (no code)

- [ ] Show the Story Map (CLAUDE.md §2) and get the User's prediction.
- [ ] `git switch -c story/2-5-invite-team-members` from an up-to-date `main`. Add label `in-progress` to issue #12.
- [ ] `sprint-status.yaml`: `2-5-invite-team-members-and-manage-the-team: in-progress`.
- [ ] Check Docker Desktop runs. Backend tests run in WSL: `wsl --cd "<repo>/backend" uv run pytest …`.

---

### Task 1: The `invites` table (CORE) — checkpoint after

**Files:**
- Modify: `backend/app/modules/accounts/models.py` (add `Invite`)
- Create: `backend/migrations/versions/0004_invites.py`
- Modify: `backend/tests/integration/test_migrations.py` (expected table set)
- Test: `backend/tests/integration/test_invites_table.py`

**Interfaces:**
- Produces: `class Invite(TenantModel)`, table `invites`: `id` (uuid7 PK), `email: str` (cleaned), `roles: list[str]` (`ARRAY(Text)`), `token_hash: str` (unique), `expires_at: datetime` (tz), `used_at: datetime | None` (tz, nullable), `created_at` (server default now). `__table_args__`: `UniqueConstraint("business_id", "id")`, `CheckConstraint("cardinality(roles) > 0 AND roles <@ ARRAY['staff','technician']::text[]", name="roles_valid")`.
- Migration constraint names (written by hand, as in 0003): `pk_invites`, `fk_invites_business_id_businesses`, `uq_invites_token_hash`, `uq_invites_business_id_id`, `ck_invites_roles_valid`. `revision = "0004"`, `down_revision = "0003"`. `downgrade` drops the table.

- [ ] **Step 1: Write the failing tests**

`test_migrations.py`: the set after `upgrade head` adds `"invites"`.

`test_invites_table.py` (`pytestmark = pytest.mark.isolation`), using a helper that inserts an invite row with `Session(get_engine())` inside `tenant_scope(business_id)` for a Business from `sign_up_owner`:
- `test_invite_with_owner_role_is_refused` — roles `["owner"]` → `IntegrityError` (the DB itself forbids inviting a second Owner).
- `test_invite_with_no_roles_is_refused` — roles `[]` → `IntegrityError`.
- `test_staff_and_technician_invite_is_stored` — roles `["staff", "technician"]` saves; `used_at is None`.
- `test_real_schema_follows_the_tenant_rules` (existing, in `test_tenant_schema.py`) must stay green with the new table.

- [ ] **Step 2: Run and see them fail** — `uv run pytest tests/integration/test_invites_table.py tests/integration/test_migrations.py -v` → FAIL (no table `invites`).
- [ ] **Step 3: Add the model and migration 0004.**
- [ ] **Step 4: Run** the two files plus `tests/integration/test_tenant_schema.py` → PASS.
- [ ] **Step 5: Commit** `feat(accounts): invites table stores only a token hash (story 2.5)`.

---

### Task 2: One password rule and one "create a User" path (STANDARD)

Sign-up and invite-accept must use the same password rule and the same "make a User + membership" steps. Today the rule lives in `business/schemas.py`, which `accounts` may not import. Move it down to `accounts`.

**Files:**
- Modify: `backend/app/modules/accounts/schemas.py` (add `MIN_PASSWORD = 12`, `check_new_password`)
- Modify: `backend/app/modules/accounts/service.py` (re-export `check_new_password`; extract `_create_user`; rename `_hash_token` → `hash_token`)
- Modify: `backend/app/modules/business/schemas.py` (`check_password` calls `accounts_service.check_new_password`; delete its own `MIN_PASSWORD`/`MAX_PASSWORD`)
- Test: `backend/tests/unit/test_passwords.py` (add cases)

**Interfaces:**
- Produces:
  - `check_new_password(value: str) -> str` in `accounts/schemas.py`: raises `PydanticCustomError("password_short", "Use at least 12 characters.")` / `("password_long", "Use at most 128 characters.")`; returns the value unchanged (not stripped). Re-exported in `service.py` as `check_new_password as check_new_password`.
  - `hash_token(token: str) -> str` (public now: `team.py` hashes invite tokens with it). Every old `_hash_token` call updated.
  - `_create_user(session, email: str, password: str, roles: set[Role], caller: str) -> Membership` in `service.py`: the body of today's `create_owner` (email check in `system_scope(caller)`, hash, add User, `IntegrityError` → `EmailTaken`, add membership with `sorted(roles)`). Must run inside a `tenant_scope`. `create_owner` becomes a 2-line call with `caller="signup"`.

- [ ] **Step 1: Write the failing tests** in `test_passwords.py`: `check_new_password("a" * 11)` raises with type `password_short`; `"a" * 129` raises `password_long`; `"  twelve chars"` (14 chars with spaces) returns itself unchanged.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_passwords.py -v` → FAIL (import error).
- [ ] **Step 3: Implement** the three changes above. No behaviour change for sign-up.
- [ ] **Step 4: Run** `tests/unit/test_passwords.py tests/integration/test_signup.py tests/integration/test_login.py tests/integration/test_sessions.py` and `uv run lint-imports` → all PASS.
- [ ] **Step 5: Commit** `refactor(accounts): one password rule and one create-user path for sign-up and invites (story 2.5)`.

---

### Task 3: Owner creates an invite link (CORE) — checkpoint after

**Files:**
- Modify: `backend/app/modules/accounts/schemas.py` (`InviteRequest`, `InviteCreated`)
- Modify: `backend/app/modules/accounts/repository.py` (`InviteRepository`)
- Create: `backend/app/modules/accounts/team.py`
- Create: `backend/app/modules/accounts/team_router.py`
- Modify: `backend/app/main.py` (include `team_router.router`)
- Modify: `backend/pyproject.toml` (front-door contract: add `app.modules.accounts.team` and `app.modules.accounts.team_router` to `forbidden_modules`)
- Modify: `backend/tests/integration/test_tenant_isolation.py` (`check_create_invite`)
- Test: `backend/tests/integration/test_team_invites.py`

**Interfaces:**
- Consumes: `hash_token`, `require_roles`, `Permission.MANAGE_SETUP` (Task 2 / story 2.4).
- Produces:
  - `TEAM_ROLES: frozenset[Role] = frozenset({Role.STAFF, Role.TECHNICIAN})` in `schemas.py` — the Roles an Owner may give.
  - `InviteRequest(BaseModel)`: `email: str` (validator: `clean_email`), `roles: list[Role]` (validator: empty → `PydanticCustomError("roles_empty", "Choose at least one Role.")`; any Role not in `TEAM_ROLES` → `("roles_not_allowed", "Choose Staff, Technician, or both.")`; returns `sorted(set(value))`).
  - `InviteCreated(BaseModel)`: `token: str`, `expires_at: datetime`.
  - `InviteRepository(TenantRepository[Invite])` with `model = Invite` (the base `add` sets `business_id`).
  - `INVITE_LIFETIME = timedelta(days=7)` in `team.py`.
  - `create_invite(session, actor: Actor, request: InviteRequest) -> InviteCreated` in `team.py`: `require_roles` first; `token = secrets.token_urlsafe(32)`; store `hash_token(token)` and `expires_at = now(UTC) + INVITE_LIFETIME`; return the raw token once.
  - `team_router.router = APIRouter(prefix="/api/v1")`; `POST /team/invites`, `status_code=201`, `operation_id="create_invite"`, `responses={401, 403, 422: ErrorEnvelope}`, takes `ActorDep` + `SessionDep`.
  - `check_create_invite(owners: TwoOwners)` in `test_tenant_isolation.py`: A creates an invite; reading `invites` directly, the row has A's `business_id`; B's `GET /api/v1/me` still works and B has no new invite row.

- [ ] **Step 1: Write the failing tests** (`test_team_invites.py`). Before each CORE test, tell the User its behaviour in one line.
  - `test_owner_gets_a_token_once_and_db_keeps_only_its_hash` — 201; body has `token` and `expires_at` ≈ now + 7 days (±1 min); the DB row's `token_hash == sha256(token)` and no column holds the raw token; row `email` is cleaned (send `"  New@Shop.IN "`, expect `"new@shop.in"`).
  - `test_forbidden_roles_cannot_create_an_invite` — parametrize over `["staff"]` and `["technician"]` (`set_owner_roles`) → 403 `forbidden`, no row in `invites`. Send a VALID body: FastAPI checks the body before the service runs, so a bad body would give 422, not 403.
  - `test_owner_role_cannot_be_invited` — roles `["owner"]` → 422, `fields[0] == {"field": "roles", "message": "Choose Staff, Technician, or both."}`.
  - `test_empty_roles_are_refused` — roles `[]` → 422 field `roles` `Choose at least one Role.`
  - `test_bad_email_is_refused` — `"not-an-email"` → 422 field `email` (message from `clean_email`).
  - Add `("POST", "/api/v1/team/invites"): check_create_invite` to `ISOLATION_CHECKS`.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_team_invites.py tests/integration/test_tenant_isolation.py -v` → FAIL (404 route).
- [ ] **Step 3: Implement** the schemas, repository, `team.py`, `team_router.py`, register the router in `main.py`, and extend the import-linter contract.
- [ ] **Step 4: Run** the two files → PASS. Run `uv run lint-imports` → PASS.
- [ ] **Step 5: Commit** `feat(accounts): Owner creates a single-use 7-day invite link (story 2.5)`.

---

### Task 4: Open and accept an invite (CORE) — checkpoint after

**Files:**
- Modify: `backend/app/core/tenancy.py` (`SYSTEM_SCOPE_CALLERS` adds `"invite_accept"`)
- Modify: `backend/tests/unit/test_tenancy.py` (allow-list test)
- Modify: `backend/app/modules/accounts/schemas.py` (`InviteTokenRequest`, `InvitePreview`, `AcceptInviteRequest`)
- Modify: `backend/app/modules/accounts/repository.py` (`InviteRepository.find_by_token_hash`)
- Modify: `backend/app/modules/accounts/service.py` (`InviteInvalid`, `_valid_invite`, `preview_invite`, `accept_invite`)
- Modify: `backend/app/modules/accounts/router.py` (two routes; they log in, like `/login`, so they live next to it and reuse `_me`)
- Modify: `backend/tests/integration/conftest.py` (`invite_member` fixture, `Member` dataclass)
- Modify: `backend/tests/integration/test_tenant_isolation.py` (`NO_TENANT_DATA` rows)
- Test: `backend/tests/integration/test_invite_accept.py`

**Interfaces:**
- Consumes: `_create_user`, `hash_token`, `start_session`, `_actor` (service.py); `create_invite` route (Task 3).
- Produces:
  - `InviteTokenRequest`: `token: str = Field(max_length=64)`. `InvitePreview`: `email: str`. `AcceptInviteRequest`: `token: str = Field(max_length=64)`, `password: str` (validator: `check_new_password`).
  - `InviteRepository.find_by_token_hash(token_hash: str, *, lock: bool) -> Invite | None`: `require_system_scope()`; no tenant filter (we look it up to LEARN the Business); adds `.with_for_update()` only when `lock` is true, so a second accept waits until the first one commits.
  - `class InviteInvalid(AppError)`: code `"invite_invalid"`, message `"This invite is no longer valid."`, status 404. One answer for unknown, used, and expired (no leak).
  - `_valid_invite(session, token: str, *, lock: bool) -> Invite` (private): lookup inside `system_scope("invite_accept")`; `None`, `used_at is not None`, or `now >= expires_at` → `InviteInvalid`.
  - `preview_invite(session, token: str) -> InvitePreview` — `lock=False` (a read never takes a lock).
  - `accept_invite(session, token: str, password: str) -> tuple[str, Actor]`: `_valid_invite(lock=True)`; inside `tenant_scope(invite.business_id)`: `_create_user(..., roles={Role(r) for r in invite.roles}, caller="invite_accept")`; set `invite.used_at = now` AFTER the user exists (so an `EmailTaken` rollback leaves the invite unused); `start_session`. No commit (AD-15).
  - Routes in `router.py`: `POST /invites/preview` (`operation_id="preview_invite"`, body `InviteTokenRequest`, returns `InvitePreview`, responses 404/422) and `POST /invites/accept` (`operation_id="accept_invite"`, body `AcceptInviteRequest`, ends `old_token` session first (D11), sets cookie, returns `MeResponse` via `_me`, responses 404/409/422).
  - `NO_TENANT_DATA` rows: `("POST", "/api/v1/invites/preview")` and `("POST", "/api/v1/invites/accept")`, both with the reason `"no session; the Business comes from the secret token's own invite row"`.
  - conftest: `@dataclass class Member: client: TestClient; email: str; membership_id: uuid.UUID`. Fixture `invite_member(make_client)` → function `(owner: TestClient, roles: list[str]) -> Member`: owner POSTs `/api/v1/team/invites` with a fresh `uuid4().hex@example.com`, a new client accepts with `GOOD_PASSWORD`, asserts 200; `membership_id` is read directly from the DB by the new user's email.

- [ ] **Step 1: Write the failing tests.**
  - `test_tenancy.py`: `system_scope("invite_accept")` is allowed.
  - `test_invite_accept.py` (helper `new_invite(owner, roles) -> str` returns the token):
    - `test_preview_shows_the_invited_email` — 200 `{"email": …}`.
    - `test_accept_makes_a_member_with_the_invited_roles_and_logs_in` — 200 body `{"roles": ["staff", "technician"], "permissions": [...]}` (`permissions_for` of those Roles); the same client's `GET /api/v1/me` is 200; the new membership has `business_id` == the Owner's Business; `invites.used_at` is set.
    - `test_used_invite_is_no_longer_valid` — accept, then preview and accept again with a second client → both 404 `{"error": {"code": "invite_invalid", "message": "This invite is no longer valid."}}`; still exactly one new User.
    - `test_expired_invite_is_no_longer_valid` — set `expires_at = now - 1 s` by a direct DB update → preview 404 and accept 404; no User with that email.
    - `test_unknown_token_is_no_longer_valid` — random token → same 404 body.
    - `test_too_long_token_is_a_field_error` — 65-character token → 422.
    - `test_email_that_already_has_an_account_gets_409` (Review Focus 2) — invite the email of another Business's Owner → 409 `email_taken`; `used_at is None`; no new membership.
    - `test_second_accept_waits_for_the_lock_and_then_fails` (Review Focus 1, deterministic): in a separate connection, `SELECT … FROM invites WHERE id = … FOR UPDATE` and keep that transaction open; start the accept in a thread (`ThreadPoolExecutor`); after 0.5 s assert the future is NOT done (it waits on the lock); then `UPDATE invites SET used_at = now()` and commit; assert the thread's answer is 404 `invite_invalid` (not 409) and no User with that email exists. Without `with_for_update()` this test fails (accept would not wait).
    - `test_short_password_is_a_field_error` — 422 field `password` `Use at least 12 characters.`; invite still unused.
  - Add the two `NO_TENANT_DATA` rows.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_invite_accept.py tests/unit/test_tenancy.py tests/integration/test_tenant_isolation.py -v` → FAIL.
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run** the three files → PASS. Then the whole backend suite → PASS.
- [ ] **Step 5: Commit** `feat(accounts): accept an invite link, set a password, and log in (story 2.5)`.

---

### Task 5: Team list, change Roles, deactivate (CORE) — checkpoint after

**Files:**
- Modify: `backend/app/modules/accounts/schemas.py` (`Member`, `TeamResponse`, `MemberUpdate`)
- Modify: `backend/app/modules/accounts/repository.py` (`MembershipRepository.list_with_emails`, `.active_technician_ids`; `SessionRepository.delete_for_user`, `.touch`)
- Modify: `backend/app/modules/accounts/service.py` (`active_technician_ids`; `resolve_session` uses `touch`)
- Modify: `backend/app/modules/accounts/team.py` (`list_team`, `update_member`, `TeamRuleBroken`)
- Modify: `backend/app/modules/accounts/team_router.py` (two routes)
- Modify: `backend/tests/integration/test_tenant_isolation.py` (`check_list_team`, `check_update_member`)
- Modify: `backend/tests/integration/test_role_access.py`, `backend/tests/integration/probe_app.py` (remove the stale "no real endpoint needs a Role yet" comments)
- Test: `backend/tests/integration/test_team_manage.py`, `backend/tests/integration/test_sessions.py` (touch case)

**Interfaces:**
- Consumes: `invite_member` fixture and `Member` dataclass (Task 4).
- Produces:
  - `Member` (schema): `membership_id: UUID`, `email: str`, `roles: list[Role]`, `is_active: bool`, `is_you: bool`. `TeamResponse`: `members: list[Member]` (oldest first), `just_you: bool`. `MemberUpdate`: `roles: list[Role] | None = None` (validator, `mode="after"`, skips `None`: empty → `roles_empty` `Choose at least one Role.`; returns sorted, deduped), `is_active: bool | None = None`; a `model_validator` refuses a body where both are `None` (`{}` or all nulls) with `PydanticCustomError("nothing_to_change", "Nothing to change.")`.
  - `MembershipRepository.list_with_emails() -> list[tuple[Membership, str]]`: starts from `self._select()` (tenant filter), joins `User`, orders by `Membership.created_at`.
  - `MembershipRepository.active_technician_ids() -> list[uuid.UUID]`: from `self._select()`, `is_active` and `roles` contains `"technician"`.
  - `SessionRepository.delete_for_user(user_id: uuid.UUID) -> None`.
  - `SessionRepository.touch(session_id: uuid.UUID, now: datetime) -> None`: a bulk `update(UserSession).where(UserSession.id == session_id).values(last_seen_at=now)`. `resolve_session` calls it instead of `row.last_seen_at = now`. Why: if the Owner deletes this session while the member's request runs, a bulk update just changes 0 rows; the old ORM change would raise `StaleDataError` (a 500).
  - `active_technician_ids(session) -> list[uuid.UUID]` in `service.py` — the ONE place that says who counts as an active Technician (AR-7). Bookings will call it later.
  - `TeamRuleBroken(field: str, message: str)` (AppError): status 422, code `"validation_error"`, message `"Some fields need fixing."`, `fields=[FieldError(field, message)]`.
  - `list_team(session, actor) -> TeamResponse`: `require_roles` first; `just_you = active_technician_ids(session) == [actor.membership_id]`.
  - `update_member(session, actor, membership_id: UUID, change: MemberUpdate) -> TeamResponse`, in this order: `require_roles`; `get_or_raise` (404 for other Business); if `change.roles` and `(Role.OWNER in new) != ("owner" in row.roles)` → `TeamRuleBroken("roles", "The Owner Role can't be changed.")`; if `change.is_active is False` and `row.id == actor.membership_id` → `TeamRuleBroken("is_active", "You can't deactivate yourself.")`; apply; when deactivating, `delete_for_user(row.user_id)`; return `list_team(...)`. Never deletes a membership.
  - Routes: `GET /team` (`operation_id="list_team"`, responses 401/403), `PATCH /team/members/{membership_id}` (`operation_id="update_member"`, responses 401/403/404/422).
  - `check_list_team(owners)`: A's `GET /team` holds only A's emails (none of B's). `check_update_member(owners)`: A PATCHes B's Owner membership `{"roles": ["owner"]}` → 404 `not_found`; B's roles are unchanged.

- [ ] **Step 1: Write the failing tests** (`test_team_manage.py`; ids come from `Member.membership_id` and `GET /api/v1/team`; never `membership_of` after an invite).
  - `test_solo_owner_sees_just_you` — new Owner → `just_you is True`, one member, `is_you`, roles `["owner", "technician"]`.
  - `test_a_second_technician_ends_just_you` — `invite_member(owner, ["technician"])` → `just_you is False`, two members.
  - `test_owner_turns_off_own_technician_role` (FR-7) — PATCH own roles `["owner"]` → 200; `active_technician_ids` (called in a `tenant_scope` with a direct `Session`) no longer holds the Owner's id; `just_you is False`.
  - `test_owner_changes_a_members_roles_and_it_applies_at_once` — member `["staff"]` → PATCH `["technician"]` → `member.client` `GET /api/v1/me` shows `roles == ["technician"]`.
  - `test_deactivated_member_is_logged_out_everywhere` (Review Focus 5) — log a second client in with `member.email` + `GOOD_PASSWORD`; PATCH `{"is_active": false}` → both clients' `/me` are 401; `/login` again is 401; the membership row still exists with `is_active False`; zero `sessions` rows for that user.
  - `test_reactivated_member_can_log_in_again` — PATCH `true` after `false` → `/login` with `member.email` is 200.
  - `test_owner_rules_cannot_be_broken` (Review Focus 3) — each answers 422 with the field and message above and changes nothing: own roles `["technician"]`; a member's roles `["owner", "staff"]`; own `{"is_active": false}`.
  - `test_empty_change_is_refused` — PATCH `{}` → 422, message `Nothing to change.` in `fields`.
  - `test_forbidden_roles_cannot_see_or_change_the_team` — parametrize over `["staff"]` and `["technician"]` (members made with `invite_member`): `GET /team` → 403; PATCH the Owner's id with a VALID body `{"roles": ["owner"]}` → 403.
  - `test_sessions.py`: `test_touch_on_a_deleted_session_does_not_fail` — `SessionRepository.touch(uuid.uuid7(), now)` on a missing id raises nothing.
  - Add `("GET", "/api/v1/team"): check_list_team` and `("PATCH", "/api/v1/team/members/{membership_id}"): check_update_member` to `ISOLATION_CHECKS` (Review Focus 4).
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_team_manage.py tests/integration/test_tenant_isolation.py tests/integration/test_sessions.py -v` → FAIL.
- [ ] **Step 3: Implement** as in Interfaces. Remove the stale comments in `test_role_access.py` and `probe_app.py`.
- [ ] **Step 4: Run** the whole backend suite with coverage (`uv run pytest --cov`) and `uv run pytest -m isolation` → PASS, coverage ≥ 80 %. `uv run lint-imports`, `uv run ruff check`, `uv run ruff format --check` → clean.
- [ ] **Step 5: Commit** `feat(accounts): Team list, change Roles, deactivate members (story 2.5)`.

---

### Task 6: API types, permissions context, Team link (STANDARD)

**Files:**
- Modify: `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (regenerate in WSL, the exact CI command: `cd backend && uv run python -m app.export_openapi ../frontend/openapi.json && cd ../frontend && npm run gen:api`)
- Create: `frontend/src/lib/permissions.tsx`
- Modify: `frontend/src/app/app/layout.tsx` (wrap the page in `PermissionsProvider`)
- Modify: `frontend/src/lib/access.ts` (+ `access.test.ts`)
- Modify: `frontend/src/lib/nav.ts` (+ `nav.test.ts`), `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/SettingsLinks.tsx` (+ `SettingsLinks.test.tsx`)
- Modify: `frontend/src/app/app/more/page.tsx` (render `<SettingsLinks />` above `LogoutButton`; remove the "settings links come in later stories" comment)

**Interfaces:**
- Produces:
  - `PermissionsProvider({ permissions, children })` and `usePermissions(): Permission[]` (React context; default `[]`). The layout already holds the list (story 2.4); this shares it with pages, so a page can hide its own buttons.
  - `PAGE_RULES` gets `{ href: "/app/settings/team", needs: "manage_setup" }`.
  - `NavItem` gets an optional `alsoActiveUnder?: string[]`; the More item sets `["/app/settings"]`. `AppShell` marks an item current when `isUnder(pathname, href)` or `isUnder` matches any `alsoActiveUnder` entry. So More is highlighted on `/app/settings/team`.
  - `SettingsLinks()` (client component): a "Team" link to `/app/settings/team`, shown only when `canOpen("/app/settings/team", usePermissions())`.

- [ ] **Step 1: Write the failing tests**: `access.test.ts` — `canOpen("/app/settings/team", ["see_dashboard"])` is false, with `["manage_setup"]` is true. `SettingsLinks.test.tsx` — inside a provider with `["manage_setup"]` there is a link named "Team" to `/app/settings/team`; with `["see_own_bookings"]` there is none. `AppShell.test.tsx` — on `/app/settings/team` the More link has `aria-current="page"`.
- [ ] **Step 2: Run** `npm test` → FAIL.
- [ ] **Step 3: Implement**, and regenerate the API files in WSL.
- [ ] **Step 4: Run** `npm test`, `npm run lint`, `npm run typecheck` → PASS; `git diff --stat frontend/openapi.json` shows the new routes; `git diff` shows no CRLF changes.
- [ ] **Step 5: Commit** `feat(app): share permissions in a context; Team link on More for Owners (story 2.5)`.

---

### Task 7: Settings → Team page (STANDARD)

**Files:**
- Create: `frontend/src/app/app/settings/team/page.tsx` (metadata title `Team · SevaDesk`, renders `<TeamSettings />`)
- Create: `frontend/src/components/InviteForm.tsx` (+ test)
- Create: `frontend/src/components/TeamSettings.tsx` (+ test)

**Interfaces:**
- Consumes: `create_invite`, `list_team`, `update_member` (Tasks 3, 5) through `api`.
- Produces:
  - `InviteForm()`: email field; a `<fieldset>` with `<legend>Roles</legend>` holding two native checkboxes "Staff" and "Technician"; the `roles` error sits under the fieldset and the fieldset points at it with `aria-describedby`. Button `Create invite link` (`Creating…` while busy). On success it shows, in an `aria-live="polite"` region, the link `${window.location.origin}/invite/${token}` in a read-only input labelled "Invite link" (it selects its text on focus, so a long-press copy works when the clipboard API fails), the hint `Works once. Expires in 7 days.`, and a `Copy link` button (`navigator.clipboard.writeText`; then the button says `Copied`). Backend field errors (`email`, `roles`) show under their field, like `SignupForm`.
  - `TeamSettings()`: loads `GET /api/v1/team`. While loading: skeleton rows (`aria-busy`, like the layout's placeholder). Load failure: `Could not load. Please try again.` + `Try again` button (same pattern as `app/layout.tsx`). Shows `Just you for now` when `just_you`. One row per member: email, `(you)` when `is_you`, `Owner` text when the member has that Role, checkboxes with unique labels `Staff for {email}` and `Technician for {email}` (a change sends PATCH with the new full Role list, keeping `owner` if present), and for others a `Deactivate` button (asks `window.confirm("Deactivate {email}? They are logged out at once.")`) or, when inactive, the text `Deactivated` and a `Reactivate` button. Each PATCH answer replaces the list. A 422 message shows in a `role="alert"` line. Renders `<InviteForm />` above the list.

- [ ] **Step 1: Write the failing tests** (mock `@/api/client` like `LoginForm.test.tsx`):
  - InviteForm: sends `{ email, roles: ["technician"] }` to `/api/v1/team/invites`; then shows the link with the token and `Works once. Expires in 7 days.`; `Copy link` calls `navigator.clipboard.writeText` with the link; a `roles` field error shows and the `Roles` group (`getByRole("group", { name: "Roles" })`) is described by it.
  - TeamSettings: `just_you: true` shows `Just you for now`; `just_you: false` does not; ticking `Staff for tech@shop.in` sends PATCH `/api/v1/team/members/{membership_id}` with `{ roles: ["staff", "technician"] }`; the own row has no `Deactivate` button; `Deactivate` with `confirm` → true sends `{ is_active: false }`; a failed load shows `Could not load. Please try again.` and `Try again` asks again.
- [ ] **Step 2: Run** `npm test` → FAIL.
- [ ] **Step 3: Implement.** Reuse `Button`, `Input`, `Label`; native `<input type="checkbox">` inside a `<label>` (no new dependency); 44 px tap targets (`min-h-11`).
- [ ] **Step 4: Run** `npm test`, `npm run lint`, `npm run typecheck` → PASS.
- [ ] **Step 5: Commit** `feat(app): Settings → Team page with invite link, Roles, deactivate (story 2.5)`.

---

### Task 8: Accept invite page `/invite/{token}` + token-free traces (STANDARD)

> **Changed during execution (2026-11-16, User chose "Collector rule"):** the live trace check found that Caddy ALSO writes the full path into the span attribute `url.path`, which Caddy cannot turn off; and Caddy read `{token}` as an empty placeholder. So the Caddyfile change below was undone. Instead, `infra/compose/otel-collector.yaml` (CI copies it to the demo too) has a `transform/hide_invite_token` processor, first in the traces pipeline, that rewrites the span name and `url.path` to `/invite/:token`. Test: `backend/tests/unit/test_collector_hides_invite_tokens.py`. Live proof: a fresh token appeared 0 times in Tempo; both page traces were named `GET /invite/:token`.

**Files:**
- Create: `frontend/src/app/invite/[token]/page.tsx`
- Create: `frontend/src/components/AcceptInviteForm.tsx` (+ test)
- Modify: `infra/compose/Caddyfile`, `infra/demo/Caddyfile`
- Test: `backend/tests/unit/test_caddy_tracing.py`

**Interfaces:**
- Consumes: `preview_invite`, `accept_invite` (Task 4); `landingPath` from `@/lib/auth`.
- Produces:
  - Page (server component): `export const metadata: Metadata = { title: "Join · SevaDesk", referrer: "no-referrer" }` (the token never leaks in a Referer header). `export default async function InvitePage({ params }: PageProps<"/invite/[token]">) { const { token } = await params; … }` — in Next 16, `params` is a Promise. Renders `<AcceptInviteForm token={token} />`.
  - `AcceptInviteForm({ token }: { token: string })` (client): on mount POSTs `/api/v1/invites/preview` with `{ token }`. States: loading (placeholder block, like the layout); invalid (404 `invite_invalid`) → heading `This invite is no longer valid.`; failed (5xx or network) → `Could not load. Please try again.` + `Try again`; ready → heading `Join your team`, the text `You're joining as {email}.`, a password field (hint `At least 12 characters.`, `autoComplete="new-password"`), button `Join` (`Joining…`). On success `router.replace(landingPath(data.permissions))`. An `invite_invalid` answer to accept switches to the invalid state; a `password` field error shows under the field and focuses it; a 409 shows the backend message in `role="alert"` plus a `Log in` link to `/login`; anything else shows the backend message in `role="alert"`.
  - Both Caddyfiles: replace the single `tracing { span … }` with two matched blocks:
    ```
    @invite path /invite/*
    tracing @invite {
    	span "GET /invite/{token}"
    }
    @not_invite not path /invite/*
    tracing @not_invite {
    	span "{http.request.method} {http.request.uri.path}"
    }
    ```
    with a comment: the invite page path holds a secret token, so its span name is fixed.
  - `test_caddy_tracing.py`: for each Caddyfile, the text contains `span "GET /invite/{token}"` and every `span "{http.request.method} {http.request.uri.path}"` line sits inside a `@not_invite` block (read the file as text, like `test_demo_compose.py`).

- [ ] **Step 1: Write the failing tests**: AcceptInviteForm — preview 404 `invite_invalid` → shows `This invite is no longer valid.` and no password field; preview 500 → `Could not load. Please try again.`; preview OK → shows the email; submit sends `/api/v1/invites/accept` with `{ token, password }` and goes to `/app/calendar` for `permissions: ["see_own_bookings"]`; a password field error shows and focuses the field; a 409 shows `An account with this email already exists.` as an alert and a `Log in` link. Plus `test_caddy_tracing.py`.
- [ ] **Step 2: Run** `npm test` and `uv run pytest tests/unit/test_caddy_tracing.py` → FAIL.
- [ ] **Step 3: Implement.** Validate each Caddyfile: `docker run --rm -v "$PWD/infra/compose:/etc/caddy" caddy:2 caddy validate --config /etc/caddy/Caddyfile` (and the demo one with `DEMO_DOMAIN=example.com`).
- [ ] **Step 4: Run** `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`, the Caddy test → PASS.
- [ ] **Step 5: Manual check** (`run` skill or docker compose): Owner signs up → More → Team (More is highlighted) → invite a Technician → copy link → open it in a private window → set a password → lands on Calendar. Open the link again → `This invite is no longer valid.` Deactivate the member → the private window's next click goes to `/login`.
- [ ] **Step 6: Traces check (DoD "traces visible"):** open the accept request's trace in the trace viewer. The Caddy span is named `GET /invite/{token}`; no span name or attribute holds the raw token. If an attribute (e.g. `url.path`) still holds it, stop and tell the User before shipping.
- [ ] **Step 7: Commit** `feat(app): accept invite page sets a password and logs in; traces hide the token (story 2.5)`.

---

### Task 9: Finish the story (docs, gate, PR)

- [ ] `docs/learning/2-5.md` (what, why, concept: single-use tokens, row lock `SELECT … FOR UPDATE`, soft delete vs delete, React context, secrets in URLs; key files).
- [ ] `docs/learning/glossary.md`: invite token, single-use link, row lock, race condition, soft deactivation, React context, clipboard API, Referer header, span name.
- [ ] Understanding Gate (3 questions, one at a time, with reading first) and the hands-on task (memory: hands-on format).
- [ ] Opus review of the whole branch (superpowers:requesting-code-review), then PR with `Closes #12`; CI green; merge.
- [ ] After merge: `sprint-status.yaml` → `done`; close issue #12 and remove `in-progress`; update the resume-point memory; remind the User to `/clear`.
