terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.region

  # Set once here rather than copied onto every resource. A resource that has
  # to remember its own tags is a resource that will eventually forget.
  default_tags {
    tags = {
      Project     = "scih"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
