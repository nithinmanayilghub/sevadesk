# Story 4.2 — Chat Page stays live by polling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, per CLAUDE.md §4: build in this session, stop after each CORE task, one Opus whole-branch review at the end). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Chat Page shows new Messages without a reload. It polls one endpoint with an opaque cursor. A poll with no change stops at Redis and never touches Postgres.

**Architecture:** The existing `GET /chat/{slug}/messages` becomes the one poll endpoint. It takes an optional `cursor` and returns only Messages after it, plus a snapshot (`conversation_state`) and a new cursor. Every commit that changes a Conversation raises a Redis counter `ver:<business_id>:<conversation_id>`; one `core` helper collects the changed Conversations in the session and raises their counters after commit. A **fast path** in the router answers "no change" from Redis only: a small Redis map (visitor hash → slug + conversation id, written only by the slow path) proves who the visitor is and which Conversation is theirs. Any doubt falls back to the **slow path** (the 4.1 code: slug → Business → cookie → Conversation in Postgres). The frontend gets one shared poll hook `usePoll` in `src/api/`; `ChatPanel` uses it.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2.1 (class-level session events `after_commit` / `after_rollback`; engine events `checkout` / `before_cursor_execute` in tests), redis-py, pytest + testcontainers; Next.js 16, React 19, Vitest (fake timers), openapi-fetch (`signal`).

**Spec:** `_bmad-output/planning-artifacts/epics.md:759-788` (Story 4.2, GitHub issue #18). Also AR-3 (`:96`), AR-6 (`:101`), AR-10 (`:105`), AR-12 (`:109`), AR-22 (`:121`), AR-23 (`:122`), UX-DR26 (`:161`), NFR-3 (`:80`), NFR-5 (`:82`); ARCHITECTURE-SPINE.md AD-3 (`:73`), AD-7 (`:94-106`).

**Review history:** an Opus plan review (2026-11-24) found 0 blockers, 4 major, 8 minor gaps. All 12 are fixed below (marked `[G#]`).

## Key decision (A; the user asked to go on with the plan, 2026-11-24)

**How a "no change" poll finds the Conversation without Postgres.**
- **A (chosen): a Redis map.** The server hashes the cookie with the cursor's Business id (the 4.1 per-Business hash) and reads `chat_visitor:<business_id>:<hash>` → `"<slug> <conversation_id>"`. Only the slow path writes this map, inside the slug's real tenant scope. So a hit whose slug equals the request slug proves the Business and the Conversation. **No new secret, no infra change.**
- B (rejected): an HMAC-signed cursor carrying the `conversation_id`. Needs a new secret env var in 4 places.

## Global Constraints

- New file `backend/app/core/versions.py` owns the counter `[G4]`. In `core` because later `bookings` (Epic 5, AD-7 "or its Booking") and `inbox` both must raise it, and `bookings` cannot import `inbox` (layers contract, `pyproject.toml`).
- Redis keys (AD-3 "purpose, then business_id"):
  - `ver:<business_id>:<conversation_id>` — integer. **No TTL.** Starts at a random number in `[2**32, 2**40)` (`SET NX`), never at 0 or 1 `[G2]`. So a lost key that comes back has a new random start, and an old client version almost never matches by chance.
  - `chat_visitor:<business_id>:<token_hash>` — text `f"{slug} {conversation_id}"`. TTL 86 400 s, refreshed by every slow-path poll. `token_hash` = `hash_token(f"{business_id}:{token}")` (the 4.1 hash).
- Cursor: text `f"v1.{business_id}.{after_seq}.{version}"`. Parsed with `re.fullmatch(r"v1\.([0-9a-f-]{36})\.(\d{1,9})\.(\d{1,15})", raw)` then `uuid.UUID(...)` inside `try/except ValueError` `[G8]`. Query param `cursor: str | None = Query(None, max_length=128)` `[G8]`. Anything that does not parse = no cursor → slow path, all Messages. The frontend never reads inside it.
- **Order rule (the core invariant):**
  1. The counter goes up only **after** commit. (Before commit, a poll could store the new version but not yet see the row, and the Message would never show.)
  2. The slow path reads (or seeds) the version **before** it reads the Messages. A send that commits in between leaves the client with an older version, so the next poll takes the slow path again.
  3. This needs READ COMMITTED (Postgres default): each statement sees the newest commits. Write this in a comment `[G5]`.
- New cursor's `after_seq` = `messages[-1].seq` if any Messages were listed, else `min(after_seq, conversation.last_seq)` `[G5]`. (Never "last_seq read earlier": it can be older than the newest listed row. `min` stops a forged high `after_seq` from hiding Messages.)
- A missing `ver` key: the slow path seeds it (`SET NX` random) and reads it back before the Messages `[G2]`. The fast path still never treats a missing key as "no change".
- Route (same path and `operation_id` as 4.1; new response shape):
  - `GET /api/v1/chat/{chat_slug}/messages?cursor=…` → `ChatPollOut`, operation_id `list_chat_messages`, responses 404, 429, 503.
- `ChatPollOut`: `changed: bool`, `messages: list[MessageOut]` (only after the cursor, oldest first; `[]` when `changed` is false), `snapshot: ChatSnapshot | None` (None when `changed` is false or no Conversation yet), `cursor: str | None` (None before the first Message; on "no change" it is `parsed.format()` `[G8]`).
- `ChatSnapshot`: `conversation_state: str` (`agent | handoff | closed`). `reply_pending` and Booking status come with Epic 6 / Epic 5.
- **Fast path, in this order** `[G3]` (no Postgres, no connection checkout):
  1. `parsed = ChatCursor.parse(cursor)` and `token = usable_token(cookie)`; both needed.
  2. Read the map for `(parsed.business_id, hash)` — NO tenant scope yet, nothing counted. Miss, bad value, or slug ≠ `chat_slug.lower()` → slow path.
  3. Now the Business id is proven. `with tenant_scope(parsed.business_id)`: hit the poll limiter (`counted = True`), read `ver`. Equal to `parsed.version` (and not None) → "no change".
  4. Else slow path.
- AD-3 note (comment in router + PR): the fast path's tenant comes from the visitor token (AD-3 source "visitor token / chat slug"), proven by a map entry that only the slug's own slow path writes.
- Slow path: `with chat_business_scope(session, chat_slug) as business` `[G9]` (404 for a bad slug); hit the limiter unless already `counted` (a counted fast path always proved the same Business, so a plain bool is enough); `after_seq = parsed.after_seq if parsed and parsed.business_id == business.business_id else 0`; `poll_messages`; write the map.
- Poll rate limit (AR-12, NFR-5), `AttemptLimiter`, fail closed: purpose `chat_poll:ip`, key `f"{business_id}:{client_ip(request)}"`, limit **600**, window/lock **60 s**. 429 code `too_many_polls`, message `Too many requests. Please wait a minute.`, header `Retry-After`. 503 message `Chat is not available right now. Please try again.`. A `RedisError` on any poll Redis read/write → that 503. Comment: no per-Conversation poll limit because a poll writes nothing and per IP meets AR-12; NFR-5's per-Conversation limit is on sends (4.1) `[G12]`.
- A failed counter bump after commit is logged (`logger.exception("conversation version bump failed")`, no PII) and swallowed.
- The poll never writes Postgres (AD-5). It may write Redis (map, version seed) and set the visitor cookie (4.1 rule).
- No `conversation_id` in any public input or output (AR-10).
- Frontend:
  - One shared poll hook `usePoll` in `frontend/src/api/usePoll.ts` (AR-3). No data-fetching library.
  - Interval 5000 ms while visible. Each poll gets its own `AbortController`, aborted by a plain `setTimeout` at 5000 ms (not `AbortSignal.timeout`: it ignores fake timers) `[G10]`; an abort is a failure. Next poll starts `max(0, 5000 - elapsed)` after the previous one ends. Never two at once.
  - Hidden tab: no new polls. Visible again: poll at once.
  - `enabled` turns false or unmount → abort the running poll and drop its answer (no callback after that) `[G10]`.
  - 3 failures in a row (429 and 5xx count) → banner `Reconnecting…` (`role="status"`). One success hides it.
  - `ChatPanel` polls only after the first load is `ready` AND (it has a cursor OR one local send is `sent`).
  - **One list, sorted by `seq`** `[G1]`: server Messages and this page's `sent` items (by `message.seq`) together; `sending` and `failed` items last, in send order.
  - Chat Page first load ≤ 204 800 bytes gzip. Plain elements only.
- Backend commands in WSL: `wsl --cd "C:\Books\DataSense Community\Seva Desk\backend" -e bash -lc "uv run …"`. Frontend in PowerShell: `npx vitest run …`, `npm run lint`, `npm run typecheck`. Docker Desktop must run.
- Regenerate types: WSL `uv run python -m app.export_openapi ../frontend/openapi.json`, then `npm run gen:api` in `frontend/`.
- Branch `story/4-2-chat-page-polling`. PR body ends with `Closes #18`.

## Review Focus

1. **A send commits between the poll's version read and its Message read** → next poll still sees it. Test: Task 2 `test_version_is_read_before_messages`.
2. **A forged cursor, or one from Business B on Business A's slug** → no data from B, no tenant scope from the raw cursor, no 500. Tests: Task 3 `test_forged_business_id_counts_nothing`, `test_cursor_from_other_business_is_ignored`, `test_bad_cursor_is_a_full_poll`.
3. **Old Conversations (no `ver` key) or a Redis restart** → one slow poll, then fast again (Neon can sleep). Tests: Task 1 `test_lost_key_gets_a_new_random_start`, Task 3 `test_missing_version_key_is_slow_once_then_fast`.
4. **A polled reply after the Customer's own send** → shows below it. Test: Task 5 `polled reply after own send shows below it`.
5. **A slow or hung poll on a bad network** → aborts at 5 s, next one starts; 3 → `Reconnecting…`. Test: Task 4 `aborts a slow poll and starts the next within 5 s`.

---

### Task 0: Branch housekeeping and Story Map (BOILERPLATE)

- [ ] `git switch -c story/4-2-chat-page-polling` from up-to-date `main`.
- [ ] `sprint-status.yaml`: `4-2-chat-page-stays-live-by-polling: in-progress`. Commit `chore: start story 4.2`.
- [ ] Give the user the Story Map (CLAUDE.md §2, max 5 bullets, one predict question) `[G11]`.

### Task 1: Conversation version counter (CORE)

**Files:**
- Create: `backend/app/core/versions.py`
- Modify: `backend/app/modules/inbox/service.py` (`receive_message`, new-Message branch)
- Test: `backend/tests/integration/test_conversation_versions.py`

**Interfaces:**
- Produces (all in `app.core.versions`):
  - `version_key(business_id: UUID, conversation_id: UUID) -> str` → `f"ver:{business_id}:{conversation_id}"`.
  - `mark_conversation_changed(session: Session, conversation_id: UUID) -> None` — adds `(current_business_id(), conversation_id)` to `session.info.setdefault("changed_conversations", set())`. Captures the Business NOW (the tenant scope ends before the commit).
  - Module-level `@event.listens_for(Session, "after_commit")` handler: pops the set; for each key, one pipeline `SET key <random> NX` + `INCR key`; `RedisError` → log, swallow. `@event.listens_for(Session, "after_rollback")`: drop the set. (A set: the same Conversation twice in one transaction bumps once.)
  - `read_or_seed_version(business_id, conversation_id) -> int` — `SET NX <random>` then `GET`; for the slow path. Raises `RedisError`.
  - `read_version(business_id, conversation_id) -> int | None` — `GET`; for the fast path. Raises `RedisError`.
  - Random start: `secrets.randbelow(2**40 - 2**32) + 2**32`.
- Comment in `versions.py`: the order rule, why after commit, why a random start, why no TTL, that callers in later stories (4.4 staff reply and handoff, Epic 5 Booking) call `mark_conversation_changed`.

- [ ] **Step 1: Write the failing tests** (reuse `client`, `shop`, `post` from `test_chat_messages.py`; read keys with `get_redis()`):
  - `test_send_bumps_version_after_commit` — after one send the key is an int ≥ 2**32; a second send (new id) → +1.
  - `test_duplicate_send_does_not_bump` — same `client_message_id` twice → unchanged.
  - `test_refused_send_does_not_bump` — monkeypatch `service.CHAT_SEND_CONVERSATION_LIMIT = 1`; 2nd send 429 → unchanged.
  - `test_bump_waits_for_commit` — in a `Session` + `tenant_scope`, `mark_conversation_changed`; key missing before `commit()`, present after.
  - `test_rollback_drops_the_mark` — mark, `rollback()`, then begin + commit an empty transaction → key still missing.
  - `test_lost_key_gets_a_new_random_start` — note value v; delete key; send again → new value ≠ v + 1 (and ≥ 2**32).
  - `test_bump_failure_is_logged_not_raised` — monkeypatch `versions.get_redis` (its own import name) to a client on port 1; send → 201; `caplog` has `conversation version bump failed`.
- [ ] **Step 2:** `uv run pytest tests/integration/test_conversation_versions.py -v` → FAIL.
- [ ] **Step 3:** Implement. `receive_message` calls `mark_conversation_changed(session, conversation.id)` on the new-Message branch only. Make sure `app.core.versions` is imported by `inbox.service` (so the listeners are registered).
- [ ] **Step 4:** Run this file + `tests/integration/test_chat_messages.py` → PASS.
- [ ] **Step 5:** Commit `feat(core): raise a Conversation version after each commit that changes it`.
- [ ] **CHECKPOINT** (CORE): explain after-commit vs before-commit in 3 lines.

### Task 2: Poll response and slow path (CORE)

**Files:**
- Modify: `backend/app/modules/business/dependencies.py` (add `chat_business_scope`; update header comment) `[G9]`
- Modify: `backend/app/modules/inbox/schemas.py` (replace `ChatMessagesOut` with `ChatSnapshot`, `ChatPollOut`; add `ChatCursor`)
- Modify: `backend/app/modules/inbox/repository.py` (`MessageRepository.list_after`)
- Modify: `backend/app/modules/inbox/service.py` (`list_messages` → `poll_messages`)
- Modify: `backend/app/modules/inbox/webchat.py` (`remember_conversation`)
- Modify: `backend/app/modules/inbox/router.py` (`list_chat_messages`)
- Modify (old tests, new shape) `[G6]`: `test_chat_messages.py:55,75` and `:153` (schema list → `SendMessageIn, MessageOut, ChatPollOut, ChatSnapshot`), `test_tenant_isolation.py:259`
- Test: `backend/tests/unit/test_chat_cursor.py`, `backend/tests/integration/test_chat_poll.py`
- Regenerate: `frontend/openapi.json`, `frontend/src/api/schema.d.ts`

**Interfaces:**
- Produces:
  - `business.dependencies.chat_business_scope(session: Session, chat_slug: str) -> ContextManager[ChatBusiness]` — `find_chat_business` + `tenant_scope`. `chat_business_in_tenant_scope` uses it too, so there is still one way to turn a slug into a scope.
  - `ChatCursor(business_id: UUID, after_seq: int, version: int)` frozen dataclass: `format() -> str`, `@classmethod parse(raw: str | None) -> ChatCursor | None`.
  - `MessageRepository.list_after(conversation_id, after_seq: int) -> list[Message]` (`seq > after_seq`, by `seq`).
  - `service.poll_messages(session, channel: Channel, after_seq: int) -> tuple[ChatPollOut, UUID | None]` — order: `find_conversation`; none → `(ChatPollOut(changed=True, messages=[], snapshot=None, cursor=None), None)`. Else `read_or_seed_version` FIRST, then `list_after`; new `after_seq` per the Global rule; cursor with that version. `RedisError` → 503 AppError.
  - `WebchatChannel.remember_conversation(slug: str, conversation_id: UUID) -> None` — `SET chat_visitor:<bid>:<hash> "<slug> <cid>" EX 86400`.
  - Router `list_chat_messages(chat_slug: str, request: Request, response: Response, session: SessionDep, cookie: VisitorTokenCookie = None, cursor: str | None = Query(None, max_length=128))` `[G9]`. No `ChatBusinessDep`. This task: slow path only (the Global "Slow path" bullet), without the limiter yet.

- [ ] **Step 1: Unit tests** `test_chat_cursor.py`: `test_round_trip`; `test_bad_cursors_are_none` over `None`, `""`, `"v2.…"`, a trailing `"\n"` after a good cursor, 36 dashes as the id, a non-UUID id, a negative seq, a missing part.
- [ ] **Step 2: Integration tests** `test_chat_poll.py`:
  - `test_first_poll_returns_all_and_a_cursor` — 2 sends; poll without cursor → `changed` true, seqs `[1, 2]`, `snapshot == {"conversation_state": "agent"}`, cursor not None.
  - `test_poll_with_cursor_returns_only_new` — poll, 1 more send, poll with cursor → seqs `[3]`.
  - `test_no_conversation_has_no_cursor` — fresh browser → `{"changed": True, "messages": [], "snapshot": None, "cursor": None}`.
  - `test_version_is_read_before_messages` — class-level monkeypatch of `MessageRepository.list_after` that first `INCR`s the key, then calls the real one; returned cursor version ≠ the Redis value.
  - `test_cursor_after_seq_is_the_last_listed_seq` — monkeypatch `list_after` to insert one more Message via a second session (commit) before the real query; the cursor's `after_seq` equals the last returned seq.
  - `test_forged_high_after_seq_still_sees_new_messages` — cursor with `after_seq = 999999999` → no Messages now; after a send, the next poll shows it.
  - `test_poll_writes_no_database_rows` — counts of `VisitorToken`, `Conversation`, `Message` unchanged across a poll (AD-5).
- [ ] **Step 3:** Run → FAIL.
- [ ] **Step 4:** Implement. Update the old tests `[G6]`.
- [ ] **Step 5:** Run unit + `test_chat_poll.py` + `test_chat_messages.py` + `test_tenant_isolation.py` + `test_chat_page.py` → PASS.
- [ ] **Step 6:** Regenerate `openapi.json` + `schema.d.ts`; `npm run typecheck` (ChatPanel reads only `data.messages`; fix types only if needed).
- [ ] **Step 7:** Commit `feat(inbox): poll returns new Messages, a snapshot, and a cursor`.
- [ ] **CHECKPOINT** (CORE): explain the order rule with a 3-row timeline.

### Task 3: Fast "no change" path and poll limit (CORE)

**Files:**
- Modify: `backend/app/modules/inbox/router.py`, `service.py` (limiter, `TooManyPolls`, `unchanged`), `webchat.py` (`cached_conversation`)
- Test: `backend/tests/integration/test_chat_poll.py`, `test_tenant_isolation.py`

**Interfaces:**
- Consumes: Task 1 `read_version`; Task 2 `ChatCursor`, `poll_messages`, `remember_conversation`, `chat_business_scope`.
- Produces:
  - `service.chat_poll_ip_limiter() -> AttemptLimiter` (`"chat_poll:ip"`, `CHAT_POLL_IP_LIMIT = 600`, `CHAT_POLL_WINDOW_SECONDS = 60`); `class TooManyPolls(AppError)`.
  - `WebchatChannel.cached_conversation(business_id: UUID, slug: str) -> UUID | None` — hash with the GIVEN id (no tenant scope needed), `GET` the map; None if missing, malformed, or slug differs `[G3]`.
  - `service.unchanged(conversation_id: UUID, version: int) -> bool` — inside the tenant scope; `read_version(...)` is not None and equals `version`.
  - Router: the Global fast-path order, then the slow path. Header comment: fast vs slow in 4 lines, the AD-3 note, why no `ChatBusinessDep`.

- [ ] **Step 1: Tests** (add to `test_chat_poll.py`). A helper counts both `event.listen(get_engine(), "checkout", …)` and `"before_cursor_execute"` `[G7]`:
  - `test_no_change_poll_skips_postgres` — poll for a cursor; poll again → `{"changed": False, "messages": [], "snapshot": None, "cursor": <same>}`, **0** checkouts and **0** statements.
  - `test_change_after_send_takes_slow_path` — after a send, old cursor → the new Message.
  - `test_missing_version_key_is_slow_once_then_fast` — delete `ver`; poll with cursor → slow (`changed` true); poll with the new cursor → 0 checkouts `[G2]`.
  - `test_forged_business_id_counts_nothing` — cursor with a random Business id → slow path for the slug; no `chat_poll:ip:<random id>:*` key in Redis `[G3]`.
  - `test_cursor_from_other_business_is_ignored` — browser chats in A and B; A's slug with B's cursor → A's Messages from seq 1.
  - `test_cursor_with_another_cookie_is_slow` — browser 2 with browser 1's cursor → `messages == []`.
  - `test_bad_cursor_is_a_full_poll` — `cursor=garbage` → 200, all Messages; `cursor` of 200 chars → 422.
  - `test_poll_limit_returns_429` — `CHAT_POLL_IP_LIMIT = 2`; 3rd poll → 429, `too_many_polls`, `Retry-After`. Once on the fast path, once without cursor.
  - `test_poll_fails_closed_without_redis` — `REDIS_URL` port 1 → 503.
  - `test_unknown_slug_is_not_found` (existing) passes with and without a cursor.
  - Isolation: extend `check_list_chat_messages` — A's slug with B's cursor → A's empty shape.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Full backend suite with coverage (`uv run pytest --cov`, gate as in CI) + `uv run lint-imports` + ruff → PASS `[G11]`.
- [ ] **Step 5:** Regenerate `openapi.json` + `schema.d.ts`. Commit `feat(inbox): "no change" polls stop at Redis; poll rate limit`.
- [ ] **CHECKPOINT** (CORE): walk one fast-path poll step by step.

### Task 4: The shared poll hook (STANDARD)

**Files:**
- Create: `frontend/src/api/usePoll.ts`, `frontend/src/api/usePoll.test.ts`

**Interfaces:**
- Produces: `usePoll(poll: (signal: AbortSignal) => Promise<boolean>, options: { enabled: boolean; intervalMs?: number }): { reconnecting: boolean }`. `true` = success; `false` or a throw = failure. Newest `poll` kept in a ref. Default `intervalMs` 5000. `FAILS_BEFORE_BANNER = 3`. A poll whose `enabled`/mount ended is aborted and its result ignored.

- [ ] **Step 1: Tests** (`vi.useFakeTimers()`, `vi.advanceTimersByTimeAsync`, `renderHook`, mock `poll`; set `document.visibilityState` with `Object.defineProperty`, dispatch `visibilitychange`) `[G10]`:
  - `polls every 5 s while visible` — 0 calls at start, 1 at 5000 ms, 2 at 10 000 ms.
  - `never runs two polls at once` — a poll that resolves at 3 s; the next starts at 5 s.
  - `aborts a slow poll and starts the next within 5 s` — never-resolving poll: signal aborted 5000 ms after start; next call by 10 000 ms total.
  - `stops while hidden and polls at once when visible`.
  - `shows reconnecting after 3 failures and hides it after a success`.
  - `disable while in flight aborts and drops the answer` — the poll's signal is aborted; no new calls.
  - `does nothing while disabled`, `stops after unmount`.
- [ ] **Step 2:** `npx vitest run src/api/usePoll.test.ts` → FAIL.
- [ ] **Step 3:** Implement (one `setTimeout` chain, one `AbortController` per poll, a `visibilitychange` listener). Header comment lists the rules.
- [ ] **Step 4:** Run → PASS. Commit `feat(frontend): one shared poll hook`.

### Task 5: ChatPanel goes live (STANDARD)

**Files:**
- Create: `frontend/src/lib/chatPoll.ts`, `chatPoll.test.ts`
- Modify: `frontend/src/components/ChatPanel.tsx`, `ChatPanel.test.tsx`

**Interfaces:**
- Consumes: Task 4 `usePoll`; `components["schemas"]["ChatPollOut"]`.
- Produces:
  - `mergePoll(current: ChatPollOut, next: ChatPollOut): ChatPollOut` — `next.changed` false → `current` (same object). Else messages = current + next's with `seq` > the last current `seq`; `cursor = next.cursor`; `snapshot = next.snapshot ?? current.snapshot`.
  - `chatItems(saved: MessageOut[], sent: Sent[])` (in `chatPoll.ts`) `[G1]` — one list: saved Messages not sent by this page + `sent` items with `status === "sent"`, sorted by `seq`; then `sending`/`failed` items in send order.

- [ ] **Step 1: Tests**:
  - `chatPoll.test.ts`: no change keeps current; new Messages append; a repeated seq is not added twice; cursor/snapshot take new values; `chatItems` sorts by seq and puts sending/failed last.
  - `ChatPanel.test.tsx` (fake timers, mocked `api.GET`):
    - `shows a new Message from a poll` — first GET has a cursor; at 5 s the GET with `query: { cursor }` returns an `agent` Message → it shows.
    - `polled reply after own send shows below it` `[G1]` — send gets seq 1; poll returns the agent seq 2 → DOM order: Customer, then agent.
    - `does not poll before the chat exists` — first GET `cursor: null`, no sends → no second GET in 20 s.
    - `starts polling after the first send`.
    - `shows Reconnecting… after 3 failed polls, then hides it`.
    - `own sent Message is not shown twice when the poll returns it`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement: keep `useLoad` for the first load. `usePoll` with `enabled = state.status === "ready" && (state.data.cursor !== null || sent.some((s) => s.status === "sent"))`. The poll reads the newest cursor from a ref, calls `api.GET(..., { params: { path, query: { cursor } }, signal })`, and on `data.changed` calls `state.replace((current) => mergePoll(current, data))`. (A timer callback is not a child's effect, so `replace` is allowed; `usePoll` drops answers after disable/unmount, so an old slug's data cannot merge.) Banner `<p role="status">Reconnecting…</p>` above the log. Render `chatItems(...)`. Update the header comment.
- [ ] **Step 4:** `npx vitest run`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm run check:chat-size` → PASS (≤ 204 800 bytes).
- [ ] **Step 5:** Commit `feat(chat): the Chat Page shows new Messages by polling`.

### Task 6: Docs, checks, review, finish

- [ ] Docs: `docs/learning/architecture-map.md` (poll flow, fast vs slow, the 2 Redis keys); `docs/learning/glossary.md` (cursor, version counter, fast path, `after_commit`, READ COMMITTED); ARCHITECTURE-SPINE AD-7 one line on decision A.
- [ ] Manual check in docker compose: send from the page; insert an `agent` Message with SQL and `INCR` its `ver` key; it shows within 5 s, below the Customer's Message. Hide the tab → no polls in DevTools Network.
- [ ] NFR-3 before merge `[G11]`: in local compose, 100 "no change" polls with `curl -w "%{time_total}\n"` (cookie + cursor); p95 < 0.5 s. After merge: same loop on demo; record both in the learning note; if > 0.5 s on demo, open a bug issue.
- [ ] Traces `[G11]`: in Grafana Cloud find one fast-path poll span (no DB child span) and one slow-path span. Note the extra volume (1 span + 1 access log per 5 s per open tab) against the free tier in the learning note; if it is a problem, open an issue (do not sample in this story).
- [ ] Opus whole-branch review; fix findings with regression tests. Then `docs/agents/after-story.md`. Sprint-status `done` on the branch before merge. PR body: decision A, the order rule, the AD-3 note, "no poll before a Conversation exists" (another tab of the same browser sees a first Message only after reload), and the Known limits. Ends with `Closes #18`.

## Known limits (accepted, written in the PR)

- If the bump fails after a commit, open pages miss that change until the next change or a reload (logged).
- The cursor is not tied to a Conversation. Fine while a visitor has one Conversation; a later story that starts a new one after `closed` must reset `after_seq` (compare the map's Conversation).
- `ver` and `chat_visitor` keys stay after a Customer delete until Story 4.5 deletes them.
