# Tests for the staging network and data parts. Fake AWS (mock provider): no AWS calls, no credentials.
mock_provider "aws" {
  override_during = plan
}

mock_provider "random" {
  override_during = plan
}

# Two zones (data centres) in Mumbai. The real list comes from AWS.
override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
  }
}

# Fixed security-group IDs, so the tests can check who is allowed to talk to whom.
override_resource {
  target          = aws_security_group.alb
  override_during = plan
  values = {
    id = "sg-alb"
  }
}

override_resource {
  target          = aws_security_group.tasks
  override_during = plan
  values = {
    id = "sg-tasks"
  }
}

override_resource {
  target          = aws_security_group.data
  override_during = plan
  values = {
    id = "sg-data"
  }
}

variables {
  image_tag    = "abc123"
  boundary_arn = "arn:aws:iam::111122223333:policy/sevadesk-staging-boundary"
}

# Behaviour: one public subnet in EVERY zone of the region. Small machine types sell out per zone;
# with a subnet everywhere, RDS can pick a zone that still has space (2026-11-13: only 1c had space).
run "public_subnets_in_every_zone" {
  command = plan

  assert {
    condition     = length(aws_subnet.public) == 3
    error_message = "There must be one public subnet per zone (3 in the test region)."
  }
  assert {
    condition     = length(distinct([for s in aws_subnet.public : s.availability_zone])) == 3
    error_message = "Each subnet must be in a different zone."
  }
  assert {
    condition     = alltrue([for s in aws_subnet.public : s.map_public_ip_on_launch])
    error_message = "Every subnet must give public IPs (no NAT gateway: tasks reach GHCR directly)."
  }
}

# Behaviour: Valkey does not pick a zone with space by itself, so we name one (default ap-south-1c).
run "cache_goes_to_the_chosen_zone" {
  command = plan

  assert {
    condition     = tolist(aws_elasticache_replication_group.main.preferred_cache_cluster_azs) == tolist(["ap-south-1c"])
    error_message = "The cache must go to var.cache_az (default ap-south-1c)."
  }
}

# Behaviour: only our app containers can reach Postgres and Valkey; the database has no public address.
run "data_only_from_tasks" {
  command = plan

  assert {
    condition = alltrue([
      for r in [aws_vpc_security_group_ingress_rule.data_postgres_from_tasks, aws_vpc_security_group_ingress_rule.data_valkey_from_tasks] :
      r.security_group_id == "sg-data" && r.referenced_security_group_id == "sg-tasks" && r.cidr_ipv4 == null
    ])
    error_message = "The data security group must accept traffic only from the tasks security group."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.data_postgres_from_tasks.from_port == 5432 && aws_vpc_security_group_ingress_rule.data_valkey_from_tasks.from_port == 6379
    error_message = "Postgres is port 5432, Valkey is port 6379."
  }
  assert {
    condition     = aws_db_instance.main.publicly_accessible == false
    error_message = "RDS must not be publicly accessible."
  }
}

# Behaviour: only the load balancer can reach the app containers (frontend 3000, backend 8000).
run "tasks_only_from_alb" {
  command = plan

  assert {
    condition = alltrue([
      for r in [aws_vpc_security_group_ingress_rule.tasks_frontend_from_alb, aws_vpc_security_group_ingress_rule.tasks_backend_from_alb] :
      r.security_group_id == "sg-tasks" && r.referenced_security_group_id == "sg-alb" && r.cidr_ipv4 == null
    ])
    error_message = "The tasks security group must accept traffic only from the ALB security group."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.tasks_frontend_from_alb.from_port == 3000 && aws_vpc_security_group_ingress_rule.tasks_backend_from_alb.from_port == 8000
    error_message = "Frontend is port 3000, backend is port 8000."
  }
}

# Behaviour: destroy really deletes the data parts (no snapshot left, no secret waiting 7-30 days).
run "destroy_really_deletes_data" {
  command = plan

  assert {
    condition     = aws_db_instance.main.skip_final_snapshot && !aws_db_instance.main.deletion_protection && aws_db_instance.main.backup_retention_period == 0
    error_message = "RDS: skip the final snapshot, no deletion protection, no backups."
  }
  assert {
    condition     = aws_secretsmanager_secret.database_url.recovery_window_in_days == 0
    error_message = "The secret must be deleted at once, not kept in a recovery window."
  }
}

# Behaviour: the cache is one small Valkey node (cheap; no second node, no failover).
run "valkey_is_one_small_node" {
  command = plan

  assert {
    condition     = aws_elasticache_replication_group.main.engine == "valkey" && aws_elasticache_replication_group.main.node_type == "cache.t4g.micro"
    error_message = "The cache must be Valkey on cache.t4g.micro."
  }
  assert {
    condition     = aws_elasticache_replication_group.main.num_cache_clusters == 1 && !aws_elasticache_replication_group.main.automatic_failover_enabled
    error_message = "The cache must be one node with no failover."
  }
}
