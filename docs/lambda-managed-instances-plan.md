# Plan: Lambda Managed Instances for WebSocket Lambdas

## Problem Statement

The CE Router system experienced cascade failures when WebSocket Lambda cold starts or failures occurred:

1. WebSocket connection fails or times out
2. Compilation results cannot be delivered back to CE Router
3. SQS messages pile up (instances process work but results go nowhere)
4. Auto-scaling spawns more instances, exacerbating the problem
5. System enters degraded state until manual intervention

The root cause: Lambda cold starts and throttling during traffic spikes cause the WebSocket result delivery path to become unreliable.

## Current Architecture

Three Lambda functions handle WebSocket communication:

| Function | Purpose | Current Config | Traffic Pattern |
|----------|---------|----------------|-----------------|
| `events-onconnect` | Handle new WebSocket connections | 1 Provisioned Concurrency | Low-medium |
| `events-ondisconnect` | Clean up closed connections | 1 Provisioned Concurrency | Low-medium |
| `events-sendmessage` | Relay compilation results to subscribers | 5 Provisioned Concurrency | **High** |

All functions:
- Runtime: Node.js 22.x on arm64
- Share DynamoDB table for connection state
- Connected via API Gateway WebSocket API

## Proposed Solution: Lambda Managed Instances

Use [AWS Lambda Managed Instances](https://docs.aws.amazon.com/lambda/latest/dg/lambda-managed-instances.html) (announced re:Invent 2025) to eliminate cold starts and improve reliability.

### Key Benefits

1. **No cold starts** - Instances are pre-provisioned and always warm
2. **Multi-concurrency** - Single execution environment handles multiple requests simultaneously
3. **50% burst absorption** - Can handle traffic spikes without scaling delay
4. **Cost efficiency** - Compatible with EC2 Savings Plans (up to 72% discount)
5. **Instance control** - Choose optimal instance type for workload

### Mixing Managed and Regular Lambda

Lambda Managed Instances use the same runtime API as regular Lambda, so mixing is fully supported. Each Lambda function can independently use either compute type.

**Recommendation: Start with Managed Instances for all three WebSocket Lambdas.**

Rationale:
- Consistent behavior across the WebSocket system
- Simpler operational model (one capacity provider)
- All three functions share the same traffic patterns (connected to same API Gateway)
- Cost difference is minimal with 1 instance minimum

Alternative (if cost is critical):
- Only `events-sendmessage` on Managed Instances (highest traffic, most critical)
- Keep `events-onconnect` and `events-ondisconnect` on regular Lambda with Provisioned Concurrency

## Configuration Plan

### Capacity Provider

```hcl
resource "aws_lambda_capacity_provider" "events_websocket" {
  name = "events-websocket"

  vpc_config {
    subnet_ids         = [for s in aws_subnet.ce-subnets : s.id]
    security_group_ids = [aws_security_group.CompilerExplorer.id]
  }

  permissions_config {
    capacity_provider_operator_role_arn = aws_iam_role.lambda_capacity_operator.arn
  }

  instance_requirements {
    architectures          = ["ARM64"]
    allowed_instance_types = ["c8g.medium", "c8g.large"]  # Graviton4
  }

  capacity_provider_scaling_policy {
    scaling_mode   = "AUTO"
    max_vcpu_count = 10  # Limits scale-out
  }
}
```

### Workload Analysis

The WebSocket Lambdas are **I/O-bound**, not CPU-bound. This is because large compilation results use a two-medium approach (see [ce-router source](https://github.com/compiler-explorer/ce-router)):

1. **Small results**: Sent directly through WebSocket
2. **Large results**: Stored in S3, only a lightweight reference (`s3Key`) sent via WebSocket

The ce-router's `result-waiter.ts` handles S3 fetching:
```typescript
// Check if this is a lightweight message - fetch complete result from S3
if (!message.s3Key) return message;
const s3Content = await this.fetchResultFromS3(message.s3Key);
```

**What the WebSocket Lambda actually does:**
- DynamoDB query for subscribers (network I/O)
- API Gateway Management API call to post message (network I/O)
- Small JSON payloads only (minimal CPU)

The heavy JSON parsing of large compilation results happens in the ce-router, not the Lambda.

### Instance Type Selection

| Instance | vCPU | Memory | Network | Monthly Cost (on-demand) |
|----------|------|--------|---------|--------------------------|
| `c8g.medium` | 1 | 2 GB | Up to 12.5 Gbps | ~$25 |
| `m8g.medium` | 1 | 4 GB | Up to 12.5 Gbps | ~$30 |
| `c8g.large` | 2 | 4 GB | Up to 12.5 Gbps | ~$50 |
| `m8g.large` | 2 | 8 GB | Up to 12.5 Gbps | ~$65 |

**Recommendation: `c8g.medium`** - Graviton4 (30% faster than Graviton3), compute-optimized is fine for I/O-bound workload, and cheaper than general-purpose.

### Minimum Instance Behavior

**Important:** Lambda Managed Instances launches **3 instances by default** for AZ resiliency.
There is no configuration to reduce this to 1 instance.

From [AWS documentation](https://docs.aws.amazon.com/lambda/latest/dg/lambda-managed-instances-capacity-providers.html):
> Lambda launches three instances by default for AZ resiliency, ensuring high availability for your functions.

**Cost implication with 3x c8g.medium baseline:**

| Resource | Monthly Cost |
|----------|--------------|
| 3x c8g.medium | ~$75 |
| 15% management fee | ~$11 |
| Lambda invocations | ~$5-10 |
| **Total (on-demand)** | **~$90-95** |
| **Total (1yr Savings Plan)** | **~$55-60** |

This is higher than originally estimated but provides:
- Zero cold starts (always warm)
- AZ redundancy (survives AZ failures)
- 50% burst absorption without scaling

### Lambda Function Updates

```hcl
resource "aws_lambda_function" "events_onconnect" {
  # ... existing config ...

  capacity_provider_config {
    lambda_managed_instances_capacity_provider_config {
      capacity_provider_arn                    = aws_lambda_capacity_provider.events_websocket.arn
      per_execution_environment_max_concurrency = 100
    }
  }
}

resource "aws_lambda_function" "events_ondisconnect" {
  # ... existing config ...

  capacity_provider_config {
    lambda_managed_instances_capacity_provider_config {
      capacity_provider_arn                    = aws_lambda_capacity_provider.events_websocket.arn
      per_execution_environment_max_concurrency = 100
    }
  }
}

resource "aws_lambda_function" "events_sendmessage" {
  # ... existing config ...

  capacity_provider_config {
    lambda_managed_instances_capacity_provider_config {
      capacity_provider_arn                    = aws_lambda_capacity_provider.events_websocket.arn
      per_execution_environment_max_concurrency = 200  # Higher for main traffic handler
    }
  }
}
```

### Remove Provisioned Concurrency

Once Managed Instances are active, remove existing Provisioned Concurrency config:

```hcl
# DELETE these resources after migration:
# - aws_lambda_provisioned_concurrency_config.events_sendmessage
# - aws_lambda_provisioned_concurrency_config.events_onconnect
# - aws_lambda_provisioned_concurrency_config.events_ondisconnect
```

## Cost Analysis

### Current Cost (Provisioned Concurrency)

| Resource | Config | Monthly Cost |
|----------|--------|--------------|
| events-sendmessage | 5 PC @ 512MB | ~$15 |
| events-onconnect | 1 PC @ 128MB | ~$2 |
| events-ondisconnect | 1 PC @ 128MB | ~$2 |
| Lambda invocations | Variable | ~$5-10 |
| **Total** | | **~$25-30** |

### Proposed Cost (Managed Instances)

**Note:** Lambda Managed Instances requires minimum 3 instances for AZ resiliency (not configurable).

| Resource | Config | Monthly Cost |
|----------|--------|--------------|
| c8g.medium instances | 3 minimum (AZ resiliency) | ~$75 |
| Management fee | 15% of EC2 | ~$11 |
| Lambda invocations | Same volume | ~$5-10 |
| **Total (on-demand)** | | **~$90-95** |
| **Total (1yr Savings Plan, 40% off)** | | **~$55-60** |

Higher cost than Provisioned Concurrency, but provides:
- Zero cold starts (eliminates cascade failure risk)
- AZ redundancy (survives AZ failures)
- 50% burst absorption without scaling delays
- Multi-concurrency (better resource utilization)

## Implementation Steps

### Phase 1: Infrastructure Setup

1. [ ] Verify Terraform provider supports Lambda Managed Instances
2. [ ] Create capacity provider resource
3. [ ] Create/update security group for Lambda VPC access
4. [ ] Plan Terraform changes

### Phase 2: Migration (One Lambda at a Time)

1. [ ] Migrate `events-ondisconnect` first (lowest risk)
   - Update function config
   - Test WebSocket disconnection handling
   - Monitor for 24 hours

2. [ ] Migrate `events-onconnect`
   - Update function config
   - Test new connection establishment
   - Monitor for 24 hours

3. [ ] Migrate `events-sendmessage` (most critical)
   - Update function config
   - Test compilation result delivery
   - Load test with simulated traffic
   - Monitor for 48 hours

### Phase 3: Cleanup

1. [ ] Remove Provisioned Concurrency resources
2. [ ] Update documentation
3. [ ] Consider purchasing Savings Plan if stable

## Monitoring

### New CloudWatch Alarms

```hcl
# Managed Instance health
resource "aws_cloudwatch_metric_alarm" "events_capacity_provider_health" {
  alarm_name          = "EventsWebSocketCapacityHealth"
  alarm_description   = "Managed Instance capacity provider unhealthy"
  namespace           = "AWS/Lambda"
  metric_name         = "CapacityProviderUnhealthyInstances"
  dimensions = {
    CapacityProviderName = aws_lambda_capacity_provider.events_websocket.name
  }
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  period              = 60
  statistic           = "Maximum"
  alarm_actions       = [data.aws_sns_topic.alert.arn]
}

# Lambda errors (keep existing pattern)
resource "aws_cloudwatch_metric_alarm" "events_sendmessage_errors" {
  alarm_name          = "EventsSendMessageErrors"
  alarm_description   = "WebSocket sendmessage Lambda errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions = {
    FunctionName = aws_lambda_function.events_sendmessage.function_name
  }
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  period              = 60
  statistic           = "Sum"
  alarm_actions       = [data.aws_sns_topic.alert.arn]
}
```

### Key Metrics to Watch

- `CapacityProviderUnhealthyInstances` - Instance health
- `ConcurrentExecutions` - Multi-concurrency utilization
- `Duration` - Should decrease with warm instances
- `Errors` - Should decrease with eliminated cold starts

## Rollback Plan

If issues occur:

1. Update Lambda functions to remove `compute_type` and `capacity_provider`
2. Re-enable Provisioned Concurrency resources
3. Apply Terraform

Rollback can be completed in under 5 minutes.

## Terraform Support

### Provider Version Required

**AWS Provider v6.24.0** (released December 2, 2025) added Lambda Managed Instances support:

- New resource: `aws_lambda_capacity_provider`
- New arguments on `aws_lambda_function`: `capacity_provider_config`, `publish_to`

**Current CE version:** `~> 5.96.0` (in `terraform/main.tf`)

**Action required:** Upgrade to AWS provider 6.24.0+ (staged, pending commit)

### Terraform Resource Reference

Based on [terraform-provider-aws documentation](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/lambda_capacity_provider.html.markdown).

#### aws_lambda_capacity_provider

```hcl
resource "aws_lambda_capacity_provider" "events_websocket" {
  name = "events-websocket"

  # Required: VPC configuration
  vpc_config {
    subnet_ids         = [for s in aws_subnet.ce-subnets : s.id]
    security_group_ids = [aws_security_group.CompilerExplorer.id]
  }

  # Required: IAM role for Lambda to manage EC2 instances
  permissions_config {
    capacity_provider_operator_role_arn = aws_iam_role.lambda_capacity_operator.arn
  }

  # Optional: Instance requirements
  instance_requirements {
    architectures          = ["ARM64"]  # Graviton
    allowed_instance_types = ["c8g.medium", "c8g.large"]
  }

  # Optional: Scaling configuration
  capacity_provider_scaling_policy {
    scaling_mode   = "AUTO"
    max_vcpu_count = 10
  }

  tags = {
    Site = "CompilerExplorer"
  }
}
```

#### IAM Role for Capacity Provider Operator

Lambda Managed Instances requires an **operator role** to manage EC2 instances.
Use the AWS managed policy `AWSLambdaManagedEC2ResourceOperator`.

```hcl
resource "aws_iam_role" "lambda_capacity_operator" {
  name = "lambda-capacity-provider-operator"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_capacity_operator" {
  role       = aws_iam_role.lambda_capacity_operator.name
  policy_arn = "arn:aws:iam::aws:policy/AWSLambdaManagedEC2ResourceOperator"
}
```

The managed policy grants:
- `ec2:RunInstances` - Launch instances (restricted to Amazon-owned AMIs)
- `ec2:DescribeInstances`, `ec2:DescribeInstanceStatus` - Monitor instances
- `ec2:CreateTags` - Tag resources for management
- `ec2:DescribeAvailabilityZones` - Instance placement decisions

A service-linked role is auto-created on first capacity provider creation for `ec2:TerminateInstances`.

#### Updated Lambda Function

```hcl
resource "aws_lambda_function" "events_sendmessage" {
  # ... existing config ...

  # Add capacity provider configuration
  capacity_provider_config {
    lambda_managed_instances_capacity_provider_config {
      capacity_provider_arn = aws_lambda_capacity_provider.events_websocket.arn

      # Optional: Memory per vCPU (GiB)
      # execution_environment_memory_gib_per_vcpu = 2

      # Optional: Max concurrent requests per execution environment
      per_execution_environment_max_concurrency = 200
    }
  }
}
```

**Note:** When using `capacity_provider_config`, the function runs on Managed Instances
instead of standard Lambda. Remove `provisioned_concurrency` config when migrating.

### CLI Reference

```bash
# Create capacity provider
aws lambda create-capacity-provider \
  --capacity-provider-name events-websocket \
  --vpc-config SubnetIds=subnet-xxx,SecurityGroupIds=sg-xxx \
  --permissions-config CapacityProviderOperatorRoleArn=arn:aws:iam::xxx:role/xxx \
  --instance-requirements Architectures=ARM64 \
  --capacity-provider-scaling-config ScalingMode=Auto

# Check status
aws lambda get-capacity-provider --capacity-provider-name events-websocket

# List capacity providers
aws lambda list-capacity-providers
```

### Quotas

| Quota | Value |
|-------|-------|
| Capacity providers per account | 1,000 |
| Function versions per capacity provider | 100 (hard limit) |
| Max vCPUs per capacity provider | 400 (default, adjustable) |

## Open Questions

1. [x] ~~Terraform AWS provider version required?~~ **v6.24.0+**
2. [ ] Does API Gateway WebSocket API require any changes for Managed Instances?
3. [ ] Are there regional availability limitations?
4. [x] ~~Breaking changes in AWS provider 5.x → 6.x upgrade?~~ **Minimal impact, see below**

## AWS Provider 5.x → 6.x Upgrade Analysis

Analyzed CE terraform against [v6.0.0 breaking changes](https://github.com/hashicorp/terraform-provider-aws/blob/main/CHANGELOG.md).

### Breaking Changes Impact

| Change | Affected? | Notes |
|--------|-----------|-------|
| `aws_ami` most_recent + owner required | No | No `data "aws_ami"` blocks |
| `aws_instance` cpu_core_count removed | No | Not using deprecated args |
| `aws_instance` user_data cleartext | Yes | Cosmetic display change only |
| `aws_eip` vpc → domain | No | No aws_eip resources |
| `aws_launch_template` elastic_* removed | No | Not using deprecated attrs |
| `aws_opsworks_*` removed | No | Not using OpsWorks |
| Multi-region `region` attribute | All | State diffs on first plan |

### Upgrade Process

```bash
# 1. Update terraform/main.tf
#    version = "~> 5.96.0"  →  version = "~> 6.24"

# 2. Initialize
terraform init -upgrade

# 3. Plan (expect region attribute diffs on all resources)
terraform plan -out=upgrade.plan

# 4. Review and apply
terraform apply upgrade.plan
```

### Expected Behavior

- First `terraform plan` shows diffs for every resource (region metadata added)
- No actual infrastructure changes, just state updates
- `user_data` in ec2.tf will display cleartext instead of hash

## References

- [AWS Lambda Managed Instances Documentation](https://docs.aws.amazon.com/lambda/latest/dg/lambda-managed-instances.html)
- [AWS Blog Announcement](https://aws.amazon.com/blogs/aws/introducing-aws-lambda-managed-instances-serverless-simplicity-with-ec2-flexibility/)
- [re:Invent 2025 Session CNS382](https://dev.to/kazuya_dev/aws-reinvent-2025-lambda-managed-instances-ec2-power-with-serverless-simplicity-cns382-3jnm)
