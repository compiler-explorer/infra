# Color-Specific Queues for Blue-Green Deployments

## Overview
This implementation solves the queue consumption overlap issue during blue-green deployments (#1783) by creating separate SQS queues for blue and green deployment colors. This ensures that during deployments, old and new code versions don't process the same compilation requests.

## Architecture

### Queue Structure
Each environment now has two SQS FIFO queues:
- `{environment}-compilation-queue-blue.fifo`
- `{environment}-compilation-queue-green.fifo`

### Routing Logic
The compilation Lambda determines which queue to use based on:
1. Checks the active color from SSM Parameter Store (`/compiler-explorer/{environment}/active-color`)
2. Routes compilation requests to the active color's queue
3. Caches the active color for 30 seconds to reduce SSM API calls

### Instance Consumption
- Blue instances consume only from the blue queue
- Green instances consume only from the green queue
- No overlap during deployments as inactive color's queue receives no new messages

## Deployment Flow

1. **Before Deployment**
   - Active color (e.g., blue) instances consume from blue queue
   - Lambda routes all requests to blue queue
   - Green queue is empty

2. **During Deployment**
   - New instances (green) start and consume from green queue (empty)
   - Blue instances continue processing blue queue
   - Lambda still routes to blue queue (active color)

3. **Traffic Switch**
   - ALB switches traffic to green instances
   - SSM parameter updated to mark green as active
   - Lambda starts routing new requests to green queue

4. **After Switch**
   - Green instances process new requests from green queue
   - Blue instances drain remaining messages from blue queue
   - Blue instances can be safely scaled down once queue is empty

## Implementation Details

### Terraform Changes

#### Queue Creation
- Modified `terraform/modules/compilation_lambda/main.tf` to create color-specific queues
- Updated module outputs to expose both blue and green queue IDs, ARNs, and names

#### Auto-Scaling Policies
- Updated `terraform/beta-blue-green.tf` to use color-specific queue metrics
- Blue ASG scales based on blue queue depth
- Green ASG scales based on green queue depth

#### IAM Permissions
- Updated Lambda IAM policy to access both colored queues
- Added SSM GetParameter permission for active color lookup
- Updated instance IAM policies to access both queues

### Lambda Changes

#### Routing Module (`compilation-lambda/lib/routing.js`)
- Added `getActiveColor()` function to fetch active color from SSM
- Implemented 30-second cache for active color
- Modified `getColoredQueueUrl()` to route to appropriate queue
- Removed legacy queue references

#### AWS Clients (`compilation-lambda/lib/aws-clients.js`)
- Added SSM client for parameter store access
- Added GetParameterCommand for active color lookup

## Configuration

### Environment Variables
Lambda functions now use:
- `SQS_QUEUE_URL_BLUE`: Blue queue URL
- `SQS_QUEUE_URL_GREEN`: Green queue URL
- `ENVIRONMENT_NAME`: Environment identifier

### SSM Parameters
- `/compiler-explorer/{environment}/active-color`: Current active color (blue/green)

## Migration Notes

### Instance Updates Required
The CE instances need to be updated to:
1. Determine their color from EC2 tags
2. Connect to the appropriate colored queue
3. This requires changes in the main compiler-explorer repository

### Rollout Strategy
1. Deploy terraform changes to create new queues
2. Deploy updated Lambda with color-aware routing
3. Update instances to use color-specific queues
4. Test in staging environment
5. Deploy to production

## Testing

### Staging Validation
1. Deploy changes to staging environment
2. Verify both queues are created
3. Test Lambda routing to active color queue
4. Perform blue-green deployment
5. Verify no queue overlap during deployment
6. Confirm clean traffic switch

### Monitoring
- Monitor queue depth for both colors
- Track Lambda routing decisions in CloudWatch
- Verify auto-scaling responds to correct queue metrics

## Deployment Safety Improvements

To address timing issues where instances appeared healthy but compilers weren't ready:

### Compiler Registration Check
- Added Step 3.5 to blue-green deployments
- Verifies `/api/compilers` endpoint returns expected number of compilers
- Configurable via `--skip-compiler-check` and `--compiler-timeout` flags
- Prevents traffic switching to instances with incomplete compiler discovery

### Integration with Colored Queues
- Ensures instances are ready to consume from their assigned colored queue
- Prevents premature scaling based on queue metrics
- Complements the color separation strategy by ensuring readiness

## Benefits

1. **Clean Separation**: Each deployment color processes its own queue
2. **No Message Loss**: Messages naturally drain from old queue
3. **Predictable Scaling**: Auto-scaling based on color-specific metrics
4. **Safe Deployments**: No risk of mixed code versions processing same requests
5. **Gradual Migration**: System works with existing infrastructure during transition
6. **Ready State Verification**: Compiler registration checks ensure instances are ready before receiving traffic
