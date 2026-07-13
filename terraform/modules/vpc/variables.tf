variable "name" {
  description = "Name prefix for VPC resources."
  type        = string
}

variable "environment" {
  description = "Environment tag applied to every resource."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
}

variable "availability_zones" {
  description = "Availability zones to spread public/private subnets across."
  type        = list(string)
}
