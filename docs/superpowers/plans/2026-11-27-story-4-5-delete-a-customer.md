# Story 4.5 — Delete a Customer and all their data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, per CLAUDE.md §4: build in this session, stop after each CORE task, one Opus whole-branch review at the end). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Owner opens a Conversation, opens the Customer detail sheet from the header, sees the Customer's data, and deletes the Customer. One transaction removes the Customer, their visitor tokens, Conversations, and Messages. The deleted Customer's cookie then opens no chat. Staff and Technicians get 403.

**Architecture:** `inbox/service.py` gets two front-door functions: `customer_details` and `delete_customer`. `delete_customer` takes the locks in the SAME order as a Customer send (visitor token rows → Conversation rows), then runs plain `DELETE` statements child-first (messages → conversations → visitor_tokens → customers), each filtered by the current Business. It marks each deleted Conversation "changed", so open screens (Chat Page, Inbox) leave their fast "no change" path. One new Permission, Owner only. Two new routes. The frontend adds a `CustomerSheet` (shadcn Sheet + AlertDialog) opened from the `ConversationView` header.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2.1, pytest + testcontainers; Next.js 16, React 19, shadcn (radix-ui), Vitest, openapi-fetch.

**Spec:** `_bmad-output/planning-artifacts/epics.md:860-883` (Story 4.5, GitHub issue #21). Also NFR-8 (`:85`), AR-11 (`:106`), UX-DR28 (`:163`); ARCHITECTURE-SPINE.md AD-13 (`:152-156`), lock order across modules (`:170`), AD-5 (`:86`, no change on GET); EXPERIENCE.md `:39` (Customer detail: sheet, Owner), `:96` (confirm dialog).

## Global Constraints

- **Who:** a new `Permission.MANAGE_CUSTOMER_DATA = "manage_customer_data"`, Owner only (`permissions.py`). It guards BOTH new routes (the sheet is Owner-only, EXPERIENCE.md `:39`). The `Permission` docstring already expects this member.
- **Routes** (both `ActorDep`; another Business's id is 404 `not_found`, never 403; order: Role check → find/lock → work):
  - `GET /api/v1/inbox/conversations/{conversation_id}/customer` → `CustomerOut {customer_id, created_at, conversation_count, message_count}`. operation_id `get_conversation_customer`. responses 401, 403, 404, 422.
  - `DELETE /api/v1/inbox/customers/{customer_id}` → 204. operation_id `delete_customer`. responses 401, 403, 404, 422.
- **No Bookings yet.** Epic 5 adds `bookings.delete_for_customer` BEFORE inbox's own deletes (AD-13). This story leaves one comment at that spot. No stub function.
- **Lock order (no deadlock):** a Customer send locks visitor token → Conversation (`webchat.py:106-119`). A team reply locks only the Conversation. Delete locks: Customer row → its visitor token rows → its Conversation rows, all `FOR UPDATE`, then deletes. Nobody else locks a Customer row, so there is no cycle.
- **Which visitor tokens:** the ones its Conversations point at. Today a token's Conversations always belong to ONE Customer (`open_conversation` makes the Customer and the Conversation together). Say so in a comment.
- **Deletes are statements, not `session.delete()` per row:** `delete(Model).where(Model.business_id == current_business_id(), …)`, child-first so every foreign key is still valid. No migration (no `ON DELETE CASCADE`): explicit steps are easier to read and keep AD-13's order visible.
- **Open screens after a delete:** `mark_conversation_changed` for each deleted Conversation (after commit, existing mechanism). Then:
  - Chat Page with the old cursor → version differs → slow path → the cookie's token row is gone → `ChatPollOut(changed=True, messages=[], snapshot=None, cursor=None)`. A reload shows an empty chat. The next send makes a NEW Customer.
  - Inbox thread poll → slow path → 404 → "This conversation was not found."
  - Known, accepted: an open Chat Page keeps the old bubbles on screen until reload (the client merges, it does not clear). The Redis version key and the 24 h chat map entry stay behind; they hold only ids, and the map expires.
- **Trace (no PII):** one span event `customer.deleted` with `conversations` and `messages` counts only.
- **Copy (exact):**
  - Header button: "Customer" (Owner only, `usePermissions().includes("manage_customer_data")`).
  - Sheet title "Customer". Rows: "Customer since" (date, `en-IN`, `dateStyle: "medium"`), "Conversations", "Messages". Destructive button "Delete customer".
  - Confirm dialog title "Delete this customer?". Text: "This deletes their {N} conversation(s) and {M} message(s). This cannot be undone." Buttons "Cancel" and "Delete customer" (destructive).
  - Load failed: `LoadFailed`. Not found: "This customer was not found."
  - Delete failed: `role="alert"` "Could not delete the customer. Try again."
  - After a delete: go to `/app/inbox` (`router.push`). The list drops the row on its next poll.
- **Tests:** backend in WSL: `wsl --cd "C:\Books\DataSense Community\Seva Desk\backend" -e bash -lc "uv run pytest …"`. Frontend in PowerShell: `npx vitest run …`. Mock `@/api/client` like `ServicesSettings.test.tsx`.
- **Regenerate types** after Task 2: WSL `uv run python -m app.export_openapi ../frontend/openapi.json`, then `npm run gen:api` in `frontend/`.
- **Lint:** `uv run ruff check .`, `uv run ruff format --check .`, `uv run lint-imports`; frontend `npm run lint`, `npx tsc --noEmit`.

## Review Focus

1. **Everything goes, nothing else goes:** the Customer, their tokens, Conversations, Messages are gone; another Customer in the SAME Business is untouched. `test_delete_removes_all_their_rows`, `test_delete_keeps_other_customers` (Task 1).
2. **The cookie opens nothing:** `test_deleted_cookie_opens_no_conversation` (poll with old cursor and without; then a send makes a new Customer) (Task 1).
3. **A send at the same moment:** delete waits for the send's lock, then deletes its Message too; no deadlock. `test_delete_waits_for_a_send` (Task 1).
4. **Another Business's id:** 404, nothing deleted. Isolation checks for both routes (Task 2).
5. **Staff and Technician:** 403 on both routes, nothing deleted. `test_only_the_owner_may_delete` (Task 2).

---

### Task 0: Branch and Story Map (BOILERPLATE)

- [x] `story/4-5-delete-a-customer` from up-to-date `main`.
- [x] `sprint-status.yaml`: `in-progress`; commit `chore: start story 4.5` with this plan.
- [ ] Story Map given. Ask the predict question before Task 1.

### Task 1: The delete and the details in the service (CORE: data deletion, transactions, locks)

Files: `accounts/schemas.py` + `accounts/permissions.py` (Permission), `inbox/repository.py`, `inbox/schemas.py` (`CustomerOut`), `inbox/service.py`; tests `tests/integration/test_inbox_delete_customer.py`, `tests/unit/test_permissions.py` (or the existing permissions test).

- [ ] **Step 1: Failing tests** (service level, each call in its own Session + `tenant_scope`, like `test_inbox_reply.py`):
  - `test_only_owner_has_manage_customer_data` (unit: the FR-10 table).
  - `test_details_counts_their_data` (2 Messages → `conversation_count=1`, `message_count=2`).
  - `test_delete_removes_all_their_rows` (direct DB reads: 0 rows in all four tables for them).
  - `test_delete_keeps_other_customers`.
  - `test_delete_missing_or_twice_is_404`.
  - `test_deleted_cookie_opens_no_conversation` (old cursor → `changed=True`, no messages, no snapshot; then a send → a new `customer_id`).
  - `test_delete_waits_for_a_send` (hold the visitor-token row lock in a raw transaction and insert a Message; the delete thread waits; commit; the delete finishes and that Message is gone too).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Repository: `CustomerRepository.lock(id)`, `details(customer_id)` counts; `ConversationRepository.lock_for_customer(customer_id)`; `VisitorTokenRepository.lock_ids(ids)`; one `delete_…` per table, tenant-filtered. Service: `customer_details`, `delete_customer` (order above, comment where `bookings.delete_for_customer` will go).
- [ ] **Step 4: Run** → PASS; whole inbox suite → PASS.
- [ ] **Step 5: Commit** `feat(inbox): delete a Customer and all their chats in one transaction`. **Checkpoint.**

### Task 2: The two routes (CORE: auth + tenant boundary)

Files: `inbox/router.py`; tests `test_inbox_delete_customer.py` (part 2), `test_tenant_isolation.py`.

- [ ] **Step 1: Failing tests:** `test_owner_deletes_by_route` (GET then DELETE → 204, then GET of the thread → 404); `test_only_the_owner_may_delete` (Staff and Technician-only → 403 on both, rows still there); isolation checks `check_get_conversation_customer`, `check_delete_customer` (A with B's ids → 404, B's Customer still there).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** the routes. Regenerate `openapi.json` + `schema.d.ts`.
- [ ] **Step 4: Run** → PASS; full backend suite + lint.
- [ ] **Step 5: Commit** `feat(inbox): routes to see and delete a Customer (Owner only)`. **Checkpoint.**

### Task 3: Customer detail sheet (STANDARD; shadcn files BOILERPLATE)

Files: `npx shadcn add sheet alert-dialog` → `components/ui/sheet.tsx`, `components/ui/alert-dialog.tsx`; new `components/CustomerSheet.tsx` + test; `ConversationView.tsx` (+ test).

- [ ] **Step 1: Failing tests:** `owner sees a Customer button; staff does not`; `sheet shows the counts`; `confirm names conversations and messages and says it cannot be undone`; `confirm deletes and goes to the Inbox`; `a failed delete shows an alert and stays`; `cancel deletes nothing`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** whole frontend suite + lint + `tsc` + `npm run build` → OK.
- [ ] **Step 5: Commit** `feat(inbox): Customer detail sheet with a delete confirm`.

### Task 4: Finish (BOILERPLATE)

- [ ] Full backend + frontend suites and lint.
- [ ] Run the app (`run` skill): chat as a Customer, delete as Owner, reload the Chat Page (empty), phone width 360px.
- [ ] PR body has `Closes #21`.
- [ ] `sprint-status.yaml`: story `done` on the branch before merge ([[status-done-in-story-pr]]).
- [ ] One Opus whole-branch review (CLAUDE.md §4). Fix real findings with regression tests.
- [ ] Then `docs/agents/after-story.md`. Last story of Epic 4: update `docs/learning/architecture-map.md` + 5-sentence recap.
