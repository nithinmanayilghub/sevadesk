# SevaDesk — Project Seed (input for BMAD agents)

## Idea
AI operating system for Indian home-service businesses (AC repair, plumbers, electricians, appliance repair). Inspired by Podium (homeservices.podium.com), adapted for India.

## Problem
Small service businesses miss calls and WhatsApp messages while on jobs. Missed message = lost customer. Owners rely on paper and memory for bookings, payments and follow-ups.

## Users
Owner, office staff, technician, end customer.

## Product goal
Premium feature set, delivered as a scalable MVP in phases. Build phases in order.
- P0 Walking skeleton: hello-world frontend + backend + DB with CI, tests, tracing, evals harness, and deploy to AWS staging working end to end.
- P1 Core: multi-tenant, auth/roles (owner, staff, technician), unified inbox (webchat), AI agent that collects details and books jobs, scheduling calendar, owner dashboard.
- P2 Field ops: technician mobile view, job status, estimates + GST invoices, mock payment link.
- P3 Channels + payments: WhatsApp Business API, SMS, Razorpay UPI.
- P4 Growth: Google review requests, AMC (annual maintenance contract) reminders, campaigns.
- P5 Intelligence: Hindi/Kannada/Tamil, analytics, "AI business manager" (ask questions about revenue).
- P6 Voice AI calls.

## India-specific
WhatsApp-first, UPI payments, GST invoices, AMC contracts, Indian languages, mobile-first, low-bandwidth friendly.

## Technical constraints
- Backend: Python, FastAPI, SQLAlchemy, Alembic.
- DB: PostgreSQL. Cache/queue: Redis + background worker (AI calls, messages, reminders).
- Frontend: Next.js + TypeScript + Tailwind, responsive, mobile-first.
- AI: Claude API behind a swappable AI service layer. Prompts versioned in code.
- Multi-tenant: every table has business_id; strict isolation.
- Adapter pattern for channels (webchat → WhatsApp/SMS) and payments (mock → Razorpay).
- Config via env vars. Docker + docker-compose locally.

## Production Engineering (required in architecture and every story)

### Testing
- Unit: pytest (backend), Vitest (frontend).
- Integration: real Postgres/Redis via Testcontainers; API tests.
- E2E/regression: Playwright for key user flows.
- Every bug fix adds a regression test. Coverage gate in CI.

### Observability
- OpenTelemetry for traces, logs, metrics (backend + worker).
- Structured JSON logs with request and trace IDs.
- LLM observability with Langfuse (self-hostable): prompts, responses, tokens, cost, latency per call.
- Health checks, error tracking, basic dashboards and alerts.

### AI Evals
- Golden dataset of customer conversations (English + Hindi).
- Checks: correct detail extraction, correct booking, no hallucinated prices/slots, tone, language match.
- Code-based checks first; LLM-as-judge for tone/quality.
- Evals run in CI; block merge if score drops (AI regression).

### Delivery
- Environments: local (docker-compose), demo (always-on, low cost), aws-staging (on-demand).
- GitHub Actions: lint → tests → evals → build → deploy demo → manual approval for aws-staging.
- Alembic migrations run in the pipeline.
- Same Docker images run everywhere. Only config (env vars) changes.

### Budget: under $10/month total (hard constraint)
Two deployment tracks:

Track A — Always-on demo (portfolio link), target $0–5/month:
- Frontend: Vercel free tier.
- Backend + worker: one small server (~$5) running docker-compose, or a free-tier host.
- Postgres: Neon or Supabase free tier.
- Redis: Upstash free tier.
- LLM tracing: Langfuse Cloud free (hobby) plan.
- Logs/traces/metrics: Grafana Cloud free tier via OpenTelemetry.

Track B — Full AWS (for learning), on-demand only:
- Terraform: ECS Fargate, RDS Postgres, ElastiCache, ALB, Secrets Manager, CloudWatch.
- Paid by new-account AWS Free Tier credits ($100, up to $200; Free plan ends after 6 months or when credits run out).
- Deploy → test for a few hours → `terraform destroy`. Never leave running.
- Portfolio-ready = P0 + P1 deployable to AWS with one command; switch on for interviews/demo days only, then destroy.
- No NAT Gateway (use public subnets with strict security groups for staging).
- Always-on Track B would cost roughly $100–130/month, so it must stay on-demand.

Cost guardrails (set up in Epic P0):
- AWS Budget alert at $5.
- Anthropic Console monthly spending limit.
- Use a cheaper Claude model (Haiku) for development and most evals; larger model only where quality needs it.
- Evals in CI run a small smoke set on every PR; full eval set on demand or nightly.
- Observability code must be vendor-neutral (OpenTelemetry), so free-tier tools can be swapped later.

AI API budget: about $2–5/month for light use.

Open-source cost choices (decided 2026-11-01):
- Daily development uses open-weight models on the Groq API free tier (OpenAI-compatible), behind the same AI service layer. Claude runs CI evals that gate merges, and the demo. Ollama rejected: laptop has 8 GB RAM, no GPU. Send only fake data to Groq.
- Database, Redis, and observability stay on free managed tiers (no self-hosting: it needs RAM and upkeep).
- No unofficial WhatsApp libraries (they break Meta's rules and risk a number ban). Use the official API in P3.
- Backend server (Track A demo): Oracle Cloud Always Free runs backend + worker via docker-compose. PostgreSQL stays the database.

### Security & compliance
- Tenant-isolation tests, rate limiting, input validation.
- PII handling per India's DPDP Act. No secrets in code.

### Definition of Done (every story)
Tests pass. Evals pass (if AI touched). Traces visible. Docs updated. Learning note written. Understanding Gate done (see CLAUDE.md).

## Context
Personal portfolio project to learn how production systems are built and deployed. Solo builder, beginner programmer. Total budget under $10/month (see "Budget" section).

## Out of scope
Anything beyond the current phase.
