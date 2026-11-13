# Values to copy into GitHub (and the laptop shell) after the first apply.
# They contain the account ID, so they go into GitHub secrets/variables, never into git.

output "state_bucket" {
  description = "GitHub variable TF_STATE_BUCKET / laptop env TF_STATE_BUCKET."
  value       = aws_s3_bucket.state.bucket
}

output "deployer_role_arn" {
  description = "GitHub secret AWS_ROLE_ARN / role_arn of the laptop profile sevadesk-staging."
  value       = aws_iam_role.deployer.arn
}

output "boundary_arn" {
  description = "GitHub secret BOUNDARY_ARN / laptop env TF_VAR_boundary_arn."
  value       = aws_iam_policy.boundary.arn
}
