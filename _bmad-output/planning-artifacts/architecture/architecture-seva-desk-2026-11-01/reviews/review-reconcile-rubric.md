---
title: 'Review: reconcile + rubric — SevaDesk architecture spine'
reviewed: _bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md
inputs:
  - docs/project-seed.md
  - _bmad-output/planning-artifacts/prds/prd-seva-desk-2026-11-01/prd.md
  - _bmad-output/planning-artifacts/prds/prd-seva-desk-2026-11-01/addendum.md
  - _bmad-output/planning-artifacts/ux-designs/ux-seva-desk-2026-11-01/DESIGN.md
  - _bmad-output/planning-artifacts/ux-designs/ux-seva-desk-2026-11-01/EXPERIENCE.md
  - .memlog.md (decision log)
date: 2026-11-01
reviewer: independent (reconcile + rubric)
---

# Review — SevaDesk Architecture Spine

## Verdict

**Not ready to hand to epics/stories yet; close.** The spine is strong on the big shape: modular monolith, tenant scoping, one origin, worker-based agent, a single booking write path, owned state machines, and a generated API contract. But one AD contradicts the PRD's data model (multi-role users), and several real divergence points are still open: Chat Page identity, the Message shape, agent job concurrency, the live-update contract, the eval/test AI path, and the free-tier budget for Redis/Postgres. All are fixable with small additions. None needs a paradigm change.

Known drift ignored on purpose: the seed and addendum still name Vercel. The decision log drops it on purpose (AD-6). This is not a finding.

Severity scale: **critical** = contradicts a requirement or forces a schema rewrite; **high** = two stories will very likely build it two ways, or a hard constraint (budget, security) breaks; **medium** = a likely gap that a story can close if told to; **low** = polish.

---

## Part 1 — Reconcile (requirements and quiet constraints vs spine)

### R-1 (critical) — Multi-role users contradict AD-4

- **Source:** PRD Glossary "Role" (one User can hold several Roles; a solo owner holds all three), FR-7 (sign-up gives Owner + Technician), FR-9 (invite with one or more Roles), EXPERIENCE nav ("Technician-only Users").
- **Spine:** AD-4 `memberships(user_id, business_id, role)`. That is one role per membership, and the unique constraint on `user_id` means one membership per user. So a user can hold exactly one role.
- **Impact:** the accounts story builds a single `role` column. The bookings story needs "count of active Technicians" (FR-17 capacity) and finds that a solo Owner is not a Technician. Fixing it later is a schema change plus every role check.
- **Fix:** amend AD-4: `memberships(user_id, business_id, roles[] or is_owner/is_staff/is_technician booleans, is_active)`. State that **capacity = count of active memberships with the Technician role** (addendum "Slot calculation"). Add `is_active` for FR-10 "deactivate". Name one backend helper (`require_roles(...)` in `accounts`/`core`) as the only way to check roles.

### R-2 (high) — Technician-only data scoping has no owner

- **Source:** FR-10 (Technician sees only own assigned Bookings), FR-26 (Technician sees only own Bookings in Calendar), EXPERIENCE IA (Calendar is the Technician default; Booking detail read-only).
- **Spine:** AD-3 covers tenant scoping. It says nothing about *row scoping by role inside a tenant*. AD-5 says "role checks happen in the backend only", but not where.
- **Impact:** Calendar, Booking detail, and Dashboard stories each add their own `technician_id = me` filter, or forget it. This is the same "forgotten filter" divergence AD-3 exists to prevent, one level down.
- **Fix:** add to AD-10 or a new AD: "`bookings` front-door read functions take the caller's membership. For a caller without Owner/Staff, they always filter to `technician_membership_id = caller`. No router filters by role itself." Add a role-scoping case to the isolation suite (Technician A cannot read Technician B's Booking → 404).

### R-3 (high) — Chat Page identity and "return from the same browser" are undefined

- **Source:** FR-15 (return later to the same Conversation from the same browser; no account), PRD §10 assumption (a browser token links a Customer to a Conversation; a new device starts a new Conversation), Glossary (Customer is identified by phone within one Business), NFR-5 (rate limit per Conversation).
- **Spine:** AD-3 resolves the *tenant* from the chat slug. Nothing says how a public request proves *which Conversation* it may read or write. AD-7's `GET … ?after=<cursor>` does not say what the key is.
- **Impact:**
  - Security: if public endpoints take `conversation_id` from the URL, anyone who learns or guesses an id can read another Customer's chat (name, phone, address). UUIDv7 ids are time-ordered, so they are partly guessable.
  - Divergence: the inbox story may create the Customer at the first message (phone unknown); the agent story may create it when the phone is collected. Then "Customer identified by phone" merges or duplicates rows differently.
- **Fix:** add an AD "Public chat identity": the first Chat Page visit gets a random opaque **visitor token** in an `httpOnly` cookie scoped to `/c/{slug}` and to the API path, stored hashed and owned by `inbox`. Every public chat endpoint resolves `slug → business` and `token → conversation`. It never accepts a `conversation_id` from the client. Also fix the Customer lifecycle: a Customer row is created with the Conversation (phone nullable); when the agent collects a phone, `inbox` links or merges by `(business_id, phone)`. Rate-limit keys: IP and visitor token.

### R-4 (high) — The "within 5 seconds" contract is weakened, and the booking-status path is ambiguous

- **Source:** FR-24 (new Messages within 5 s), FR-25 (Chat Page shows new status and time within 5 s), EXPERIENCE ("polling every 5 s while visible", "Reconnecting…" after 3 failures; Dashboard is also live), UJ-1/UJ-4 climax (Confirm → Chat Page updates within 5 s).
- **Spine:** AD-7: fast (≈1–2 s) while a reply is pending, "slower when idle", stopped when hidden. "Slower" has no upper bound. The confirm in UJ-1 happens when the Chat Page is *idle* (no reply pending). So "slower" can break the 5 s promise in the key demo moment.
- **Second gap:** AD-7 polls *messages after a cursor*. A Booking confirm/decline/expiry is a *state change in `bookings`*, not a message. The spine does not say whether a status change writes a status Message into the Conversation, or whether the Chat Page also polls Booking state. Two stories will pick differently. The Dashboard is also live per EXPERIENCE ("Stale data | Inbox, Dashboard") but is not named in AD-7.
- **Fix:** amend AD-7: "Idle interval is at most 5 s while the tab is visible; 1–2 s while a reply is pending; paused when hidden; 'Reconnecting…' after 3 failed polls." And pick one status path. Recommended: every Booking state change that the Customer must see makes `inbox` write a **status event Message** (`author_type = system`, with `booking_id` and the new state). Then the one cursor poll carries both chat and status. Name Dashboard as a polling screen too.

### R-5 (high) — The Message shape is not fixed, but UX and FR-16a depend on it

- **Source:** EXPERIENCE (quick-reply chips on the last Agent Message; up to 4 Slot chips plus "Other times"; a User reply shows the User's name; Agent labeled "SevaDesk assistant"; Hindi Messages carry `lang="hi"`; "Not sent · Retry"), FR-16a (no Booking Request unless the Customer *accepted the Price in that Conversation*; store the Price seen).
- **Spine:** the ER diagram has `messages` with no fields. AD-8's post-check scans free text for Prices and Slots.
- **Impact:**
  - The Chat Page story, the agent story, and the inbox story will each invent fields for author, chips, and language.
  - FR-16a "accepted" has no defined evidence. One story may let the LLM decide; another may require a chip tap.
  - The AD-8 post-check on free text is fragile in Hindi and Hinglish ("₹1,499", "1499 रुपये", "कल सुबह 10 बजे").
  - Retry after "Not sent" can create duplicate Messages without an idempotency key.
- **Fix:** add a convention row or AD for Message: `author_type (customer|agent|user|system)`, `author_membership_id`, `body`, `lang`, `client_message_id` (idempotency for retry), and `actions[]` (chips). Each chip has a kind (`service`, `accept_price`, `slot`) and a server-issued reference (service_id, slot start/end). Rule: Slots and Prices shown as chips come only from tool results. `create_booking_request` takes `service_id` and slot, and **derives `price_paise` from the Service record on the server**. It never takes a price from the model. "Price accepted" is recorded as a structured event (chip tap or an agent tool call `record_price_acceptance(service_id)`) that `bookings` checks before it creates the request. Then AD-8's post-check can compare structured parts, not parse free text.

### R-6 (high) — Agent jobs have no concurrency, idempotency, or timeout rule

- **Source:** FR-21 (no Agent Message during Handoff), FR-22 (fallback on failure *or timeout*), NFR-3 (reply within 10 s p95), NFR-7 (cost cap).
- **Spine:** AD-7 enqueues one `agent_reply` job per Customer Message. AD-10 says the worker checks state before replying.
- **Gaps:**
  - Two quick Customer Messages make two jobs. Two concurrent agent runs on one Conversation give duplicate or crossed replies, and two AI calls.
  - A User can take over *while* a job runs. A check only "before" lets the Agent post into a Handoff.
  - arq retries a failed job by default. That repeats AI calls (cost) and can repeat `create_booking_request`.
  - No AI timeout value is set, so "timeout" in FR-22 is undefined.
- **Fix:** add to AD-7: one job per Conversation at a time (arq `_job_id = agent_reply:{conversation_id}`, or a Redis lock); the job answers *all* unanswered Customer Messages; state is re-checked through `inbox` **before saving** the Agent Message, not only before calling the model; no automatic retries for `agent_reply` (FR-22 fallback instead); AI call timeout ≈ 8 s total so the 10 s p95 holds; `create_booking_request` is idempotent per `(conversation_id, slot, service)`.

### R-7 (high) — Eval gating and the test AI path are not specified

- **Source:** seed "AI Evals" (golden set EN+HI; code checks first; LLM-as-judge for tone; block merge if score drops; smoke set per PR, full set nightly or on demand), FR-5 (score per check; fail below stored baseline; placeholder in P0), NFR-2, FR-30 (cases use seeded demo Businesses), NFR-10 (Playwright E2E for UJ-1–UJ-3), cost guardrails (Haiku for most evals).
- **Spine:** the pipeline has an "evals smoke set (Claude)" step. AD-12 records prompt versions. Nothing else.
- **Gaps that let stories diverge:**
  - How the eval runner calls the agent. Through the real `agent` service and tool handlers against a seeded Testcontainers DB? Or a copy of the prompt? Only the first tests what ships.
  - Where the baseline lives (a file in the repo, per check), and what "drop" means (any drop, or a tolerance).
  - Which model is the judge, and whether judge scores gate or only report.
  - The smoke-set size and nightly full set (a scheduled workflow).
  - Playwright E2E and integration tests need a **deterministic fake AI adapter**. Otherwise E2E costs money and flakes. AD-11 names only Claude and Groq.
  - Claude API key in CI: fork PRs must not get it, and the spend must fit the $2–5/month AI budget.
- **Fix:** add an AD "Eval and test AI path": `evals/` runs the real agent loop through the `agent` front door against the seeded demo Businesses (FR-29) in Testcontainers; baseline per check in `evals/baseline.json`, updated only by a reviewed PR; gate = code checks; judge = cheap Claude model, report-only at first (or gated with a tolerance); smoke set ≈ 10 cases per PR, full set on a nightly/manual workflow; a `fake` AI adapter (scripted responses) is selected by env for unit, integration, and E2E tests; Claude evals run only on same-repo PRs.

### R-8 (high) — Free-tier budget risk: Redis commands and Postgres compute

- **Source:** seed budget (under $10/month total, hard), Track A free tiers (Neon/Supabase, Upstash), NFR-7, NFR-3 (500 ms p95 API).
- **Spine:** arq worker on Upstash Redis; a scheduled expiry job; Redis counters for caps and (likely) rate limits; 1–5 s polling on Neon.
- **Risks (verify current free-tier limits when deciding):**
  - arq polls Redis constantly (default `poll_delay` 0.5 s). That alone can be well over 100k commands a day. Upstash's free tier has a monthly command quota. Each rate-limited poll request adds more Redis commands.
  - Neon's free tier suspends idle compute and limits compute hours. A frequent cron (for example, every minute) plus polling keeps compute awake around the clock. Cold starts after a suspend can also break the 500 ms p95. Supabase's free tier pauses projects after a period of inactivity.
- **Fix:** add a "Free-tier budget" decision with a short command and compute calculation. Options: run Redis as a container in the demo docker-compose on the Oracle VM (the ARM Always Free shape has enough RAM; this conflicts with the seed's "no self-hosting", so ask the user), or raise arq `poll_delay` and keep rate-limit counters cheap. Make expiry **lazy on read** (a request older than 12 h counts as expired in every query) plus an infrequent sweep (for example, every 15–30 min). That keeps FR-18a exact without a per-minute cron.

### R-9 (medium) — Rate limiting has no mechanism, keys, or client-IP rule

- **Source:** FR-8 (wrong passwords rate-limited per account and per IP), NFR-5 (rate limits on log-in and the public Chat Page, per IP and per Conversation), seed (rate limiting, input validation).
- **Spine:** `core` owns "rate limiting"; AD-7 says poll endpoints are rate-limited.
- **Gaps:**
  - Behind Caddy or the ALB, the app sees the proxy's IP. "Per IP" limits then throttle everyone together unless the app trusts `X-Forwarded-For` from the proxy only.
  - No storage (Redis) or algorithm is named.
  - The limits must allow the AD-7 poll cadence (1 req/s while pending), or the Chat Page throttles itself.
  - Message-send limits (AI cost abuse on the public demo) are not separated from poll limits.
- **Fix:** add a `core` convention: one rate-limit dependency backed by Redis (fixed or sliding window); keys `ip`, `account`, `visitor_token`; trusted-proxy config per environment (Caddy, ALB); separate budgets for `login`, `chat_send`, and `chat_poll`; limits documented next to the poll intervals.

### R-10 (medium) — Observability: worker health, trace propagation, errors, alerts

- **Source:** FR-2 (`GET /health` for backend *and worker*; 503 when DB or Redis is down), FR-4 (one trace through frontend, backend, worker, DB), NFR-4 (error tracking; dashboards and alerts for errors and Agent cost), seed (health checks, error tracking, basic dashboards and alerts).
- **Spine:** OTel, JSON logs, Langfuse, Grafana Cloud. AD-7's job payload holds only `business_id` and `conversation_id`.
- **Gaps:**
  - **Path conflict:** AD-6 routes only `/api/*` to FastAPI, and AD-14 puts routes under `/api/v1`. FR-2's `GET /health` would go to Next.js. Pick `/api/health` (and update FR-2) or add a proxy rule.
  - The worker has no HTTP server. How is it health-checked (heartbeat key in Redis read by `/api/health`, or a container health command)? ECS and compose need a defined check.
  - A trace from the API to the worker needs the W3C `traceparent` in the job payload. Without it, FR-4's single trace breaks at the queue.
  - Frontend spans (FR-4 "through the frontend") are not decided: Next.js server instrumentation, browser, or both.
  - No decision on error tracking (Grafana alerts on error logs, or a free error tracker), or on the two alerts NFR-4 asks for (error rate; Agent cost per day).
- **Fix:** add to AD-12 or a new "Observability" AD: job payloads carry `traceparent`; worker writes a Redis heartbeat; `/api/health` checks DB, Redis, and worker heartbeat; Next.js server is OTel-instrumented (browser spans deferred); two named Grafana alerts (5xx/error-log rate; daily Agent cost from Langfuse or a metric); OTLP export goes straight from each container to Grafana Cloud (no collector) in demo.

### R-11 (medium) — DPDP: masking point, Langfuse contents, retention, Groq guard

- **Source:** NFR-8 (no phone numbers or addresses in plain text in logs and traces; delete Customer with all Conversations and Bookings; notice before first Message), NFR-7 / seed (Groq gets fake data only).
- **Spine:** AD-13 masks logs, traces, and Langfuse payloads; deletion through front doors. AD-11 "Groq gets fake data only".
- **Gaps:**
  - The agent *collects* phone and address on purpose, so the full prompt and response sent to Langfuse contain them. AD-13 does not name *one* place where masking happens. If each story masks its own log lines, one will forget.
  - Customer delete does not reach Langfuse or Grafana. With masking that may be fine, but say so, and set a retention period.
  - "Groq gets fake data only" is not enforceable as written.
- **Fix:** name one masking function in `core` used by (a) a logging filter, (b) an OTel span processor, (c) the Langfuse client wrapper in the AI port. Add an isolation-style test: a seeded phone number never appears in captured logs or traces. State Langfuse/Grafana retention. Make AD-11 enforceable: "the Groq adapter refuses to start unless `APP_ENV` is `local` or `ci`".

### R-12 (medium) — Demo mode operations and public-demo abuse

- **Source:** FR-29 (two seeded Businesses with demo logins in demo and AWS; a reset command; no real data), UJ-4 (AWS URL works with seeded data after one deploy command), FR-31 (landing links to a demo Chat Page and a demo Owner log-in).
- **Spine:** `demo` holds seed scripts that call front doors.
- **Gaps:**
  - How the seed and reset run in each environment (compose exec on the Oracle VM, an ECS one-off task after `terraform apply`, a pipeline step). UJ-4 needs seeding to be part of the one deploy command.
  - Reset spans many tenants. Under AD-3 it must loop per Business with tenant context set; say so.
  - The demo login is public. Visitors can change the demo password, deactivate Services, delete Customers, or burn Claude spend through the Chat Page. Nothing protects the demo.
- **Fix:** add a `demo` rule: seed and reset are one CLI command run per Business with tenant context; the deploy pipeline (demo and AWS) runs it after migrations if the demo Businesses are missing; demo accounts cannot change password or team; a scheduled reset (for example, nightly) restores data; daily Agent cap (200) plus the Anthropic console limit bound cost.

### R-13 (medium) — Cross-tenant jobs and AD-3 wording

- **Source:** NFR-1 (no API endpoint *or background job* crosses Businesses), FR-18a (expiry).
- **Spine:** AD-3 says worker jobs take `business_id` from the payload. AD-10 has a scheduled expiry job, which by nature sweeps all Businesses.
- **Impact:** the expiry story either breaks AD-3 (one cross-tenant query) or invents a pattern.
- **Fix:** add to AD-3: "Scheduled jobs list Business ids through `business` (a global read), then run one unit of work per Business with tenant context set." (Or use the lazy-expiry approach from R-8, which removes most of this.)

### R-14 (medium) — AD-9 locks a table it does not own

- **Source:** AD-1/AD-2 (one owner per table; never query another module's tables).
- **Spine:** AD-9 runs `SELECT … FOR UPDATE` on the Business row from `bookings`. `businesses` is owned by `business`.
- **Fix:** either `business` exposes `lock_business_for_capacity(session)` as a front-door function, or `bookings` owns a small `booking_locks(business_id)` row it locks. The second keeps `bookings` self-contained. State that the lock, the capacity count (Technicians from `accounts`), and the write share one DB session and transaction.

### R-15 (medium) — Low-bandwidth Chat Page needs a rendering decision and a budget check

- **Source:** NFR-6 (Chat Page first load under 200 KB compressed), FR-31 (landing under 1 MB), DESIGN/EXPERIENCE (no images, no glass, Inter subset, Devanagari font only on demand; shadcn/ui on Next.js + Tailwind).
- **Spine:** Next.js, render-only. Data-fetching library and UI kit deferred.
- **Gaps:** Next.js + React already uses a large share of 200 KB. The spine does not say how the Chat Page stays small (Server Components with one small client island for the chat; no component kit or data library on that route), how Next.js fetches data (browser calls `/api` with the cookie, or server-side fetch that forwards the cookie to an internal URL), or how the budget is checked.
- **Fix:** add a "Frontend" AD: app screens fetch in the browser through the generated client (same origin, cookie sent automatically); the Chat Page and landing render on the server with minimal client JS; one shared polling hook used by Chat Page, Inbox, Conversation, and Dashboard; a CI check fails if the Chat Page first-load bundle exceeds 200 KB compressed (and landing exceeds 1 MB).

### R-16 (medium) — Same images on ARM (Oracle) and x86 (Fargate)

- **Source:** FR-1 / seed (the same Docker images run locally, on demo, and on AWS).
- **Spine:** "The same Docker images run in every environment." Demo on Oracle Always Free. The Always Free shape with enough RAM for Next.js + FastAPI + worker + Caddy is Ampere (ARM64). Fargate defaults to x86_64. The image registry is not named.
- **Fix:** decide: build multi-arch images (`linux/amd64,linux/arm64`) with buildx in CI, *or* run Fargate on ARM64 (Graviton) so one arch serves both. Name the registry (GHCR is free; ECR for AWS, or pull from GHCR). Say how the pipeline deploys to the Oracle VM (SSH + `docker compose pull && up`).

### R-17 (low) — Smaller gaps

- **Session idle timeout** (FR-8 "sessions expire after inactivity"): AD-5 does not set the idle period or the sliding renewal. Add one line (for example, 7 days idle, renewed on use).
- **CSRF:** same origin plus `SameSite=Lax` blocks most cross-site writes. Say that state-changing routes accept only JSON (`Content-Type: application/json`) so form-based CSRF cannot reach them.
- **Theme saved per User** (EXPERIENCE "saved per User"): needs a user preference field owned by `accounts`. Tiny, but name it, or decide `localStorage` and update UX.
- **Daily cap day boundary** (AD-12): per Business day in the Business timezone, or UTC? Pick one.
- **AWS deploy trigger:** the pipeline shows "manual approval → aws-staging", but aws-staging usually does not exist (destroyed). Make it a manually triggered workflow: `terraform apply` → migrate → seed → deploy → E2E smoke (SM-1), with a separate `destroy` workflow plus a "no billable resources left" check (FR-6).
- **Migrations during deploy:** the old version keeps running while `alembic upgrade head` runs. State "migrations are backward compatible with the previous release (expand, then contract)".
- **Coverage gate** (seed, NFR-10): no threshold is set. Pick one (for example, 80% backend lines) so stories do not argue it.
- **Backups and restore:** not mentioned. Demo data is reseedable, so "no backups; reseed" is a valid decision. Write it down.
- **DNS/TLS for the demo:** Caddy needs a domain for automatic TLS. Name it (a free subdomain or the builder's domain).
- **Message size limit and input validation** for the public chat (NFR-5): one max length in `inbox`.

---

## Part 2 — Rubric

### 2.1 Does it fix the real divergence points for epics/stories, and miss none?

**Fixed well:** code placement (AD-1), cross-module access (AD-2), tenant source and scoping (AD-3), auth scheme (AD-5), origin/CORS (AD-6), where AI runs (AD-7), agent facts via tools (AD-8), booking write path (AD-9), state ownership (AD-10), provider boundaries (AD-11), prompt versioning and tracing (AD-12), API contract and error envelope (AD-14), and the conventions table (IDs, money, time, naming, config, migrations). The dependency-direction fix (`bookings` never imports `inbox`) is a good catch.

**Missed divergence points:** multi-role memberships (R-1), role-based row scoping (R-2), Chat Page visitor identity and Customer lifecycle (R-3), status-update path and poll intervals (R-4), Message shape, chips, and price acceptance (R-5), agent job concurrency and idempotency (R-6), eval runner and fake AI adapter (R-7), rate-limit keys (R-9), masking point (R-11), cross-tenant scheduled jobs (R-13), frontend data and polling pattern (R-15).

**Result: partial.** Most core rules are in place. About ten real divergence points are open.

### 2.2 Is every AD Rule enforceable, and does it prevent its stated divergence?

| AD | Enforceable? | Prevents its divergence? | Note |
| --- | --- | --- | --- |
| AD-1 | Yes (review, folder layout) | Yes | — |
| AD-2 | Only by review as written | Yes, if enforced | Add `import-linter` contracts in CI so a forbidden import fails the build. |
| AD-3 | Yes (isolation suite, base repo) | Mostly | Add scheduled-job rule (R-13) and role scoping (R-2). |
| AD-4 | Yes | **No: it encodes the wrong model** | Single `role` contradicts multi-role users (R-1). |
| AD-5 | Yes | Mostly | Add idle timeout and the role-check helper. |
| AD-6 | Yes | Yes | Conflicts with FR-2's `/health` path (R-10). |
| AD-7 | Partly | Partly | "Slower when idle" has no bound and can break the 5 s rule; status path open; no job concurrency rule (R-4, R-6). |
| AD-8 | Weak | Partly | A free-text post-check is hard to make reliable in Hindi/Hinglish; price comes from the model unless the tool derives it (R-5). |
| AD-9 | Yes (integration test with concurrent requests) | Yes | But it breaks AD-2 by locking `businesses` (R-14). |
| AD-10 | Yes | Mostly | Add re-check before save (R-6) and lazy expiry (R-8). |
| AD-11 | Partly | Partly | "Groq gets fake data only" has no enforcement (R-11); no fake adapter for tests (R-7). |
| AD-12 | Yes | Yes for tracing | Cap day boundary unset; no cost alert (R-10, R-17). |
| AD-13 | Weak | Partly | No single masking point; no test (R-11). |
| AD-14 | Yes (generation in CI; diff check) | Yes | Add a CI step that fails if the generated client is stale. |

### 2.3 Could anything under Deferred let two units diverge?

- **"Frontend state and data-fetching library, UI component kit — left to the first frontend story": yes, this can diverge.** The UX spec has already fixed shadcn/ui, so the UI kit is not open; record it. The data-fetching/polling pattern is used by four screens (Chat Page, Inbox, Conversation, Dashboard) built in different stories. Deferring it invites two patterns. Decide it now, or bind "the first frontend story's choice is binding for all later stories, through one shared polling hook" (R-15).
- **"Exact Claude and Groq model ids — set in env":** safe for code, but the eval baseline is only valid for one model. Add: "a model change re-records the eval baseline in the same PR."
- **RLS, exclusion constraint, SSE/WebSockets, event bus, separate `customers` module, multi-business users, payments, WhatsApp/SMS:** safe. Each has a trigger condition and no story needs it in the MVP. Note: the "multi-business users" deferral is fine only after R-1 is fixed. Lifting the `user_id` unique constraint is easy; changing single role to multi-role is not.

### 2.4 Is every dimension the altitude owns decided, deferred, or an open question?

| Dimension | Status | Missing |
| --- | --- | --- |
| Deployment / environments | Mostly decided | CPU arch and registry (R-16); demo deploy mechanism; AWS deploy as a manual workflow; seeding in deploy (R-12); DNS/TLS (R-17). |
| Infrastructure | Mostly decided | Free-tier quota check for Redis and Postgres (R-8). |
| Operations | Thin | Demo reset/abuse (R-12), backups (R-17), migration compatibility (R-17), runbook for destroy check (FR-6). |
| Observability | Partly | Worker health, `/health` path, trace propagation through jobs, frontend spans, error tracking, alerts (R-10). |
| Testing | Partly | Eval runner, baseline, judge, smoke vs nightly, fake AI adapter, coverage threshold, where E2E runs (R-7, R-17). |
| Security | Partly | Chat Page identity (R-3), rate-limit keys and trusted proxy (R-9), CSRF statement, session idle (R-17), Groq guard (R-11), demo-account limits (R-12). |
| Frontend | Thin | Rendering and fetch strategy, polling hook, bundle-size check, theme persistence (R-15, R-17). |
| Data | Mostly decided | Multi-role (R-1), Message shape (R-5), Customer lifecycle (R-3). |
| AI | Mostly decided | Job concurrency and timeout (R-6), structured price acceptance (R-5), open question "which Claude model and cost per Conversation" (PRD §9) is not carried as an open question in the spine; add it. |

The spine has no **Open Questions** section. PRD §9 (model choice and cost per Conversation) should appear there, plus any R-items the user wants to decide later (for example, R-8 Redis hosting).

---

## Top fixes in priority order

1. **R-1** Amend AD-4 for multi-role memberships with `is_active`; define capacity as active Technician memberships. *(critical)*
2. **R-3** Add a "Public chat identity" AD: visitor token cookie → Conversation; never accept `conversation_id` from the public client; fix the Customer lifecycle. *(high)*
3. **R-4 + R-6** Tighten AD-7: idle poll at most 5 s; Booking status changes become system Messages; one agent job per Conversation; re-check state before save; no auto-retry; AI timeout about 8 s. *(high)*
4. **R-5** Fix the Message shape (author type, lang, chips, client id) and make price acceptance and `price_paise` server-derived and structured. *(high)*
5. **R-7** Add an "Eval and test AI path" AD: real agent loop on seeded DB, baseline file, judge policy, smoke/nightly split, fake adapter for tests. *(high)*
6. **R-8** Check Upstash and Neon free-tier quotas against arq polling and cron; choose self-hosted Redis on the VM or tuned polling; lazy expiry. *(high)*
7. **R-2, R-9 – R-16** Medium items, then R-17 low items. Add an Open Questions section.
