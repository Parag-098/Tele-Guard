terraform {
  required_version = ">= 1.9, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "TeleGuard"
      Environment = "production"
      ManagedBy   = "Terraform"
    }
  }
}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
