provider "aws" {
  region = var.aws_region
}

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# VPC Configuration
resource "aws_vpc" "arkashri_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "arkashri-production-vpc"
    Environment = "production"
  }
}

# Immutable Evidence Storage (WORM)
resource "aws_s3_bucket" "evidence_vault" {
  bucket = var.s3_bucket_name
}

resource "aws_s3_bucket_object_lock_configuration" "evidence_vault_lock" {
  bucket = aws_s3_bucket.evidence_vault.id

  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = 7
    }
  }
}

resource "aws_s3_bucket_public_access_block" "evidence_vault_public_access_block" {
  bucket = aws_s3_bucket.evidence_vault.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence_vault_encryption" {
  bucket = aws_s3_bucket.evidence_vault.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
