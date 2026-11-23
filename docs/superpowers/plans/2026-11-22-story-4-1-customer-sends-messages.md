# Story 4.1 — Customer sends Messages on the Chat Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, per CLAUDE.md §4: build in this session, stop after each CORE task, one Opus whole-branch review at the end). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Customer with no account writes Messages on `/c/{slug}`. The server saves each one once, in order. The same browser sees the same Conversation when it comes back.

**Architecture:** A new module `inbox` owns 4 tenant tables (`customers`, `visitor_tokens`, `conversations`, `messages`). A shared FastAPI dependency in `business` turns the slug into a Business and enters `tenant_scope` (used by the old Chat Page route and the 2 new routes). Identity is a channel concern: a `Channel` port (2 methods) with one adapter, `WebchatChannel`, that turns the visitor cookie into a Conversation. `inbox/service.py` is channel-neutral: it locks the Conversation row, checks `client_message_id`, gives the next `seq`, and saves. The frontend adds a `ChatPanel` under the Services list.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2.1 (postgresql `insert … on_conflict_do_nothing`, `with_for_update`, `populate_existing`), Alembic, Redis/Valkey (`AttemptLimiter`), pytest + testcontainers; Next.js 16, React 19, Tailwind 4, Vitest, openapi-typescript.

**Spec:** `_bmad-output/planning-artifacts/epics.md:719-757` (Story 4.1, GitHub issue #17). Also FR-15 (`:47`), NFR-5/6/8/9 (`:82-86`), AR-1/4/6/10/12/13 (`:94-110`), UX-DR7/13/20/32 (`:138,144,155,169`); ARCHITECTURE-SPINE.md AD-3, AD-5, AD-7, AD-8 (Message shape), AD-15, AD-16, dependency direction (`:183-200`), ER (`:323`); mockups/key-chat-page.html (placeholder copy `:71,92`).

**Review history:** an Opus plan review (2026-11-22) found 1 blocker, 5 major, 11 minor gaps. All 17 are fixed below (marked `[G#]`).

## Global Constraints

- Module `inbox` owns `customers`, `visitor_tokens`, `conversations`, `messages` (AR-1). All 4 are tenant tables (`TenantModel`, `UniqueConstraint("business_id","id")`, composite FKs, AD-3).
- Dependency direction: `inbox → business → accounts → core` (import-linter layers). `inbox` uses `business` only via `business.service` / `business.dependencies`, and `accounts` only via `accounts.service` / `accounts.dependencies`.
- **GET never writes the database (AD-5).** `GET /chat/{slug}/messages` may SET the visitor cookie, nothing else. The `visitor_tokens` row is written on the first send. **This differs from the AC wording ("stores only its hash" on the first visit); approved by the user 2026-11-22; say so in the PR body** `[G17]`.
- **Per-Business hash** `[G6]`: a `__Host-` cookie has `Path=/`, so one token reaches every slug. The stored value is `hash_token(f"{business_id}:{token}")`, so the same browser has a different hash in each Business and the database cannot link a visitor across Businesses. Never the raw token.
- Visitor cookie: name `__Host-sevadesk_visitor`, value `new_token()` (`secrets.token_urlsafe(32)` = exactly 43 chars of `[A-Za-z0-9_-]`), flags `path=/`, `secure`, `httponly`, `samesite=lax`, `max_age` 365 days. A cookie that is not exactly `^[A-Za-z0-9_-]{43}$` counts as missing, and a new token is issued `[G10]`.
- Public routes never accept a `conversation_id` (path, query, or body) and never return one (AR-10). They return no ids at all except `client_message_id`.
- Routes (all under `/api/v1`, no log-in):
  - `GET /chat/{chat_slug}` (existing, `get_chat_page`).
  - `GET /chat/{chat_slug}/messages` → `ChatMessagesOut`, operation_id `list_chat_messages`, responses 404.
  - `POST /chat/{chat_slug}/messages` → `MessageOut`, status 201, operation_id `send_chat_message`, responses 404, 422, 429, 503.
- Message shape (AR-13) in the DB: `author_type` (`customer | agent | user | system`), `author_membership_id` (null unless `user`), `body`, `lang` (`en | hi`), `client_message_id` (uuid, null for non-customer), `actions` (jsonb, default `[]`), plus `seq`, `created_at`.
- `MessageOut` (public): `seq: int`, `author_type: str`, `body: str`, `lang: str`, `client_message_id: UUID | None`, `actions: list[dict[str, Any]]`, `created_at: datetime`.
- `SendMessageIn`: `body: str`, `client_message_id: UUID`. Body rules, in order: refuse any control character (Unicode category `Cc`) except `\n`, `\r`, `\t` — this includes NUL, which Postgres refuses (→ 500) `[G1]`; then strip; then 1–2000 chars. Copy: control char → `This message has characters we cannot save.`; empty → `Write a message first.`; too long → `A message can be at most 2000 characters.`
- `lang`: `"hi"` if the body has any char in U+0900–U+097F (Devanagari), else `"en"`.
- New Conversation: `state = "agent"`, `last_seq = 0`. First Message gets `seq = 1`.
- **Lock order** `[G17]`: visitor-token row first, then Conversation row. Any later flow that takes both (Story 4.5 Customer delete, 4.4 staff reply takes only the Conversation) follows this order. Written as a comment in `webchat.py` and `service.py`.
- Rate limits (NFR-5), `AttemptLimiter`, fail closed (503). Both keys follow AD-3 "purpose, then business_id" `[G8]`:
  - per IP per Business: purpose `chat_send:ip`, key `f"{business_id}:{client_ip(request)}"`, limit 120, window/lock 600 s. Checked in the router BEFORE the database. (Per Business, not global: Indian carriers put many phones behind one IP, CGNAT.)
  - per Conversation: purpose `chat_send:conv`, key `f"{business_id}:{conversation_id}"`, limit 30, window/lock 600 s. Checked in the service AFTER the duplicate check, so a retry of a saved Message never gets 429 `[G7]`.
  - 429: code `too_many_messages`, `You are sending messages too fast. Please wait a few minutes.`, header `Retry-After`. 503: `Chat is not available right now. Please try again.`
- No `agent_reply` job yet (Epic 6). No poll loop yet (Story 4.2).
- UI copy, verbatim: composer label `Message` (visually hidden), placeholder `Type a message…` (mockup) `[G14]`, button `Send`; failed bubble: `Not sent` + button `Retry`; collapse button `Services & prices`; panel load failed: `Could not load the chat.` + button `Try again`; DPDP notice text unchanged from Story 3.3.
- UI behaviour `[G15]`:
  - The DPDP notice shows above the composer while the panel has NO items at all (loaded or local). The first local item (even a failed one) hides it.
  - `taking_requests === false` → no composer, no notice from the panel; the page keeps "Not taking requests yet". (The panel still shows any old Messages.)
  - Panel states: loading → a small skeleton; failed → `Could not load the chat.` + `Try again` (reload); not_found → nothing (the page itself already handles a bad slug). The composer shows only when the messages GET is `ready`, so the cookie is set before the first POST `[G10]`.
  - Several sends in flight: each bubble keeps its screen place (send order). Server `seq` order may differ; accepted in 4.1 (4.2 polling will show server order).
- Chat Page first load ≤ 204,800 bytes gzip (CI step). Plain elements on `/c` pages, no `ui/button` (radix). No lazy loading unless the measure says so `[G3]`.
- Backend commands run in WSL: `wsl --cd "C:\Books\DataSense Community\Seva Desk\backend" -e bash -lc "uv run …"`. Frontend: PowerShell `npx vitest run …`, `npm run lint`, `npm run typecheck`. Docker Desktop must run.
- Branch `story/4-1-customer-sends-messages`. PR body ends with `Closes #17`.

## Review Focus

1. **A send and a staff write on the same Conversation at the same moment** → the send waits for the lock and gets the next free `seq`, never a stale one. Test: Task 4 `test_send_waits_for_the_conversation_lock` `[G2]`.
2. **The same browser opens another Business's Chat Page** (the cookie is shared across slugs) → sees none of the first Business's Messages, its send starts a new Conversation there, and its stored hash differs. Tests: Task 4 `test_same_cookie_gets_a_different_hash_per_business`, Task 5 isolation checks `[G6]`.
3. **A forged, short, or huge cookie value** → treated as a new visitor, never a 500. Test: Task 5 `test_bad_cookie_is_a_new_visitor` `[G10]`.
4. **A body with NUL or another control character** → 422 with a field error, never 500. Tests: Task 4 unit + Task 5 `test_nul_in_body_is_422` `[G1]`.
5. **A retry after the first try really saved** (response lost), even at the rate limit → the same Message comes back, no second row, no 429. Tests: Task 4 `test_same_client_message_id_saves_once`, `test_retry_of_saved_message_skips_the_limit`, Task 6 `retry sends the same client_message_id` `[G7]`.

---

### Task 0: Branch housekeeping (BOILERPLATE)

- [ ] Branch exists (`story/4-1-customer-sends-messages`).
- [ ] `docs/learning/gaps.md`: set status of the 3.3 Q1 (NUL slug) and Q3 (`tenant_scope`) rows to `passed 2026-11-22 (Epic 4 start quiz, re-ask)`.
- [ ] `sprint-status.yaml`: `epic-4: in-progress` `[G17]` and `4-1-customer-sends-messages-on-the-chat-page: in-progress`.
- [ ] Commit `chore: start story 4.1`.

### Task 1: Shared token helpers in core (STANDARD)

**Files:** Create `backend/app/core/tokens.py`; modify `backend/app/modules/accounts/service.py:144-153`; test `backend/tests/unit/test_tokens.py`.

**Interfaces — Produces:** `new_token() -> str` (`secrets.token_urlsafe(32)`), `hash_token(token: str) -> str` (sha256 hex). `accounts/service.py` keeps the name importable: `from app.core.tokens import hash_token as hash_token` (`team.py:39` and `tests/integration/test_invite_accept.py:17` use `accounts.service.hash_token`) `[G16]`.

- [ ] Write `test_tokens.py`: `test_new_tokens_differ` (two calls differ, each matches `^[A-Za-z0-9_-]{43}$`), `test_hash_is_sha256_hex` (`hash_token("abc") == hashlib.sha256(b"abc").hexdigest()`). Run → FAIL.
- [ ] Create `core/tokens.py`; accounts imports from it (delete its own body, use `new_token()` where it calls `secrets.token_urlsafe(32)`). Run unit + `tests/integration/test_sessions.py test_team_invites.py test_invite_accept.py test_login.py` → PASS `[G16]`.
- [ ] Commit `refactor(core): one token helper for sessions, invites, and visitors`.

### Task 2: Shared Chat Page entry dependency (CORE) — checkpoint after

**Files:** Create `backend/app/modules/business/dependencies.py`; modify `business/service.py:219-260`, `business/router.py:122-127`, `business/schemas.py`, `pyproject.toml` (allow `business.dependencies` as a front door in comments only; no contract change yet); test `backend/tests/integration/test_chat_page.py`; regenerate `frontend/openapi.json`, `frontend/src/api/schema.d.ts` `[G17]`.

**Interfaces — Produces:**
- `business.schemas.ChatBusiness(BaseModel)`: `business_id: UUID`, `name: str`.
- `business.service.find_chat_business(session, chat_slug: str) -> ChatBusiness` — lowercases, `_SLUG_SHAPE` check, `find_by_chat_slug`, raises `NotFound` for both bad shape and unknown.
- `business.dependencies.ChatBusinessDep = Annotated[ChatBusiness, Depends(chat_business_in_tenant_scope, scope="function")]`. Sync `get_chat_business(chat_slug: str, session: SessionDep) -> ChatBusiness` + async `chat_business_in_tenant_scope(business: Annotated[ChatBusiness, Depends(get_chat_business)])` that yields inside `tenant_scope(business.business_id)` (same reason as `accounts/dependencies.py:21-28`).
- `business.service.get_chat_page(session, business: ChatBusiness) -> ChatPageOut` (no slug, no `tenant_scope` inside: the dependency set it).

- [ ] Before each test, one line on what it checks. Add to `test_chat_page.py`: `test_route_runs_inside_the_slug_business` — a probe route on a throwaway `FastAPI` app that uses `ChatBusinessDep` and returns `str(current_business_id())`; it equals the slug's Business id. Existing tests (`test_bad_slug_is_not_found[nul]` etc.) must still pass. Run → FAIL (module missing).
- [ ] Implement. Run `test_chat_page.py`, `uv run pytest -m isolation` → PASS.
- [ ] Regenerate `openapi.json` (`uv run python -m app.export_openapi ../frontend/openapi.json` in WSL) and `npm run gen:api`; `git diff` shows only harmless changes (the `chat_slug` parameter keeps its name and type).
- [ ] Commit `refactor(business): one slug-to-Business dependency for public chat routes`.
- [ ] **CHECKPOINT** — explain the dependency chain to the user; wait.

### Task 3: Inbox tables and migration (CORE) — checkpoint after

**Files:** Create `backend/app/modules/inbox/__init__.py`, `inbox/models.py`, `backend/migrations/versions/0009_inbox.py`; modify `backend/migrations/env.py:5-7` (add `import app.modules.inbox.models`) `[G5]`, `backend/tests/integration/test_migrations.py:28-40` (add the 4 table names to the expected set) `[G5]`; test `backend/tests/integration/test_inbox_tables.py`.

**Interfaces — Produces (SQLAlchemy models, inbox-private):**
- `Customer`: `id`, `business_id`, `created_at`.
- `VisitorToken`: `id`, `business_id`, `token_hash: str`, `created_at`; `UniqueConstraint("business_id","token_hash")`.
- `Conversation`: `id`, `business_id`, `customer_id`, `visitor_token_id`, `state: str` (server_default `agent`, CHECK `state IN ('agent','handoff','closed')` name `state_valid`), `last_seq: int` (server_default `0`, CHECK `last_seq >= 0` name `last_seq_valid`), `created_at`. Composite FKs to `customers` and `visitor_tokens`.
- `Message`: `id`, `business_id`, `conversation_id`, `seq: int`, `author_type: str`, `author_membership_id: UUID | None`, `body: str`, `lang: str`, `client_message_id: UUID | None`, `actions: list` (JSONB, server_default `'[]'`), `created_at`. Constraints: UNIQUE `(business_id, conversation_id, seq)`; UNIQUE `(business_id, conversation_id, client_message_id)`; CHECK `author_type IN ('customer','agent','user','system')` name `author_type_valid`; CHECK `(author_type = 'user') = (author_membership_id IS NOT NULL)` name `member_only_for_user`; CHECK `lang IN ('en','hi')` name `lang_valid`; CHECK `char_length(body) > 0` name `body_not_empty`; composite FKs to `conversations` and `memberships(business_id, id)`.
- The token links to the Customer THROUGH the Conversation (`conversations.customer_id` + `conversations.visitor_token_id`); `visitor_tokens` has no `customer_id`. Task 7 updates the spine ER to match `[G9]`.
- Migration names written by hand following `core/db.py:13-19` (e.g. `uq_messages_business_id_conversation_id_seq`, `fk_messages_business_id_conversations`, `ck_messages_author_type_valid`).

- [ ] One line per test, then write `test_inbox_tables.py` (direct SQL inserts, like `test_working_hours_table.py`): `test_seq_is_unique_per_conversation`, `test_client_message_id_is_unique_per_conversation`, `test_two_null_client_message_ids_are_allowed` (agent rows), `test_bad_author_type_is_refused`, `test_user_message_needs_a_member`, `test_message_cannot_point_into_another_business` (composite FK), `test_visitor_token_hash_unique_per_business` (same hash in 2 Businesses is allowed). Each refusal asserts `IntegrityError` and the constraint name. Run → FAIL.
- [ ] Write models + migration 0009 (downgrade drops in reverse) + the `env.py` import + the `test_migrations.py` table set. Run `test_inbox_tables.py`, `test_migrations.py`, `test_tenant_schema.py` → PASS (the schema test sees the 4 new tables).
- [ ] Commit `feat(inbox): customers, visitor tokens, conversations, messages tables`.
- [ ] **CHECKPOINT.**

### Task 4: Channel port, webchat adapter, and the save logic (CORE) — checkpoint after

**Files:** Create `inbox/channel.py`, `inbox/webchat.py`, `inbox/repository.py`, `inbox/schemas.py`, `inbox/service.py`; tests `backend/tests/integration/test_inbox_service.py`, `backend/tests/unit/test_inbox_schemas.py`.

**Interfaces:**
- Consumes: `core.tokens.hash_token`, `core.tenancy.current_business_id`, `core.repository.TenantRepository`, `core.rate_limit.AttemptLimiter`, `core.redis_client.get_redis`.
- Produces:
  - `channel.Channel(Protocol)`: `find_conversation(self, session) -> Conversation | None` (read only, never writes) and `open_conversation(self, session) -> Conversation` (find or start; returns the row LOCKED). Docstring: one adapter per channel; WhatsApp later = a new adapter, no change in `service.py`. Outbound `deliver` comes with the first reply (Story 4.4 / Epic 6), not now.
  - `repository`: every `FOR UPDATE` read also sets `.execution_options(populate_existing=True)`, so SQLAlchemy's identity map (its in-memory copy of rows already read) is refreshed with the locked values `[G2]`. Methods: `VisitorTokenRepository.ensure(token_hash) -> None` (postgresql `insert().on_conflict_do_nothing(index_elements=["business_id","token_hash"])`, `business_id` from `current_business_id()` by hand, like `replace_week`), `VisitorTokenRepository.find(token_hash) -> VisitorToken | None`, `VisitorTokenRepository.lock(token_hash) -> VisitorToken`, `ConversationRepository.newest_for_visitor(visitor_token_id, *, lock: bool) -> Conversation | None` (ONE query: `order_by(created_at desc, id desc).limit(1)`, `with_for_update()` when `lock`), `MessageRepository.list_for(conversation_id)`, `MessageRepository.find_by_client_id(conversation_id, client_message_id)`.
  - `webchat.WebchatChannel(token: str)`: `_hash()` = `hash_token(f"{current_business_id()}:{token}")` `[G6]`. `find_conversation`: `find` → `newest_for_visitor(lock=False)`. `open_conversation`: `ensure` → `lock` (visitor row; this makes a visitor's sends wait in line) → `newest_for_visitor(lock=True)`, or a new `Customer` + `Conversation` (a row this transaction inserted is already its own). Comment: lock order visitor token → Conversation `[G17]`.
  - `webchat` cookie parts: `VISITOR_COOKIE`, `VisitorTokenCookie` (Annotated Cookie), `set_visitor_cookie(response, token)`, `usable_token(raw: str | None) -> str | None` (None unless it matches `^[A-Za-z0-9_-]{43}$`) `[G10]`.
  - `schemas`: `SendMessageIn` (rules and copy in Global Constraints `[G1]`), `MessageOut`, `ChatMessagesOut(messages: list[MessageOut])`, `detect_lang(body: str) -> Literal["en","hi"]`.
  - `service.list_messages(session, channel: Channel) -> ChatMessagesOut` (by `seq`, empty if no Conversation; writes nothing).
  - `service.receive_message(session, channel: Channel, data: SendMessageIn) -> MessageOut`, in this order `[G7]`: `open_conversation` (locked) → existing by `client_message_id`? return it → conversation limiter `hit` (raise `TooManyMessages(retry_after)`) → `seq = last_seq + 1`, set `last_seq`, insert `author_type="customer"`, `lang=detect_lang(body)`. No commit (AD-15).
  - `service.TooManyMessages(AppError)` (429, copy in Global Constraints), `service.chat_send_ip_limiter() -> AttemptLimiter`, `service.chat_send_conversation_limiter() -> AttemptLimiter` (tests monkeypatch the limit constants `CHAT_SEND_IP_LIMIT`, `CHAT_SEND_CONVERSATION_LIMIT`).

- [ ] One line per test, then write `test_inbox_service.py` (call the service inside `tenant_scope` with a real `Session`; Valkey from `migrated_db`):
  - `test_first_send_starts_customer_and_conversation` → 1 customer, 1 conversation with `state == "agent"`, message `seq == 1`, `author_type == "customer"`, `actions == []`.
  - `test_seq_goes_up_by_one` → 3 sends → seqs `[1, 2, 3]`, `last_seq == 3`.
  - `test_same_client_message_id_saves_once` → same id twice → 1 row; both calls return the same `seq`.
  - `test_retry_of_saved_message_skips_the_limit` → limit 1: send id A (ok), send id A again → returns it, no `TooManyMessages` `[G7]`.
  - `test_conversation_limit_returns_429` → limit 2; 3rd new id raises `TooManyMessages`.
  - `test_token_stored_only_as_hash` → `token_hash == sha256(f"{business_id}:{token}")`; the raw token appears in no column of any inbox table.
  - `test_same_cookie_gets_a_different_hash_per_business` → one token sends in Business A and B → 2 rows, hashes differ `[G6]`.
  - `test_list_messages_is_own_conversation_only` → tokens X and Y in one Business; X lists only X's bodies.
  - `test_list_with_unknown_token_writes_nothing` → 0 rows in `visitor_tokens` afterwards.
  - `test_send_waits_for_the_conversation_lock` `[G2]` — the step-by-step pattern of `test_invite_accept.py:127-144`: (1) make a Conversation with 1 Message; (2) a raw connection runs `SELECT … FROM conversations WHERE id = … FOR UPDATE` and holds it; (3) a send runs in a `threading.Thread` that enters `tenant_scope` ITSELF (ContextVars are not copied into new threads) with its own `Session`; (4) after 0.5 s the thread is still alive; (5) the held connection sets `last_seq = 5` and commits; (6) the thread finishes and its Message has `seq == 6`. Join with a timeout so a bug fails, not hangs.
  - `test_first_sends_from_one_browser_share_one_conversation` → 2 threads (each with its own `tenant_scope` + `Session`), same token, different ids → 1 conversation, seqs `{1, 2}`. A behaviour test: it does not prove which lock does the work.
  - `test_hindi_body_gets_lang_hi` (`"नमस्ते"` → `hi`; `"namaste"` → `en`).
  - `test_another_channel_needs_no_service_change` → a ~10-line `FakeChannel` in the test (makes one Customer + Conversation, returns it locked) works with `receive_message` unchanged.
  - Unit `test_inbox_schemas.py`: body stripped; `""`/`"   "` → `Write a message first.`; 2001 chars → `A message can be at most 2000 characters.`; 2000 OK; `"hi\u0000"` and `"\u0007"` → `This message has characters we cannot save.`; `"line 1\nline 2\ttab"` OK `[G1]`.
  Run → FAIL.
- [ ] Implement. Run both test files → PASS. Run `uv run lint-imports` → PASS.
- [ ] Commit `feat(inbox): channel port, webchat adapter, and idempotent Message save`.
- [ ] **CHECKPOINT.**

### Task 5: Public routes, rate limits, isolation, import rules (STANDARD)

**Files:** Create `inbox/router.py`; modify `app/main.py`, `backend/pyproject.toml` (import-linter), `tests/integration/test_tenant_isolation.py`; test `backend/tests/integration/test_chat_messages.py`; regenerate `frontend/openapi.json`, `frontend/src/api/schema.d.ts`.

**Interfaces — Consumes:** `ChatBusinessDep` (Task 2), everything from Task 4. Router: `token = usable_token(cookie)`; if None → `new_token()` + `set_visitor_cookie`. POST: `chat_send_ip_limiter().hit(f"{business.business_id}:{client_ip(request)}")` first (raise `TooManyMessages(retry_after)` if not None) `[G8]`, then `service.receive_message(session, WebchatChannel(token), body)`.

- [ ] Write `test_chat_messages.py` (TestClient keeps cookies):
  - `test_first_visit_sets_an_httponly_visitor_cookie` → `set-cookie` has `__Host-sevadesk_visitor=`, `HttpOnly`, `Secure`, `SameSite=lax`, `Path=/`; body `{"messages": []}`; 0 `visitor_tokens` rows.
  - `test_second_visit_keeps_the_cookie` → no new `set-cookie` on the 2nd GET.
  - `test_send_then_return_sees_own_messages` → POST 201 with `seq 1`; a new GET in the same client lists it; a 2nd client (other browser) lists `[]`.
  - `test_send_without_cookie_still_works` → fresh client POSTs first → 201 and a cookie is set.
  - `test_duplicate_send_returns_the_same_message` → 2 POSTs, same id → both 201, same `seq`, 1 row.
  - `test_unknown_slug_is_not_found` for GET and POST (`assert_not_found`).
  - `test_bad_body_is_422` → `{"body": " "}` → 422, field `body`.
  - `test_nul_in_body_is_422` → `{"body": "hi\u0000"}` → 422, field `body`, 0 messages `[G1]`.
  - `test_ip_limit_returns_429` → monkeypatch `CHAT_SEND_IP_LIMIT` to 2 → 3rd POST (new ids) 429 with `Retry-After`, code `too_many_messages`.
  - `test_send_fails_closed_without_redis` → set `REDIS_URL` to a closed port, then `get_settings.cache_clear()` AND `get_redis.cache_clear()` (as `test_login.py:169-171`), client with `raise_server_exceptions=False` → 503; 0 messages `[G11]`.
  - `test_bad_cookie_is_a_new_visitor` (parametrized: 5000 chars, `"a"`, 43 chars with `!`) → a FRESH client sends the cookie through `headers={"Cookie": f"__Host-sevadesk_visitor={value}"}` (as `test_invite_accept.py:160`, not `client.cookies.set`) → 200 and a new `set-cookie` `[G10]` `[G11]`.
  - `test_public_routes_take_no_conversation_id` → no parameter or body property named `conversation_id` in any `/api/v1/chat/` operation of `app.openapi()`, and `MessageOut` has no `conversation_id`.
  - Isolation (`test_tenant_isolation.py`): `check_list_chat_messages` (one browser sends to B's slug, then lists A's slug → `[]`) and `check_send_chat_message` (that browser sends to A → A has 1 Conversation, B still 1, by direct DB count); add both to `ISOLATION_CHECKS`.
  Run → FAIL.
- [ ] Implement router, include it in `main.py`. Import-linter: layers become `["app.modules.inbox", "app.modules.business", "app.modules.accounts", "app.core"]`; add forbidden contracts "inbox uses business only through its front door" (forbid `business.models`, `business.repository`, `business.router`, `business.chat_slug`) and "inbox uses accounts only through its front door" (same list as the business one). Run all of the above + `uv run pytest -m isolation` + `uv run lint-imports` + `uv run ruff check .` → PASS.
- [ ] Regenerate `openapi.json` and `schema.d.ts` (as Task 2).
- [ ] Commit `feat(inbox): public routes to read and send chat Messages`.

### Task 6: Chat UI (STANDARD)

**Files:** Create `frontend/src/components/ChatPanel.tsx`, `ChatPanel.test.tsx`; modify `ChatPage.tsx`, `ChatPage.test.tsx`.

**Interfaces:** `export function ChatPanel({ slug, businessName, takingRequests, onHasMessages }: { slug: string; businessName: string; takingRequests: boolean; onHasMessages: (has: boolean) => void })`. `ChatPage` imports it normally (no `lazy`) and renders it under the Services list when the page is `ready` `[G3]`.

- `ChatPanel` loads `GET …/messages` with `useLoad`. States in Global Constraints "UI behaviour" `[G15]`. Local list item: `{ clientMessageId: string; body: string; status: "sending" | "sent" | "failed"; message?: MessageOut }`. Send = `crypto.randomUUID()`, clear the box, add item `sending`, POST; 201 → `sent` with the server message; any error or network failure → `failed`. Retry re-POSTs the SAME `client_message_id` and body. Display order = loaded messages, then local items in send order.
- Bubbles: `author_type === "customer"` → right, `bg-primary text-primary-foreground`; others left on card with border; `rounded-xl`. `lang` attribute from the message (`lang="hi"` on Hindi). The list `<ol role="log" aria-live="polite">` is ALWAYS rendered, even empty, so the first Message is announced `[G13]`.
- Composer (only when `ready` and `takingRequests`): visually hidden `<label>` `Message`, `<textarea>` placeholder `Type a message…`, `<button>` `Send` (disabled when the trimmed text is empty; 44 px tall). Focus stays in the textarea after Send `[G13]`. Enter without Shift sends only when `typeof window.matchMedia === "function" && window.matchMedia("(pointer: fine)").matches`; Shift+Enter is a new line `[G12]`.
- `onHasMessages(items.length > 0)` is called from a `useEffect`, never during render `[G13]`.
- `ChatPage`: state `hasMessages` + `servicesOpen`. When `hasMessages`, below `md` the Services section is hidden unless `servicesOpen`, and a `md:hidden` button `Services & prices` with `aria-expanded` toggles it. The old always-on notice in `Ready` is removed (the panel owns it now).

- [ ] Write tests (mock `api` as in `ChatPage.test.tsx`):
  - `ChatPanel.test.tsx`: shows loaded messages, customer bubble has the right-side class; `lang="hi"` on a Hindi message; `role="log"` present with 0 messages; notice shown with 0 messages and gone after a send; no composer and no notice when `takingRequests` is false; no composer while loading; failed load shows `Could not load the chat.` and `Try again` reloads; send posts body + a uuid and shows the saved bubble; focus is back in the textarea after Send; a failed POST shows `Not sent` and `Retry`, the text stays; `retry sends the same client_message_id`; Send disabled for spaces; with `matchMedia` stubbed to `pointer: fine`, Enter sends and Shift+Enter does not; with no `matchMedia`, Enter does not send `[G12]`. Move the 2 notice tests from `ChatPage.test.tsx:55-58,72-78` here `[G4]`.
  - `ChatPage.test.tsx`: `vi.mock("./ChatPanel")` with a stub that renders a button calling `onHasMessages(true)` `[G4]`; after it, the `Services & prices` button appears and toggles `aria-expanded`; with no messages there is no button; the stub gets `takingRequests` from the page.
  Run `npx vitest run src/components/ChatPanel.test.tsx src/components/ChatPage.test.tsx` → FAIL.
- [ ] Implement. Run `npx vitest run`, `npm run lint`, `npm run typecheck` → PASS.
- [ ] `npm run build; npm run check:chat-size` → ≤ 204,800. Record the number for the learning note. **If over:** stop and tell the user; the fix (lazy loading) must then also make the size check count the panel chunk, or it only hides the bytes `[G3]`.
- [ ] Commit `feat(frontend): chat panel on the Chat Page`.

### Task 7: Finish (BOILERPLATE)

- [ ] Fix the stale comment `business/service.py:6` (hours_on is for Epic 5 slot math, not Epic 4).
- [ ] Update the spine ER (`ARCHITECTURE-SPINE.md:323`): `visitor_tokens ||--o{ conversations` and `customers ||--o{ conversations` instead of `customers ||--o{ visitor_tokens` `[G9]`. Update `docs/learning/architecture-map.md` (new `inbox` module, 4 tables) and `glossary.md` (visitor token, channel port, `seq`, idempotency, row lock, identity map).
- [ ] Full backend suite + coverage (`uv run pytest --cov`), full frontend suite. Manual check in the compose stack: send 2 Messages, reload, both still there; another browser sees none. **Traces visible:** find the `POST /api/v1/chat/{chat_slug}/messages` span in Grafana Cloud and check the body is not in it `[G17]`. Stop the stack after.
- [ ] Opus whole-branch review; fix findings; then `docs/agents/after-story.md`. Set sprint-status `done` on the branch before merge. PR body: note the "hash stored on first send" decision `[G17]`.

## Decisions made in this plan

- **Cookie on GET, row on first send.** AD-5 forbids writes on GET, and a row per page view (bots too) is waste. The DB still never holds the raw token. User approved 2026-11-22.
- **Per-Business hash** of one shared cookie, so tenants cannot be linked through the database.
- **`inbox` gets its own read route** (`GET /chat/{slug}/messages`). `business` may not import `inbox`. Story 4.2 grows it into the poll endpoint.
- **Identity lives in the adapter.** `Channel` has 2 methods only. `deliver` waits for the first outbound Message.
- **Two locks, fixed order:** the visitor-token row (a visitor's sends wait in line), then the Conversation row (AR-12 `seq`; staff replies in 4.4 take the same lock). Locked reads refresh the identity map (`populate_existing`).
- **IP limit (per Business) in the router, Conversation limit in the service after the duplicate check.**
- **No lazy loading** unless the size check fails; then the check must count the lazy chunk.
- **No generic "save module" on the frontend.** The send list has its own states (many in flight, retry by id). The planned save-module grilling stays open.
