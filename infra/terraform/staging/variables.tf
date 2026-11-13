# No defaults: deploy.sh / destroy.sh (or the GitHub workflow) always pass them.

variable "image_tag" {
  description = "Full git commit SHA. CI built and pushed the GHCR images with this tag."
  type        = string
}

variable "boundary_arn" {
  description = "ARN of the sevadesk-staging-boundary policy (bootstrap output). Every role made here must carry it."
  type        = string
}

variable "cache_az" {
  description = "Zone for the one Valkey node. Change it (TF_VAR_cache_az) if AWS says this zone has no capacity."
  type        = string
  default     = "ap-south-1c"
}
