import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

import boto3
import websocket
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables with defaults
RETRY_COUNT = int(os.environ.get("RETRY_COUNT", "1"))
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "60"))
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
WEBSOCKET_URL = os.environ.get("WEBSOCKET_URL", "")

# Initialize AWS clients
sqs = boto3.client("sqs")


class CompilationError(Exception):
    """Base exception for compilation-related errors."""

    pass


class WebSocketTimeoutError(CompilationError):
    """Raised when WebSocket response times out."""

    pass


class SQSError(CompilationError):
    """Raised when SQS operations fail."""

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


def send_to_sqs(guid: str, compiler_id: str, body: str, is_cmake: bool, headers: Dict[str, str]) -> None:
    """Send compilation request to SQS queue with headers preserved."""
    if not SQS_QUEUE_URL:
        raise SQSError("SQS_QUEUE_URL environment variable not set")

    # Parse body based on content type
    content_type = headers.get("content-type", headers.get("Content-Type", ""))
    request_data = parse_request_body(body, content_type)

    message_body = {
        "guid": guid,
        "compilerId": compiler_id,
        "isCMake": is_cmake,
        "request": request_data,
        "headers": headers,  # Preserve original headers for response formatting
    }

    try:
        sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(message_body),
            MessageGroupId="default",
            MessageDeduplicationId=guid,
        )
        logger.info(f"Sent compilation request {guid} to SQS queue")
    except ClientError as e:
        logger.error(f"Failed to send message to SQS: {e}")
        raise SQSError(f"Failed to send message to SQS: {e}") from e


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
        logger.info(f"WebSocket connected for {self.guid}")
        self.connected = True
        # Subscribe to messages for this GUID
        subscribe_msg = json.dumps({"action": "subscribe", "guid": self.guid})
        ws.send(subscribe_msg)

    def on_message(self, ws, message):
        """Called when WebSocket receives a message."""
        try:
            data = json.loads(message)
            if data.get("guid") == self.guid:
                logger.info(f"Received result for {self.guid}")
                self.result = data.get("result")
                ws.close()
        except json.JSONDecodeError:
            logger.warning(f"Received invalid JSON message: {message}")

    def on_error(self, ws, error):
        """Called when WebSocket encounters an error."""
        logger.error(f"WebSocket error for {self.guid}: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Called when WebSocket connection closes."""
        logger.info(f"WebSocket closed for {self.guid}")

    def connect_and_wait(self, timeout: int) -> Dict[str, Any]:
        """Connect to WebSocket and wait for result."""
        if not self.url:
            raise CompilationError("WEBSOCKET_URL environment variable not set")

        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(
            self.url, on_open=self.on_open, on_message=self.on_message, on_error=self.on_error, on_close=self.on_close
        )

        # Start WebSocket in a separate thread and wait for result
        import threading

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
            logger.warning(f"WebSocket attempt {attempt + 1} failed: {e}")
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

        logger.info(f"Processing {method} request to {path}")

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
        logger.info(f"Generated GUID {guid} for compiler {compiler_id}")

        # Send request to SQS queue with headers
        try:
            send_to_sqs(guid, compiler_id, body, is_cmake, headers)
        except SQSError as e:
            logger.error(f"SQS error: {e}")
            return create_error_response(500, f"Failed to queue compilation request: {str(e)}")

        # Wait for compilation result via WebSocket
        try:
            result = wait_for_compilation_result(guid, TIMEOUT_SECONDS)
            logger.info(f"Compilation {guid} completed successfully")

            # Get Accept header for response formatting
            accept_header = headers.get("accept", headers.get("Accept", ""))
            return create_success_response(result, accept_header)

        except WebSocketTimeoutError as e:
            logger.error(f"Timeout waiting for compilation result: {e}")
            return create_error_response(408, f"Compilation timeout: {str(e)}")

        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            return create_error_response(500, f"Failed to receive compilation result: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {e}")
        return create_error_response(500, f"Internal server error: {str(e)}")
