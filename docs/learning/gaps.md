# Learning gaps

This file lists things I did not understand yet. Each entry says where it came up and what to re-quiz.
At the start of each new epic, I get quizzed on 2 items from here.

| Date | Source | Question | Status |
|------|--------|----------|--------|
| 2026-11-02 | planning quiz, start of Epic 1 | Why does an agent job drop its old reply when a newer Customer Message exists? (AD-7) | explained; re-quiz at end of Epic 1 |
| 2026-11-03 | Story 1.2 Understanding Gate, Q1 | Why does the worker heartbeat key have a 30 s TTL? The worker crashed 10 s ago: 200 or 503? (Answer: 200, because the last key is still alive for up to 30 s. The TTL makes a missing key mean "worker dead".) | explained; re-quiz at start of Epic 2 |
| 2026-11-04 | Story 1.5 Understanding Gate, Q2 | What carries the trace ID from the API to the worker? (Answer: the `traceparent` label inside the job payload. Valkey only stores the job. `job_context()` writes the label; `job_span()` reads it.) | explained; re-quiz at start of Epic 2 |
| 2026-11-06 | Story 1.6 Understanding Gate, Q2 | How does merged code reach the demo server? (Answer: 1. CI builds the images and pushes them to GHCR, tagged with the commit SHA. 2. The deploy job logs in to the VM with SSH and copies the demo files. 3. On the VM, deploy.sh pulls the images, migrates, then starts them. 4. CI checks that /api/v1/hello answers with this SHA.) | explained; re-quiz at start of Epic 2 |
| 2026-11-13 | Story 1.7 Understanding Gate, Q2 | How does a GitHub run get into AWS? (Answer: 1. You approve; the job runs in environment aws-staging. 2. GitHub gives the job a signed token: "repo sevadesk, environment aws-staging". 3. configure-aws-credentials shows the token to AWS and asks for sevadesk-deployer. 4. AWS checks the role trust policy against the token. 5. AWS lends the role for a short time. No stored keys.) | passed 2026-11-13 (end of Epic 1 recap, 2nd try) |
| 2026-11-13 | Story 2.1 Story Map, predict + re-ask | Which module hashes a password (sign-up, log-in, invite accept)? (Answer: always `accounts`. It owns the `users` table and its `password_hash` column; other modules only call the `accounts` front door, AD-1/AD-2.) | explained; re-quiz at Story 2.1 Understanding Gate |
