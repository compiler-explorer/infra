# Compilation Lambda

This Node.js Lambda function handles compilation requests for Compiler Explorer with improved performance over the previous Python implementation.

## Performance Benefits

- **2-3x Faster Cold Starts**: Node.js Lambda functions start significantly faster than Python
- **Better Concurrency**: Event loop model handles concurrent WebSocket connections more efficiently
- **Lower Memory Usage**: Reduced memory allocation for similar workloads
- **Faster JSON Processing**: V8's optimized JSON parsing outperforms Python's json module

## Architecture

The lambda handles two routing strategies:

1. **Queue-based routing**: Sends requests to SQS queues and waits for results via WebSocket
2. **URL forwarding**: Directly forwards requests to environment-specific URLs (Windows, GPU, ARM environments)

## Request Flow

1. ALB receives POST request to `/api/compiler/{compiler_id}/compile` or `/api/compiler/{compiler_id}/cmake`
2. Lambda queries DynamoDB for compiler routing configuration
3. **Queue routing**: Sends to SQS queue and waits for WebSocket result
4. **URL routing**: Forwards directly to target environment URL
5. Returns formatted response to client

## Environment Variables

- `RETRY_COUNT` (default: 1) - Number of WebSocket connection retry attempts
- `TIMEOUT_SECONDS` (default: 60) - Timeout for WebSocket response in seconds
- `SQS_QUEUE_URL` - URL of the SQS FIFO queue for compilation requests
- `WEBSOCKET_URL` - URL of the WebSocket endpoint for receiving results

## Logging

The Lambda uses WARNING level logging by default for optimal performance. Only errors, warnings, and critical issues are logged to CloudWatch.

## Request Flow

1. ALB receives POST request to `/api/compiler/{compiler_id}/compile` or `/api/compiler/{compiler_id}/cmake`
2. Lambda extracts `compiler_id` from URL path
3. Lambda generates unique GUID for tracking
4. Lambda connects to WebSocket and subscribes to messages for the GUID
5. Lambda wraps request body with GUID, compiler ID, and cmake flag
6. Lambda sends message to SQS queue
7. Worker processes compilation and sends result to WebSocket
8. Lambda receives result and returns it to client

## Error Handling

- **400 Bad Request**: Invalid path or missing compiler ID
- **405 Method Not Allowed**: Non-POST requests
- **408 Request Timeout**: No response received within timeout period
- **500 Internal Server Error**: SQS failures, WebSocket errors, or other exceptions

## Development

### Installing Dependencies

```bash
npm install
```

### Running Tests

```bash
npm test
npm run test:coverage
```

### Building Lambda Package

From the infra root directory:

```bash
make compilation-lambda-package
```

This creates a deterministic ZIP package for deployment.

## Message Format

SQS message body:
```json
{
  "guid": "uuid-string",
  "compilerId": "gcc12",
  "isCMake": false,
  "headers": {"Content-Type": "application/json"},
  "source": "int main() { return 0; }",
  "options": ["-O2"],
  "filters": {},
  "libraries": [],
  "backendOptions": {},
  "tools": [],
  "files": [],
  "executeParameters": {}
}
```

WebSocket subscription:
```
subscribe: uuid-string
```

WebSocket result:
```json
{
  "guid": "uuid-string",
  "code": 0,
  "stdout": ["Hello World"],
  "stderr": [],
  "asm": []
}
```
