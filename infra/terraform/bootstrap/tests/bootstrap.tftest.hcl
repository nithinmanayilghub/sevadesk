# Tests for the bootstrap stack. They use a fake AWS (mock provider): no AWS calls, no credentials.
# override_during = plan: the fake fills in computed values (ARNs, IDs) during plan,
# so the asserts below compare real strings, not "known after apply".
mock_provider "aws" {
  override_during = plan
}

# The real account ID and the existing GitHub login provider, replaced by fixed test values.
override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "111122223333"
  }
}

override_data {
  target = data.aws_iam_openid_connect_provider.github
  values = {
    arn = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
  }
}

# Fixed ARNs for resources the policies point at. (The fake's own random values are not valid ARNs.)
override_resource {
  target          = aws_iam_policy.boundary
  override_during = plan
  values = {
    arn = "arn:aws:iam::111122223333:policy/sevadesk-staging-boundary"
  }
}

override_resource {
  target          = aws_iam_policy.deployer
  override_during = plan
  values = {
    arn = "arn:aws:iam::111122223333:policy/sevadesk-deployer"
  }
}

override_resource {
  target          = aws_s3_bucket.state
  override_during = plan
  values = {
    arn = "arn:aws:s3:::sevadesk-tfstate-111122223333"
  }
}

variables {
  budget_email         = "test@example.com"
  laptop_principal_arn = "arn:aws:iam::111122223333:user/tester"
}

# Behaviour: the budget alert fires when the real monthly spend reaches $5.
run "budget_is_five_dollars" {
  command = plan

  assert {
    condition     = aws_budgets_budget.monthly.limit_amount == "5"
    error_message = "The budget limit must be 5."
  }
  assert {
    condition     = aws_budgets_budget.monthly.limit_unit == "USD" && aws_budgets_budget.monthly.time_unit == "MONTHLY"
    error_message = "The budget must be in USD per month."
  }
  assert {
    condition     = anytrue([for n in aws_budgets_budget.monthly.notification : n.threshold == 100 && n.notification_type == "ACTUAL"])
    error_message = "There must be an alert at 100% of the ACTUAL spend."
  }
}

# Behaviour: credits do not hide the spend (with credits counted, the cost looks like $0).
run "budget_counts_real_cost" {
  command = plan

  assert {
    condition     = one(aws_budgets_budget.monthly.cost_types).include_credit == false
    error_message = "The budget must ignore credits."
  }
}

# Behaviour: Terraform's state file (its memory, with the DB password) is private and keeps old versions.
run "state_bucket_is_private_and_versioned" {
  command = plan

  assert {
    condition     = aws_s3_bucket.state.bucket == "sevadesk-tfstate-111122223333"
    error_message = "The bucket name must be sevadesk-tfstate-<account-id>."
  }
  assert {
    condition     = one(aws_s3_bucket_versioning.state.versioning_configuration).status == "Enabled"
    error_message = "Bucket versioning must be on."
  }
  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.state.block_public_acls,
      aws_s3_bucket_public_access_block.state.block_public_policy,
      aws_s3_bucket_public_access_block.state.ignore_public_acls,
      aws_s3_bucket_public_access_block.state.restrict_public_buckets,
    ])
    error_message = "All four public-access blocks must be on."
  }
}

# Behaviour: only the aws-staging GitHub environment of this repo, and the laptop user, can borrow the role.
run "trust_pins_the_environment" {
  command = plan

  assert {
    condition = anytrue([
      for s in jsondecode(aws_iam_role.deployer.assume_role_policy).Statement :
      try(s.Condition.StringEquals["token.actions.githubusercontent.com:sub"], "") == "repo:nithinmanayilghub@71773426/sevadesk@1441590930:environment:aws-staging"
      && try(s.Condition.StringEquals["token.actions.githubusercontent.com:aud"], "") == "sts.amazonaws.com"
      && try(s.Principal.Federated, "") == "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
    ])
    error_message = "GitHub may assume the role only from environment aws-staging of nithinmanayilghub/sevadesk."
  }
  assert {
    condition = anytrue([
      for s in jsondecode(aws_iam_role.deployer.assume_role_policy).Statement :
      try(s.Principal.AWS, "") == "arn:aws:iam::111122223333:user/tester"
    ])
    error_message = "The laptop user must be able to assume the role."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role.deployer.assume_role_policy).Statement :
      s.Principal != "*" && !contains(try(values(s.Principal), []), "*")
    ])
    error_message = "No statement may trust everyone (*)."
  }
}

# Behaviour: the deployer can never make an admin. Every role it creates gets the hard limit
# (permissions boundary), it can attach only the ECS policy, and it can hand roles only to ECS tasks.
run "deployer_cannot_make_admins" {
  command = plan

  assert {
    condition = anytrue([
      for s in jsondecode(aws_iam_policy.deployer.policy).Statement :
      contains(flatten([s.Action]), "iam:CreateRole")
      && try(s.Condition.StringEquals["iam:PermissionsBoundary"], "") == aws_iam_policy.boundary.arn
    ])
    error_message = "iam:CreateRole must require the boundary."
  }
  assert {
    condition = anytrue([for s in jsondecode(aws_iam_policy.deployer.policy).Statement : contains(flatten([s.Action]), "iam:AttachRolePolicy")]) && alltrue([
      for s in jsondecode(aws_iam_policy.deployer.policy).Statement :
      try(s.Condition.StringEquals["iam:PolicyARN"], "") == "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
      if contains(flatten([s.Action]), "iam:AttachRolePolicy")
    ])
    error_message = "iam:AttachRolePolicy may attach only AmazonECSTaskExecutionRolePolicy."
  }
  assert {
    condition = anytrue([for s in jsondecode(aws_iam_policy.deployer.policy).Statement : contains(flatten([s.Action]), "iam:PassRole")]) && alltrue([
      for s in jsondecode(aws_iam_policy.deployer.policy).Statement :
      try(s.Condition.StringEquals["iam:PassedToService"], "") == "ecs-tasks.amazonaws.com"
      if contains(flatten([s.Action]), "iam:PassRole")
    ])
    error_message = "iam:PassRole may pass roles only to ECS tasks."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_policy.deployer.policy).Statement :
      !contains(flatten([s.Action]), "*") && !contains(flatten([s.Action]), "iam:*")
    ])
    error_message = "No statement may allow every action (* or iam:*)."
  }
}

# Behaviour (review 2026-11-13): the boundary fences roles in to OUR staging things only.
# A role that escapes (e.g. trusts an outside account) can then read only the staging secret,
# never another project's secrets in this shared account.
run "boundary_only_covers_staging" {
  command = plan

  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_policy.boundary.policy).Statement :
      !contains(flatten([s.Resource]), "*")
    ])
    error_message = "No boundary statement may cover every resource (*)."
  }
  assert {
    condition = anytrue([
      for s in jsondecode(aws_iam_policy.boundary.policy).Statement :
      contains(flatten([s.Action]), "secretsmanager:GetSecretValue")
      && flatten([s.Resource]) == ["arn:aws:secretsmanager:ap-south-1:111122223333:secret:sevadesk-staging/*"]
    ])
    error_message = "Secrets: only sevadesk-staging/* in ap-south-1."
  }
  assert {
    condition = anytrue([
      for s in jsondecode(aws_iam_policy.boundary.policy).Statement :
      contains(flatten([s.Action]), "logs:PutLogEvents")
      && flatten([s.Resource]) == ["arn:aws:logs:ap-south-1:111122223333:log-group:/ecs/sevadesk-staging:*"]
    ])
    error_message = "Logs: only the /ecs/sevadesk-staging log group in ap-south-1."
  }
}
