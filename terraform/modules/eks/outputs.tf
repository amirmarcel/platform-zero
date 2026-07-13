output "cluster_name" {
  description = "Name of the EKS cluster."
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "API server endpoint of the EKS cluster (a Terraform-computed attribute, not a real, provisioned endpoint — this layer is never applied)."
  value       = aws_eks_cluster.this.endpoint
}

output "node_security_group_id" {
  description = "Security group ID attached to worker nodes."
  value       = aws_security_group.node.id
}
