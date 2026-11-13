# Personal values. They have no default and are never committed:
# pass them as environment variables (TF_VAR_budget_email, TF_VAR_laptop_principal_arn).

variable "budget_email" {
  description = "Email address that gets the $5 budget alert."
  type        = string
}

variable "laptop_principal_arn" {
  description = "ARN of the laptop IAM user that may assume the deployer role (aws sts get-caller-identity)."
  type        = string
}
