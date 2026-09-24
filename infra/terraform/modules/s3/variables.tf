variable "bucket_name" {
  type        = string
  description = "Globally unique bucket name."
}

variable "kms_key_arn" {
  type        = string
  description = "Customer managed key for server side encryption."
}
