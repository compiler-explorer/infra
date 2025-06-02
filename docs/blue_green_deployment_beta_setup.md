# Blue-Green Deployment Beta Testing Setup

This document describes how to deploy and test the blue-green deployment infrastructure for the beta environment.

## Prerequisites

- AWS credentials with appropriate permissions
- Terraform installed
- Access to the CE infrastructure repository

## Deployment Steps

### 1. Deploy Terraform Infrastructure

First, review the changes that will be made:

```bash
cd terraform/
terraform plan -target=module.beta_blue_green
```

The plan should show:
- 2 new target groups (Beta-Blue, Beta-Green)
- 2 new ASGs (beta-blue, beta-green)
- 2 new SSM parameters for tracking active color/target group

Deploy the infrastructure:

```bash
# Deploy blue-green resources for beta
terraform apply -target=aws_alb_target_group.beta_blue
terraform apply -target=aws_alb_target_group.beta_green
terraform apply -target=aws_autoscaling_group.beta_blue
terraform apply -target=aws_autoscaling_group.beta_green
terraform apply -target=aws_ssm_parameter.beta_active_color
terraform apply -target=aws_ssm_parameter.beta_active_target_group

# Or apply all at once if you're confident
terraform apply
```

### 2. Verify Infrastructure

Check that resources were created:

```bash
# Check ASGs
aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names beta-blue beta-green

# Check target groups
aws elbv2 describe-target-groups --names Beta-Blue Beta-Green

# Check SSM parameters
aws ssm get-parameter --name /compiler-explorer/beta/active-color
```

### 3. Initial Setup

The blue ASG is set as active by default. To prepare for testing:

```bash
# Check current status
ce --env beta blue-green status

# Validate the setup
ce --env beta blue-green validate
```

## Testing Procedures

### Test 1: Basic Blue-Green Switch

1. **Start with blue active (default)**
   ```bash
   ce --env beta environment start  # This starts the legacy beta ASG
   ```

2. **Deploy to blue ASG**
   ```bash
   # Scale up blue ASG
   aws autoscaling set-desired-capacity --auto-scaling-group-name beta-blue --desired-capacity 1

   # Wait for instance to be healthy
   ce --env beta blue-green status
   ```

3. **Set the ALB rule to use blue target group**
   ```bash
   # For initial testing, manually update the ALB rule
   # Get the rule ARN first
   aws elbv2 describe-rules --listener-arn <HTTPS_LISTENER_ARN> | grep -B5 "/beta"

   # Update the rule to point to Beta-Blue target group
   aws elbv2 modify-rule --rule-arn <RULE_ARN> \
     --actions Type=forward,TargetGroupArn=<BETA_BLUE_TG_ARN>
   ```

4. **Deploy new version to green**
   ```bash
   ce --env beta builds set_current <test-version>
   ce --env beta blue-green deploy --capacity 1
   ```

5. **Verify the switch worked**
   ```bash
   # Check that traffic is now going to green
   curl https://godbolt.org/beta/healthcheck
   ce --env beta blue-green status
   ```

### Test 2: Rollback Scenario

1. **With green active from Test 1**
   ```bash
   ce --env beta blue-green status  # Should show green active
   ```

2. **Simulate an issue and rollback**
   ```bash
   ce --env beta blue-green rollback
   ```

3. **Verify rollback**
   ```bash
   ce --env beta blue-green status  # Should show blue active again
   ```

### Test 3: Capacity Scaling

1. **Test scaling during deployment**
   ```bash
   # Deploy with specific capacity
   ce --env beta blue-green deploy --capacity 2

   # Monitor scaling
   watch 'ce --env beta blue-green status'
   ```

### Test 4: Cleanup

1. **Scale down inactive ASG**
   ```bash
   ce --env beta blue-green cleanup
   ```

## Monitoring During Tests

Watch these metrics during testing:

1. **Target Group Health**
   - Monitor both Beta-Blue and Beta-Green target groups in AWS Console
   - Check `/healthcheck` endpoint responses

2. **ASG Metrics**
   - Instance launch times
   - Health check status
   - Scaling activities

3. **Application Logs**
   - Check for any errors during switches
   - Verify version changes

## Troubleshooting

### If deployment fails:

1. Check ASG scaling activities:
   ```bash
   aws autoscaling describe-scaling-activities --auto-scaling-group-name beta-blue
   ```

2. Check target group health:
   ```bash
   aws elbv2 describe-target-health --target-group-arn <TG_ARN>
   ```

3. Check instance logs:
   ```bash
   ce --env beta instances list
   ce --env beta instances ssh <instance-id>
   ```

### To reset to original state:

1. Point ALB rule back to original beta target group:
   ```bash
   aws elbv2 modify-rule --rule-arn <RULE_ARN> \
     --actions Type=forward,TargetGroupArn=<ORIGINAL_BETA_TG_ARN>
   ```

2. Scale down blue-green ASGs:
   ```bash
   aws autoscaling set-desired-capacity --auto-scaling-group-name beta-blue --desired-capacity 0
   aws autoscaling set-desired-capacity --auto-scaling-group-name beta-green --desired-capacity 0
   ```

## Success Criteria

- [ ] Can deploy to inactive color without affecting active traffic
- [ ] Switch between blue and green takes < 5 seconds
- [ ] No 5xx errors during switch
- [ ] Rollback works within 1 minute
- [ ] Health checks pass throughout deployment
- [ ] Can scale ASGs independently
- [ ] SSM parameters correctly track active color

## Next Steps

After successful beta testing:

1. Document any issues or improvements needed
2. Update monitoring and alerting
3. Plan production rollout strategy
4. Create runbooks for operations team
