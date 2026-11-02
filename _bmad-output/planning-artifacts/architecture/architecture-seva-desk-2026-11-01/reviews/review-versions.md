# Review: Versions and technology reality-check

- **Reviewed:** `ARCHITECTURE-SPINE.md` (Stack table, AD-6, AD-7, AD-11, AD-12, AD-14, Deployment) and the `(version)` entries in `.memlog.md`
- **Date:** 2026-11-01
- **Method:** Live checks against PyPI JSON, the npm registry, the GitHub API, endoflife.date, vendor docs, and web search. I installed and resolved the stack in a scratch folder: `uv pip compile` for Python, and `npm install` plus a real `openapi-typescript` run for the frontend.

## Verdict

**Not ready to build. Two pins cannot be installed together, and one free-tier choice cannot carry the design.** Every version number in the Stack table is the current latest. But the memlog checked versions one at a time ("what is latest?"). It never checked whether they work together. That gap caused three blocking problems:

1. `arq 0.28.0` + `redis-py 8.1.0` cannot be installed together (proved with `uv`).
2. `TypeScript 7.0.2` + `openapi-typescript 7.13.0` cannot be installed together, and codegen crashes when forced (proved with npm and a real run).
3. An idle arq worker sends about 10x the Upstash free-tier monthly command limit.

There is also one maintenance risk: arq is officially in "maintenance only mode".

## Findings (ordered by severity)

### F1. BLOCKER: arq 0.28.0 needs redis-py below 6, but the spine pins redis-py 8.1.0

- **Evidence:** arq 0.28.0 `requires_dist`: `redis[hiredis]>=4.2.0,<6`. The same limit is in `pyproject.toml` on arq `main`. Running `uv pip compile` on the full stack (Python 3.14) fails:
  > Because arq==0.28.0 depends on redis[hiredis]>=4.2.0,<6 … and you require redis==8.1.0 … your requirements are unsatisfiable.
- If I drop the redis pin, the stack resolves with `redis==5.3.1` and `hiredis==3.5.0`.
- **Fix:** Pick one of these:
  - (a) Keep arq and pin `redis` to `>=5.3,<6`. Change the Stack row to "redis-py 5.3.1 (capped by arq)".
  - (b) Replace arq (see F2). Then redis-py 8.1.0 can stay.

### F2. HIGH: arq is in "maintenance only mode"

- **Evidence:** The arq README says: "**In maintenance only mode**: arq is in maintenance only mode, see #510." The last push and release was 2026-04-16 (0.28.0, which added Python 3.14 support). It has 111 open issues. It is not archived, but it is pinned to an old redis-py major (F1).
- **Why it matters:** arq carries AD-7 (agent replies) and AD-10 (the 12 h expiry cron). A queue that only gets maintenance, and is stuck on an old Redis client, is a weak base for the core async path. Neither the memlog nor the spine records this status.
- **Alternatives that are maintained** (checked on PyPI, all support Python 3.14):
  - **SAQ 0.26.5**: async, cron support. Released 2026-10-29.
  - **Procrastinate 3.10.0**: Postgres-backed, so no Redis is needed for jobs. Released 2026-09-23.
  - **Taskiq 0.13.0**: still marked Alpha.
- **Fix:** Either (a) record a deliberate decision: "arq accepted although maintenance-only; redis-py capped <6; revisit at P4". Or (b) switch to SAQ, which has a similar API and cron jobs. Procrastinate also deserves a look: it would let jobs live in Postgres and would remove the Upstash problem in F3.

### F3. HIGH: Upstash Redis free tier cannot run an always-on arq worker

- **Evidence:** The Upstash free tier is 500,000 commands per month, 256 MB, one database (Upstash blog 2026; third-party pricing pages agree). arq's worker defaults to `poll_delay=0.5` and runs `zrangebyscore` on every loop (`arq/worker.py` lines 207 and 391). That is 2 commands per second while idle: 172,800 per day, about **5.2M per month, 10x the free limit**. This is before any jobs, cron ticks, health checks, rate-limit counters, or the AD-12 cap counters. Raising `poll_delay` to 5 s still gives about 520K per month and adds latency, which works against NFR-3.
- **Compatibility:** Upstash speaks the Redis protocol, so arq would connect. The problem is cost and quota, not the protocol.
- **Fix:** On the demo, run Redis (or Valkey) as a container inside the same docker-compose on the Oracle VM, just like local. Remove "Upstash Redis free" from the Deployment diagram. Or move jobs to Postgres (Procrastinate) and keep Redis only for counters.

### F4. HIGH: TypeScript 7.0.2 breaks openapi-typescript 7.13.0, and with it AD-14

- **Evidence:**
  - `openapi-typescript@7.13.0` declares `peerDependencies: {"typescript": "^5.x"}`. `npm install typescript@7.0.2 openapi-typescript@7.13.0` fails with `ERESOLVE`. With `typescript@6.0.3` it also fails with `ERESOLVE`.
  - Forced with `--legacy-peer-deps`, the CLI crashes on a trivial spec: `TypeError: Cannot read properties of undefined (reading 'createKeywordTypeNode')` in `openapi-typescript/dist/lib/ts.mjs`. TS 7 is the native Go compiler and has no JavaScript compiler API yet (the Next.js docs say the same).
  - Upstream issue openapi-ts/openapi-typescript#2841 "openapi-typescript doesn't work with Typescript 7" is **open**.
  - With `typescript@5.9.3`, all three of typescript, openapi-typescript and openapi-fetch install cleanly. With TS 6.0.3 forced, codegen works, but the peer conflict stays.
- **Next.js 16 + TS 7:** This pairing *is* supported. Per the current Next.js docs, `next build` uses the project-local `tsc` CLI by default, so TS 7 works. The cost is that you lose Next-specific error code frames. So TS 7 does not block Next.js. It blocks only the generated API client.
- **Fix:** Pin **TypeScript 5.9.3** (latest 5.x, 2025-09-30) until #2841 is fixed. Note that Next.js's own TS plugin and the JS-API type checker work fully on 5.x. Record "TS 7 blocked by openapi-typescript #2841" in Deferred.

### F5. MEDIUM: openapi-typescript / openapi-fetch release activity has slowed

- **Evidence:** The last releases were openapi-typescript 7.13.0 and openapi-fetch 0.17.0, both on 2026-02-11, almost 9 months ago. The repo was last pushed 2026-09-25 and has 287 open issues. It is not archived. openapi-fetch is still 0.x.
- **Fix:** Acceptable for the MVP, but write it down. Pin exact versions and check the generated client into Git, so a broken upstream cannot block builds. Also record a fallback, such as `@hey-api/openapi-ts` or Orval (not verified in this review).

### F6. MEDIUM: Oracle Cloud Always Free "always on" demo has reclamation and capacity risk

- **Evidence (secondary sources; I could not read Oracle's primary page text):**
  - Oracle reclaims idle Always Free instances. Low CPU, network and memory over 7 days, below about 15% at the 95th percentile, can trigger it.
  - Several 2026 reports (InfoQ, Japanese and Korean guides) say the A1 allowance was cut in half, to 2 OCPU / 12 GB. A1 creation often fails with "Out of host capacity".
- **Why it matters:** A quiet portfolio demo is exactly the low-use profile that gets reclaimed. The spine assumes the server is "always on".
- **Fix:**
  - Mark the Oracle allowance as **unconfirmed** and check it on the Oracle console before the deploy story.
  - Upgrading the account to Pay-As-You-Go (it stays $0 inside Always Free limits) is the usual way to avoid idle reclamation. Verify that claim on Oracle's docs.
  - Size the compose stack to fit 1 OCPU / 6 GB in case of the cut: Next.js + FastAPI + worker + Caddy + Redis.

### F7. MEDIUM: "Neon/Supabase" is not one decision, and Supabase pauses idle projects

- **Neon:** Supports Postgres 14–18, with 18.6 available (Neon version-policy page). So **PostgreSQL 18 works on Neon**. Whether PG 18 is offered on the Free plan was not explicitly confirmed. The free plan has 100 CU-hours per project per month (some Neon docs still say 50) and 0.5 GB storage. Compute suspends after the quota is used up.
  - Watch out: if the expiry cron (AD-10) or any health check hits Postgres every minute, Neon never scales to zero. At 0.25 CU that is about 182 CU-h per month, which is over the quota and the demo DB stops.
- **Supabase:** Free projects pause after 7 days of inactivity, which conflicts with "always on". Its default Postgres major version for new projects was not confirmed.
- **Fix:**
  - Pick **Neon** and write it down. Drop Supabase.
  - Run the expiry job hourly, not every minute, and send no DB health checks.
  - Or run Postgres 18 in the Oracle VM's compose. The VM has enough RAM, but you must then own backups.
  - Confirm PG 18 in the Neon project-creation UI.

### F8. MEDIUM: Groq is fine for tool calling, but the details matter for AD-8 / AD-11

- **Evidence:**
  - Groq docs say all hosted models support tool use, using the OpenAI-style `tools` / `tool_calls` / `role: tool` format. The `openai` SDK with a Groq `base_url` is the usual client, so that part is confirmed.
  - **Parallel tool calls are not supported** on `openai/gpt-oss-20b` and `gpt-oss-120b`. They are supported on `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `qwen/qwen3.8-27b` and others.
  - The rate-limit page lists gpt-oss and qwen at 30 RPM, 1K RPD, **8K TPM**, 200K TPD. The page labels these "base limits for the Developer plan". Exact free-tier numbers were **not confirmed** from the primary source.
- **Why it matters:** 8K tokens per minute is tight once you count tool schemas, the system prompt and conversation history across several agent loop turns.
- **Fix:** The AI port should send `parallel_tool_calls=false`, or the agent loop should handle tool calls one at a time. Choose the Groq model id with tool-use and TPM limits in mind, and record it in the agent story. This is already deferred correctly in the spine.

### F9. LOW: anthropic 2.x is ten days old

- **Evidence:** anthropic 2.0.0 was released 2026-10-21. Four releases followed in three days (2.3.0 on 2026-10-23). It now depends on `httpx2`, while langfuse 5.1.0 still depends on `httpx<1`. Both resolved together, so there is no conflict, but the app will ship two HTTP stacks.
- **Fix:** Pin the exact version (already done), and pass the `httpx`/`httpx2` difference to the agent story. If the 2.x churn bites, 1.x is the fallback.

### F10. LOW: Node.js 24 is now in maintenance LTS

- **Evidence:** endoflife.date shows Node 24 active support ended 2026-10-20. Security support runs to 2028-04-30. Node 26 became LTS 2026-10-28. Next.js 16.4.3 needs `node >=20.9.0`, so it is fine.
- **Fix:** Node 24 is acceptable. Pin `24.22.2` in the Dockerfile. Consider Node 26 LTS once Next.js, Vitest and Playwright confirm it.

### F11. LOW: pwdlib is still a "Beta" package

- **Evidence:** pwdlib 0.3.1 (2026-08-12) has the classifier `Development Status :: 4 - Beta`. The repo is active (last push 2026-08-17). It wraps `argon2-cffi` 25.1.0, which is stable.
- **Fix:** Fine for the MVP (it is what FastAPI's docs use). Record that `argon2-cffi` is the stable fallback, so AD-5 does not depend on pwdlib.

### F12. INFO: Langfuse Cloud free and Grafana Cloud free

- **Langfuse Hobby:** 50k units per month, 30-day retention, 2 users. Each AI call, span and score uses units. CI eval runs (AD-12) can use them up quickly.
  - Fix: tag eval traces, sample them, or send CI evals to a separate project.
- **Grafana Cloud free:** 10k metric series, 50 GB logs, 50 GB traces, 14-day retention, 3 users. These are secondary sources, but they agree. The OTel OTLP export fits.
  - Some third-party pages carry conflicting claims of a free-tier change in September 2026. **Confirm on grafana.com/pricing.**

## Confirmed OK (live check, 2026-11-01)

| Item | Pinned | Latest / status | Python 3.14 | Notes |
| --- | --- | --- | --- | --- |
| Python | 3.14 | 3.14.10; 3.15.2 also out | n/a | Good choice. 3.14 is in bugfix support until 2027-10 |
| FastAPI | 0.162.0 | 0.162.0 (2026-10-23) | yes | |
| Uvicorn | 0.54.0 | 0.54.0 | yes | |
| SQLAlchemy | 2.1.6 | 2.1.6 (py>=3.11) | yes | |
| Alembic | 1.20.1 | 1.20.1 | yes | |
| Pydantic | 2.14.2 | 2.14.2 (2026-10-29) | yes | |
| pydantic-settings | 2.16.2 | 2.16.2 | yes | |
| psycopg (+binary) | 3.3.6 | 3.3.6 | yes | |
| arq | 0.28.0 | 0.28.0 | yes | **maintenance-only; redis<6 (F1, F2)** |
| redis-py | 8.1.0 | 8.1.0 | yes | **incompatible with arq (F1)** |
| pwdlib | 0.3.1 | 0.3.1, Beta | yes | F11 |
| anthropic | 2.3.0 | 2.3.0 | yes | F9 |
| openai | 3.42.0 | 3.42.0 (2026-10-31) | yes | Groq client |
| langfuse | 5.1.0 | 5.1.0 (needs OTel >=1.45) | yes | Matches OTel pin |
| opentelemetry-sdk | 1.45.2 | 1.45.2 | yes | |
| pytest | 9.2.0 | 9.2.0 | yes | |
| testcontainers | 4.15.0 | 4.15.0 | yes | |
| PostgreSQL | 18 | 18.6; EOL 2030-11 | n/a | On Neon and RDS (RDS 18.6) |
| Node.js | 24 LTS | 24.22.2, maintenance LTS | n/a | F10 |
| Next.js | 16.4.3 | 16.4.3 | n/a | TS 7 is OK through the CLI checker |
| React | 19.3.1 | 19.3.1 | n/a | Next.js peer `^19` OK |
| TypeScript | 7.0.2 | 7.0.2 | n/a | **breaks codegen (F4)** |
| Tailwind CSS | 4.3.3 | 4.3.3 | n/a | |
| openapi-typescript | 7.13.0 | 7.13.0 (2026-02-11) | n/a | **peer TS ^5 (F4, F5)** |
| openapi-fetch | 0.17.0 | 0.17.0 (2026-02-11) | n/a | F5 |
| Vitest | 5.0.5 | 5.0.5 | n/a | |
| Playwright | 1.64.1 | 1.64.1 | n/a | |
| Caddy | 2.11.7 | v2.11.7 (2026-10-03) | n/a | |
| Terraform | 1.17.1 | v1.17.1 (2026-10-28) | n/a | BUSL licence; fine for this use |

Python 3.14 is fine for the whole Python stack. Every package lists a 3.14 classifier, and `uv pip compile --python-version 3.14` resolves once the redis pin is removed. I did not check that every compiled dependency (for example `hiredis`, `argon2-cffi-bindings`) ships cp314 wheels for linux/arm64, which the Oracle A1 VM needs. Check this in the first Docker build.

## Process note

The memlog `(version)` entries say "Registry check" but record only the latest numbers. Add a lock-file step to the walking-skeleton story: `uv lock` plus `npm install` with no `--force`. That turns "latest" into "installable together" in CI.

## Sources

- PyPI JSON API (`pypi.org/pypi/<pkg>/json`) for all Python pins; npm registry for all JS pins; GitHub API for Caddy, Terraform, arq, openapi-typescript and pwdlib
- [arq README (maintenance-only notice)](https://github.com/python-arq/arq) and its `pyproject.toml` / `arq/worker.py`
- [openapi-typescript issue #2841](https://github.com/openapi-ts/openapi-typescript/issues/2841)
- [Next.js TypeScript docs (Using TypeScript 7)](https://nextjs.org/docs/app/api-reference/config/typescript)
- [endoflife.date: Node.js](https://endoflife.date/nodejs), [Python](https://endoflife.date/python), [PostgreSQL](https://endoflife.date/postgresql), [RDS PostgreSQL](https://endoflife.date/amazon-rds-postgresql)
- [Neon Postgres version policy](https://neon.com/docs/postgresql/postgres-version-policy), [Neon pricing](https://neon.com/pricing)
- [Upstash vs ElastiCache 2026 (free tier 500K commands/month)](https://upstash.com/blog/upstash-vs-aws-elasticache-serverless-redis-pricing-and-performance-2026)
- [Groq tool use](https://console.groq.com/docs/tool-use), [Groq rate limits](https://console.groq.com/docs/rate-limits)
- [Langfuse pricing](https://langfuse.com/pricing.md)
- [Grafana Cloud pricing explained 2026 (Last9)](https://last9.io/blog/grafana-cloud-pricing/)
- [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm), [InfoQ on Oracle free-tier limits](https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/)
- [Supabase project paused (Product Compass)](https://www.productcompass.pm/p/supabase-project-paused)
- Local reproductions (scratchpad): `uv pip compile` of the full Python stack; `npm install` + `npx openapi-typescript` with TS 7.0.2, 6.0.3 and 5.9.3
