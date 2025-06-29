data "aws_iam_policy_document" "aws_lambda_trust_policy" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "iam_for_lambda" {
  name               = "iam_for_lambda"
  assume_role_policy = data.aws_iam_policy_document.aws_lambda_trust_policy.json
}

resource "aws_iam_role_policy_attachment" "terraform_lambda_policy" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Pretty sure this is subsumed by https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AWSLambdaBasicExecutionRole.html above?
data "aws_iam_policy_document" "aws_lambda_logging" {
  statement {
    sid       = "AllowLogging"
    resources = ["arn:aws:logs:*:*:*"]
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
  }
}

resource "aws_iam_policy" "lambda_logging" {
  name        = "aws_lambda_logging"
  description = "Allow logging"
  policy      = data.aws_iam_policy_document.aws_lambda_logging.json
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.lambda_logging.arn
}

data "aws_iam_policy_document" "aws_lambda_stats" {
  statement {
    sid       = "WriteStatsLog"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.compiler-explorer-logs.arn}/stats/*"]
  }
  statement {
    sid = "AccessSQS"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:SendMessage"
    ]
    resources = [aws_sqs_queue.stats_queue.arn]
  }
  statement {
    sid = "ReadCompilerDb"
    actions = [
      "dynamodb:Query"
    ]
    resources = [aws_dynamodb_table.compiler-builds.arn]
  }
}

resource "aws_iam_policy" "aws_lambda_stats" {
  name        = "aws_lambda_stats_logs"
  description = "Lambda stats policy (Stats, SQS, dynamodb)"
  policy      = data.aws_iam_policy_document.aws_lambda_stats.json
}

resource "aws_iam_role_policy_attachment" "aws_lambda_stats" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.aws_lambda_stats.arn
}

data "aws_iam_policy_document" "alert_on_elb_instance" {
  statement {
    sid = "AccessSNS"
    actions = [
      "sns:Publish",
    ]
    resources = [data.aws_sns_topic.alert.arn]
  }
}

resource "aws_iam_policy" "alert_on_elb_instance" {
  name        = "alert_on_elb_instance"
  description = "Lambda elb instance policy (SNS)"
  policy      = data.aws_iam_policy_document.alert_on_elb_instance.json
}

resource "aws_iam_role_policy_attachment" "alert_on_elb_instance" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.alert_on_elb_instance.arn
}

# WebSocket API Gateway permissions for compilation Lambda
data "aws_iam_policy_document" "compilation_lambda_websocket" {
  statement {
    sid       = "WebSocketAccess"
    actions   = [
      "execute-api:ManageConnections",
      "execute-api:Invoke"
    ]
    resources = ["arn:aws:execute-api:*:*:*"]
  }
}

resource "aws_iam_policy" "compilation_lambda_websocket" {
  name        = "compilation_lambda_websocket"
  description = "Allow compilation Lambda to connect to WebSocket API Gateway"
  policy      = data.aws_iam_policy_document.compilation_lambda_websocket.json
}

resource "aws_iam_role_policy_attachment" "compilation_lambda_websocket" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.compilation_lambda_websocket.arn
}

data "aws_ssm_parameter" "discord_webhook_url" {
  name = "/admin/discord_webhook_url"
}

# Disabled for now as it's pretty chatty
#resource "aws_sns_topic_subscription" "sns_to_lambda" {
#  topic_arn = data.aws_sns_topic.alert.arn
#  protocol  = "lambda"
#  endpoint  = aws_lambda_function.cloudwatch_to_discord.arn
#}

data "aws_s3_object" "lambda_zip" {
  # Lambda zip is uploaded and rebuild by the Makefile: make upload-lambda
  bucket = aws_s3_bucket.compiler-explorer.bucket
  key    = "lambdas/lambda-package.zip"
}

data "aws_s3_object" "lambda_zip_sha" {
  # Lambda zip's SHA256 is uploaded and rebuild by the Makefile: make upload-lambda
  bucket = aws_s3_bucket.compiler-explorer.bucket
  key    = "lambdas/lambda-package.zip.sha256"
}

resource "aws_lambda_function" "cloudwatch_to_discord" {
  description       = "Dispatch cloudwatch messages to discord"
  s3_bucket         = data.aws_s3_object.lambda_zip.bucket
  s3_key            = data.aws_s3_object.lambda_zip.key
  s3_object_version = data.aws_s3_object.lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.lambda_zip_sha.body)
  function_name     = "cloudwatch_to_discord"
  role              = aws_iam_role.iam_for_lambda.arn
  handler           = "cloudwatch_to_discord.lambda_handler"

  runtime = "python3.12"

  environment {
    variables = {
      WEBHOOK_URL = data.aws_ssm_parameter.discord_webhook_url.value
    }
  }
  depends_on = [aws_cloudwatch_log_group.cloudwatch_to_discord]
}

resource "aws_cloudwatch_log_group" "cloudwatch_to_discord" {
  name              = "/aws/lambda/cloudwatch_to_discord"
  retention_in_days = 14
}


resource "aws_lambda_permission" "with_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cloudwatch_to_discord.arn
  principal     = "sns.amazonaws.com"
  source_arn    = data.aws_sns_topic.alert.arn
}

resource "aws_cloudwatch_log_group" "alert_on_elb_instance" {
  name              = "/aws/lambda/alert_on_elb_instance"
  retention_in_days = 14
}

resource "aws_lambda_function" "alert_on_elb_instance" {
  description       = "Look at every ELB instance shutdown and post to SNS on failures"
  s3_bucket         = data.aws_s3_object.lambda_zip.bucket
  s3_key            = data.aws_s3_object.lambda_zip.key
  s3_object_version = data.aws_s3_object.lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.lambda_zip_sha.body)
  function_name     = "alert_on_elb_instance"
  role              = aws_iam_role.iam_for_lambda.arn
  handler           = "alert_on_elb_instance.lambda_handler"

  runtime = "python3.12"

  environment {
    variables = {
      TOPIC_ARN = data.aws_sns_topic.alert.arn
    }
  }
  depends_on = [aws_cloudwatch_log_group.alert_on_elb_instance]
}

resource "aws_lambda_permission" "alert_elb_with_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alert_on_elb_instance.arn
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.elb-instance-terminate.arn
}

resource "aws_sns_topic_subscription" "alert_elb_with_sns" {
  topic_arn = aws_sns_topic.elb-instance-terminate.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.alert_on_elb_instance.arn
}

resource "aws_lambda_function" "stats" {
  description       = "Respond to various CE-specific stats records"
  s3_bucket         = aws_s3_bucket.compiler-explorer.bucket
  s3_key            = data.aws_s3_object.lambda_zip.key
  s3_object_version = data.aws_s3_object.lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.lambda_zip_sha.body)
  function_name     = "stats"
  role              = aws_iam_role.iam_for_lambda.arn
  handler           = "stats.lambda_handler"
  timeout           = 10

  runtime = "python3.12"

  environment {
    variables = {
      S3_BUCKET_NAME       = aws_s3_bucket.compiler-explorer-logs.bucket
      SQS_STATS_QUEUE      = aws_sqs_queue.stats_queue.id
      COMPILER_BUILD_TABLE = aws_dynamodb_table.compiler-builds.name
    }
  }
  depends_on = [aws_cloudwatch_log_group.stats]

}

resource "aws_cloudwatch_log_group" "stats" {
  name              = "/aws/lambda/stats"
  retention_in_days = 14
}

resource "aws_sqs_queue" "stats_queue" {
  name                      = "CompilerExplorerStats"
  max_message_size          = 1024
  message_retention_seconds = 600
}

resource "aws_lambda_permission" "from_alb" {
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.stats.arn
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_alb_target_group.lambda.arn
}

resource "aws_lambda_permission" "from_sqs" {
  statement_id  = "AllowExecutionFromSQS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.stats.arn
  principal     = "sqs.amazonaws.com"
  source_arn    = aws_sqs_queue.stats_queue.arn
}

resource "aws_lambda_event_source_mapping" "sqs_to_lambda" {
  event_source_arn                   = aws_sqs_queue.stats_queue.arn
  function_name                      = aws_lambda_function.stats.arn
  batch_size                         = 100
  maximum_batching_window_in_seconds = 300
}

# Status Lambda Policy
data "aws_iam_policy_document" "aws_lambda_status" {
  statement {
    sid       = "S3Access"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.compiler-explorer.arn}/version/*"]
  }
  statement {
    sid     = "ElbAccess"
    actions = ["elasticloadbalancing:DescribeTargetHealth"]
    # Must use wildcard resource because DescribeTargetHealth requires permissions on both
    # target groups AND their associated load balancers. AWS doesn't provide a way to determine
    # which load balancer a target group belongs to at policy definition time.
    # See: https://serverfault.com/questions/856737/aws-iam-policy-for-elasticloadbalancingdescribetargethealth
    resources = ["*"]
  }
  statement {
    sid     = "AutoScalingAccess"
    actions = ["autoscaling:DescribeAutoScalingGroups"]
    # Must use wildcard resource as ASG ARNs cannot be specified more precisely in IAM
    resources = ["*"]
  }
  statement {
    sid       = "Ec2Access"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "aws_lambda_status" {
  name        = "aws_lambda_status"
  description = "Lambda status policy (S3, ELB, EC2, AutoScaling)"
  policy      = data.aws_iam_policy_document.aws_lambda_status.json
}

resource "aws_iam_role_policy_attachment" "aws_lambda_status" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.aws_lambda_status.arn
}

resource "aws_cloudwatch_log_group" "status" {
  name              = "/aws/lambda/status"
  retention_in_days = 14
}

resource "aws_lambda_function" "status" {
  description       = "Provide status information for CE environments"
  s3_bucket         = data.aws_s3_object.lambda_zip.bucket
  s3_key            = data.aws_s3_object.lambda_zip.key
  s3_object_version = data.aws_s3_object.lambda_zip.version_id
  source_code_hash  = chomp(data.aws_s3_object.lambda_zip_sha.body)
  function_name     = "status"
  role              = aws_iam_role.iam_for_lambda.arn
  handler           = "status.lambda_handler"
  timeout           = 10

  runtime = "python3.12"

  environment {
    variables = {
      PROD_LB_BLUE_ARN         = module.prod_blue_green.target_group_arns["blue"]
      PROD_LB_GREEN_ARN        = module.prod_blue_green.target_group_arns["green"]
      STAGING_LB_BLUE_ARN      = module.staging_blue_green.target_group_arns["blue"]
      STAGING_LB_GREEN_ARN     = module.staging_blue_green.target_group_arns["green"]
      BETA_LB_BLUE_ARN         = module.beta_blue_green.target_group_arns["blue"]
      BETA_LB_GREEN_ARN        = module.beta_blue_green.target_group_arns["green"]
      GPU_LB_BLUE_ARN          = module.gpu_blue_green.target_group_arns["blue"]
      GPU_LB_GREEN_ARN         = module.gpu_blue_green.target_group_arns["green"]
      ARM_PROD_LB_BLUE_ARN     = module.aarch64prod_blue_green.target_group_arns["blue"]
      ARM_PROD_LB_GREEN_ARN    = module.aarch64prod_blue_green.target_group_arns["green"]
      ARM_STAGING_LB_BLUE_ARN  = module.aarch64staging_blue_green.target_group_arns["blue"]
      ARM_STAGING_LB_GREEN_ARN = module.aarch64staging_blue_green.target_group_arns["green"]
      WIN_PROD_LB_BLUE_ARN     = module.winprod_blue_green.target_group_arns["blue"]
      WIN_PROD_LB_GREEN_ARN    = module.winprod_blue_green.target_group_arns["green"]
      WIN_STAGING_LB_BLUE_ARN  = module.winstaging_blue_green.target_group_arns["blue"]
      WIN_STAGING_LB_GREEN_ARN = module.winstaging_blue_green.target_group_arns["green"]
      WIN_TEST_LB_BLUE_ARN     = module.wintest_blue_green.target_group_arns["blue"]
      WIN_TEST_LB_GREEN_ARN    = module.wintest_blue_green.target_group_arns["green"]
    }
  }
  depends_on = [aws_cloudwatch_log_group.status]
}

# Grant permission for the ALB to invoke the Lambda
resource "aws_lambda_permission" "from_alb_status" {
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.status.arn
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_alb_target_group.lambda_status.arn
}
