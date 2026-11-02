---
type: architecture-review
lens: adversarial (compliant-but-incompatible unit pairs)
target: ../ARCHITECTURE-SPINE.md
date: '2026-11-01'
verdict: 'Not build-ready. The module map is sound, but transactions, tenant context outside requests, technician identity, and polling are under-specified. Two units can each obey every AD and still not fit.'
---

# Adversarial Review — Architecture Spine, SevaDesk MVP

## Method

For each hole I describe two units (stories or epics) built by different people. Each one obeys every AD to the letter. Together they still break. Then I propose a new or tighter AD rule. Severity:

- **Critical**: wrong data, a cross-tenant leak, or a double booking in production.
- **High**: the units do not integrate without rework.
- **Medium**: drift that costs a refactor later.

## Summary table

| # | Hole | Severity | Proposed rule |
| --- | --- | --- | --- |
| H1 | AD-9 locks the `businesses` row, but AD-1/AD-2 say only `business` may query that table | Critical | AD-9': bookings uses its own lock (a `pg_advisory_xact_lock` keyed on business_id, or a bookings-owned `booking_capacity` row) |
| H2 | Nobody owns the transaction. AD-9 and AD-13 say "one transaction", but front doors can call each other and AD-7 allows long AI calls | Critical | AD-15 Unit of Work: the entry point owns the transaction, services never commit, and no external I/O runs while a transaction is open |
| H3 | Tenant context is missing for login, invites, sign-up, the 12 h cron, demo seeding, and evals | Critical | AD-3': named context entry points, plus one audited `system_scope` |
| H4 | The polling cursor is undefined, UUIDv7 order is not commit order, and booking status changes write no message | Critical | AD-7': a per-conversation `seq` plus a status snapshot in every poll response |
| H5 | Agent jobs for one Conversation can run in parallel, and the state check is a time-of-check/time-of-use race | Critical | AD-7'': one job per Conversation (dedupe), and a conditional `save_agent_message` |
| H6 | Booking state changes race each other: the expiry job, confirm, and decline are not all under the lock | Critical | AD-10': every Booking transition is a guarded update (`WHERE state = expected`) under the AD-9 lock |
| H7 | AD-4 stores a single `role`, but FR-7/FR-9 need several roles per person. Technician identity is not fixed | High | AD-4': a set of roles; Technician = `membership_id`; memberships are soft-deactivated |
| H8 | Where the Price the Customer accepted comes from: the LLM's tool args or a fresh read of the Service | Critical | AD-8': a server-recorded `price_quote` per Conversation; `create_request` takes its id |
| H9 | Conversation state vs the "Booking Request" badge; who sets handoff, and through which function | High | AD-10'': a closed list of Conversation transitions with named inbox functions; the badge is derived |
| H10 | inbox → agent import cycle through job enqueue and the handoff fallback | High | AD-2': job names and the queue helper live in `core`; `worker.py` is the only composition root |
| H11 | No Actor model, so role checks, agent tools, seeding, and jobs authorize in different ways | High | AD-16: every front-door write takes an `Actor` |
| H12 | Front doors return ORM objects; models carry cross-module relationships | High | AD-2'': front doors return DTOs; no cross-module ORM relationships |
| H13 | Customer delete (AD-13): order across modules, foreign keys, and PII copied into bookings | High | AD-13': one transaction, a fixed delete order, a declared PII snapshot |
| H14 | Who owns customer details and the phone-in booking; is `conversation_id` nullable | High | AD-17: customer details are written only through inbox; a Booking stores a snapshot; `conversation_id` is nullable |
| H15 | Public Chat Page identity: a guessable UUIDv7, no rule for the visitor token | Critical | AD-5': an opaque visitor token in an httpOnly cookie, scoped to the slug |
| H16 | Time: slot step, "today", "this week", and the daily cap day boundary each computed their own way | Medium | One time module in `core`; the slot step is a constant |
| H17 | Technician deactivation vs future bookings and capacity | Medium | Deactivation goes through a bookings check under the AD-9 lock |
| H18 | Several Alembic heads from parallel module stories | Medium | CI asserts a single head; one migration per story |

---

## H1 — AD-9's lock reads a table that AD-2 forbids (Critical)

**Pair.**
- **Story A (bookings, FR-18).** It follows AD-9 to the letter: `SELECT … FROM businesses WHERE id = :bid FOR UPDATE`.
- **Story B (business, FR-12/14).** It follows AD-1: `businesses` belongs to `business`. It adds a `BusinessRepository` with an optimistic `version` column, or it caches the row.
- **Result.** Story A queries another module's table. That breaks AD-2. A reviewer applying AD-2 rejects Story A. A reviewer applying AD-9 rejects any alternative.
- **A worse variant.** Story A calls `business.service.lock_business()` instead. The lock then lives in a transaction that `business` opened, so Story A's recount runs outside it (see H2).

There is a second problem. Every Owner edit to the Business (name, timezone) waits behind booking writes, and booking writes wait behind those edits.

**Proposed rule (AD-9').** The capacity lock belongs to `bookings`. Use `SELECT pg_advisory_xact_lock(hashtextextended('capacity:' || business_id, 0))`, or a bookings-owned `booking_capacity(business_id)` row locked `FOR UPDATE`. Take it as the first statement of any capacity write. No other module takes it.

## H2 — Nobody owns the transaction (Critical)

AD-9 says "one transaction in bookings". AD-13 says "each module deletes its own rows in one transaction". FastAPI plus SQLAlchemy gives every developer a different default.

**Pair 1: nested commits.**
- **Agent tool story.** `create_booking_request` calls `bookings.create_request()`, then `inbox.save_agent_message()`.
- **Bookings story.** `create_request` opens `with session.begin():` and commits. That is what AD-9 literally says.
- **Inbox story.** It uses the request or job session and commits at the end.
- **Result.** If the Agent Message write fails, the Booking Request already exists and holds a Slot, with no message telling the Customer. Or, if both use `session.begin()` on one session, SQLAlchemy raises "a transaction is already begun".

**Pair 2: the lock is held during the AI call.**
- **Worker story.** It wraps the whole `agent_reply` job in one transaction for safety.
- **Agent loop.** Inside that job it calls Claude (up to about 10 s), runs tools, and calls Claude again.
- **Result.** If a booking tool ran first, the AD-9 lock is held across the second AI call. Every other booking for that Business (Inbox confirms, other Customers) stalls for seconds. That breaks NFR-3's 500 ms target. A DB connection is also tied up on the Postgres free tier.

**Pair 3: lock order.**
- **Phone-in booking (inbox composes it).** It inserts a customer and a conversation, then calls bookings, which takes the capacity lock.
- **Customer delete (AD-13).** It runs bookings first (which may take the lock), then inbox.
- **Result.** The two flows take locks in opposite orders. That is a deadlock risk.

**Proposed rule (AD-15 — Unit of Work).**
1. The entry point owns the one transaction: the router dependency for HTTP, the job wrapper for the worker, the CLI command for seed or reset. It commits on success and rolls back on error.
2. Services and repositories never call `commit()` or `begin()`. They use the ambient session from `core`. `bookings` may use `session.begin_nested()` (a SAVEPOINT) only to recover from `SlotUnavailable`.
3. No external I/O while a transaction is open: no AI provider, no Redis enqueue (enqueue after commit), no HTTP. The agent loop runs each tool call in its own short transaction, with no open transaction during the model call.
4. Lock order: the capacity lock (AD-9') is the first lock taken in any transaction that touches bookings.

## H3 — Tenant context gaps (Critical)

AD-3 lists three sources of tenant context: session, chat slug, and job payload. Each case below is either covered by none of them or covered in a way that contradicts the base repository.

| Unit | Why it breaks AD-3 |
| --- | --- |
| **Login / session resolve** (accounts) | You must read `memberships` to find `business_id`. But `memberships` is tenant-scoped, and no tenant is set yet. The developer either marks memberships as global (which AD-3 does not allow) or writes a raw query. |
| **Invite accept** (FR-9) | The person has no session. Looking up `invites` by token needs to search across all Businesses. |
| **Sign-up** (FR-7) | It creates the Business, then a membership. The base repository sets `business_id` from context, so the context must change in the middle of the request. No rule says how. |
| **12 h expiry job** (FR-18a) | A cron job has no `business_id` in its payload. One developer writes `UPDATE bookings SET state='expired' WHERE …` across all tenants, which breaks NFR-1. Another enqueues one job per Business but needs an unscoped list of Businesses. |
| **Demo seed / reset** (FR-29) | It seeds through front doors, but there is no session and many Businesses. "Reset" means deleting whole Businesses, and no front door does that. |
| **Evals runner** | It drives the agent against the seeded Businesses. Which context source applies? |
| **Redis keys** | The daily cap counter and rate limits: key shape and day boundary (see H16). If one story writes `cap:{date}` and another reads `cap:{business_id}:{date}`, the counts never match. |

**Proposed rule (AD-3').**
- **(a)** `core.tenant` exposes exactly these ways to set context: `from_session`, `from_chat_slug`, `from_job(payload)`, and `system_scope(reason)`.
- **(b)** `system_scope` is the only unscoped mode. Only these may use it: session resolution, invite-token lookup, sign-up, cron fan-out (`business.list_active_business_ids()`), and demo reset. Every use is logged, and a lint/grep test lists the allowed callers.
- **(c)** Cron jobs never touch tenant rows. They fan out one job per Business, with `business_id` in each payload.
- **(d)** Sign-up switches context with `tenant.bind(business_id)` right after the Business is inserted.
- **(e)** `sessions` holds `user_id` only. Membership is resolved after that.
- **(f)** Redis keys are `{purpose}:{business_id}:{scope}`.

## H4 — The polling cursor is undefined and unsafe (Critical)

AD-7 says `GET … ?after=<cursor>`.

**Pair.**
- **Chat Page story.** The cursor is the last `message.id`, because UUIDv7 is time-ordered.
- **Inbox list story.** The cursor is `conversations.updated_at`.
- **Bookings confirm story (FR-25).** It changes `bookings.state`. It writes no Message, because bookings cannot import inbox.
- **Result 1: missed status.** A message-id cursor never returns the confirm. FR-25's "Chat Page shows the new status within 5 s" fails, and so does FR-18a's "Not confirmed".
- **Result 2: missed messages.** UUIDv7 ids are made in two processes (web and worker), and id order is not commit order. Transaction X gets the id `…01`. Transaction Y gets `…02` and commits first. The poll returns Y and moves the cursor to `…02`. Then X commits, and it is never delivered.
- **Result 3: no stop signal.** AD-7 says to poll "fast only while a reply is pending". The frontend guesses "pending" from "the last message is the Customer's". In Handoff no reply may come for hours, so it polls fast forever.

**Proposed rule (AD-7').**
- Each Conversation has `last_seq`. Every Message insert does `UPDATE conversations SET last_seq = last_seq + 1 … RETURNING last_seq` and stores it as `messages.seq`. The row lock makes the order the same as the commit order.
- The cursor is an opaque string that encodes `seq`. Clients never parse it.
- Every poll response returns `{messages_after_cursor, next_cursor, conversation_state, reply_pending, bookings: [current status snapshot]}`.
- The booking snapshot is always the full current value, not a delta. `inbox` composes it by calling `bookings.status_for_conversation()`.
- `reply_pending` is computed on the server (an agent job is queued or running).
- The Inbox list uses `(last_activity_at, id)` keyset paging with a small overlap window, and the client deduplicates by id.

## H5 — Concurrent agent jobs and a state check race (Critical)

**Pair.**
- **Chat story.** Each Customer Message enqueues `agent_reply(business_id, conversation_id)`. That obeys AD-7.
- **Worker story.** arq runs jobs concurrently by default.
- **Inbox reply story.** A User reply sets `handoff`. That obeys AD-10.
- **Result 1: double replies.** The Customer sends "AC repair" and then "tomorrow" within 1 s. Two jobs run at the same time. Two replies go out, and there may be two Booking Requests.
- **Result 2: reply after takeover.** The worker checks state = `agent` (as AD-10 requires) and calls Claude. The User takes over. The worker saves its reply anyway, so the Agent talks during a Handoff. That breaks FR-21.

**Proposed rule (AD-7'').**
- Set `_job_id = f"agent_reply:{conversation_id}"` so that only one job is queued or running per Conversation. A job that starts handles every unanswered Customer Message up to the latest `seq`.
- `inbox.save_agent_message(conversation_id, text, expected_state="agent", based_on_seq=n)` saves only if the state is still `agent`. Otherwise it discards the reply and records the discard.
- Booking tools also re-check the Conversation state inside their own transaction.

## H6 — Booking transitions race each other (Critical)

AD-9 takes the lock only for writes that "take or move capacity". Expiry and decline free capacity, so they are not covered.

**Pair.**
- **Expiry job.** It runs `UPDATE bookings SET state='expired' WHERE state='requested' AND created_at < now() - 12h`. There is no lock, because AD-9 does not require one.
- **Confirm (FR-25).** It loads the booking (`requested`), takes the lock, checks the Technician, and sets `confirmed`.
- **Result 1.** In the same second, confirm overwrites `expired` with `confirmed`, or expiry overwrites `confirmed`. The Customer sees "Not confirmed" while a Technician is dispatched.
- **Result 2.** Decline and "change Slot" race in the same way.

**Proposed rule (AD-10').**
- Every Booking transition is one bookings function that runs `UPDATE … SET state=:to WHERE id=:id AND state=:from` under the AD-9' lock and checks the row count. Zero rows raises `BookingStateConflict`, which maps to 409.
- Expiry is measured from a stored `expires_at`, set when the request is created.
- The transition table in code is the single source of truth, and it is tested.

## H7 — Roles and technician identity (High)

**Pair.**
- **Accounts story.** AD-4 literally says `memberships(user_id, business_id, role)`. The developer makes one enum column.
- **Sign-up story (FR-7).** It needs Owner **and** Technician on one person. FR-9 needs "one or more Roles". The developer adds a second membership row, but AD-4's unique constraint on `user_id` blocks it. So they add `is_technician` to `users`, which breaks AD-4's purpose.
- **Bookings story.** It stores `technician_user_id`. The ER diagram says memberships → bookings. Calendar (FR-26, "a Technician sees only their own") filters by the session's `membership_id`. The two never match.
- **Member removal (AD-5).** It hard-deletes the membership, so `bookings.technician_*` either dangles or the foreign key blocks the removal.

**Proposed rule (AD-4').**
- Memberships hold `roles` as a set (a Postgres enum array, or a `membership_roles` child table owned by accounts).
- Bookings reference `technician_membership_id`.
- Memberships are never hard-deleted while any Booking references them. Removal sets `deactivated_at` and deletes sessions.
- "Active Technician" = membership active AND `technician ∈ roles`. Only `accounts.list_active_technicians()` computes it.

## H8 — Provenance of the accepted Price (Critical)

AD-10 says "a Booking stores the `price_paise` the Customer accepted". It does not say where that number comes from.

**Pair.**
- **Agent tool schema.** `create_booking_request(service_id, slot_start, price_paise)`. The LLM fills in `price_paise`.
- **Bookings story.** It trusts the argument. Or it reads `business.get_service().price_paise` at creation time.
- **Result.** In the first case, a prompt-injected Customer ("book at ₹1") gets a stored ₹1 Price. AD-8's post-check only checks the reply text, not tool arguments. In the second case, if the Owner changed the Price between the quote and the booking, the stored Price is not the one the Customer saw. That breaks FR-16a. Nobody enforces "no request unless the Price was accepted".

**Proposed rule (AD-8').**
- The `get_service_price` tool writes a server-side `price_quotes(conversation_id, service_id, price_paise, quoted_at)` row. It is owned by agent or inbox, and the story must name the owner.
- An `accept_price(quote_id)` tool marks the quote accepted. It is only allowed after a Customer Message that follows the quote.
- `bookings.create_request(..., accepted_quote_id)` copies the Price from the quote. The LLM never supplies money.
- AD-8's post-check also covers tool arguments.

## H9 — Conversation state vs "Booking Request" (High)

**Pair.**
- **Inbox list story (FR-23).** It needs the row states Agent / Needs Human / **Booking Request**. The developer adds `booking_request` to the Conversation state enum.
- **Agent story.** It obeys AD-10's three states. After `create_request` it leaves the Conversation in `agent`. Or it sets `closed`, because "the job is done".
- **Result.** Either there are two sources of truth for "has a request", or Customers who come back to a `closed` Conversation get no Agent. FR-18a says the Customer "can start a new request in the same chat". Who reopens it?
- **A further gap.** AD-10 names one setter for `handoff` (a User reply). FR-21's agent-triggered handoff, FR-22's fallback, the daily cap (AD-12), and "give back to Agent" each invent their own call.

**Proposed rule (AD-10'').**
- Conversation state stays `agent | handoff | closed`. The transitions are only these inbox functions:
  - `start_handoff(reason ∈ {customer_asked, not_understood, out_of_scope, ai_failure, cap_reached, unsupported_language, user_replied})`
  - `return_to_agent()`
  - `close()`
  - `reopen_on_customer_message()` (a Customer Message on a `closed` Conversation reopens it to `agent`)
- Creating a Booking Request never changes Conversation state.
- The Inbox badge is derived: inbox batch-calls `bookings.open_requests_for(conversation_ids)`.

## H10 — Import cycle through jobs (High)

**Pair.**
- **Inbox chat-POST story (AD-7).** "Enqueue an `agent_reply` job". The developer imports `agent.service.agent_reply` to enqueue it by function reference. That creates the edge inbox → agent.
- **Agent story.** It needs `inbox.get_history`, `save_agent_message`, and `start_handoff`. That creates agent → inbox.
- **Result.** A cycle, which the dependency diagram forbids. The same thing happens if the FR-22 fallback is written inside inbox.

**Proposed rule (AD-2').**
- Job names are string constants in `core/jobs.py`. The enqueue helper `core.queue.enqueue(name, payload)` runs after commit.
- `worker.py` is the only composition root: it maps names to `agent`/`bookings` handlers.
- An import-linter contract (for example `import-linter` layers) enforces the diagram in CI.

## H11 — No Actor, so authorization is inconsistent (High)

**Pair.**
- **Bookings story.** It puts role checks in the service (`require_role(INBOX)`), because "role checks happen in the backend".
- **Agent tool story.** It calls `bookings.create_request` from the worker. There is no user, so the call fails, or the developer adds a `skip_auth=True` flag.
- **Demo seed.** It needs the same bypass.
- **Router story.** It puts checks in FastAPI dependencies instead. Now the worker path has no checks at all.

**Proposed rule (AD-16).**
- Every front-door write takes `actor: Actor`. The types are `StaffActor(membership_id, roles)`, `CustomerActor(conversation_id)`, and `SystemActor(job_name)`.
- Each function declares which actor kinds and roles it allows.
- Routers build the actor. Jobs and seeds build a `SystemActor`. The isolation and role test suites go through this one place.

## H12 — ORM objects cross module lines (High)

**Pair.**
- **business story.** It returns a SQLAlchemy `Service` from `business.service.get_service()`.
- **bookings story.** It declares `relationship("Service")` on `Booking` "for convenience", and dashboard reads `booking.service.name`.
- **Result.** AD-2 is never visibly broken, yet bookings now depends on business's table shape. Lazy loads also fail with "DetachedInstanceError" after the session closes. That fails in the worker in particular.

**Proposed rule (AD-2'').** Front doors return Pydantic or frozen dataclass DTOs from `schemas.py`, never ORM instances. No `relationship()` and no `ForeignKey` import that crosses modules. Cross-module foreign keys are declared at the column level only, by table name.

## H13 — Customer delete (High)

AD-13: "each module deletes its own rows in one transaction".

**Pair.**
- **Bookings story.** It adds `FOREIGN KEY (conversation_id) REFERENCES conversations ON DELETE RESTRICT`. That is good hygiene, and nothing forbids it.
- **Inbox delete story.** It deletes messages, then conversations, then customers, then calls `bookings.delete_for_customer`.
- **Result.** The foreign key fails. Another reading of the rule gives one transaction per module, which leaves a partial delete when step 3 fails. That is exactly what AD-13 claims to prevent.
- **More gaps.** Booking PII copies (H14), price quotes (H8), Langfuse traces (masked, but still holding conversation text?), and Redis keys are not listed.

**Proposed rule (AD-13').**
- Delete is one transaction (AD-15), composed by `inbox.delete_customer`.
- Fixed order: bookings → price quotes → messages → conversations → customers.
- Cross-module foreign keys use `ON DELETE RESTRICT`, so a wrong order fails loudly.
- Every table holding Customer PII is listed in a `PII_TABLES` registry in `core`, and a test checks that delete clears all of them.

## H14 — Customer details and the phone-in booking (High)

**Pair.**
- **Agent story.** Its `save_customer_details` tool writes name, phone, and address through `inbox.update_customer`.
- **Bookings story.** It stores the address on the Booking for the Technician, because Technicians cannot read inbox data.
- **Phone-in story (FR-27).** It is built in the bookings router. But bookings cannot create a customer, so it takes free-text fields. Or it is built in inbox with a fake Conversation, because `conversation_id` is required.
- **Result.** There are three places for the same data, and they disagree.

**Proposed rule (AD-17).**
- `customers` is the only editable record, written only by inbox.
- A Booking stores a declared, immutable `contact_snapshot` (name, phone, address, problem) at creation, and it is listed in `PII_TABLES`.
- `bookings.conversation_id` is nullable. A phone-in booking is the endpoint `inbox.create_phone_in_booking`, which creates or finds the customer by phone, then calls bookings.

## H15 — Public Chat Page identity (Critical)

**Pair.**
- **Chat frontend.** It keeps `conversation_id` in `localStorage` and sends it as a path parameter. AD-3 only forbids `business_id` from the URL.
- **Inbox chat API.** It scopes by slug → business and returns the Conversation if the id matches.
- **Result.** Anyone who knows or guesses a `conversation_id` for that Business can read its messages. UUIDv7 is about 74 random bits plus a timestamp, and ids leak in logs and screenshots. Those messages contain phone numbers and addresses, which is a DPDP problem. Rate limiting "per Conversation" (NFR-5) is also undefined without an identity.

**Proposed rule (AD-5').**
- On the first Message the server creates a random 256-bit visitor token. It is stored hashed and set as an `httpOnly; Secure; SameSite=Lax; Path=/c/{slug}` cookie.
- Chat endpoints resolve slug → business, then token → conversation. They never take a `conversation_id` from the client.
- Rate limits key on IP and token.

## H16 — Time boundaries (Medium)

- **Pair 1.** The Slots story uses a 30-minute grid. The phone-in booking story allows any minute. Then the overlap math and the agent's "free Slot" offers disagree.
- **Pair 2.** Dashboard "today" and "this week" use UTC. The daily cap counter (AD-12) resets at UTC midnight, which is 05:30 IST. The calendar uses the Business timezone.

**Proposed rule.**
- `core.time` provides `business_day_bounds(tz, date)` and `business_week_bounds` (Monday start). Every module uses only these.
- `SLOT_STEP_MINUTES = 30` lives in bookings.
- Every booking `start_at` is aligned to that step.
- Cap keys use the Business-local date.

## H17 — Technician deactivation vs capacity (Medium)

**Pair.**
- **Accounts story.** The Owner turns off their own Technician role (FR-7). Accounts updates the role set.
- **Bookings.** It has 3 confirmed bookings tomorrow for that Technician. Capacity drops below the confirmed count, the free-slot math goes negative, and those bookings now belong to a non-Technician.

**Proposed rule.** Removing the Technician role or a member calls `bookings.check_technician_removable(membership_id)` under the AD-9' lock. If there are future `requested` or `confirmed` bookings, it refuses with `TechnicianHasBookings` until they are reassigned.

## H18 — Alembic heads (Medium)

**Pair.** Two module stories, merged the same day, each create a migration with `down_revision = <same head>`. Then `alembic upgrade head` fails in the pipeline.

**Proposed rule.** CI asserts `alembic heads` returns exactly one head. Every migration file name starts with the owning module.

---

## Smaller notes

- **AD-12, cap counting.** Does the counter increase per AI call or per Customer reply? The AD-8 retry doubles calls. Rule: count per AI call, and check before the retry too.
- **AD-7 / FR-22 timeout.** No number is given. Rule: AI timeout = 8 s, so the NFR-3 target of 10 s is still reachable.
- **AD-14 error codes.** No registry exists. `SlotUnavailable`, `BookingStateConflict`, and `TechnicianHasBookings` need stable `code` strings that the frontend can switch on. Rule: one `ErrorCode` enum in `core`.
- **FR-11's 404 rule.** AD-3 should state: "A record outside the tenant is invisible, so it returns 404, never 403." Otherwise the role-check code (403) and the scoping code race to answer first.

## Verdict

The module map and the dependency direction are good foundations. But AD-9 contradicts AD-2 (H1). No AD owns transaction boundaries (H2). Tenant context has no defined path for login, invites, cron, or seeding (H3). Polling, agent concurrency, and booking transitions each allow lost or duplicated writes (H4–H6). Add AD-15 (Unit of Work), AD-16 (Actor), and AD-17 (customer data), and tighten AD-3, AD-4, AD-7, AD-8, AD-9, AD-10, and AD-13 as above, before the first P1 story is planned.
