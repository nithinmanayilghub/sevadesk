# Story 4.4 — Reply to a Customer and take over the chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, per CLAUDE.md §4: build in this session, stop after each CORE task, one Opus whole-branch review at the end). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Owner or Staff member opens a Conversation in the Inbox, reads the full history, and replies. A reply starts a Handoff (the Agent pauses). A Handoff bar lets them take over or give the chat back to the Agent. The reply shows on the Customer's Chat Page within 5 s.

**Architecture:** `inbox/service.py` gets the only two state setters, `start_handoff` and `end_handoff` (AD-10). Both run on a Conversation row the caller holds locked (`SELECT … FOR UPDATE`). The save steps of `receive_message` move into one helper, `_append`, that the Customer send and the team reply share (seq, last_message_at, version bump). Four new logged-in routes: poll one Conversation (the same `ChatPollOut` shape as the Chat Page, AD-7), send a reply, take over, give back. The frontend moves the bubble, composer, and send logic out of `ChatPanel` into shared parts, and builds `ConversationView` on them.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2.1, redis-py, pytest + testcontainers; Next.js 16 (`useSelectedLayoutSegment`), React 19, Vitest, openapi-fetch.

**Spec:** `_bmad-output/planning-artifacts/epics.md:827-858` (Story 4.4, GitHub issue #20). Also FR-21 (`:55`), FR-24 (`:61`), AR-15 (`:112`), UX-DR7 (`:138`), UX-DR12 (`:143`), UX-DR13 (`:144`); ARCHITECTURE-SPINE.md AD-7 (`:94-107`), AD-10 (`:138`); EXPERIENCE.md `:76-77` (Handoff bar, Composer), `:101` (Enter rule).

## Global Constraints

- **Decision (user, 2026-11-26): no User names exist.** `users` has only an email. A team reply shows the **Business name** above the bubble on the Chat Page, and "Team" in the Inbox (Task 4). No new column, no new form. Log the real-name gap in `docs/learning/gaps.md` (Task 6).
- **Agent label (UX-DR7):** an `agent` bubble shows "SevaDesk assistant" above it. No Agent Messages exist yet; the label is one line in `authorLabel`.
- **Bubble sides (UX-DR7, same on both screens):** `customer` on the right in `bg-primary text-primary-foreground`; `agent`, `user`, `system` on the left in `border bg-card`, `rounded-xl`.
- **State rule (AD-10, AR-15):** only `start_handoff` and `end_handoff` in `inbox/service.py` write `Conversation.state`. `close` is not built: no story calls it yet.
  - `start_handoff`: any state → `handoff`. (From `closed` it reopens the chat; no closed chats exist yet.) Already `handoff` → no change, no version bump.
  - `end_handoff`: only `handoff` → `agent`. Any other state → no change.
  - Each real change calls `mark_conversation_changed` (the poll snapshot carries the state).
- **Lock order:** team routes lock only the Conversation row. The Chat Page locks visitor token → Conversation. One lock cannot wait on the other in a cycle, so no deadlock.
- **Routes** (all `ActorDep`, all check `Permission.USE_INBOX_AND_BOOKINGS`; an id from another Business is 404 `not_found`, never 403):
  - `GET /api/v1/inbox/conversations/{conversation_id}/messages?cursor=` → `ChatPollOut`. operation_id `poll_inbox_conversation`. responses 401, 403, 404, 429, 503. Counts `count_inbox_poll(actor)` first.
  - `POST /api/v1/inbox/conversations/{conversation_id}/messages` body `SendMessageIn` → 201 `MessageOut`. operation_id `send_inbox_reply`. responses 401, 403, 404, 422.
  - `POST /api/v1/inbox/conversations/{conversation_id}/take-over` → `ConversationStateOut`. operation_id `take_over_conversation`. responses 401, 403, 404.
  - `POST /api/v1/inbox/conversations/{conversation_id}/give-back` → `ConversationStateOut`. operation_id `give_back_conversation`. responses 401, 403, 404.
- **Poll fast path (AD-7 "cheap polls"):** parse the cursor with `ChatCursor.parse`. If it parses, its `business_id` is the actor's, and `read_version(actor.business_id, conversation_id) == parsed.version` → `ChatPollOut(changed=False, messages=[], snapshot=None, cursor=parsed.format())`, no Postgres. Else the slow path: `ConversationRepository.get_or_raise(conversation_id)` (404), then `poll_conversation(session, conversation, after_seq)` with `after_seq = parsed.after_seq` only when the cursor is this Business's, else 0. Redis down → 503 (`chat_unavailable()`).
- **Poll budget:** unchanged (`INBOX_POLL_LIMIT = 120` per 60 s). An open chat tab now polls 3 routes every 5 s = 36 a minute: room for 3 tabs. Update the comment at `service.py:199-201`.
- **No reply limit.** Team members are logged in and few. A retry with the same `client_message_id` returns the saved Message (idempotent), like the Customer send.
- **Copy (exact):**
  - Handoff bar, `agent` state: "Agent is replying" + button "Take over".
  - Handoff bar, `handoff` state: "You are replying. The Agent is paused." + button "Give back to Agent".
  - Handoff bar, `closed` state: no bar.
  - One-time hint above the composer: "Your reply pauses the Agent." Shown while the state is `agent` and the browser has not saved the flag. Saved after the first successful reply. `localStorage` key `sevadesk:reply-hint-seen`, value `"1"`, every read and write in `try/catch` (a private window can throw).
  - Composer: label "Reply" (screen reader only), placeholder "Type a reply…", button "Send". Failed send: "Not sent · Retry" (shared with the Chat Page).
  - Thread not found (404): "This conversation was not found." + link "Back to Inbox" (`/app/inbox`).
  - Load failed: `LoadFailed` component. Take-over / give-back failure: `role="alert"` text "Could not change who replies. Try again."
  - Mobile back link above the thread: "← Inbox" (`/app/inbox`), hidden from `lg`.
- **Enter rule (UX-DR13):** Enter sends only with a fine pointer (`(pointer: fine)`); Shift+Enter is a new line; on a phone Enter is a new line and Send sends. Same `hasFinePointer` as today, moved to `Composer.tsx`.
- **Two panes on mobile:** below `lg`, with a Conversation open, hide the list and show the thread. With none open, show the list only. From `lg`: both, as today. Use `useSelectedLayoutSegment()` (it returns the `[conversationId]` value, or `null` on `/app/inbox`).
- **Chat Page stays light (NFR-6):** shared parts use plain elements, no `ui/button`, no icon sets.
- **Tests:** backend in WSL: `wsl --cd "C:\Books\DataSense Community\Seva Desk\backend" -e bash -lc "uv run pytest …"` (call `wsl` from PowerShell). Frontend in PowerShell: `npx vitest run …` (`--maxWorkers=2` on low RAM). Check effect results with `vi.waitFor`. Mock `@/api/client` like `ServicesSettings.test.tsx`.
- **Regenerate types** after Task 2: WSL `uv run python -m app.export_openapi ../frontend/openapi.json`, then `npm run gen:api` in `frontend/`.
- **Lint:** `uv run ruff check .`, `uv run ruff format --check .`, `uv run lint-imports`; frontend `npm run lint`, `npx tsc --noEmit`.

## Review Focus

1. **An id from another Business** (guessed or pasted) on any of the 4 routes → 404, nothing saved, no state change. Pinned by `test_other_business_conversation_is_404` (Task 2), over all 4 routes.
2. **A lost answer and a retry** (same `client_message_id`) → one Message, the state set once. Pinned by `test_reply_retry_saves_once` (Task 1).
3. **Two members act at once** (one gives back while the other takes over, or Give back twice) → the row lock puts them in line; Give back on an `agent` chat changes nothing and does not bump the version. Pinned by `test_end_handoff_only_from_handoff` and `test_start_handoff_twice_bumps_once` (Task 1).
4. **The Customer's Chat Page sees the reply** without a reload: the reply bumps the version, so the fast poll is not "no change". Pinned by `test_chat_page_poll_sees_team_reply` (Task 2).
5. **A Technician-only User** posts a reply or takes over by direct URL → 403. Pinned by `test_technician_gets_403_on_team_routes` (Task 2).

---

### Task 0: Branch and Story Map (BOILERPLATE)

- [x] `story/4-4-reply-and-take-over` from up-to-date `main` (done).
- [ ] `sprint-status.yaml`: `4-4-reply-to-a-customer-and-take-over-the-chat: in-progress`. Commit `chore: start story 4.4` with this plan.
- [ ] Give the user the Story Map (CLAUDE.md §2, max 5 bullets, one predict question).

---

### Task 1: State setters and the shared save (CORE: state machine, concurrency)

**Files:**
- Modify: `backend/app/modules/inbox/service.py` (`receive_message` step 4–5 → `_append`; new `start_handoff`, `end_handoff`, `reply`, `take_over`, `give_back`, `_locked_for_member`)
- Modify: `backend/app/modules/inbox/repository.py` (`ConversationRepository.lock`)
- Modify: `backend/app/modules/inbox/schemas.py` (`ConversationStateOut`)
- Modify: `backend/app/modules/inbox/channel.py:10-11` (comment: web outbound = the Chat Page poll; no outbound method until WhatsApp)
- Create: `backend/tests/integration/test_inbox_reply.py`
- Create: `backend/tests/unit/test_conversation_state_owner.py`

**Interfaces:**
- Produces:
  - `ConversationRepository.lock(conversation_id: uuid.UUID) -> Conversation | None` — `_locked(self._select().where(Conversation.id == conversation_id))`.
  - `start_handoff(session: Session, conversation: Conversation) -> None` and `end_handoff(session: Session, conversation: Conversation) -> None` — caller holds the row lock.
  - `_append(session: Session, conversation: Conversation, message: Message) -> MessageOut` — sets `seq = conversation.last_seq + 1`, adds, refreshes, raises `last_message_at` with `max(...)`, calls `mark_conversation_changed`. `receive_message` and `reply` both use it.
  - `reply(session: Session, actor: Actor, conversation_id: uuid.UUID, data: SendMessageIn) -> MessageOut`
  - `take_over(session, actor, conversation_id) -> ConversationStateOut`, `give_back(session, actor, conversation_id) -> ConversationStateOut`
  - `class ConversationStateOut(BaseModel): state: Literal["agent", "handoff", "closed"]`
- `reply` order: `_locked_for_member` (roles check, then lock, `NotFound` if None) → `find_by_client_id` (a retry returns the saved one, no state change) → `start_handoff` → `_append(Message(author_type="user", author_membership_id=actor.membership_id, body, lang=detect_lang(body), client_message_id))`.

- [ ] **Step 1: Write the failing tests** in `test_inbox_reply.py`, service-level (call the functions inside `tenant_scope` with a real session, like `test_inbox_service.py`). Reuse `new_chat` / `set_state` from `test_inbox_list.py`.
  - `test_reply_saves_a_user_message` — behaviour: a team reply is saved as the next Message, written by that member. Assert `seq == 2`, `author_type == "user"`, the row's `author_membership_id == actor.membership_id`, `last_message_at` ≥ the Customer Message's time.
  - `test_reply_starts_handoff` — behaviour: replying pauses the Agent. State `agent` → `handoff` after `reply`.
  - `test_reply_retry_saves_once` — same `client_message_id` twice → one row, same `seq`.
  - `test_take_over_and_give_back` — `take_over` → `"handoff"`; `give_back` → `"agent"`.
  - `test_end_handoff_only_from_handoff` — `give_back` on an `agent` chat → still `"agent"`, version unchanged (`read_version` before == after commit).
  - `test_start_handoff_twice_bumps_once` — `take_over` twice → the version went up once.
  - `test_customer_send_still_works` — the existing `receive_message` tests stay green after the `_append` move (run the whole `test_inbox_service.py`).
- [ ] **Step 2: Write the failing rule test** `test_conversation_state_owner.py` (unit, no DB). Behaviour: only the named setters write the state (AR-15). Walk every `.py` under `backend/app` with `ast`; collect each `Assign`/`AugAssign` whose target is an `Attribute` named `state`, with its file and enclosing function name. Assert the set is exactly `{("app/modules/inbox/service.py", "start_handoff"), ("app/modules/inbox/service.py", "end_handoff")}`. Comment: `bookings` adds its own setters to this list in Epic 5.
- [ ] **Step 3: Run both, expect FAIL** (`ImportError` / missing functions; the rule test fails on an empty set).
- [ ] **Step 4: Implement** the Interfaces above. Comment the lock rule and the "no change → no bump" rule in plain words.
- [ ] **Step 5: Run** `uv run pytest tests/integration/test_inbox_reply.py tests/integration/test_inbox_service.py tests/unit/test_conversation_state_owner.py` → PASS. Then ruff + lint-imports.
- [ ] **Step 6: Commit** `feat(inbox): start_handoff, end_handoff, and team replies`.
- [ ] **CHECKPOINT** (CORE): explain the lock, the idempotent retry, and why a no-op skips the version bump. Wait for the user.

---

### Task 2: The four team routes (STANDARD)

**Files:**
- Modify: `backend/app/modules/inbox/router.py` (4 routes, header comment), `backend/app/modules/inbox/service.py` (`poll_for_member`, budget comment)
- Modify: `backend/tests/integration/test_inbox_reply.py` (HTTP tests)
- Regenerate: `frontend/openapi.json`, `frontend/src/api/schema.d.ts`

**Interfaces:**
- Consumes: Task 1's `reply`, `take_over`, `give_back`, `ConversationStateOut`.
- Produces: `poll_for_member(session: Session, actor: Actor, conversation_id: uuid.UUID, cursor: str | None) -> ChatPollOut` (roles check first; the fast/slow path in Global Constraints). Frontend paths: `"/api/v1/inbox/conversations/{conversation_id}/messages"` (GET, POST), `".../take-over"`, `".../give-back"` (POST).

- [ ] **Step 1: Write the failing HTTP tests** (owner client from `sign_up_owner`; the test client already sends the Origin header):
  - `test_open_conversation_shows_full_history` — 2 Customer sends; GET with no cursor → `changed`, 2 Messages oldest first, `snapshot.conversation_state == "agent"`, a cursor.
  - `test_thread_poll_no_change` — GET again with that cursor → `changed is False`, `messages == []`.
  - `test_reply_route` — POST reply → 201, `author_type == "user"`; the next GET with the old cursor → `changed`, 1 new Message, state `"handoff"`.
  - `test_chat_page_poll_sees_team_reply` — the Customer polls `/api/v1/chat/{slug}/messages` with its cursor (fast path) after the reply → `changed`, the reply is there with `author_type == "user"`.
  - `test_take_over_and_give_back_routes` — POST take-over → `{"state": "handoff"}`; give-back → `{"state": "agent"}`.
  - `test_other_business_conversation_is_404` — a second Business's Conversation id on all 4 routes → 404 `not_found`; that chat still has 1 Message and state `agent`.
  - `test_technician_gets_403_on_team_routes` — a Technician-only member (`set_owner_roles`) → 403 on all 4.
  - `test_reply_bad_body_is_422` — empty body → 422 `message_empty`.
  - `test_thread_poll_redis_down_is_503` — like `test_inbox_redis_down_is_503`.
- [ ] **Step 2: Run, expect FAIL** (404 / 405 on the new paths).
- [ ] **Step 3: Implement** `poll_for_member` and the 4 routes. POST reply has `status_code=201`. Each route is one line into `service` (the poll route calls `count_inbox_poll` first).
- [ ] **Step 4: Run** the file and the whole inbox suite → PASS. Lint.
- [ ] **Step 5: Regenerate types** (commands in Global Constraints). `npx tsc --noEmit` → clean.
- [ ] **Step 6: Commit** `feat(inbox): routes to read, reply, take over, and give back`.

---

### Task 3: Shared chat parts, and the team name on the Chat Page (STANDARD: refactor)

**Files:**
- Create: `frontend/src/components/ChatBubble.tsx` (`Bubble`, `SentBubble`, `authorLabel`), moved from `ChatPanel.tsx:212-268`
- Create: `frontend/src/components/Composer.tsx` (textarea + Send + Enter rule + optional hint), moved from `ChatPanel.tsx:176-205`
- Create: `frontend/src/lib/useSends.ts` (the `sent` list, `send`, `retry`; `retryable` and `reasonOf` move here), moved from `ChatPanel.tsx:30-41, 95-125`
- Modify: `frontend/src/components/ChatPanel.tsx` (uses the three; passes `label` from `authorLabel`)
- Test: `frontend/src/components/ChatPanel.test.tsx` (all old tests stay green, plus one new), `frontend/src/lib/useSends.test.ts`

**Interfaces:**
- Produces:
  - `authorLabel(authorType: string, teamName: string): string | undefined` — `"user"` → `teamName`; `"agent"` → `"SevaDesk assistant"`; else `undefined`.
  - `Bubble({ authorType, lang?, body, label?, sending?, children? })` — `label` shows above the bubble as small muted text.
  - `SentBubble({ item, onRetry, authorType })` — `authorType` is `"customer"` on the Chat Page, `"user"` in the Inbox.
  - `Composer({ id, label, placeholder, value, onChange, onSend, hint? })` — `hint` shows as muted text above the box.
  - `useSends(post: (body: string, clientMessageId: string) => Promise<{ data?: MessageOut; error?: unknown; response: Response }>): { sent: Sent[]; send: (body: string) => void; retry: (clientMessageId: string, body: string) => void }`. Optional second arg `{ onSent?: (message: MessageOut) => void }` (the Inbox uses it to set `handoff` and save the hint flag).

- [ ] **Step 1: Write the failing test** in `ChatPanel.test.tsx`: `a team reply shows the Business name above the bubble` — a poll answer with an `author_type: "user"` Message; the Business name shows next to it on the left.
- [ ] **Step 2: Write** `useSends.test.ts`: `send marks a saved Message sent`, `a 422 fails with no Retry`, `a network error fails with Retry`, `retry sends the same client_message_id`, `onSent gets the saved Message`.
- [ ] **Step 3: Run, expect FAIL.**
- [ ] **Step 4: Move the code** into the three files. No behaviour change except the label.
- [ ] **Step 5: Run** `npx vitest run src/components/ChatPanel.test.tsx src/components/ChatPage.test.tsx src/lib/useSends.test.ts` → PASS. Lint + `tsc`.
- [ ] **Step 6: Commit** `refactor(chat): share bubbles, composer, and sends; label team replies`.

---

### Task 4: ConversationView (CORE: live thread + handoff UI)

**Files:**
- Create: `frontend/src/components/ConversationView.tsx`, `frontend/src/components/ConversationView.test.tsx`

**Interfaces:**
- Consumes: Task 2 paths; Task 3 `Bubble`, `SentBubble`, `Composer`, `useSends`, `authorLabel`; `mergePoll`, `chatItems` (`lib/chatPoll.ts`); `usePoll`; `useLoad`; `LoadFailed`.
- Produces: `ConversationView({ conversationId }: { conversationId: string })`.
- Label: in the Inbox, team replies show **"Team"** (`authorLabel(type, "Team")`). Why not the Business name: the thread poll does not carry it, and Staff cannot read the setup routes. The Customer still sees the Business name on the Chat Page.

Behaviour:
- Load `GET …/messages` (no cursor). `useLoad` status `not_found` → the not-found copy. `failed` → `LoadFailed`.
- Poll every 5 s with the cursor (`usePoll`, enabled when ready); `state.replace(mergePoll)` on `changed`. "Reconnecting…" status line like `ChatPanel`.
- Bubbles via `chatItems(saved, sent)`; own sends as `SentBubble authorType="user"` with label "Team".
- Handoff bar from `snapshot.conversation_state` (copy in Global Constraints). Its button POSTs take-over / give-back, then sets the snapshot state from the answer (`state.replace`). Button disabled while its request runs.
- Reply `onSent`: set the snapshot state to `handoff` at once; save the hint flag.
- Hint: shown when state is `agent` and the flag is not saved.

- [ ] **Step 1: Write the failing tests** (one line of behaviour above each CORE test):
  - `shows the full history, Customer on the right` — 2 Messages render in order; the Customer bubble has `ml-auto`.
  - `agent state shows "Agent is replying" and Take over`.
  - `Take over posts and switches the bar` — after click, "You are replying. The Agent is paused." and "Give back to Agent".
  - `Give back to Agent posts and switches the bar back`.
  - `a failed take over shows an alert` — 500 → "Could not change who replies. Try again.".
  - `a reply switches to handoff and hides the hint` — hint shown first; after a 201 the bar says "You are replying…", the hint is gone, `localStorage` has the flag.
  - `the hint stays hidden once seen` — flag preset → no hint.
  - `Enter sends with a fine pointer; Shift+Enter does not` — `matchMedia` mocked.
  - `a 404 shows not found with a link back`.
  - `a poll adds a new Customer Message` — fake timers, 5 s, second GET answer with seq 3.
- [ ] **Step 2: Run, expect FAIL** (module missing).
- [ ] **Step 3: Implement** `ConversationView.tsx`.
- [ ] **Step 4: Run** → PASS. Lint + `tsc`.
- [ ] **Step 5: Commit** `feat(inbox): open a conversation, reply, take over, give back`.
- [ ] **CHECKPOINT** (CORE): walk the data flow click → POST → version bump → both polls. Wait for the user.

---

### Task 5: The page and the mobile panes (STANDARD)

**Files:**
- Modify: `frontend/src/app/app/inbox/[conversationId]/page.tsx` (server page: `await params`, render `<ConversationView key={conversationId} conversationId={conversationId} />` under the mobile back link; metadata title `"Conversation · SevaDesk"`)
- Modify: `frontend/src/app/app/inbox/layout.tsx` (`"use client"`; `useSelectedLayoutSegment()`; list section `hidden lg:flex` when open; thread section `hidden lg:block` when closed, `block` when open)
- Create: `frontend/src/app/app/inbox/layout.test.tsx` (mock `next/navigation` and `InboxList`)
- Modify: `frontend/src/lib/inboxList.ts:31-32` (comment: give-back moves a chat down; a row past 100 keeps its old badge until reload — known limit, kept)

- [ ] **Step 1: Write the failing tests:** `no open conversation: list shown, thread pane hidden on mobile`; `open conversation: list hidden on mobile, thread shown`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the whole frontend suite → PASS. `npm run build` → OK (checks the server page + client layout split).
- [ ] **Step 5: Commit** `feat(inbox): the open conversation fills the screen on mobile`.

---

### Task 6: Finish (BOILERPLATE)

- [ ] Full backend suite + lint (WSL); full frontend suite + lint + `tsc` + build (PowerShell).
- [ ] Run the app (`run` skill): reply from the Inbox, see it on the Chat Page within 5 s with the Business name; take over / give back; phone width 360px.
- [ ] `docs/learning/gaps.md`: add "Users have no name: team replies show the Business name (Chat Page) and 'Team' (Inbox). A later story adds names."
- [ ] `sprint-status.yaml`: `done` on the branch before merge ([[status-done-in-story-pr]]).
- [ ] One Opus whole-branch review (CLAUDE.md §4). Fix real findings with regression tests.
- [ ] Then `docs/agents/after-story.md` (Understanding Gate).
