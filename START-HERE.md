# START HERE — How to run SevaDesk

## Setup (once)
1. Create project folder. Copy in `CLAUDE.md` and `docs/project-seed.md`.
2. Install BMAD: `npx bmad-method install` → choose Claude Code.
3. Install Superpowers plugin in Claude Code (see obra/superpowers README).
4. `git init` and push to GitHub.

## Phase A — Planning with BMAD (new chat for each step, use /clear)
Use BMAD's help command to see exact command names for your version.

1. Analyst:   "Create a product brief from docs/project-seed.md. Don't re-ask what the seed answers."
2. PM:        "Create the PRD from the brief. Epics = phases P0–P6. Include Production Engineering requirements."
3. UX:        "Create a UX spec for P1 only. Mobile-first."
4. Architect: "Create the architecture from the PRD and seed. Cover testing, observability, evals, Terraform and CI/CD in detail. Add a Mermaid system diagram."
5. Readiness check: validate PRD, UX and architecture agree. Shard large docs.
6. Scrum Master: "Create stories for Epic P0 only."

After step 4, read the architecture yourself. Ask Claude:
"Walk me through this architecture in simple words. Tag each component CORE/STANDARD/BOILERPLATE."

## Phase B — Building with Superpowers (per story)
Send:
"Follow CLAUDE.md. Use writing-plans on docs/stories/<story-file>.md. Skip brainstorming; the story is approved. Start with the Story Map."

Then let the Learning Protocol run: Story Map → TDD → Understanding Gate → hands-on task → learning note → merge.

When an epic is done: go back to BMAD Scrum Master for the next epic's stories.

## Token-saving habits
- /clear between stories. Docs carry the memory, not chat history.
- Create stories for one epic at a time.
- Paste exact errors. Never say "it doesn't work".
- Never ask to "improve everything".

## Cost habits (budget: under $10/month)
- Day one: create an AWS Budget alert at $5.
- Day one: set a monthly spending limit in the Anthropic Console.
- Work locally with docker-compose.
- Portfolio demo runs on free tiers (Track A in project-seed.md).
- Full AWS (Track B) only on-demand: deploy → test a few hours → `terraform destroy`.
- Never create a NAT Gateway.
- Use Haiku for development and most evals.
