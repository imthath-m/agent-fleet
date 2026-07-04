output "tool_backend_url" {
  description = "HTTPS URL of the Cloud Run tool backend."
  value       = google_cloud_run_v2_service.tool_backend.uri
}

output "agent_staging_bucket" {
  description = "GCS bucket used to stage the deployed agent package."
  value       = google_storage_bucket.agent_staging.name
}
