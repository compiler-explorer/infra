# IAM and Security Configuration for Compilation Lambda Infrastructure
# Policies, roles, and permissions for compilation Lambda functions

# IAM policy for compilation Lambda to access SQS queues
data "aws_iam_policy_document" "compilation_lambda_sqs" {
  statement {
    sid = "SQSAccess"
    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueAttributes"
    ]
    resources = [
      aws_sqs_queue.compilation_queue_beta.arn,
      aws_sqs_queue.compilation_queue_staging.arn,
      aws_sqs_queue.compilation_queue_prod.arn
    ]
  }
}

resource "aws_iam_policy" "compilation_lambda_sqs" {
  name        = "compilation_lambda_sqs"
  description = "Allow compilation Lambda to send messages to SQS queues"
  policy      = data.aws_iam_policy_document.compilation_lambda_sqs.json
}

resource "aws_iam_role_policy_attachment" "compilation_lambda_sqs" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.compilation_lambda_sqs.arn
}

# Lambda permissions for ALB to invoke functions
resource "aws_lambda_permission" "compilation_beta_alb" {
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.compilation_beta.arn
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_alb_target_group.compilation_lambda_beta.arn
}

resource "aws_lambda_permission" "compilation_staging_alb" {
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.compilation_staging.arn
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_alb_target_group.compilation_lambda_staging.arn
}

resource "aws_lambda_permission" "compilation_prod_alb" {
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.compilation_prod.arn
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_alb_target_group.compilation_lambda_prod.arn
}