variable "region" {
  description = "AWS region for the reference topology. A placeholder, not a claim of a deployed environment."
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Environment name, used to tag and namespace resources."
  type        = string
  default     = "production"
}

variable "cluster_name" {
  description = "Name of the EKS cluster."
  type        = string
  default     = "platform-zero"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones the VPC's subnets are spread across."
  type        = list(string)
  default     = ["us-west-2a", "us-west-2b"]
}

variable "node_instance_type" {
  description = "EC2 instance type for the EKS managed node group."
  type        = string
  default     = "t3.medium"
}

variable "node_desired_size" {
  description = "Desired number of worker nodes."
  type        = number
  default     = 2
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.medium"
}

variable "db_engine_version" {
  description = "PostgreSQL engine version for RDS."
  type        = string
  default     = "16.4"
}

variable "db_name" {
  description = "Name of the default database created on the RDS instance."
  type        = string
  default     = "platform"
}

variable "db_username" {
  description = "Master username for the RDS instance. The master password is never set here — RDS-managed master password (Secrets Manager) is used instead, so no credential of any kind lives in this repository."
  type        = string
  default     = "platform_admin"
}
