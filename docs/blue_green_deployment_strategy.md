# Blue-Green Deployment Implementation for Compiler Explorer

## Overview

Compiler Explorer has implemented a blue-green deployment strategy for both beta and production environments, providing zero-downtime deployments with instant rollback capabilities. This implementation uses ALB listener rule switching (beta) or listener default action switching (production) with dual ASGs and target groups.

## Problem Solved

The previous deployment process caused version inconsistencies during rolling updates:
- Old instances with version A and new instances with version B served traffic simultaneously
- Users experienced different behavior between requests
- No instant rollback capability if issues were detected

## Architecture

### Implementation Approach: ALB Listener Rule/Action Switching

The implementation uses **dual target groups** with different switching mechanisms:

**Beta Environment** - Uses listener rule switching:
```
ALB (godbolt.org)
├── HTTPS Listener :443
    ├── Default rule → prod target groups
    ├── /beta* rule → Beta-Blue OR Beta-Green (switchable)
    ├── /staging* rule → staging target group (unchanged)
    └── /gpu* rule → gpu target group (unchanged)
```

**Production Environment** - Uses default action switching:
```
ALB (godbolt.org)
├── HTTP Listener :80
│   └── Default action → Prod-Blue OR Prod-Green (switchable)
├── HTTPS Listener :443
    └── Default action → Prod-Blue OR Prod-Green (switchable)
```

### Terraform Module Structure

The blue-green infrastructure is defined using a reusable Terraform module:

```hcl
# Beta environment configuration
module "beta_blue_green" {
  source = "./modules/blue_green"

  environment               = "beta"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-beta.id
  subnets                   = local.subnets
  asg_max_size              = 4
  initial_desired_capacity  = 0
  initial_active_color      = "blue"
}

# Production environment configuration
module "prod_blue_green" {
  source = "./modules/blue_green"

  environment               = "prod"
  vpc_id                    = module.ce_network.vpc.id
  launch_template_id        = aws_launch_template.CompilerExplorer-prod.id
  subnets                   = local.subnets
  asg_max_size              = 40
  initial_desired_capacity  = 0
  initial_active_color      = "blue"

  # Production uses mixed instances for cost optimization
  use_mixed_instances_policy = true
  on_demand_base_capacity    = 0
  on_demand_percentage_above_base_capacity = 0
  spot_allocation_strategy   = "price-capacity-optimized"
  mixed_instances_overrides = [
    { instance_type = "m5zn.large" },
    { instance_type = "m5.large" },
    # ... additional instance types
  ]

  # Enable auto-scaling for production
  enable_autoscaling_policy = true
  autoscaling_target_cpu    = 50.0
}
```

### Components Created

For each environment using blue-green:

1. **Two Target Groups**:
   - Beta: `Beta-Blue` and `Beta-Green`
   - Prod: `Prod-Blue` and `Prod-Green`
2. **Two ASGs**:
   - Beta: `beta-blue` and `beta-green`
   - Prod: `prod-blue` and `prod-green`
3. **SSM Parameters**: Track active color and target group ARN
   - `/compiler-explorer/{env}/active-color`
   - `/compiler-explorer/{env}/active-target-group-arn`
4. **Auto-scaling Policies** (production only): CPU-based scaling

## Deployment Process

### CLI Commands

```bash
# Check current status (available for all environments)
ce --env {beta|prod|staging|gpu|wintest|winstaging|winprod|aarch64staging|aarch64prod} blue-green status

# Deploy to inactive color
ce --env <environment> blue-green deploy [--capacity N] [version]

# List available versions for deployment
ce --env <environment> blue-green deploy list [--branch branch_name]

# Switch to specific color manually
ce --env <environment> blue-green switch {blue|green}

# Rollback to previous color
ce --env <environment> blue-green rollback

# Clean up inactive ASG
ce --env <environment> blue-green cleanup

# Shut down environment
ce --env <environment> blue-green shutdown

# Validate setup
ce --env <environment> blue-green validate
```

### Deployment Flow

1. **Preparation**: Identify active and inactive colors
2. **Scaling Protection**: Lock active ASG capacity (min/max = current)
3. **Deploy to Inactive**: Scale up inactive ASG with new instances
4. **Health Verification**: Ensure all instances pass health checks
5. **Traffic Switch**: Update ALB listener rule to point to new target group
6. **Cleanup**: Reset min sizes and restore ASG settings
7. **Completion**: New version serving traffic, old version available for rollback

### Switch Mechanism

The system switches traffic differently based on environment:

**Beta Environment** - Updates listener rule:
```python
elb_client.modify_rule(
    RuleArn=rule_arn,
    Actions=[{
        "Type": "forward",
        "TargetGroupArn": new_tg_arn
    }]
)
```

**Production Environment** - Updates listener default actions:
```python
# Updates both HTTP and HTTPS listeners
for listener in [http_listener, https_listener]:
    elb_client.modify_listener(
        ListenerArn=listener["ListenerArn"],
        DefaultActions=[{
            "Type": "forward",
            "TargetGroupArn": new_tg_arn
        }]
    )
```

## Safety Features

### ASG Protection During Deployment

During deployment, the active ASG is protected from unwanted scaling:

```python
def protect_asg_capacity(asg_name: str) -> Optional[Tuple[int, int]]:
    # Set both MinSize and MaxSize to current capacity
    # Prevents scale-up from CloudWatch alarms
    # Prevents scale-down from policies
    as_client.update_auto_scaling_group(
        AutoScalingGroupName=asg_name,
        MinSize=current_capacity,
        MaxSize=current_capacity
    )
```

### Existing Instance Detection

The system warns users when deploying to ASGs with existing instances:

```bash
⚠️  WARNING: The green ASG already has 1 instance(s) running!
This means you'll be switching to existing instances rather than deploying fresh ones.

If you want to:
  • Switch traffic to existing green instances → use 'ce --env beta blue-green switch'
  • Roll back to green → use 'ce --env beta blue-green rollback'
  • Deploy fresh instances → run 'ce --env beta blue-green cleanup' first, then deploy
```

### Signal Handling

Deployment interruptions are handled gracefully:
- SIGINT/SIGTERM signals trigger cleanup
- Active ASG protection is restored
- Inactive ASG is reset to min size 0
- No orphaned resources or stuck states

## State Management

### SSM Parameters

The system tracks state using AWS Systems Manager Parameter Store:

```bash
/compiler-explorer/beta/active-color = "blue" | "green"
/compiler-explorer/beta/active-target-group-arn = "arn:aws:elasticloadbalancing:..."
```

### Status Command Output

```bash
$ ce --env beta blue-green status

Blue-Green Status for beta:
Active Color: blue
Inactive Color: green

ASG Status:
  blue (ACTIVE):
    ASG Name: beta-blue
    Desired/Min/Max: 1/0/4
    ASG Health: 1/1 healthy
    Target Group: 1/1 healthy ✅
    HTTP Health: skipped (not running on admin node) ℹ️
  green:
    ASG Name: beta-green
    Desired/Min/Max: 0/0/4
    ASG Health: 0/0 healthy
    Target Group: 0/0 healthy ❓
    HTTP Health: 0/0 healthy ⚪
```

## Production Discovery Management

Production deployments require compiler discovery files for safety. The blue-green deployment system automatically handles discovery requirements:

### Interactive Production Deployments

When deploying to production without an existing discovery file, users are presented with options:

```bash
⚠️  WARNING: Compiler discovery has not run for prod/gh-123
For production deployments, we can copy discovery from staging if available.
Options:
  1. Copy discovery from staging (recommended)
  2. Continue without discovery (risky)
  3. Cancel deployment
Choose option (1/2/3):
```

### Skip Confirmation Restrictions

Production deployments **cannot** use `--skip-confirmation` when discovery is missing:

```bash
❌ ERROR: --skip-confirmation cannot be used for production deployments without discovery.
Production deployments require either:
  1. Existing discovery file for the version
  2. Manual confirmation to copy discovery from staging
Deployment cancelled.
```

### Discovery Copy Process

When option 1 is selected, the system:
1. Attempts to copy discovery from `staging` to `prod` for the specified version
2. Retries the discovery check after successful copy
3. **Fails the deployment** if the copy operation encounters errors (permissions, network, etc.)
4. Continues with deployment if copy succeeds

This ensures production deployments maintain safety standards while providing a streamlined workflow when discovery files are available in staging.

## Advantages

1. **Zero Downtime**: Atomic traffic switching between versions
2. **Instant Rollback**: Previous version remains available
3. **Pre-deployment Testing**: Validate instances before receiving traffic
4. **Version Consistency**: No mixed versions serving simultaneously
5. **Comprehensive Protection**: ASG scaling protection during deployment
6. **Safety Checks**: Warnings and confirmations for risky operations

## Current Implementation Scope

- **Beta Environment**: Fully implemented and operational
- **Production Environment**: Fully implemented and operational with mixed instances and auto-scaling
- **Staging Environment**: Blue-green infrastructure implemented
- **GPU Environment**: Blue-green infrastructure implemented with mixed instances and auto-scaling
- **Windows Environments**: Blue-green infrastructure implemented for wintest, winstaging, and winprod
- **AArch64 Environments**: Blue-green infrastructure implemented for aarch64staging and aarch64prod with SQS-based scaling

## Migration Considerations

### Production Migration (Completed)

Production has been successfully migrated to blue-green deployment. The migration process was:

1. **Initial Setup**:
   - Apply Terraform changes to create blue-green infrastructure
   - The old `prod-mixed` ASG remains commented out for safety
   - Initial active color is set to "blue" with 0 instances

2. **Migration Steps**:
   ```bash
   # 1. Deploy initial instances to blue ASG
   ce --env prod blue-green deploy --capacity 10

   # 2. Verify blue instances are healthy
   ce --env prod blue-green status --detailed

   # 3. Switch traffic to blue (this updates ALB default actions)
   ce --env prod blue-green switch blue

   # 4. Monitor and verify traffic is being served correctly

   # 5. Remove old prod-mixed ASG from Terraform after successful migration
   ```

3. **Post-Migration**:
   - The old `prod-mixed` ASG has been removed from Terraform
   - Production now operates fully on blue-green deployment
   - Use standard blue-green commands for all production deployments

### Special Considerations for Production

1. **CloudFront Integration**: CloudFront automatically uses the ALB's default actions
2. **Mixed Instances**: Production uses spot instances for cost optimization
3. **Auto-scaling**: CPU-based scaling is enabled (target: 50%)
4. **Capacity**: Production supports up to 40 instances vs beta's 4

## Environment-Specific Implementations

### All Environment Terraform Files Created

New blue-green infrastructure files have been created:
- `staging-blue-green.tf` - Staging environment (AMD64)
- `gpu-blue-green.tf` - GPU environment with mixed instances and auto-scaling
- `windows-blue-green.tf` - Windows environments (wintest, winstaging, winprod)
- `aarch64-blue-green.tf` - AArch64 environments with custom SQS-based scaling

### Environment-Specific Features

**GPU Environment**:
- Mixed instances policy (g4dn.xlarge, g4dn.2xlarge)
- CPU-based auto-scaling (50% target)
- On-demand base capacity of 1 instance

**Windows Environments**:
- Increased health check grace periods (300s-500s)
- WinProd uses mixed instances policy with CPU auto-scaling

**AArch64 Environments**:
- Custom SQS queue backlog-based auto-scaling
- Separate scaling policies for blue and green ASGs
- Target: 3 messages per instance

### Migration Strategy for New Environments

1. **Phase 1**: Deploy blue-green infrastructure (no traffic impact)
2. **Phase 2**: Test blue-green deployments on each environment
3. **Phase 3**: Update ALB listener rules to use blue-green target groups
4. **Phase 4**: Remove old single ASG resources

## Future Enhancements

Based on implementation experience, potential improvements include:

1. **Canary Deployments**: Gradual traffic shifting between colors
2. **Automated Testing**: Integration tests before traffic switch
3. **Enhanced Monitoring**: Blue-green specific metrics and alerts
4. **Cross-region Support**: Extend to other AWS regions
