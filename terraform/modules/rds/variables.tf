variable "name" {
  description = "Name prefix for RDS resources."
  type        = string
}

variable "environment" {
  description = "Environment tag applied to every resource."
  type        = string
}

variable "vpc_id" {
  description = "VPC the database and its security group live in."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs the DB subnet group spans."
  type        = list(string)
}

variable "node_security_group_id" {
  description = "Security group of EKS worker nodes — the only ingress source allowed to the database."
  type        = string
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
}

variable "engine_version" {
  description = "PostgreSQL engine version."
  type        = string
}

variable "db_name" {
  description = "Name of the default database created on the instance."
  type        = string
}

variable "db_username" {
  description = "Master username. The master password is RDS-managed (Secrets Manager), never set here."
  type        = string
}
