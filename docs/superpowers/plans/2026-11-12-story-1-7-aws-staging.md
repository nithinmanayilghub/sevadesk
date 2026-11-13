# Story 1.7 One-Command AWS Staging Deploy and Destroy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (CLAUDE.md: Terraform, IAM and the deploy scripts are CORE → inline with checkpoints). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `infra/terraform/deploy.sh <sha>` creates the full AWS staging environment and serves the hello page from the same GHCR images as the demo. `infra/terraform/destroy.sh` removes it all and proves nothing billable is left. Both run on the laptop or in a GitHub Actions workflow that waits for manual approval.

**Architecture:** Two Terraform stacks. `bootstrap/` is applied once with an admin login and never destroyed: the S3 state bucket, the $5 AWS Budget, the deployer role (with a permissions boundary) and the boundary policy. `staging/` is created and destroyed per session by the deployer role: VPC with 2 public subnets (no NAT), ALB (`/api/*` → backend, rest → frontend), ECS Fargate ARM64 services (frontend, backend, worker), RDS Postgres, ElastiCache Valkey, one Secrets Manager secret (`DATABASE_URL`), CloudWatch log group. The backend image CMD already runs `alembic upgrade head` before uvicorn, so migrations run before the backend starts with no extra step. Terraform state lives in S3, so the laptop and CI share it.

**Tech Stack:** Terraform `~> 1.17` (laptop 1.17.2), AWS provider `~> 6.0`, random provider; `terraform test` with `mock_provider` (no AWS calls, no credentials); bash scripts; pytest subprocess/text tests with fake `terraform`/`aws`/`curl` (same pattern as `test_deploy_script.py`); GitHub Actions `workflow_dispatch` + environment protection rule; AWS OIDC.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 1.7: One-command AWS staging deploy and destroy" (FR-6, AR-19, AR-20, NFR-7). Architecture: `_bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md` → "Deployment & environments". Seed: `docs/project-seed.md` → "Track B".

## User decisions (2026-11-12)

- Region: **ap-south-1 (Mumbai)**.
- Run mode: **laptop and CI**. S3 remote state; GitHub logs in with OIDC (no AWS keys in GitHub).
- Credits: **unknown** → the runbook's first step is "check Billing → Credits". The budget counts real cost, not cost after credits.
- Account: **same shared account, tight role**. The account also hosts other projects (verified: the everyday IAM user belongs to other projects' groups). Bootstrap runs once with an admin login. After that the laptop AND CI use only the deployer role.

## Facts verified by the plan review (2026-11-12)

- A GitHub OIDC provider `token.actions.githubusercontent.com` **already exists** in the account → read it with a data source, never create or import it.
- the everyday IAM user gets AccessDenied on `rds:DescribeDBEngineVersions` and `elasticache:DescribeCacheEngineVersions` → it cannot deploy; it may only assume the deployer role.
- `AWSServiceRoleForECS` does not exist yet → the first apply may fail once while AWS creates it; re-run once.
- GHCR images are public and multi-arch (anonymous pull works).
- Latest Terraform is 1.17.2; AWS provider 6.73.0.

## Global Constraints

- Region `ap-south-1`. Every staging resource name starts with `sevadesk-staging`.
- Provider `default_tags`: `Project = "sevadesk"`, `Environment = "staging"` (staging) / `Environment = "bootstrap"` (bootstrap). `check-clean.sh` relies on these tags.
- Images, exact: `ghcr.io/nithinmanayilghub/sevadesk-backend:${var.image_tag}` (backend AND worker) and `ghcr.io/nithinmanayilghub/sevadesk-frontend:${var.image_tag}`. `image_tag` = full commit SHA, no default.
- Same env vars as the demo: backend/worker get `DATABASE_URL` (from Secrets Manager), `REDIS_URL` (plain env). No `OTEL_EXPORTER_OTLP_ENDPOINT` on AWS: traces off, JSON logs go to CloudWatch (telemetry.py sends nothing when the var is empty).
- `DATABASE_URL` = `postgresql+psycopg://seva:<pw>@<rds-address>:5432/seva?sslmode=require`. Password from `random_password` with `special = false` (no URL escaping). It lives in the S3 state: bucket private, SSE-S3, versioned (comment this).
- Backend container has **no `command`** (keeps the image CMD: migrate, then start). Worker `command = ["saq", "app.worker.settings"]`.
- Fargate: `runtime_platform` `LINUX`/`ARM64`, each task `cpu = 256`, `memory = 512`, `desired_count = 1`, `assign_public_ip = true`, `wait_for_steady_state = true`.
- No `aws_nat_gateway` anywhere. No Elastic IP.
- Security groups: ALB accepts 80 from the internet. Tasks accept 3000/8000 only from the ALB SG. RDS (5432) and Valkey (6379) accept only from the tasks SG. RDS `publicly_accessible = false`.
- Destroy must really delete: RDS `skip_final_snapshot = true`, `deletion_protection = false`, `backup_retention_period = 0`; secret `recovery_window_in_days = 0`; ALB `enable_deletion_protection = false`; log group `retention_in_days = 1`.
- HTTP only (no domain → no TLS certificate). Public URL = `http://<alb-dns-name>`. Accepted for staging; noted in the runbook.
- Budget: `limit_amount = "5"`, `USD`, `MONTHLY`, `COST`, notify at 100 % `ACTUAL`, `include_credit = false`. Email from `var.budget_email` (no default; `TF_VAR_budget_email`, never committed). It covers the **whole shared account** (a tag-filtered budget needs an activated cost-allocation tag: deferred).
- Deployer role `sevadesk-staging-deployer`. Trust (built with `jsonencode`, not `aws_iam_policy_document`):
  - GitHub: Federated = existing OIDC provider ARN; `StringEquals` `token.actions.githubusercontent.com:aud = sts.amazonaws.com` and `:sub = repo:nithinmanayilghub/sevadesk:environment:aws-staging`.
  - Laptop: AWS principal = `var.laptop_principal_arn` (the the everyday IAM user user ARN; `TF_VAR_`, never committed).
- Deployer permissions (one customer-managed policy, no `PowerUserAccess`):
  - `ec2:*`, `ecs:*`, `elasticloadbalancing:*`, `rds:*`, `elasticache:*`, `secretsmanager:*`, `logs:*` only with condition `aws:RequestedRegion = ap-south-1`.
  - `s3:ListBucket` on the state bucket; `s3:GetObject`/`PutObject`/`DeleteObject` on `<state-bucket>/staging/*`.
  - `iam:CreateServiceLinkedRole` for `ecs`, `elasticloadbalancing`, `rds`, `elasticache` service names only (`iam:AWSServiceName` condition).
  - IAM writes (`CreateRole`, `DeleteRole`, `TagRole`, `UntagRole`, `PutRolePolicy`, `DeleteRolePolicy`, `AttachRolePolicy`, `DetachRolePolicy`) only on `arn:aws:iam::*:role/sevadesk-staging-*` **and** `CreateRole`/`PutRolePolicy`/`AttachRolePolicy` require `iam:PermissionsBoundary = <boundary ARN>`. `AttachRolePolicy` also requires `iam:PolicyARN = arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy`.
  - `iam:PassRole` on `sevadesk-staging-*` only with `iam:PassedToService = ecs-tasks.amazonaws.com`.
  - IAM/STS reads (`iam:Get*`, `iam:List*`, `sts:GetCallerIdentity`).
  - Accepted risk (comment in code + runbook): the deployer can still change other projects' EC2/RDS/etc. in ap-south-1. It cannot create admins or touch IAM outside `sevadesk-staging-*`.
- Boundary policy `sevadesk-staging-boundary`: allows only `logs:CreateLogStream`, `logs:PutLogEvents`, `secretsmanager:GetSecretValue`, `ecr:GetAuthorizationToken` (needed by the managed execution policy; harmless) — the most any task role can ever do.
- No AWS account ID, role ARN, or bucket name in git. Bucket = `sevadesk-tfstate-<account-id>` (from `aws_caller_identity`). Scripts read `TF_STATE_BUCKET` from the env. CI: variable `TF_STATE_BUCKET`, secret `AWS_ROLE_ARN`, and `mask-aws-account-id: true`.
- Laptop uses an AWS CLI profile `sevadesk-staging` (`role_arn` = deployer, `source_profile = default`, `region = ap-south-1`); scripts take `AWS_PROFILE` from the env.
- Bootstrap state stays local (gitignored). Commit both `.terraform.lock.hcl` files.
- Pin every new GitHub Action to an exact version, like `ci.yml`. `hashicorp/setup-terraform` with `terraform_version: 1.17.2`, `terraform_wrapper: false` (the wrapper breaks `terraform output -raw`).
- **All `terraform test` mocks:** `mock_provider "aws" { override_during = plan }` (same for `random`). Without it, mocked computed values are unknown at plan time and every assert on them fails. Set-typed blocks (`aws_lb_listener_rule.condition`, `path_pattern.values`, `aws_budgets_budget.notification`) are read with `one(...)`, `contains(...)` or `anytrue([for ...])`, never `[0]`.

## Review Focus

1. **Credits hide the spend** — with credits the net cost is $0, so a default budget never fires. Test in Task 1 (`budget_counts_real_cost`).
2. **Destroy leaves something billable, or the check cries wolf** (old INACTIVE task definitions keep tags; other projects' NATs/EIPs) → check only billable types, only `Project=sevadesk`. Tests in Task 4 (`test_check_clean_reports_leftovers`, `test_check_clean_passes_when_empty`, `test_check_clean_ignores_task_definitions`).
3. **The deployer role becomes an admin** (create a `sevadesk-staging-x` role with AdministratorAccess, then assume it) → boundary + PolicyARN + PassedToService conditions. Test in Task 1 (`deployer_cannot_make_admins`).
4. **A workflow, a fork PR, or another branch gets AWS access** → only `aws-staging.yml` has `id-token: write`, only `workflow_dispatch`, environment `aws-staging` limited to `main`; trust pins that environment. Tests in Task 1 (`trust_pins_the_environment`) and Task 5 (`test_only_aws_workflow_can_get_aws_tokens`).
5. **Database or cache open to the internet** → ingress only from the tasks SG, RDS not public. Test in Task 2 (`data_only_from_tasks`).

---

### Task 1: Bootstrap stack (state bucket, budget, deployer role, boundary)

**Files:**
- Delete: `infra/terraform/.gitkeep`
- Create: `infra/terraform/bootstrap/versions.tf`, `main.tf`, `iam.tf`, `variables.tf`, `outputs.tf`, `.terraform.lock.hcl`
- Create: `infra/terraform/bootstrap/tests/bootstrap.tftest.hcl`
- Modify: `.gitignore` (add `.terraform/`, `*.tfstate`, `*.tfstate.*`, `*.tfvars`)

**Interfaces:**
- Produces: outputs `state_bucket` (string), `deployer_role_arn` (string), `boundary_arn` (string). Resources `aws_s3_bucket.state`, `aws_budgets_budget.monthly`, `aws_iam_role.deployer`, `aws_iam_policy.deployer`, `aws_iam_policy.boundary`. Data `aws_iam_openid_connect_provider.github` (`url = "https://token.actions.githubusercontent.com"`).
- Variables: `budget_email` (string), `laptop_principal_arn` (string). No defaults.

- [ ] **Step 1: Upgrade the laptop to Terraform 1.17.2** (replace `C:\terraform\terraform.exe` from the HashiCorp download page). `terraform version` → `Terraform v1.17.2`.
- [ ] **Step 2: Write the failing test** `bootstrap.tftest.hcl`: `mock_provider "aws" { override_during = plan }`; `override_data` for `aws_caller_identity` (`account_id = "111122223333"`) and `aws_iam_openid_connect_provider.github` (`arn = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"`); `variables { budget_email = "test@example.com", laptop_principal_arn = "arn:aws:iam::111122223333:user/tester" }`; `command = plan` runs:
  - `budget_is_five_dollars`: `limit_amount == "5"`, `limit_unit == "USD"`, `time_unit == "MONTHLY"`; `anytrue([for n in notification : n.threshold == 100 && n.notification_type == "ACTUAL"])`.
  - `budget_counts_real_cost`: `one(cost_types).include_credit == false`.
  - `state_bucket_is_private_and_versioned`: bucket `== "sevadesk-tfstate-111122223333"`; versioning `Enabled`; all four public-access-block flags `true`.
  - `trust_pins_the_environment`: decoded `aws_iam_role.deployer.assume_role_policy` has the exact `sub` and `aud` from Global Constraints, and the laptop principal; no `"*"` principal.
  - `deployer_cannot_make_admins`: decoded `aws_iam_policy.deployer.policy` — the `iam:CreateRole` statement has condition `iam:PermissionsBoundary == aws_iam_policy.boundary.arn`; the `iam:AttachRolePolicy` statement pins `iam:PolicyARN` to the ECS execution policy; the `iam:PassRole` statement has `iam:PassedToService == "ecs-tasks.amazonaws.com"`; no statement has `Action == "*"` or `"iam:*"`.
- [ ] **Step 3: Run it to see it fail** — `terraform -chdir=infra/terraform/bootstrap init -backend=false && terraform -chdir=infra/terraform/bootstrap test` → FAIL (resources missing).
- [ ] **Step 4: Implement the stack.** `versions.tf`: `required_version = "~> 1.17"`, aws `~> 6.0`, region `ap-south-1`, default tags. `main.tf`: bucket + versioning + public access block + budget. `iam.tf`: OIDC data source, boundary policy, deployer policy, deployer role — all JSON via `jsonencode`, values from Global Constraints. Comment each statement in one plain line, plus the accepted-risk comment.
- [ ] **Step 5: Run the test** → all 5 runs PASS. `terraform fmt -check -recursive infra/terraform` → no output.
- [ ] **Step 6: Commit** — `feat(infra): bootstrap stack for state, $5 budget, bounded deployer role`.

### Task 2: Staging network and data (VPC, security groups, RDS, Valkey, secret)

**Files:**
- Create: `infra/terraform/staging/versions.tf`, `variables.tf`, `network.tf`, `data.tf`, `.terraform.lock.hcl`
- Create: `infra/terraform/staging/tests/network_data.tftest.hcl`

**Interfaces:**
- Produces: `aws_subnet.public` (count 2), `aws_security_group.alb`, `aws_security_group.tasks`, `aws_security_group.data`, `aws_secretsmanager_secret.database_url`, `local.redis_url` (`"redis://${primary_endpoint_address}:6379/0"`). Variables `image_tag` (string, no default), `boundary_arn` (string, no default; comes from env `TF_VAR_boundary_arn` — laptop shell or CI secret `BOUNDARY_ARN`).

- [ ] **Step 1: Write the failing test** (mocks per Global Constraints; `override_data` for `aws_availability_zones` → `names = ["ap-south-1a", "ap-south-1b"]`; `variables { image_tag = "abc123", boundary_arn = "arn:aws:iam::111122223333:policy/sevadesk-staging-boundary" }`; `command = plan`):
  - `two_public_subnets`: `length(aws_subnet.public) == 2`, both `map_public_ip_on_launch == true`, `aws_subnet.public[0].availability_zone != aws_subnet.public[1].availability_zone`.
  - `data_only_from_tasks`: the 5432 and 6379 ingress rules on the data SG have `referenced_security_group_id == aws_security_group.tasks.id` and `cidr_ipv4 == null`; `aws_db_instance.main.publicly_accessible == false`.
  - `tasks_only_from_alb`: the 3000 and 8000 ingress rules on the tasks SG reference `aws_security_group.alb.id`.
  - `destroy_really_deletes_data`: RDS `skip_final_snapshot == true`, `deletion_protection == false`, `backup_retention_period == 0`; secret `recovery_window_in_days == 0`.
  - `valkey_is_one_small_node`: replication group `engine == "valkey"`, `num_cache_clusters == 1`, `node_type == "cache.t4g.micro"`, `automatic_failover_enabled == false`.
- [ ] **Step 2: Run it to see it fail** (`init -backend=false`, `test`) → FAIL.
- [ ] **Step 3: Implement.** `versions.tf`: `backend "s3" { key = "staging/terraform.tfstate", region = "ap-south-1", use_lockfile = true }` (bucket from `-backend-config`). VPC `10.40.0.0/16`, IGW, route table `0.0.0.0/0` → IGW, 2 public subnets. One `aws_vpc_security_group_ingress_rule` / `_egress_rule` per rule. RDS `db.t4g.micro`, 20 GB gp3, db/user `seva`. Look up versions **with the deployer profile** (after Task 6 Part 1; until then use the bootstrap admin login): `aws rds describe-db-engine-versions --engine postgres --region ap-south-1 --query "DBEngineVersions[-1].EngineVersion"` → use major `18` if listed (same as Neon), else the newest; `aws elasticache describe-cache-engine-versions --engine valkey --region ap-south-1` → newest major (likely 8, not 9 like local; the parameter group family must match, e.g. `default.valkey8`). `transit_encryption_enabled = false` (private, SG-locked, plain `redis://` like the demo — comment it). Secret value = `DATABASE_URL` per Global Constraints.
- [ ] **Step 4: Run the test** → PASS. `terraform validate` → Success.
- [ ] **Step 5: Commit** — `feat(infra): staging network, RDS, Valkey, database secret`.

### Task 3: Staging app (ECS, ALB, IAM, logs, output URL)

**Files:**
- Create: `infra/terraform/staging/app.tf`, `outputs.tf`
- Create: `infra/terraform/staging/tests/app.tftest.hcl`

**Interfaces:**
- Consumes: Task 2 subnets, SGs, secret, `local.redis_url`, `var.image_tag`, `var.boundary_arn`.
- Produces: output `url` (string, `"http://${aws_lb.main.dns_name}"`). Names: cluster `sevadesk-staging`, services `sevadesk-staging-frontend|backend|worker`, execution role `sevadesk-staging-task-exec` with `permissions_boundary = var.boundary_arn`.

- [ ] **Step 1: Write the failing test** (same mocks and variables as Task 2):
  - `api_goes_to_backend`: `contains(one(one(aws_lb_listener_rule.api.condition).path_pattern).values, "/api/*")`; its forward target is the backend target group; the listener default action forwards to the frontend target group.
  - `same_images_as_demo`: `jsondecode(<backend task def>.container_definitions)[0].image == "ghcr.io/nithinmanayilghub/sevadesk-backend:abc123"`; worker same image; frontend `...sevadesk-frontend:abc123`.
  - `backend_migrates_before_start`: backend container definition has no `command` key (`!contains(keys(...), "command")`); worker `command == ["saq", "app.worker.settings"]`.
  - `secret_not_plain_env`: backend `secrets[0].name == "DATABASE_URL"`; no `environment` entry named `DATABASE_URL`.
  - `fargate_arm_small`: each task def `cpu == "256"`, `memory == "512"`, `one(runtime_platform).cpu_architecture == "ARM64"`; each service `wait_for_steady_state == true`.
  - `task_role_is_bounded`: execution role `permissions_boundary == var.boundary_arn`.
  - `logs_expire_fast`: log group `retention_in_days == 1`; ALB `enable_deletion_protection == false`.
- [ ] **Step 2: Run it to see it fail** → FAIL.
- [ ] **Step 3: Implement.** ALB in both public subnets, listener :80. Target groups `target_type = "ip"`: frontend port 3000 health `/`, backend port 8000 health `/api/health` (AR-22 is about Neon; RDS has no sleep). Execution role: managed `AmazonECSTaskExecutionRolePolicy` + inline `secretsmanager:GetSecretValue` on the one secret. `awslogs` driver to the one log group, stream prefix per service. Container Insights off (default). Services `depends_on` the listener; backend `health_check_grace_period_seconds = 60`.
- [ ] **Step 4: Run all staging tests** → PASS. `terraform validate` → Success. `terraform fmt -check -recursive infra/terraform` → clean.
- [ ] **Step 5: Commit** — `feat(infra): staging ECS services behind one ALB`.

### Task 4: The three scripts (deploy, destroy, check-clean)

**Files:**
- Create: `infra/terraform/deploy.sh`, `destroy.sh`, `check-clean.sh` (all `set -euo pipefail`, `AWS_REGION` defaults to `ap-south-1`, `cd "$(dirname "$0")"`)
- Test: `backend/tests/unit/test_aws_scripts.py` (fake `terraform`, `aws`, `curl` on PATH; each logs `"<name> <args>"` to `$CALLS_LOG`; fake output from env vars; reuse the pattern in `test_deploy_script.py`)

**Interfaces:**
- Env for deploy/destroy: `TF_STATE_BUCKET` and `TF_VAR_boundary_arn` (both required; missing → exit 2 before any call). `AWS_PROFILE` is passed through untouched.
- `deploy.sh <image-tag>`: calls, in order: `terraform -chdir=staging init -input=false -backend-config=bucket=$TF_STATE_BUCKET`, `terraform -chdir=staging apply -auto-approve -input=false -var image_tag=<tag>`, `terraform -chdir=staging output -raw url`, then `curl -fsS --retry 30 --retry-delay 10 --retry-all-errors <url>/api/v1/hello`; compares `.version` with `jq`. Prints `staging is live: <url>`.
- `destroy.sh`: init (same), `terraform -chdir=staging destroy -auto-approve -input=false -var image_tag=destroy`, then `./check-clean.sh`; its exit code is the result.
- `check-clean.sh`: in `ap-south-1`, one call: `aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=sevadesk Key=Environment,Values=staging --resource-type-filters rds elasticache elasticloadbalancing ec2:natgateway ec2:elastic-ip ec2:vpc secretsmanager ecs:service --query "ResourceTagMappingList[].ResourceARN" --output text`; plus direct `aws rds describe-db-instances` and `aws elasticache describe-replication-groups` filtered to ids starting `sevadesk-staging` (the two slow, costly ones; the tagging API can lag). Prints `LEFTOVER: <arn-or-id>` per item. Exit 0 + `clean: no billable staging resources` when none; exit 1 otherwise. Never looks at other projects' resources.

- [ ] **Step 1: Write the failing tests** (each with a one-line behaviour comment):
  - `test_deploy_needs_an_image_tag` → exit 2, no calls, stderr `usage: deploy.sh <image-tag>`.
  - `test_deploy_needs_the_state_bucket` → `TF_STATE_BUCKET` unset → exit 2, no calls.
  - `test_deploy_order` → calls are exactly init, apply (with `image_tag=abc123`), output, curl; stdout has `staging is live: http://fake-alb`.
  - `test_failed_apply_stops_before_check` → fake terraform fails on `apply` → exit 1, no `curl` call.
  - `test_deploy_fails_when_version_differs` → curl returns `{"version": "old"}` → exit 1, stderr names both versions.
  - `test_destroy_then_checks_clean` → calls end with destroy then the check; exit 0 when the check passes.
  - `test_check_clean_passes_when_empty` → all fake `aws` outputs empty → exit 0, `clean:` line.
  - `test_check_clean_reports_leftovers` → fake RDS output `sevadesk-staging-db` → exit 1, stdout `LEFTOVER: sevadesk-staging-db`.
  - `test_check_clean_ignores_task_definitions` → the tagging call's args include `--resource-type-filters` and do not include `ecs:task-definition`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_aws_scripts.py -q` (from `backend/`) → FAIL (scripts missing).
- [ ] **Step 3: Write the three scripts** with `--query ... --output text` on every `aws` call (no JSON parsing in bash except the one `jq` on hello). Comment every step in plain words.
- [ ] **Step 4: Run the tests** → 9 PASS. `git update-index --chmod=+x infra/terraform/*.sh`.
- [ ] **Step 5: Commit** — `feat(infra): one-command staging deploy, destroy and clean check`.

### Task 5: CI — Terraform checks on every PR, manual-approval staging workflow

**Files:**
- Modify: `.github/workflows/ci.yml` (lint job: `hashicorp/setup-terraform` + `terraform fmt -check -recursive infra/terraform`, and for `bootstrap` and `staging`: `init -backend=false` + `validate` + `test`)
- Create: `.github/workflows/aws-staging.yml`
- Test: `backend/tests/unit/test_aws_workflow.py`; extend `backend/tests/unit/test_ci_workflow.py` with `test_lint_runs_terraform_tests`

**Interfaces:**
- `aws-staging.yml`: `on: workflow_dispatch` only, inputs `action` (choice `deploy` | `destroy`, default `deploy`) and `image_tag` (string, optional; empty → `github.sha`). Top `permissions: contents: read, id-token: write`. `concurrency: { group: aws-staging, cancel-in-progress: false }`. One job `staging` with `environment: aws-staging` (approval gate, `main` only — set in Task 6 Part 2), steps: checkout, setup-terraform (Global Constraints), `aws-actions/configure-aws-credentials` (`role-to-assume: ${{ secrets.AWS_ROLE_ARN }}`, `aws-region: ap-south-1`, `mask-aws-account-id: true`), then `infra/terraform/deploy.sh <tag>` or `destroy.sh` with env `TF_STATE_BUCKET: ${{ vars.TF_STATE_BUCKET }}`, `TF_VAR_boundary_arn: ${{ secrets.BOUNDARY_ARN }}`.

- [ ] **Step 1: Write the failing tests:**
  - `test_staging_runs_only_by_hand` → `workflow_dispatch` is the only trigger.
  - `test_staging_waits_for_approval` → job has `environment: aws-staging`.
  - `test_only_aws_workflow_can_get_aws_tokens` → `id-token: write` appears in `aws-staging.yml` and in no other file under `.github/workflows/`.
  - `test_staging_uses_no_stored_aws_keys` → no `aws-access-key-id` / `AWS_SECRET_ACCESS_KEY` in any workflow; `mask-aws-account-id: true` present.
  - `test_staging_calls_the_same_scripts` → contains `infra/terraform/deploy.sh` and `infra/terraform/destroy.sh`.
  - `test_no_nat_gateway_in_terraform` → no `.tf` file under `infra/terraform` contains `aws_nat_gateway`.
  - `test_lint_runs_terraform_tests` → lint job contains `terraform fmt -check` and `terraform test` twice (bootstrap, staging).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Write `aws-staging.yml` and the lint steps** (comments in the `ci.yml` style).
- [ ] **Step 4: Run all unit tests + ruff** (`uv run pytest tests/unit -q`, `uv run ruff check .`, `uv run ruff format --check .`) → PASS.
- [ ] **Step 5: Commit** — `ci: terraform checks on PRs and a manual-approval aws-staging workflow`.

### Task 6: Runbook and live proof (user + me, ~1 h, costs < $1)

**Files:**
- Create: `infra/terraform/README.md`
- Modify: `ARCHITECTURE-SPINE.md` (AR-19/AR-20 + Deployment section: dispatched workflow with approval instead of a chained job — avoids a waiting approval on every merge; HTTP only; traces off on AWS, logs in CloudWatch; shared account with bounded deployer role)
- Create: `docs/learning/1-7.md`; modify `docs/learning/glossary.md`

- [ ] **Step 1: Write the runbook.** Parts:
  0. Check Billing → Credits and free-plan status. Note: the $5 budget covers the whole shared account.
  1. Bootstrap with an **admin login** (root is not used; an admin IAM user or SSO admin profile): `TF_VAR_budget_email=... TF_VAR_laptop_principal_arn=$(aws sts get-caller-identity --query Arn --output text) AWS_PROFILE=<admin> terraform apply` in `bootstrap/`. Then add the `[profile sevadesk-staging]` block to `~/.aws/config` and check `aws sts get-caller-identity --profile sevadesk-staging` shows the deployer role.
  2. GitHub, **before the PR merges**: environment `aws-staging` with Required reviewers = you and Deployment branches = `main` only; secrets `AWS_ROLE_ARN`, `BOUNDARY_ARN`; variable `TF_STATE_BUCKET`.
  3. Deploy from laptop. First run may fail once on a missing ECS service-linked role → run again.
  4. Deploy from CI (Actions → aws-staging → Run → Approve).
  5. Destroy + clean check.
  6. Cost table (~$0.12/hour: ALB, 3 small Fargate tasks, RDS micro, Valkey micro, public IPv4s) and "never leave it running".
  7. Anthropic: set the monthly spending limit in console.anthropic.com → Settings → Limits (no API for it).
- [ ] **Step 2: Live — bootstrap + GitHub setup** (Parts 1–2). Expected: `aws budgets describe-budgets` shows `5.0 USD`; deployer profile works; environment shows the reviewer rule.
- [ ] **Step 3: Live — laptop deploy.** `AWS_PROFILE=sevadesk-staging TF_STATE_BUCKET=... TF_VAR_boundary_arn=... infra/terraform/deploy.sh $(git rev-parse origin/main)`. Expected (~15 min): `staging is live: http://sevadesk-staging-...elb.amazonaws.com`; hello page shows; backend log in CloudWatch shows the migration line before uvicorn.
- [ ] **Step 4: Live — destroy.** `infra/terraform/destroy.sh` → `clean: no billable staging resources`, exit 0.
- [ ] **Step 5: Live — CI with approval** (after merge, so the workflow is on main): run action **destroy** only (user decision 2026-11-13: no second paid deploy), see it wait, approve, see OIDC login + `clean: no billable staging resources`. This proves the approval gate, the role trust, and the shared state at $0.
- [ ] **Step 6: Learning notes** `1-7.md` + glossary (Terraform state, OIDC, permissions boundary, ALB path routing, Fargate, security group, `terraform test` mocks).
- [ ] **Step 7: Commit** — `docs: AWS staging runbook, spine update, story 1.7 notes`.

### Task 7: Close the story

- [ ] Opus final review of the branch diff vs `main`; fix findings.
- [ ] Understanding Gate + hands-on task (CLAUDE.md).
- [ ] `sprint-status.yaml`: `1-7-...: done` inside the PR. Push → `gh pr create` → CI green → `gh pr merge --merge --delete-branch`.
- [ ] Task 6 Step 5 (CI approval proof). **Issue #7 stays open until it passes**, then close it. Update memory. Remind `/clear`.
