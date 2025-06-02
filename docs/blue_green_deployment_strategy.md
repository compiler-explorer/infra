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