---
name: SevaDesk
status: final
created: 2026-11-01
updated: 2026-11-01
sources:
  - _bmad-output/planning-artifacts/prds/prd-seva-desk-2026-11-01/prd.md
  - _bmad-output/planning-artifacts/briefs/brief-seva-desk-2026-11-01/brief.md
  - docs/project-seed.md
---

# SevaDesk — Experience Spine

`DESIGN.md` owns how SevaDesk looks. This file owns how it works. Terms (Business, Booking Request, Slot, Handoff, ...) follow the PRD Glossary exactly. FR/UJ IDs refer to the PRD. When a mock or wireframe disagrees with this file or `DESIGN.md`, the two spines win.

**Mock-ups** (static HTML, open in a browser): [Chat Page](mockups/key-chat-page.html) · [Dashboard + Booking Request card](mockups/key-dashboard.html) · [Landing page hero](mockups/key-landing-hero.html). All other surfaces are built from this file and `DESIGN.md` alone (shadcn defaults + the tokens): Inbox, Conversation, Calendar, Booking detail, Customer detail, Settings, Sign up, Log in, and Accept invite.

## Foundation

- **Form factor:** one responsive web app, mobile-first from 360px (NFR-6). No native apps.
- **UI system:** shadcn/ui on Next.js + Tailwind. This file specifies only the behavior that differs from shadcn's defaults.
- **Themes:** light and dark. The default follows the device setting. A User can override it in Settings. The Chat Page and the landing page follow the device setting only.
- **Two worlds:** public pages (landing page, Chat Page) with no log-in, and the app (Dashboard, Inbox, Calendar, Settings) behind log-in.

## Information Architecture

| Surface | URL (indicative) | Who | Reached from | Purpose | FR |
|---|---|---|---|---|---|
| Landing page | `/` | Visitor | Direct link, GitHub README | Explain SevaDesk, open the demo | FR-31 |
| Chat Page | `/c/{business}` | Customer | Link shared by the Business | Services and Prices, chat with the Agent, Booking status | FR-14–22, FR-16a, FR-18a |
| Sign up | `/signup` | New Owner | Landing page, log-in page | Create a Business | FR-7 |
| Log in | `/login` | User | Landing page ("Demo log-in"), direct | Start a session | FR-8 |
| Accept invite | `/invite/{token}` | Invited person | Invite link | Set a password, join the Business | FR-9 |
| Dashboard | `/app` | Owner, Staff | Log-in (default for Owner/Staff) | Today at a glance, items needing action | FR-28, FR-18a |
| Inbox | `/app/inbox` | Owner, Staff | Nav, Dashboard items | List of Conversations | FR-23 |
| Conversation | `/app/inbox/{id}` | Owner, Staff | Inbox row | History, reply, Handoff, Booking Request card | FR-21, FR-24, FR-25 |
| Calendar | `/app/calendar` | All Roles | Nav (default for Technician-only Users) | Day and week views; Technicians see only their own jobs | FR-26, FR-27 |
| Booking detail | sheet over Calendar or Conversation | Owner, Staff (Technician read-only) | Calendar block, Booking Request card | Confirm, change, decline, cancel, complete | FR-25, FR-27 |
| Customer detail | sheet from Conversation | Owner | Conversation header | Customer data; delete Customer (DPDP) | NFR-8 |
| Settings → Services | `/app/settings/services` | Owner | Nav "More" | Services with duration and Price | FR-12 |
| Settings → Working Hours | `/app/settings/hours` | Owner | Nav "More" | Weekly hours, closed days | FR-13 |
| Settings → Team | `/app/settings/team` | Owner | Nav "More" | Invite, Roles, deactivate | FR-9, FR-10 |
| Settings → Chat link | `/app/settings/chat-link` | Owner | Nav "More", Dashboard (first run) | Copy and share the Chat Page link | FR-14 |
| Settings → Appearance | `/app/settings/appearance` | All | Nav "More" | Theme: system / light / dark | — |

**Navigation:**
- **Mobile:** a bottom tab bar. Owner and Staff see Dashboard · Inbox · Calendar · More. Technician-only Users see Calendar · More. The Inbox tab shows a red count of Needs Human Conversations.
- **Desktop (≥1024px):** a left sidebar with the same items. The Inbox uses a two-pane layout: the list on the left and the Conversation on the right.
- **Solo Owner (one active Technician):** the Team page says "Just you for now", and no screen asks the User to assign a Technician (FR-25).

## Voice and Tone

- **App microcopy:** short, plain, action-first. "Confirm", not "Approve Booking Request". Say what happened and what is next.
- **Agent voice:** polite, warm, and brief, like a good receptionist. It mirrors the Customer's language and script (English, Hindi in Devanagari, or Hinglish in Roman script). It never promises what the data does not say (FR-20).
- **Prices:** always "from ₹499". Always followed by "Final price after inspection. Parts extra." (FR-12)
- **Time and date:** 12-hour time with "am/pm" ("10:00 am – 11:00 am"). Dates read "Tue, 4 Nov". All times are in the Business's timezone (IST in the MVP).

| Moment | Copy |
|---|---|
| Booking Request sent (Customer) | "Request sent ✓ {Business} will confirm soon. You'll see the update here." |
| Confirmed (Customer) | "Confirmed: {Service}, {date}, {time}." |
| Expired (Customer) | "Not confirmed. Please contact the business, or send a new request below." |
| Declined (Customer) | "{Business} can't take this request. Reason: {reason}." |
| AI failure (Customer) | "We got your message. The team will reply soon." (FR-22) |
| Handoff started (Customer) | "Connecting you to the team. Someone will reply here." |
| Empty Inbox (User) | "No conversations yet. Share your chat link to get your first customer." + Copy link |
| Slot gone (Agent) | "Sorry, that time was just taken. Here are other times:" |

## Component Patterns

- **Chat Page header and Services list:** the Business name, then the list of active Services with "from ₹X" and the duration (FR-16a). On mobile, the list collapses after the first message, with a "Services & prices" button to reopen it. The DPDP notice sits above the composer until the first message (NFR-8).
- **Quick-reply chips:** the Agent attaches tappable chips to questions with fixed answers: Service choice, Price acceptance ("Yes, book it" / "No"), and Slot choice. Typing a reply always works too. Chips stay on the last Agent Message only.
- **Slot chips:** up to 4 Slots per Agent Message, for example "Tomorrow 10:00 am". The last chip is "Other times".
- **Booking Request card** (inside the Conversation and on the Dashboard): Customer, Service, Price shown, Slot, address, and an amber countdown ("Expires in 9 h"). Actions: **Confirm** (`button-action`), Change, Decline. Change opens a sheet with a Slot picker, and a Technician picker if there is more than one Technician. Decline asks for a reason (preset options + free text).
- **Inbox row:** a status badge (Agent / Needs Human / Booking Request), the Customer name or phone, the last Message preview (1 line), and the time. Needs Human rows are pinned at the top.
- **Handoff bar** (Conversation): during a Handoff: "You are replying. The Agent is paused." + "Give back to Agent". When the Agent is active: "Agent is replying" + "Take over".
- **Composer:** a multi-line input with a Send button. Sending a User reply starts a Handoff (FR-24). The User sees this once as a hint: "Your reply pauses the Agent."
- **Calendar:** the day view is the default on mobile. The week view is the default on desktop. Booking blocks are colored by status badge rules. Requested Bookings show with a dashed border, because they hold the Slot but are not confirmed.

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| First load | App screens | shadcn `Skeleton` rows that match the layout |
| First run (no Services) | Dashboard | A checklist: Add Services → Set Working Hours → Copy chat link. The Chat Page shows "Not taking requests yet" until at least one Service and Working Hours exist |
| Agent typing | Chat Page | A three-dot indicator after 1 s. After 10 s: "Still working…" (NFR-3) |
| Agent failed | Chat Page | Fixed fallback copy (Voice table). The Conversation goes to Needs Human (FR-22) |
| Daily Agent cap reached | Chat Page | The same as a Handoff. The Customer is not told about the cap (NFR-7) |
| No free Slot in 7 days | Chat Page | The Agent says so and offers a Handoff (FR-17) |
| Booking Request waiting | Dashboard, Conversation | An amber badge + countdown |
| Booking Request expired | Chat Page, Inbox | Expired copy for the Customer. Zinc badge "Expired" in the Inbox, kept for follow-up (FR-18a) |
| Offline / send failed | Chat Page, Composer | The Message shows "Not sent · Retry". Nothing is lost while the page stays open |
| Stale data | Inbox, Dashboard | Polling every 5 s (FR-24). If polling fails 3 times: a banner "Reconnecting…" |
| Unsupported language | Chat Page | A short English reply + Handoff (FR-19) |
| Forbidden action | App | The action is hidden for that Role. A direct URL shows "You don't have access to this page." (FR-10) |
| Delete Customer | Customer detail | A confirm dialog that names what is deleted (Conversations, Bookings) and says it cannot be undone (NFR-8) |

## Interaction Primitives

- Tap targets are at least 44px. There is no hover-only information. Everything works by touch.
- **Enter** sends on desktop. **Shift+Enter** makes a new line. On mobile, the Send button sends.
- Live updates use polling every 5 s while the tab is visible, and pause while it is hidden (FR-24, FR-25).
- Lists use simple pagination ("Load more"), not infinite scroll, so slow networks stay usable.
- **Motion:** in the app, only 150–200 ms color and opacity transitions. On the landing page: the user's fade-in-up (0.8 s, `cubic-bezier(0.16, 1, 0.3, 1)`) and 105% hover scale. Both turn off with `prefers-reduced-motion`.
- **Theme toggle:** system / light / dark, saved per User.

## Accessibility Floor

- WCAG 2.2 AA. The color pairs in `DESIGN.md` meet 4.5:1 for text.
- Status is never shown by color alone. Each badge has text and an icon.
- New chat Messages are announced through an `aria-live="polite"` region. Hindi Messages carry `lang="hi"`, so screen readers use the correct voice.
- Every control has a visible focus ring (shadcn `ring`) and a text label. Icon-only buttons have `aria-label`.
- Forms show errors next to the field in text, and move focus to the first error.
- The Agent's chips are real buttons, reachable by keyboard.

## Responsive & Platform

- Breakpoints: 360px (minimum), 768px (tablet: wider cards), 1024px (sidebar and two-pane Inbox).
- **Chat Page budget:** under 200 KB compressed on first load (NFR-6). No images, no glass, and no web font for Latin text beyond an Inter subset. The Devanagari font loads only when Hindi appears.
- **Landing page budget:** under 1 MB (FR-31). No photos: the hero uses CSS or SVG gradients plus the grain SVG. Glass `backdrop-filter` is used only on the landing page.
- Targets: recent Chrome on Android (the main one), Safari on iOS, and desktop Chrome, Edge, and Firefox.

## Inspiration & Anti-patterns

**From the user's design system (landing page):** a floating glass pill navbar; a 92vh dark hero with a giant blurred background word ("SEVA" at 3% opacity) and glass stat cards; a two-column feature grid with a sticky header; a dark "How it works" block with numbered steps (01, 02, 03) and a tilted Chat Page mock-up; a three-card bento. The bento shows **"How it's built"** (Tests · Evals · Tracing/AWS), not pricing, because SevaDesk has no paid plans (FR-31).

**Anti-patterns:**
- Glass, blur, or grain on app screens.
- Hiding Prices until late in the chat (FR-16a).
- Making the Customer create an account.
- Chat bots that pretend to be human. A User's reply is labeled with the User's name, and the Agent is labeled "SevaDesk assistant".

## Key Flows

### Flow 1 — UJ-1: Ravi gets a booking request while he is on a ladder

Visual reference: [Chat Page](mockups/key-chat-page.html) (steps 1–4), [Dashboard](mockups/key-dashboard.html) (steps 5–6).

1. A Customer opens Ravi's Chat Page from his Google profile and sees his Services with "from ₹" Prices.
2. The Customer writes in Hindi: "AC ठंडा नहीं कर रहा". The Agent replies in Hindi and asks for the missing details one at a time.
3. The Agent shows "AC gas check — from ₹499. Final price after inspection." with chips "हाँ, बुक करें" / "नहीं". The Customer taps yes.
4. The Agent offers 3 Slot chips for tomorrow. The Customer picks 10:00 am. The Chat Page shows "Request sent ✓".
5. After his job, Ravi opens the Dashboard. A Booking Request card shows an amber "Expires in 11 h".
6. **Climax:** Ravi taps **Confirm**. He is the only Technician, so there is no assign step. The Customer's Chat Page changes to "Confirmed: AC gas check, Wed 5 Nov, 10:00 am" within 5 seconds.

### Flow 2 — UJ-2: Anita takes over a confused conversation

1. A Customer describes three problems and writes "talk to a person". The Agent replies "Connecting you to the team" and stops.
2. Anita's Inbox tab shows a red "1". The Conversation is pinned at the top with a red Needs Human badge.
3. She opens it, reads the history, and replies. The Handoff bar says "You are replying. The Agent is paused."
4. **Climax:** she creates a Booking by hand from the Conversation (FR-27), and the Customer sees her named reply and the confirmed time.
5. She taps "Give back to Agent" for later questions.

### Flow 3 — UJ-3: Suresh, a solo electrician, sets up his business

1. Suresh signs up. The Dashboard opens with the first-run checklist.
2. He adds three Services, each with a duration and a "from ₹" Price. The Price field is required.
3. He sets Mon–Sat, 9:00 am – 6:00 pm.
4. **Climax:** the checklist turns emerald, and "Copy chat link" appears. He pastes it into his WhatsApp status.
5. The Team page says "Just you for now", and he is never asked to assign a Technician.

### Flow 4 — UJ-4: The builder demos SevaDesk on AWS for an interview

Visual reference: [Landing page hero](mockups/key-landing-hero.html).

1. The interviewer opens the AWS URL. The landing page shows the hero, "How it works", and "How it's built".
2. They tap "Try the chat" and book a Service on a demo Business's Chat Page.
3. They tap "Demo log-in" in a second tab and see the Booking Request on the Dashboard.
4. **Climax:** they confirm it, and the first tab updates to "Confirmed" within 5 seconds: the full loop, live.
