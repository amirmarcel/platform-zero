variable "name" {
  description = "Name of the EKS cluster."
  type        = string
}

variable "environment" {
  description = "Environment tag applied to every resource."
  type        = string
}

variable "cluster_role_arn" {
  description = "IAM role ARN assumed by the EKS control plane."
  type        = string
}

variable "node_role_arn" {
  description = "IAM role ARN assumed by EKS worker nodes."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs the cluster control plane is reachable from."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs the worker nodes run in."
  type        = list(string)
}

variable "vpc_id" {
  description = "VPC the cluster and its node security group live in."
  type        = string
}

variable "node_instance_type" {
  description = "EC2 instance type for the managed node group."
  type        = string
}

variable "node_desired_size" {
  description = "Desired number of worker nodes."
  type        = number
}
