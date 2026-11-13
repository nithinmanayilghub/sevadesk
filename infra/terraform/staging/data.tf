# The data stores: RDS Postgres, ElastiCache Valkey, and the DATABASE_URL secret.
# Everything here is set to be REALLY deleted by destroy: no snapshot, no backups, no secret recovery window.

# --- Postgres (RDS) ---
# The password is made by Terraform. It is stored in the S3 state (private, encrypted, versioned)
# and in Secrets Manager. No special characters, so it is safe inside a URL.
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "sevadesk-staging"
  subnet_ids = aws_subnet.public[*].id
}

resource "aws_db_instance" "main" {
  identifier     = "sevadesk-staging-db"
  engine         = "postgres"
  engine_version = "18" # same major version as Neon (demo) and local; RDS picks the newest 18.x
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"

  db_name  = "seva"
  username = "seva"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.data.id]
  publicly_accessible    = false # in a public subnet, but no public address; only the tasks SG can reach it

  # Staging is thrown away after each session.
  skip_final_snapshot     = true
  deletion_protection     = false
  backup_retention_period = 0
  apply_immediately       = true
}

# --- Valkey (ElastiCache) ---
resource "aws_elasticache_subnet_group" "main" {
  name       = "sevadesk-staging"
  subnet_ids = aws_subnet.public[*].id
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "sevadesk-staging-cache"
  description          = "SevaDesk staging job queue (SAQ)"
  engine               = "valkey"
  engine_version       = "9.0" # same as local and the demo (valkey/valkey:9.0); offered in ap-south-1 (checked 2026-11-13)
  node_type            = "cache.t4g.micro"
  port                 = 6379

  num_cache_clusters = 1 # one node: no replica, so no failover
  # Valkey does not look for a zone with space by itself (2026-11-13: it chose 1b, which was full).
  preferred_cache_cluster_azs = [var.cache_az]
  automatic_failover_enabled  = false

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.data.id]

  # Plain redis:// like the demo. The cache has no public address and only the tasks SG can reach it.
  transit_encryption_enabled = false
  at_rest_encryption_enabled = true # free

  snapshot_retention_limit = 0
  apply_immediately        = true
}

locals {
  redis_url = "redis://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
}

# --- DATABASE_URL secret ---
# The backend and worker read it at start (ECS "secrets"), so it never appears as plain env.
resource "aws_secretsmanager_secret" "database_url" {
  name                    = "sevadesk-staging/database-url"
  recovery_window_in_days = 0 # delete at once on destroy; the name is free again for the next deploy
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  # sslmode=require: RDS Postgres refuses connections without TLS (rds.force_ssl).
  secret_string = "postgresql+psycopg://seva:${random_password.db.result}@${aws_db_instance.main.address}:5432/seva?sslmode=require"
}
