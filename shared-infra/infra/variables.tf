variable "project_id" {
  type        = string
  description = "GCP project ID for the target environment (dev/staging/prod)."
}

variable "region" {
  type        = string
  description = "Default region for regional resources."
  default     = "us-central1"
}

variable "environment" {
  type        = string
  description = "Deployment environment name."
  default     = "dev"
}

variable "tool_backend_image" {
  type        = string
  description = "Container image for the Cloud Run tool backend (spine.tool_backend)."
  default     = "gcr.io/cloudrun/placeholder"
}
