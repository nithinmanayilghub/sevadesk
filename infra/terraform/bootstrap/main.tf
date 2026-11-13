# The state bucket and the budget.

# Who we are logged in as. Gives the account ID without writing it in git.
data "aws_caller_identity" "current" {}

# --- Terraform state bucket ---
# Terraform's "state" is its memory of what it built. Staging keeps it here, so the laptop
# and GitHub Actions share one memory. It holds the database password, so it must stay private.
resource "aws_s3_bucket" "state" {
  # Bucket names are global across all of AWS; the account ID makes ours unique.
  bucket = "sevadesk-tfstate-${data.aws_caller_identity.current.account_id}"
}

# Keep old versions of the state file, so a bad write can be undone.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Nobody on the internet can read it. (S3 also encrypts every object by default, SSE-S3.)
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- $5 monthly budget ---
# It watches the WHOLE account (other projects share it), not only SevaDesk.
resource "aws_budgets_budget" "monthly" {
  name         = "sevadesk-monthly-5usd"
  budget_type  = "COST"
  limit_amount = "5"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Count the real cost. With credits counted, spend looks like $0 and the alert never fires.
  cost_types {
    include_credit = false
  }

  # Email when the real spend this month reaches 100% of $5.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}
