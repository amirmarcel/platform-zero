# Reference EKS topology: one cluster spanning both public and private
# subnets (control plane ENIs need both, per the AWS EKS networking
# requirements), one managed node group running in the private subnets only,
# and a security group for the nodes that the RDS module opens ingress to —
# this is the mechanical link between the compute plane and the data plane
# in this reference topology.

resource "aws_eks_cluster" "this" {
  name     = var.name
  role_arn = var.cluster_role_arn

  vpc_config {
    subnet_ids = concat(var.public_subnet_ids, var.private_subnet_ids)
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_security_group" "node" {
  name        = "${var.name}-node"
  description = "Security group for EKS worker nodes"
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.name}-node"
    Environment = var.environment
  }
}

resource "aws_security_group_rule" "node_self_ingress" {
  description              = "Allow nodes to talk to each other"
  type                     = "ingress"
  from_port                = 0
  to_port                  = 0
  protocol                 = "-1"
  security_group_id        = aws_security_group.node.id
  source_security_group_id = aws_security_group.node.id
}

resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${var.name}-default"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = [var.node_instance_type]

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = 1
    max_size     = var.node_desired_size + 2
  }

  update_config {
    max_unavailable = 1
  }
}
