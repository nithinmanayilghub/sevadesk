# Story 3.3 — Share the Chat Page link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, per CLAUDE.md §4: build in this session, stop after each CORE task, one Opus whole-branch review at the end). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Business gets a stable chat slug. The Owner copies the link `/c/{slug}` from Settings → Chat link or from a Dashboard checklist. A visitor with no log-in opens `/c/{slug}` and sees the Business name, the active Services with Prices, the DPDP notice, and "Not taking requests yet" while setup is not done.

**Architecture:** `business` owns a new `businesses.chat_slug` column (text, NOT NULL, UNIQUE), made at sign-up by a pure helper `make_chat_slug(name)`. Two new routes in `business/router.py`: Owner-only `GET /api/v1/setup` (slug + "has Services" + "has Working Hours") and public `GET /api/v1/chat/{chat_slug}`. The public route finds the Business by slug, then enters `tenant_scope(business.id)` — AD-3 source (b): the tenant comes from the slug only. The frontend adds `/c/[slug]` (public), `/app/settings/chat-link`, and a checklist on the Dashboard. A Node script measures the Chat Page first load in CI.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2.1, Alembic, pytest + testcontainers; Next.js 16, React 19, Tailwind 4, Vitest, openapi-typescript; Node 24 (`zlib`, `fetch`) for the size check.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 3.3: Share the Chat Page link" (line ~680), GitHub issue #16. Also FR-14, FR-16a, NFR-6, NFR-8 (`epics.md:43,49,83,85`), AR-6 (`epics.md:101`), AR-23 (`epics.md:122`), UX-DR8, UX-DR20, UX-DR23 (`epics.md:139,155,158`), EXPERIENCE.md:30 (route `/c/{business}`), :43 (`/app/settings/chat-link`, Owner, from More and Dashboard), :55 (price copy), :85 (first run), :119 (200 KB budget), ARCHITECTURE-SPINE.md:30 (`business` owns the chat slug), :73 (AD-3 tenant sources), mockups/key-chat-page.html (DPDP notice text).

**Review history:** an Opus plan review (2026-11-20) found 5 major and 10 minor gaps; all 15 are fixed below (marked `[G#]`).

## Global Constraints

- Column `businesses.chat_slug`: `text NOT NULL`, constraint `uq_businesses_chat_slug` (follows the naming rule in `core/db.py:15`). Never changes after it is made ("stable"), even if the name changes later.
- Slug format: `<name part>-<6 random chars>`. Name part = the name NFKD-normalised with accent marks dropped (`"Café"` → `"Cafe"`) `[G15]`, lowercased, every run of characters outside `a-z0-9` becomes one `-`, `-` trimmed from both ends, cut to 30 chars (then trimmed again). Empty name part (e.g. a Hindi-only name) → `chat`. Random part: 6 chars from `abcdefghjkmnpqrstuvwxyz23456789` (no `i l o 0 1`: easy to read aloud), chosen with `secrets.choice`. Example: `Ravi Cool Services` → `ravi-cool-services-k7m2qx`.
- A valid slug shape: `^[a-z0-9-]{1,40}$` `[G3]`. It covers new slugs (≤ 37 chars) and backfilled ones (`chat-` + 6 hex).
- Routes: `GET /api/v1/setup` (operation_id `get_setup`, `Permission.MANAGE_SETUP`, checked first) and `GET /api/v1/chat/{chat_slug}` (operation_id `get_chat_page`, no log-in).
- "Has Services" = at least one ACTIVE Service. "Has Working Hours" = at least one `working_hours` row. Closed dates do not count. Taking requests = both.
- Unknown slug AND a badly shaped slug (NUL, upper case after lowering fails, too long) → the existing `NotFound` (404, `{"error": {"code": "not_found", "message": "We could not find that."}}`), raised BEFORE any database query for a bad shape `[G3]`. The input is lowercased first, so a hand-typed `RAVI-K7M2QX` still works.
- The public route returns NO ids (no business_id, no service_id): only what the page shows.
- Copy, verbatim:
  - Price row: `from ₹499` (via `formatRupees`), duration like `1 h 30 min`, then once under the list: `Final price after inspection. Parts extra.`
  - DPDP notice, ALWAYS shown (FR-14) `[G5]`: `We collect your name, phone, and address only to book your job. {Business name} can delete them on request.`
  - Not set up: `Not taking requests yet` (shown in addition to the Services list and the notice).
  - Unknown slug: heading `Chat page not found`, text `Check the link and try again.`
  - Checklist steps: `Add Services` → `Set Working Hours` → `Copy chat link`. Copy button label: `Copy link` (Settings) / `Copy chat link` (checklist). After a copy the button text becomes `Copied` (the `InviteForm.tsx:62-70,129-130` pattern) `[G4]`. Copy failed: `Could not copy. Select the link and copy it.` plus the URL in a read-only input that selects itself on focus (the `InviteForm.tsx:127` pattern) `[G4]`.
- Full URL = `${window.location.origin}/c/${chat_slug}` (built in the browser: one origin serves both apps, AD-6).
- Settings page: `/app/settings/chat-link`, label `Chat link`, `needs: "manage_setup"`, in `PAGES` right AFTER Working Hours.
- Emerald = the existing `brand` / `brand-soft` tokens (`globals.css:92-94`). Solid surfaces only on app and Chat Page (DESIGN.md:135).
- Chat Page first load ≤ 200 KB gzip, where **200 KB = 204,800 bytes** (1 KB = 1024 bytes, the usual meaning in bundle tools) `[G2]`. Counted: the HTML + every `<script src>` WITHOUT `nomodule` + every `<link rel="stylesheet">` + every `<link rel="preload">` the HTML names. NOT counted: `nomodule` scripts (modern browsers skip them), the favicon, and the API JSON response.
- Every new route is in `tests/integration/test_tenant_isolation.py` `ISOLATION_CHECKS`. Both routes have tenant data, so neither goes in `NO_TENANT_DATA`.
- `frontend/openapi.json` and `src/api/schema.d.ts` regenerated in the SAME commit as the routes.
- Backend commands run in WSL: `wsl --cd "C:\Books\DataSense Community\Seva Desk\backend" -e bash -lc "uv run …"`. Frontend tests in Windows PowerShell (`npx vitest run …`). Docker Desktop must run.
- Branch `story/3-3-chat-link`. PR body ends with `Closes #16`.

## Decisions made in this plan

- **`BusinessRepository.add(name)` keeps its signature and makes the slug itself** `[G1]`: `Business(name=name, chat_slug=make_chat_slug(name))`. So `sign_up` and the 11 existing test calls (`test_sessions.py:26`, `test_tenant_repository.py`, `test_tenant_schema.py:77`) stay unchanged.
- **One Owner endpoint for both screens.** `GET /api/v1/setup` → `SetupOut(chat_slug, has_services, has_working_hours)`. The checklist and Settings → Chat link both read it.
- **The checklist shows only to Users with `manage_setup`** (the Owner). Staff also see the Dashboard, but they cannot add Services. Users without `manage_setup` keep the line `Coming soon.` `[G14]`. The checklist stays visible in its emerald "done" state; Story 8.1 decides when to hide it.
- **The slug lookup needs no `system_scope`.** `businesses` is a global table, and the slug is public by design. The architecture lists "chat slug" as its own tenant source (AD-3 b). `get_chat_page` sets `tenant_scope(business.id)` itself, the same way `sign_up` does. The route has no `ActorDep`, so a logged-in Owner's cookie never picks the tenant.
- **The slug shape is checked in `service.py`, not with `Path(pattern=…)`** `[G3]`: a pattern answers 422, which looks different from an unknown slug. One answer (404) for every slug that is not a real one.
- **A slug collision is not retried.** 31^6 ≈ 887 million random parts per name. The UNIQUE rule is the guard; a collision would be a 500 on one sign-up.
- **Migration backfill uses SQL, not app code:** existing Businesses get `'chat-' || substr(md5(id::text), 1, 6)`. A migration must not import app code that can change later. (Two old Businesses with the same 6 hex chars would stop the migration; with a handful of demo rows the chance is near zero, and the migration then fails loudly, not silently.)
- **The Chat Page is a client component** that calls the API from the browser, like every other page. Side effect: an unknown slug answers HTTP 200 with the "not found" text (the page itself loads; the API call is the 404).
- **The DPDP notice and the Services list always show** `[G5]` (FR-14, `epics.md:700`). "Not taking requests yet" is one extra line when setup is not done.
- **The Services list uses the row index as the React key** `[G14]`: the public response has no ids, and Service names are not unique (`models.py:50`).
- **Size check = measure the real page.** `next build`, then `next start` (with `output: "standalone"` it only prints a warning and still serves `.next/static`, `next/dist/server/next.js:255-257`) `[G9]`. Fetch `/c/size-check`, gzip the HTML and every counted asset, sum. Any counted asset that is not HTTP 200 fails the check.
- **The budget is already about 95% used** `[G2]` (the Opus review measured the current home page at about 194.5 KB counted: scripts 138.5 KB, Inter font preload 47.3 KB, CSS 6.5 KB, HTML 2.2 KB). So Task 5 measures a stub `/c/[slug]` page FIRST and records the baseline. Fallback if the real page goes over: set `preload: false` on Inter (`app/layout.tsx`) — the font still loads, but only when used, and it is no longer counted as a preload. Try that only if needed, and record the before/after numbers.
- **`formatDuration(minutes)` goes in `lib/time.ts`:** `30 → "30 min"`, `60 → "1 h"`, `90 → "1 h 30 min"`, `480 → "8 h"`.
- **Not in this story:** the chat itself, visitor tokens, the composer (Epic 4); rate limits on public routes (NFR-5 lands with public chat in Epic 4); a QR code; editing the slug.

## Review Focus

1. **A Service is deactivated** → it disappears from the Chat Page, and if it was the only one, the page shows `Not taking requests yet` and the checklist step "Add Services" is not done. → Task 2 `test_inactive_services_are_hidden`, `test_setup_counts_only_active_services`.
2. **A name with no Latin letters (`"सेवा"`), only symbols (`"!!!"`), or accents (`"Café Cool"`)** → `chat-xxxxxx` / `cafe-cool-xxxxxx`, never a leading `-` or an empty name part. → Task 1 `test_slug_name_part`.
3. **A logged-in Owner A opens B's chat link** → the page shows B's data, decided by the slug only. → Task 2 isolation check `check_get_chat_page` calls it with A's logged-in client.
4. **The clipboard is blocked or missing** (http page, old browser, permission denied, `navigator.clipboard` undefined) → the fallback text and the URL in a selectable box, on BOTH the Settings page and the checklist. → Task 4 `shows a fallback when copy fails`, `shows a fallback when there is no clipboard`.
5. **A strange slug (`%00`, 500 chars, upper case)** → 404 for the bad ones, never a 500; upper case finds the Business. → Task 2 `test_bad_slug_is_not_found`, `test_slug_is_case_insensitive`.

---

### Task 0: Start (done before this plan was reviewed)

- [x] Branch `story/3-3-chat-link`; `gh issue edit 16 --add-label in-progress`.
- [x] Story Map shown to the user, with one prediction question (CLAUDE.md §2).
- [ ] Set `3-3-share-the-chat-page-link: in-progress` in `_bmad-output/implementation-artifacts/sprint-status.yaml`; commit it with the plan: `docs: Story 3.3 plan` `[G12]`.

### Task 1: The chat slug column (CORE — data model)

**Files:**
- Create: `backend/app/modules/business/chat_slug.py`
- Create: `backend/migrations/versions/0008_chat_slug.py`
- Modify: `backend/app/modules/business/models.py` (`Business`), `backend/app/modules/business/repository.py` (`BusinessRepository.add` body only)
- Test: `backend/tests/unit/test_chat_slug.py`, `backend/tests/integration/test_chat_slug_table.py`, `backend/tests/integration/test_migrations.py`

**Interfaces:**
- Produces: `make_chat_slug(name: str) -> str`; `SLUG_ALPHABET: str`; `Business.chat_slug: Mapped[str]` (`mapped_column(Text, unique=True)`, constraint name `uq_businesses_chat_slug`); `BusinessRepository.add(name: str) -> Business` (unchanged signature) `[G1]`.

- [ ] **Step 1: Write the failing unit tests** in `tests/unit/test_chat_slug.py`:
  - `test_slug_name_part` parametrized: `"Ravi Cool Services" → "ravi-cool-services"`, `"  A/C & Fridge!! " → "a-c-fridge"`, `"Café Cool" → "cafe-cool"`, `"सेवा" → "chat"`, `"!!!" → "chat"`, `"x" * 50 → "x" * 30`, `"a" * 29 + " b" → "a" * 29` (no trailing `-` after the cut). Assert `slug.rsplit("-", 1)[0] == expected`.
  - `test_slug_random_part`: `make_chat_slug("Ravi")` ends with `-` + 6 chars, all in `SLUG_ALPHABET`.
  - `test_two_slugs_differ`: two calls with the same name give different slugs.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_chat_slug.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement** `make_chat_slug` in `chat_slug.py` (`unicodedata.normalize("NFKD", name)` → drop combining marks → `.lower()` → regex `[^a-z0-9]+` → `-` → strip → cut 30 → strip → fallback `chat`, then `-` + 6 × `secrets.choice(SLUG_ALPHABET)`).
- [ ] **Step 4: Run** the unit tests → PASS.
- [ ] **Step 5: Write the failing integration tests:**
  - `tests/integration/test_chat_slug_table.py` → `test_new_business_gets_a_slug(sign_up_owner)`: the Business row's `chat_slug` matches `^[a-z0-9-]+-[a-hj-km-np-z2-9]{6}$`.
  - Same file → `test_database_refuses_a_duplicate_slug`: insert two Businesses with the same `chat_slug` in their own session (like `test_working_hours_table.insert`) → `IntegrityError` matching `uq_businesses_chat_slug`.
  - `tests/integration/test_migrations.py` → `test_upgrade_gives_old_businesses_a_slug`: downgrade to `0007`, insert a Business by SQL, upgrade to head, its `chat_slug` matches `^chat-[0-9a-f]{6}$`. Follow the file's existing downgrade/upgrade pattern (`test_migrations_downgrade_to_base_and_back`).
- [ ] **Step 6: Run** them → FAIL.
- [ ] **Step 7: Implement** migration `0008` (add column nullable → `UPDATE businesses SET chat_slug = 'chat-' || substr(md5(id::text), 1, 6)` → `alter_column nullable=False` → `create_unique_constraint("uq_businesses_chat_slug", "businesses", ["chat_slug"])`; downgrade drops the constraint, then the column). Add `chat_slug` to the model. `BusinessRepository.add` builds `Business(name=name, chat_slug=make_chat_slug(name))`.
- [ ] **Step 8: Run** the whole backend suite (`uv run pytest`) → PASS.
- [ ] **Step 9: Commit** `feat(business): every Business gets a stable chat slug`.
- [ ] **CHECKPOINT** (CORE): stop; explain the column, the slug rule, and the backfill.

### Task 2: Setup status and the public Chat Page API (CORE — multi-tenancy)

**Files:**
- Modify: `backend/app/modules/business/schemas.py`, `repository.py`, `service.py`, `router.py`
- Modify: `backend/tests/integration/test_tenant_isolation.py`
- Modify: `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (regenerated)
- Test: `backend/tests/integration/test_chat_page.py`

**Interfaces:**
- Consumes: `Business.chat_slug` (Task 1).
- Produces (schemas):
  - `SetupOut(chat_slug: str, has_services: bool, has_working_hours: bool)`
  - `ChatServiceOut(name: str, duration_minutes: int, price_paise: int)`
  - `ChatPageOut(business_name: str, taking_requests: bool, services: list[ChatServiceOut])` (services oldest first, active only)
- Produces (repository): `BusinessRepository.find_by_chat_slug(chat_slug: str) -> Business | None`; `WorkingHoursRepository.has_any() -> bool`.
- Produces (service): `get_setup(session, actor) -> SetupOut`; `get_chat_page(session, chat_slug: str) -> ChatPageOut`. Both use one private `_is_set_up(session) -> tuple[bool, bool]` (has active Services, has Working Hours), called inside a tenant scope. A module constant `_SLUG_SHAPE = re.compile(r"[a-z0-9-]{1,40}")`, used with `fullmatch` on the lowercased input.

- [ ] **Step 1: Write the failing tests** in `tests/integration/test_chat_page.py` (helpers: `sign_up_owner`, a public `client` with no session, `_add_service`/`_put_week` patterns from `test_tenant_isolation.py`). Before each CORE test, tell the user in one line what it checks.
  - `test_new_business_setup_is_not_done`: `GET /api/v1/setup` → 200, `has_services` and `has_working_hours` both False, `chat_slug` = the row's slug.
  - `test_setup_counts_only_active_services`: one inactive Service → `has_services` False; activate it → True.
  - `test_setup_sees_working_hours`: after a PUT with one open day → `has_working_hours` True.
  - `test_setup_is_owner_only`: a Staff-only user → 403 (use `set_owner_roles(business_id, ["staff"])`).
  - `test_chat_page_needs_no_login`: a client with no cookie → `GET /api/v1/chat/{slug}` → 200, `business_name` right.
  - `test_chat_page_lists_active_services`: two active Services → both, in order, with exactly the keys `name, duration_minutes, price_paise` (no ids).
  - `test_inactive_services_are_hidden`: one active + one inactive → only the active one.
  - `test_not_taking_requests_without_services_or_hours`: parametrized (none / services only / hours only) → `taking_requests` False; both → True.
  - `test_bad_slug_is_not_found` `[G3]`: parametrized `"no-such-slug"`, `"%00"` (sent raw in the URL), `"a" * 500`, `"bad slug!"` → each `assert_not_found`.
  - `test_slug_is_case_insensitive`: the real slug in upper case → 200, same `business_name`.
- [ ] **Step 2: Run** `uv run pytest tests/integration/test_chat_page.py -v` → FAIL (route missing).
- [ ] **Step 3: Implement** schemas, the two repository methods, `_is_set_up`, `get_setup` (Role check first), `get_chat_page` (lowercase → `_SLUG_SHAPE.fullmatch` or `NotFound()` → find by slug → `NotFound()` if None → `with tenant_scope(business.id):` list active Services and `_is_set_up`), and the two routes (`responses={401,403}` for setup; `{404}` for chat page). The `get_chat_page` route takes no `ActorDep`, and its comment says why: the tenant comes from the slug only (AD-3 b).
- [ ] **Step 4: Run** those tests → PASS.
- [ ] **Step 5: Add isolation checks** to `ISOLATION_CHECKS` `[G6]`:
  - `("GET", "/api/v1/setup"): check_get_setup` — B adds an active Service and a week; A's setup is still False/False, and A's `chat_slug` ≠ B's.
  - `("GET", "/api/v1/chat/{chat_slug}"): check_get_chat_page` — A adds a Service named `"A only"`, B adds `"B only"` (a `name` override on the `SERVICE` body). Each slug comes from that Owner's own `GET /api/v1/setup`. Owner A's LOGGED-IN client opens B's slug → the Service names are exactly `["B only"]`; A's slug → exactly `["A only"]`. A comment says: this check expects 200 on purpose, not `assert_not_found` — the page is public, and the proof is that the slug, not the cookie, picks the Business.
- [ ] **Step 6: Run** `uv run pytest -m isolation` → PASS (including `test_every_endpoint_is_listed_once`).
- [ ] **Step 7: Regenerate** `openapi.json` and `schema.d.ts` (`uv run python -m app.export_openapi ../frontend/openapi.json` in WSL, then `npm run gen:api` in `frontend`).
- [ ] **Step 8: Run** the whole backend suite → PASS.
- [ ] **Step 9: Commit** `feat(business): setup status and the public Chat Page API`.
- [ ] **CHECKPOINT** (CORE): stop; explain how the slug becomes the tenant, and why the logged-in Owner A still sees B's page.

### Task 3: Duration text (STANDARD)

**Files:** Modify `frontend/src/lib/time.ts`; Test `frontend/src/lib/time.test.ts`

**Interfaces:** Produces `formatDuration(minutes: number): string`.

- [ ] **Step 1: Write the failing test** `formatDuration`: `30 → "30 min"`, `60 → "1 h"`, `90 → "1 h 30 min"`, `480 → "8 h"`.
- [ ] **Step 2: Run** `npx vitest run src/lib/time.test.ts` → FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(app): duration text like 1 h 30 min`.

### Task 4: Copy the chat link — Settings page and Dashboard checklist (STANDARD)

**Files:**
- Create: `frontend/src/components/CopyChatLinkButton.tsx`, `ChatLinkSettings.tsx`, `SetupChecklist.tsx`, `frontend/src/app/app/settings/chat-link/page.tsx`
- Modify: `frontend/src/lib/pages.ts` (new row), `frontend/src/app/app/page.tsx` (render `<SetupChecklist />` under the heading)
- Test: `CopyChatLinkButton.test.tsx`, `ChatLinkSettings.test.tsx`, `SetupChecklist.test.tsx`, `frontend/src/lib/pages.test.ts`

**Interfaces:**
- Consumes: `GET /api/v1/setup` → `SetupOut` (Task 2).
- Produces: `CopyChatLinkButton({ slug: string; label: string })`; `chatPageUrl(slug: string): string` exported from `CopyChatLinkButton.tsx` (`${window.location.origin}/c/${slug}`). The button owns its fallback: on failure it shows the fallback text AND the URL in a read-only, select-on-focus input, so every place that uses it has a way out `[G4]`.

- [ ] **Step 1: Update `pages.test.ts` first (red)** `[G7]`: the exact settings list at `pages.test.ts:80-82` becomes `["Services", "Working Hours", "Chat link", "Team", "Appearance"]`; add `Chat link needs manage_setup` like the test at `:91-95`.
- [ ] **Step 2: Write failing component tests.** Mock `api.GET` as the other component tests do. Mock the clipboard with `Object.assign(navigator, { clipboard: { writeText } })` (`InviteForm.test.tsx:13`). Build expected URLs with `${window.location.origin}`, never a fixed host `[G13]`.
  - CopyChatLinkButton: `copies the full chat URL` (writeText called with `${window.location.origin}/c/ravi-k7m2qx`; the button text becomes `Copied`); `shows a fallback when copy fails` (writeText rejects → `Could not copy. Select the link and copy it.` and a read-only input whose value is the URL); `shows a fallback when there is no clipboard` (`navigator.clipboard` undefined → the same fallback, no crash — so the call sits inside the `try`).
  - ChatLinkSettings: `shows the link and a Copy link button` (the full URL is visible as text; button `Copy link`); `shows an error with retry when loading fails`.
  - SetupChecklist — every test wraps it in `<PermissionsProvider permissions={["manage_setup"]}>` (`SettingsLinks.test.tsx:8-14`), except the last `[G8]`: `shows three steps for a new Business` (`Add Services` links to `/app/settings/services`, `Set Working Hours` to `/app/settings/hours`, `Copy chat link` is NOT a button); `marks done steps` (has_services True → that step has `aria-label` `Add Services, done`); `turns emerald with a Copy chat link button when both are done` (container has class `bg-brand-soft`; button `Copy chat link` exists); `shows nothing without manage_setup` (provider with `[]` → renders null, no API call).
  - Dashboard: `Coming soon.` still shows for a User without `manage_setup` `[G14]` (in `SetupChecklist.test.tsx` or a small `page.test.tsx`; the checklist renders `Coming soon.` in its place when the User lacks `manage_setup` — simplest: the Dashboard page renders `<SetupChecklist />`, and SetupChecklist returns `<p>Coming soon.</p>` instead of null for non-Owners. Adjust the `shows nothing without manage_setup` test to expect only that line).
- [ ] **Step 3: Run** them → FAIL.
- [ ] **Step 4: Implement** the three components (loading = skeleton block as in other settings pages; the checklist hides itself silently on a load error, since the Dashboard is still useful without it), the page (`metadata` title `Chat link · SevaDesk`), and the `PAGES` row.
- [ ] **Step 5: Run** `npx vitest run` (all frontend tests) → PASS. Also `npm run lint` and `npm run typecheck`.
- [ ] **Step 6: Commit** `feat(app): copy the chat link from Settings and the Dashboard checklist`.

### Task 5: The public Chat Page (STANDARD)

**Files:**
- Create: `frontend/src/app/c/[slug]/page.tsx`, `frontend/src/components/ChatPage.tsx`
- Test: `frontend/src/components/ChatPage.test.tsx`

**Interfaces:** Consumes `GET /api/v1/chat/{chat_slug}` → `ChatPageOut` (Task 2), `formatRupees` (`lib/money.ts`), `formatDuration` (Task 3). Produces `ChatPage({ slug: string })`.

- [ ] **Step 1: Baseline first** `[G2]`: create the route page with a stub `ChatPage` that renders only `<main />`. This step needs Task 6's script, so do Task 6 BEFORE Task 5 (order: 0 → 1 → 2 → 3 → 4 → 6 → 5 → 7). Run `npm run build; npm run check:chat-size` and record the baseline total in the learning notes.
- [ ] **Step 2: Write failing tests** (mock `api.GET`):
  - `shows the Business name, Services and the price note`: `h1` = name; each row shows name, `from ₹499`, `1 h`; `Final price after inspection. Parts extra.` once.
  - `always shows the DPDP notice` `[G5]`: exact copy with the Business name, for both `taking_requests: true` and `false`.
  - `shows Not taking requests yet`: `taking_requests: false` → that text, and the Services still show; `taking_requests: true` → that text is absent.
  - `two Services with the same name both show` `[G14]`.
  - `shows not found for an unknown slug`: response status 404 → `Chat page not found` + `Check the link and try again.`; no Business data.
  - `shows an error with retry on other failures`: status 500 → alert + `Try again` button that calls the API again.
- [ ] **Step 3: Run** → FAIL.
- [ ] **Step 4: Implement** `ChatPage` (client component; skeleton while loading; a `<section aria-label="Services & prices">` list keyed by row index; max width `max-w-md`, works from 360 px) and the route page (server component, awaits `params`, `metadata` title `Chat · SevaDesk`). Do not import `lucide-react` or other heavy libraries here (200 KB budget).
- [ ] **Step 5: Run** all frontend tests, lint, typecheck → PASS.
- [ ] **Step 6: Size check** `npm run build; npm run check:chat-size` → under 204,800. If over, apply the Inter `preload: false` fallback (Decisions), re-run, and record both numbers.
- [ ] **Step 7: Commit** `feat(chat): public Chat Page with Services, Prices and the DPDP notice`.

### Task 6: Chat Page size check in CI (STANDARD) — runs BEFORE Task 5

**Files:**
- Create: `frontend/scripts/chat-page-size.mjs`, `frontend/scripts/chat-page-size.test.mjs`
- Modify: `frontend/package.json` (script `"check:chat-size": "node scripts/chat-page-size.mjs"`), `.github/workflows/ci.yml` (test job, after "Frontend tests"), `backend/tests/unit/test_ci_workflow.py`

**Interfaces** `[G10]`: exported pure helpers
- `assetPaths(html: string): string[]` — every `<script src>` WITHOUT a `nomodule` attribute, every `<link rel="stylesheet" href>`, every `<link rel="preload" … href>`; de-duplicated; same-origin paths only.
- `gzipBytes(data: Uint8Array | string): number`
- `measure(baseUrl: string, fetchFn: typeof fetch): Promise<{ total: number; rows: [string, number][] }>` — fetches `${baseUrl}/c/size-check`, then every asset path; throws an error naming the path if any answer is not 200.
- `LIMIT_BYTES = 204_800`; `main()` runs only when `import.meta.url === pathToFileURL(process.argv[1]).href`.

- [ ] **Step 1: Write failing tests** in `chat-page-size.test.mjs`, first line `// @vitest-environment node` (the global environment is jsdom, `vitest.config.ts:9`): `finds scripts, stylesheets and preloads` (sample HTML with 2 scripts, 1 `nomodule` script, 1 stylesheet, 1 font preload, 1 duplicate, 1 inline script → exactly 4 paths, the `nomodule` one absent); `gzipBytes is smaller than the raw size for repeated text`; `measure sums the page and its assets` (a fake fetch); `fails when an asset is missing` (the fake fetch answers 404 for one asset → the error message names that path).
- [ ] **Step 2: Run** `npx vitest run scripts` → FAIL.
- [ ] **Step 3: Implement** the script. `main()` starts the server with NO shell `[G9]`: `spawn(process.execPath, [<resolved path to node_modules/next/dist/bin/next>, "start", "-p", "3999"])`. It waits until `/c/size-check` answers (max 60 s), runs `measure`, prints one row per asset and the total, and stops the server in `finally` (`child.kill()`). It exits 1 if `total > LIMIT_BYTES`.
- [ ] **Step 4: Run** `npx vitest run scripts` → PASS. (`npm test` in CI runs these too: Vitest's default include finds `scripts/*.test.mjs`. ESLint lints `.mjs`; tsc does not check it.)
- [ ] **Step 5: Write the failing CI test** `[G11]` in `test_ci_workflow.py`: `test_ci_runs_the_chat_page_size_check` — the `test` job has a step that runs `npm run build` and, AFTER it, a step that runs `npm run check:chat-size`, both with `working-directory: frontend`. Follow `test_ci_runs_the_isolation_suite` (`:91-96`). Run it → FAIL.
- [ ] **Step 6: Add the CI steps** in the test job: `Build frontend` (`npm run build`) and `Chat Page size check (NFR-6, ≤ 200 KB)` (`npm run check:chat-size`). Run the CI test → PASS.
- [ ] **Step 7: Commit** `ci: fail the build if the Chat Page first load is over 200 KB`. (The local size run happens in Task 5 Step 1, when the `/c/[slug]` route exists.)

### Task 7: Finish

- [ ] Run the whole backend suite (WSL), all frontend tests, lint, typecheck, the size check.
- [ ] Manual check with the compose stack: sign up → Dashboard checklist (3 steps) → add a Service and hours → checklist emerald → copy → open the link in a private window → page shows name, Services, DPDP notice. Open `/c/nope` → not found. Check that the `GET /api/v1/chat/{chat_slug}` span shows in the traces (Definition of Done: "Traces visible", `docs/project-seed.md`) `[G12]`. Stop the stack after.
- [ ] Set `3-3-share-the-chat-page-link: done` in `_bmad-output/implementation-artifacts/sprint-status.yaml` on this branch.
- [ ] One Opus whole-branch review (CLAUDE.md §4); fix findings with regression tests.
- [ ] Push the branch, open the PR (body ends with `Closes #16`), wait for the 4 green checks `[G12]`.
- [ ] Then `docs/agents/after-story.md`; as the LAST story of Epic 3, also update `docs/learning/architecture-map.md` and ask the user to explain the system in 5 sentences.
