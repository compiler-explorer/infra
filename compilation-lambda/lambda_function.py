import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional

import boto3
import requests
import websocket
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.WARNING)

# Environment variables with defaults
RETRY_COUNT = int(os.environ.get("RETRY_COUNT", "1"))
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "60"))
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
WEBSOCKET_URL = os.environ.get("WEBSOCKET_URL", "")
ENVIRONMENT_NAME = os.environ.get("ENVIRONMENT_NAME", "unknown")

# Initialize AWS clients
sqs = boto3.client("sqs")
dynamodb = boto3.client("dynamodb")

# DynamoDB table for compiler routing
COMPILER_ROUTING_TABLE = "CompilerRouting"


class CompilationError(Exception):
    """Base exception for compilation-related errors."""

    pass


class WebSocketTimeoutError(CompilationError):
    """Raised when WebSocket response times out."""

    pass


class SQSError(CompilationError):
    """Raised when SQS operations fail."""

    pass


class URLForwardingError(CompilationError):
    """Raised when URL forwarding fails."""

    pass


def generate_guid() -> str:
    """Generate a unique GUID for request tracking."""
    return str(uuid.uuid4())


def extract_compiler_id(path: str) -> Optional[str]:
    """
    Extract compiler ID from ALB request path.
    Expected paths:
    - Production: /api/compiler/{compiler_id}/compile or /api/compiler/{compiler_id}/cmake
    - Other envs: /{env}/api/compiler/{compiler_id}/compile or /{env}/api/compiler/{compiler_id}/cmake
    """
    try:
        path_parts = path.strip("/").split("/")

        # Production format: /api/compiler/{compiler_id}/compile
        if len(path_parts) >= 4 and path_parts[0] == "api" and path_parts[1] == "compiler":
            return path_parts[2]

        # Other environments format: /{env}/api/compiler/{compiler_id}/compile
        if len(path_parts) >= 5 and path_parts[1] == "api" and path_parts[2] == "compiler":
            return path_parts[3]

    except (IndexError, AttributeError):
        pass
    return None


def is_cmake_request(path: str) -> bool:
    """Check if the request is for cmake compilation."""
    return path.endswith("/cmake")


def parse_request_body(body: str, content_type: str) -> Dict[str, Any]:
    """
    Parse request body based on content type.
    Supports both JSON and plain text (for source code).
    """
    if not body:
        return {}

    # Check if content type indicates JSON
    if content_type and "application/json" in content_type.lower():
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON body, treating as plain text")
            return {"source": body}
    else:
        # Plain text body - treat as source code
        return {"source": body}


def lookup_compiler_routing(compiler_id: str) -> Dict[str, Any]:
    """
    Look up routing information for a specific compiler using DynamoDB.
    Returns routing decision with type and target information.
    Uses environment-prefixed composite key for isolation.
    """
    try:
        # Create composite key with environment prefix for isolation
        composite_key = f"{ENVIRONMENT_NAME}#{compiler_id}"

        # Look up compiler in DynamoDB routing table using composite key
        response = dynamodb.get_item(TableName=COMPILER_ROUTING_TABLE, Key={"compilerId": {"S": composite_key}})

        item = response.get("Item")
        if not item:
            # Fallback: try old format (without environment prefix) for backward compatibility
            logger.info(f"Composite key not found for {composite_key}, trying legacy format")
            fallback_response = dynamodb.get_item(
                TableName=COMPILER_ROUTING_TABLE, Key={"compilerId": {"S": compiler_id}}
            )
            item = fallback_response.get("Item")
            if item:
                logger.warning(f"Using legacy routing entry for {compiler_id} - consider migration")

        if item:
            routing_type = item.get("routingType", {}).get("S", "queue")

            if routing_type == "url":
                target_url = item.get("targetUrl", {}).get("S", "")
                if target_url:
                    logger.info(f"Compiler {compiler_id} routed to URL: {target_url}")
                    return {
                        "type": "url",
                        "target": target_url,
                        "environment": item.get("environment", {}).get("S", ""),
                    }
            else:
                # Queue routing
                queue_name = item.get("queueName", {}).get("S")
                if queue_name:
                    # Convert queue name to queue URL
                    account_id = boto3.client("sts").get_caller_identity()["Account"]
                    region = boto3.Session().region_name or "us-east-1"

                    # Handle both FIFO and standard queues
                    if queue_name.endswith(".fifo"):
                        queue_url = f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"
                    else:
                        queue_url = f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"

                    logger.info(f"Compiler {compiler_id} routed to queue: {queue_name}")
                    return {
                        "type": "queue",
                        "target": queue_url,
                        "environment": item.get("environment", {}).get("S", ""),
                    }

        # No routing found, use default queue
        logger.info(f"No routing found for compiler {compiler_id}, using default queue")
        return {
            "type": "queue",
            "target": SQS_QUEUE_URL,
            "environment": "unknown",
        }

    except Exception as e:
        # On any error, fall back to default queue
        logger.warning(f"Failed to lookup routing for compiler {compiler_id}: {e}")
        return {
            "type": "queue",
            "target": SQS_QUEUE_URL,
            "environment": "unknown",
        }


def send_to_sqs(
    guid: str, compiler_id: str, body: str, is_cmake: bool, headers: Dict[str, str], queue_url: str
) -> None:
    """Send compilation request to SQS queue as RemoteCompilationRequest."""
    if not queue_url:
        raise SQSError("No queue URL available (neither DynamoDB lookup nor SQS_QUEUE_URL env var set)")

    # Parse body based on content type
    content_type = headers.get("content-type", headers.get("Content-Type", ""))
    request_data = parse_request_body(body, content_type)

    if not isinstance(request_data, dict):
        logger.warning(f"Request data is not a dict: {str(request_data)[:100]}...")

    # Start with Lambda-specific fields
    message_body = {
        "guid": guid,
        "compilerId": compiler_id,
        "isCMake": is_cmake,
        "headers": headers,  # Preserve original headers for response formatting
    }

    # Merge all fields from the original request first (preserves original values)
    message_body.update(request_data)

    # Add defaults for fields that are required by the consumer but might be missing
    if "source" not in message_body:
        message_body["source"] = ""
    if "options" not in message_body:
        message_body["options"] = []
    if "filters" not in message_body:
        message_body["filters"] = {}
    if "backendOptions" not in message_body:
        message_body["backendOptions"] = {}
    if "tools" not in message_body:
        message_body["tools"] = []
    if "libraries" not in message_body:
        message_body["libraries"] = []
    if "files" not in message_body:
        message_body["files"] = []
    if "executeParameters" not in message_body:
        message_body["executeParameters"] = {}

    try:
        # Ensure we're sending a proper JSON string (not double-encoded)
        if isinstance(message_body, str):
            logger.warning("Message body is already a string - this might cause double encoding")
            message_json = message_body
        else:
            message_json = json.dumps(message_body, separators=(",", ":"))

        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=message_json,
            MessageGroupId="default",
            MessageDeduplicationId=guid,
        )

    except (TypeError, ValueError) as e:
        logger.error(f"Failed to JSON encode message body: {e}")
        raise SQSError(f"Failed to JSON encode message: {e}") from e
    except ClientError as e:
        logger.error(f"Failed to send message to SQS: {e}")
        raise SQSError(f"Failed to send message to SQS: {e}") from e


def forward_to_environment_url(
    compiler_id: str, url: str, body: str, is_cmake: bool, headers: Dict[str, str]
) -> Dict[str, Any]:
    """Forward compilation request directly to environment URL.

    Args:
        compiler_id: Compiler identifier
        url: Target URL for forwarding
        body: Request body
        is_cmake: Whether this is a cmake request
        headers: Original request headers

    Returns:
        Response from the target environment

    Raises:
        URLForwardingError: If forwarding fails
    """
    try:
        # Adjust URL for cmake vs compile endpoint
        if is_cmake and not url.endswith("/cmake"):
            if url.endswith("/compile"):
                url = url.replace("/compile", "/cmake")
            else:
                url = f"{url}/cmake" if not url.endswith("/") else f"{url}cmake"
        elif not is_cmake and not url.endswith("/compile"):
            if url.endswith("/cmake"):
                url = url.replace("/cmake", "/compile")
            else:
                url = f"{url}/compile" if not url.endswith("/") else f"{url}compile"

        # Prepare headers for forwarding (filter out ALB-specific headers)
        forward_headers = {}
        for key, value in headers.items():
            if key.lower() not in ["host", "x-forwarded-for", "x-forwarded-proto", "x-forwarded-port"]:
                forward_headers[key] = value

        # Set appropriate content type if not already set
        if "content-type" not in forward_headers and "Content-Type" not in forward_headers:
            try:
                # Try to parse as JSON first
                json.loads(body)
                forward_headers["Content-Type"] = "application/json"
            except (json.JSONDecodeError, TypeError):
                # Fallback to plain text
                forward_headers["Content-Type"] = "text/plain"

        logger.info(f"Forwarding request to {url}")

        # Make the HTTP request to the target environment
        response = requests.post(
            url,
            data=body,
            headers=forward_headers,
            timeout=60,  # 60 second timeout
        )

        # Check if the request was successful
        response.raise_for_status()

        # Return the response content and headers
        return {
            "statusCode": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
        }

    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout forwarding to {url}: {e}")
        raise URLForwardingError(f"Request timeout: {e}") from e
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error forwarding to {url}: {e}")
        # For HTTP errors, still return the response to preserve error details
        return {
            "statusCode": e.response.status_code if e.response else 500,
            "headers": dict(e.response.headers) if e.response else {},
            "body": e.response.text if e.response else str(e),
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error forwarding to {url}: {e}")
        raise URLForwardingError(f"Request failed: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error forwarding to {url}: {e}")
        raise URLForwardingError(f"Unexpected error: {e}") from e


class WebSocketClient:
    """WebSocket client for receiving compilation results."""

    def __init__(self, url: str, guid: str):
        self.url = url
        self.guid = guid
        self.ws = None
        self.result = None
        self.connected = False

    def on_open(self, ws):
        """Called when WebSocket connection opens."""
        self.connected = True
        # Subscribe to messages for this GUID
        subscribe_msg = f"subscribe: {self.guid}"
        ws.send(subscribe_msg)

    def on_message(self, ws, message):
        """Called when WebSocket receives a message."""
        try:
            data = json.loads(message)
            message_guid = data.get("guid")

            if message_guid == self.guid:
                # The entire message IS the result
                self.result = data
                ws.close()
        except json.JSONDecodeError as e:
            logger.warning(f"Received invalid JSON message: {message[:100]}... Error: {e}")

    def on_error(self, ws, error):
        """Called when WebSocket encounters an error."""
        logger.error(f"WebSocket error for {self.guid}: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Called when WebSocket connection closes."""
        pass

    def connect_and_subscribe(self):
        """Connect to WebSocket and subscribe to GUID (doesn't wait for result)."""
        if not self.url:
            raise CompilationError("WEBSOCKET_URL environment variable not set")

        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(
            self.url, on_open=self.on_open, on_message=self.on_message, on_error=self.on_error, on_close=self.on_close
        )

        if self.ws is None:
            raise CompilationError("WebSocket client not initialized")

    def wait_for_result(self, timeout: int) -> Dict[str, Any]:
        """Wait for compilation result on already-connected WebSocket."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.result is not None:
                if self.ws:
                    self.ws.close()
                return self.result
            time.sleep(0.1)

        # Timeout reached
        logger.error(f"WebSocket timeout for {self.guid} after {timeout}s")
        if self.ws:
            self.ws.close()
        raise WebSocketTimeoutError(f"No response received within {timeout} seconds")

    def connect_and_wait(self, timeout: int) -> Dict[str, Any]:
        """Connect to WebSocket and wait for result."""
        if not self.url:
            raise CompilationError("WEBSOCKET_URL environment variable not set")

        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(
            self.url, on_open=self.on_open, on_message=self.on_message, on_error=self.on_error, on_close=self.on_close
        )

        # Start WebSocket in a separate thread and wait for result
        if self.ws is not None:
            ws_thread = threading.Thread(target=self.ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
        else:
            raise CompilationError("WebSocket client not initialized")

        # Wait for connection and result
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.result is not None:
                return self.result
            time.sleep(0.1)

        # Timeout reached
        logger.error(f"WebSocket timeout for {self.guid} after {timeout}s")
        if self.ws:
            self.ws.close()
        raise WebSocketTimeoutError(f"No response received within {timeout} seconds")


def wait_for_compilation_result(guid: str, timeout: int) -> Dict[str, Any]:
    """Wait for compilation result via WebSocket with retry logic."""
    last_error = None

    for attempt in range(RETRY_COUNT + 1):
        try:
            client = WebSocketClient(WEBSOCKET_URL, guid)
            return client.connect_and_wait(timeout)
        except Exception as e:
            last_error = e
            if attempt < RETRY_COUNT:
                time.sleep(1)  # Brief delay before retry

    raise last_error or CompilationError("All WebSocket attempts failed")


def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Create an ALB-compatible error response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps({"error": message}),
    }


def create_success_response(result: Dict[str, Any], accept_header: str) -> Dict[str, Any]:
    """
    Create an ALB-compatible success response.
    Response format depends on Accept header.
    """
    # Determine response format based on Accept header
    if accept_header and "text/plain" in accept_header.lower():
        # Plain text response - typically just the assembly output
        body = ""
        if "asm" in result:
            # Join assembly lines
            body = "\n".join(line.get("text", "") for line in result.get("asm", []))
        elif "stdout" in result:
            # Fallback to stdout if no asm
            body = "\n".join(result.get("stdout", []))

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/plain; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST",
                "Access-Control-Allow-Headers": "Content-Type, Accept",
            },
            "body": body,
        }
    else:
        # Default to JSON response
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST",
                "Access-Control-Allow-Headers": "Content-Type, Accept",
            },
            "body": json.dumps(result),
        }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for compilation requests.
    Handles ALB requests for /api/compilers/{compiler_id}/compile and /api/compilers/{compiler_id}/cmake
    """
    try:
        # Parse ALB request
        path = event.get("path", "")
        method = event.get("httpMethod", "")
        body = event.get("body", "")
        headers = event.get("headers", {})

        # Validate request method
        if method != "POST":
            return create_error_response(405, "Method not allowed")

        # Extract compiler ID from path
        compiler_id = extract_compiler_id(path)
        if not compiler_id:
            return create_error_response(400, "Invalid path: compiler ID not found")

        # Check if this is a cmake request
        is_cmake = is_cmake_request(path)

        # Generate unique GUID for this request
        guid = generate_guid()

        # Determine routing strategy for this compiler
        routing_info = lookup_compiler_routing(compiler_id)

        if routing_info["type"] == "url":
            # Direct URL forwarding - no WebSocket needed
            try:
                response = forward_to_environment_url(compiler_id, routing_info["target"], body, is_cmake, headers)

                # Create ALB-compatible response
                response_headers = response.get("headers", {})
                # Ensure CORS headers are present
                response_headers.update(
                    {
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "POST",
                        "Access-Control-Allow-Headers": "Content-Type, Accept",
                    }
                )

                return {
                    "statusCode": response.get("statusCode", 200),
                    "headers": response_headers,
                    "body": response.get("body", ""),
                }

            except URLForwardingError as e:
                logger.error(f"URL forwarding error: {e}")
                return create_error_response(500, f"Failed to forward request: {str(e)}")

        # Queue-based routing - continue with existing WebSocket flow
        queue_url = routing_info["target"]

        # First, establish WebSocket connection and subscribe to the GUID
        # This ensures we're ready to receive the result before sending to SQS
        try:
            ws_client = WebSocketClient(WEBSOCKET_URL, guid)

            # Initialize the WebSocket app
            websocket.enableTrace(False)
            ws_client.ws = websocket.WebSocketApp(
                ws_client.url,
                on_open=ws_client.on_open,
                on_message=ws_client.on_message,
                on_error=ws_client.on_error,
                on_close=ws_client.on_close,
            )

            # Start the WebSocket connection in a separate thread using run_forever
            if ws_client.ws is not None:
                ws_thread = threading.Thread(target=ws_client.ws.run_forever)
                ws_thread.daemon = True
                ws_thread.start()
            else:
                raise CompilationError("WebSocket client not initialized")

            # Wait a moment to ensure subscription is established
            start_time = time.time()
            while not ws_client.connected and time.time() - start_time < 5:
                time.sleep(0.1)

            if not ws_client.connected:
                raise CompilationError("Failed to establish WebSocket connection within 5 seconds")

        except Exception as e:
            logger.error(f"Failed to setup WebSocket subscription: {e}")
            return create_error_response(500, f"Failed to setup result subscription: {str(e)}")

        # Now send request to SQS queue with headers
        try:
            send_to_sqs(guid, compiler_id, body, is_cmake, headers, queue_url)
        except SQSError as e:
            logger.error(f"SQS error: {e}")
            try:
                if ws_client and ws_client.ws:
                    ws_client.ws.close()
            except Exception:
                pass
            return create_error_response(500, f"Failed to queue compilation request: {str(e)}")

        # Wait for compilation result via the already-connected WebSocket
        try:
            result = ws_client.wait_for_result(TIMEOUT_SECONDS)

            # Get Accept header for response formatting
            accept_header = headers.get("accept", headers.get("Accept", ""))
            return create_success_response(result, accept_header)

        except WebSocketTimeoutError as e:
            logger.error(f"Timeout waiting for compilation result: {e}")
            try:
                if ws_client and ws_client.ws:
                    ws_client.ws.close()
            except Exception:
                pass
            return create_error_response(408, f"Compilation timeout: {str(e)}")

        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            try:
                if ws_client and ws_client.ws:
                    ws_client.ws.close()
            except Exception:
                pass
            return create_error_response(500, f"Failed to receive compilation result: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {e}")
        return create_error_response(500, f"Internal server error: {str(e)}")
