# SevaDesk architecture map (end of Epic 2)

Epic 1 built the **skeleton**: every part exists and talks to the others, but the app only says
"Namaste". Epics 2+ put real features into this skeleton.

## 1. One request, end to end (runtime)

```mermaid
flowchart LR
    U([Browser]) -->|HTTPS| C[Caddy<br/>front door + TLS]
    C -->|"/"| F[Frontend<br/>Next.js]
    C -->|"/api/*"| B[Backend<br/>FastAPI]
    B -->|SQL| P[(Postgres<br/>data)]
    B -->|"put job"| V[(Valkey<br/>job queue + heartbeat)]
    V -->|"take job"| W[Worker<br/>SAQ]
    W -->|SQL| P
    W -->|"heartbeat key (30 s TTL)"| V

    C -. spans .-> O[OTel collector]
    B -. "spans + JSON logs" .-> O
    W -. spans .-> O
    O -. "one trace" .-> G[Grafana<br/>local lgtm or Grafana Cloud]
```

- The **job** carries a `traceparent` label, so the worker's work joins the same trace as the request.
- `/api/health` asks Postgres, Valkey, and the worker heartbeat key. If one is missing, it answers 503.

## 2. Where the same app runs

| Place | How it starts | Postgres | TLS | Cost |
|---|---|---|---|---|
| Laptop | `docker compose up` (infra/compose) | container | Caddy, local | $0 |
| Demo (DigitalOcean droplet) | CI after every merge to main (infra/demo) | Neon (cloud) | Caddy + sslip.io | $12/month |
| AWS staging | `deploy.sh` / approved workflow (infra/terraform) | RDS | none (HTTP via ALB) | cents per hour, then `destroy.sh` |

On AWS the parts change names but keep their jobs: **ALB** = Caddy, **ECS Fargate** = the three
containers, **RDS** = Postgres, **ElastiCache** = Valkey, **Secrets Manager** holds `DATABASE_URL`.

## 3. How code reaches the world (delivery)

```mermaid
flowchart LR
    D[You: story branch] -->|PR| CI{CI<br/>lint, test, eval, build}
    CI -->|green + merge| M[main]
    M -->|images tagged with commit SHA| R[(GHCR)]
    R -->|"deploy job: SSH, pull, migrate, start"| DEMO[Demo droplet]
    DEMO -->|"/api/v1/hello version == SHA?"| OK([proved live])

    M -. "Run workflow + your approval" .-> AWS[aws-staging workflow]
    AWS -->|"OIDC: short login, no keys"| ROLE[sevadesk-deployer role<br/>inside the boundary]
    ROLE -->|Terraform| STG[AWS staging]
    STG -->|"destroy → check-clean"| CLEAN([nothing billable left])
```

## 4. Safety rails built in Epic 1

| Rail | Stops what |
|---|---|
| Branch protection + CI | broken code reaching main |
| Eval harness (exit 0/1/2) | the agent's answers getting worse without anyone noticing |
| Version check after deploy | "deployed" when the old code still runs |
| PII masking in logs | phone numbers and similar data in logs |
| OIDC + approval + boundary | stolen keys; unapproved AWS changes; a role that grows into an admin |
| `check-clean.sh` + $5 budget | a forgotten AWS bill |

## 5. Epic 2: who is calling, which Business, what may they do

Epic 2 put **people** into the skeleton: sign-up, log-in, one Business per User, Roles, a team, and a theme.
Every `/api/*` request that needs a User goes through the same gates, in this order:

```mermaid
flowchart LR
    U([Browser]) -->|"cookie: session token"| R[Route with ActorDep]
    R --> S{resolve_session<br/>hash token, find session,<br/>idle? membership active?}
    S -->|no| E401[401 → /login]
    S -->|yes| A[Actor<br/>user_id, business_id, roles]
    A --> T[tenant_scope business_id<br/>repositories filter by Business]
    T --> P{require_roles<br/>FR-10 table}
    P -->|no| E403[403]
    P -->|yes| DB[(Postgres<br/>only this Business's rows)]
    A -.->|"GET /me: roles, permissions, theme"| FE[Frontend /app layout<br/>hides pages + sets data-theme]
```

| Gate | Lives in | Stops what |
|---|---|---|
| Session cookie (only a hash stored) | `accounts/service.py` `resolve_session` | strangers; a leaked database giving working logins |
| Tenant scope | `core/tenancy.py`, `core/repository.py` | Owner A reading Business B's data (answers 404) |
| Roles | `accounts/permissions.py` `require_roles` | a Technician doing an Owner action (403) |
| Frontend `access.ts` | `frontend/src/lib/access.ts` | showing pages a Role cannot use (display only; the backend still checks) |

Per-person data (email, password hash, theme) sits on the global `users` table. Business data
(memberships, invites, and everything later) sits on tenant tables with a `business_id`.
