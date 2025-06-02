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