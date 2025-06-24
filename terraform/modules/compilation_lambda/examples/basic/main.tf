# Example usage of the compilation_lambda module

module "compilation_lambda_example" {
  source = "../../"

  environment         = "test"
  websocket_url       = "wss://events.test.com/test"
  alb_listener_arn    = "arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/test-alb/50dc6c495c0c9188/0467ef3c8400ae65"
  enable_alb_listener = true
  alb_priority        = 100
  alb_path_patterns = [
    "/test/api/compilers/*/compile",
    "/test/api/compilers/*/cmake"
  ]
  s3_bucket    = "test-bucket"
  iam_role_arn = "arn:aws:iam::123456789012:role/test-lambda-role"

  tags = {
    Environment = "test"
    Project     = "compiler-explorer"
  }
}

# Example output usage
output "queue_name" {
  value = module.compilation_lambda_example.sqs_queue_name
}

output "lambda_arn" {
  value = module.compilation_lambda_example.lambda_function_arn
}
