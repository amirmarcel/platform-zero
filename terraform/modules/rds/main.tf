# Reference RDS topology: a single PostgreSQL instance in the private
# subnets, reachable only from the EKS node security group. This models the
# data plane every tier-1/tier-2 service in docs/service-contract.md
# ultimately depends on — it is not a multi-instance or multi-AZ topology,
# which would be a scale decision made at apply time, not at reference-model
# time.

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name        = "${var.name}-db"
    Environment = var.environment
  }
}

resource "aws_security_group" "db" {
  name        = "${var.name}-db"
  description = "Security group for the RDS instance"
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.name}-db"
    Environment = var.environment
  }
}

resource "aws_security_group_rule" "db_ingress_from_nodes" {
  description              = "Allow Postgres from EKS worker nodes"
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.db.id
  source_security_group_id = var.node_security_group_id
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name}-db"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  db_name  = var.db_name
  username = var.db_username
  # No password field: RDS generates and stores the master password in
  # Secrets Manager, so no credential of any kind is set here or persisted
  # in this repository. See docs/service-contract.md's "no secrets" rule.
  manage_master_user_password = true

  allocated_storage      = 20
  storage_encrypted      = true
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]

  multi_az            = false
  publicly_accessible = false
  skip_final_snapshot = true

  tags = {
    Name        = "${var.name}-db"
    Environment = var.environment
  }
}
