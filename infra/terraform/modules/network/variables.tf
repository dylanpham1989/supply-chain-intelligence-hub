variable "name" {
  description = "Prefix for every resource name in this module."
  type        = string
}

variable "region" {
  description = "AWS region, used for the S3 gateway endpoint service name."
  type        = string
}

variable "cidr_block" {
  description = "VPC CIDR. Needs room for 2 public and 2 private /20 subnets."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.cidr_block)) && tonumber(split("/", var.cidr_block)[1]) <= 20
    error_message = "cidr_block must be a valid CIDR of /20 or larger."
  }
}

variable "single_nat_gateway" {
  description = "One NAT gateway for the whole VPC. Cheaper, and a zone outage takes egress with it."
  type        = bool
  default     = true
}
