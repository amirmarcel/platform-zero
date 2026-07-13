output "cluster_role_arn" {
  description = "ARN of the IAM role assumed by the EKS control plane."
  value       = aws_iam_role.eks_cluster.arn
}

output "node_role_arn" {
  description = "ARN of the IAM role assumed by EKS worker nodes."
  value       = aws_iam_role.eks_node.arn
}
