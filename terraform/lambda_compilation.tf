# Compilation Lambda Functions
# Handles /api/compilers/{compiler_id}/compile and /api/compilers/{compiler_id}/cmake endpoints

# Get compilation lambda package from S3
data "aws_s3_object" "compilation_lambda_zip" {
  bucket = aws_s3_bucket.compiler-explorer.bucket
  key    = "lambdas/compilation-lambda-package.zip"
}

data "aws_s3_object" "compilation_lambda_zip_sha" {
  bucket = aws_s3_bucket.compiler-explorer.bucket
  key    = "lambdas/compilation-lambda-package.zip.sha256"
}

# Lambda function for Beta environment
resource "aws_lambda_function" "compilation_beta" {
  description       = "Handle compilation requests for beta environment"
  s3_bucket         = data.aws_s3_object.compilation_lambda_zip.bucket
  s3_key            = data.aws_s3_object.compilation_lambda_zip.key
  s3_object_version = data.aws_s3_object.compilation_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.compilation_lambda_zip_sha.body)
  function_name     = "compilation-beta"
  role              = aws_iam_role.iam_for_lambda.arn
  handler           = "lambda_function.lambda_handler"
  timeout           = 120  # 2 minutes (max time for WebSocket response)

  runtime = "python3.12"

  environment {
    variables = {
      SQS_QUEUE_URL    = aws_sqs_queue.compilation_queue_beta.id
      WEBSOCKET_URL    = "wss://events.godbolt.org/beta"
      RETRY_COUNT      = "2"
      TIMEOUT_SECONDS  = "90"
    }
  }
  
  depends_on = [aws_cloudwatch_log_group.compilation_beta]
  
  tags = {
    Environment = "beta"
    Purpose     = "compilation"
  }
}

resource "aws_cloudwatch_log_group" "compilation_beta" {
  name              = "/aws/lambda/compilation-beta"
  retention_in_days = 14
  
  tags = {
    Environment = "beta"
    Purpose     = "compilation-logs"
  }
}

# Lambda function for Staging environment
resource "aws_lambda_function" "compilation_staging" {
  description       = "Handle compilation requests for staging environment"
  s3_bucket         = data.aws_s3_object.compilation_lambda_zip.bucket
  s3_key            = data.aws_s3_object.compilation_lambda_zip.key
  s3_object_version = data.aws_s3_object.compilation_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.compilation_lambda_zip_sha.body)
  function_name     = "compilation-staging"
  role              = aws_iam_role.iam_for_lambda.arn
  handler           = "lambda_function.lambda_handler"
  timeout           = 120  # 2 minutes

  runtime = "python3.12"

  environment {
    variables = {
      SQS_QUEUE_URL    = aws_sqs_queue.compilation_queue_staging.id
      WEBSOCKET_URL    = "wss://events.godbolt.org/staging"
      RETRY_COUNT      = "2"
      TIMEOUT_SECONDS  = "90"
    }
  }
  
  depends_on = [aws_cloudwatch_log_group.compilation_staging]
  
  tags = {
    Environment = "staging"
    Purpose     = "compilation"
  }
}

resource "aws_cloudwatch_log_group" "compilation_staging" {
  name              = "/aws/lambda/compilation-staging"
  retention_in_days = 14
  
  tags = {
    Environment = "staging"
    Purpose     = "compilation-logs"
  }
}

# Lambda function for Production environment
resource "aws_lambda_function" "compilation_prod" {
  description       = "Handle compilation requests for production environment"
  s3_bucket         = data.aws_s3_object.compilation_lambda_zip.bucket
  s3_key            = data.aws_s3_object.compilation_lambda_zip.key
  s3_object_version = data.aws_s3_object.compilation_lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.compilation_lambda_zip_sha.body)
  function_name     = "compilation-prod"
  role              = aws_iam_role.iam_for_lambda.arn
  handler           = "lambda_function.lambda_handler"
  timeout           = 120  # 2 minutes

  runtime = "python3.12"

  environment {
    variables = {
      SQS_QUEUE_URL    = aws_sqs_queue.compilation_queue_prod.id
      WEBSOCKET_URL    = "wss://events.godbolt.org/"
      RETRY_COUNT      = "2"
      TIMEOUT_SECONDS  = "90"
    }
  }
  
  depends_on = [aws_cloudwatch_log_group.compilation_prod]
  
  tags = {
    Environment = "prod"
    Purpose     = "compilation"
  }
}

resource "aws_cloudwatch_log_group" "compilation_prod" {
  name              = "/aws/lambda/compilation-prod"
  retention_in_days = 14
  
  tags = {
    Environment = "prod"
    Purpose     = "compilation-logs"
  }
}

