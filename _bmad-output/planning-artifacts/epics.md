---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, step-04-final-validation]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-seva-desk-2026-11-01/prd.md
  - _bmad-output/planning-artifacts/prds/prd-seva-desk-2026-11-01/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/ux-designs/ux-seva-desk-2026-11-01/DESIGN.md
  - _bmad-output/planning-artifacts/ux-designs/ux-seva-desk-2026-11-01/EXPERIENCE.md
  - docs/project-seed.md
---

# SevaDesk - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for SevaDesk, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

**P0 — Walking skeleton**

- FR-1: A visitor opens the frontend and sees a value that the backend read from the database, plus the backend version. The same Docker images run on local, demo, and AWS staging; only env vars change.
- FR-2: `GET /health` returns 200 when the database and Redis are reachable, and 503 when one is not. The worker has its own health check.
- FR-3: Each PR runs lint → tests → evals (smoke) → build. A merge to main also deploys to demo. A failing step blocks the merge. Migrations run in the pipeline before the new version starts.
- FR-4: One request is traceable through frontend, backend, worker, and database in a single trace. Every log line is JSON with a request ID and a trace ID. Traces, logs, and metrics reach the free observability tier.
- FR-5: The builder runs Evals locally and in CI against the Golden Dataset and gets a score per check. CI fails when the score drops below the stored baseline. In P0, one placeholder Eval proves the pipeline.
- FR-6: One command creates the full AWS staging environment; one command removes all of it. After deploy, a public AWS URL serves the same app as demo. After destroy, no billable resource remains (script check). An AWS budget alert fires at $5.

**P1 — Accounts, Businesses, Roles**

- FR-7: Sign-up with email and password creates a Business and a User with Owner + Technician Roles. The Owner can turn the Technician Role off.
- FR-8: A User logs in and logs out. Sessions expire after inactivity. Wrong passwords are rate-limited per account and per IP.
- FR-9: An Owner invites a person by email with one or more Roles. The Owner copies the invite link (no emails sent). The link works once and expires after 7 days. The person sets a password on accept.
- FR-10: Role-based access per the PRD table (Owner: setup + team; Owner/Staff: Inbox, approve Bookings, Dashboard; all: own assigned Bookings). A forbidden action returns 403 and changes nothing.
- FR-11: A User reads and changes only their own Business's data. A request for another Business's record returns 404. Automated tests try cross-Business access on every endpoint; all must fail.

**P1 — Business setup**

- FR-12: An Owner adds, edits, and deactivates Services: name, duration 30–480 min, Price (required). A Service cannot be saved or activated without a Price. The Agent states Prices only as "from ₹X", with "final amount quoted on site".
- FR-13: An Owner sets weekly Working Hours (per day: closed, or start and end) and marks single days closed (holidays).
- FR-14: Each Business has one Chat Page with a stable, shareable link that the Owner can copy. The Chat Page shows the Business name and the DPDP notice.

**P1 — Customer chat and AI Agent**

- FR-15: A Customer opens the Chat Page, sends Messages, and returns later to the same Conversation from the same browser. No account. Works on a slow mobile connection.
- FR-16: The Agent collects name, phone, address, problem description, and matching Service before it offers Slots. It asks only for missing details. It validates the phone as an Indian mobile number.
- FR-16a: Before Slots, the Agent shows the chosen Service's Price and the Customer accepts it. No Booking Request without an accepted Price in that Conversation. The Booking Request stores the Price seen. The Chat Page lists all active Services with Prices above the chat.
- FR-17: The Agent offers only Slots the system calculates as free for the chosen Service: inside Working Hours, and overlapping confirmed + requested Bookings < active Technicians. If no Slot is free in the next 7 days, the Agent says so and offers a Handoff.
- FR-18: When the Customer picks a Slot, the system creates a Booking Request and holds the Slot. If the Slot was just taken, the Agent apologizes and offers new Slots. The Agent says the Business will confirm and the status shows on the Chat Page.
- FR-18a: A Booking Request not confirmed or declined within 12 hours expires and frees its Slot. The Chat Page shows "Not confirmed. Please contact the business." and allows a new request in the same chat. The expired request stays visible in the Inbox. The Dashboard shows time left on each waiting request.
- FR-19: The Agent replies in the language of the Customer's last Message: English or Hindi (Devanagari or Roman). Other languages get a short English reply and a Handoff.
- FR-20: The Agent never states a Price, Slot, opening time, or policy not in Business data. For unknown questions it says the Business will answer and offers a Handoff.
- FR-21: The Agent hands off when the Customer asks for a person, when it fails to understand twice in a row, or when the topic is out of scope (complaints, refunds). During a Handoff, the Agent sends no Messages. A User can give the Conversation back to the Agent.
- FR-22: If the AI service fails or times out, the Customer gets "We got your message. The team will reply soon." and the Conversation goes to Handoff.

**P1 — Inbox**

- FR-23: Inbox lists Conversations, newest activity first, Handoff first. Each row: Customer name or phone, last Message, time, state (Agent / Needs Human / Booking Request).
- FR-24: A User opens a Conversation, reads full history, and replies. The reply appears on the Chat Page. Replying starts a Handoff. New Messages appear without reload within 5 seconds.

**P1 — Bookings and Calendar**

- FR-25: A User with Inbox access confirms a Booking Request, changes its Slot or Technician then confirms, or declines with a reason. Decline frees the Slot and the Chat Page shows it. Confirm needs a free Technician; with one active Technician, the system assigns that one. The Chat Page shows the new status within 5 seconds.
- FR-26: Day and week Calendar views of Bookings. A Technician sees only their own. Works at 360 px.
- FR-27: A User with Inbox access creates a Booking for a phone-in Customer, cancels a Booking, and marks a Booking completed.

**P1 — Dashboard, demo, dataset, landing**

- FR-28: The Owner sees today's confirmed Bookings, waiting Booking Requests, Conversations in Handoff, and counts of new Conversations and confirmed Bookings this week. Each item links to its detail. No revenue.
- FR-29: Demo and AWS start with at least two seeded demo Businesses (one solo, one team), fake data, and demo logins. A command resets demo data. No real personal data.
- FR-30: The builder turns Scenario Cards into draft conversations with an LLM, reviews them, and saves approved cases in the repo. Each case stores conversation, language, expected details, expected Service and Price shown, and expected result. Only reviewed cases enter. First version ≥ 30 cases, about half English and half Hindi/Hinglish, covering happy paths, missing details, Price and discount questions, no free Slot, request for a person, unsupported language. Uses seeded demo Businesses and fake data.
- FR-31: A public landing page at `/` explains SevaDesk and links to a demo Chat Page, a demo Owner log-in, and the GitHub repo. It shows how SevaDesk is built (tests, Evals, tracing, AWS deploy), no pricing. Under 1 MB on mobile. Animations stop under reduced motion.

### NonFunctional Requirements

- NFR-1 Tenant isolation: no API endpoint or background job reads or writes across Businesses. FR-11 tests run in CI on every PR.
- NFR-2 Agent quality gates: Evals on the Golden Dataset (English + Hindi). Code checks first (detail extraction, correct Booking, no invented Prices/Slots, language match), then an LLM judge for tone. A score drop blocks the merge.
- NFR-3 Response time: Agent reply reaches the Chat Page within 10 s in 95% of cases on demo. Other API calls answer within 500 ms at p95.
- NFR-4 Observability: every Agent call records prompt version, model, tokens, cost, and latency in the LLM tracing tool, linked to the request trace. Error tracking, basic dashboards, and alerts for errors and Agent cost.
- NFR-5 Security: input validation on every endpoint. Rate limits on log-in and the public Chat Page (per IP and per Conversation). No secrets in code. Passwords stored only as strong hashes.
- NFR-6 Mobile-first, low bandwidth: all screens work from 360 px. Chat Page first load < 200 KB compressed.
- NFR-7 Cost: total < $10/month. Daily Agent reply cap per Business (200 on demo); after the cap, Handoff. Dev uses Groq free tier with fake data only. Claude runs CI Evals and demo. Spending limits set in AWS and Anthropic consoles.
- NFR-8 Personal data (DPDP): notice on the Chat Page before the first Message (what, why, deletable). An Owner deletes a Customer with all Conversations and Bookings. Logs and traces never hold phone numbers or addresses in plain text.
- NFR-9 Swappable providers: AI, Channels, and payments sit behind adapters. A new provider needs no booking-logic change.
- NFR-10 Testing: every story meets the Definition of Done (tests pass, evals pass if AI touched, traces visible, docs updated, learning note, Understanding Gate). Every bug fix adds a regression test. Playwright E2E for UJ-1, UJ-2, UJ-3. CI enforces minimum coverage.

### Additional Requirements

**Starter template:** none. The architecture gives a structural seed instead (`backend/`, `frontend/`, `evals/`, `infra/compose`, `infra/terraform`, `.github/workflows`). Epic 1 Story 1 creates this skeleton from scratch, with the pinned stack versions.

**Structure and code rules**
- AR-1 (AD-1): Backend code under `backend/app/modules/<module>/` with modules `core, accounts, business, inbox, agent, bookings, dashboard, demo`. Each table has one owning module; each story that adds a table names its owner.
- AR-2 (AD-2): Modules call each other only through `service.py` front doors, with Pydantic DTOs. `import-linter` enforces the dependency direction in CI.
- AR-3 (AD-14): All routes under `/api/v1`, JSON only, one error envelope `{"error": {"code", "message"}}`. Frontend TypeScript client generated from OpenAPI (`openapi-typescript` + `openapi-fetch`). One shared poll hook. No other data-fetching library. No logic in Next.js API routes.
- AR-4 (AD-15): The entry point (router dependency, job handler, CLI) owns the one transaction; services never commit. No AI call or enqueue inside an open transaction. Agent jobs use one short transaction per tool call; write tools are idempotent.
- AR-5 Conventions: UUIDv7 ids; `timestamptz` UTC with a Business timezone (default `Asia/Kolkata`); money as integer `*_paise`; typed domain exceptions mapped once in `core`; config via one `pydantic-settings` object; one Alembic history (CI fails on >1 head).

**Tenancy, auth, security**
- AR-6 (AD-3): A `core` tenant-scoped base repository adds the `business_id` filter and sets it on insert. Tenant context only from session, visitor token / chat slug, job payload, or one audited `system_scope` allow-list. Redis keys start with purpose then `business_id`. DB second guard: `UNIQUE (business_id, id)` and composite foreign keys on every tenant table. Raw SQL only in `core`.
- AR-7 (AD-4): `memberships(user_id, business_id, roles set, is_active)`, unique on `user_id`. Deactivate, never delete. One `require_roles` helper on an `Actor`. Only `accounts` computes "active Technicians".
- AR-8 (AD-5): Server-side opaque session token in an `httpOnly`, `Secure`, `SameSite=Lax` cookie. Argon2id passwords. No JWT. Logout and deactivation delete sessions at once. CSRF guard: state-changing requests must carry a matching `Origin`; no state change on `GET`.
- AR-9 (AD-6): One origin. Caddy (local, demo) or ALB (AWS) routes `/api/*` to FastAPI and the rest to Next.js. Health at `/api/health` and `/api/health/worker`. No CORS. Client IP only from the trusted proxy header.
- AR-10 (AD-16): First visit to a chat slug sets a random visitor token in an `httpOnly` cookie; `inbox` stores only its hash. Public endpoints never accept a `conversation_id`. Customer linked by `(business_id, phone)` for the Owner's view only; a visitor never sees other chats by phone match.
- AR-11 (AD-13): One PII masking function in `core` for logs, traces, and Langfuse. "Delete Customer" runs in `inbox` in one transaction: `bookings.delete_for_customer` first, then its own rows.

**Agent, worker, polling**
- AR-12 (AD-7): Per-Conversation increasing `seq` under a row lock; opaque client cursor. Send saves and, after commit, enqueues `agent_reply` (job key `<conversation_id>:<seq>`, with `business_id`, `seq`, `traceparent`). Redis lock per Conversation (TTL 30 s). A job drops its reply if a newer Customer Message exists; saves only in `agent` state. 9 s turn deadline, max 4 tool calls, no auto-retry; on failure → FR-22 message + Handoff. `reply_pending` is derived; every pending reply ends within 30 s (SAQ timeout + aborted-job handler). One poll endpoint shape: new Messages + `conversation_state`, `reply_pending`, Booking status. Redis version counter `ver:<business_id>:<conversation_id>` makes "no change" polls skip Postgres. Poll 1–2 s while pending, ≤ 5 s while visible, stop when hidden. Poll endpoints rate-limited.
- AR-13 (AD-8): The Agent gets facts and acts only through tools that call front doors, one tool call at a time. `bookings.quote_price` records a quote (one Conversation, own expiry). The server renders an "Accept ₹X" chip with the `quote_id`; only a tap accepts it, never the LLM. `bookings.create_request(quote_id, slot)` refuses unaccepted, expired, or foreign quotes and takes the price from the quote. Prices and Slots appear only in server-built chips/cards. A post-check rejects reply text with money amounts or Slot times/dates; regenerate once, then hand off. Message shape: `author_type`, `author_membership_id`, `body`, `lang`, `client_message_id` (idempotent), `actions[]`.
- AR-14 (AD-9): Every capacity write runs in `bookings` under `pg_advisory_xact_lock(namespace, hash(business_id))`, then recounts. Guarded `UPDATE … WHERE state = :from`. `UNIQUE (bookings.quote_id)`. Anti-hoarding: ≤ 1 open request per Conversation, small fixed limit per visitor token and per IP, checked inside the lock. Expiry computed on read from `expires_at` by one repository function; hourly sweep persists it. Taken Slot raises `SlotUnavailable`.
- AR-15 (AD-10): `inbox` owns Conversation state `agent | handoff | closed` via `start_handoff`, `end_handoff`, `close`. `bookings` owns Booking state `requested → confirmed | declined | expired`, `confirmed → completed | cancelled`. The Inbox "Booking Request" badge is derived.
- AR-16 (AD-11): Only adapter files import provider SDKs. Provider chosen by env var. Groq adapter refuses to start outside `local`/`dev`. Deterministic `FakeAI` adapter for unit, integration, and E2E tests.
- AR-17 (AD-12): Prompts versioned in `agent/prompts/`. Each AI call records prompt version, model, tokens, cost, latency in Langfuse, linked to the OTel trace. Daily cap via atomic Redis `INCR` before each call; over cap → Handoff.
- AR-18 (AD-17): Evals run the real agent loop on a seeded Testcontainers DB. Smoke set per PR with Claude's cheap model; full set nightly/on demand. Baseline score file in repo. Hard zero on invented Price/Slot or request without accepted Price; other metrics block beyond a fixed tolerance. Temperature 0; smoke cases run twice. Claude key never exposed to fork PRs.

**Infrastructure, delivery, operations**
- AR-19: Local = docker-compose (Caddy, Next.js, FastAPI, worker, Postgres 18, Valkey 9). Demo = Oracle Cloud Always Free ARM VM (Caddy + TLS, Next.js, FastAPI, worker, Valkey with AOF) + Neon Postgres in the nearest region. AWS staging = Terraform (ECS Fargate, RDS, ElastiCache, ALB, Secrets Manager, CloudWatch), public subnets, no NAT, destroy after each session.
- AR-20: Images built once per commit for `amd64` + `arm64`, pushed to GHCR. Pipeline: lint + import-linter → tests (incl. isolation) → evals smoke → build → migrate + deploy demo + demo reset → manual approval → aws-staging.
- AR-21: OpenTelemetry for traces, logs, metrics to Grafana Cloud free; Langfuse Cloud free for LLM traces. Grafana alerts on API error rate, worker health, daily agent cost. AWS budget alert $5. Anthropic monthly limit.
- AR-22: Idle-cost guard: worker polls Valkey, not Postgres; expiry sweep hourly; no-change polls stop at Valkey so Neon can sleep.
- AR-23 Required tests: tenant-isolation suite every PR (read and write paths); agent-job concurrency test (two Messages 1 s apart → one reply covering both); one integration test per cross-module lock-order flow (phone-in booking, Customer delete); Chat Page bundle-size check (≤ 200 KB) in CI; coverage gate.

**Decisions left to specific stories (fixed constants, set there)**
- AR-24: Slot length and step (slot-math story). Open-request limit per visitor/IP, quote expiry, eval tolerance. Exact Claude and Groq model ids per environment (agent story). UI component kit choice (first frontend story; no data-fetching library). Oracle Pay-As-You-Go upgrade (decide before the demo-deploy story).

### UX Design Requirements

**Design tokens and theming**
- UX-DR1: Implement the brand token layer on top of shadcn/ui in Tailwind: all light and dark colors from DESIGN.md (zinc neutrals, primary that inverts in dark, accent `#047857` light / `#34D399` dark only, accent-soft, status-requested amber, status-handoff red), radii (`sm 8, md 12, lg 16, xl 24, section 40, full`), spacing tokens (page-x 16/32, max-width app 1280 / landing 1600, tap-target 44).
- UX-DR2: Typography: Inter (subset) for Latin; Noto Sans Devanagari loaded only via `unicode-range` when Hindi appears. Scales `display, heading, title, body, body-sm, label` as specified. Body weight 400; no weight 300; labels 12px uppercase minimum.
- UX-DR3: Light and dark themes. Default follows the device. A logged-in User overrides it in Settings → Appearance (system / light / dark), saved per User. Chat Page and landing follow the device only. Dark app background uses a subtle bottom-heavy gradient.
- UX-DR4: Formatting helpers: money with Indian grouping (₹1,499; ₹1,00,000) from paise; time as 12-hour "10:00 am – 11:00 am"; dates as "Tue, 4 Nov"; all in the Business timezone.

**Reusable components**
- UX-DR5: `button-primary` (pill, primary color, 44px, 150 ms color hover, no scale in app) and `button-action` (pill with nested 40px icon circle; landing CTAs and Booking Request Confirm only; 105% hover scale on landing only).
- UX-DR6: `status-badge`: pill with label + icon. Confirmed = emerald, Requested = amber, Needs Human = red, Expired/Declined/Cancelled = zinc. Never color alone.
- UX-DR7: Chat bubbles: Customer right in primary; Agent and User left on card with border, radius xl. A User reply shows the User's name above the bubble. The Agent is labeled "SevaDesk assistant".
- UX-DR8: Service price row: Service name, "from ₹X" in title style, duration in body-sm muted, always followed by "Final price after inspection. Parts extra."
- UX-DR9: Quick-reply chips (real buttons, keyboard reachable): Service choice, Price acceptance ("Accept ₹X" / "No", server-built with `quote_id`), Slot chips (max 4 + "Other times"). Chips show on the last Agent Message only. Typing always works too.
- UX-DR10: Booking Request card (Conversation and Dashboard): Customer, Service, Price shown, Slot, address, amber countdown ("Expires in 9 h"). Actions Confirm (`button-action`), Change (sheet with Slot picker, plus Technician picker if > 1 Technician), Decline (preset reasons + free text).
- UX-DR11: Inbox row: status badge (Agent / Needs Human / Booking Request / Expired), Customer name or phone, 1-line last Message preview, time. Needs Human rows pinned at top.
- UX-DR12: Handoff bar: "You are replying. The Agent is paused." + "Give back to Agent" during Handoff; "Agent is replying" + "Take over" otherwise.
- UX-DR13: Composer: multi-line input + Send. Enter sends on desktop, Shift+Enter new line, Send button on mobile. One-time hint "Your reply pauses the Agent." Failed send shows "Not sent · Retry" with nothing lost.
- UX-DR14: Calendar blocks colored by status rules; requested Bookings shown with a dashed border. Day view default on mobile, week view default on desktop.
- UX-DR15: Landing-only glass components: `glass-panel` / glass stat card (white 5% fill, 12px blur, white 10% border, radius xl), landing section wrapper (radius 40, dark gradient), grain overlay at 15%. Never used on app screens.

**Navigation and layout**
- UX-DR16: Mobile bottom tab bar: Owner/Staff see Dashboard · Inbox · Calendar · More; Technician-only Users see Calendar · More. Inbox tab shows a red count of Needs Human Conversations. Desktop (≥ 1024px): left sidebar with the same items.
- UX-DR17: Inbox two-pane layout on desktop (list left, Conversation right); single pane on mobile.
- UX-DR18: Default landing screen after log-in: Dashboard for Owner/Staff; Calendar for Technician-only Users.
- UX-DR19: Breakpoints 360 (min), 768 (tablet, wider cards), 1024 (sidebar, two-pane). Mobile-first. App surfaces solid only: no glass, grain, or blur.

**Screen states and flows**
- UX-DR20: Chat Page header: Business name, active Services list with prices; on mobile the list collapses after the first Message behind a "Services & prices" button. DPDP notice above the composer until the first Message. "Not taking requests yet" when no Service or no Working Hours exist.
- UX-DR21: Chat Page status copy exactly as the Voice table: Request sent, Confirmed, Expired (with new request option), Declined with reason, AI failure, Handoff started, Slot gone.
- UX-DR22: Agent typing indicator: three dots after 1 s; "Still working…" after 10 s.
- UX-DR23: Dashboard first-run checklist: Add Services → Set Working Hours → Copy chat link; turns emerald when done and shows "Copy chat link".
- UX-DR24: Empty Inbox: "No conversations yet. Share your chat link to get your first customer." + Copy link.
- UX-DR25: Loading: shadcn `Skeleton` rows matching each layout. Lists use "Load more" pagination, not infinite scroll.
- UX-DR26: Polling banner "Reconnecting…" after 3 failed polls. Polling pauses when the tab is hidden.
- UX-DR27: Forbidden actions are hidden per Role; a direct URL shows "You don't have access to this page."
- UX-DR28: Delete Customer confirm dialog names what is deleted (Conversations, Bookings) and says it cannot be undone.
- UX-DR29: Team page shows "Just you for now" for a solo Owner; no screen asks to assign a Technician when only one is active.
- UX-DR30: Landing page sections: floating glass pill navbar; 92vh dark hero with giant blurred "SEVA" word (3% opacity) and glass stat cards; two-column feature grid with sticky header; dark "How it works" with steps 01–03 and a tilted Chat Page mock; three-card bento "How it's built" (Tests · Evals · Tracing/AWS). CTAs: "Try the chat", "Demo log-in", GitHub. No photos (CSS/SVG gradients + grain SVG). Fade-in-up 0.8 s `cubic-bezier(0.16, 1, 0.3, 1)`.

**Accessibility and motion**
- UX-DR31: WCAG 2.2 AA: text contrast ≥ 4.5:1 (use the DESIGN.md pairs); visible focus ring on every control; text labels; `aria-label` on icon-only buttons; no hover-only information; tap targets ≥ 44px.
- UX-DR32: New chat Messages announced via an `aria-live="polite"` region; Hindi Messages carry `lang="hi"`.
- UX-DR33: Forms show errors in text next to the field and move focus to the first error.
- UX-DR34: Motion: app uses only 150–200 ms color/opacity transitions; landing motion as UX-DR30. All motion off under `prefers-reduced-motion`.
- UX-DR35: Browser targets: recent Chrome on Android (main), Safari on iOS, desktop Chrome, Edge, Firefox.

### FR Coverage Map

FR-1: Epic 1 - End-to-end hello path
FR-2: Epic 1 - Health checks (API and worker)
FR-3: Epic 1 - Delivery pipeline
FR-4: Epic 1 - Observability baseline
FR-5: Epic 1 - Eval harness with placeholder Eval
FR-6: Epic 1 - One-command AWS deploy and destroy (full-app AWS run re-checked in Epic 8)
FR-7: Epic 2 - Owner sign-up
FR-8: Epic 2 - Log in and log out
FR-9: Epic 2 - Invite team members
FR-10: Epic 2 - Role-based access
FR-11: Epic 2 - Tenant isolation (suite extended by every later epic)
FR-12: Epic 3 - Manage Services with Prices
FR-13: Epic 3 - Working Hours and closed days
FR-14: Epic 3 - Chat Page link
FR-15: Epic 4 - Start and continue a Conversation
FR-16: Epic 6 - Collect booking details
FR-16a: Epic 6 - Show and accept the Price before booking
FR-17: Epic 5 - Slot calculation; Epic 6 - Agent offers only free Slots
FR-18: Epic 6 - Create a Booking Request
FR-18a: Epic 6 - Booking Request expiry
FR-19: Epic 6 - Language match
FR-20: Epic 6 - No invented facts
FR-21: Epic 4 - Human take-over and give-back; Epic 6 - Agent-triggered Handoff
FR-22: Epic 6 - Agent failure fallback
FR-23: Epic 4 - Inbox list
FR-24: Epic 4 - Read and reply, live within 5 s
FR-25: Epic 6 - Confirm, change, or decline a Booking Request
FR-26: Epic 5 - Calendar day and week views
FR-27: Epic 5 - Manual create, cancel, complete Bookings
FR-28: Epic 8 - Owner Dashboard
FR-29: Epic 8 - Seeded demo Businesses and reset
FR-30: Epic 7 - Golden Dataset
FR-31: Epic 8 - Landing page

NFRs are cross-cutting. First home: NFR-1 Epic 2 (then every epic); NFR-2 Epic 7 (placeholder in Epic 1); NFR-3 Epic 4 (polling) and Epic 6 (agent); NFR-4 Epic 1 (baseline) and Epic 6 (LLM tracing); NFR-5 Epic 2 (log-in) and Epic 4 (public chat); NFR-6 Epic 4 (Chat Page budget); NFR-7 Epic 1 (cost guardrails) and Epic 6 (daily cap); NFR-8 Epic 1 (masking) and Epic 4 (notice, delete Customer); NFR-9 Epic 4 (channel port) and Epic 6 (AI port); NFR-10 every epic.

## Epic List

### Epic 1: Walking Skeleton
The builder opens a live page that shows a value the backend read from the database. CI (lint, tests, eval smoke, build), structured logs and traces, health checks, demo deploy, and one-command AWS deploy/destroy all work end to end. No product features yet.
**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6

### Epic 2: Accounts and Team
An Owner signs up (creating a Business), logs in and out, and invites Staff and Technicians with Roles. Each action is allowed only for its Roles. No Business can see or change another Business's data.
**FRs covered:** FR-7, FR-8, FR-9, FR-10, FR-11

### Epic 3: Business Setup
An Owner adds Services with a duration and a required Price, sets weekly Working Hours and closed days, and copies a stable Chat Page link.
**FRs covered:** FR-12, FR-13, FR-14

### Epic 4: Live Chat and Inbox (humans only)
A Customer opens the Chat Page (with Services, Prices, and the DPDP notice), chats without an account, and returns to the same Conversation. Owner and Staff see the Inbox, read, and reply live within 5 s; a reply starts a Handoff that can be given back. An Owner can delete a Customer and all their data. No AI yet.
**FRs covered:** FR-15, FR-21 (human take-over and give-back), FR-23, FR-24

### Epic 5: Bookings and Calendar
The system calculates free Slots from Working Hours and active Technicians under a capacity lock. Staff create Bookings for phone-in Customers, cancel and complete them, and see day and week Calendars; Technicians see only their own.
**FRs covered:** FR-17 (slot calculation), FR-26, FR-27

### Epic 6: AI Agent Books Jobs
The Agent replies in the Customer's language, collects details, shows the Price for acceptance, offers only real free Slots, and creates a Booking Request. Staff confirm, change, or decline it; unanswered requests expire after 12 h. The Agent never invents facts, hands off when it should, and falls back safely when the AI fails or the daily cap is hit.
**FRs covered:** FR-16, FR-16a, FR-17 (offer), FR-18, FR-18a, FR-19, FR-20, FR-21 (agent-triggered), FR-22, FR-25

### Epic 7: Proven Agent Quality
The builder creates a reviewed Golden Dataset of at least 30 English and Hindi/Hinglish cases. Evals run the real agent loop and block any merge that invents a Price or Slot, or that drops below baseline.
**FRs covered:** FR-30

### Epic 8: Dashboard and Portfolio Demo
The Owner sees today at a glance. Demo and AWS start with seeded solo and team Businesses that can be reset. A public landing page explains SevaDesk and opens the demo. The full app deploys to AWS and passes the E2E tests there.
**FRs covered:** FR-28, FR-29, FR-31

## Epic 1: Walking Skeleton

The builder opens a live page that shows a value the backend read from the database. CI, structured logs and traces, health checks, demo deploy, and one-command AWS deploy/destroy all work end to end. No product features yet.

### Story 1.1: Hello path runs locally with one command

As the builder,
I want one command to start the frontend, backend, database, cache, and proxy on my laptop,
So that I can see a value travel from the database to the browser before I build any feature.

**Acceptance Criteria:**

**Given** a fresh clone with the structural seed folders (`backend/`, `frontend/`, `evals/`, `infra/compose/`, `.github/workflows/`) and an `.env.example` with no real secrets
**When** the builder runs `docker compose up` from `infra/compose/`
**Then** Caddy, Next.js, FastAPI, Postgres 18, and Valkey 9 start, and `http://localhost` serves the frontend
**And** `/api/*` goes to FastAPI and every other path goes to Next.js (one origin, no CORS) (AR-9)

**Given** the stack is running
**When** the builder opens the home page
**Then** the page shows a hello value that FastAPI read from Postgres through `GET /api/v1/hello`, plus the backend version (FR-1)
**And** the frontend calls the API only through a TypeScript client generated from the FastAPI OpenAPI schema (AR-3)

**Given** the backend starts
**When** Alembic runs `upgrade head`
**Then** it creates only one non-tenant table, `app_meta`, owned by `core`, with the hello value
**And** all config comes from one `pydantic-settings` object read from env vars (AR-5)

**Given** the repository
**When** the builder runs the backend and frontend unit tests
**Then** a pytest test for the hello endpoint and a Vitest test for the hello page pass

### Story 1.2: Health checks for the API and the worker

As an operator,
I want health endpoints for the backend and the worker,
So that I know at once when a part of the system is down.

**Acceptance Criteria:**

**Given** the stack is running with Postgres and Valkey reachable
**When** an operator calls `GET /api/health`
**Then** it returns 200 with the status of the database and Redis (FR-2)

**Given** Postgres or Valkey is stopped
**When** an operator calls `GET /api/health`
**Then** it returns 503 and names the failing dependency in the error envelope `{"error": {"code", "message"}}` (AR-3)

**Given** the SAQ worker runs as its own container from `backend/app/worker.py`
**When** an operator calls `GET /api/health/worker`
**Then** it returns 200 if the worker sent a heartbeat to Valkey in the last 30 seconds, and 503 if not

**Given** the health code
**When** integration tests run with real Postgres and Redis through Testcontainers
**Then** the 200 and 503 cases for both endpoints pass

### Story 1.3: Eval harness with a placeholder Eval

As the builder,
I want an eval runner that scores checks and compares them with a stored baseline,
So that AI quality gates exist before the Agent exists.

**Acceptance Criteria:**

**Given** `evals/` holds a runner, a dataset folder, and a baseline score file in the repo
**When** the builder runs the eval command locally
**Then** it runs one placeholder Eval case and prints a score per check (FR-5)

**Given** a score below the stored baseline
**When** the eval command finishes
**Then** it exits with a non-zero code, so CI can fail on it

**Given** the runner
**When** it records a result
**Then** the result names the prompt version and the dataset version it used (AR-17)

### Story 1.4: CI pipeline blocks bad merges

As the builder,
I want every pull request checked automatically,
So that broken code, broken structure, or lower AI quality never reaches main.

**Acceptance Criteria:**

**Given** a pull request on GitHub
**When** GitHub Actions runs
**Then** it runs in order: lint + `import-linter` → backend and frontend tests → eval smoke set → image build (FR-3, AR-2)
**And** a failing step blocks the merge

**Given** the test step
**When** coverage is below the configured minimum
**Then** the step fails (NFR-10)

**Given** the Alembic history has more than one head
**When** CI runs
**Then** the pipeline fails (AR-5)

**Given** the build step
**When** it succeeds
**Then** it builds the backend, worker, and frontend images once for `amd64` and `arm64` and pushes them to GHCR, tagged with the commit (AR-20)

**Given** a pull request from a fork
**When** CI runs
**Then** no secret (such as the Claude key) is available to the job (AR-18)

### Story 1.5: One trace across the whole request

As an operator,
I want structured logs and one trace per request across frontend, backend, worker, and database,
So that I can find the cause of any error quickly.

**Acceptance Criteria:**

**Given** a request to `GET /api/v1/hello` that also enqueues a test job to the worker
**When** the operator opens Grafana Cloud
**Then** one trace shows the frontend request, the FastAPI handler, the Postgres query, and the worker job (FR-4)
**And** the job carries `traceparent` in its payload, so the worker span joins the same trace

**Given** any log line from the backend or the worker
**When** it is written
**Then** it is JSON with a request ID and a trace ID

**Given** a log message, trace attribute, or exported payload that contains an Indian phone number or an address field
**When** it passes through the one `core` masking function
**Then** the value is masked (AR-11, NFR-8)
**And** a unit test proves that phone numbers in Latin and Devanagari digits are masked

**Given** the observability code
**When** the builder reads it
**Then** only OpenTelemetry APIs are used, so the backend tool can change by config alone

### Story 1.6: Merge to main deploys the demo

As the builder,
I want a merge to main to deploy the same images to the always-on demo server,
So that the portfolio link always shows the latest working version.

**Acceptance Criteria:**

**Given** the builder has decided whether to upgrade the Oracle account to Pay-As-You-Go, and recorded the decision in the architecture spine (AR-24)
**When** the Oracle Always Free ARM VM is set up
**Then** it runs Caddy with TLS, Next.js, FastAPI, the worker, and Valkey (AOF on) through docker-compose, and connects to Neon Postgres in the nearest region (AR-19)
**And** demo secrets live in an env file on the server, outside Git

**Given** a merge to main whose CI passes
**When** the deploy job runs
**Then** it runs `alembic upgrade head` before the new version starts, then starts the commit's images from GHCR (FR-3)
**And** the public demo URL shows the hello page with the new backend version

**Given** a migration fails
**When** the deploy job runs
**Then** the old version keeps running and the job fails

**Given** the demo is idle
**When** nobody uses it
**Then** the worker polls Valkey only, so Neon can sleep (AR-22)

### Story 1.7: One-command AWS staging deploy and destroy

As the builder,
I want to create and remove the full AWS staging environment with one command each,
So that I can show the app on AWS for an interview and pay almost nothing.

**Acceptance Criteria:**

**Given** Terraform files in `infra/terraform/` (ECS Fargate for frontend, backend, and worker; RDS Postgres; ElastiCache; one ALB with path routing; Secrets Manager; CloudWatch; public subnets; no NAT Gateway)
**When** the builder runs the deploy command
**Then** a public AWS URL serves the same hello page from the same GHCR images as the demo (FR-6, AR-19)
**And** migrations run before the backend starts

**Given** the AWS environment exists
**When** the builder runs the destroy command
**Then** Terraform removes everything, and a check script confirms that no billable resource remains

**Given** the AWS account
**When** the deploy runs for the first time
**Then** an AWS Budget alert at $5 exists (FR-6, NFR-7)
**And** the docs note that the Anthropic monthly spending limit is set in the console

**Given** the GitHub Actions pipeline
**When** a deploy to aws-staging is requested
**Then** it waits for a manual approval before it runs (AR-20)

## Epic 2: Accounts and Team

An Owner signs up (creating a Business), logs in and out, and invites Staff and Technicians with Roles. Each action is allowed only for its Roles. No Business can see or change another Business's data.

### Story 2.1: Owner signs up and creates a Business

As a new business owner,
I want to sign up with my email and password,
So that I get my own SevaDesk Business and can start setting it up.

**Acceptance Criteria:**

**Given** the first frontend story
**When** the builder sets up the UI
**Then** shadcn/ui runs on Next.js + Tailwind with the DESIGN.md brand tokens (colors light and dark, radii, spacing, tap target 44px), Inter plus Noto Sans Devanagari by `unicode-range`, and the theme follows the device (UX-DR1, UX-DR2, UX-DR3)
**And** the chosen UI kit adds no data-fetching library (AR-3, AR-24)
**And** the accessibility floor applies from this first screen on: text contrast ≥ 4.5:1, a visible focus ring and a text label on every control, `aria-label` on icon-only buttons, no hover-only information, and tap targets ≥ 44px (UX-DR31)

**Given** a visitor on `/signup`
**When** they submit a business name, email, and a valid password
**Then** the system creates a Business, a User, and a membership with Roles `{owner, technician}` in one transaction (FR-7, AR-4)
**And** the `business` module runs this flow and calls the `accounts` front door, so `accounts` never imports `business` (AR-2)
**And** the password is stored only as an Argon2id hash (AR-8, NFR-5)

**Given** an email that already has an account
**When** a visitor signs up with it
**Then** the system refuses with a clear error and creates nothing

**Given** invalid input (empty name, bad email, weak password)
**When** the visitor submits
**Then** each error shows in text next to its field, and focus moves to the first error (UX-DR33)

**Given** the new tables `users` and `sessions` (global, owned by `accounts`), `memberships` (tenant, owned by `accounts`), and `businesses` (global, owned by `business`)
**When** the migration runs
**Then** each table has a UUIDv7 key, `memberships` has `UNIQUE (business_id, id)` and a unique `user_id` (AR-5, AR-6, AR-7)
**And** the `core` tenant-scoped base repository exists and `memberships` uses it (AR-6)
**And** sign-up uses the audited `system_scope` allow-list for its lookups (AR-6)

### Story 2.2: Log in, log out, and the app shell

As a User,
I want to log in and log out safely,
So that only I can use my Business account.

**Acceptance Criteria:**

**Given** a User with a valid email and password
**When** they log in on `/login`
**Then** the server creates an opaque session token, stores it server-side, and sets it in an `httpOnly`, `Secure`, `SameSite=Lax` cookie (FR-8, AR-8)
**And** a sign-up (Story 2.1) also logs the new Owner in

**Given** a logged-in User
**When** they log out
**Then** the server deletes the session at once, and the old cookie no longer works

**Given** a session with no activity for longer than the fixed inactivity timeout (a constant set in this story)
**When** the User makes a request
**Then** the request returns 401 and the frontend sends the User to `/login`

**Given** repeated wrong passwords
**When** the limit per account or per client IP is reached
**Then** further log-in attempts return 429 for a fixed time (FR-8, NFR-5)
**And** the client IP comes only from the trusted proxy header (AR-9)

**Given** a `POST`, `PUT`, `PATCH`, or `DELETE` request with a missing or wrong `Origin` header
**When** it reaches the backend
**Then** it is refused and changes nothing (AR-8)

**Given** a logged-in User
**When** the app opens
**Then** it shows the app shell: a bottom tab bar on mobile and a left sidebar from 1024px, with items per Role (UX-DR16, UX-DR19)
**And** Owner and Staff land on the Dashboard placeholder; Technician-only Users land on the Calendar placeholder (UX-DR18)

### Story 2.3: Tenant isolation is tested on every pull request

As an Owner,
I want to be sure no other Business can see or change my data,
So that I can trust SevaDesk with my customers.

**Acceptance Criteria:**

**Given** two Businesses, each with a logged-in Owner
**When** Owner A requests or changes any record of Business B by id
**Then** the API returns 404, not 403, and changes nothing (FR-11)

**Given** the tenant-isolation test suite
**When** it runs
**Then** it lists every API endpoint from the OpenAPI schema and tries cross-Business reads and writes on each (FR-11, NFR-1, AR-23)
**And** a new endpoint with no isolation test makes the suite fail

**Given** a repository method
**When** it runs a query
**Then** the `core` base repository adds the `business_id` filter, and no repository method accepts `business_id` from a caller (AR-6)
**And** raw `text()` SQL outside `core` fails a CI check

**Given** a tenant row that points at a row of another Business
**When** it is inserted
**Then** the database refuses it through the composite foreign key `(business_id, <x>_id)` (AR-6)

**Given** any pull request
**When** CI runs
**Then** the isolation suite runs and blocks the merge on failure

### Story 2.4: Role-based access

As an Owner,
I want each team member to do only what their Role allows,
So that a Technician cannot change prices or read every chat.

**Acceptance Criteria:**

**Given** the FR-10 permission table
**When** a service function runs
**Then** it checks the `Actor` roles with the one `require_roles` helper (AR-7)

**Given** an Actor without the needed Role
**When** they call a forbidden endpoint
**Then** it returns 403 and changes nothing (FR-10)

**Given** a Technician-only Actor
**When** they ask for Bookings
**Then** the rule "own assigned Bookings only" is ready in `accounts` for the bookings module to use (AR-7)

**Given** a User in the app
**When** a screen has an action their Role may not do
**Then** the action is hidden, and a direct URL to a forbidden page shows "You don't have access to this page." (UX-DR27)

**Given** the permission rules
**When** tests run
**Then** each row of the FR-10 table has a test for allowed and forbidden Roles

### Story 2.5: Invite team members and manage the team

As an Owner,
I want to invite Staff and Technicians and manage their Roles,
So that my team can share the work.

**Acceptance Criteria:**

**Given** an Owner on Settings → Team
**When** they invite an email with one or more Roles
**Then** the system creates a single-use invite link that expires after 7 days, and the Owner can copy it (FR-9)
**And** the new tenant table `invites` is owned by `accounts`, and stores only a hash of the invite token
**And** SevaDesk sends no email

**Given** a valid invite link
**When** the invited person opens `/invite/{token}` and sets a password
**Then** they get a User and a membership in that Business with the invited Roles, and they are logged in

**Given** an invite link that was used or is older than 7 days
**When** someone opens it
**Then** the page says the invite is no longer valid, and nothing is created

**Given** an Owner on the Team page
**When** they change a member's Roles or deactivate a member
**Then** the membership changes, and a deactivated member's sessions are deleted at once (AR-7, AR-8)
**And** memberships are never deleted

**Given** an Owner who is also a Technician
**When** they turn off their own Technician Role
**Then** they no longer count as an active Technician (FR-7)

**Given** an Owner who is the only active Technician
**When** they open the Team page
**Then** it says "Just you for now" (UX-DR29)

### Story 2.6: Choose light or dark theme

As a User,
I want to choose a light, dark, or system theme,
So that the app is easy to read in sunlight or at night.

**Acceptance Criteria:**

**Given** a User on Settings → Appearance
**When** they choose system, light, or dark
**Then** the app uses that theme at once and saves the choice for that User (UX-DR3)

**Given** the User logs in on another device
**When** the app opens
**Then** it uses the saved theme

**Given** the public pages (Chat Page, landing page)
**When** a visitor opens them
**Then** they follow the device setting only

## Epic 3: Business Setup

An Owner adds Services with a duration and a required Price, sets weekly Working Hours and closed days, and copies a stable Chat Page link.

### Story 3.1: Manage Services with Prices

As an Owner,
I want to add, edit, and deactivate my Services with a duration and a Price,
So that customers and the Agent see only what I really sell, at my prices.

**Acceptance Criteria:**

**Given** an Owner on Settings → Services
**When** they add a Service with a name, a duration of 30–480 minutes, and a Price
**Then** the Service is saved as active, with the Price stored as integer `price_paise` (FR-12, AR-5)
**And** the new `services` table is a tenant table owned by `business` (AR-1, AR-6)

**Given** a Service form with no Price, or a duration outside 30–480 minutes
**When** the Owner saves or activates it
**Then** the system refuses, and the error shows next to the field (FR-12, UX-DR33)

**Given** an existing Service
**When** the Owner edits or deactivates it
**Then** the change is saved, and a deactivated Service is no longer offered (FR-12)

**Given** any money amount on screen
**When** it is shown
**Then** it uses Indian grouping from paise, for example ₹1,499 and ₹1,00,000 (UX-DR4)

**Given** a Staff or Technician User
**When** they call the Service write endpoints
**Then** the API returns 403 (FR-10)
**And** the isolation suite covers the new endpoints (FR-11)

### Story 3.2: Set Working Hours and closed days

As an Owner,
I want to set my weekly hours and mark holidays,
So that customers can only book when I really work.

**Acceptance Criteria:**

**Given** an Owner on Settings → Working Hours
**When** they set each weekday as closed, or with a start and an end time
**Then** the hours are saved for the Business (FR-13)
**And** the new `working_hours` and `closed_days` tables are tenant tables owned by `business`

**Given** an end time that is not after the start time
**When** the Owner saves
**Then** the system refuses, and the error shows next to that day

**Given** an Owner
**When** they mark a single date as closed
**Then** that date is closed, whatever the weekly hours say

**Given** the Business
**When** times are stored and shown
**Then** they use the Business timezone (default `Asia/Kolkata`), stored as UTC `timestamptz` where a moment in time is stored, and shown as "10:00 am – 6:00 pm" (AR-5, UX-DR4)

**Given** a Staff or Technician User
**When** they call the write endpoints
**Then** the API returns 403, and the isolation suite covers the new endpoints (FR-10, FR-11)

### Story 3.3: Share the Chat Page link

As an Owner,
I want a stable link to my public Chat Page and a short setup checklist,
So that I can share it with customers as soon as my Business is ready.

**Acceptance Criteria:**

**Given** a Business
**When** it is created
**Then** it gets one stable, unique chat slug owned by `business` (FR-14)

**Given** an Owner on Settings → Chat link
**When** they tap "Copy link"
**Then** the full Chat Page URL `/c/{slug}` is copied (FR-14)

**Given** a new Business with no Services or no Working Hours
**When** the Owner opens the Dashboard
**Then** it shows the checklist Add Services → Set Working Hours → Copy chat link (UX-DR23)
**And** when both are done, the checklist turns emerald and shows "Copy chat link"

**Given** a visitor opens `/c/{slug}` with no log-in
**When** the page loads
**Then** it shows the Business name, the active Services with "from ₹X", duration, and "Final price after inspection. Parts extra.", and the DPDP notice (FR-14, FR-16a, UX-DR8, UX-DR20)
**And** the tenant context comes from the chat slug only (AR-6)

**Given** the Business has no active Service or no Working Hours
**When** a visitor opens the Chat Page
**Then** it shows "Not taking requests yet" (UX-DR20)

**Given** an unknown slug
**When** a visitor opens it
**Then** the page shows "not found" and reveals nothing about other Businesses

**Given** CI
**When** the frontend builds
**Then** a check fails the build if the Chat Page first load is over 200 KB compressed (NFR-6, AR-23)

## Epic 4: Live Chat and Inbox (humans only)

A Customer opens the Chat Page, chats without an account, and returns to the same Conversation. Owner and Staff see the Inbox, read, and reply live within 5 s; a reply starts a Handoff that can be given back. An Owner can delete a Customer and all their data. No AI yet.

### Story 4.1: Customer sends Messages on the Chat Page

As a Customer,
I want to write to a Business on its Chat Page without an account, and come back to the same chat later,
So that I can ask for help in seconds.

**Acceptance Criteria:**

**Given** a first visit to `/c/{slug}`
**When** the page loads
**Then** the server sets a random visitor token in an `httpOnly` cookie and stores only its hash (FR-15, AR-10)
**And** the new tenant tables `customers`, `visitor_tokens`, `conversations`, and `messages` are owned by `inbox` (AR-1)

**Given** a visitor with a token
**When** they send their first Message
**Then** a Customer and a Conversation (state `agent`) are created, and the Message is saved with the next per-Conversation `seq`, set under a row lock (AR-12)
**And** the Message has the shape `author_type`, `author_membership_id`, `body`, `lang`, `client_message_id`, `actions[]` (AR-13)

**Given** the same `client_message_id` is sent twice (for example after a network retry)
**When** the server receives it
**Then** only one Message is saved

**Given** a visitor returns in the same browser
**When** they open the Chat Page
**Then** they see their own Conversation and nothing else; public endpoints never accept a `conversation_id` (FR-15, AR-10)

**Given** Messages are sent and received
**When** the code handles them
**Then** it goes through a channel port with one webchat adapter, so WhatsApp can be added later with no inbox logic change (NFR-9)

**Given** many Messages from one IP or one Conversation
**When** the rate limit is reached
**Then** further sends return 429 (NFR-5)

**Given** the Chat Page UI
**When** the Customer chats
**Then** the DPDP notice sits above the composer until the first Message; Customer bubbles are on the right; on mobile the Services list collapses behind "Services & prices" after the first Message (NFR-8, UX-DR7, UX-DR20)
**And** a failed send shows "Not sent · Retry", and the text is kept while the page is open (UX-DR13)
**And** new Messages are announced through an `aria-live="polite"` region, and Hindi text carries `lang="hi"` (UX-DR32)

### Story 4.2: Chat Page stays live by polling

As a Customer,
I want new Messages to appear without reloading the page,
So that the chat feels live on my phone.

**Acceptance Criteria:**

**Given** an open Chat Page
**When** it polls the one poll endpoint with its opaque cursor
**Then** it gets only the new Messages plus a snapshot with `conversation_state` (AR-12)

**Given** nothing changed since the last poll
**When** the poll arrives
**Then** the Redis counter `ver:<business_id>:<conversation_id>` matches the client version, and the server answers "no change" without a Postgres query (AR-12, AR-22)
**And** every commit that changes a Conversation increases that counter

**Given** a visible tab
**When** it polls
**Then** polls are never more than 5 s apart; they stop while the tab is hidden and restart when it is visible (AR-12, UX-DR26)
**And** the frontend uses the one shared poll hook from the generated client (AR-3)

**Given** three polls in a row fail
**When** the next one is due
**Then** the page shows a "Reconnecting…" banner, which goes away after a successful poll (UX-DR26)

**Given** the poll endpoint
**When** it is called too often
**Then** it is rate-limited (AR-12)
**And** a "no change" poll answers within 500 ms at p95 on demo (NFR-3)

### Story 4.3: Inbox lists all Conversations

As an Owner or Staff member,
I want one list of all Conversations, with the urgent ones on top,
So that I never miss a Customer.

**Acceptance Criteria:**

**Given** a User with Inbox access
**When** they open `/app/inbox`
**Then** they see Conversations, newest activity first, with Handoff Conversations pinned at the top (FR-23)
**And** each row shows a status badge (Agent / Needs Human), the Customer name or phone (or "New visitor"), a one-line last Message preview, and the time (UX-DR6, UX-DR11)

**Given** a new Customer Message
**When** the Inbox polls
**Then** the list updates within 5 s without reload (FR-24)

**Given** Needs Human Conversations exist
**When** the app shell shows the Inbox tab
**Then** it shows a red count of them (UX-DR16)

**Given** no Conversations yet
**When** the Inbox opens
**Then** it shows "No conversations yet. Share your chat link to get your first customer." with a Copy link button (UX-DR24)

**Given** a long list
**When** the User scrolls to the end
**Then** a "Load more" button loads the next page; while loading the first page, Skeleton rows show (UX-DR25)

**Given** a desktop screen of 1024px or more
**When** the Inbox opens
**Then** it shows two panes: the list on the left and the open Conversation on the right (UX-DR17)

**Given** a Technician-only User
**When** they call the Inbox endpoints
**Then** the API returns 403 (FR-10), and the isolation suite covers the new endpoints (FR-11)

### Story 4.4: Reply to a Customer and take over the chat

As an Owner or Staff member,
I want to read a Conversation and reply myself,
So that I can help a Customer when the Agent should not.

**Acceptance Criteria:**

**Given** a User opens a Conversation
**When** it loads
**Then** they see the full history, with Customer bubbles on the right and Agent and User bubbles on the left (FR-24, UX-DR7)

**Given** a User sends a reply from the composer
**When** it is saved
**Then** it calls `inbox.start_handoff`, the Conversation state becomes `handoff`, and the reply appears on the Customer's Chat Page within 5 s with the User's name above the bubble (FR-24, FR-21, AR-15, UX-DR7)
**And** the first time, the composer shows the hint "Your reply pauses the Agent." (UX-DR13)

**Given** the desktop composer
**When** the User presses Enter
**Then** the reply is sent; Shift+Enter adds a new line (UX-DR13)

**Given** a Conversation in `agent` state
**When** the User opens it
**Then** the Handoff bar says "Agent is replying" with a "Take over" button; in `handoff` state it says "You are replying. The Agent is paused." with "Give back to Agent" (UX-DR12)

**Given** a Conversation in Handoff
**When** the User taps "Give back to Agent"
**Then** `inbox.end_handoff` sets the state to `agent` (FR-21, AR-15)

**Given** any code that changes the Conversation state
**When** it runs
**Then** it uses only the named `inbox` functions `start_handoff`, `end_handoff`, or `close` (AR-15)

### Story 4.5: Delete a Customer and all their data

As an Owner,
I want to delete a Customer and everything about them,
So that I follow the DPDP Act when a Customer asks.

**Acceptance Criteria:**

**Given** an Owner opens a Conversation
**When** they open the Customer detail sheet from the header
**Then** they see the Customer data and a "Delete customer" action (NFR-8)

**Given** the Owner taps "Delete customer"
**When** the confirm dialog opens
**Then** it names what will be deleted (Conversations, Messages, and, once bookings exist, Bookings) and says it cannot be undone (UX-DR28)

**Given** the Owner confirms
**When** the delete runs
**Then** `inbox` deletes the Customer, their visitor tokens, Conversations, and Messages in one transaction (NFR-8, AR-11)
**And** the deleted Customer's visitor cookie no longer opens any Conversation

**Given** a Staff or Technician User
**When** they call the delete endpoint
**Then** the API returns 403, and the isolation suite covers it (FR-10, FR-11)

## Epic 5: Bookings and Calendar

The system calculates free Slots from Working Hours and active Technicians under a capacity lock. Staff create Bookings for phone-in Customers, cancel and complete them, and see day and week Calendars; Technicians see only their own.

### Story 5.1: Calculate free Slots

As an Owner or Staff member,
I want to see which times are free for a Service,
So that I never promise a time when nobody can come.

**Acceptance Criteria:**

**Given** the slot-math story
**When** the builder starts it
**Then** the Slot length and step are chosen and stored as fixed constants in `bookings` (AR-24)
**And** the new tenant table `bookings` (state, start, end, `customer_id`, nullable `conversation_id`, `technician_membership_id`, `price_paise`, `expires_at`) is owned by `bookings` and uses composite foreign keys (AR-1, AR-6)

**Given** a Service, Working Hours, closed days, and existing Bookings
**When** `bookings` lists free Slots for the next 7 days
**Then** a Slot is free only if it fits the Service duration inside Working Hours, is not on a closed day, and the count of overlapping live `requested` + `confirmed` Bookings is less than the number of active Technicians (FR-17)
**And** the number of active Technicians comes only from the `accounts` front door (AR-7)

**Given** a `requested` Booking whose `expires_at` is in the past
**When** Slots are counted
**Then** it does not count, because one `bookings` repository function computes "expired" on read, and every count uses it (AR-14)

**Given** Business times
**When** Slots are computed and shown
**Then** they use the Business timezone, including on days around midnight (AR-5, UX-DR4)

**Given** the Slot rules
**When** unit tests run
**Then** they cover: closed day, Slot at the end of Working Hours, one Technician fully booked, two Technicians with one free, and an expired request that frees capacity

**Given** a User with Inbox access
**When** they call the free-Slots endpoint
**Then** they get the free Slots; a Technician-only User gets 403 (FR-10)

### Story 5.2: Create a Booking for a phone-in Customer

As an Owner or Staff member,
I want to create a Booking for a Customer who phoned me,
So that phone jobs and chat jobs live in one calendar.

**Acceptance Criteria:**

**Given** a User with Inbox access
**When** they create a Booking with a Customer name and phone, a Service, a free Slot, and (if more than one Technician) a Technician
**Then** the Booking is saved as `confirmed` with no `conversation_id` (FR-27)
**And** with only one active Technician, that Technician is assigned automatically and no picker is shown (FR-25, UX-DR29)

**Given** a User has a Conversation open
**When** they create a Booking from it by hand (UJ-2)
**Then** the Booking is saved as `confirmed` for that Conversation's Customer, with its `conversation_id` set (FR-27)

**Given** any write that takes capacity
**When** it runs in `bookings`
**Then** it first takes `pg_advisory_xact_lock(<bookings namespace>, <hash of business_id>)`, then recounts, then checks that the Technician has no overlapping confirmed Booking (AR-14)

**Given** two Users book the last free Slot at the same moment
**When** both requests run in parallel in an integration test
**Then** exactly one succeeds, and the other gets `SlotUnavailable` with a clear message (AR-14)

**Given** the phone-in flow
**When** it runs
**Then** `inbox` finds or creates the Customer by `(business_id, phone)` and calls `bookings` before it writes its own rows (AR-4 lock order, AR-10)
**And** one integration test covers this lock order (AR-23)

**Given** the new endpoints
**When** the isolation suite runs
**Then** it covers them (FR-11)

### Story 5.3: Cancel and complete Bookings

As an Owner or Staff member,
I want to cancel a Booking or mark it as completed,
So that the calendar shows the truth.

**Acceptance Criteria:**

**Given** a `confirmed` Booking
**When** a User with Inbox access cancels it
**Then** its state becomes `cancelled`, and its Slot is free again (FR-27)

**Given** a `confirmed` Booking
**When** the User marks it as completed
**Then** its state becomes `completed` (FR-27)

**Given** any Booking state change
**When** it runs
**Then** it is a guarded `UPDATE … WHERE state = :from` inside `bookings`; if the state already changed, nothing happens and the User gets a clear message (AR-14, AR-15)

**Given** a cancelled or completed Booking
**When** someone tries to change it again
**Then** the system refuses

### Story 5.4: Calendar day and week views

As a User,
I want day and week views of my Bookings,
So that I know where to be and when.

**Acceptance Criteria:**

**Given** a User opens `/app/calendar`
**When** the page loads
**Then** mobile shows the day view and desktop shows the week view by default, and the User can switch views (FR-26, UX-DR14)
**And** the views work on a 360px-wide screen (NFR-6)

**Given** Bookings in the view
**When** they are drawn
**Then** each block is colored by the status-badge rules and has text and an icon; requested Bookings have a dashed border (UX-DR6, UX-DR14)

**Given** a Technician-only User
**When** they open the Calendar
**Then** they see only their own assigned Bookings; the API never returns others to them (FR-26, AR-7)

**Given** a User taps a Booking block
**When** the Booking detail sheet opens
**Then** Owner and Staff see Cancel and Complete actions; a Technician sees the details read-only (FR-27, UX-DR27)

### Story 5.5: Deleting a Customer also deletes their Bookings

As an Owner,
I want a Customer delete to remove their Bookings too,
So that no personal data stays behind.

**Acceptance Criteria:**

**Given** a Customer with Conversations and Bookings
**When** the Owner confirms "Delete customer"
**Then** `inbox` calls `bookings.delete_for_customer` first, then deletes its own rows, all in one transaction (NFR-8, AR-11)
**And** the confirm dialog now lists Bookings too (UX-DR28)

**Given** the delete flow
**When** integration tests run
**Then** one test covers the lock order across `inbox` and `bookings` (AR-23)
**And** after the delete, no row of that Customer remains in any table

## Epic 6: AI Agent Books Jobs

The Agent replies in the Customer's language, collects details, shows the Price for acceptance, offers only real free Slots, and creates a Booking Request. Staff confirm, change, or decline it; unanswered requests expire after 12 h. The Agent never invents facts, hands off when it should, and falls back safely when the AI fails or the daily cap is hit.

### Story 6.1: The Agent replies in the background

As a Customer,
I want an answer from the Business's assistant within seconds,
So that I get help even when the owner is busy on a job.

**Acceptance Criteria:**

**Given** the `agent` module
**When** it calls an AI model
**Then** it goes through the AI port; only adapter files import `anthropic` or `openai`; the provider and the exact model id come from env vars (AR-16, AR-24, NFR-9)
**And** the Groq adapter refuses to start outside `local`/`dev`, and a deterministic `FakeAI` adapter serves all tests (AR-16, NFR-7)
**And** the prompt is a versioned file in `agent/prompts/` (AR-17)

**Given** a Customer sends a Message in a Conversation in `agent` state
**When** the web request saves it
**Then** after commit it enqueues `agent_reply` with job key `<conversation_id>:<seq>`, `business_id`, `seq`, and `traceparent`, and returns at once (AR-12, AR-4)

**Given** the worker runs `agent_reply`
**When** it starts
**Then** it takes a Redis lock per Conversation (TTL 30 s), so only one reply job runs at a time, and it answers every Customer Message up to its `seq` (AR-12)

**Given** a newer Customer Message arrived during the job
**When** the job is ready to save
**Then** it drops its own reply, and the newer job answers all Messages
**And** an integration test sends two Messages 1 s apart and gets exactly one Agent reply that covers both (AR-23)

**Given** the Conversation moved to `handoff` during the job
**When** the job is ready to save
**Then** it saves nothing (FR-21, AR-12)

**Given** a Customer Message
**When** the Agent replies
**Then** the reply is in the language and script of that Message: English, Hindi in Devanagari, or Hinglish in Roman script (FR-19)
**And** the bubble is labeled "SevaDesk assistant" (UX-DR7)

**Given** a reply is pending
**When** the Chat Page polls
**Then** the snapshot has a derived `reply_pending`, polls run every 1–2 s, a three-dot indicator shows after 1 s, and "Still working…" after 10 s (AR-12, UX-DR22)

### Story 6.2: Safe fallback when the AI fails

As a Customer,
I want a clear answer even when the AI breaks,
So that I am never left waiting with no reply.

**Acceptance Criteria:**

**Given** an agent turn
**When** it runs
**Then** it has a 9 s deadline from job start and at most 4 tool calls; each AI call gets only the time left; a failed call is not retried (AR-12)

**Given** the AI fails, times out, or the deadline passes
**When** the worker handles it
**Then** it saves "We got your message. The team will reply soon." and calls `inbox.start_handoff` (FR-22, AR-15)

**Given** the worker crashes during a job
**When** the SAQ job timeout fires
**Then** the aborted-job handler writes the FR-22 message and sets Handoff, so every pending reply ends within 30 s (AR-12)

**Given** each job
**When** it starts
**Then** the queue wait time is logged, so NFR-3 can be measured (AR-12, NFR-3)

### Story 6.3: Every AI call is traced and capped

As the builder,
I want each AI call recorded with its cost, and a daily cap per Business,
So that I can debug the Agent and never overspend.

**Acceptance Criteria:**

**Given** any AI call
**When** it finishes
**Then** Langfuse records the prompt version, model, tokens, cost, and latency, linked to the OTel trace (NFR-4, AR-17)
**And** the Langfuse payload passes through the `core` masking function, so no phone number or address appears in plain text (AR-11, NFR-8)

**Given** the per-Business daily Redis counter `cap:<business_id>:<date>`
**When** the worker is about to call the AI
**Then** it runs an atomic `INCR` first, then compares with the cap (200 on demo) (AR-17, NFR-7)

**Given** the cap is reached
**When** the next Customer Message arrives
**Then** the Conversation goes to Handoff, and the Customer sees the normal Handoff copy with no mention of the cap (NFR-7, UX-DR21)

**Given** Grafana Cloud
**When** the daily Agent cost passes a set limit
**Then** an alert fires (AR-21)

### Story 6.4: The Agent collects booking details

As a Customer,
I want the assistant to ask me only for what it still needs,
So that booking is quick and I do not repeat myself.

**Acceptance Criteria:**

**Given** the Agent needs Business facts
**When** it gets them
**Then** it reads Services and Working Hours only through tools whose handlers call other modules' front doors, one tool call at a time (AR-13)
**And** each tool schema is defined once in `agent`, and the AI port translates it per provider (AR-13)

**Given** a Conversation
**When** the Agent works on a booking
**Then** it collects name, phone, address, problem description, and the matching Service before it offers Slots, and asks only for the details still missing (FR-16)

**Given** the Customer gives a phone number
**When** the Agent saves it
**Then** the system checks it is a valid Indian mobile number; if not, the Agent asks again (FR-16)
**And** `inbox` links the Customer by `(business_id, phone)` for the Owner's view only; the visitor never sees other chats by that phone (AR-10)

**Given** the Agent asks which Service
**When** it sends the question
**Then** it attaches Service choice chips that are real buttons; chips show on the last Agent Message only, and typing also works (UX-DR9)

### Story 6.5: The Customer sees and accepts the Price

As a Customer,
I want to see the Price and agree to it before I pick a time,
So that there are no surprises.

**Acceptance Criteria:**

**Given** the Customer chose a Service
**When** the Agent calls the quote tool
**Then** `bookings.quote_price(service_id)` stores a quote with the Price, tied to that Conversation, with its own fixed expiry (FR-16a, AR-13, AR-24)
**And** the new tenant table `price_quotes` is owned by `bookings`

**Given** a stored quote
**When** the Agent's reply is shown
**Then** the server builds the Price chip "Accept ₹X" with the `quote_id`, plus "No", and the text "Final price after inspection. Parts extra." (FR-12, UX-DR8, UX-DR9)
**And** the Price appears only in this server-built chip, never in the model's reply text (AR-13)

**Given** the Customer taps "Accept ₹X"
**When** the server receives it
**Then** it records the acceptance directly, with no tool call; the model can never mark a quote accepted (AR-13)

**Given** the Customer taps "No" or asks for a discount
**When** the Agent replies
**Then** it does not change the Price, and it offers a Handoff for price questions (FR-20)

### Story 6.6: The Agent offers free Slots and creates a Booking Request

As a Customer,
I want to pick a real free time and send a booking request,
So that the Business can confirm my job.

**Acceptance Criteria:**

**Given** an accepted quote
**When** the Agent offers times
**Then** it calls the free-Slots tool and the server shows at most 4 Slot chips (for example "Tomorrow 10:00 am") plus "Other times" (FR-17, UX-DR9)

**Given** no free Slot in the next 7 days
**When** the Agent checks
**Then** it says so and offers a Handoff (FR-17)

**Given** the Customer taps a Slot chip
**When** the request tool runs
**Then** `bookings.create_request(quote_id, slot)` takes the capacity lock, refuses a quote that is not accepted, is expired, or belongs to another Conversation, takes the Price from the quote, and saves a `requested` Booking with `expires_at` 12 h later (FR-16a, FR-18, AR-13, AR-14)
**And** `UNIQUE (bookings.quote_id)` makes a repeated call create no second Booking (AR-14)

**Given** anti-hoarding limits
**When** a Conversation, visitor token, or client IP already has its maximum of open requests (fixed constants set in this story)
**Then** a new request is refused inside the lock (AR-14, AR-24)

**Given** the Slot was just taken by someone else
**When** `SlotUnavailable` is raised
**Then** the Agent says "Sorry, that time was just taken. Here are other times:" with new Slot chips (FR-18, UX-DR21)

**Given** the request is saved
**When** the Chat Page polls
**Then** it shows "Request sent ✓ {Business} will confirm soon. You'll see the update here." and the snapshot includes the Booking status, composed by `inbox` calling `bookings` (FR-18, AR-12, UX-DR21)

**Given** a write tool committed but the final reply failed
**When** the Chat Page polls
**Then** the Booking stays and the snapshot shows it (AR-4)

### Story 6.7: The Agent never invents facts and hands off by itself

As an Owner,
I want the assistant to say only what my data says, and to call a human when it should,
So that it never makes a promise I cannot keep.

**Acceptance Criteria:**

**Given** a draft Agent reply
**When** the post-check runs before sending
**Then** it rejects any money amount or Slot time or date in the text, in any script or wording; on failure the text is generated once more (tools are not re-run), then the Conversation hands off (FR-20, AR-13)

**Given** a question that the Business data cannot answer (policy, opening time, anything else)
**When** the Agent replies
**Then** it says the Business will answer and offers a Handoff (FR-20)

**Given** the Customer asks for a person, the Agent fails to understand twice in a row, or the topic is a complaint or refund
**When** the Agent detects it
**Then** it says "Connecting you to the team. Someone will reply here." and calls `inbox.start_handoff`; it sends no more Messages in that Conversation (FR-21, UX-DR21)

**Given** a Message in a language other than English or Hindi
**When** the Agent replies
**Then** it sends a short English reply and hands off (FR-19)

### Story 6.8: Staff confirm, change, or decline a Booking Request

As an Owner or Staff member,
I want to act on a Booking Request in one tap,
So that the Customer gets an answer fast.

**Acceptance Criteria:**

**Given** a Conversation with a `requested` Booking
**When** a User opens it
**Then** the Booking Request card shows Customer, Service, Price shown, Slot, address, an amber "Expires in N h" countdown, and Confirm, Change, Decline (UX-DR10)
**And** the Inbox row shows a derived "Booking Request" badge (FR-23, AR-15)

**Given** the User taps Confirm
**When** the Business has one active Technician
**Then** that Technician is assigned automatically and the Booking becomes `confirmed` (FR-25)
**And** with more than one Technician, a free Technician must be chosen; the system checks the Technician has no overlapping confirmed Booking (AR-14)

**Given** the User taps Change
**When** the sheet opens
**Then** they can pick a new free Slot, and a Technician if there is more than one, then confirm (FR-25, UX-DR10)

**Given** the User taps Decline
**When** they pick a preset reason or type one
**Then** the Booking becomes `declined`, its Slot is free, and the Chat Page shows "{Business} can't take this request. Reason: {reason}." (FR-25, UX-DR21)

**Given** a confirm
**When** the Customer's Chat Page polls
**Then** it shows "Confirmed: {Service}, {date}, {time}." within 5 s (FR-25, UX-DR21)

**Given** two Users act on the same request at once
**When** both run
**Then** the guarded `UPDATE … WHERE state = 'requested'` lets only one win, and the other sees a clear message (AR-14)

### Story 6.9: Booking Requests expire after 12 hours

As a Customer,
I want to know when nobody confirmed my request,
So that I can call the Business or try again.

**Acceptance Criteria:**

**Given** a `requested` Booking older than its `expires_at`
**When** any read or count runs
**Then** it counts as expired, and its Slot is free (FR-18a, AR-14)

**Given** the hourly sweep
**When** it runs
**Then** a cross-tenant cron enqueues one job per Business, and each job persists the `expired` state with a guarded update (AR-6, AR-14, AR-22)

**Given** a confirm and an expiry race on the same request
**When** both run
**Then** only one state change wins (AR-14)

**Given** an expired request
**When** the Customer's Chat Page polls
**Then** it shows "Not confirmed. Please contact the business, or send a new request below." and the Customer can start a new request in the same chat (FR-18a, UX-DR21)

**Given** an expired request
**When** a User opens the Inbox
**Then** the Conversation stays visible with a zinc "Expired" badge for follow-up (FR-18a, UX-DR6, UX-DR11)

## Epic 7: Proven Agent Quality

The builder creates a reviewed Golden Dataset of at least 30 English and Hindi/Hinglish cases. Evals run the real agent loop and block any merge that invents a Price or Slot, or that drops below baseline.

### Story 7.1: Golden Dataset format and draft-and-review tool

As the builder,
I want to turn Scenario Cards into draft conversations and approve each one by hand,
So that the dataset is realistic and every case is checked by a human.

**Acceptance Criteria:**

**Given** two fixed eval Businesses (one solo, one team) with fake Services, Prices, Working Hours, and Technicians, seeded through module front doors
**When** the eval fixture loads
**Then** it uses the audited `system_scope` and contains no real personal data (FR-30, AR-6)
**And** the data lives in one place that the Epic 8 demo seed will reuse

**Given** a Scenario Card (Service, language, Customer behavior, expected result)
**When** the builder runs the draft command
**Then** an LLM writes a draft conversation, saved as a case with status `draft` (FR-30)

**Given** a case
**When** it is saved
**Then** it stores the conversation, the language, the expected details, the expected Service and Price shown, and the expected result (Booking Request, Handoff, or no booking) (FR-30)

**Given** a draft case
**When** the builder reviews and fixes it, then marks it `reviewed`
**Then** only `reviewed` cases are used by the eval runner (FR-30)

### Story 7.2: Code checks run the real agent loop

As the builder,
I want each case scored by code against the real Agent,
So that I test exactly what production runs.

**Acceptance Criteria:**

**Given** a reviewed case
**When** the eval runner plays it
**Then** it runs the real agent loop against a seeded Testcontainers database, at temperature 0 (AR-18)

**Given** the run finishes
**When** the code checks score it
**Then** they score: detail extraction, correct Booking result and Service, no invented Price or Slot, no Booking Request without an accepted Price, and language match (NFR-2)

**Given** any case where the Agent invents a Price or Slot, or creates a request without an accepted Price
**When** the runner reports
**Then** that check is a hard fail with a zero tolerance (SM-3, AR-18)

**Given** the runner result
**When** it is written
**Then** it records the prompt version, model, and dataset version (AR-17)

### Story 7.3: The first 30 reviewed cases and the baseline

As the builder,
I want a first dataset that covers the main real-life situations,
So that the Agent's quality is measured on what Customers really do.

**Acceptance Criteria:**

**Given** the draft-and-review tool
**When** the builder finishes this story
**Then** the dataset has at least 30 `reviewed` cases, about half English and half Hindi or Hinglish (FR-30)

**Given** the cases
**When** they are listed by scenario
**Then** they cover happy paths, missing details, Price questions and discount requests, no free Slot, a request for a person, and an unsupported language (FR-30)

**Given** the full set runs once
**When** it finishes
**Then** its scores are saved as the baseline score file in the repo (AR-18)
**And** the result shows whether SM-2 (≥ 90% correct bookings) and SM-5 (≥ 95% language match) are met

### Story 7.4: Tone judge and merge gates in CI

As the builder,
I want CI to block any change that makes the Agent worse,
So that AI quality never goes down by accident.

**Acceptance Criteria:**

**Given** the code checks pass for a case
**When** the LLM judge runs
**Then** it scores tone (polite, warm, brief) and adds the score to the result (NFR-2)

**Given** a pull request
**When** CI runs the eval step
**Then** it replaces the P0 placeholder with the smoke set, run with Claude's cheap model, and each smoke case runs twice (AR-18)

**Given** the eval results
**When** they are compared with the baseline
**Then** any hard-zero failure blocks the merge, and other metrics block only when they drop more than the fixed tolerance (a constant set in this story) below baseline (AR-18, AR-24)

**Given** a schedule or a manual trigger
**When** the full eval set is requested
**Then** it runs nightly or on demand, not on every PR (AR-18)

**Given** a pull request from a fork
**When** CI runs
**Then** the eval step that needs the Claude key does not get it (AR-18)

## Epic 8: Dashboard and Portfolio Demo

The Owner sees today at a glance. Demo and AWS start with seeded solo and team Businesses that can be reset. A public landing page explains SevaDesk and opens the demo. The full app deploys to AWS and passes the E2E tests there.

### Story 8.1: Owner Dashboard shows today at a glance

As an Owner,
I want one screen with everything that needs me today,
So that I can act in a few taps between jobs.

**Acceptance Criteria:**

**Given** an Owner or Staff member opens `/app`
**When** the Dashboard loads
**Then** it shows today's confirmed Bookings, waiting Booking Requests, Conversations in Handoff, and the counts of new Conversations and confirmed Bookings this week (FR-28)
**And** `dashboard` owns no tables and reads only through the `bookings`, `inbox`, and `business` front doors (AR-1, AR-2)

**Given** a waiting Booking Request
**When** it shows on the Dashboard
**Then** it uses the same Booking Request card as the Conversation, with the amber time-left countdown and Confirm, Change, Decline (FR-18a, UX-DR10)

**Given** any Dashboard item
**When** the Owner taps it
**Then** it opens its detail screen (FR-28)

**Given** the Dashboard
**When** it loads
**Then** Skeleton rows show first, it polls every 5 s while visible, and the first-run checklist from Story 3.3 still shows until setup is done (UX-DR23, UX-DR25)
**And** it shows no revenue (FR-28)

### Story 8.2: Seeded demo Businesses with a reset command

As the builder,
I want the demo to start with ready-made Businesses and logins,
So that a visitor can try SevaDesk at once, with no setup.

**Acceptance Criteria:**

**Given** the `demo` module
**When** the seed command runs
**Then** it creates at least two demo Businesses (one solo, one team) with fake Services, Prices, Working Hours, Technicians, Conversations, and Bookings, through module front doors only (FR-29, AR-2)
**And** it reuses the eval fixture data from Story 7.1, so demo and evals match

**Given** the seed
**When** it runs
**Then** it uses the audited `system_scope`, and it contains no real personal data (FR-29, AR-6)

**Given** the demo logins
**When** a visitor uses the "Demo log-in"
**Then** they log in as the demo Owner of the solo Business (FR-29)

**Given** the reset command
**When** it runs
**Then** demo data returns to its seeded state, and real (non-demo) Businesses are untouched (FR-29)
**And** the deploy pipeline runs it after each demo deploy (AR-20)

### Story 8.3: Portfolio landing page

As a recruiter or visitor,
I want one page that shows what SevaDesk does and lets me try it,
So that I understand the project in a minute.

**Acceptance Criteria:**

**Given** a visitor opens `/`
**When** the page loads
**Then** it shows the floating glass pill navbar, a dark 92vh hero with the blurred "SEVA" word and glass stat cards, a feature grid, "How it works" with steps 01–03, and a "How it's built" bento (Tests · Evals · Tracing/AWS) (FR-31, UX-DR15, UX-DR30)
**And** it shows no pricing (FR-31)

**Given** the call-to-action buttons
**When** the visitor taps them
**Then** "Try the chat" opens a demo Chat Page, "Demo log-in" logs in as the demo Owner, and a link opens the GitHub repository (FR-31, UX-DR5)

**Given** the page
**When** CI checks its size
**Then** it is under 1 MB on mobile, with no photos (CSS or SVG gradients and the grain SVG only) (FR-31, UX-DR30)

**Given** a device with `prefers-reduced-motion`
**When** the page loads
**Then** the fade-in-up and hover-scale animations are off (FR-31, UX-DR34)

**Given** the glass styles
**When** the app screens render
**Then** they never use glass, grain, or blur (UX-DR15, UX-DR19)

### Story 8.4: End-to-end tests for the key journeys

As the builder,
I want automatic browser tests for the three main user journeys,
So that I know the whole product still works after every change.

**Acceptance Criteria:**

**Given** Playwright tests that run with the `FakeAI` adapter
**When** CI runs them on every pull request
**Then** they pass for UJ-1 (Customer books, Owner confirms, Chat Page shows "Confirmed" within 5 s), UJ-2 (Customer asks for a person, Staff take over, create a Booking by hand, give back), and UJ-3 (Owner signs up, adds Services and Working Hours, copies the chat link) (NFR-10, AR-23)

**Given** a failing journey
**When** CI runs
**Then** the merge is blocked, and the test report has a trace of the failed steps

**Given** the E2E tests
**When** they run
**Then** they work at a 360px phone width and at desktop width (NFR-6)
**And** they run on Chromium (the Chrome on Android target), WebKit (the Safari on iOS target), and Firefox (UX-DR35)

### Story 8.5: The full app runs on AWS for an interview

As the builder,
I want to deploy the full app to AWS, show it, and destroy it,
So that SevaDesk is portfolio-ready.

**Acceptance Criteria:**

**Given** the Story 1.7 Terraform setup
**When** the builder deploys the current version to AWS staging
**Then** migrations run, the demo seed runs, and the landing page, Chat Page, and app work at the AWS URL (FR-6, FR-29, SM-1)

**Given** the AWS environment
**When** the E2E tests run against the AWS URL
**Then** they pass (SM-1)

**Given** the UJ-4 interview demo
**When** a visitor books on a demo Chat Page in one tab and confirms it from "Demo log-in" in a second tab
**Then** the first tab shows "Confirmed" within 5 s, with the real Claude Agent

**Given** the demo session is over
**When** the builder runs the destroy command
**Then** no billable AWS resource remains (FR-6)
