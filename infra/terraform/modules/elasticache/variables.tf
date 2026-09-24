variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "client_security_group_id" {
  type = string
}

variable "kms_key_arn" {
  type        = string
  description = "Customer managed key for encryption at rest."
}

variable "engine_version" {
  type    = string
  default = "7.1"
}

variable "node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "replica_count" {
  type        = number
  default     = 0
  description = "Replicas beyond the primary. Above zero turns on failover and multi-AZ."

  validation {
    condition     = var.replica_count >= 0 && var.replica_count <= 5
    error_message = "replica_count must be between 0 and 5."
  }
}
