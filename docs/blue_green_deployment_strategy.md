# Blue-Green Deployment Strategy for Compiler Explorer

## Problem Statement

The current environment refresh process uses AWS ASG's `start_instance_refresh` API, which gradually replaces instances while maintaining a minimum healthy percentage (default 75%). This causes a period where both old and new instances serve traffic simultaneously, creating version inconsistencies for users.

During refresh:
- Old instances with version A and new instances with version B are both active
- Users may experience different behavior between requests
- State inconsistencies can occur when requests are routed to different versions

## Current Architecture Analysis

### Key Components
- **Auto Scaling Groups (ASGs)**: Directly attached to ALB target groups via `target_group_arns`
- **Application Load Balancer (ALB)**: Routes traffic based on path patterns (e.g., `/beta*`, `/staging*`)
- **Target Groups**: Configure health checks on `/healthcheck` endpoint
- **Instance Registration**: Automatic when instances pass health checks
- **Deregistration Delay**: 20 seconds for connection draining

### Current Refresh Process
1. User runs `ce --env prod builds set_current <version>`
2. User runs `ce --env prod environment refresh`
3. ASG instance refresh starts with `MinHealthyPercentage=75`
4. New instances launch and register with target group
5. Old instances are gradually terminated
6. **Problem**: Mixed versions serve traffic during this transition

## Proposed Solution: Blue-Green Deployment

### Architecture Overview

Implement a dual ASG pattern where:
- Each environment has two ASGs: "blue" and "green"
- Only one ASG is active (attached to target group) at a time
- New deployments go to the inactive ASG
- Traffic switches atomically between ASGs

### Benefits
1. **Zero Downtime**: No mixed versions serving traffic
2. **Instant Rollback**: Previous version remains available
3. **Pre-deployment Testing**: Validate new instances before switching
4. **Reduced Risk**: Atomic switch minimizes failure window

## Technical Deep Dive: ASG to Target Group Attachment

### AWS API Options for Target Group Management

There are two primary approaches for managing ASG-to-target-group associations:

#### Option 1: Direct ASG Attachment (Not Suitable for Blue-Green)
```python
# This permanently attaches an ASG to a target group
as_client.attach_load_balancer_target_groups(
    AutoScalingGroupName='prod-blue',
    TargetGroupARNs=['arn:aws:elasticloadbalancing:...']
)
```
**Problem**: This creates a permanent association. All future instances in the ASG automatically register with the target group. You cannot have an ASG "standing by" without being in the target group.

#### Option 2: Individual Instance Registration (Recommended)
```python
# Register instances individually
elb_client.register_targets(
    TargetGroupArn='arn:aws:elasticloadbalancing:...',
    Targets=[
        {'Id': 'i-1234567890abcdef0'},
        {'Id': 'i-0987654321fedcba0'}
    ]
)

# Deregister instances
elb_client.deregister_targets(
    TargetGroupArn='arn:aws:elasticloadbalancing:...',
    Targets=[{'Id': 'i-1234567890abcdef0'}]
)
```

### Timing and Performance Characteristics

1. **Registration Speed**
   - API call: Near-instant (< 1 second)
   - Health check passing: 20-40 seconds (depends on health check configuration)
   - Total time to serve traffic: ~30-50 seconds per instance

2. **Deregistration Speed**
   - API call: Near-instant (< 1 second)
   - Connection draining: 20 seconds (configured `deregistration_delay`)
   - Instance fully removed: ~20-30 seconds

3. **Batch Operations**
   - Both APIs support up to 20 targets per call
   - For larger ASGs, multiple API calls needed
   - Can register/deregister in parallel

### Critical Consideration: No Atomic Swap API

**Important**: AWS does **not** provide an atomic "swap" operation for target groups. This means:
- You must orchestrate the attach/detach sequence yourself
- There will be a brief period where both ASGs have instances in the target group
- This is actually beneficial for zero-downtime deployment

### Recommended Sequencing Strategy

```python
def perform_blue_green_switch(self, target_group_arn: str, 
                             old_instances: List[str], 
                             new_instances: List[str]):
    """
    Performs a zero-downtime switch between ASGs.
    
    Timeline:
    0s: Start - Old instances serving 100% traffic
    0-5s: Register all new instances (batch API calls)
    5-45s: Wait for new instances to pass health checks
    45s: Both old and new instances serving traffic
    45-50s: Deregister old instances
    50-70s: Connection draining for old instances
    70s: Complete - New instances serving 100% traffic
    """
    
    # Step 1: Register new instances (fast - API calls only)
    # Can handle up to 20 instances per API call
    for i in range(0, len(new_instances), 20):
        batch = new_instances[i:i+20]
        elb_client.register_targets(
            TargetGroupArn=target_group_arn,
            Targets=[{'Id': instance_id} for instance_id in batch]
        )
    
    # Step 2: Wait for new instances to become healthy
    # This is the longest part - typically 20-40 seconds
    healthy_new = self.wait_for_targets_healthy(target_group_arn, new_instances)
    
    # Step 3: Verify minimum healthy count
    if len(healthy_new) < len(new_instances):
        raise Exception(f"Only {len(healthy_new)}/{len(new_instances)} instances became healthy")
    
    # Step 4: Deregister old instances (fast - API calls only)
    for i in range(0, len(old_instances), 20):
        batch = old_instances[i:i+20]
        elb_client.deregister_targets(
            TargetGroupArn=target_group_arn,
            Targets=[{'Id': instance_id} for instance_id in batch]
        )
    
    # Connection draining happens automatically (20s)
```

### Alternative Approach: Target Group Switching

Instead of switching instances, you could switch entire target groups:

```python
# Update ALB listener rule to point to new target group
elb_client.modify_rule(
    RuleArn='arn:aws:elasticloadbalancing:...',
    Actions=[{
        'Type': 'forward',
        'TargetGroupArn': new_target_group_arn
    }]
)
```

**Pros**:
- Truly atomic switch
- Instant traffic cutover

**Cons**:
- Requires duplicating target groups for each environment
- More complex Terraform management
- Breaks the current path-based routing model

#### How Current Path-Based Routing Works

The current architecture uses a single ALB with path-based routing rules:

```
ALB (compiler-explorer.com)
├── Default rule → prod target group
├── /beta* → beta target group
├── /staging* → staging target group
├── /gpu* → gpu target group
└── /wintest* → wintest target group
```

Each environment has:
- **One target group** (e.g., "Prod", "Beta", "Staging")
- **One ASG** attached to that target group
- **Path-based routing** to direct traffic

Example current Terraform:
```hcl
# One target group per environment
resource "aws_alb_target_group" "ce" {
  for_each = {
    "prod"    = 1
    "staging" = 2
    "beta"    = 3
  }
  name = title(each.key)
}

# ALB listener rules route by path
resource "aws_alb_listener_rule" "staging" {
  priority = 2
  condition {
    path_pattern {
      values = ["/staging*"]
    }
  }
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.ce["staging"].arn
  }
}
```

#### How Target Group Switching Would Change This

With target group switching, each environment would need **two target groups**:

```
ALB (compiler-explorer.com)
├── Default rule → prod-blue OR prod-green (switchable)
├── /beta* → beta-blue OR beta-green (switchable)
├── /staging* → staging-blue OR staging-green (switchable)
└── /gpu* → gpu-blue OR gpu-green (switchable)
```

Required changes:

1. **Double the Target Groups**:
```hcl
# Need blue AND green target groups for each environment
resource "aws_alb_target_group" "ce_blue" {
  for_each = var.environments
  name = "${title(each.key)}-Blue"
}

resource "aws_alb_target_group" "ce_green" {
  for_each = var.environments
  name = "${title(each.key)}-Green"
}
```

2. **Dynamic Listener Rules**:
```hcl
# Listener rules must be updateable via Terraform variables or data sources
resource "aws_alb_listener_rule" "staging" {
  condition {
    path_pattern {
      values = ["/staging*"]
    }
  }
  action {
    type = "forward"
    # This would need to be dynamic based on active color
    target_group_arn = data.aws_ssm_parameter.staging_active_tg.value
  }
}
```

3. **Complex State Management**:
```python
# Need to track which target group is active for EACH environment
def get_active_target_groups():
    return {
        "prod": "prod-blue",      # or "prod-green"
        "staging": "staging-green", # or "staging-blue"
        "beta": "beta-blue",      # or "beta-green"
    }

# Switching would update the ALB rule for that specific path
def switch_environment(env: str, new_color: str):
    rule_arn = get_rule_arn_for_environment(env)
    new_tg_arn = get_target_group_arn(f"{env}-{new_color}")
    
    elb_client.modify_rule(
        RuleArn=rule_arn,
        Actions=[{
            'Type': 'forward',
            'TargetGroupArn': new_tg_arn
        }]
    )
```

#### Why This Breaks the Current Model

1. **Terraform Complexity**:
   - Currently: 9 target groups (one per environment)
   - With switching: 18 target groups (two per environment)
   - Need dynamic rule updates based on external state

2. **State Synchronization**:
   - Must track active color for EACH environment separately
   - Can't use a single "active color" for all environments
   - Risk of state drift between Terraform and reality

3. **Path-Based Routing Complications**:
   - Each path rule needs independent blue/green state
   - Can't refresh all environments simultaneously
   - More complex rollback scenarios

4. **Operational Overhead**:
   - Double the health checks to monitor
   - Double the CloudWatch alarms
   - More complex debugging ("which target group is /staging using?")

#### Example Deployment Sequence with Target Group Switching

```python
def deploy_with_target_group_switching(env: str):
    # 1. Identify current active target group
    current_tg = f"{env}-blue"  # example
    new_tg = f"{env}-green"
    
    # 2. Ensure new ASG is attached to new target group
    as_client.attach_load_balancer_target_groups(
        AutoScalingGroupName=f"{env}-green",
        TargetGroupARNs=[get_tg_arn(new_tg)]
    )
    
    # 3. Scale up new ASG
    scale_up_asg(f"{env}-green")
    
    # 4. Wait for healthy instances in new target group
    wait_for_healthy_targets(new_tg)
    
    # 5. ATOMIC SWITCH - Update ALB rule
    rule_arn = get_listener_rule_for_path(f"/{env}*")
    elb_client.modify_rule(
        RuleArn=rule_arn,
        Actions=[{
            'Type': 'forward',
            'TargetGroupArn': get_tg_arn(new_tg)
        }]
    )
    
    # 6. Scale down old ASG
    scale_down_asg(f"{env}-blue")
```

While this approach provides a truly atomic switch, the added complexity of managing double the target groups and coordinating path-based rules makes it less attractive than the instance-switching approach for Compiler Explorer's architecture.

### Hybrid Approach: Target Group Switching for Production Only

An interesting middle ground would be implementing target group switching **only for production** while keeping the simpler model for other environments:

```
ALB (compiler-explorer.com)
├── Default rule → prod-blue OR prod-green (switchable)
├── /beta* → beta target group (unchanged)
├── /staging* → staging target group (unchanged)
└── /gpu* → gpu target group (unchanged)
```

#### Why This Makes Sense

1. **Production is Special**:
   - Handles 95%+ of total traffic
   - Most critical for zero-downtime
   - Worth the extra complexity for atomic switching
   - Default route (no path prefix) is simpler to manage

2. **Other Environments Stay Simple**:
   - Lower traffic, less critical
   - Can tolerate rolling deployments
   - Easier to debug and manage
   - No need to double resources

#### Implementation for Prod-Only Target Group Switching

**Terraform Changes**:
```hcl
# Two target groups for production only
resource "aws_alb_target_group" "prod_blue" {
  name     = "Prod-Blue"
  port     = 80
  protocol = "HTTP"
  vpc_id   = module.ce_network.vpc.id
  
  health_check {
    path                = "/healthcheck"
    timeout             = 8
    unhealthy_threshold = 3
    healthy_threshold   = 2
    interval            = 10
  }
}

resource "aws_alb_target_group" "prod_green" {
  name = "Prod-Green"
  # ... identical configuration
}

# Track active production target group
resource "aws_ssm_parameter" "prod_active_tg" {
  name  = "/compiler-explorer/prod/active-target-group"
  type  = "String"
  value = aws_alb_target_group.prod_blue.arn
}

# Update default listener to use parameter
resource "aws_alb_listener" "https" {
  default_action {
    type             = "forward"
    # This is the key change - dynamic target group
    target_group_arn = data.aws_ssm_parameter.prod_active_tg.value
  }
}

# Keep other environments unchanged
resource "aws_alb_listener_rule" "staging" {
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.ce["staging"].arn
  }
  # ... rest unchanged
}
```

**Python Implementation**:
```python
class HybridDeployment:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.env = cfg.env.value
    
    def refresh(self):
        if self.env == "prod":
            self._blue_green_deploy_prod()
        else:
            self._rolling_deploy_other()
    
    def _blue_green_deploy_prod(self):
        """Target group switching for production"""
        # 1. Get current active target group
        param = ssm_client.get_parameter(
            Name="/compiler-explorer/prod/active-target-group"
        )
        current_tg_arn = param['Parameter']['Value']
        
        # 2. Determine new target group
        if "Blue" in current_tg_arn:
            new_tg_arn = current_tg_arn.replace("Blue", "Green")
            new_asg = "prod-green"
            old_asg = "prod-blue"
        else:
            new_tg_arn = current_tg_arn.replace("Green", "Blue")
            new_asg = "prod-blue"
            old_asg = "prod-green"
        
        # 3. Scale up new ASG (already attached to its TG)
        scale_up_asg(new_asg)
        
        # 4. Wait for healthy instances
        wait_for_healthy_targets(new_tg_arn)
        
        # 5. ATOMIC SWITCH - Update default listener
        listener_arn = get_default_listener_arn()
        elb_client.modify_listener(
            ListenerArn=listener_arn,
            DefaultActions=[{
                'Type': 'forward',
                'TargetGroupArn': new_tg_arn
            }]
        )
        
        # 6. Update SSM parameter
        ssm_client.put_parameter(
            Name="/compiler-explorer/prod/active-target-group",
            Value=new_tg_arn,
            Overwrite=True
        )
        
        # 7. Scale down old ASG
        scale_down_asg(old_asg)
    
    def _rolling_deploy_other(self):
        """Keep existing rolling deployment for non-prod"""
        # Current refresh logic
        perform_instance_refresh(self.cfg)
```

#### Advantages of Hybrid Approach

1. **Best of Both Worlds**:
   - Atomic switching for production (where it matters most)
   - Simple management for other environments
   - Reduced infrastructure complexity

2. **Easier Migration Path**:
   - Start with production only
   - Prove the concept works
   - Optionally expand to other environments later

3. **Cost Efficient**:
   - Only duplicate resources for production
   - Other environments stay lean

4. **Cleaner Terraform**:
   - Default listener can be dynamic
   - Path-based rules stay static
   - Less state management complexity

#### Considerations

1. **Different Deployment Strategies**:
   - Team needs to understand two approaches
   - Different commands for prod vs non-prod
   - Documentation must be clear

2. **Monitoring Differences**:
   - Production has two target groups to monitor
   - Different alerting rules needed

3. **Testing Strategy**:
   - Can't test the prod deployment strategy in staging
   - Need separate testing approach

This hybrid approach offers a pragmatic solution that provides maximum benefit (atomic switching for 95% of traffic) with minimum complexity (only doubling production resources).

## Testing Strategy: Using Beta Environment

Beta environment is ideal for testing blue-green deployments because:
- Usually offline, minimizing user impact
- Has path-based routing (/beta*) similar to other environments
- Lower stakes for testing infrastructure changes
- Can validate both target group and instance switching approaches

### Phase 1: Beta Environment Test Plan

#### 1.1 Infrastructure Setup for Beta Testing
```hcl
# Create blue/green resources for beta
resource "aws_autoscaling_group" "beta_blue" {
  name                      = "beta-blue"
  min_size                  = 0
  max_size                  = 2
  desired_capacity          = 0  # Start with zero
  health_check_type         = "ELB"
  health_check_grace_period = 240
  
  launch_template {
    id      = aws_launch_template.CompilerExplorer-beta.id
    version = "$Latest"
  }
  
  # Attach to blue target group
  target_group_arns = [aws_alb_target_group.beta_blue.arn]
  
  tag {
    key                 = "Color"
    value               = "blue"
    propagate_at_launch = true
  }
}

resource "aws_autoscaling_group" "beta_green" {
  # Identical setup with green target group
}

# Two target groups for beta
resource "aws_alb_target_group" "beta_blue" {
  name = "Beta-Blue"
  # ... standard configuration
}

resource "aws_alb_target_group" "beta_green" {
  name = "Beta-Green"
  # ... standard configuration
}
```

#### 1.2 Test Sequence
```bash
# 1. Deploy test infrastructure
terraform apply -target=aws_autoscaling_group.beta_blue
terraform apply -target=aws_autoscaling_group.beta_green

# 2. Start with blue
ce --env beta environment start  # Scale up beta-blue
ce --env beta environment test-blue-green --validate

# 3. Deploy new version to green
ce --env beta builds set_current <test-version>
ce --env beta environment refresh --strategy=blue-green --target=green

# 4. Test the switch
ce --env beta environment switch --from=blue --to=green

# 5. Validate and switch back
ce --env beta environment validate
ce --env beta environment switch --from=green --to=blue
```

### Phase 2: Testing Scenarios

#### Test Cases for Beta
1. **Happy Path**
   - Deploy to inactive color
   - Health checks pass
   - Switch traffic
   - Verify no 5xx errors during switch

2. **Rollback Test**
   - Deploy bad version to green
   - Detect failures
   - Quick rollback to blue
   - Measure rollback time (<1 minute target)

3. **Capacity Test**
   - Ensure sufficient capacity during switch
   - Test with different instance counts
   - Verify traffic distribution

4. **Monitoring Test**
   - CloudWatch metrics for both target groups
   - Alert on switching events
   - Track deployment duration

## Migration Strategy: From Current to Blue-Green

### Pre-Migration Checklist

1. **Communication**
   - Announce maintenance window (2-3 hours recommended)
   - Prepare rollback plan documentation
   - Brief operations team on new process

2. **Infrastructure Preparation**
   ```bash
   # Create new resources without affecting existing
   terraform plan -out=blue-green.tfplan
   terraform apply blue-green.tfplan
   ```

3. **Validation Steps**
   - Verify new ASGs are created but scaled to zero
   - Confirm target groups are healthy (no targets yet)
   - Test parameter store access
   - Validate IAM permissions for switching

### Migration Plan for Production

#### Option A: Safe Migration with Maintenance Window

```python
def migrate_to_blue_green_prod():
    """
    Migrate production from single ASG to blue/green with downtime.
    Total time: ~30 minutes with validation
    """
    
    # 1. Set maintenance message (T+0)
    set_update_message("Upgrading deployment system - brief downtime expected")
    
    # 2. Note current version (T+1)
    current_version = get_current_build_version("prod")
    current_instances = get_healthy_instances("prod")
    
    # 3. Create new blue ASG with current version (T+2)
    set_build_version("prod-blue", current_version)
    scale_asg("prod-blue", len(current_instances))
    
    # 4. Wait for blue instances healthy in new TG (T+5 to T+10)
    wait_for_healthy_targets("Prod-Blue", timeout=300)
    
    # 5. CRITICAL: Atomic switch to blue target group (T+10)
    # This is the actual downtime moment - ~1 second
    switch_alb_default_action_to("Prod-Blue")
    update_parameter_store("/compiler-explorer/prod/active-target-group", "blue")
    
    # 6. Verify traffic flowing (T+11)
    verify_health_endpoint()
    verify_no_5xx_errors()
    
    # 7. Drain and terminate old ASG (T+12 to T+15)
    # Set desired=0, let ALB drain connections (20 seconds)
    scale_asg("prod", 0)
    
    # 8. Clear maintenance message (T+20)
    set_update_message("")
    
    # 9. Test green deployment (T+25)
    test_blue_green_switch()
```

#### Option B: Zero-Downtime Migration (Complex but Safer)

```python
def migrate_zero_downtime():
    """
    Migrate with zero downtime using instance-level management.
    Total time: ~45 minutes but no service interruption
    """
    
    # 1. Create blue ASG with same version
    current_version = get_current_build_version("prod")
    set_build_version("prod-blue", current_version)
    
    # 2. Scale blue to match current capacity
    current_count = get_instance_count("prod")
    scale_asg("prod-blue", current_count)
    
    # 3. Wait for blue instances healthy
    blue_instances = wait_for_healthy_instances("prod-blue")
    
    # 4. Gradually migrate instances to blue target group
    for instance in blue_instances[:len(blue_instances)//2]:
        # Register new instance
        register_target("Prod-Blue", instance)
        wait_for_target_healthy("Prod-Blue", instance)
        
        # Deregister one old instance
        old_instance = get_instances("prod")[0]
        deregister_target("Prod", old_instance)
        terminate_instance(old_instance)
        
        # Wait to avoid thundering herd
        time.sleep(30)
    
    # 5. Switch default action to blue TG
    switch_alb_default_action_to("Prod-Blue")
    
    # 6. Migrate remaining instances
    # ... continue gradual migration
```

### Post-Migration Validation

1. **Functional Tests**
   ```bash
   # Verify blue deployment
   ce --env prod environment status
   ce --env prod environment health-check
   
   # Test switch to green
   ce --env prod environment refresh --strategy=blue-green --dry-run
   ```

2. **Performance Tests**
   - Load test during switch
   - Measure switch time
   - Verify no increase in error rates

3. **Monitoring Setup**
   - CloudWatch dashboard for blue/green target groups
   - Alerts for failed deployments
   - Deployment duration metrics

### Rollback Plan

If issues arise during migration:

1. **Before ALB Switch**:
   - Simply terminate new ASGs
   - No impact to service

2. **After ALB Switch**:
   ```python
   # Quick rollback to original setup
   switch_alb_default_action_to("Prod")  # Original TG
   scale_asg("prod", original_capacity)
   scale_asg("prod-blue", 0)
   ```

3. **Emergency Procedure**:
   - Have terraform state backup
   - Document original ALB listener configuration
   - Keep original ASG configuration as terraform backup

### Success Criteria

- [ ] Zero 5xx errors during migration
- [ ] Switch time < 2 seconds
- [ ] All health checks passing
- [ ] Successful test deployment post-migration
- [ ] Rollback tested and timed (< 1 minute)
- [ ] Team trained on new procedures

### Why "Attach New First, Then Detach Old"?

1. **Zero Downtime**: Ensures capacity never drops below required
2. **Gradual Transition**: New instances start taking traffic gradually
3. **Safe Rollback**: Old instances still available if issues detected
4. **Connection Preservation**: Existing connections complete gracefully

### Health Check Verification Function

```python
def wait_for_targets_healthy(self, target_group_arn: str, 
                           instance_ids: List[str], 
                           timeout: int = 300) -> List[str]:
    """
    Wait for instances to become healthy in the target group.
    Returns list of healthy instances.
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        response = elb_client.describe_target_health(
            TargetGroupArn=target_group_arn,
            Targets=[{'Id': iid} for iid in instance_ids]
        )
        
        healthy = []
        unhealthy = []
        
        for target in response['TargetHealthDescriptions']:
            if target['TargetHealth']['State'] == 'healthy':
                healthy.append(target['Target']['Id'])
            else:
                unhealthy.append({
                    'id': target['Target']['Id'],
                    'state': target['TargetHealth']['State'],
                    'reason': target['TargetHealth'].get('Reason', 'Unknown')
                })
        
        if len(healthy) == len(instance_ids):
            return healthy
            
        print(f"Health check status: {len(healthy)}/{len(instance_ids)} healthy")
        if unhealthy:
            print(f"Unhealthy instances: {unhealthy}")
            
        time.sleep(5)
    
    raise TimeoutError(f"Timeout waiting for instances to become healthy")
```

## Implementation Plan

### Phase 1: Terraform Infrastructure Changes

#### 1.1 Create Dual ASGs
```hcl
# Example for production environment
resource "aws_autoscaling_group" "prod-blue" {
  name                      = "prod-blue"
  min_size                  = 2
  max_size                  = 24
  health_check_type         = "ELB"
  health_check_grace_period = 240
  # Note: No target_group_arns here - will be attached dynamically
  
  mixed_instances_policy {
    # ... existing configuration ...
  }
  
  tag {
    key                 = "Environment"
    value               = "prod"
    propagate_at_launch = true
  }
  
  tag {
    key                 = "Color"
    value               = "blue"
    propagate_at_launch = true
  }
}

resource "aws_autoscaling_group" "prod-green" {
  # Duplicate configuration with name="prod-green" and Color="green"
}
```

#### 1.2 Active ASG Tracking
Use AWS Systems Manager Parameter Store to track active ASG:
```hcl
resource "aws_ssm_parameter" "active_asg" {
  name  = "/compiler-explorer/${var.environment}/active-asg"
  type  = "String"
  value = "blue"  # Initial value
}
```

### Phase 2: Python CLI Implementation

#### 2.1 New Blue-Green Deployment Module
Create `bin/lib/blue_green_deploy.py`:

```python
import time
from typing import Dict, List, Optional
import boto3
from lib.amazon import as_client, elb_client, ssm_client
from lib.env import Config

class BlueGreenDeployment:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.env = cfg.env.value
        
    def get_active_color(self) -> str:
        """Get currently active ASG color from Parameter Store"""
        param_name = f"/compiler-explorer/{self.env}/active-asg"
        response = ssm_client.get_parameter(Name=param_name)
        return response['Parameter']['Value']
    
    def get_inactive_color(self, active: str) -> str:
        """Determine inactive color"""
        return "green" if active == "blue" else "blue"
    
    def wait_for_instances_healthy(self, asg_name: str) -> List[str]:
        """Wait for all instances in ASG to be healthy"""
        while True:
            asg = as_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )['AutoScalingGroups'][0]
            
            healthy_instances = [
                i['InstanceId'] for i in asg['Instances']
                if i['HealthStatus'] == 'Healthy' 
                and i['LifecycleState'] == 'InService'
            ]
            
            if len(healthy_instances) == asg['DesiredCapacity']:
                return healthy_instances
                
            print(f"Waiting for instances: {len(healthy_instances)}/{asg['DesiredCapacity']} healthy")
            time.sleep(10)
    
    def perform_switch(self, target_group_arn: str, 
                      old_instances: List[str], 
                      new_instances: List[str]):
        """Atomically switch target group attachments"""
        # Register new instances
        for instance_id in new_instances:
            elb_client.register_targets(
                TargetGroupArn=target_group_arn,
                Targets=[{'Id': instance_id}]
            )
        
        # Wait for new instances to be healthy in target group
        self.wait_for_targets_healthy(target_group_arn, new_instances)
        
        # Deregister old instances
        for instance_id in old_instances:
            elb_client.deregister_targets(
                TargetGroupArn=target_group_arn,
                Targets=[{'Id': instance_id}]
            )
        
        # Update active ASG parameter
        param_name = f"/compiler-explorer/{self.env}/active-asg"
        new_color = self.get_inactive_color(self.get_active_color())
        ssm_client.put_parameter(
            Name=param_name,
            Value=new_color,
            Overwrite=True
        )
```

#### 2.2 Modified Environment Refresh Command

Update `bin/lib/cli/environment.py`:

```python
@environment.command(name="refresh")
@click.option(
    "--strategy",
    type=click.Choice(["rolling", "blue-green"]),
    default="blue-green",
    help="Deployment strategy to use"
)
@click.option(
    "--min-healthy-percent",
    type=click.IntRange(min=0, max=100),
    default=75,
    help="For rolling strategy: minimum healthy percentage"
)
@click.pass_obj
def environment_refresh(cfg: Config, strategy: str, min_healthy_percent: int, motd: str):
    """Refreshes an environment using the specified strategy."""
    
    if strategy == "blue-green":
        deployment = BlueGreenDeployment(cfg)
        deployment.execute()
    else:
        # Keep existing rolling deployment
        perform_rolling_refresh(cfg, min_healthy_percent, motd)
```

### Phase 3: Deployment Process

#### New Deployment Workflow
1. **Preparation**
   ```bash
   ce --env prod builds set_current <version>
   ```

2. **Blue-Green Refresh**
   ```bash
   ce --env prod environment refresh --strategy=blue-green
   ```
   
   This will:
   - Identify inactive ASG (e.g., "green")
   - Scale up inactive ASG with new instances
   - Wait for all instances to pass health checks
   - Atomically switch target group attachments
   - Scale down old ASG (optionally keep warm for rollback)

3. **Verification**
   ```bash
   ce --env prod environment status
   ```

#### Rollback Process
```bash
ce --env prod environment rollback
```
This quickly switches back to the previous ASG.

### Phase 4: Migration Strategy

1. **Test Environments First**
   - Start with `staging` environment
   - Validate blue-green process
   - Monitor for issues

2. **Gradual Production Rollout**
   - Enable for `beta` environment
   - Finally migrate `prod` environment
   - Keep rolling strategy as fallback option

3. **Monitoring Updates**
   - Update CloudWatch dashboards for dual ASGs
   - Create alerts for deployment failures
   - Monitor target group health during switches

## Alternative Approaches Considered

### 1. Target Group Switching
- Create blue/green target groups instead of ASGs
- Switch ALB rules between target groups
- **Rejected**: More complex ALB rule management

### 2. Manual Instance Management
- Temporarily detach ASG from target group
- Manually register/deregister instances
- **Rejected**: More error-prone, less automated

### 3. AWS CodeDeploy Integration
- Use CodeDeploy's blue-green deployment
- **Rejected**: Requires significant infrastructure changes

## Risk Mitigation

1. **Deployment Failures**
   - Automatic rollback on health check failures
   - Keep previous ASG warm for quick recovery

2. **Capacity Issues**
   - Ensure sufficient EC2 capacity before scaling
   - Use multiple instance types for flexibility

3. **State Management**
   - Use Parameter Store for active ASG tracking
   - Add safeguards against concurrent deployments

## Success Metrics

- **Zero-downtime deployments**: No user-facing errors during refresh
- **Deployment time**: Reduced from 15-20 minutes to 5-10 minutes
- **Rollback time**: Under 1 minute
- **Version consistency**: No mixed-version serving

## Future Enhancements

1. **Canary Deployments**
   - Gradually shift traffic between ASGs
   - Monitor error rates during transition

2. **Automated Testing**
   - Run integration tests on new ASG before switching
   - Automated rollback on test failures

3. **Multi-Region Support**
   - Coordinate blue-green deployments across regions
   - Ensure global consistency