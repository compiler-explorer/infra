# Blue-Green Deployment Implementation for Compiler Explorer

## Overview

Compiler Explorer has implemented a blue-green deployment strategy for the beta environment, providing zero-downtime deployments with instant rollback capabilities. This implementation uses ALB listener rule switching with dual ASGs and target groups.

## Problem Solved

The previous deployment process caused version inconsistencies during rolling updates:
- Old instances with version A and new instances with version B served traffic simultaneously
- Users experienced different behavior between requests
- No instant rollback capability if issues were detected

## Architecture

### Implementation Approach: ALB Listener Rule Switching

The implementation uses **dual target groups** with **listener rule switching**:

```
ALB (godbolt.org)
├── HTTPS Listener :443
    ├── Default rule → prod target group (unchanged)
    ├── /beta* rule → Beta-Blue OR Beta-Green (switchable)
    ├── /staging* rule → staging target group (unchanged)
    └── /gpu* rule → gpu target group (unchanged)
```

### Terraform Module Structure

The blue-green infrastructure is defined using a reusable Terraform module:

```hcl
# terraform/modules/blue_green/
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
```

### Components Created

For each environment using blue-green (currently beta):

1. **Two Target Groups**: `Beta-Blue` and `Beta-Green`
2. **Two ASGs**: `beta-blue` and `beta-green`
3. **SSM Parameters**: Track active color and target group ARN
4. **Terraform Module**: Reusable for other environments

## Deployment Process

### CLI Commands

```bash
# Check current status
ce --env beta blue-green status

# Deploy to inactive color
ce --env beta blue-green deploy [--capacity N]

# Switch to specific color manually
ce --env beta blue-green switch green

# Rollback to previous color
ce --env beta blue-green rollback

# Clean up inactive ASG
ce --env beta blue-green cleanup

# Shut down environment
ce --env beta blue-green shutdown

# Validate setup
ce --env beta blue-green validate
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

The system switches traffic by updating the ALB listener rule:

```python
# From blue_green_deploy.py
def switch_target_group(self, new_color: str) -> None:
    rule_arn = self.get_listener_rule_arn()
    new_tg_arn = self.get_target_group_arn(new_color)

    elb_client.modify_rule(
        RuleArn=rule_arn,
        Actions=[{
            "Type": "forward",
            "TargetGroupArn": new_tg_arn
        }]
    )

    # Update SSM parameters for state tracking
    self._update_ssm_parameters(new_color, new_tg_arn)
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

## Advantages

1. **Zero Downtime**: Atomic traffic switching between versions
2. **Instant Rollback**: Previous version remains available
3. **Pre-deployment Testing**: Validate instances before receiving traffic
4. **Version Consistency**: No mixed versions serving simultaneously
5. **Comprehensive Protection**: ASG scaling protection during deployment
6. **Safety Checks**: Warnings and confirmations for risky operations

## Current Implementation Scope

- **Beta Environment**: Fully implemented and operational
- **Production**: Still uses rolling deployments
- **Other Environments**: Continue with existing deployment strategies

## Future Enhancements

Based on beta experience, potential improvements include:

1. **Production Implementation**: Extend to production environment
2. **Canary Deployments**: Gradual traffic shifting
3. **Automated Testing**: Integration tests before traffic switch
4. **Enhanced Monitoring**: Blue-green specific metrics and alerts

## Migration from Previous Architecture

The implementation replaced the old single beta ASG with:
- Removal of `aws_autoscaling_group.beta` resource
- Removal of "beta" from target groups variable
- Updated ALB listener rule to use blue-green target groups
- Added blue-green module infrastructure

This ensures no conflicts between old and new deployment strategies.
