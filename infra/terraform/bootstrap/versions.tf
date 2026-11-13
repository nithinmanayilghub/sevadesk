# Bootstrap stack: made ONCE with an admin login, never destroyed.
# It holds what must outlive every staging session: the state bucket, the $5 budget, and the deployer role.
# Its own state stays on the laptop (gitignored): it is tiny and rarely changes.
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "ap-south-1"

  # Every resource made here gets these tags, so we can always find what belongs to SevaDesk.
  default_tags {
    tags = {
      Project     = "sevadesk"
      Environment = "bootstrap"
    }
  }
}
