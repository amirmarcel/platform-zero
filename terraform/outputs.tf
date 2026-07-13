output "vpc_id" {
  description = "ID of the reference VPC."
  value       = module.vpc.vpc_id
}

output "cluster_name" {
  description = "Name of the reference EKS cluster."
  value       = module.eks.cluster_name
}

output "db_instance_id" {
  description = "Identifier of the reference RDS instance."
  value       = module.rds.db_instance_id
}
