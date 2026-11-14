# Story 2.2 — Log in, log out, and the app shell — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (CLAUDE.md: CORE-heavy story → inline with checkpoints). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A User logs in on `/login`, gets a server-side session in a safe cookie, sees the app shell with nav items for their Roles, and can log out; wrong passwords are rate-limited and cross-site writes are refused.

**Architecture:** `accounts` owns sessions: it makes a random token, stores only its SHA-256 hash in `sessions`, and turns a cookie back into an `Actor`. `core` gets three small, module-free tools: the session cookie helpers, a Redis attempt limiter with a client-IP reader, and an `Origin` guard middleware. Sign-up (in `business`) now also starts a session. The frontend gets `/login`, a 401 → `/login` redirect in the API client, and an `/app` layout with a bottom tab bar (mobile) and a left sidebar (≥ 1024px).

**Tech Stack:** FastAPI, SQLAlchemy 2.1, pwdlib[argon2] 0.3.1, redis-py 7.4.1 (Valkey), Postgres 18 + Valkey 9 (Testcontainers), Next.js 16, Tailwind 4, shadcn/ui, lucide-react, Vitest.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → Story 2.2 (lines 466–499); rules AD-2, AD-3, AD-4, AD-5, AD-6, AD-14, AD-15 in `_bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md`; routes and nav in `_bmad-output/planning-artifacts/ux-designs/ux-seva-desk-2026-11-01/EXPERIENCE.md` (Information Architecture).

**Plan review:** Opus critique on 2026-11-14 (18 findings, all applied by user decision).

## Decisions (confirmed 2026-11-14)

| # | Topic | Decision | Why |
|---|---|---|---|
| D1 | Inactivity timeout | `SESSION_IDLE_TIMEOUT = 7 days` | Owners use a phone all day; a daily log-in is annoying. |
| D2 | Touch interval | update `last_seen_at` only if older than `5 minutes` | No DB write on every request. |
| D3 | Rate limits | 5 log-in attempts per account, 20 per IP; then 429 for `900 s`. **Count first**: every attempt adds 1 before the password check. | Parallel requests cannot all slip past a count of 0. |
| D4 | `Origin` check | lowercase `Origin` host:port must equal lowercase `Host`; a missing `Host` or `Origin` is refused | No new env var. Caddy and the ALB keep `Host` (no proxy may rewrite it). |
| D5 | Client IP | rightmost `X-Forwarded-For` value, checked with `ipaddress`; invalid → socket address. IPv6 is keyed by its `/64` network. | Caddy replaces the header; the ALB appends the real IP. One IPv6 user owns a whole /64. |
| D6 | Password normalisation | NFKC before hash and verify | NIST SP 800-63B. Only test accounts exist; demo accounts with non-ASCII passwords may need a reset. |
| D7 | NUL in email | refused as "Enter a valid email address." | Postgres cannot store `\x00`; today it gives a 500. |
| D8 | Email rules in one place | `accounts/emails.py`, re-exported by `accounts.service` | Sign-up and log-in clean emails the same way. |
| D9 | Cookie name | `__Host-sevadesk_session` | The `__Host-` prefix makes the browser refuse a cookie set by another `*.sslip.io` site. |
| D10 | Session → membership lookup | a quiet `session_lookup()` guard in `core.tenancy` (AD-3 source (a)), no INFO line | `system_scope` writes an audit line; one per request would bury the rare real ones. |
| D11 | Old session on log-in / sign-up | if a cookie is present, end that session first | A shared phone does not keep the old person's session alive. |

## Global Constraints

- Branch `story/2-2-login-logout-app-shell`. GitHub issue #9. PR flow: push → `gh pr create` (`Closes #9`) → green → `gh pr merge --merge --delete-branch`. Sprint-status `done` is committed inside the PR.
- **Backend commands run in WSL.** `BE` below means `wsl -e bash -lc 'cd "/mnt/c/Books/DataSense Community/Seva Desk/backend" && <command>'`. Windows `uv` cannot use the WSL `.venv`.
- Cookie: `__Host-sevadesk_session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain`, `Max-Age` 30 days. The cookie is set once at log-in and never refreshed, so 30 days is also an absolute limit; the server idle timeout (D1) is the other limit.
- Token: `secrets.token_urlsafe(32)`. The DB keeps only `hashlib.sha256(token).hexdigest()` in `sessions.token_hash`. No JWT.
- Routes under `/api/v1`: `POST /login` (`operation_id="log_in"`, 200), `POST /logout` (`log_out`, 204), `GET /me` (`get_me`, 200). Each route lists its error responses with `ErrorEnvelope` (as `business/router.py:16` does), so the generated types know the shape.
- Error codes: `invalid_credentials` 401 "Wrong email or password.", `not_authenticated` 401 "Please log in.", `too_many_attempts` 429 "Too many tries. Please wait 15 minutes and try again." (+ `Retry-After`), `origin_refused` 403 "This request was refused.", `dependency_unavailable` 503 "Log-in is not available right now. Please try again.".
- Unknown email and wrong password return the **same** 401 body, and both run `verify_password` exactly once.
- Log-in password: 1–128 characters (more → 422 "Use at most 128 characters.", no hashing).
- Redis keys: `login_fail:acct:<sha256 of cleaned email>` and `login_fail:ip:<ip or /64>`. No raw email in Redis.
- `system_scope` callers grow from `{"signup"}` to `{"signup", "login"}`. The session lookup uses `session_lookup()` (D10).
- AD-2 note: `accounts/dependencies.py` is the **HTTP front door** of `accounts` (FastAPI dependencies for routers). Other modules may import `accounts.service` and `accounts.dependencies` only; import-linter also forbids `accounts.router`.
- Services never commit (AD-15). `core` imports no module.
- Frontend routes (EXPERIENCE.md): `/login`, `/app` (Dashboard), `/app/inbox`, `/app/calendar`, `/app/more`. Landing: Owner or Staff → `/app`; Technician-only → `/app/calendar`. Nav: Owner/Staff = Dashboard · Inbox · Calendar · More; Technician-only = Calendar · More. Sidebar from `lg` (1024px). Solid surfaces only. Tap targets ≥ 44px.
- Backend owns validation; forms show field errors next to the field and focus the first one (UX-DR33).
- No new dependencies.

## Review Focus

1. Redis is down during log-in → 503 envelope, not 500, and no session row. Test in Task 4.
2. A client sends `X-Forwarded-For: 1.2.3.4, <real ip>` → the rightmost value is used. Test in Task 3.
3. `OWNER@Shop.com` vs `owner@shop.com` → both log in, and both count against **one** account limit. Test in Task 4.
4. Ten wrong log-ins sent at the same moment → at most 5 get to check a password. Test in Task 4.
5. A cross-site `POST /api/v1/signup` → 403, and no Business is created. Test in Task 5.

Deferred (note in the PR):
- A sweep that deletes old `sessions` rows; a server-side absolute session lifetime.
- **AWS staging cannot log in yet:** the ALB listener is plain HTTP (`infra/terraform/staging/app.tf:105-113`), and browsers drop `Secure` cookies there. Staging needs TLS on the ALB. Add this line to `infra/terraform/README.md` in Task 8.
- Safari refuses `Secure` cookies on `http://localhost`; use Chrome or Firefox locally.
- Story 2.3: `get_actor` is a sync dependency, so it runs in a copied context; a `tenant_scope` set inside it does not reach the endpoint. Set tenant scope in the service from `actor.business_id`, or use an async dependency.
- 401/403/429 in the OpenAPI `responses` of routes other than `/login` and `/me`.

---

### Task 0: Learning steps before coding [no code]

- [x] **Step 1:** User confirmed D1–D8; review fixes D9–D11 added (2026-11-14).
- [ ] **Step 2:** Story Map + one predict question (CLAUDE.md §2).
- [ ] **Step 3:** Create branch `story/2-2-login-logout-app-shell`; add label `in-progress` to issue #9.
- [ ] **Rule for all tasks:** before each CORE test, tell the user in one line what behaviour it checks.

### Task 1: One email rule and NFKC passwords [CORE]

**Files:**
- Create: `backend/app/modules/accounts/emails.py`, `backend/tests/unit/test_emails.py`, `backend/tests/unit/test_passwords.py`
- Modify: `backend/app/modules/accounts/service.py`, `backend/app/modules/business/schemas.py`, `backend/tests/integration/test_signup.py`

**Interfaces:**
- Produces: `emails.clean_email(value: str) -> str` (strip, lowercase, then shape check `^[^@\s\x00]+@[^@\s\x00]+\.[^@\s\x00]+$` and ≤ 254 chars; else `PydanticCustomError("email_invalid", "Enter a valid email address.")`). `accounts.service.clean_email` (re-export), `accounts.service.hash_password(plain: str) -> str`, `accounts.service.verify_password(plain: str, password_hash: str) -> bool`. Both NFKC-normalise `plain` with `unicodedata.normalize("NFKC", …)`.

- [ ] **Step 1: Failing tests.**
  - `test_emails.py`: `clean_email("  Owner@Shop.COM ") == "owner@shop.com"`; `clean_email("a\x00b@shop.com")` raises with type `email_invalid`; a 255-char address raises.
  - `test_passwords.py`: `verify_password("café is open now", hash_password("café is open now")) is True`; a wrong password → `False`.
  - `test_signup.py::test_nul_in_email_is_a_field_error`: sign-up with `"a\x00b@example.com"` → 422, `fields == [{"field": "email", "message": "Enter a valid email address."}]`.
- [ ] **Step 2: Run** `BE: uv run pytest tests/unit/test_emails.py tests/unit/test_passwords.py tests/integration/test_signup.py -q` → FAIL.
- [ ] **Step 3: Implement.** Move `_EMAIL_RE` and `MAX_EMAIL` from `business/schemas.py` into `emails.py`; the sign-up validator calls `accounts_service.clean_email`. `verify_password` uses `_password_hash.verify`.
- [ ] **Step 4: Run** the same command → PASS; then `BE: uv run pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(accounts): one email rule, NFKC passwords, NUL refused (story 2.2)`

### Task 2: Sessions in `accounts` [CORE]

**Files:**
- Modify: `backend/app/core/tenancy.py`, `backend/app/modules/accounts/{repository,schemas,service}.py`, `backend/tests/integration/conftest.py`
- Test: `backend/tests/integration/test_sessions.py`, `backend/tests/unit/test_tenancy.py`

**Interfaces:**
- Consumes: `Role`, `Membership`, `UserSession`, `tenant_scope`, `BusinessRepository`, `accounts_service.create_owner`.
- Produces:
  - `tenancy.session_lookup() -> ContextManager[None]`: sets the same flag that `require_system_scope()` checks, with **no** log line. Docstring: "AD-3 source (a): staff session → membership. Only `accounts.service.resolve_session` uses it." `SYSTEM_SCOPE_CALLERS = {"signup", "login"}`.
  - `schemas.Actor(BaseModel)`: `user_id: UUID`, `membership_id: UUID`, `business_id: UUID`, `roles: set[Role]`.
  - `service.SESSION_IDLE_TIMEOUT = timedelta(days=7)`, `service.SESSION_TOUCH_INTERVAL = timedelta(minutes=5)`.
  - `service.start_session(session: Session, user_id: UUID) -> str` (returns the raw token).
  - `service.resolve_session(session: Session, token: str | None) -> Actor` (raises `NotAuthenticated`).
  - `service.end_session(session: Session, token: str | None) -> None` (no error if missing or unknown).
  - `service.NotAuthenticated(AppError)`: 401, `not_authenticated`, "Please log in."
  - `SessionRepository(session)`: `add(user_id, token_hash) -> UserSession`, `get_by_token_hash(h) -> UserSession | None`, `delete_by_token_hash(h) -> None`. `MembershipRepository.find_for_user(user_id) -> Membership | None` (calls `require_system_scope()`, plain `select(Membership)`, no tenant filter — documented exception like `email_exists`).
  - conftest: new fixture `migrated_db(pg, redis_url, monkeypatch)` (sets env vars, clears caches, runs `alembic upgrade head`, disposes the engine after). `client` now depends on it.

- [ ] **Step 1: Failing tests** in `test_sessions.py` (use `migrated_db`). A file helper `make_owner(s) -> (user_id, business_id)` builds the Owner directly: `BusinessRepository(s).add("Test Shop")`, then `accounts_service.create_owner` inside `tenant_scope`. It does **not** use `business.service.sign_up` (Task 4 changes it).
  - `test_start_session_stores_only_the_token_hash`: the token string is not in any `sessions` row; `token_hash == sha256(token)`.
  - `test_resolve_session_returns_the_actor`: `roles == {Role.OWNER, Role.TECHNICIAN}`, `business_id` equals the new Business.
  - `test_unknown_or_missing_token_is_not_authenticated`: `"nope"` and `None` → `NotAuthenticated`.
  - `test_idle_session_is_refused`: `last_seen_at = now() - 7 days - 1 minute` → `NotAuthenticated`.
  - `test_touch_only_after_five_minutes`: 1 minute old → unchanged; 6 minutes old → moved to about now.
  - `test_inactive_membership_is_refused`: `is_active = False` → `NotAuthenticated`.
  - `test_end_session_deletes_the_row`: then `resolve_session` → `NotAuthenticated`; `end_session(s, None)` and `end_session(s, "nope")` do nothing.
  - `test_tenancy.py`: `find_for_user` outside any scope raises `SystemScopeRequired`; inside `session_lookup()` it works and logs nothing (`caplog` empty); `system_scope("session")` raises `ValueError`.
- [ ] **Step 2: Run** `BE: uv run pytest tests/integration/test_sessions.py tests/unit/test_tenancy.py -q` → FAIL.
- [ ] **Step 3: Implement.** Expired sessions are only refused, not deleted: the 401 rolls the transaction back, so a delete there would be lost. Compare times with `datetime.now(UTC)` (the columns are `timestamptz`).
- [ ] **Step 4: Run** → PASS; `BE: uv run pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(accounts): server-side sessions with idle timeout (story 2.2)`

### Task 3: Attempt limiter and client IP in `core` [CORE]

**Files:**
- Create: `backend/app/core/rate_limit.py`, `backend/app/core/client_ip.py`
- Modify: `backend/app/core/errors.py` (`AppError` gets `headers: dict[str, str] | None = None`; the handler passes them on)
- Test: `backend/tests/integration/test_rate_limit.py`, `backend/tests/unit/test_client_ip.py`, `backend/tests/unit/test_errors.py`

**Interfaces:**
- Produces:
  - `AttemptLimiter(redis: Redis, purpose: str, limit: int, lock_seconds: int, unavailable_message: str)`. Redis key = `f"{purpose}:{key}"`.
    - `hit(key: str) -> int | None`: counts this attempt **first**. One `MULTI` pipeline: `INCR key` + `EXPIRE key lock_seconds NX`. If the new count `== limit`, run `EXPIRE key lock_seconds` (the fixed lock starts at the limit-reaching attempt). If the new count `> limit`, return the seconds left (`TTL`; if TTL is −1, set `EXPIRE key lock_seconds` and return `lock_seconds`). Else return `None`.
    - `undo(key: str) -> None`: `DECR` (used when an attempt turns out fine and should not count, e.g. the IP key on success).
    - `clear(key: str) -> None`: `DEL`.
    - Any `redis.RedisError` → `AppError("dependency_unavailable", unavailable_message, 503)`.
  - `client_ip(request: Request) -> str`: rightmost non-empty `X-Forwarded-For` value, stripped, parsed with `ipaddress.ip_address`; an invalid value falls back to `request.client.host`; no client → `"unknown"`. IPv4 → the address; IPv6 → `str(ip_network(f"{ip}/64", strict=False))`.

- [ ] **Step 1: Failing tests.**
  - `test_rate_limit.py` (real Valkey via `redis_url`; limit 5, lock 900): hits 1–5 → `None`; hit 6 → `0 < n <= 900`; after `clear` → `None`; `undo` lowers the count by 1; the key has the purpose prefix and a TTL > 0 after the first hit; a limiter on `redis://localhost:1/0` → `AppError` status 503 with the given message.
  - `test_client_ip.py`: `"1.2.3.4, 10.0.0.9"` → `"10.0.0.9"`; `" 10.0.0.9 "` → `"10.0.0.9"`; `"garbage"` → socket host; no header → socket host; no header and no client → `"unknown"`; `"2001:db8::1"` and `"2001:db8::ffff"` → both `"2001:db8::/64"`.
  - `test_errors.py`: an `AppError(..., headers={"Retry-After": "900"})` response has that header.
- [ ] **Step 2: Run** `BE: uv run pytest tests/integration/test_rate_limit.py tests/unit/test_client_ip.py tests/unit/test_errors.py -q` → FAIL.
- [ ] **Step 3: Implement** as above.
- [ ] **Step 4: Run** → PASS; `BE: uv run pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(core): attempt limiter and trusted client IP (story 2.2)`

### Task 4: Log-in, log-out, `/me`, and sign-up logs in [CORE]

**Files:**
- Create: `backend/app/core/session_cookie.py`, `backend/app/modules/accounts/router.py`, `backend/app/modules/accounts/dependencies.py`, `backend/tests/integration/test_login.py`
- Modify: `backend/app/modules/accounts/{schemas,service}.py`, `backend/app/modules/business/{service,router}.py`, `backend/app/main.py`, `backend/pyproject.toml` (import-linter), `backend/tests/integration/conftest.py`, `backend/tests/integration/test_signup.py`, `frontend/openapi.json`, `frontend/src/api/schema.d.ts`

**Interfaces:**
- Consumes: Task 1 `verify_password`, `clean_email`; Task 2 session functions and `Actor`; Task 3 `AttemptLimiter`, `client_ip`.
- Produces:
  - `session_cookie.SESSION_COOKIE = "__Host-sevadesk_session"`, `set_session_cookie(response: Response, token: str) -> None`, `clear_session_cookie(response: Response) -> None`.
  - `schemas.LoginRequest`: `email` (cleaned with `clean_email`), `password` (empty → `PydanticCustomError("password_empty", "Enter your password.")`; > 128 chars → `PydanticCustomError("password_long", "Use at most 128 characters.")`). `schemas.MeResponse`: `roles: list[Role]` (sorted).
  - `service.LOGIN_ACCOUNT_LIMIT = 5`, `LOGIN_IP_LIMIT = 20`, `LOGIN_LOCK_SECONDS = 900`.
  - `service.log_in(session: Session, email: str, password: str, ip: str) -> tuple[str, Actor]`; raises `InvalidCredentials` (401) or `TooManyAttempts` (429, `Retry-After`).
  - `dependencies.ActorDep = Annotated[Actor, Depends(get_actor)]`; `get_actor` reads the cookie and calls `resolve_session`.
  - `business.service.sign_up(...) -> tuple[SignupResponse, str]` (the second item is the session token).
  - conftest: `make_client(**kwargs) -> TestClient` = `TestClient(app, base_url="https://testserver", headers={"Origin": "https://testserver"}, **kwargs)`. `client` uses it. `migrated_db` also runs `get_redis().flushdb()` (the IP counter is shared by all tests).

- [ ] **Step 1: Test fixtures.** Add `make_client`; replace the two hand-built `TestClient(app, raise_server_exceptions=False)` in `test_signup.py` (lines ~141 and ~154) with `make_client(raise_server_exceptions=False)`. Every new test that needs a second client uses `make_client()` too.
- [ ] **Step 2: Failing tests** in `test_login.py`:
  - `test_login_sets_a_safe_cookie`: 200, `roles == ["owner", "technician"]`; `set-cookie` has `__Host-sevadesk_session`, `HttpOnly`, `Secure`, `SameSite=lax`, `Path=/`, no `Domain`.
  - `test_signup_also_logs_in`: after sign-up, `GET /api/v1/me` → 200.
  - `test_login_ends_the_old_session`: log in as A, save the cookie, log in as B on the same client → A's saved cookie on a new client → `/me` 401.
  - `test_wrong_password_and_unknown_email_look_the_same`: both 401, identical JSON bodies.
  - `test_unknown_email_still_checks_one_password`: `monkeypatch` a counting wrapper around `accounts.service.verify_password` → exactly 1 call.
  - `test_email_case_does_not_matter`: `OWNER@…` logs in.
  - `test_me_without_cookie_is_401`: code `not_authenticated`.
  - `test_logout_kills_the_old_cookie`: save the cookie, log out → 204 and cookie cleared; a new client with the saved cookie → `/me` 401.
  - `test_account_limit`: 5 wrong passwords (2 of them upper-case email) → 6th with the **right** password → 429 with `Retry-After`; another account from the same IP still logs in.
  - `test_parallel_wrong_logins_are_capped`: 10 wrong log-ins for one account at once (`ThreadPoolExecutor`, one `make_client()` each) → at most 5 replies are 401, the rest 429.
  - `test_ip_limit`: 20 wrong log-ins for different emails with `X-Forwarded-For: 203.0.113.7` → next one 429; the same with `203.0.113.8` → 401.
  - `test_success_clears_the_account_counter`: 4 wrong, 1 right, 4 wrong → last reply 401, not 429.
  - `test_no_raw_email_in_redis`: after a failed log-in, no key from `get_redis().keys("*")` contains `"@"`.
  - `test_redis_down_gives_503`: `REDIS_URL` → `redis://localhost:1/0` (clear caches) → `POST /login` 503 `dependency_unavailable`; no new `sessions` row.
  - `test_idle_session_returns_401`: push `last_seen_at` back 8 days → `/me` 401.
  - `test_inactive_member_cannot_log_in`: 401 `invalid_credentials`.
  - `test_login_field_errors`: empty password → 422 field `password`; 129-char password → 422 "Use at most 128 characters."; `"a\x00b@x.com"` → 422 field `email`.
  - `test_openapi_lists_envelope_errors`: in `app.openapi()`, `/api/v1/login` `post` responses 401, 422, 429, 503 and `/api/v1/me` `get` response 401 reference `ErrorEnvelope`.
- [ ] **Step 3: Run** `BE: uv run pytest tests/integration/test_login.py tests/integration/test_signup.py -q` → FAIL.
- [ ] **Step 4: Implement.** Order in `log_in`: `hit` the account key and the IP key (any 429 → raise `TooManyAttempts` with the larger wait) → look up the user in `system_scope("login")` → `verify_password` (against a module-level dummy hash when the user is missing) → check the membership is active → on failure raise `InvalidCredentials` (the attempt is already counted); on success `clear` the account key, `undo` the IP key, and `start_session`. The login and sign-up routers call `end_session` on any incoming cookie first (D11), then set the new cookie on the injected `Response`. Logout reads the cookie directly (no `ActorDep`), so an expired session can still log out. `main.py` includes `accounts.router`. In `pyproject.toml`, add `app.modules.accounts.router` to the forbidden list of the "business uses accounts only through its front door" contract, with a comment: "`dependencies.py` is the HTTP front door (AD-2 note, story 2.2)".
- [ ] **Step 5: Run** → PASS; `BE: uv run pytest -q` → PASS; `BE: uv run lint-imports` → PASS.
- [ ] **Step 6: Regenerate API types:** `BE: uv run python -m app.export_openapi ../frontend/openapi.json`, then (Windows) `cd frontend && npm run gen:api`.
- [ ] **Step 7: Commit** `feat(accounts): log in, log out, /me; sign-up starts a session (story 2.2)`

### Task 5: `Origin` guard for state-changing requests [CORE]

**Files:**
- Create: `backend/app/core/origin_guard.py`, `backend/tests/integration/test_origin_guard.py`
- Modify: `backend/app/core/errors.py` (public `error_response(status, code, message) -> JSONResponse` replaces the private `_envelope`), `backend/app/main.py` (call `add_origin_guard(app)` **before** `add_request_id(app)`, so the guard runs inside it and the 403 is logged with a request ID)

**Interfaces:**
- Produces: `add_origin_guard(app: FastAPI) -> None`. For `POST`, `PUT`, `PATCH`, `DELETE`: refuse with the `origin_refused` 403 envelope unless both headers exist and `urlsplit(origin).netloc.lower() == host.lower()`. Comment: "Caddy and the ALB pass `Host` through unchanged; no proxy may rewrite it." Other methods pass.

- [ ] **Step 1: Failing tests** (use `make_client` and override headers per request):
  - `test_post_without_origin_is_refused`: `POST /api/v1/login` without `Origin` → 403 `origin_refused`; after 6 such calls the account is still not locked (a right log-in with `Origin` → 200).
  - `test_cross_site_signup_creates_nothing`: `Origin: https://evil.example` → 403; Business count unchanged.
  - `test_null_origin_is_refused`: `Origin: null` → 403.
  - `test_every_unsafe_method_is_guarded`: `PUT`, `PATCH`, `DELETE` on `/api/v1/me` without `Origin` → 403 (not 405).
  - `test_origin_case_does_not_matter`: `Origin: https://TestServer` → not 403.
  - `test_get_needs_no_origin`: `GET /api/health` without `Origin` → not 403.
  - `test_same_origin_post_works`: the default client sign-up → 201.
- [ ] **Step 2: Run** `BE: uv run pytest tests/integration/test_origin_guard.py -q` → FAIL.
- [ ] **Step 3: Implement** as an `@app.middleware("http")` function that returns `error_response(...)`.
- [ ] **Step 4: Run** → PASS; `BE: uv run pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(core): Origin guard refuses cross-site writes (story 2.2)`

### Task 6: `/login` page and the 401 redirect [STANDARD]

**Files:**
- Create: `frontend/src/lib/navigate.ts`, `frontend/src/lib/auth.ts`, `frontend/src/lib/auth.test.ts`, `frontend/src/components/LoginForm.tsx`, `frontend/src/components/LoginForm.test.tsx`, `frontend/src/app/login/page.tsx`
- Modify: `frontend/src/api/client.ts`, `frontend/src/components/SignupForm.tsx`, `frontend/src/components/SignupForm.test.tsx`, `frontend/src/app/signup/page.tsx`

**Interfaces:**
- Produces:
  - `navigate.goTo(path: string): void` — a full page load (`window.location.assign`). Tests mock this module, because jsdom does not let tests spy on `window.location.assign`.
  - `auth.landingPath(roles: string[]): "/app" | "/app/calendar"`.
  - `auth.shouldRedirectToLogin(status: number, schemaPath: string, currentPath: string): boolean` — true only for 401, when `schemaPath !== "/api/v1/login"` and `currentPath !== "/login"`.
  - `client.ts`: `api.use({ onResponse({ response, schemaPath }) { … goTo("/login") … } })`.

- [ ] **Step 1: Failing tests.**
  - `auth.test.ts`: `["owner","technician"]` → `/app`; `["staff"]` → `/app`; `["technician"]` → `/app/calendar`; redirect: `(401, "/api/v1/me", "/app")` → true; `(401, "/api/v1/login", "/login")` and `(401, "/api/v1/login", "/app")` → false; `(403, "/api/v1/me", "/app")` → false; `(401, "/api/v1/me", "/login")` → false.
  - `LoginForm.test.tsx` (mock `@/api/client` and `next/navigation`): labels "Email" and "Password", button "Log in"; sends `{email, password}` to `/api/v1/login`; success with `roles ["technician"]` → `router.replace("/app/calendar")`; a 401 shows "Wrong email or password." in `role="alert"`; a 429 shows "Too many tries. Please wait 15 minutes and try again."; a 422 shows the field error and focuses it; button disabled with "Logging in…" while busy; link "Create your Business" → `/signup`.
  - `SignupForm.test.tsx`: add `vi.mock("next/navigation")` for the whole file; success → `router.replace("/app")`; the "sends the three fields" test waits for the `POST` call (`await vi.waitFor(() => expect(POST).toHaveBeenCalled())`) instead of `role="status"`.
- [ ] **Step 2: Run** `cd frontend && npm test` → FAIL.
- [ ] **Step 3: Implement.** Reuse the field/error pattern of `SignupForm` (same markup, `autoComplete="current-password"`). `/login` page copies the `/signup` layout; heading "Log in to SevaDesk"; metadata title "Log in · SevaDesk". `/signup` page gets "Already have an account? Log in" → `/login`.
- [ ] **Step 4: Run** `npm test && npm run lint && npm run typecheck` → PASS.
- [ ] **Step 5: Commit** `feat(frontend): /login page and 401 redirect (story 2.2)`

### Task 7: App shell with Role-based nav [STANDARD]

**Files:**
- Create: `frontend/src/lib/nav.ts`, `frontend/src/lib/nav.test.ts`, `frontend/src/components/AppShell.tsx`, `frontend/src/components/AppShell.test.tsx`, `frontend/src/components/LogoutButton.tsx`, `frontend/src/components/LogoutButton.test.tsx`, `frontend/src/app/app/layout.tsx`, `frontend/src/app/app/page.tsx`, `frontend/src/app/app/inbox/page.tsx`, `frontend/src/app/app/calendar/page.tsx`, `frontend/src/app/app/more/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/me` → `{roles}`; `POST /api/v1/logout`; `goTo`.
- Produces: `navItems(roles: string[]): {href: string; label: string; icon: LucideIcon}[]` — Owner/Staff: Dashboard `/app` (`LayoutDashboard`), Inbox `/app/inbox` (`Inbox`), Calendar `/app/calendar` (`CalendarDays`), More `/app/more` (`Ellipsis`); Technician-only: Calendar, More. `<AppShell roles={string[]}>{children}</AppShell>`.

- [ ] **Step 1: Failing tests.**
  - `nav.test.ts`: the two role sets give the labels above in that order; `["owner","technician"]` gives the four-item list.
  - `AppShell.test.tsx` (mock `usePathname` → `/app/calendar`): one `nav` labelled "Main" (mobile) and one labelled "Sidebar" (desktop); each item is a link with its label; the Calendar links have `aria-current="page"`; Technician-only shows no "Dashboard".
  - `LogoutButton.test.tsx` (mock `@/api/client` and `@/lib/navigate`): click "Log out" → `POST /api/v1/logout`, then `goTo("/login")`; when the call fails, it still calls `goTo("/login")`.
- [ ] **Step 2: Run** `npm test` → FAIL.
- [ ] **Step 3: Implement.** Bottom bar: `fixed inset-x-0 bottom-0 lg:hidden`, items `min-h-11`; sidebar: `hidden lg:flex w-60`; main content gets bottom padding on mobile so the bar hides nothing. `app/app/layout.tsx` is a client component: `GET /api/v1/me` on mount; while waiting it shows a plain skeleton block; on data it renders `AppShell`; on 401 the client middleware redirects. Placeholder pages: an `h1` with the page name and "Coming soon." The More page holds `LogoutButton`.
- [ ] **Step 4: Run** `npm test && npm run lint && npm run typecheck && npm run build` → PASS.
- [ ] **Step 5: Commit** `feat(frontend): app shell with Role-based nav and log out (story 2.2)`

### Task 8: Live check, learning notes, PR [STANDARD]

**Files:**
- Create: `docs/learning/2-2.md`
- Modify: `docs/learning/glossary.md`, `infra/terraform/README.md` (one line: "Log-in needs TLS on the ALB: browsers drop the `Secure` session cookie over plain HTTP."), `_bmad-output/implementation-artifacts/sprint-status.yaml` (`2-2…: done`)

- [ ] **Step 1: Live check** (`docker compose up --build` in `infra/compose`, Chrome at `http://localhost`):
  - sign up → lands on `/app` with 4 tabs (narrow window) and a sidebar (≥ 1024px)
  - DevTools → Application → Cookies: `__Host-sevadesk_session` is HttpOnly, Secure, Lax
  - More → Log out → `/login`; then open `/app` → sent to `/login` again
  - 6 wrong passwords → "Too many tries…"
  - `curl -X POST http://localhost/api/v1/logout` (no Origin) → 403
  - `psql`: `sessions.token_hash` is 64 hex chars; no raw token anywhere
  - local Grafana: the `POST /api/v1/login` trace is there; no email or password in span attributes or log lines
  - Lighthouse Accessibility on `/login` and `/app` → no label or contrast failures
- [ ] **Step 2: Full suite** (stack down): `BE: uv run pytest --cov -q`, `cd frontend && npm test` → PASS.
- [ ] **Step 3: Write** `docs/learning/2-2.md` and glossary terms: session token, cookie flags (HttpOnly, Secure, SameSite, `__Host-`), CSRF, `Origin` header, rate limit / fixed lock, race condition, `X-Forwarded-For`, user enumeration, NFKC.
- [ ] **Step 4: Opus final review** of the whole branch; fix findings.
- [ ] **Step 5: Understanding Gate + hands-on task** (CLAUDE.md §5–6).
- [ ] **Step 6: Commit, push, PR** with `Closes #9` and the Deferred list; merge when green; check the demo deploy (`/login` 200, log-in works over https).
