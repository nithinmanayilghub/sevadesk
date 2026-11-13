# Staging stack: created for a session, then destroyed. Run it only through deploy.sh / destroy.sh.
# Its state lives in the S3 bucket made by bootstrap/, so the laptop and GitHub Actions share it.
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # The bucket name holds the account ID, so it is not written here.
  # deploy.sh passes it: terraform init -backend-config=bucket=$TF_STATE_BUCKET
  # use_lockfile: a small lock file in S3 stops two runs from changing staging at the same time.
  backend "s3" {
    key          = "staging/terraform.tfstate"
    region       = "ap-south-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = "ap-south-1"

  # check-clean.sh finds leftovers by these tags.
  default_tags {
    tags = {
      Project     = "sevadesk"
      Environment = "staging"
    }
  }
}
