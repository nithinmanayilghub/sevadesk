---
title: "PRD: SevaDesk"
status: final
created: 2026-11-01
updated: 2026-11-01
sources:
  - _bmad-output/planning-artifacts/briefs/brief-seva-desk-2026-11-01/brief.md
  - docs/project-seed.md
---

# PRD: SevaDesk

## 0. Document Purpose

This PRD is for the solo builder and for the next BMAD steps: UX, architecture, and epics and stories. It turns the final product brief into testable requirements. It gives full detail only for the MVP (P0 + P1). P2–P6 appear as a short roadmap. Each later phase gets a PRD update before its work starts.

How to read it:
- §3 Glossary fixes the words. All other sections use them exactly.
- Requirements have stable IDs: FR (functional requirement), NFR (non-functional requirement), UJ (user journey), and SM (success metric).
- §10 lists the assumptions that the builder accepted on 2026-11-01. Revisit them if facts change.
- The tech stack, engineering rules, budget, and Definition of Done are in `docs/project-seed.md`. This PRD does not copy them. `addendum.md` holds the technical notes.

## 1. Vision

SevaDesk is an AI front desk for small Indian home-service businesses: AC repair, plumbers, electricians, and appliance repair. When the owner is on a job, an AI agent answers the customer, collects the job details, and requests a booking. The owner or staff approve it with one tap. The owner sees all conversations, the schedule, and the day's work in one place.

The MVP proves the core loop: **a customer message becomes an approved job on the calendar**. It works for a solo owner and for a small team. It runs on free tiers. The builder can deploy it to AWS with one command for interviews.

## 2. Target User

### 2.1 Jobs To Be Done

- **Owner:** "When I am on a job, make sure no customer leaves without an answer. Show me what came in, and let me approve it fast."
- **Staff:** "Give me one inbox and one calendar, so I can confirm jobs and step in when the AI cannot help."
- **Technician:** "Tell me which jobs are mine today."
- **Customer:** "Get a fast reply in my language and a clear answer: is someone coming, and when?"
- **Builder:** "Ship a production-grade system that I can explain and demo in an interview."

### 2.2 Non-Users (v1)

- Large service companies with dispatch teams and many branches.
- Marketplaces that sell leads to many businesses (like Urban Company).
- Customers who want to pay online (there are no payments in the MVP).

### 2.3 Key User Journeys

- **UJ-1. Ravi gets a booking request while he is on a ladder.**
  Ravi runs a two-person AC repair business in Bengaluru. He is on a job when a customer opens his SevaDesk chat link from his Google profile and writes in Hindi: "AC is not cooling." The Agent replies in Hindi. It asks for the name, phone, address, and AC type. It offers two free Slots for tomorrow. The customer picks one. The Agent says: "Your request is sent. The business will confirm soon." Ravi sees the Booking Request on his phone dashboard after the job and taps **Confirm**. The customer's chat page now shows "Confirmed: tomorrow 10:00–11:00."
  Before it offers Slots, the Agent shows the Price: "AC not cooling — inspection and gas check: from ₹499. Parts extra, quoted before work starts." The customer agrees.
  **Edge case:** the customer asks for a discount. The Agent says it cannot change Prices and offers a Handoff. It never invents a number.

- **UJ-2. Anita takes over a confused conversation.**
  Anita is the office staff for a plumbing business. A customer writes about three different problems and asks to "talk to a person". The Agent hands off the Conversation. It is marked **Needs Human** at the top of the Inbox. Anita opens it, reads the history, and replies herself. The Agent stays silent in that Conversation until Anita hands it back.

- **UJ-3. Suresh, a solo electrician, sets up his business in 10 minutes.**
  Suresh signs up. This creates his Business and makes him the Owner. He also holds the Technician role. He adds three Services (fan repair, wiring check, inverter install), each with a duration. He sets his Working Hours to Mon–Sat, 9:00–18:00. He copies his chat link to his WhatsApp status. The setup never asks him to "assign a technician", because he is the only one.

- **UJ-4. The builder demos SevaDesk on AWS for an interview.**
  The day before an interview, the builder runs one deploy command. About 20 minutes later, an AWS URL works with seeded demo Businesses. After the interview, one destroy command removes every AWS resource. The AWS bill for the day is a few dollars.

## 3. Glossary

- **Business** — One home-service company that uses SevaDesk. It is the tenant: all its data is isolated from other Businesses. It has 1 or more Users.
- **User** — A person who logs in to SevaDesk. A User belongs to exactly one Business in the MVP. A User has 1 or more Roles.
- **Role** — Owner, Staff, or Technician. One User can hold several Roles (a solo owner holds all three).
- **Customer** — A person who contacts a Business. A Customer does not log in. A Customer is identified by phone number within one Business.
- **Chat Page** — The public web page of a Business where Customers chat. It has a shareable link.
- **Channel** — The route a message travels. In the MVP, the only Channel is webchat (the Chat Page). WhatsApp and SMS come in P3.
- **Conversation** — All Messages between one Customer and one Business on one Channel.
- **Message** — One piece of text in a Conversation. It comes from the Customer, the Agent, or a User.
- **Agent** — The AI that replies to Customers on behalf of a Business.
- **Handoff** — The state where a User, not the Agent, answers a Conversation.
- **Inbox** — The list of all Conversations of a Business, for Owner and Staff.
- **Service** — A job type that a Business offers, with a name, a duration, and a Price.
- **Price** — The "starting from" amount in rupees that a Customer sees before booking a Service ("from ₹499, parts extra"). The final amount is quoted on site. Every active Service has one.
- **Working Hours** — The weekly hours when a Business accepts jobs.
- **Slot** — A start time and an end time inside Working Hours, when a Technician is free for a Service.
- **Booking** — A planned job: a Customer, a Service, an address, a Slot, and a status. Statuses: **requested**, **confirmed**, **declined**, **expired**, **cancelled**, **completed**.
- **Booking Request** — A Booking with status requested. It waits for a User to approve it.
- **Dashboard** — The Owner's home screen: today's work and the items that need action.
- **Golden Dataset** — A fixed set of example Customer conversations (English and Hindi) with the expected results. Evals use it.
- **Scenario Card** — A short description of one test situation (Service, language, Customer behaviour, expected result). An LLM turns it into a draft Golden Dataset conversation.
- **Eval** — An automatic test that checks how good the Agent's behavior is against the Golden Dataset.

## 4. Features

### 4.1 Walking Skeleton (P0)

**Description:** The smallest system that runs end to end on every environment: a frontend page, a backend API, and a database, with the full delivery pipeline. It has no product features. It proves the plumbing. Realizes UJ-4.

#### FR-1: End-to-end hello path
A visitor can open the frontend and see a value that the backend read from the database.
- The page shows the value and the backend version.
- The same Docker images run locally, on the demo environment, and on AWS staging. Only environment variables change.

#### FR-2: Health checks
An operator can check the health of the backend and the worker.
- `GET /health` returns 200 when the database and Redis are reachable, and 503 when one is not.

#### FR-3: Delivery pipeline
Each pull request runs lint → tests → evals (smoke set) → build. A merge to main also deploys to the demo environment.
- A failing step blocks the merge.
- Database migrations run in the pipeline before the new version starts.

#### FR-4: Observability baseline
An operator can follow one request through the frontend, backend, worker, and database in a single trace.
- Every log line is structured JSON with a request ID and a trace ID.
- Traces, logs, and metrics reach the free observability tier.

#### FR-5: Eval harness
The builder can run Evals locally and in CI against the Golden Dataset, and get a score per check.
- CI fails when the score drops below the stored baseline.
- In P0, the harness runs one placeholder Eval, so the pipeline is proven before the Agent exists.

#### FR-6: One-command AWS deploy and destroy
The builder can create the full AWS staging environment with one command, and remove all of it with one command. Realizes UJ-4.
- After deploy, a public AWS URL serves the same app as the demo environment.
- After destroy, no billable AWS resource remains (checked by a script or the console).
- An AWS budget alert fires at $5.

### 4.2 Accounts, Businesses, and Roles (P1)

**Description:** An Owner signs up and creates a Business. The Owner invites Staff and Technicians. Each User sees only the data of their own Business. Realizes UJ-3.

#### FR-7: Owner sign-up
A new person can sign up with email and password. This creates a Business and a User with the Owner and Technician Roles.
- The Technician Role is on by default, so a solo owner can take jobs. The Owner can turn it off.

#### FR-8: Log in and log out
A User can log in and log out. Sessions expire after inactivity.
- Wrong passwords are rate-limited per account and per IP address.

#### FR-9: Invite team members
An Owner can invite a person by email, with one or more Roles. The person accepts through an invite link and sets a password.
- In the MVP, the Owner copies and shares the invite link. SevaDesk sends no emails.
- An invite link works once and expires after 7 days.

#### FR-10: Role-based access
The system allows each action only for the Roles that may do it:

| Action | Owner | Staff | Technician |
|---|---|---|---|
| Manage Services, Working Hours, and team | ✓ | | |
| Use the Inbox and approve Bookings | ✓ | ✓ | |
| See own assigned Bookings | ✓ | ✓ | ✓ |
| See the Dashboard | ✓ | ✓ (without team settings) | |

- A request for a forbidden action returns 403 and changes nothing.

#### FR-11: Tenant isolation
A User can read and change only the data of their own Business.
- Every query is scoped to the User's Business. A request for another Business's record returns 404 (not 403, so the record's existence does not leak).
- Automated tests try cross-Business access for every API endpoint. All of them must fail.

### 4.3 Business Setup (P1)

**Description:** The Owner tells SevaDesk what the Business sells and when it works. The Agent may offer only these Services and Slots. Realizes UJ-3.

#### FR-12: Manage Services
An Owner can add, edit, and deactivate Services. Each Service has a name, a duration (30–480 minutes), and a Price (required).
- A Service cannot be saved or activated without a Price.
- The Agent states a Price only from the Service data, always as "from ₹X", and says that the final amount is quoted on site.

#### FR-13: Working Hours
An Owner can set weekly Working Hours (per day: closed, or a start and an end time) and mark single days as closed (holidays).

#### FR-14: Chat Page link
Each Business has one Chat Page with a stable, shareable link. The Owner can copy it.
- The Chat Page shows the Business name and the DPDP consent notice (see NFR-8).

### 4.4 Customer Chat and AI Agent (P1)

**Description:** A Customer opens the Chat Page and talks to the Agent. The Agent collects the details, offers real free Slots, and creates a Booking Request. It replies in the Customer's language (English or Hindi). It never invents Prices, Slots, or facts. When it cannot help, it hands off to a human. Realizes UJ-1, UJ-2.

#### FR-15: Start and continue a Conversation
A Customer can open the Chat Page, send Messages, and return later to the same Conversation from the same browser.
- The Customer needs no account.
- The page works on a slow mobile connection (see NFR-6).

#### FR-16: Collect booking details
The Agent collects the name, phone number, address, the problem description, and the matching Service, before it offers Slots.
- It asks only for the missing details. It does not ask again for details the Customer already gave.
- It checks that the phone number is a valid Indian mobile number.

#### FR-16a: Show the Price before booking
Before it offers Slots, the Agent shows the Price of the chosen Service, and the Customer confirms that they accept it.
- No Booking Request is created unless the Customer accepted the Price in that Conversation.
- The Booking Request stores the Price that the Customer saw, so a later Price change does not change it.
- The Chat Page lists all active Services with their Prices above the chat, so a Customer sees them before the first Message.

#### FR-17: Offer real Slots only
The Agent offers only Slots that the system calculates as free, for the chosen Service.
- A Slot is free when it is inside Working Hours and the number of confirmed or requested Bookings that overlap it is less than the number of active Technicians.
- If no Slot is free in the next 7 days, the Agent says so and offers a Handoff.

#### FR-18: Create a Booking Request
When the Customer picks a Slot, the system creates a Booking Request and holds the Slot.
- If the Slot is no longer free (a race with another Customer), the Agent apologizes and offers new Slots.
- The Agent tells the Customer that the Business will confirm, and that the status shows on the Chat Page.

#### FR-18a: Booking Request expiry
A Booking Request that no User confirms or declines within 12 hours gets the status expired, and its Slot becomes free again.
- The Customer's Chat Page shows: "Not confirmed. Please contact the business." The Customer can start a new request in the same chat.
- The expired Booking Request stays visible to Users in the Inbox for follow-up.
- The Dashboard shows the time left on each waiting Booking Request.

#### FR-19: Language match
The Agent replies in the language of the Customer's last Message: English or Hindi (Devanagari or Roman script).
- Other languages get a short English reply and a Handoff.

#### FR-20: No invented facts
The Agent never states a Price, Slot, opening time, or policy that is not in the Business data.
- For unknown questions, it says that the Business will answer, and it offers a Handoff.

#### FR-21: Handoff to a human
The Agent hands off a Conversation when the Customer asks for a person, when the Agent fails to understand twice in a row, or when the topic is out of scope (complaints, refunds). Realizes UJ-2.
- During a Handoff, the Agent sends no Messages in that Conversation.
- A User can end the Handoff and give the Conversation back to the Agent.

#### FR-22: Agent failure fallback
If the AI service fails or times out, the Customer gets a fixed message ("We got your message. The team will reply soon.") and the Conversation goes to Handoff.

### 4.5 Inbox (P1)

**Description:** Owner and Staff see all Conversations in one list, read them, and reply. Realizes UJ-2.

#### FR-23: Inbox list
A User with Inbox access sees Conversations, newest activity first. Conversations in Handoff come first.
- Each row shows the Customer name or phone, the last Message, the time, and the state (Agent / Needs Human / Booking Request).

#### FR-24: Read and reply
A User can open a Conversation, read the full history, and reply. The reply appears on the Customer's Chat Page.
- Replying starts a Handoff automatically.
- New Messages appear without a page reload within 5 seconds.

### 4.6 Bookings and Calendar (P1)

**Description:** Users approve Booking Requests and see the schedule. Realizes UJ-1, UJ-3.

#### FR-25: Approve, change, or decline
A User with Inbox access can confirm a Booking Request, change its Slot or Technician and then confirm it, or decline it with a reason. A declined Booking Request frees its Slot, and the Customer's Chat Page shows that it was declined.
- Confirming needs a Technician who is free in that Slot. If the Business has only one active Technician, the system assigns that Technician automatically. (This is why a solo owner never sees an "assign" step.)
- The Customer's Chat Page shows the new status and time within 5 seconds. In the MVP, the Chat Page is the only place where the Customer sees the confirmation; WhatsApp updates come in P3.

#### FR-26: Calendar
A User sees a day view and a week view of the Bookings. A Technician sees only their own Bookings.
- The views work on a 360-pixel-wide phone screen.

#### FR-27: Create, cancel, and complete Bookings by hand
A User with Inbox access can create a Booking for a phone-in Customer, cancel a Booking, and mark a Booking as completed.

### 4.7 Owner Dashboard (P1)

#### FR-28: Today at a glance
The Owner sees: today's confirmed Bookings, waiting Booking Requests, Conversations in Handoff, and the count of new Conversations and confirmed Bookings this week.
- Each item links to its detail screen.
- Revenue is not in the MVP, because there are no invoices or payments before P2/P3.

### 4.8 Demo Mode (P1)

#### FR-29: Seeded demo Businesses
The demo and AWS environments start with at least two seeded demo Businesses (one solo, one team) with fake data and demo logins. Realizes UJ-4.
- A command resets the demo data.
- Demo data contains no real personal data.

### 4.9 Golden Dataset (P1)

**Description:** The builder creates the Golden Dataset with an LLM and checks every case by hand. No public dataset fits SevaDesk, and scraping is not allowed (personal data, site terms). See addendum "Golden Dataset".

#### FR-30: Build the Golden Dataset
The builder can turn Scenario Cards into draft conversations with an LLM, review them, and save the approved cases in the repo.
- Each case stores: the conversation, the language, the expected details, the expected Service and Price shown, and the expected result (Booking Request, Handoff, or no booking).
- A case enters the dataset only after the builder marks it as reviewed.
- The first version has at least 30 cases: about half English and half Hindi or Hinglish. It covers happy paths, missing details, Price questions and discount requests, no free Slot, a request for a person, and an unsupported language.
- Cases use the seeded demo Businesses (FR-29) and only fake personal data.

### 4.10 Portfolio Landing Page (P1)

**Description:** A public page at the root URL that explains SevaDesk to recruiters and visitors and sends them into the demo. It carries the brand's glass look; the app screens do not. Realizes UJ-4. Visual and behavior specs: UX `DESIGN.md` and `EXPERIENCE.md`.

#### FR-31: Landing page
A visitor can learn what SevaDesk does and open the demo from one page.
- It links to a demo Business's Chat Page, a demo Owner log-in, and the GitHub repository.
- It shows how SevaDesk is built (tests, Evals, tracing, AWS deploy). It shows no pricing, because SevaDesk has no paid plans.
- It loads under 1 MB on mobile, and its animations stop when the visitor's device asks for reduced motion.

## 5. Cross-Cutting Non-Functional Requirements

- **NFR-1 Tenant isolation.** No API endpoint or background job reads or writes across Businesses. FR-11's tests run in CI on every pull request.
- **NFR-2 Agent quality gates.** Evals run on the Golden Dataset (English and Hindi). Code-based checks (detail extraction, correct Booking, no invented Prices or Slots, language match) run first. An LLM-as-judge checks tone. A score drop blocks the merge.
- **NFR-3 Response time.** The Agent's reply reaches the Chat Page within 10 seconds in 95% of cases on the demo environment. Other API calls answer within 500 ms in 95% of cases.
- **NFR-4 Observability.** Every Agent call records the prompt version, model, tokens, cost, and latency in the LLM tracing tool, linked to the request trace. Errors are tracked, and basic dashboards and alerts exist for errors and Agent cost.
- **NFR-5 Security.** Input validation on every endpoint. Rate limits on log-in and on the public Chat Page (per IP and per Conversation). No secrets in code. Passwords are stored only as strong hashes.
- **NFR-6 Mobile-first and low bandwidth.** All screens work from 360 px width. The first load of the Chat Page is under 200 KB compressed.
- **NFR-7 Cost.** Total running cost stays under $10 a month. Each Business has a daily cap on Agent replies. After the cap, the Agent hands off. Development uses the Groq free tier with fake data only. Claude runs CI Evals and the demo. Monthly spending limits are set in the AWS and Anthropic consoles.
- **NFR-8 Personal data (DPDP Act).** The Chat Page shows a short notice before the first Message: what data is collected, why, and that the Business can delete it. An Owner can delete a Customer and all their Conversations and Bookings. Logs and traces do not store phone numbers or addresses in plain text.
- **NFR-9 Swappable providers.** The AI provider, Channels, and payment providers sit behind adapters. Adding a provider needs no change in the booking logic.
- **NFR-10 Testing.** Every story meets the Definition of Done in `docs/project-seed.md`. Every bug fix adds a regression test. Key flows (UJ-1, UJ-2, UJ-3) have Playwright E2E tests. CI enforces a minimum code coverage.

## 6. Non-Goals (Explicit)

- SevaDesk is not a marketplace. It does not find customers for businesses.
- No customer accounts or customer apps.
- No route planning, GPS tracking, or inventory management.
- No real money flows before P3.
- No users who belong to several Businesses in the MVP.
- No always-on AWS. AWS runs only for tests and interviews.

## 7. MVP Scope

### 7.1 In Scope (P0 + P1)

FR-1 to FR-31 (including FR-16a and FR-18a) and NFR-1 to NFR-10.

### 7.2 Roadmap After the MVP (detail comes in a PRD update before each phase)

- **P2 Field ops:** technician mobile job view and job status updates, estimates, GST invoices, mock payment link.
- **P3 Channels and payments:** WhatsApp Business API, SMS, Razorpay UPI. Customers get booking updates on WhatsApp.
- **P4 Growth:** Google review requests, AMC reminders, campaigns.
- **P5 Intelligence:** Hindi, Kannada, and Tamil in the app screens and the Agent; analytics; an "AI business manager" that answers questions about revenue.
- **P6 Voice AI calls.**

## 8. Success Metrics

**Primary**
- **SM-1 Portfolio-ready:** P0 + P1 deploy to AWS with one command and pass the E2E tests there. Target: yes, before the first interview demo. Validates FR-6, FR-29.
- **SM-2 Correct bookings:** in at least 90% of Golden Dataset cases, the Agent creates a Booking Request with the correct details and Service. Validates FR-16, FR-17, FR-18.
- **SM-3 No invented facts, Price always shown:** 0 cases of an invented Price or Slot, and 0 Booking Requests without an accepted Price, in the Golden Dataset. Validates FR-12, FR-16a, FR-17, FR-20.
- **SM-4 Isolation:** 0 cross-Business access in the isolation tests. Validates FR-11, NFR-1.

**Secondary**
- **SM-5 Language match:** at least 95% of Agent replies match the Customer's language in the Golden Dataset. Validates FR-19.
- **SM-6 Cost:** monthly running cost under $10, checked each month. Validates NFR-7.
- **SM-7 Understanding:** the builder passes the Understanding Gate for every CORE story.
- **SM-8 Pilot (after P1 or P3):** one real Business uses SevaDesk for 2 weeks and says it saved at least one lost Customer.

**Counter-metrics (do not optimize)**
- **SM-C1 Booking volume:** do not push the Agent to create more Booking Requests. A request with missing or wrong details costs the Business a wasted trip. Counterbalances SM-2.
- **SM-C2 Reply speed alone:** do not cut the checks for invented facts to make replies faster. Counterbalances NFR-3.
- **SM-C3 Feature count:** do not start P2+ features before P1 is portfolio-ready and understood. Counterbalances progress through the roadmap.

## 9. Open Questions

1. Which Claude model does the demo Agent use, and what is the cost per Conversation? The architecture step measures this.

## 10. Accepted Assumptions (2026-11-01)

- §4.2 FR-9 — No email service in the MVP. Invite links are copied by hand.
- §4.4 FR-15 — A browser token links a Customer to a Conversation. A new device starts a new Conversation.
- §4.4 FR-19 — Languages other than English or Hindi get an English reply and a Handoff.
- §4.5 FR-24 — Polling every few seconds is acceptable for live updates in the MVP.
- §5 NFR-6 — The Chat Page first load is under 200 KB.
- §5 NFR-7 — The daily Agent cap is 200 replies per Business on the demo.
- §8 SM-2, SM-5 — The target values 90% and 95%.
- §8 SM-8 — The pilot is 2 weeks long and asks one question.
