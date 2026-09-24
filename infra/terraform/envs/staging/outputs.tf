output "cluster_name" {
  value = module.eks.cluster_name
}

output "database_endpoint" {
  value = module.database.endpoint
}

output "cache_endpoint" {
  value = module.cache.endpoint
}

output "documents_bucket" {
  value = module.documents.bucket_name
}

output "app_role_arn" {
  description = "Put this on the scih ServiceAccount in the staging overlay."
  value       = module.app_identity.role_arn
}
