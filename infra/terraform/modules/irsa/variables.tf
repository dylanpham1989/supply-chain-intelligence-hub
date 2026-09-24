variable "name" {
  type = string
}

variable "oidc_provider_arn" {
  type = string
}

variable "oidc_provider_url" {
  type        = string
  description = "Issuer without the https:// prefix."
}

variable "namespace" {
  type    = string
  default = "scih"
}

variable "service_account" {
  type    = string
  default = "scih"
}

variable "bucket_arn" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "secret_arns" {
  type        = list(string)
  description = "Secrets Manager entries the application may read."

  validation {
    condition     = length(var.secret_arns) > 0
    error_message = "Grant at least one secret, or drop the statement."
  }
}
