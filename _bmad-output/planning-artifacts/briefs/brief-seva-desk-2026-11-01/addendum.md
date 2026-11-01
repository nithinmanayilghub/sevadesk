---
title: "Addendum: SevaDesk Product Brief"
created: 2026-11-01
---

# Addendum: SevaDesk Product Brief

These details do not fit in the brief. The PRD and architecture can use them.

## Pointer to technical detail

The tech stack, production engineering rules (testing, observability, AI evals, delivery), budget tracks A and B, cost guardrails, and the Definition of Done are in `docs/project-seed.md`. This addendum does not copy them, so there is only one source of truth.

## Competitor scan (short, 2026-11-01)

One web search only. Most sources are vendor marketing, so the claims are not verified. A deep check needs `bmad-deep-recon`.

- **Global:** Podium (the idea for this project), Jobber, and Housecall Pro. They are built for US workflows and prices.
- **India field-service tools:** KaryaFlow (offline field ops, maintenance contracts), MyService CRM (iPhone only), Aplany, Naxio (AI missed-call recovery for home services), Klervo, WePro, and low-cost listings around ₹500 per month on IndiaMART.
- **WhatsApp automation for appliance and AC repair:** for example, guides from Richautomate. They cover booking, estimate approval, ETA, and AMC reminders.
- **What this means for SevaDesk:** the category is crowded. SevaDesk positions itself as a well-engineered portfolio example, not as a market winner.

Sources: [KaryaFlow (GoodFirms)](https://www.goodfirms.co/software/karyaflow), [Capterra India: field service management](https://www.capterra.in/directory/10009/field-service-management/software?page=5), [Richautomate: field service](https://richautomate.in/tags/field-service), [MyService CRM](https://apps.apple.com/us/app/-/id6757950686), [IndiaMART listing](https://m.indiamart.com/impcat/field-management-service.html).

## Design note: solo owner and small team

Both business shapes have equal priority. So the role model must let one user hold the owner, staff, and technician roles at the same time. The UI must not force a solo owner through team-only steps (for example, "assign technician" when there is only one person).
