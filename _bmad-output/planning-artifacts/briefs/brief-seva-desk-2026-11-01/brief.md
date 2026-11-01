---
title: "Product Brief: SevaDesk"
status: final
created: 2026-11-01
updated: 2026-11-01
source: docs/project-seed.md
---

# Product Brief: SevaDesk

## Executive Summary

SevaDesk is an AI front desk for small Indian home-service businesses: AC repair, plumbing, electrical work, and appliance repair. The owner or a technician is often on a job with dirty hands or on a ladder. Unanswered calls and WhatsApp messages become lost customers, and bookings live on paper and in memory.

SevaDesk answers the customer first. An AI agent talks with the customer, collects the job details, and books a slot on the business calendar. The owner sees all messages in one inbox, sees the schedule, and sees how the business is doing. Later phases add the tools Indian businesses need: WhatsApp, UPI payments, GST invoices, AMC (annual maintenance contract) reminders, and Indian languages.

SevaDesk is also a learning project. One beginner builds it alone to learn how real production systems are built, tested, observed, and deployed, with a budget under $10 a month. The product idea is the "what". The production engineering is the real lesson.

## The Problem

- **Missed messages mean lost jobs.** A customer with a broken AC in May does not wait. If the business does not reply in minutes, the customer calls the next number. [ASSUMPTION: replies within minutes decide the booking; this is not yet checked with a real business.]
- **No system, only memory.** Bookings sit in a notebook, in WhatsApp chats, and in the owner's head. Jobs are forgotten, two jobs get the same slot, and payments are not followed up.
- **Repeat revenue leaks.** AMC renewals and yearly servicing depend on someone remembering to call the customer. Usually nobody does.
- **Today's tools do not fit.** Global tools like Podium, Jobber, and Housecall Pro are built for US workflows and prices. Indian tools exist, but most are field-service software or WhatsApp bots. Few combine an AI agent that books jobs with GST, UPI, and AMC in one simple, mobile-first product. [ASSUMPTION: based on a short web scan only; see addendum.]

## The Solution

SevaDesk is built in phases. Each phase works end to end before the next one starts.

1. **Answer and book (P1).** A webchat inbox. An AI agent collects the customer's name, address, problem, and preferred time, then books a real free slot. It never invents prices or slots. The owner gets a calendar and a simple dashboard.
2. **Run the job (P2).** A mobile view for technicians, job status updates, estimates, GST invoices, and a mock payment link.
3. **Meet customers where they are (P3).** WhatsApp Business API, SMS, and Razorpay UPI. The channels and payments plug in through adapters (small swappable connectors), so the core does not change.
4. **Grow and get smarter (P4–P6).** Google review requests, AMC reminders, campaigns, Hindi, Kannada, and Tamil, revenue questions to an "AI business manager", and voice AI calls.

## What Makes This Different

This is honest positioning, not a claimed moat.

- **AI that books, not only replies.** The agent finishes the task (a confirmed booking), and evals (automatic tests of the AI's answers) check that it does this correctly.
- **India-native in one place.** WhatsApp first, UPI, GST, AMC, Indian languages, low bandwidth.
- **Built like production software from day one.** Tests, tracing, AI evals in CI, tenant isolation, and cost guardrails. For a portfolio, this is the real differentiator: it shows engineering depth, not only features.

The market already has many tools. SevaDesk does not need to beat them commercially. It needs to be a credible, working, well-engineered example of the category.

## Who This Serves

SevaDesk designs for two business shapes equally:

- **Solo owner.** One person answers the phone and also does the job. One login holds the owner, staff, and technician roles. Needs: never miss a customer and see today's jobs on a phone.
- **Small team (2–10 people).** An owner, 1–2 office staff, and several technicians. Needs: one shared inbox, a clear schedule, and job status from the field.

The **end customer** uses SevaDesk without an account, through chat (later WhatsApp). Success for them is a fast reply and a confirmed time.

## Success Criteria

**For the builder (primary):**
- **Portfolio-ready (the "good enough" point):** P0 + P1 run on AWS from one deploy command, with a working AWS URL. AWS is switched on only for interviews or demo days (a few hours, a few dollars), then destroyed.
- Each shipped phase works end to end on the always-on free demo link.
- The builder can explain every CORE part of the system (architecture, data model, AI agent, auth, multi-tenancy, payments, evals) without notes. The Understanding Gate after each story checks this.
- The project creates interview opportunities for backend or AI engineering roles. [ASSUMPTION: no numeric target set.]
- Total running cost stays under $10 a month.

**For the product (checked by tests and evals):** [ASSUMPTION: first targets; the PRD will set the final numbers.]
- The AI agent books a correct job from a golden-dataset conversation in at least 90% of cases.
- The agent invents a price or slot in 0 cases in the eval set.
- Tenant-isolation tests show 0 data leaks between businesses.
- The AI service replies to a customer within 10 seconds.

**Pilot check (after P1 or P3):** one real business (a friend or relative) uses SevaDesk for 2 weeks and answers one question: "Did it save you a lost customer?" [ASSUMPTION: pilot length and question.]

## Scope

**First version = P0 + P1.**
- P0 walking skeleton: frontend + backend + database, CI, tests, tracing, evals harness, demo deploy, and AWS staging deploy.
- P1 core: multi-tenancy (many businesses share one system, each sees only its own data), auth and roles, webchat inbox, booking AI agent, calendar, and owner dashboard.

**Out of scope for the first version:** everything in P2–P6 (see The Solution). Phases are built in order.

## Constraints

- **Budget:** under $10 a month (expected $0–3). Open-source stack; Groq free tier (open-weight models) for daily development, Claude for CI evals and the demo; free managed tiers for the database, Redis, and observability; AWS on demand only. The backend and worker run on Oracle Cloud's free tier. Details: `docs/project-seed.md`.
- **Builder:** one beginner, who learns while building. Strict TDD. No code merged that the builder cannot explain at the CORE level.
- **Data:** customer names, phone numbers, and addresses are personal data under India's DPDP Act. A real pilot needs consent and safe handling of this data. Never send real customer data to free-tier AI services.
- The tech stack and engineering rules are fixed in `docs/project-seed.md`.

## Risks and Open Questions

- **Scope versus time.** P0–P6 is a big plan for one beginner. A half-built P5 is worth less than a solid P1–P3. The portfolio-ready point is P1 on AWS; later phases are a bonus.
- **WhatsApp access (P3).** The WhatsApp Business API needs Meta business verification and has a cost per conversation. This can break the budget or block P3. Check it before P3 starts.
- **Free-tier limits.** Free tiers can change or sleep when not in use. The demo can then be slow on first load.
- **Development model differs from Claude.** A prompt that works on a Groq model can fail on Claude, and the reverse. The Claude evals in CI are the final check. Groq free-tier limits can also change; the swappable AI layer limits the impact.

## Vision

If SevaDesk succeeds, it becomes the builder's flagship proof: a live, multi-tenant, AI-powered product with real tests, evals, and observability, and maybe one real business that depends on it. It shows the full path from idea to production. If the pilot goes well, the same base can grow into a real product for Indian service businesses.
