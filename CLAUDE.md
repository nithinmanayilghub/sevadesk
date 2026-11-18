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
- Every story: use executing-plans (you build in this session; saves tokens).
- Stop at a checkpoint after each CORE task, so I can follow along.
- At the end: one whole-branch review by an Opus subagent.

### 5–7. After the story
- Story code done and final review clean: read docs/agents/after-story.md (Understanding Gate, hands-on task, learning notes).
- At the start of each new epic: quiz me on 2 items from gaps.md.

### 8. Time budget
- Learning steps should take about 20–25% of story time. If I'm going slower, tell me and suggest what to skip.

### Golden rule
Never let me merge code I cannot explain at the CORE level.
