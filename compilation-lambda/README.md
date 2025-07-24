# Compilation Lambda

This Lambda function handles compilation requests for Compiler Explorer by:

1. Accepting POST requests to `/api/compiler/{compiler_id}/compile` and `/api/compiler/{compiler_id}/cmake`
2. Extracting the compiler ID from the URL path
3. Generating a unique GUID for request tracking
4. Sending the request to an SQS queue for processing
5. Waiting for compilation results via WebSocket
6. Returning the compilation results to the client

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

## Testing

Run unit tests with:

```bash
python -m pytest test_lambda_function.py -v
```

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
