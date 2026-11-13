# The deployer role: the ONE identity that builds and destroys staging (from the laptop or GitHub).
# A role is a set of rights that a person or program borrows for a short time (no stored keys).
#
# Accepted risk: this AWS account is shared with other projects. The deployer can still change
# other projects' EC2/RDS/ECS/etc. resources in ap-south-1. It can NOT make an admin, and it can
# NOT touch IAM roles outside sevadesk-staging-*.

locals {
  # The only AWS-managed policy the deployer may attach (lets ECS pull images and write logs).
  ecs_execution_policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
  # Every role that the staging stack creates has a name with this prefix.
  staging_roles_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/sevadesk-staging-*"
}

# GitHub's login provider already exists in this account (another project made it).
# We only READ it, so a destroy here can never delete it.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# --- Permissions boundary: the hard upper limit for every role the staging stack creates ---
# Even if a role gets more rights attached, it can never do more than this.
# It names OUR staging secret and log group only. So even a role that escapes (for example one that
# trusts an outside account) can never read another project's secrets in this shared account.
# (No ECR: our images come from GHCR, so the ECR part of the managed ECS policy is simply cut off.)
resource "aws_iam_policy" "boundary" {
  name        = "sevadesk-staging-boundary"
  description = "Upper limit for SevaDesk staging task roles: the staging log group and the staging secrets."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "WriteStagingLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["arn:aws:logs:ap-south-1:${data.aws_caller_identity.current.account_id}:log-group:/ecs/sevadesk-staging:*"]
      },
      {
        Sid      = "ReadStagingSecrets"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = ["arn:aws:secretsmanager:ap-south-1:${data.aws_caller_identity.current.account_id}:secret:sevadesk-staging/*"]
      },
    ]
  })
}

# --- What the deployer may do ---
resource "aws_iam_policy" "deployer" {
  name        = "sevadesk-deployer"
  description = "Build and destroy SevaDesk staging in ap-south-1."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # The services staging is made of, in Mumbai only.
        Sid      = "StagingServicesInMumbai"
        Effect   = "Allow"
        Action   = ["ec2:*", "ecs:*", "elasticloadbalancing:*", "rds:*", "elasticache:*", "secretsmanager:*", "logs:*"]
        Resource = "*"
        Condition = {
          StringEquals = { "aws:RequestedRegion" = "ap-south-1" }
        }
      },
      {
        # Read and write the staging state file (and its lock file) in the state bucket.
        Sid      = "StateBucketList"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.state.arn
      },
      {
        Sid      = "StateObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.state.arn}/staging/*"
      },
      {
        # AWS makes a helper role per service the first time it is used (e.g. AWSServiceRoleForECS).
        Sid      = "ServiceLinkedRoles"
        Effect   = "Allow"
        Action   = ["iam:CreateServiceLinkedRole"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "iam:AWSServiceName" = [
              "ecs.amazonaws.com",
              "elasticloadbalancing.amazonaws.com",
              "rds.amazonaws.com",
              "elasticache.amazonaws.com",
            ]
          }
        }
      },
      {
        # Create staging roles and give them inline rights, but ONLY with the boundary on them.
        Sid      = "CreateBoundedRoles"
        Effect   = "Allow"
        Action   = ["iam:CreateRole", "iam:PutRolePolicy"]
        Resource = local.staging_roles_arn
        Condition = {
          StringEquals = { "iam:PermissionsBoundary" = aws_iam_policy.boundary.arn }
        }
      },
      {
        # Attach ONE managed policy (the ECS one), and only to a bounded staging role.
        Sid      = "AttachOnlyEcsExecutionPolicy"
        Effect   = "Allow"
        Action   = ["iam:AttachRolePolicy"]
        Resource = local.staging_roles_arn
        Condition = {
          StringEquals = {
            "iam:PolicyARN"           = local.ecs_execution_policy_arn
            "iam:PermissionsBoundary" = aws_iam_policy.boundary.arn
          }
        }
      },
      {
        # Clean up and tag staging roles (needed by destroy). None of these adds rights.
        Sid      = "ManageStagingRoles"
        Effect   = "Allow"
        Action   = ["iam:DeleteRole", "iam:TagRole", "iam:UntagRole", "iam:DeleteRolePolicy", "iam:DetachRolePolicy"]
        Resource = local.staging_roles_arn
      },
      {
        # Hand a staging role to ECS tasks, and to nothing else.
        Sid      = "PassStagingRolesToEcs"
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = local.staging_roles_arn
        Condition = {
          StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" }
        }
      },
      {
        # Read-only: Terraform reads roles and policies to compare them with the code.
        Sid      = "ReadIdentity"
        Effect   = "Allow"
        Action   = ["iam:Get*", "iam:List*", "sts:GetCallerIdentity"]
        Resource = "*"
      },
    ]
  })
}

# --- The role, and who may borrow it ---
# Not named sevadesk-staging-*: the deployer must not be able to change its own role.
resource "aws_iam_role" "deployer" {
  name                 = "sevadesk-deployer"
  description          = "Builds and destroys SevaDesk staging. Borrowed by GitHub (aws-staging env) and the laptop user."
  max_session_duration = 7200 # 2 hours: a deploy takes about 15 minutes
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # GitHub Actions, but only a job in environment aws-staging of this repo (that job waits for approval).
        Sid       = "GitHubAwsStagingEnvironment"
        Effect    = "Allow"
        Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
        Action    = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = "repo:nithinmanayilghub/sevadesk:environment:aws-staging"
          }
        }
      },
      {
        # The laptop user (profile sevadesk-staging in ~/.aws/config).
        Sid       = "LaptopUser"
        Effect    = "Allow"
        Principal = { AWS = var.laptop_principal_arn }
        Action    = "sts:AssumeRole"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "deployer" {
  role       = aws_iam_role.deployer.name
  policy_arn = aws_iam_policy.deployer.arn
}
