terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
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

resource "aws_s3_bucket" "env" {
  for_each = toset(var.environments)
  bucket   = "${var.student}-capstone-${each.key}"
}

resource "aws_security_group" "api" {
  name        = "${var.student}-capstone-api"
  description = "capstone api"

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

# IAM Role for Lambda
resource "aws_iam_role" "lambda_exec" {
  name = "${var.student}-capstone-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Zip the Lambda handler
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/handler.py"
  output_path = "${path.module}/handler.zip"
}

# Lambda Function
resource "aws_lambda_function" "ingest" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${var.student}-capstone-ingest"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
}

# Lambda Permission for S3 invocation
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.env["dev"].arn
}

# S3 Bucket Notification on dev bucket
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.env["dev"].id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingest.arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.allow_s3]
}

output "buckets" { value = [for b in aws_s3_bucket.env : b.bucket] }
output "lambda_arn" { value = aws_lambda_function.ingest.arn }
