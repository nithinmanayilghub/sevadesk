# The app: one load balancer (ALB) in front, three ECS Fargate services behind it, and their logs.
# Fargate = AWS runs our containers; we never manage a server.
#
#   browser --> ALB :80 --/api/*--> backend (FastAPI :8000)
#                        --else---> frontend (Next.js :3000)
#   worker (SAQ): no traffic in; it reads jobs from Valkey.

locals {
  backend_image  = "ghcr.io/nithinmanayilghub/sevadesk-backend:${var.image_tag}" # backend AND worker
  frontend_image = "ghcr.io/nithinmanayilghub/sevadesk-frontend:${var.image_tag}"

  # Same settings for the backend and the worker (like the x-backend block in the demo compose file).
  # No OTEL_EXPORTER_OTLP_ENDPOINT: traces are off on AWS. JSON logs go to CloudWatch.
  backend_environment = [{ name = "REDIS_URL", value = local.redis_url }]
  backend_secrets     = [{ name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn }]
}

# --- Logs ---
# Every container writes its stdout here. Kept 1 day: staging is short-lived.
resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/sevadesk-staging"
  retention_in_days = 1
}

# How each container sends its logs (one log stream prefix per service).
locals {
  log_options = {
    for svc in ["frontend", "backend", "worker"] : svc => {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.main.name
        "awslogs-region"        = "ap-south-1"
        "awslogs-stream-prefix" = svc
      }
    }
  }
}

# --- Execution role: what ECS itself needs to START our containers ---
# (write logs, read the DATABASE_URL secret). The containers get no AWS rights of their own.
resource "aws_iam_role" "task_exec" {
  name                 = "sevadesk-staging-task-exec"
  permissions_boundary = var.boundary_arn # the hard upper limit; the deployer can only create bounded roles
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "task_exec" {
  role       = aws_iam_role.task_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "task_exec_secret" {
  name = "read-database-url"
  role = aws_iam_role.task_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = aws_secretsmanager_secret.database_url.arn
    }]
  })
}

# --- Load balancer ---
resource "aws_lb" "main" {
  name                       = "sevadesk-staging"
  load_balancer_type         = "application"
  internal                   = false
  security_groups            = [aws_security_group.alb.id]
  subnets                    = aws_subnet.public[*].id
  enable_deletion_protection = false
}

# A target group is the list of containers the ALB may send requests to, plus how it checks they are alive.
resource "aws_lb_target_group" "frontend" {
  name                 = "sevadesk-staging-frontend"
  port                 = 3000
  protocol             = "HTTP"
  target_type          = "ip" # Fargate containers have their own IP address
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 5 # staging: do not wait 5 minutes for old connections
  health_check {
    path = "/"
  }
}

resource "aws_lb_target_group" "backend" {
  name                 = "sevadesk-staging-backend"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 5
  health_check {
    # Checks the database too. Fine on RDS (it never sleeps). The demo avoids this because Neon sleeps.
    path = "/api/health"
  }
}

# Port 80 (HTTP only: no domain name, so no TLS certificate). Default: send to the frontend.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

# /api/* goes to the backend instead.
resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10
  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# --- ECS ---
resource "aws_ecs_cluster" "main" {
  name = "sevadesk-staging"
}

# A task definition is the recipe for one container: image, size, ports, settings, logs.
resource "aws_ecs_task_definition" "frontend" {
  family                   = "sevadesk-staging-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256" # 0.25 vCPU
  memory                   = "512" # MB
  execution_role_arn       = aws_iam_role.task_exec.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64" # about 20% cheaper; CI builds arm64 images too
  }
  container_definitions = jsonencode([{
    name             = "frontend"
    image            = local.frontend_image
    essential        = true
    portMappings     = [{ containerPort = 3000 }]
    logConfiguration = local.log_options.frontend
  }])
}

# No "command": the image's own CMD runs "alembic upgrade head" first, then starts uvicorn.
# So migrations always finish before the API takes traffic.
resource "aws_ecs_task_definition" "backend" {
  family                   = "sevadesk-staging-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_exec.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode([{
    name             = "backend"
    image            = local.backend_image
    essential        = true
    portMappings     = [{ containerPort = 8000 }]
    environment      = local.backend_environment
    secrets          = local.backend_secrets
    logConfiguration = local.log_options.backend
  }])
}

# Same image as the backend; only the command differs (like the demo compose file).
resource "aws_ecs_task_definition" "worker" {
  family                   = "sevadesk-staging-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_exec.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode([{
    name             = "worker"
    image            = local.backend_image
    essential        = true
    command          = ["saq", "app.worker.settings"]
    environment      = local.backend_environment
    secrets          = local.backend_secrets
    logConfiguration = local.log_options.worker
  }])
}

# A service keeps one copy of a task running, and restarts it if it dies.
# wait_for_steady_state: "terraform apply" waits until the task is running and healthy.
resource "aws_ecs_service" "frontend" {
  name                  = "sevadesk-staging-frontend"
  cluster               = aws_ecs_cluster.main.id
  task_definition       = aws_ecs_task_definition.frontend.arn
  desired_count         = 1
  launch_type           = "FARGATE"
  wait_for_steady_state = true
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true # no NAT gateway: a public IP lets the task pull from GHCR
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }
  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "backend" {
  name                  = "sevadesk-staging-backend"
  cluster               = aws_ecs_cluster.main.id
  task_definition       = aws_ecs_task_definition.backend.arn
  desired_count         = 1
  launch_type           = "FARGATE"
  wait_for_steady_state = true
  # The migration runs before uvicorn starts; give it time before health checks count.
  health_check_grace_period_seconds = 60
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }
  depends_on = [aws_lb_listener_rule.api, aws_secretsmanager_secret_version.database_url]
}

resource "aws_ecs_service" "worker" {
  name                  = "sevadesk-staging-worker"
  cluster               = aws_ecs_cluster.main.id
  task_definition       = aws_ecs_task_definition.worker.arn
  desired_count         = 1
  launch_type           = "FARGATE"
  wait_for_steady_state = true
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }
  # Start after the backend, so the database is already migrated.
  depends_on = [aws_ecs_service.backend]
}
