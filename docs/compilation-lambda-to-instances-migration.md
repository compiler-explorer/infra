# Migration Plan: Lambda to Instance-Based Compilation

## Overview

This document outlines the plan to migrate Compiler Explorer's compilation system from AWS Lambda functions to dedicated AArch64 EC2 instances. The migration aims to provide better performance, cost optimization, and operational control over the compilation workload.

## Current Architecture

### Existing Lambda-Based System
- **Lambda Function**: Handles compilation requests via ALB routing
- **SQS Queues**: Color-specific (blue/green) FIFO queues for request distribution
- **WebSocket**: Real-time result delivery via persistent connections
- **DynamoDB**: Compiler routing table for queue/URL mapping
- **ALB Integration**: Routes compilation paths to Lambda target groups

### Current Flow
1. ALB receives compilation request at `/api/compiler/{id}/compile`
2. Request routed to Lambda function based on path patterns
3. Lambda looks up compiler routing in DynamoDB
4. For queue routing: sends message to appropriate SQS queue (blue/green)
5. Lambda subscribes to WebSocket for result delivery
6. Returns compilation result to client

## Target Architecture

### New Instance-Based System
- **AArch64 Instances**: Dedicated compilation workers running Node.js
- **Single ASG**: Auto-scaling group with CPU-based scaling (no blue-green)
- **Single SQS Queue**: Simplified FIFO queue for all compilation requests
- **Direct ALB Integration**: Target group pointing to compilation instances
- **Persistent Workers**: Long-running Node.js processes consuming SQS messages

### New Flow
1. ALB receives compilation request
2. Request routed to compilation instance target group
3. Instance looks up compiler routing in DynamoDB
4. Instance processes compilation directly or forwards to appropriate environment
5. Result returned directly through HTTP response (or via WebSocket for async)

## Implementation Plan

### Phase 1: Infrastructure Setup

#### 1.1 Packer Configuration
Create `packer/compilation-node.pkr.hcl`:
- Base: Ubuntu 24.04 ARM64 AMI
- Instance type for building: `c7g.medium`
- Setup script: `setup-compilation-node.sh`

#### 1.2 Setup Script
Create `setup-compilation-node.sh`:
- Install Node.js 22.x (matching Lambda runtime)
- Install compilation dependencies (AWS SDK, WebSocket client)
- Configure systemd service for compilation worker
- Set up CloudWatch logging and metrics
- Configure SQS queue consumption
- Optimize network settings for high throughput

#### 1.3 Launch Template
Add to `terraform/lc.tf`:
```hcl
compilation = {
  image_id      = "ami-xxx" # New compilation AMI
  instance_type = "t4g.medium" # 2 vCPU, up to 5 Gbps network
}
```

#### 1.4 Auto Scaling Group
Create `terraform/compilation-asg.tf`:
- Single ASG: `compilation-asg`
- Mixed instances policy (t4g.medium, t4g.large, m7g.medium)
- Min: 2, Desired: 3, Max: 20 instances
- CPU-based auto-scaling (target: 70% CPU)
- Health checks via ALB target group

#### 1.5 SQS Queue
Simplified queue structure:
```hcl
resource "aws_sqs_queue" "compilation_queue" {
  name                        = "compilation-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  message_retention_seconds   = 300
  visibility_timeout_seconds  = 60
}
```

#### 1.6 ALB Configuration
- Single target group: `compilation-instances`
- Health check endpoint: `/healthcheck`
- Load balancing: least outstanding requests
- Listener rule priority: 70 (higher than Lambda rules)

### Phase 2: Application Development

#### 2.1 Node.js Worker Application
Create `compilation-worker/` directory with:
- `index.js`: Main worker process
- `package.json`: Dependencies (AWS SDK, WebSocket client, etc.)
- `lib/`: Port existing Lambda functionality
  - `routing.js`: Compiler routing logic
  - `websocket-client.js`: WebSocket connection management
  - `utils.js`: Utility functions
  - `http-forwarder.js`: Environment URL forwarding

#### 2.2 Key Changes from Lambda
- Remove color-switching logic (single queue)
- Implement long-polling SQS message consumption
- Maintain persistent WebSocket connections
- Add health check endpoint
- Handle graceful shutdown (SIGTERM)
- Use Node.js cluster module for multi-core utilization

#### 2.3 Systemd Service
Create `init/compilation-worker.service`:
- Auto-start on boot
- Restart on failure
- Proper logging configuration
- Environment variable management

### Phase 3: Management Tools

#### 3.1 CLI Commands
Create `bin/lib/cli/compilation.py`:
```python
@cli.group()
def compilation():
    """Compilation instance management commands."""

@compilation.command()
def status():
    """Show compilation ASG status and instance health"""

@compilation.command()
def scale():
    """Manually scale compilation instances"""

@compilation.command()
def isolate():
    """Isolate a compilation instance for debugging"""

@compilation.command()
def logs():
    """Stream logs from compilation instances"""
```

### Phase 4: Monitoring & Observability

#### 4.1 CloudWatch Metrics
- ASG metrics: CPU utilization, instance count
- Custom metrics: Requests/second, WebSocket connections
- SQS metrics: Queue depth, message age
- Network metrics: Throughput, packet loss

#### 4.2 Alarms
- High CPU utilization (>85% for 3 minutes)
- SQS message age > 30 seconds
- Instance health check failures
- Network throttling detection

#### 4.3 Dashboards
- Compilation instance overview
- Request latency and error rates
- Cost comparison with Lambda
- Scaling behavior visualization

## Migration Strategy

### Phase 1: Development & Testing (Week 1-2)
1. Build compilation AMI with packer
2. Deploy single test instance
3. Validate worker functionality with subset of compilers
4. Load testing and performance validation

### Phase 2: Parallel Deployment (Week 3)
1. Deploy ASG with 2-3 instances
2. Route specific compiler types to instances (e.g., GCC only)
3. Monitor performance, error rates, and costs
4. Compare metrics with Lambda baseline

### Phase 3: Gradual Migration (Week 4-6)
Use ALB weighted target groups for gradual traffic shift:
- Week 4: 10% instances, 90% Lambda
- Week 5: 50% instances, 50% Lambda
- Week 6: 90% instances, 10% Lambda

Monitor throughout:
- Response times and error rates
- Cost impact
- Resource utilization
- User experience

### Phase 4: Full Cutover (Week 7)
1. Route 100% compilation traffic to instances
2. Keep Lambda functions disabled (not deleted) for emergency rollback
3. Monitor intensively for first 48 hours
4. Document any issues and resolutions

### Phase 5: Cleanup (Week 9-10)
1. Remove Lambda functions after 2 weeks of stable operation
2. Remove Lambda-specific SQS queues (blue/green)
3. Clean up Lambda-related IAM policies
4. Update documentation
5. Remove Lambda code paths from routing logic

## Instance Sizing & Scaling

### Recommended Instance Types

**Primary: t4g.medium**
- 2 vCPU, 4 GB RAM
- Up to 5 Gbps network bandwidth
- Burstable performance for compilation spikes
- Cost: ~$0.0336/hour

**Alternative Options:**
- `t4g.large`: More burst credits for sustained high load
- `m7g.medium`: Higher baseline network (12.5 Gbps)
- `c7gn.medium`: Maximum network performance (25 Gbps)

### Scaling Configuration
- **Minimum**: 2 instances (high availability)
- **Desired**: 3 instances (normal operations)
- **Maximum**: 20 instances (handle peak loads)
- **Scale Up**: 70% average CPU utilization
- **Scale Down**: 40% average CPU utilization
- **Warmup Time**: 2 minutes for new instances

## High Availability
- Multi-AZ deployment
- Minimum 2 instances at all times
- Health check monitoring
- Auto-scaling for demand spikes

### Monitoring & Alerting
- Real-time dashboards for instance health
- Automated alerting for failures
- SLA monitoring for response times

## Success Criteria

### Performance Targets
- **Response Time**: ≤ current Lambda p95 latency
- **Error Rate**: ≤ 0.1% (same as Lambda)
- **Availability**: ≥ 99.9% uptime

### Operational Targets
- **Scaling**: Auto-scale within 2 minutes of demand change
- **Recovery**: Self-heal from instance failures within 5 minutes

### Timeline
- **Total Migration**: 10 weeks from start to cleanup completion
- **Full Cutover**: Week 7
- **Stability Period**: 2 weeks before cleanup

## Files to Create/Modify

### New Files
- `packer/compilation-node.pkr.hcl`
- `setup-compilation-node.sh`
- `terraform/compilation-asg.tf`
- `compilation-worker/index.js`
- `compilation-worker/package.json`
- `compilation-worker/lib/` (port from Lambda)
- `init/compilation-worker.service`
- `bin/lib/cli/compilation.py`

### Modified Files
- `terraform/lc.tf` (add compilation launch template)
- `terraform/alb.tf` (update listener rules)
- `CLAUDE.md` (document compilation infrastructure)

### Cleanup (Post-Migration)
- `compilation-lambda/` (entire directory)
- `terraform/compilation-lambda-environments.tf`
- Lambda-specific outputs in various Terraform files

## Benefits of Single Environment Approach

### Simplified Architecture
- No blue-green complexity for compilation workload
- Single queue eliminates color coordination
- Easier debugging and troubleshooting
- Simpler deployment and rollback procedures

### Operational Advantages
- Direct CPU-based scaling without color switching delays
- Single target group for load balancer simplicity
- Unified monitoring and alerting
- Consistent instance configuration

### Cost Benefits
- Single ASG reduces infrastructure overhead
- No duplicate resources (blue/green)
- More predictable scaling behavior
- Simplified resource management

This migration plan provides a structured approach to modernizing the compilation infrastructure while maintaining high availability and performance standards.
