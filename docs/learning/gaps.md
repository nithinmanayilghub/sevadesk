# Learning gaps

This file lists things I did not understand yet. Each entry says where it came up and what to re-quiz.
At the start of each new epic, I get quizzed on 2 items from here.

| Date | Source | Question | Status |
|------|--------|----------|--------|
| 2026-11-02 | planning quiz, start of Epic 1 | Why does an agent job drop its old reply when a newer Customer Message exists? (AD-7) | explained; re-quiz at end of Epic 1 |
| 2026-11-03 | Story 1.2 Understanding Gate, Q1 | Why does the worker heartbeat key have a 30 s TTL? The worker crashed 10 s ago: 200 or 503? (Answer: 200, because the last key is still alive for up to 30 s. The TTL makes a missing key mean "worker dead".) | explained; re-quiz at start of Epic 2 |
