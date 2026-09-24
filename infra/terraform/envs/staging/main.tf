locals {
  name = "scih-${var.environment}"
}

# One customer managed key for the documents bucket and the database. An AWS
# managed key cannot be given a rotation policy or a key policy of its own.
resource "aws_kms_key" "this" {
  description             = "${local.name} data at rest"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  # Written out rather than left to the default, so that adding a grant later is
  # an edit to something visible instead of a console click nobody records.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountAdministration"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid    = "ServiceUse"
        Effect = "Allow"
        Principal = {
          Service = [
            "logs.${var.region}.amazonaws.com",
            "rds.amazonaws.com",
            "elasticache.amazonaws.com",
            "s3.amazonaws.com",
          ]
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_kms_alias" "this" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.this.key_id
}

module "network" {
  source = "../../modules/network"

  name        = local.name
  region      = var.region
  cidr_block  = var.cidr_block
  kms_key_arn = aws_kms_key.this.arn
  # Staging pays for one. Prod passes false and gets one per zone.
  single_nat_gateway = true
}

module "eks" {
  source = "../../modules/eks"

  name               = local.name
  kms_key_arn        = aws_kms_key.this.arn
  kubernetes_version = var.kubernetes_version
  private_subnet_ids = module.network.private_subnet_ids
  public_subnet_ids  = module.network.public_subnet_ids
  api_allowed_cidrs  = var.api_allowed_cidrs
  instance_types     = ["t3.large"]
  desired_size       = 2
  min_size           = 2
  max_size           = 4
}

module "documents" {
  source = "../../modules/s3"

  bucket_name = "${local.name}-documents"
  kms_key_arn = aws_kms_key.this.arn
}

module "database" {
  source = "../../modules/rds"

  name                     = local.name
  vpc_id                   = module.network.vpc_id
  subnet_ids               = module.network.private_subnet_ids
  client_security_group_id = module.eks.node_security_group_id
  kms_key_arn              = aws_kms_key.this.arn
  instance_class           = "db.t4g.medium"
  multi_az                 = false
  deletion_protection      = true
}

module "cache" {
  source = "../../modules/elasticache"

  name                     = local.name
  vpc_id                   = module.network.vpc_id
  subnet_ids               = module.network.private_subnet_ids
  client_security_group_id = module.eks.node_security_group_id
  kms_key_arn              = aws_kms_key.this.arn
  node_type                = "cache.t4g.micro"
  replica_count            = 0
}

module "app_identity" {
  source = "../../modules/irsa"

  name              = local.name
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider_url = module.eks.oidc_provider_url
  bucket_arn        = module.documents.bucket_arn
  kms_key_arn       = aws_kms_key.this.arn
  secret_arns = [
    "arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:scih/${var.environment}/*",
    module.database.master_secret_arn,
  ]
}
