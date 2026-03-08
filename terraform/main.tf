provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  default = "us-east-1"
}

variable "cluster_name" {
  default = "arkashri-production-cluster"
}

data "aws_availability_zones" "available" {}

locals {
  name   = var.cluster_name
  vpc_cidr = "10.0.0.0/16"
  azs      = slice(data.aws_availability_zones.available.names, 0, 3)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${local.name}-vpc"
  cidr = local.vpc_cidr

  azs             = local.azs
  private_subnets = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 4, k)]
  public_subnets  = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 48)]

  enable_nat_gateway = true
  single_nat_gateway = true

  tags = {
    "kubernetes.io/cluster/${local.name}" = "shared"
  }

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = local.name
  cluster_version = "1.30"

  cluster_endpoint_public_access  = true
  
  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.private_subnets

  eks_managed_node_groups = {
    api_nodes = {
      min_size     = 3
      max_size     = 10
      desired_size = 3

      instance_types = ["m6i.large"]
      capacity_type  = "ON_DEMAND"
    }
    worker_nodes = {
      min_size     = 2
      max_size     = 20
      desired_size = 2
      
      instance_types = ["c6i.xlarge"]
      capacity_type  = "SPOT"
    }
  }

  enable_cluster_creator_admin_permissions = true
}

resource "aws_elasticache_subnet_group" "arkashri_redis" {
  name       = "${local.name}-redis-subnet"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "arkashri_redis" {
  replication_group_id          = "arkashri-prod-redis"
  description                   = "Redis cluster for Arkashri Risk Engine caching"
  node_type                     = "cache.r6g.large"
  port                          = 6379
  parameter_group_name          = "default.redis7.cluster.on"
  automatic_failover_enabled    = true
  multi_az_enabled              = true
  num_node_groups               = 2
  replicas_per_node_group       = 1
  subnet_group_name             = aws_elasticache_subnet_group.arkashri_redis.name
  security_group_ids            = [module.eks.node_security_group_id]
}

output "cluster_endpoint" {
  description = "Endpoint for EKS control plane."
  value       = module.eks.cluster_endpoint
}

output "redis_endpoint" {
  description = "Redis configuration endpoint"
  value       = aws_elasticache_replication_group.arkashri_redis.configuration_endpoint_address
}
