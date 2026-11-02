---
title: "Addendum: SevaDesk PRD"
created: 2026-11-01
---

# Addendum: SevaDesk PRD

Technical notes for the architecture step. The PRD says *what*. These notes say *how*, where an early decision was made. The stack, budget tracks, and engineering rules are in `docs/project-seed.md`.

## AI providers

- Development: Groq API free tier (open-weight models, OpenAI-compatible API). Fake data only.
- CI Evals and demo: Claude API (a cheap model such as Haiku by default; a larger model only where quality needs it).
- Both sit behind one AI service adapter (NFR-9). Prompts are versioned in code. Each Eval run records the prompt version.
- Rejected: Ollama on the builder's laptop (8 GB RAM, no GPU; it cannot run beside the Docker stack).

## Hosting

- Demo: frontend, backend, worker, and Valkey (Redis) together on Oracle Cloud Always Free (docker-compose, one web address); Postgres on Neon free tier. Superseded the earlier Vercel / Supabase / Upstash plan (see architecture spine, 2026-11-01).
- AWS staging (Terraform): on demand only. Turn it on for interviews, then destroy it (FR-6).

## Slot calculation (FR-17)

- Capacity = the number of active Users with the Technician Role.
- A Slot is free if the count of confirmed or requested Bookings that overlap it is less than the capacity.
- Slot holding and double-booking: decided in the architecture spine (AD-9: bookings-owned advisory lock per Business, recount, then write).

## Tenant isolation (FR-11)

- Every table has `business_id` (from the seed). Decided in the architecture spine (AD-3): automatic application-level scoping now; Row-Level Security deferred as a second guard.

## Agent design hints

- The Agent uses tools (function calls) to get free Slots and to create the Booking Request. It never writes Slots or prices from memory (FR-17, FR-20).
- Agent calls run in the background worker, so the web request does not wait for the LLM.

## Golden Dataset (source plan)

No public dataset fits SevaDesk directly: Indian home services, our Services and Prices, Hindi and Hinglish, with expected booking results. So the builder creates it.

- **Main source: synthetic + hand-checked.** An LLM writes draft conversations from scenario cards (Service, language, Customer behaviour, expected result). The builder reads and fixes every one. Each case stores the expected details, Service, Price shown, Booking result, and language.
- **Inspiration only (check each licence first):** Schema-Guided Dialogue (Google, CC BY-SA 4.0; booking dialogues with slots), and research sets with Hindi-English code-mixed booking dialogues (DSTC2 code-mixed; HDRS). Use them to learn realistic phrasing, not as the golden set.
- **Later: the pilot.** Real pilot conversations can become cases only with the Customer's consent, and only after names, phones, and addresses are replaced with fake values (DPDP Act).
- **Do not scrape.** Real chats, reviews, or forum posts contain personal data, and most sites forbid scraping in their terms.
