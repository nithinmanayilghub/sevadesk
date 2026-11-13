# Tests for the staging app part: ECS services, ALB routing, the execution role, logs.
# Fake AWS (mock provider): no AWS calls, no credentials.
mock_provider "aws" {
  override_during = plan
}

mock_provider "random" {
  override_during = plan
}

override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
  }
}

# Fixed values the checks below compare against (the fake's own values are unknown during plan).
override_resource {
  target          = aws_lb_target_group.frontend
  override_during = plan
  values = {
    arn = "arn:aws:elasticloadbalancing:ap-south-1:111122223333:targetgroup/sevadesk-staging-frontend/1"
  }
}

override_resource {
  target          = aws_lb_target_group.backend
  override_during = plan
  values = {
    arn = "arn:aws:elasticloadbalancing:ap-south-1:111122223333:targetgroup/sevadesk-staging-backend/2"
  }
}

override_resource {
  target          = aws_secretsmanager_secret.database_url
  override_during = plan
  values = {
    arn = "arn:aws:secretsmanager:ap-south-1:111122223333:secret:sevadesk-staging/database-url-AbCdEf"
  }
}

override_resource {
  target          = aws_elasticache_replication_group.main
  override_during = plan
  values = {
    primary_endpoint_address = "cache.example.internal"
  }
}

variables {
  image_tag    = "abc123"
  boundary_arn = "arn:aws:iam::111122223333:policy/sevadesk-staging-boundary"
}

# Behaviour: /api/* goes to FastAPI, everything else to Next.js (same rule as Caddy locally and on the demo).
run "api_goes_to_backend" {
  command = plan

  assert {
    condition     = contains(one(one(aws_lb_listener_rule.api.condition).path_pattern).values, "/api/*")
    error_message = "The listener rule must match /api/*."
  }
  assert {
    condition     = aws_lb_listener_rule.api.action[0].target_group_arn == aws_lb_target_group.backend.arn
    error_message = "/api/* must go to the backend target group."
  }
  assert {
    condition     = aws_lb_listener.http.default_action[0].target_group_arn == aws_lb_target_group.frontend.arn
    error_message = "Everything else must go to the frontend target group."
  }
}

# Behaviour: AWS runs the exact GHCR images CI built for this commit (no AWS-only build).
run "same_images_as_demo" {
  command = plan

  assert {
    condition     = jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].image == "ghcr.io/nithinmanayilghub/sevadesk-backend:abc123"
    error_message = "The backend must run the GHCR backend image for this commit."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.worker.container_definitions)[0].image == "ghcr.io/nithinmanayilghub/sevadesk-backend:abc123"
    error_message = "The worker must run the same backend image."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.frontend.container_definitions)[0].image == "ghcr.io/nithinmanayilghub/sevadesk-frontend:abc123"
    error_message = "The frontend must run the GHCR frontend image for this commit."
  }
}

# Behaviour: the backend keeps the image's own start command (alembic upgrade head, then uvicorn),
# so migrations always run before the API starts. The worker only swaps the command.
run "backend_migrates_before_start" {
  command = plan

  assert {
    condition     = !contains(keys(jsondecode(aws_ecs_task_definition.backend.container_definitions)[0]), "command")
    error_message = "The backend must not override the image command (it runs the migration first)."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.worker.container_definitions)[0].command == ["saq", "app.worker.settings"]
    error_message = "The worker must run the SAQ worker command."
  }
}

# Behaviour: DATABASE_URL (it holds the password) comes from Secrets Manager, never as plain env.
run "secret_not_plain_env" {
  command = plan

  assert {
    condition     = jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].secrets[0].name == "DATABASE_URL"
    error_message = "The backend must get DATABASE_URL from Secrets Manager."
  }
  assert {
    condition = alltrue([
      for td in [aws_ecs_task_definition.backend, aws_ecs_task_definition.worker] :
      !contains([for e in try(jsondecode(td.container_definitions)[0].environment, []) : e.name], "DATABASE_URL")
    ])
    error_message = "DATABASE_URL must never be a plain environment variable."
  }
}

# Behaviour: small, cheap ARM containers; Terraform waits until each service is healthy.
run "fargate_arm_small" {
  command = plan

  assert {
    condition = alltrue([
      for td in [aws_ecs_task_definition.frontend, aws_ecs_task_definition.backend, aws_ecs_task_definition.worker] :
      td.cpu == "256" && td.memory == "512" && one(td.runtime_platform).cpu_architecture == "ARM64"
    ])
    error_message = "Each task must be 0.25 vCPU, 512 MB, ARM64."
  }
  assert {
    condition = alltrue([
      for s in [aws_ecs_service.frontend, aws_ecs_service.backend, aws_ecs_service.worker] :
      s.wait_for_steady_state
    ])
    error_message = "Terraform must wait until every service is stable."
  }
}

# Behaviour: the role ECS uses to start containers carries the hard upper limit (permissions boundary).
run "task_role_is_bounded" {
  command = plan

  assert {
    condition     = aws_iam_role.task_exec.permissions_boundary == var.boundary_arn
    error_message = "The execution role must carry the boundary."
  }
}

# Behaviour: nothing blocks destroy, and logs do not pile up.
run "logs_expire_fast" {
  command = plan

  assert {
    condition     = aws_cloudwatch_log_group.main.retention_in_days == 1
    error_message = "Logs must be kept for 1 day only."
  }
  assert {
    condition     = aws_lb.main.enable_deletion_protection == false
    error_message = "The ALB must be deletable."
  }
}
