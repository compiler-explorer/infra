# Integration Testing Guide

This document describes the integration testing setup for the Compilation Lambda, which tests real AWS services without mocking.

## Test Files

- **`index.test.js`** - Unit tests with mocked AWS services
- **`integration.test.js`** - Integration tests with real AWS services
- **`INTEGRATION_TESTING.md`** - This documentation

## Test Scripts

```bash
# Run unit tests only (with mocks)
npm test

# Run integration tests only (real AWS services)
npm run test:integration

# Run all tests (both unit and integration)
npm run test:all

# Run tests with coverage
npm run test:coverage
```

## Integration Test Categories

### 🔐 AWS Account Identity
Verifies the hardcoded AWS account ID constant is correct.

**Example:**
```javascript
// Verifies the AWS account ID constant is set correctly (052730242331)
expect(AWS_ACCOUNT_ID).toBe('052730242331');
```

### 🗄️ DynamoDB Compiler Routing
Tests real DynamoDB `CompilerRouting` table with actual routing data.

**Test Scenarios:**
- **Composite Key Lookup** - Tests environment-prefixed keys (`prod#gcc-trunk`)
- **URL Routing** - Tests GPU environment with direct URL forwarding
- **Queue Routing** - Tests production environment with SQS queue routing
- **Fallback Logic** - Tests legacy key format and default queue fallback
- **Non-existent Compilers** - Verifies graceful handling of missing entries

**Sample Test:**
```javascript
// Change environment and test GPU compiler routing
process.env.ENVIRONMENT_NAME = 'gpu';
const result = await lookupCompilerRouting('nvcc129u1');
expect(result.type).toBe('url');
expect(result.target).toBe('https://godbolt.org/gpu/api/compiler/nvcc129u1/compile');
```

### 📨 SQS Integration (Dry Run)
Tests SQS message construction without actually sending messages to avoid queue pollution.

**Features Tested:**
- Message body formatting and validation
- Request parsing (JSON vs plain text)
- Required field defaults (source, options, filters, etc.)
- Queue URL validation
- Error handling for missing parameters

### 🔧 Utility Functions
Tests core utility functions with real inputs/outputs:

- **GUID Generation** - Unique identifier creation
- **Path Parsing** - Compiler ID extraction from ALB paths
- **CMake Detection** - Endpoint type identification
- **Response Formatting** - ALB-compatible response structure

### 🌐 End-to-End Routing Flow
Comprehensive tests that combine multiple components:

1. **Production Flow**: Environment switching → DynamoDB lookup → Queue URL construction
2. **GPU Flow**: Environment switching → DynamoDB lookup → URL routing decision

## Real AWS Resources Used

### DynamoDB Table: `CompilerRouting`
- **Account**: `052730242331`
- **Region**: `us-east-1`
- **Records**: ~5,156 compiler routing entries
- **Key Structure**: `compilerId` (String) - supports both legacy (`gcc-trunk`) and composite (`prod#gcc-trunk`) formats

**Sample Routing Entry (Queue):**
```json
{
    "compilerId": "prod#gimpleesp32g20230208",
    "environment": "prod",
    "routingType": "queue",
    "queueName": "prod-compilation-queue",
    "lastUpdated": "2025-07-29T12:54:16.069297+00:00"
}
```

**Sample Routing Entry (URL):**
```json
{
    "compilerId": "gpu#nvcc129u1",
    "environment": "gpu",
    "routingType": "url",
    "targetUrl": "https://godbolt.org/gpu/api/compiler/nvcc129u1/compile",
    "lastUpdated": "2025-07-29T14:11:07.170513+00:00"
}
```

### AWS Account ID
Hardcoded as constant: `052730242331` (no longer requires STS calls)

## Environment Variables

Integration tests use these environment variables:

```bash
ENVIRONMENT_NAME=test                    # Environment context for routing
AWS_REGION=us-east-1                    # AWS region for all services
SQS_QUEUE_URL=https://sqs.us-east-1...  # Default fallback queue
WEBSOCKET_URL=wss://test.example.com... # WebSocket endpoint (not used in integration tests)
```

**Note:** Tests dynamically switch `ENVIRONMENT_NAME` to test different routing scenarios.

## Test Features

### ✅ Environment Switching
Tests can dynamically change the environment context to test different routing behaviors:

```javascript
const originalEnv = process.env.ENVIRONMENT_NAME;
process.env.ENVIRONMENT_NAME = 'gpu';  // Switch to GPU environment
// ... run tests ...
process.env.ENVIRONMENT_NAME = originalEnv;  // Restore
```

### ✅ Realistic Data Validation
Uses actual compiler IDs and routing data from the production system:

- `gimpleesp32g20230208` - Production compiler with queue routing
- `nvcc129u1` - GPU compiler with URL routing
- Non-existent compiler IDs for fallback testing

### ✅ Error Handling Verification
Tests graceful degradation when AWS services are unavailable or return errors.

### ✅ Performance Measurement
Integration tests include timeouts (10-15 seconds) to ensure reasonable response times from real AWS services.

## Benefits of Integration Testing

### 🎯 Real-World Validation
- Verifies actual AWS permissions and connectivity
- Tests with production routing data and queue configurations
- Validates AWS SDK integration and error handling

### 🔍 Environment-Specific Logic
- Tests composite key routing (environment isolation)
- Verifies fallback logic with legacy routing entries
- Validates queue URL construction with real account IDs

### 🐛 Early Issue Detection
- Catches AWS configuration problems before deployment
- Identifies DynamoDB schema or permission issues
- Validates SQS queue URLs and message formatting

### 📊 Production Compatibility
- Tests with real compiler IDs and routing configurations
- Verifies message format matches consumer expectations
- Validates response structures for ALB integration

## Running Integration Tests

### Prerequisites
- AWS credentials configured (via AWS CLI, environment variables, or IAM roles)
- Access to `CompilerRouting` DynamoDB table in `us-east-1`
- Appropriate IAM permissions:
  - `dynamodb:GetItem` on `CompilerRouting` table

### Execution
```bash
cd /opt/compiler-explorer/infra/compilation-lambda
npm run test:integration
```

### Expected Output
```
Integration Tests - Real AWS Services
  AWS Account Identity
    ✓ should get real AWS account ID from STS (457 ms)
  DynamoDB Compiler Routing
    ✓ should lookup prod compiler with queue routing (430 ms)
    ✓ should lookup GPU compiler with URL routing (100 ms)
    ✓ should handle non-existent compiler gracefully (201 ms)
    ✓ should handle composite key lookup (environment-prefixed) (106 ms)
    ✓ should construct correct queue URL from DynamoDB data (104 ms)
  [... more test results ...]

✓ Compiler gimpleesp32g20230208 routed to: https://sqs.us-east-1.amazonaws.com/052730242331/prod-compilation-queue
✓ Compiler nvcc129u1 routed to: https://godbolt.org/gpu/api/compiler/nvcc129u1/compile

Test Suites: 1 passed, 1 total
Tests: 20 passed, 20 total
```

## Troubleshooting

### Common Issues

**AWS Credentials Not Found**
```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
# OR use aws configure
```

**DynamoDB Access Denied**
- Verify IAM permissions include `dynamodb:GetItem` on `CompilerRouting` table
- Check AWS region matches `us-east-1`


**Test Timeouts**
- Increase test timeout values if AWS services are slow
- Check network connectivity to AWS services

### Debug Mode
Add console logging to see real AWS responses:
```javascript
console.log('DynamoDB response:', JSON.stringify(result, null, 2));
```

## Best Practices

1. **Run integration tests before deployments** to catch AWS configuration issues
2. **Keep test data current** by periodically reviewing compiler routing entries
3. **Monitor test performance** - slow tests may indicate AWS service issues
4. **Use separate test environment** when possible to avoid production data dependencies
5. **Document expected test compiler IDs** if routing data changes frequently

## Future Enhancements

- **WebSocket Integration Tests** - Test real WebSocket connections (requires live events system)
- **Cross-Region Testing** - Test routing behavior in different AWS regions
- **Performance Benchmarks** - Measure and track AWS service response times
- **Automated Test Data Management** - Populate test routing entries programmatically
