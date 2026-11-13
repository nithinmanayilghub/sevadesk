# AWS staging — runbook

AWS staging is the full app on AWS: ECS Fargate (frontend, backend, worker), RDS Postgres,
ElastiCache Valkey, one load balancer, Secrets Manager, CloudWatch logs. Region **ap-south-1 (Mumbai)**.
It runs the same GHCR images as the demo.

**It costs money every hour it exists. Deploy, show it, destroy it. Never leave it running.**

Two Terraform stacks:

| Folder | Made | Holds |
|---|---|---|
| `bootstrap/` | once, by hand, with an **admin** login; never destroyed | state bucket, $5 budget, deployer role + boundary |
| `staging/` | per session by `deploy.sh`; removed by `destroy.sh` | everything the app runs on |

All commands below run in **Git Bash** from the repo root, unless a step says otherwise.

---

## Part 0 — Before the first time: check the money

1. AWS console → **Billing and Cost Management → Credits**. Note any credits and their expiry date.
2. **Free plan** accounts end after 6 months or when credits run out. Check your plan on the Billing home page.
3. The $5 budget (Part 1) counts the **real** cost (credits ignored). It covers the **whole account**,
   and this account is shared with other projects, so their spend counts too.

## Part 1 — Bootstrap (once)

You need an **admin** login for this one step. The everyday IAM user cannot create IAM roles.
Use an SSO admin profile (`aws configure sso`) or an admin IAM user's keys
(`aws configure --profile sevadesk-admin`). Do not use the root user.

```bash
cd infra/terraform/bootstrap
export AWS_PROFILE=sevadesk-admin                       # your admin profile name
export TF_VAR_budget_email='you@example.com'            # gets the budget alert; not stored in git
export TF_VAR_laptop_principal_arn="$(aws sts get-caller-identity --profile default --query Arn --output text)"
terraform init
terraform apply                                         # read the plan, then type yes
terraform output                                        # 3 values: copy them for Part 2 and Part 3
unset AWS_PROFILE
cd ../../..
```

- The bootstrap state file `infra/terraform/bootstrap/terraform.tfstate` stays on this laptop (gitignored).
  Keep a copy somewhere safe. If it is lost, the resources still work; they can be imported again.
- Check: `aws budgets describe-budgets --account-id "$(aws sts get-caller-identity --query Account --output text)" --query "Budgets[].BudgetLimit"`
  → `5.0 USD`. A direct email subscriber needs no confirmation.

### Laptop profile for the deployer role

Add this to `~/.aws/config` (`role_arn` = the `deployer_role_arn` output):

```ini
[profile sevadesk-staging]
role_arn = <deployer_role_arn>
source_profile = default
region = ap-south-1
```

Check: `aws sts get-caller-identity --profile sevadesk-staging` → an ARN with `assumed-role/sevadesk-deployer`.
If it says AccessDenied, the everyday IAM user may be missing `sts:AssumeRole`: ask the account admin to allow
`sts:AssumeRole` on the deployer role ARN for that user.

### Check the engine versions (once)

`staging/data.tf` uses Postgres `18` and Valkey `9.0`. Check that Mumbai offers them:

```bash
aws rds describe-db-engine-versions --profile sevadesk-staging --engine postgres --engine-version 18 \
  --query "DBEngineVersions[].EngineVersion" --output text
aws elasticache describe-cache-engine-versions --profile sevadesk-staging --engine valkey \
  --query "CacheEngineVersions[].EngineVersion" --output text
```

If `18` is missing, use the newest Postgres listed. If Valkey `9.0` is missing, use the newest listed.

## Part 2 — GitHub setup (once, BEFORE the PR with aws-staging.yml merges)

If the workflow runs before the environment exists, GitHub creates the environment with **no** approval rule.

1. Repo → **Settings → Environments → New environment** → `aws-staging`.
2. **Required reviewers**: add yourself. (Leave "Prevent self-review" off, so you can approve your own run.)
3. **Deployment branches and tags** → *Selected branches* → add `main`.
4. In that environment, add **secrets** `AWS_ROLE_ARN` (= `deployer_role_arn`) and `BOUNDARY_ARN` (= `boundary_arn`).
5. Add an environment **variable** `TF_STATE_BUCKET` (= `state_bucket`).
   (Secrets are hidden in logs; variables are not. The bucket name is not secret, but it holds the account ID,
   and the workflow hides the account ID with `mask-aws-account-id`.)

## Part 3 — Deploy from the laptop

Pick a commit on `main` that CI has built (its images exist in GHCR):

```bash
export AWS_PROFILE=sevadesk-staging
export TF_STATE_BUCKET='<state_bucket>'
export TF_VAR_boundary_arn='<boundary_arn>'
git fetch origin
infra/terraform/deploy.sh "$(git rev-parse origin/main)"
```

- First time: about 15 minutes (RDS and Valkey are slow to create).
- **First deploy only:** if it fails with a message about a missing service-linked role
  (`AWSServiceRoleForECS`), AWS is still creating it. Run the same command again.
- **First deploy only:** ElastiCache can fail with `408 ... This action cannot be completed now` while AWS
  creates its helper role (`AWSServiceRoleForElastiCache`). Run the same command again.
- **"insufficient capacity" in a zone:** small machine types sometimes sell out in one zone (2026-11-13:
  only `ap-south-1c` had space). There is a subnet in every zone, so RDS picks one with space on the next run.
  Valkey does not: if the error names the Valkey zone, pick another one and run again, for example
  `export TF_VAR_cache_az=ap-south-1a`.
- **Valkey stuck in `create-failed`:** every later plan (deploy AND destroy) stops with
  `unexpected state 'create-failed'`. Delete the broken cache by hand, then run the script again:
  `aws elasticache delete-replication-group --replication-group-id sevadesk-staging-cache` and
  `aws elasticache wait replication-group-deleted --replication-group-id sevadesk-staging-cache`.
- Done when it prints `staging is live: http://sevadesk-staging-....ap-south-1.elb.amazonaws.com`.
  It is HTTP, not HTTPS: there is no domain name for staging, so there is no certificate.
- Logs: AWS console → CloudWatch → Log groups → `/ecs/sevadesk-staging`. The backend stream shows the
  Alembic migration lines before Uvicorn starts.

## Part 4 — Deploy from GitHub (with approval)

1. Actions → **aws-staging** → **Run workflow** → branch `main`, action `deploy`, image tag empty (= that commit).
2. The run waits with "Review deployments". Click it → **Approve and deploy**.
3. The log ends with `staging is live: http://...`.

## Part 5 — Destroy (always, the same day)

Laptop (same three `export` lines as Part 3):

```bash
infra/terraform/destroy.sh
```

Or GitHub: Run workflow → action `destroy` → approve.

It ends with `clean: no billable staging resources` (exit 0). If it prints `LEFTOVER: ...` lines,
run `destroy.sh` again, or delete those resources in the console (region ap-south-1).
You can run the check alone at any time: `infra/terraform/check-clean.sh`.

## Part 6 — What it costs (ap-south-1, approximate)

| Part | Per hour |
|---|---|
| Load balancer | ~$0.03 |
| 3 Fargate tasks (ARM, 0.25 vCPU, 512 MB) | ~$0.03 |
| RDS db.t4g.micro + 20 GB | ~$0.025 |
| ElastiCache cache.t4g.micro | ~$0.02 |
| Public IPv4 addresses (ALB 2 + tasks 3) | ~$0.025 |
| **Total** | **~$0.12 per hour** (~$3 per day — so always destroy) |

The state bucket, budget, and roles (bootstrap) cost about $0 per month.

## Part 7 — Anthropic spending limit

The Anthropic API has no setting for this in code. Set it by hand:
console.anthropic.com → **Settings → Limits** → set a monthly spend limit (for example $5).

## Safety notes

- The deployer role can build and destroy staging. It cannot create admins: every role it makes must carry
  the boundary `sevadesk-staging-boundary`: write to the `/ecs/sevadesk-staging` log group and read
  `sevadesk-staging/*` secrets in ap-south-1, nothing else. So even an escaped role cannot read other
  projects' secrets.
- Accepted risk: the account is shared, and the deployer can still change other projects' EC2/RDS/ECS
  resources in ap-south-1, and read their Secrets Manager secrets in ap-south-1. Use it only through
  these scripts, and only from the approved GitHub environment or your own laptop.
- The database password is in the Terraform state (S3 bucket: private, encrypted, versioned) and in
  Secrets Manager. It is never in git or in a log.
- Traces are off on AWS (no collector). JSON logs go to CloudWatch.
