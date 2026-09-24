variable "name" {
  type        = string
  description = "Prefix for every resource name in this module."
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnets. The instance is never publicly accessible."

  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "RDS needs subnets in at least two availability zones."
  }
}

variable "client_security_group_id" {
  type        = string
  description = "Security group allowed to reach port 5432, normally the node group's."
}

variable "kms_key_arn" {
  type        = string
  description = "Customer managed key for storage encryption."
}

variable "engine_version" {
  type    = string
  default = "16.6"
}

variable "instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "allocated_storage" {
  type    = number
  default = 20
}

variable "database_name" {
  type    = string
  default = "scih"
}

variable "master_username" {
  type    = string
  default = "scih_owner"
}

variable "multi_az" {
  type        = bool
  default     = false
  description = "Doubles the instance cost. On for prod, off for staging."
}

variable "backup_retention_days" {
  type    = number
  default = 7

  validation {
    condition     = var.backup_retention_days >= 7
    error_message = "Keep at least a week of backups."
  }
}

variable "deletion_protection" {
  type    = bool
  default = true
}
