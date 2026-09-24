variable "environment" {
  type    = string
  default = "staging"

  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be staging or prod."
  }
}

variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "account_id" {
  type        = string
  description = "Used to scope the Secrets Manager ARNs the application may read."

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be 12 digits."
  }
}

variable "cidr_block" {
  type    = string
  default = "10.20.0.0/16"
}

variable "kubernetes_version" {
  type    = string
  default = "1.31"
}

variable "api_allowed_cidrs" {
  type        = list(string)
  description = "Addresses allowed to reach the Kubernetes API server."
  default     = ["0.0.0.0/0"]
}
