variable "region" {
  type    = string
  default = "ap-south-1"
}
variable "availability_zone" {
  type    = string
  default = "ap-south-1a"
}
variable "instance_type" {
  type    = string
  default = "t3.large"
}
variable "ami_id" {
  type        = string
  description = "Pinned region-specific Amazon Linux 2023 x86_64 AMI with SSM Agent."
  validation {
    condition     = can(regex("^ami-[a-f0-9]+$", var.ami_id))
    error_message = "Set a valid AMI ID."
  }
}
variable "data_volume_gib" {
  type    = number
  default = 40
  validation {
    condition     = var.data_volume_gib >= 40
    error_message = "Set at least 40 GiB."
  }
}
variable "github_repository" {
  type        = string
  description = "GitHub OWNER/REPOSITORY in exact case."
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use OWNER/REPOSITORY."
  }
}
variable "github_oidc_provider_arn" {
  type        = string
  default     = null
  description = "Existing GitHub OIDC ARN if the account already has a provider."
}
variable "compose_version" {
  type        = string
  description = "Pinned Docker Compose Linux x86_64 release tag."
  validation {
    condition     = can(regex("^v[0-9]+[.][0-9]+[.][0-9]+$", var.compose_version))
    error_message = "Use vMAJOR.MINOR.PATCH."
  }
}
variable "compose_sha256" {
  type        = string
  description = "Published SHA-256 of the pinned docker-compose-linux-x86_64 asset."
  validation {
    condition     = can(regex("^[a-f0-9]{64}$", var.compose_sha256))
    error_message = "Use the exact lowercase SHA-256."
  }
}
variable "operations_email" {
  type        = string
  description = "Recipient for CloudWatch and budget alerts."
}
variable "monthly_budget_usd" {
  type        = number
  description = "Approved AWS Budget alert threshold in USD."
  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "Choose a positive monthly budget."
  }
}
