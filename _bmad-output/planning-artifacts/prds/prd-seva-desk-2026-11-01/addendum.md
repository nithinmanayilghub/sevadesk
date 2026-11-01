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

- Demo: frontend on Vercel; backend and worker on Oracle Cloud Always Free (docker-compose); Postgres on Neon or Supabase free tier; Redis on Upstash free tier.
- AWS staging (Terraform): on demand only. Turn it on for interviews, then destroy it (FR-6).

## Slot calculation (FR-17)

- Capacity = the number of active Users with the Technician Role.
- A Slot is free if the count of confirmed or requested Bookings that overlap it is less than the capacity.
- Slot holding and double-booking need a database-level guard (for example, a transaction with a lock or an exclusion constraint). The architecture step chooses.

## Tenant isolation (FR-11)

- Every table has `business_id` (from the seed). The architecture step decides between application-level scoping only, or scoping plus Postgres Row-Level Security as a second guard.

## Agent design hints

- The Agent uses tools (function calls) to get free Slots and to create the Booking Request. It never writes Slots or prices from memory (FR-17, FR-20).
- Agent calls run in the background worker, so the web request does not wait for the LLM.
