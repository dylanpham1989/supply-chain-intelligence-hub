variable "name" {
  type = string
}

variable "kms_key_arn" {
  type        = string
  description = "Customer managed key for envelope encryption of Kubernetes secrets."
}

variable "kubernetes_version" {
  type    = string
  default = "1.31"
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "api_allowed_cidrs" {
  type        = list(string)
  description = "Who may reach the public API server endpoint."
  default     = ["0.0.0.0/0"]
}

variable "instance_types" {
  type    = list(string)
  default = ["t3.large"]
}

variable "desired_size" {
  type    = number
  default = 2
}

variable "min_size" {
  type    = number
  default = 2
}

variable "max_size" {
  type    = number
  default = 5

  validation {
    condition     = var.max_size >= var.min_size
    error_message = "max_size cannot be below min_size."
  }
}
