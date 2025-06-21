# Blue-Green Deployment Implementation for Compiler Explorer

## Overview

Compiler Explorer has implemented a blue-green deployment strategy for all major environments, providing zero-downtime deployments with instant rollback capabilities. This implementation uses ALB listener rule switching with dual ASGs and target groups across all supported environments.

## Problem Solved

The previous deployment process caused version inconsistencies during rolling updates:
- Old instances with version A and new instances with version B served traffic simultaneously
- Users experienced different behavior between requests
- No instant rollback capability if issues were detected

## Architecture

### Implementation Approach: ALB Listener Rule/Action Switching

The implementation uses **dual target groups** with listener rule switching for all environments:

**All Blue-Green Environments** - Uses listener rule switching:
```
ALB (godbolt.org)
├── HTTPS Listener :443
    ├── Default rule → Prod-Blue OR Prod-Green (switchable)
    ├── /beta* rule → Beta-Blue OR Beta-Green (switchable)
    ├── /staging* rule → Staging-Blue OR Staging-Green (switchable)
    ├── /gpu* rule → GPU-Blue OR GPU-Green (switchable)
    ├── /win* rules → Win-Blue OR Win-Green (switchable)
    └── /aarch64* rules → AArch64-Blue OR AArch64-Green (switchable)
```

### Terraform Module Structure

The blue-green infrastructure is defined using a reusable Terraform module:

```hcl
# All environments use the same reusable blue-green module
# Examples:

# Beta environment
module "beta_blue_green" {
  source = "./modules/blue_green"
  environment = "beta"
  asg_max_size = 4
  # ... environment-specific config
}

# Production environment
module "prod_blue_green" {
  source = "./modules/blue_green"
  environment = "prod"
  asg_max_size = 40
  use_mixed_instances_policy = true
  enable_autoscaling_policy = true
  # ... production-specific config
}

# Staging environment
module "staging_blue_green" {
  source = "./modules/blue_green"
  environment = "staging"
  asg_max_size = 4
  # ... staging-specific config
}

# GPU environment
module "gpu_blue_green" {
  source = "./modules/blue_green"
  environment = "gpu"
  asg_max_size = 8
  use_mixed_instances_policy = true
  enable_autoscaling_policy = true
  # ... GPU-specific config with g4dn instances
}

# Windows environments (wintest, winstaging, winprod)
module "winprod_blue_green" {
  source = "./modules/blue_green"
  environment = "winprod"
  use_mixed_instances_policy = true
  enable_autoscaling_policy = true
  health_check_grace_period = 500
  # ... Windows-specific config
}

# AArch64 environments (aarch64staging, aarch64prod)
module "aarch64prod_blue_green" {
  source = "./modules/blue_green"
  environment = "aarch64prod"
  enable_sqs_autoscaling = true
  # ... AArch64-specific config with SQS scaling
}
```

### Components Created

For each environment using blue-green:

1. **Two Target Groups**:
   - Example: `Prod-Blue` and `Prod-Green`, `Beta-Blue` and `Beta-Green`, etc.
2. **Two ASGs**:
   - Example: `prod-blue` and `prod-green`, `staging-blue` and `staging-green`, etc.
3. **SSM Parameters**: Track active color and target group ARN
   - `/compiler-explorer/{env}/active-color`
   - `/compiler-explorer/{env}/active-target-group-arn`
4. **Auto-scaling Policies** (where applicable): CPU-based or SQS-based scaling

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

**All Environments** - Updates listener rule or default action:
```python
# For non-production environments (beta, staging, gpu, etc.)
elb_client.modify_rule(
    RuleArn=rule_arn,
    Actions=[{
        "Type": "forward",
        "TargetGroupArn": new_tg_arn
    }]
)

# For production environment - Updates both HTTP and HTTPS listeners
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

Blue-green deployment is now **fully implemented and operational** for all major environments:

- **Production Environment**: Mixed instances, auto-scaling, default action switching
- **Beta Environment**: Standard configuration with listener rule switching
- **Staging Environment**: Standard configuration with listener rule switching
- **GPU Environment**: Mixed instances (g4dn.xlarge/2xlarge), CPU-based auto-scaling
- **Windows Environments**: Extended health check periods, mixed instances for winprod
  - wintest, winstaging, winprod
- **AArch64 Environments**: Custom SQS queue-based auto-scaling
  - aarch64staging, aarch64prod

## Migration Considerations

### All Environment Migration (Completed)

All major environments have been successfully migrated to blue-green deployment. The migration process for each environment followed a similar pattern:

1. **Infrastructure Deployment**:
   - Apply Terraform changes to create blue-green infrastructure
   - Initial active color set to "blue" with 0 instances
   - Old single ASGs removed after successful migration

2. **Migration Steps** (example for any environment):
   ```bash
   # 1. Deploy initial instances to blue ASG
   ce --env <environment> blue-green deploy --capacity <desired>

   # 2. Verify blue instances are healthy
   ce --env <environment> blue-green status --detailed

   # 3. Switch traffic to blue ASG
   ce --env <environment> blue-green switch blue

   # 4. Monitor and verify traffic is being served correctly

   # 5. Remove old single ASG from Terraform after successful migration
   ```

3. **Post-Migration Status**:
   - All environments now operate fully on blue-green deployment
   - Use standard blue-green commands for all deployments
   - Legacy single ASG configurations have been removed

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

### Migration Success

All phases have been completed successfully:

1. ✅ **Phase 1**: Blue-green infrastructure deployed for all environments
2. ✅ **Phase 2**: Blue-green deployments tested and validated
3. ✅ **Phase 3**: ALB listener rules updated to use blue-green target groups
4. ✅ **Phase 4**: Legacy single ASG resources removed

## Future Enhancements

Based on implementation experience, potential improvements include:

1. **Canary Deployments**: Gradual traffic shifting between colors
2. **Automated Testing**: Integration tests before traffic switch
3. **Enhanced Monitoring**: Blue-green specific metrics and alerts
4. **Cross-region Support**: Extend to other AWS regions
