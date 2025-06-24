# ALB Configuration for Compilation Lambda Infrastructure
# Target groups, attachments, and listener rules for routing compilation requests

# ALB Target Groups for Lambda functions
resource "aws_alb_target_group" "compilation_lambda_beta" {
  name        = "compilation-lambda-beta"
  target_type = "lambda"

  health_check {
    enabled = false
  }

  tags = {
    Environment = "beta"
    Purpose     = "compilation-lambda"
  }
}

resource "aws_alb_target_group" "compilation_lambda_staging" {
  name        = "compilation-lambda-staging"
  target_type = "lambda"

  health_check {
    enabled = false
  }

  tags = {
    Environment = "staging"
    Purpose     = "compilation-lambda"
  }
}

resource "aws_alb_target_group" "compilation_lambda_prod" {
  name        = "compilation-lambda-prod"
  target_type = "lambda"

  health_check {
    enabled = false
  }

  tags = {
    Environment = "prod"
    Purpose     = "compilation-lambda"
  }
}

# ALB Target Group Attachments for Lambda functions
resource "aws_alb_target_group_attachment" "compilation_lambda_beta" {
  target_group_arn = aws_alb_target_group.compilation_lambda_beta.arn
  target_id        = aws_lambda_function.compilation_beta.arn

  depends_on = [aws_lambda_permission.compilation_beta_alb]
}

resource "aws_alb_target_group_attachment" "compilation_lambda_staging" {
  target_group_arn = aws_alb_target_group.compilation_lambda_staging.arn
  target_id        = aws_lambda_function.compilation_staging.arn

  depends_on = [aws_lambda_permission.compilation_staging_alb]
}

resource "aws_alb_target_group_attachment" "compilation_lambda_prod" {
  target_group_arn = aws_alb_target_group.compilation_lambda_prod.arn
  target_id        = aws_lambda_function.compilation_prod.arn

  depends_on = [aws_lambda_permission.compilation_prod_alb]
}

# ALB Listener Rules to route compilation requests to Lambda
# Beta environment compilation endpoints (combined rule for both compile and cmake)
resource "aws_alb_listener_rule" "compilation_beta" {
  priority = 10

  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.compilation_lambda_beta.arn
  }

  condition {
    path_pattern {
      values = [
        "/beta/api/compilers/*/compile",
        "/beta/api/compilers/*/cmake"
      ]
    }
  }

  listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn

  tags = {
    Environment = "beta"
    Purpose     = "compilation-routing"
  }
}

# Staging environment compilation endpoints - COMMENTED OUT FOR NOW
# Uncomment this rule when ready to enable Lambda for staging
# resource "aws_alb_listener_rule" "compilation_staging" {
#   priority = 12
#
#   action {
#     type             = "forward"
#     target_group_arn = aws_alb_target_group.compilation_lambda_staging.arn
#   }
#
#   condition {
#     path_pattern {
#       values = [
#         "/staging/api/compilers/*/compile",
#         "/staging/api/compilers/*/cmake"
#       ]
#     }
#   }
#
#   listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
#
#   tags = {
#     Environment = "staging"
#     Purpose     = "compilation-routing"
#   }
# }

# Production environment compilation endpoints - COMMENTED OUT FOR NOW
# Uncomment this rule when ready to enable Lambda for production
# resource "aws_alb_listener_rule" "compilation_prod" {
#   priority = 4 # Higher priority than other environment rules
#
#   action {
#     type             = "forward"
#     target_group_arn = aws_alb_target_group.compilation_lambda_prod.arn
#   }
#
#   condition {
#     path_pattern {
#       values = [
#         "/api/compilers/*/compile",
#         "/api/compilers/*/cmake"
#       ]
#     }
#   }
#
#   listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
#
#   tags = {
#     Environment = "prod"
#     Purpose     = "compilation-routing"
#   }
# }
