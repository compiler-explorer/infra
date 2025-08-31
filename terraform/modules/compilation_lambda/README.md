# Compilation Lambda Module

This Terraform module creates the infrastructure for Lambda-based compilation endpoints in Compiler Explorer.

## Features

- **Lambda Function**: Node.js 22.x function to handle compilation requests
- **SQS FIFO Queue**: Reliable message queuing for compilation requests
- **ALB Integration**: Target group and optional listener rules for request routing
- **CloudWatch Logs**: Centralized logging with configurable retention
- **IAM Integration**: Uses provided IAM role for Lambda execution

## Usage

```terraform
module "compilation_lambda_beta" {
  source = "./modules/compilation_lambda"

  environment         = "beta"
  websocket_url       = "wss://events.compiler-explorer.com/beta"
  alb_listener_arn    = aws_alb_listener.compiler-explorer-alb-listen-https.arn
  enable_alb_listener = true
  alb_priority        = 10
  alb_path_patterns = [
    "/beta/api/compilers/*/compile",
    "/beta/api/compilers/*/cmake"
  ]
  s3_bucket    = aws_s3_bucket.compiler-explorer.bucket
  iam_role_arn = aws_iam_role.iam_for_lambda.arn

  tags = {
    Project = "compiler-explorer"
  }
}
```

## Auto-Scaling Integration

The module outputs can be used with ASG auto-scaling policies:

```terraform
resource "aws_autoscaling_policy" "compilation_scaling" {
  # ... other configuration ...

  target_tracking_configuration {
    customized_metric_specification {
      metrics {
        metric_stat {
          metric {
            dimensions {
              name  = "QueueName"
              value = module.compilation_lambda_beta.sqs_queue_name
            }
          }
        }
      }
    }
  }
}
```

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│     ALB     │───▶│    Lambda    │───▶│ SQS Queue   │
│             │    │   Function   │    │    FIFO     │
└─────────────┘    └──────────────┘    └─────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  WebSocket   │
                   │    Events    │
                   └──────────────┘
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| environment | Environment name for resource naming and tagging | `string` | n/a | yes |
| websocket_url | WebSocket URL for events system | `string` | n/a | yes |
| alb_listener_arn | ALB listener ARN for routing rules | `string` | n/a | yes |
| s3_bucket | S3 bucket for Lambda package | `string` | n/a | yes |
| iam_role_arn | IAM role ARN for Lambda execution | `string` | n/a | yes |
| enable_alb_listener | Whether to create ALB listener rule | `bool` | `false` | no |
| alb_priority | ALB listener rule priority | `number` | n/a | yes |
| alb_path_patterns | List of path patterns for ALB listener rule | `list(string)` | `[]` | no |
| lambda_timeout | Lambda function timeout in seconds | `number` | `120` | no |
| lambda_retry_count | Number of WebSocket retry attempts | `string` | `"2"` | no |
| lambda_timeout_seconds | WebSocket response timeout in seconds | `string` | `"90"` | no |
| compilation_results_bucket | S3 bucket for storing large compilation results | `string` | `"storage.godbolt.org"` | no |
| compilation_results_prefix | S3 prefix for compilation results | `string` | `"cache/"` | no |

## Outputs

| Name | Description |
|------|-------------|
| sqs_queue_id | SQS queue ID |
| sqs_queue_arn | SQS queue ARN |
| sqs_queue_name | SQS queue name |
| lambda_function_arn | Lambda function ARN |
| lambda_function_name | Lambda function name |
| alb_target_group_arn | ALB target group ARN |
| cloudwatch_log_group_name | CloudWatch log group name |

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.0 |
| aws | >= 5.0 |

## Resources Created

- `aws_sqs_queue` - FIFO queue for compilation requests
- `aws_lambda_function` - Lambda function for request processing
- `aws_cloudwatch_log_group` - Log group for Lambda function
- `aws_alb_target_group` - ALB target group for Lambda
- `aws_alb_target_group_attachment` - Target group attachment
- `aws_lambda_permission` - Permission for ALB to invoke Lambda
- `aws_alb_listener_rule` - ALB listener rule (conditional)

## Path Patterns

The module uses the `alb_path_patterns` variable to configure ALB listener rules. Common patterns:

- **Production**: `["/api/compilers/*/compile", "/api/compilers/*/cmake"]`
- **Staging/Beta**: `["/{environment}/api/compilers/*/compile", "/{environment}/api/compilers/*/cmake"]`
- **Custom**: Any list of path patterns for your specific use case

## Security

This module requires an IAM role with the following permissions:
- Lambda execution permissions
- SQS send/receive permissions
- CloudWatch logs permissions

The IAM role should be created externally and passed via the `iam_role_arn` variable.
