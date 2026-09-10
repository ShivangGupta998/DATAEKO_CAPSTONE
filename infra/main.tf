terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

# Everything points at LocalStack. No real AWS account, no real money.
provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  # Without this, Terraform addresses buckets as http://<bucket>.localhost:4566
  # which never resolves, and apply hangs instead of failing.
  s3_use_path_style = true

  endpoints {
    s3     = "http://localhost:4566"
    lambda = "http://localhost:4566"
    iam    = "http://localhost:4566"
    ec2    = "http://localhost:4566"
    logs   = "http://localhost:4566"
  }
}

variable "student" {
  type        = string
  description = "your github username, lowercase"
}

variable "environments" {
  type    = list(string)
  default = ["dev", "staging", "prod"]
}

# DEFECT: count over a list. Remove the middle environment and read the plan.
# Today's session measured exactly what this does.
resource "aws_s3_bucket" "env" {
  count  = length(var.environments)
  bucket = "${var.student}-capstone-${var.environments[count.index]}"
}

resource "aws_security_group" "api" {
  name        = "${var.student}-capstone-api"
  description = "capstone api"

  # DEFECT: the whole internet can reach SSH on this box.
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

output "buckets" { value = aws_s3_bucket.env[*].bucket }
