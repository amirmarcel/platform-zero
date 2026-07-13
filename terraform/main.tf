# Root module: wires the VPC, IAM, EKS, and RDS modules into the production
# topology this platform is designed to sit on. See terraform/README.md —
# this layer is validated and planned in CI, never applied.

module "vpc" {
  source = "./modules/vpc"

  name               = var.cluster_name
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}

module "iam" {
  source = "./modules/iam"

  name        = var.cluster_name
  environment = var.environment
}

module "eks" {
  source = "./modules/eks"

  name               = var.cluster_name
  environment        = var.environment
  cluster_role_arn   = module.iam.cluster_role_arn
  node_role_arn      = module.iam.node_role_arn
  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
  node_instance_type = var.node_instance_type
  node_desired_size  = var.node_desired_size
}

module "rds" {
  source = "./modules/rds"

  name                   = var.cluster_name
  environment            = var.environment
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnet_ids
  node_security_group_id = module.eks.node_security_group_id
  instance_class         = var.db_instance_class
  engine_version         = var.db_engine_version
  db_name                = var.db_name
  db_username            = var.db_username
}
