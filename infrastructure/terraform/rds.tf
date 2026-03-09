resource "aws_db_instance" "arkashri_postgres" {
  identifier        = "arkashri-production-db"
  engine            = "postgres"
  engine_version    = "15.4"
  instance_class    = "db.r6g.large"
  allocated_storage = 100
  storage_type      = "gp3"

  username = var.db_username
  password = var.db_password

  vpc_security_group_ids = [aws_security_group.db_sg.id]
  db_subnet_group_name   = aws_db_subnet_group.db_subnet_group.name

  multi_az               = true
  storage_encrypted      = true
  publicly_accessible    = false
  skip_final_snapshot    = false
  backup_retention_period = 30 # Point-in-time recovery for 30 days
  
  performance_insights_enabled = true

  tags = {
    Name        = "arkashri-production-db"
    Environment = "production"
  }
}

resource "aws_elasticache_cluster" "arkashri_redis" {
  cluster_id           = "arkashri-production-redis"
  engine               = "redis"
  node_type            = "cache.m6g.large"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.0"
  port                 = 6379

  subnet_group_name    = aws_elasticache_subnet_group.redis_subnet_group.name
}
