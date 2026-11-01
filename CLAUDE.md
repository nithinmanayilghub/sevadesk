# SevaDesk — Rules for Claude Code

## Who I am
- Beginner programmer. I like building and constant learning.
- Goal: ship a production-grade project AND truly understand it. No blind vibecoding.
- Talk to me in simple words. Short sentences. Explain from first principles. Low cognitive load.

## Source of truth
- WHAT to build: BMAD docs in /docs (brief, PRD, UX spec, architecture, stories).
- Project idea and constraints: docs/project-seed.md.
- HOW to build: Superpowers skills. Skip brainstorming; start at writing-plans using the BMAD story file.
- Build only the current story. Nothing extra. No over-engineering.

## Engineering rules
- Strict TDD (red → green → refactor).
- Follow the Definition of Done in docs/project-seed.md.
- Simple, readable, commented code. Clear names over clever code.
- Every bug fix adds a regression test.
- Never put secrets in code.

## Learning Protocol (balance speed + understanding)

### 1. Tag every file by learning level
Before building, label each file the story touches:
- CORE — must understand deeply (architecture, data models, AI agent, auth, multi-tenancy, payments, evals).
- STANDARD — understand purpose and data flow.
- BOILERPLATE — just know it exists and why (configs, generated migrations, styling, lockfiles).
Spend my learning time in that order. Do not over-explain boilerplate.

### 2. Before coding: Story Map (max 5 bullets)
- What this story does, in one sentence.
- Files to create/change, with CORE/STANDARD/BOILERPLATE tags.
- How data flows (request → … → response).
- Which production concept this teaches.
- Ask me to predict one thing (e.g. "Which file will handle X?").

### 3. During TDD
- Before writing each CORE test, tell me in one line what behaviour it checks.

### 4. Execution mode
- CORE-heavy stories: use executing-plans with checkpoints, so I can follow along.
- BOILERPLATE/STANDARD-heavy stories: use subagent-driven-development for speed.

### 5. After each story: Understanding Gate (max 10 minutes)
- Ask me 3 short questions: one "why", one "how does data flow", one "what breaks if…".
- If I answer wrong, explain briefly and ask once more.
- If still wrong, log it in docs/learning/gaps.md and move on. Do not block shipping.
- Skip the gate for pure-boilerplate stories.

### 6. Hands-on task
- Give me one small change (5–15 min) to make myself, by hand. Do not do it for me.
- Review my change after I finish.

### 7. Learning notes (keep short)
- Write docs/learning/<story-id>.md: what was built, why, concept learned, key files.
- Add new terms to docs/learning/glossary.md in plain words.
- At the end of each epic: update docs/learning/architecture-map.md with a Mermaid diagram, then ask me to explain the system back in 5 sentences.
- At the start of each new epic: quiz me on 2 items from gaps.md.

### 8. Time budget
- Learning steps should take about 20–25% of story time. If I'm going slower, tell me and suggest what to skip.

### Golden rule
Never let me merge code I cannot explain at the CORE level.
