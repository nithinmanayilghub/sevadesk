# Story 4.3 — Inbox lists all Conversations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, per CLAUDE.md §4: build in this session, stop after each CORE task, one Opus whole-branch review at the end). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Owner and Staff open `/app/inbox` and see every Conversation, Needs Human first, then newest activity first. The list stays live by polling, pages with "Load more", and the Inbox tab shows a red count of Needs Human Conversations.

**Architecture:** A new column `conversations.last_message_at` holds the time of the newest Message; `receive_message` sets it. One index `(business_id, (state = 'handoff') DESC, last_message_at DESC, id DESC)` serves the list order, the keyset page (a "keyset cursor": the sort key of the last row shown; the next page starts after it), and the count. Two new logged-in routes in `inbox`: the list page and the Needs Human count. Both check `USE_INBOX_AND_BOOKINGS` and share one per-member poll limit. The frontend gets `InboxList` (load, poll, Load more) in a two-pane Inbox layout, and the `/app` layout polls the count for the shell.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2.1 (`tuple_` row compare, `literal_column`), Alembic, psycopg 3, redis-py, pytest + testcontainers; Next.js 16, React 19, Vitest, openapi-fetch, lucide-react, `Intl.DateTimeFormat.formatToParts`.

**Spec:** `_bmad-output/planning-artifacts/epics.md:790-825` (Story 4.3, GitHub issue #19). Also FR-23 (`:60`), FR-24 (`:61`), UX-DR4 (`:135`), UX-DR6 (`:137`), UX-DR11 (`:142`), UX-DR16 (`:149`), UX-DR17 (`:150`), UX-DR24 (`:159`), UX-DR25 (`:160`), NFR-6 (360px); ARCHITECTURE-SPINE.md AD-7 (`:94-107`, "Poll endpoints are rate-limited"), AD-10 (`:138`); EXPERIENCE.md `:56` (time/date copy), `:75`, `:84`, `:93`, `:103`, `:110`.

**Review history:** an Opus plan review (2026-11-25) found 0 blockers, 6 major, 9 minor gaps. All 15 are fixed below (marked `[G#]`).

## Global Constraints

- **No Customer name or phone yet.** `customers` has neither column (`inbox/models.py:1-5`). Every row shows "New visitor". The story that collects them adds the field. Do not add columns now.
- **Badges (UX-DR6, AD-10):** `agent` → "Agent" (brand/emerald, `Bot` icon). `handoff` → "Needs Human" (`text-status-handoff`, `Hand` icon). `closed` → "Closed" (zinc/muted, `CircleCheck` icon). Text + icon always; never color alone. "Booking Request" / "Expired" come with Epic 5.
- **Order:** `state = 'handoff'` first, then `last_message_at DESC`, then `id DESC` (a tie-breaker, so two rows with the same time never swap or repeat between pages).
- **One pinned expression `[G5]`:** `PINNED = Conversation.state == literal_column("'handoff'")` in `inbox/repository.py`, used in the row compare, the ORDER BY, and the count. Why: a bound parameter (`state = $1`) cannot match the index expression `(state = 'handoff')` once psycopg 3 prepares the query (after 5 runs) and Postgres picks a generic plan. The model `Index` text and the migration DDL text are identical: `text("(state = 'handoff') DESC")`, `text("last_message_at DESC")`, `text("id DESC")`.
- **Page size:** default 20. `limit` query param: `ge=1, le=100`.
- **Cursor text:** `f"v1.{int(pinned)}.{micros}.{conversation_id}"`, where `micros` = whole microseconds since 1970-01-01 UTC (`(ts - EPOCH) // timedelta(microseconds=1)`, no floats). Parse with `re.fullmatch(r"v1\.([01])\.(\d{1,17})\.([0-9a-f-]{36})", raw)`, then `uuid.UUID(...)` in `try/except ValueError`. A cursor that does not parse → 422 code `invalid_cursor`, message "This list is out of date. Reload the page." Query param `cursor: str | None = Query(None, max_length=128)`.
- **Preview:** `" ".join(body.split())[:120]` — one line, at most 120 code points. It can split a Devanagari conjunct (क्ष) at the edge; that is fine, because CSS `truncate` hides the end on screen anyway `[G14]`.
- **Time and date (UX-DR4, EXPERIENCE.md:56) `[G1]`:** in the **Business timezone**, never the viewer's. `InboxPage.timezone` carries it (`businesses.timezone`, default `Asia/Kolkata`). Same Business-local day as now → "10:42 am"; same year → "Tue, 4 Nov"; older → "Tue, 4 Nov 2025".
- **Routes** (both `ActorDep`, both 401/403/429/503 in `responses`):
  - `GET /api/v1/inbox/conversations?cursor=&limit=` → `InboxPage`, operation_id `list_inbox_conversations` (also 422).
  - `GET /api/v1/inbox/needs-human-count` → `NeedsHumanCount`, operation_id `count_needs_human`.
- **Poll limit (AD-7) `[G4]`:** one `AttemptLimiter` for both routes: purpose `inbox_poll`, key `f"{business_id}:{membership_id}"`, `INBOX_POLL_LIMIT = 120` per `INBOX_POLL_WINDOW_SECONDS = 60` (one tab polls 2 routes every 5 s = 24 per minute; room for 5 tabs; a lockout lasts at most 60 s, like the chat poll, `chat_poll.py:31-32`). Message "The inbox is busy. Please try again in a minute." Error class `TooManyInboxPolls(AppError)`: 429, code `too_many_requests`, `Retry-After` header `[G14]`. Redis down → 503 (fail closed, like the other limiters).
- **Copy (exact):** empty "No conversations yet. Share your chat link to get your first customer." + button "Copy link" (`CopyChatLinkButton`). Right pane placeholder (desktop only): "Pick a conversation to read it." Open-conversation placeholder `[G13]`: "This conversation opens here soon." Load more button "Load more" / "Loading…"; its error "Could not load more. Try again." Poll banner after 3 fails: "Reconnecting…" (from `usePoll`). First-load failure: `LoadFailed` (its own copy and "Try again") `[G2]`.
- **Two panes `[G3]` `[G9]`:** `inbox/layout.tsx` owns `<main>` and `<h1>Inbox</h1>`. Below `lg`: `flex flex-1 flex-col`, the list only. From `lg` (1024px): grid `lg:grid-cols-[22rem_1fr]`, list left, `{children}` right. The list section has `min-w-0`; AppShell's content div gets `min-w-0` too, so a long preview never makes the page scroll sideways at 360px.
- **Rows link to** `/app/inbox/{conversation_id}`. A one-line placeholder page there `[G13]`; Story 4.4 replaces it. `canOpen` already allows sub-pages of `/app/inbox`.
- **Skeleton:** 5 rows of `animate-pulse rounded-lg bg-muted` (the codebase skeleton style; no shadcn `Skeleton` component is installed), inside `aria-busy="true" aria-label="Loading"`.
- **Tests:** backend in WSL: `wsl --cd "C:\Books\DataSense Community\Seva Desk\backend" -e bash -lc "uv run pytest …"` (call `wsl` from PowerShell). Frontend in PowerShell: `npx vitest run …` (`--maxWorkers=2` on low RAM). In frontend tests, check effect results with `vi.waitFor`. Mock `@/api/client` the way `ServicesSettings.test.tsx` does.
- **Regenerate types** after any schema change: WSL `uv run python -m app.export_openapi ../frontend/openapi.json`, then `npm run gen:api` in `frontend/`.
- **Lint commands `[G14]`:** `uv run ruff check .`, `uv run ruff format --check .`, `uv run lint-imports`.

## Review Focus

1. **Two Conversations with the same `last_message_at`** (same microsecond, or the same transaction) — paging must not repeat or skip one. Pinned by `test_pages_never_repeat_or_skip` (Task 2), which forces equal times.
2. **A Conversation that moves while the User pages** (a new Message lifts it to the top) — Load more must not crash or show it twice. `appendPage` drops ids already on screen (Task 5 test `appendPage drops rows already shown`).
3. **Load more and a poll at the same time** — the poll answer (top N with the OLD N) would wipe the page just added. `InboxList` turns polling off while Load more runs (`usePoll` drops the in-flight answer). Pinned by `a poll does not wipe a page Load more just added` (Task 5).
4. **A Technician-only User** — the shell must not poll the count (it would get 403 every 5 s). Pinned by `useNeedsHumanCount does not fetch when disabled` (Task 6) and the layout test for a Technician-only `/me`.
5. **A message near midnight** — 23:30 UTC is already the next day in IST; the row must show the Business-local date. Pinned by `formatListTime uses the Business timezone` (Task 4) `[G1]`.

---

### Task 0: Branch and Story Map (BOILERPLATE) `[G6]`

- [x] `story/4-3-inbox-list` from up-to-date `main` (done).
- [ ] `sprint-status.yaml`: `4-3-inbox-lists-all-conversations: in-progress`. Commit `chore: start story 4.3` (with the plan file).
- [ ] Give the user the Story Map (CLAUDE.md §2, max 5 bullets, one predict question).

---

### Task 1: `last_message_at` on Conversations (CORE: data model)

**Files:**
- Create: `backend/migrations/versions/0010_conversation_last_message_at.py`
- Modify: `backend/app/modules/inbox/models.py` (Conversation), `backend/app/modules/inbox/service.py` (`receive_message`, step 4)
- Test: `backend/tests/integration/test_inbox_service.py`, `backend/tests/integration/test_migrations.py`

**Interfaces:**
- Produces: `Conversation.last_message_at: Mapped[datetime]` (timestamptz, NOT NULL, `server_default=func.now()`); index `ix_conversations_inbox_order` (texts in Global Constraints), in the model's `__table_args__` and in the migration.

- [ ] **Step 1: Write the failing tests.** In `test_inbox_service.py` (reuse its `send` helper):
  - `test_last_message_at_follows_the_newest_message` — two sends; `conversation.last_message_at == second.created_at`.
  - `test_retry_leaves_last_message_at_unchanged` `[G12]` — send, read the time, send again with the SAME `client_message_id`; the time is the same.
  - `test_last_message_at_never_moves_back` `[G12]` — set `last_message_at` to `'2099-01-01'` by direct SQL, send; it stays `2099-01-01`.

  In `test_migrations.py`, `test_0010_backfills_last_message_at(migrated_db)` `[G7]`, the shape of `test_upgrade_gives_old_businesses_a_slug` (`:51`):
  1. `command.downgrade(config, "0009")`.
  2. One `get_engine().begin()` block of raw INSERTs with explicit `gen_random_uuid()`-free UUIDs made in Python: a business (with every NOT NULL column 0009 has, e.g. `chat_slug`), a customer, a visitor token (`token_hash = 'h'`), conversation C1 with 2 messages (`seq` 1 and 2, `author_type='customer'`, `lang='en'`, `body='hi'`, `created_at` `'2026-01-01 10:00+00'` and `'2026-01-02 10:00+00'`), and conversation C2 with `created_at = '2026-03-01 10:00+00'` and no messages.
  3. `command.upgrade(config, "head")`.
  4. Assert C1's `last_message_at = '2026-01-02 10:00+00'` and C2's `= '2026-03-01 10:00+00'`.
- [ ] **Step 2:** run them → FAIL (column missing).
- [ ] **Step 3: Implement.** Migration 0010 (`down_revision = "0009"`): add the column nullable; `UPDATE conversations c SET last_message_at = COALESCE((SELECT max(m.created_at) FROM messages m WHERE m.business_id = c.business_id AND m.conversation_id = c.id), c.created_at)`; then `alter_column(nullable=False, server_default=sa.func.now())`; then create the index. Downgrade drops the index, then the column. In `receive_message` step 4, after `session.refresh(row)`: `conversation.last_message_at = max(conversation.last_message_at, row.created_at)`, with a comment: `now()` is the time the transaction STARTED, so a send that started earlier can commit later; `max` keeps the time from going back. Comment on the model column: "Set by every new Message (customer now; user/agent replies in 4.4 / Epic 6 must set it too)."
- [ ] **Step 4:** run `tests/integration/test_inbox_service.py tests/integration/test_migrations.py tests/integration/test_tenant_schema.py tests/integration/test_inbox_tables.py` → PASS.
- [ ] **Step 5: Commit** `feat(inbox): conversations.last_message_at for the Inbox order`.

**CHECKPOINT (CORE).**

---

### Task 2: `GET /api/v1/inbox/conversations` (CORE: query, keyset paging, Roles, isolation)

**Files:**
- Modify: `backend/app/modules/inbox/schemas.py`, `repository.py`, `service.py`, `router.py`; `backend/app/modules/business/service.py` (+ `inbox_facts`; `get_setup` reuses the same repository read)
- Create: `backend/tests/integration/test_inbox_list.py`, `backend/tests/unit/test_inbox_cursor.py`
- Modify: `backend/tests/integration/test_tenant_isolation.py`

**Interfaces:**
- Consumes: Task 1 column and index; `accounts_service.require_roles(actor, Permission.USE_INBOX_AND_BOOKINGS)`.
- Produces:
  - `schemas.InboxCursor` (frozen dataclass): `pinned: bool`, `last_message_at: datetime`, `conversation_id: uuid.UUID`; `format() -> str`; `classmethod parse(raw: str) -> InboxCursor | None`.
  - `schemas.preview(body: str) -> str`.
  - `schemas.InboxRow`: `conversation_id: uuid.UUID`, `state: Literal["agent", "handoff", "closed"]`, `last_message_preview: str`, `last_message_at: datetime`.
  - `schemas.InboxPage`: `conversations: list[InboxRow]`, `next_cursor: str | None`, `chat_slug: str`, `timezone: str` `[G1]`.
  - `repository.PINNED` (Global Constraints). `ConversationRepository.inbox_page(after: InboxCursor | None, limit: int) -> list[tuple[Conversation, Message]]` — one query; joins the newest Message on `(business_id, conversation_id, seq = last_seq)`; row compare `tuple_(PINNED, last_message_at, id) < tuple_(...)`; order all three DESC; `.limit(limit + 1)` (the extra row only says "there is a next page").
  - `service.list_inbox(session, actor, cursor: str | None, limit: int) -> InboxPage`.
  - `business.service.inbox_facts(session) -> InboxFacts` (a small dataclass in `business/schemas.py`: `chat_slug: str`, `timezone: str`), one read of the current Business `[G1]`.

- [ ] **Step 1: Write the failing tests.** Unit (`test_inbox_cursor.py`): `test_cursor_round_trips` (format → parse gives an equal object, microseconds kept); `test_bad_cursor_is_none` for `"", "v2.1.5.<uuid>", "v1.2.5.<uuid>", "v1.1.5.not-a-uuid", "v1.1.5.<uuid>\n"`; `test_preview_is_one_short_line` (`"a\n\n b"` → `"a b"`; 300 × "क" → length 120).

  Integration (`test_inbox_list.py`; helper `send(business_id, token, body)` as in `test_inbox_service.py`, and `set_state(conversation_id, state)` / `set_last_message_at(conversation_id, ts)` by direct SQL). Before each CORE test, tell the user its one-line behaviour:
  - `test_newest_activity_first` — 3 visitors send in order a, b, c; then a sends again → order `[a, c, b]`.
  - `test_handoff_pinned_on_top` — the oldest one set to `handoff` comes first.
  - `test_row_shape` — `{conversation_id, state: "agent", last_message_preview: "Fan not working", last_message_at}`; `chat_slug` equals `/api/v1/setup`'s slug; `timezone == "Asia/Kolkata"`.
  - `test_pages_never_repeat_or_skip` — 25 Conversations, 3 of them forced to the SAME `last_message_at`, 2 set to `handoff`; `limit=10` pages → 10, 10, 5; `next_cursor` is None on the last; all 25 ids, each once, same order as one `limit=100` call.
  - `test_list_uses_the_inbox_index` `[G5]` — in one transaction: `SET LOCAL enable_seqscan = off`, then run the list query 6 times through the repository (past psycopg's prepare threshold), then `EXPLAIN` the compiled statement of the 7th; the plan text contains `ix_conversations_inbox_order`.
  - `test_bad_cursor_is_422` — `cursor=junk` → 422, code `invalid_cursor`.
  - `test_limit_out_of_range_is_422` — `limit=0` and `limit=101` → 422.
  - `test_empty_inbox` — `{"conversations": [], "next_cursor": None, "chat_slug": <slug>, "timezone": "Asia/Kolkata"}`.
  - `test_staff_may_list`, `test_technician_gets_403` (use `set_owner_roles`).

  Isolation: `check_list_inbox` — B's visitor sends, A's list is empty; A's visitor sends, A sees only A's id; add `("GET", "/api/v1/inbox/conversations"): check_list_inbox`.
- [ ] **Step 2:** run → FAIL (404 route / ImportError).
- [ ] **Step 3: Implement** in the files above. `list_inbox`: Role check first; `InboxCursor.parse` (None for a given cursor → raise `AppError("invalid_cursor", …, 422)`); fetch `limit + 1`; `next_cursor` from row `limit - 1` only when `limit + 1` came back. Router: `cursor: Annotated[str | None, Query(max_length=128)] = None`, `limit: Annotated[int, Query(ge=1, le=100)] = 20`. Header comment in `router.py`: the new logged-in Inbox routes.
- [ ] **Step 4:** run `tests/unit/test_inbox_cursor.py tests/integration/test_inbox_list.py tests/integration/test_tenant_isolation.py` → PASS. Then `uv run ruff check .` and `uv run lint-imports` → clean.
- [ ] **Step 5: Commit** `feat(inbox): GET /inbox/conversations with keyset pages`.

**CHECKPOINT (CORE).**

---

### Task 3: Needs Human count + the poll limit (STANDARD)

**Files:**
- Modify: `backend/app/modules/inbox/repository.py`, `service.py`, `router.py`, `schemas.py`
- Test: `backend/tests/integration/test_inbox_list.py`, `test_tenant_isolation.py`

**Interfaces:**
- Produces: `schemas.NeedsHumanCount`: `count: int`. `ConversationRepository.count_needs_human() -> int` (uses `PINNED`). `service.count_needs_human(session, actor) -> NeedsHumanCount`. `service.inbox_poll_limiter() -> AttemptLimiter`; `service.TooManyInboxPolls`. Both routes call one router helper `_count_poll(actor)` that hits the limiter with `f"{actor.business_id}:{actor.membership_id}"` (`Actor`, `accounts/schemas.py:92`). It runs before the service's queries (ActorDep has already read the session and membership) `[G14]`. The Role check stays in the service.

- [ ] **Step 1: Write the failing tests:** `test_count_needs_human` (2 handoff, 1 agent → `{"count": 2}`); `test_technician_count_is_403`; `test_inbox_poll_limit` (monkeypatch `INBOX_POLL_LIMIT` to 2: the third call to either route → 429 with `Retry-After`); `test_inbox_redis_down_is_503` `[G2]` (make the limiter's Redis raise `redis.RedisError`, the way `test_chat_poll.py` does → both routes 503); isolation `check_count_needs_human` (B has 1 handoff, A's count is 0) + dict row.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** with the Global Constraints values.
- [ ] **Step 4:** run `tests/integration/test_inbox_list.py tests/integration/test_tenant_isolation.py` → PASS.
- [ ] **Step 5:** regenerate `frontend/openapi.json` and `frontend/src/api/schema.d.ts`. **Commit** `feat(inbox): Needs Human count and the inbox poll limit`.

---

### Task 4: Badge and list-time helpers (STANDARD)

**Files:**
- Modify: `frontend/src/lib/time.ts` (+ `time.test.ts`)
- Create: `frontend/src/components/StatusBadge.tsx` (+ `StatusBadge.test.tsx`)

**Interfaces:**
- Produces: `formatListTime(iso: string, now: Date, timeZone: string): string` `[G1]`. Build the parts with `new Intl.DateTimeFormat("en-GB", { timeZone, year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", hourCycle: "h23" }).formatToParts(...)` (numbers only, stable across browsers and Node), then write the text by hand with the existing `formatTime` and the `WEEKDAYS` / `MONTHS` lists. The weekday comes from `Date.UTC(year, month - 1, day)` of the Business-local parts. `StatusBadge({ state }: { state: InboxRow["state"] })`.

- [ ] **Step 1: Tests** (fixed UTC instants, `timeZone = "Asia/Kolkata"`):
  - same IST day: iso `2026-11-25T05:12:00Z`, now `2026-11-25T10:00:00Z` → "10:42 am".
  - `formatListTime uses the Business timezone`: iso `2026-11-24T23:30:00Z` (= 25 Nov 05:00 IST), now `2026-11-25T10:00:00Z` → "5:00 am" (same IST day), and with now `2026-11-26T10:00:00Z` → "Wed, 25 Nov".
  - earlier this year: iso `2026-11-04T06:00:00Z` → "Wed, 4 Nov"; last year: iso `2025-12-04T06:00:00Z` → "Thu, 4 Dec 2025".
  - `StatusBadge` renders "Agent", "Needs Human", "Closed", each with an `aria-hidden` svg.
- [ ] **Step 2:** `npx vitest run src/lib/time.test.ts src/components/StatusBadge.test.tsx` → FAIL.
- [ ] **Step 3: Implement.** `StatusBadge`: `rounded-full` pill, label typography; a `Record<state, {label, icon, className}>` so a new state is a type error.
- [ ] **Step 4:** same command → PASS.
- [ ] **Step 5: Commit** `feat(frontend): status badge and list time`.

---

### Task 5: The Inbox list in two panes (CORE: poll + page merge)

**Files:**
- Create: `frontend/src/lib/inboxList.ts` (+ `.test.ts`), `frontend/src/components/InboxList.tsx` (+ `.test.tsx`), `frontend/src/app/app/inbox/layout.tsx`, `frontend/src/app/app/inbox/[conversationId]/page.tsx` `[G13]`
- Modify: `frontend/src/app/app/inbox/page.tsx` (only the placeholder `<p>`, keeps `metadata`) `[G9]`, `frontend/src/components/AppShell.tsx` (`min-w-0` on the content div) `[G3]`

**Interfaces:**
- Consumes: `api.GET("/api/v1/inbox/conversations", { params: { query: { cursor, limit } }, signal })`, `useLoad`, `usePoll`, `StatusBadge`, `formatListTime`, `CopyChatLinkButton`, `LoadFailed`.
- Produces (`lib/inboxList.ts`):
  - `POLL_MAX = 100`; `pollLimit(shown: number): number` = `Math.min(Math.max(shown, 20), POLL_MAX)`.
  - `appendPage(current: InboxPage, next: InboxPage): InboxPage` — keeps current rows, adds next rows whose id is not shown yet, takes next's `next_cursor`.
  - `mergePoll(current: InboxPage, answer: InboxPage): InboxPage` `[G8]` — when `current.conversations.length <= POLL_MAX`: return `answer`. Else: answer rows, then the current rows from index `POLL_MAX` on whose id is not in the answer; keep `current.next_cursor`; take `chat_slug` and `timezone` from the answer.

- [ ] **Step 1: Tests.** `inboxList.test.ts`: `appendPage drops rows already shown`; `pollLimit` (0 → 20, 35 → 35, 500 → 100); `mergePoll replaces a short list`; `mergePoll keeps rows past 100 and the old next_cursor`. `InboxList.test.tsx`:
  - `shows skeleton rows while the first page loads` (`aria-busy`).
  - `first load fails, Try again shows the rows` `[G2]`.
  - `shows a row: badge, New visitor, one-line preview, Business-time, link to /app/inbox/<id>`.
  - `empty inbox shows the share message and a Copy link button`.
  - `Load more adds the next page and hides when there is none` (button gone when `next_cursor` is null).
  - `Load more failure shows "Could not load more. Try again."`.
  - `a poll replaces the list with the newest top rows` (fake timers, advance 5 s; poll called with `limit = pollLimit(shown)` and no cursor).
  - `a poll does not wipe a page Load more just added` (Load more pending → no poll fires; after it ends, the next poll asks for the new count).
- [ ] **Step 2:** `npx vitest run src/lib/inboxList.test.ts src/components/InboxList.test.tsx` → FAIL.
- [ ] **Step 3: Implement.** `InboxList`: `useLoad` for the first page; `failed`/`not_found` → `<LoadFailed onRetry={reload} />` `[G2]`; `usePoll` with `enabled: ready && !loadingMore`, answer → `state.replace((c) => mergePoll(c, answer))`; Load more → `state.replace((c) => appendPage(c, page))`. Rows: `<ul>` of `<li><Link>`; the preview `<p className="truncate">`; Needs Human rows come first from the server (no client sort). Reconnecting banner with `aria-live="polite"`. `layout.tsx` (Global Constraints, "Two panes"): `<main>` with `<h1>Inbox</h1>`, the list in `<section aria-label="Conversations" className="min-w-0 lg:border-r">`, children in `<section className="hidden lg:block">` (4.4 changes this for the open Conversation on mobile). `[conversationId]/page.tsx`: the placeholder text only.
- [ ] **Step 4:** same command → PASS; then `npx vitest run src/lib/pages.test.ts src/components/AppShell.test.tsx` → PASS.
- [ ] **Step 5: Commit** `feat(frontend): Inbox list with polling and Load more`.

**CHECKPOINT (CORE).**

---

### Task 6: Red Needs Human count on the Inbox tab (STANDARD)

**Files:**
- Create: `frontend/src/lib/useNeedsHumanCount.ts` (+ `.test.ts`)
- Modify: `frontend/src/components/AppShell.tsx` (+ test), `frontend/src/app/app/layout.tsx` (+ test), `frontend/src/app/globals.css` (one token)

**Interfaces:**
- Produces: `useNeedsHumanCount(enabled: boolean): number` — fetches once at once when `enabled`, then `usePoll` every 5 s; keeps the last good number on a failure; 0 when disabled. `AppShell` gets `inboxCount?: number` `[G15]`. On the Inbox link only, a count > 0 shows a pill with `aria-hidden="true"` (visible "3", or "99+" above 99) plus a separate `<span className="sr-only">, 3 need a human</span>` `[G10]`. Pill colors: `bg-status-handoff text-status-handoff-foreground rounded-full`; new token `--status-handoff-foreground: light-dark(#fff, #18181b)` and `--color-status-handoff-foreground` in `globals.css` (dark mode #f87171 needs dark text for contrast).

- [ ] **Step 1: Tests:**
  - `useNeedsHumanCount does not fetch when disabled`; `fetches at once, then every 5 s`; `keeps the last count on a failure`.
  - AppShell: `shows a red count on Inbox` (link accessible name exactly `"Inbox, 3 need a human"`); `shows 99+ above 99`; `no pill at 0`; `no pill when inboxCount is omitted`. The existing `textContent` test stays as is (no count passed).
  - layout `[G11]`: in `beforeEach`, `GET.mockImplementation((path) => Promise.resolve(path === "/api/v1/me" ? { data: OWNER, response: ok } : { data: { count: 3 }, response: ok }))`; `passes the count to the Inbox tab`; `a Technician-only User never calls the count route`.
- [ ] **Step 2:** `npx vitest run src/lib/useNeedsHumanCount.test.ts src/components/AppShell.test.tsx src/app/app/layout.test.tsx` → FAIL.
- [ ] **Step 3: Implement.** In `layout.tsx`, call the hook before the early returns: `useNeedsHumanCount(me.status === "ready" && me.data.permissions.includes("use_inbox_and_bookings"))`, pass `inboxCount={count}`.
- [ ] **Step 4:** same command → PASS.
- [ ] **Step 5: Commit** `feat(frontend): Needs Human count on the Inbox tab`.

---

### Task 7: Docs, checks, review, finish `[G6]`

- [ ] **Step 1:** Backend full suite in WSL: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run lint-imports` → PASS.
- [ ] **Step 2:** Frontend: `npx vitest run`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm run check:chat-size` → PASS (the Chat Page must stay ≤ 204 800 B; this story should not touch it).
- [ ] **Step 3: Docs.** `docs/learning/architecture-map.md`: the Inbox list flow (browser → limit → Role → one query → page) and the count poll. `docs/learning/glossary.md`: keyset cursor, expression index, row compare, denormalized column, generic plan (prepared statement).
- [ ] **Step 4: Manual check** in docker compose: two visitors chat; the Inbox shows both, newest first; set one to `handoff` with SQL → it moves to the top within 5 s and the tab shows a red "1"; at 360px width no sideways scroll; at 1024px two panes.
- [ ] **Step 5: Traces.** In Grafana Cloud, find one `GET /api/v1/inbox/conversations` span with its one SELECT child span.
- [ ] **Step 6:** Set `4-3-inbox-lists-all-conversations: done` in `_bmad-output/implementation-artifacts/sprint-status.yaml` (on this branch; main is protected). Commit `docs: Story 4.3 docs and status done`.
- [ ] **Step 7:** Opus whole-branch review; fix findings with regression tests. Then `docs/agents/after-story.md`. PR body: the `last_message_at` column, the keyset cursor, `PINNED` as a literal (why), the poll limit numbers, the Known limits. Ends with `Closes #19`.

## Known limits (accepted, written in the PR)

- Every row shows "New visitor" until a story collects the Customer's name or phone.
- The open-Conversation pane is a placeholder until Story 4.4.
- The list poll reads Postgres every 5 s per open Inbox tab (no Redis "no change" short cut for the list). Logged-in users are few; revisit if traces show load.
