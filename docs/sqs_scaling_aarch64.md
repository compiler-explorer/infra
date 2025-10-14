# SQS-Based Auto-Scaling for AArch64 Environments

## Overview

Compiler Explorer implements sophisticated SQS-based auto-scaling specifically for AArch64 environments (both production and staging). Unlike other environments that use CPU-based scaling, AArch64 environments scale based on compilation job queue depth, providing more responsive and cost-effective scaling for batch workloads.

## Why SQS-Based Scaling?

AArch64 compilation requests are inherently different from general web traffic:

1. **Batch-oriented Workload**: Compilation jobs are discrete, finite tasks
2. **Variable Duration**: Individual compilations can take seconds to minutes
3. **Queue-based Processing**: Jobs are naturally queued and processed sequentially
4. **Cost Sensitivity**: ARM instances are used on-demand, requiring efficient scaling
5. **Predictable Load**: Queue depth directly correlates with required capacity

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SQS-Based Scaling Flow                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [Compilation Request] → [SQS FIFO Queue] → [AArch64 Instances]        │
│                                  │                    │                 │
│                                  ↓                    ↓                 │
│                         [CloudWatch Metrics] → [Auto-Scaling Policy]   │
│                                  │                    │                 │
│                                  ↓                    ↓                 │
│                         [Queue Depth Monitor] → [Scale Out/In]         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## SQS Queue Configuration

### Queue Setup

Two dedicated FIFO queues are configured for AArch64 environments:

```hcl
# Production AArch64 Queue
resource "aws_sqs_queue" "prod-execqueue-aarch64-linux-cpu" {
  name                        = "prod-execqueue-aarch64-linux-cpu.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
}

# Staging AArch64 Queue
resource "aws_sqs_queue" "staging-execqueue-aarch64-linux-cpu" {
  name                        = "staging-execqueue-aarch64-linux-cpu.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
}
```

### Queue Characteristics

- **FIFO (First-In-First-Out)**: Ensures compilation requests are processed in order
- **No Content Deduplication**: Each compilation request is treated as unique
- **Environment Isolation**: Separate queues prevent staging workload from affecting production
- **Message Retention**: Standard SQS retention policies apply (14 days default)

## Auto-Scaling Policy Implementation

### Target Tracking Configuration

The scaling policy uses a sophisticated "**backlog per instance**" calculation:

**Target Value: 3 messages per instance**

```hcl
target_tracking_configuration {
  target_value = 3  # Target: 3 messages per instance

  customized_metric_specification {
    # Metric 1: Queue Size (messages waiting to be processed)
    metrics {
      label = "Get the queue size (the number of messages waiting to be processed)"
      id    = "m1"
      metric_stat {
        metric {
          namespace   = "AWS/SQS"
          metric_name = "ApproximateNumberOfMessagesVisible"
          dimensions {
            name  = "QueueName"
            value = aws_sqs_queue.prod-execqueue-aarch64-linux-cpu.name
          }
        }
        stat = "Sum"
      }
    }

    # Metric 2: Current Instance Count
    metrics {
      label = "Get the group size (the number of InService instances)"
      id    = "m2"
      metric_stat {
        metric {
          namespace   = "AWS/AutoScaling"
          metric_name = "GroupInServiceInstances"
          dimensions {
            name  = "AutoScalingGroupName"
            value = module.aarch64prod_blue_green.blue_asg_name
          }
        }
        stat = "Average"
      }
    }

    # Final Calculation: Backlog per Instance
    metrics {
      label       = "Calculate the backlog per instance"
      id          = "e1"
      expression  = "m1 / m2"  # Queue Size ÷ Instance Count
      return_data = true
    }
  }
}
```

### Scaling Behavior

| Condition | Action |
|-----------|---------|
| `(Queue Size ÷ Instance Count) > 3` | **Scale OUT** (add instances) |
| `(Queue Size ÷ Instance Count) < 3` | **Scale IN** (remove instances) |
| `Queue Size = 0` | **Scale to minimum** (1 instance maintained) |

### Timing Configuration

- **Instance Warmup**: 180 seconds (`local.cooldown`)
  - Time for new instances to become ready for work
- **Health Check Grace**: 240 seconds (`local.grace_period = 60 * 4`)
  - Time before health checks begin after instance launch
- **Policy Type**: `TargetTrackingScaling`
  - Automatically maintains target value
  - Responsive to both scale-out and scale-in scenarios

## Blue-Green Integration

### Dual Scaling Policies

Each AArch64 environment has separate but identical scaling policies for both blue and green ASGs:

**Production Policies:**
- `aarch64prod-mq-tracker-blue` → References `prod-execqueue-aarch64-linux-cpu` queue
- `aarch64prod-mq-tracker-green` → References `prod-execqueue-aarch64-linux-cpu` queue

**Staging Policies:**
- `aarch64staging-mq-tracker-blue` → References `staging-execqueue-aarch64-linux-cpu` queue
- `aarch64staging-mq-tracker-green` → References `staging-execqueue-aarch64-linux-cpu` queue

### Deployment Behavior

During blue-green deployment:

1. **Normal State**: Only one color (e.g., blue) is active and processing queue messages
2. **Deployment Start**: Green ASG is scaled up based on current queue depth
3. **Traffic Switch**: ALB switches to green ASG, blue ASG becomes standby
4. **Cleanup**: Blue ASG can be scaled down (both ASGs monitor the same queue)

**Key Insight**: Both blue and green ASGs monitor the **same queue**, ensuring consistent scaling behavior regardless of which color is active.

## Environment-Specific Configuration

### AArch64 Production

- **Max Instances**: 6 (r7g.medium instances)
- **Initial Capacity**: 1 (minimum maintained)
- **Instance Types**: Exclusively `r7g.medium` (ARM Graviton3)
- **Spot Strategy**: `price-capacity-optimized`
- **Queue**: `prod-execqueue-aarch64-linux-cpu.fifo`

### AArch64 Staging

- **Max Instances**: 4 (r7g.medium instances)
- **Initial Capacity**: 0 (normally shutdown, scales from zero when active)
- **Instance Types**: Exclusively `r7g.medium` (ARM Graviton3)
- **Spot Strategy**: `price-capacity-optimized`
- **Queue**: `staging-execqueue-aarch64-linux-cpu.fifo`

## IAM Permissions

### SQS Access Policy

Instances require specific permissions to interact with SQS queues:

```hcl
data "aws_iam_policy_document" "CeSqsPushPop" {
  statement {
    sid = "CeSqsPushPop"
    actions = [
      "sqs:SendMessage",    # Push compilation jobs to queue
      "sqs:ReceiveMessage", # Pull compilation jobs from queue
      "sqs:DeleteMessage"   # Remove completed jobs from queue
    ]
    resources = [
      aws_sqs_queue.prod-execqueue-aarch64-linux-cpu.arn,
      aws_sqs_queue.staging-execqueue-aarch64-linux-cpu.arn,
    ]
  }
}
```

This policy is attached to the `CompilerExplorerRole` that AArch64 instances assume.

## Operational Workflow

### Normal Operation Flow

1. **Job Submission**:
   - User submits AArch64 compilation request
   - Application pushes job to appropriate environment queue (`prod-execqueue-aarch64-linux-cpu.fifo` or `staging-execqueue-aarch64-linux-cpu.fifo`)

2. **Queue Monitoring**:
   - CloudWatch continuously monitors `ApproximateNumberOfMessagesVisible` metric
   - Auto-scaling policy calculates backlog per instance every minute

3. **Scaling Decision**:
   - If backlog > 3 messages per instance: Launch new r7g.medium instances
   - If backlog < 3 messages per instance: Terminate excess instances
   - If no messages in queue: Scale to minimum (1 for production, 0 for staging when inactive)

4. **Instance Processing**:
   - New instances boot up (~3-4 minutes)
   - Instances poll their environment's queue for work
   - Process compilation jobs and delete messages upon completion

5. **Cost Optimization**:
   - Instances scale down to minimum when queue is empty
   - Spot instances provide cost savings
   - Minimal idle capacity maintained for responsiveness

### Scaling Examples

**Scenario 1: Burst Load**
```
Time: 10:00 - 15 AArch64 compilation jobs submitted
Queue Size: 15 messages
Current Instances: 2
Backlog per Instance: 15 ÷ 2 = 7.5 messages per instance
Action: Scale OUT (target is 3, so need ~5 instances total)
Result: Launch 3 additional instances
```

**Scenario 2: Load Decrease**
```
Time: 10:05 - Jobs completed, 6 messages remain
Queue Size: 6 messages
Current Instances: 5
Backlog per Instance: 6 ÷ 5 = 1.2 messages per instance
Action: Scale IN (target is 3, so need ~2 instances total)
Result: Terminate 3 instances
```

**Scenario 3: No Load**
```
Time: 10:10 - All jobs completed
Queue Size: 0 messages
Current Instances: 2
Backlog per Instance: 0 ÷ 2 = 0 messages per instance
Action: Scale to minimum
Result: Terminate 1 instance (maintain 1 for responsiveness)
```

## Monitoring and Observability

### CloudWatch Metrics

**SQS Queue Metrics:**
- `ApproximateNumberOfMessagesVisible`: Jobs waiting to be processed
- `NumberOfMessagesSent`: Rate of job submission
- `NumberOfMessagesDeleted`: Rate of job completion

**Auto-Scaling Metrics:**
- `GroupInServiceInstances`: Current instance count
- `GroupDesiredCapacity`: Target instance count
- `GroupPendingInstances`: Instances launching

**Custom Metric:**
- `Backlog per Instance`: (Queue Size ÷ Instance Count) - the key scaling metric

### Alarms and Monitoring

Consider setting up CloudWatch alarms for:
- Queue depth exceeding thresholds (potential capacity issues)
- Scaling activities (tracking scale-out/in events)
- Instance launch failures
- Message processing latency

## Comparison with Other Environments

| Environment | Scaling Metric | Target Value | Scaling Type |
|-------------|----------------|--------------|--------------|
| **Production** | CPU Utilization | 50% | Target Tracking |
| **Beta** | CPU Utilization | 50% | Target Tracking |
| **Staging** | CPU Utilization | 50% | Target Tracking |
| **GPU** | CPU Utilization | 50% | Target Tracking |
| **Windows** | CPU Utilization | 50% | Target Tracking |
| **AArch64** | **SQS Queue Backlog** | **3 messages/instance** | **Target Tracking** |

**Why Different?**
- AArch64 workloads are batch-oriented rather than request-response
- Queue depth is a more accurate indicator of required capacity than CPU usage
- Enables scale-to-minimum when no compilation jobs are pending
- Better cost optimization for sporadic, bursty workloads

## Troubleshooting

### Common Issues

**1. Instances Not Scaling Out**
- Check SQS queue has messages: `aws sqs get-queue-attributes --queue-url <queue-url>`
- Verify auto-scaling policy exists and is enabled
- Check CloudWatch metrics are being published
- Ensure IAM permissions are correct

**2. Instances Not Scaling In**
- Verify queue is empty or has few messages
- Check for stuck messages in the queue
- Review instance termination protection settings
- Monitor auto-scaling cooldown periods

**3. Messages Not Being Processed**
- Verify instances have SQS permissions (`CeSqsPushPop` policy)
- Check application is correctly polling the queue
- Review instance logs for application errors
- Ensure queue visibility timeout is appropriate

### Debugging Commands

```bash
# Check queue status
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/052730242331/prod-execqueue-aarch64-linux-cpu.fifo \
  --attribute-names All

# Monitor auto-scaling activities
aws autoscaling describe-scaling-activities \
  --auto-scaling-group-name aarch64prod-blue

# Check CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/SQS \
  --metric-name ApproximateNumberOfMessagesVisible \
  --dimensions Name=QueueName,Value=prod-execqueue-aarch64-linux-cpu.fifo \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

## Best Practices

### Configuration
1. **Queue Naming**: Use environment-specific queue names to prevent cross-environment interference
2. **FIFO Queues**: Maintain job ordering for consistent compilation results
3. **Target Value**: 3 messages per instance provides good balance between responsiveness and cost
4. **Instance Warmup**: 180 seconds allows adequate time for application startup

### Operations
1. **Monitor Queue Depth**: Set alarms for unusual queue accumulation
2. **Track Scaling Events**: Monitor auto-scaling activities for patterns
3. **Cost Optimization**: Review spot instance usage and scaling patterns
4. **Blue-Green Deployments**: Ensure both colors can process from the same queue

### Development
1. **Message Handling**: Implement proper error handling and retry logic
2. **Visibility Timeout**: Set appropriate timeouts for job processing duration
3. **Dead Letter Queues**: Consider implementing for failed job handling
4. **Idempotency**: Ensure compilation jobs can be safely retried

## Future Considerations

### Potential Enhancements

1. **Priority Queues**: Separate high-priority compilation requests
2. **Multi-Region**: Extend SQS scaling to multiple AWS regions
3. **Predictive Scaling**: Use historical patterns to pre-scale capacity
4. **Custom Metrics**: Additional application-level metrics for scaling decisions
5. **Spot Fleet**: Advanced spot instance management for better availability

### Scaling to Other Environments

While SQS-based scaling works well for AArch64's batch workload characteristics, consider similar approaches for:
- Other specialized compilation environments
- Batch processing workloads
- Cost-sensitive, intermittent workloads

The key is identifying workloads where queue depth correlates better with required capacity than traditional CPU or memory metrics.
