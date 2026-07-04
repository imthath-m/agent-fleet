# Phase 1 runtime skeleton (placeholders).
#
# These resources represent the two runtime targets from the plan:
#   - Vertex AI Agent Engine  -> managed runtime for the stateful "hello" agent
#   - Cloud Run               -> stateless HTTP tool backend (spine.tool_backend)
#
# This file is intentionally minimal and cannot be applied in the sandbox
# (no GCP credentials, no terraform binary). It documents intended shape.

# --- Cloud Run: tool backend ------------------------------------------------

resource "google_cloud_run_v2_service" "tool_backend" {
  name     = "spine-tool-backend-${var.environment}"
  location = var.region

  template {
    containers {
      image = var.tool_backend_image

      ports {
        container_port = 8080
      }
    }
  }
}

# --- Vertex AI Agent Engine: hello agent runtime ----------------------------
#
# Placeholder. The Agent Engine resource is provisioned once the provider
# surface is finalized; for now we reserve the artifact bucket the deployed
# agent package is staged into.

resource "google_storage_bucket" "agent_staging" {
  name          = "${var.project_id}-spine-agent-staging"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
}
