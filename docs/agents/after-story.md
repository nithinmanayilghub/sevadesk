# After a story: learning steps

Read this when a story's code is done and the final review is clean, before the PR merges.
These are CLAUDE.md Learning Protocol §5–§7.

## 5. Understanding Gate (max 10 minutes)
- Ask me 3 short questions: one "why", one "how does data flow", one "what breaks if…".
- If I answer wrong, explain briefly and ask once more.
- If still wrong, log it in docs/learning/gaps.md and move on. Do not block shipping.
- Skip the gate for pure-boilerplate stories.

## 6. Hands-on task
- Give me one small change (5–15 min) to make myself, by hand. Do not do it for me.
- Review my change after I finish.

## 7. Learning notes (keep short)
- Write docs/learning/<story-id>.md: what was built, why, concept learned, key files.
- Add new terms to docs/learning/glossary.md in plain words.
- Last story of an epic: update docs/learning/architecture-map.md with a Mermaid diagram, then ask me to explain the system back in 5 sentences.
