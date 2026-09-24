resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name}-redis"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "this" {
  name        = "${var.name}-redis"
  description = "Redis access for the cluster nodes"
  vpc_id      = var.vpc_id

  tags = { Name = "${var.name}-redis" }
}

resource "aws_vpc_security_group_ingress_rule" "from_nodes" {
  security_group_id            = aws_security_group.this.id
  referenced_security_group_id = var.client_security_group_id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
  description                  = "Redis from the EKS nodes"
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "${var.name}-redis"
  description          = "Cache and job queue for ${var.name}"

  engine         = "redis"
  engine_version = var.engine_version
  node_type      = var.node_type
  port           = 6379

  num_cache_clusters         = var.replica_count + 1
  automatic_failover_enabled = var.replica_count > 0
  multi_az_enabled           = var.replica_count > 0

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.this.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  # The cache is rebuildable, but the arq queue is not: a job lost here is a
  # document that never gets indexed.
  snapshot_retention_limit = 1
  maintenance_window       = "sun:05:00-sun:06:00"
  apply_immediately        = false
}
