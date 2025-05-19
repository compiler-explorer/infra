import argparse
import functools
import http.server
import json
import logging
import os
import socketserver
import sys
from typing import Dict, List, Optional, Tuple, Union

import anthropic
import boto3
from anthropic import Anthropic

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("explain")


# AWS clients are initialized on demand with caching to make testing easier
@functools.cache
def get_ssm_client():
    """Get or initialize SSM client"""
    return boto3.client("ssm")


# Constants
MAX_CODE_LENGTH = 10000  # 10K chars should be enough for most source files
MAX_ASM_LENGTH = 20000  # 20K chars for assembly output
MAX_ASSEMBLY_LINES = 300  # Maximum number of assembly lines to process
MODEL = "claude-3-haiku-20240307"
MAX_TOKENS = 1024  # Adjust based on desired explanation length
PARAM_NAME = "/ce/claude/api-key"  # Stored in Parameter Store

# Claude token costs (USD)
# As of May 2024, these are the costs for Claude 3 Haiku
# Update if model or pricing changes
COST_PER_INPUT_TOKEN = 0.00000025  # $0.25/1M tokens
COST_PER_OUTPUT_TOKEN = 0.00000125  # $1.25/1M tokens


def get_anthropic_client(api_key=None) -> Anthropic:
    """Get or initialize Anthropic client with API key.

    Args:
        api_key: Optional API key to use instead of retrieving from SSM
    """
    try:
        # Use provided API key if available (for local dev)
        if api_key:
            logger.info("Using provided API key")
            return Anthropic(api_key=api_key)
        else:
            # Otherwise get from SSM (for lambda)
            response = get_ssm_client().get_parameter(Name=PARAM_NAME, WithDecryption=True)
            api_key = response["Parameter"]["Value"]
            logger.info("Using API key from SSM Parameter Store")
            return Anthropic(api_key=api_key)
    except Exception as e:
        logger.error(f"Error creating Anthropic client: {type(e).__name__}: {str(e)}")
        raise


def create_response(status_code: int = 200, body: Optional[Union[Dict, List, str]] = None) -> Dict:
    """Create a standardized API response."""
    # Default CORS headers for browser access
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    response = {
        "statusCode": status_code,
        "headers": default_headers,
    }

    # Add body if provided
    if body is not None:
        if isinstance(body, dict) or isinstance(body, list):
            response["body"] = json.dumps(body)
        else:
            response["body"] = body

    return response


def handle_error(error: Exception, is_internal: bool = False) -> Dict:
    """Centralized error handler that logs and creates error responses."""
    if is_internal:
        print(f"Unexpected error: {str(error)}")
        return create_response(status_code=500, body={"status": "error", "message": "Internal server error"})
    else:
        print(f"Error: {str(error)}")
        return create_response(status_code=500, body={"status": "error", "message": str(error)})


def validate_input(body: Dict) -> Tuple[bool, str]:
    """Validate the input request body."""
    required_fields = ["language", "compiler", "code", "asm"]
    for field in required_fields:
        if field not in body:
            return False, f"Missing required field: {field}"

    # Validate code length
    if len(body.get("code", "")) > MAX_CODE_LENGTH:
        return False, f"Source code exceeds maximum length of {MAX_CODE_LENGTH} characters"

    # Validate assembly format
    if not isinstance(body.get("asm", []), list):
        return False, "Assembly must be an array"

    # Check if assembly array is empty
    if len(body.get("asm", [])) == 0:
        return False, "Assembly array cannot be empty"

    return True, ""


def select_important_assembly(
    asm_array: List[Dict], label_definitions: Dict, max_lines: int = MAX_ASSEMBLY_LINES
) -> List[Dict]:
    """Select the most important assembly lines if the output is too large.

    This function identifies and preserves:
    1. Function boundaries (entry points and returns)
    2. Instructions with source mappings
    3. Important contextual instructions
    """
    if len(asm_array) <= max_lines:
        return asm_array

    # Identify important blocks (function boundaries, etc.)
    important_indices = set()

    # Mark label definitions as important
    for _label, line_idx in label_definitions.items():
        if isinstance(line_idx, int) and 0 <= line_idx < len(asm_array):
            # Add the label line and a few lines after it (function prologue)
            for i in range(line_idx, min(line_idx + 5, len(asm_array))):
                important_indices.add(i)

    # Mark function epilogues and lines with source mappings
    for idx, asm_item in enumerate(asm_array):
        if not isinstance(asm_item, dict) or "text" not in asm_item:
            continue

        # Source mapping makes this important
        if asm_item.get("source") and asm_item["source"] is not None:
            if isinstance(asm_item["source"], dict) and asm_item["source"].get("line") is not None:
                important_indices.add(idx)

        # Function returns and epilogues are important
        text = asm_item.get("text", "").strip()
        if text in ("ret", "leave", "pop rbp") or text.startswith("ret "):
            # Add the return line and a few lines before it
            for i in range(max(0, idx - 3), idx + 1):
                important_indices.add(i)

    # Also include context around important lines
    context_indices = set()
    for idx in important_indices:
        # Add a few lines before and after for context
        for i in range(max(0, idx - 2), min(len(asm_array), idx + 3)):
            context_indices.add(i)

    # Combine all important indices
    all_indices = important_indices.union(context_indices)

    # If we still have too many lines, prioritize
    if len(all_indices) > max_lines:
        # Prioritize function boundaries and source mappings over context
        important_indices_list = sorted(list(important_indices))
        all_indices = set(important_indices_list[:max_lines])

    # Collect selected assembly items
    selected_assembly = []

    # Sort indices to maintain original order
    sorted_indices = sorted(all_indices)

    # Find gaps and add "omitted" markers
    last_idx = -2
    for idx in sorted_indices:
        if idx > last_idx + 1:
            # There's a gap, add a special marker
            selected_assembly.append(
                {"text": f"... ({idx - last_idx - 1} lines omitted) ...", "isOmissionMarker": True}
            )

        # Add the actual assembly item
        if 0 <= idx < len(asm_array):
            selected_assembly.append(asm_array[idx])

        last_idx = idx

    # Add a final omission marker if needed
    if last_idx < len(asm_array) - 1:
        selected_assembly.append(
            {"text": f"... ({len(asm_array) - last_idx - 1} lines omitted) ...", "isOmissionMarker": True}
        )

    return selected_assembly


def prepare_structured_data(body: Dict) -> Dict:
    """Prepare a structured JSON object for Claude's consumption."""
    # Extract and validate basic fields
    structured_data = {
        "language": body["language"],
        "compiler": body["compiler"],
        "sourceCode": body["code"],
        "instructionSet": body.get("instructionSet", "unknown"),
    }

    # Format compilation options
    comp_options = body.get("compilationOptions", [])
    if isinstance(comp_options, list):
        structured_data["compilationOptions"] = comp_options
    else:
        structured_data["compilationOptions"] = [str(comp_options)]

    # Process assembly array
    asm_array = body.get("asm", [])
    if len(asm_array) > MAX_ASSEMBLY_LINES:
        # If assembly is too large, we need smart truncation
        structured_data["assembly"] = select_important_assembly(asm_array, body.get("labelDefinitions", {}))
        structured_data["truncated"] = True
        structured_data["originalLength"] = len(asm_array)
    else:
        # Use the full assembly if it's within limits
        structured_data["assembly"] = asm_array
        structured_data["truncated"] = False

    # Include label definitions
    structured_data["labelDefinitions"] = body.get("labelDefinitions", {})

    # Add compiler messages if available
    stderr = body.get("stderr", [])
    if stderr and isinstance(stderr, list):
        structured_data["compilerMessages"] = stderr
    else:
        structured_data["compilerMessages"] = []

    # Add optimization remarks if available
    opt_output = body.get("optimizationOutput", [])
    if opt_output and isinstance(opt_output, list):
        structured_data["optimizationRemarks"] = opt_output
    else:
        structured_data["optimizationRemarks"] = []

    return structured_data


def process_request(body: Dict, api_key: Optional[str] = None) -> Dict:
    """Process a request and return the response.

    This is the core processing logic, separated from the lambda_handler
    to allow for reuse in the local server mode.

    Args:
        body: The request body as a dictionary
        api_key: Optional API key for local development mode

    Returns:
        A response dictionary with status and explanation
    """
    try:
        # Validate input
        valid, error_message = validate_input(body)
        if not valid:
            return create_response(status_code=400, body={"status": "error", "message": error_message})

        language = body["language"]
        arch = body.get("instructionSet", "")

        structured_data = prepare_structured_data(body)

        system_prompt = f"""You are an expert in {arch} assembly code and {language}, helping users of the Compiler Explorer website understand how their code compiles to assembly.
The request will be in the form of a JSON document, which explains a source program and how it was compiled, and the resulting assembly code that was generated.
Provide clear, concise explanations. Focus on key transformations, optimizations, and important assembly patterns.
Explanations should be educational and highlight why certain code constructs generate specific assembly instructions.
Give no commentary on the original source: it is expected the user already understands their input, and is only looking for guidance on the assembly output.
If it makes it easiest to explain, note the corresponding parts of the source code, but do not focus on this.
Do not give an overall conclusion."""

        # Call Claude API with JSON structure
        try:
            client = get_anthropic_client(api_key)
            logger.info(f"Using Anthropic client with model: {MODEL}")

            message = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Explain the {arch} assembly output.",
                            },
                            {"type": "text", "text": json.dumps(structured_data)},
                        ],
                    },
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "I have analysed the assembly code and my analysis is:",
                            },
                        ],
                    },
                ],
            )

            explanation = message.content[0].text

            # Extract usage information
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            total_tokens = input_tokens + output_tokens

            # Calculate costs
            input_cost = input_tokens * COST_PER_INPUT_TOKEN
            output_cost = output_tokens * COST_PER_OUTPUT_TOKEN
            total_cost = input_cost + output_cost

            # Construct the response with usage and cost information
            response_body = {
                "status": "success",
                "explanation": explanation,
                "model": MODEL,
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens},
                "cost": {
                    "input_cost": round(input_cost, 6),
                    "output_cost": round(output_cost, 6),
                    "total_cost": round(total_cost, 6),
                },
            }

        except Exception as e:
            logger.error(f"Error calling Claude API: {str(e)}")
            return create_response(500, {"status": "error", "message": f"Error calling Claude API: {str(e)}"})

        # Return success response
        return create_response(200, response_body)

    except json.JSONDecodeError:
        return create_response(400, {"status": "error", "message": "Invalid JSON in request body"})
    except Exception as e:
        return handle_error(e, is_internal=True)


def lambda_handler(event: Dict, context: object) -> Dict:
    """Handle Lambda invocation from API Gateway."""
    # Handle OPTIONS request (CORS preflight)
    if event.get("httpMethod") == "OPTIONS":
        return create_response(status_code=200, body={})

    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))
        return process_request(body)
    except json.JSONDecodeError:
        return create_response(400, {"status": "error", "message": "Invalid JSON in request body"})
    except Exception as e:
        return handle_error(e, is_internal=True)


class ExplainHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for local development."""

    def __init__(self, *args, api_key=None, **kwargs):
        self.api_key = api_key
        super().__init__(*args, **kwargs)

    def _set_headers(self, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_POST(self):
        if self.path == "/explain":
            try:
                content_length = int(self.headers["Content-Length"])
                post_data = self.rfile.read(content_length)

                try:
                    body = json.loads(post_data.decode("utf-8"))
                    response = process_request(body, self.api_key)

                    # Extract the statusCode and body from the lambda-style response
                    status_code = response.get("statusCode", 500)
                    response_body = response.get("body", "{}")

                    self._set_headers(status_code)
                    self.wfile.write(response_body.encode("utf-8"))
                except json.JSONDecodeError:
                    self._set_headers(400)
                    error_response = json.dumps({"status": "error", "message": "Invalid JSON in request body"})
                    self.wfile.write(error_response.encode("utf-8"))
                except Exception as e:
                    print(f"Exception during request processing: {str(e)}")
                    self._set_headers(500)
                    error_response = json.dumps({"status": "error", "message": str(e)})
                    self.wfile.write(error_response.encode("utf-8"))
            except BrokenPipeError:
                print("Client connection closed prematurely (broken pipe)")
            except Exception as e:
                print(f"HTTP handling exception: {str(e)}")
        else:
            try:
                self._set_headers(404)
                self.wfile.write(json.dumps({"status": "error", "message": "Not Found"}).encode("utf-8"))
            except BrokenPipeError:
                print("Client connection closed prematurely (broken pipe)")
            except Exception as e:
                print(f"HTTP response exception: {str(e)}")


class ExplainHTTPServer(socketserver.TCPServer):
    """HTTP server that passes API key to the handler."""

    def __init__(self, server_address, api_key=None):
        self.api_key = api_key
        # Allow address reuse to avoid "Address already in use" errors
        self.allow_reuse_address = True
        super().__init__(server_address, ExplainHandler)

    def finish_request(self, request, client_address):
        self.RequestHandlerClass(request, client_address, self, api_key=self.api_key)


def run_local_server(host="localhost", port=8080, api_key=None):
    """Run a local HTTP server for development and testing."""
    server = ExplainHTTPServer((host, port), api_key=api_key)
    print(f"Starting explain server on http://{host}:{port}/explain")
    print("Use Ctrl+C to stop the server")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    print("Server stopped")


def read_api_key_from_file(file_path):
    """Read the Claude API key from a file.

    Args:
        file_path: Path to the file containing the API key

    Returns:
        The API key as a string, with any whitespace stripped
    """
    try:
        with open(file_path, "r") as f:
            api_key = f.read().strip()
            if not api_key:
                raise ValueError("API key file is empty")
            return api_key
    except FileNotFoundError as fnf_error:
        raise FileNotFoundError(f"API key file not found: {file_path}") from fnf_error
    except Exception as e:
        raise Exception(f"Error reading API key from file: {str(e)}") from e


if __name__ == "__main__":
    # Clear any proxy environment variables to avoid issues with HTTPX client
    # used by the Anthropic library
    if "HTTP_PROXY" in os.environ:
        print("Removing HTTP_PROXY environment variable to avoid issues with Anthropic client")
        del os.environ["HTTP_PROXY"]
    if "HTTPS_PROXY" in os.environ:
        print("Removing HTTPS_PROXY environment variable to avoid issues with Anthropic client")
        del os.environ["HTTPS_PROXY"]
    if "http_proxy" in os.environ:
        print("Removing http_proxy environment variable to avoid issues with Anthropic client")
        del os.environ["http_proxy"]
    if "https_proxy" in os.environ:
        print("Removing https_proxy environment variable to avoid issues with Anthropic client")
        del os.environ["https_proxy"]

    parser = argparse.ArgumentParser(description="Claude Explain Service")
    parser.add_argument("--server", action="store_true", help="Run in local server mode")
    parser.add_argument("--host", default="localhost", help="Host for local server (default: localhost)")
    parser.add_argument("--port", type=int, default=8080, help="Port for local server (default: 8080)")
    parser.add_argument("--api-key-file", help="File containing the Claude API key (default: .claude-explain-key)")
    parser.add_argument("--model", help=f"Claude model to use (default: {MODEL})")
    parser.add_argument("--max-tokens", type=int, help=f"Maximum tokens for the explanation (default: {MAX_TOKENS})")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode with additional logging")

    args = parser.parse_args()

    # Override global settings if specified
    if args.model:
        MODEL = args.model
        print(f"Using model: {MODEL}")

    if args.max_tokens:
        MAX_TOKENS = args.max_tokens
        print(f"Max tokens set to: {MAX_TOKENS}")

    # Set up debug mode if requested
    DEBUG = args.debug
    if DEBUG:
        print("Debug mode enabled - detailed logging will be shown")
        # Print environment details
        print("\nEnvironment details:")
        print(f"Python version: {sys.version}")
        print(f"Current directory: {os.getcwd()}")
        print(f"Anthropic SDK version: {anthropic.__version__}")
        print("Environment variables:")
        for key in sorted(os.environ.keys()):
            if key.lower().startswith(("path", "python", "pwd", "ps", "term")):
                continue  # Skip long or irrelevant variables
            print(f"  {key}={os.environ[key]}")

    if args.server:
        api_key = None

        # Try the specified API key file
        if args.api_key_file:
            try:
                api_key = read_api_key_from_file(args.api_key_file)
                print(f"Using API key from file: {args.api_key_file}")
                if DEBUG:
                    print(f"API key loaded successfully (length: {len(api_key)})")
            except Exception as e:
                parser.error(str(e))

        # Otherwise, try the default file
        else:
            default_key_file = ".claude-explain-key"
            if os.path.exists(default_key_file):
                try:
                    api_key = read_api_key_from_file(default_key_file)
                    print(f"Using API key from default file: {default_key_file}")
                    if DEBUG:
                        print(f"API key loaded successfully (length: {len(api_key)})")
                except Exception as e:
                    parser.error(str(e))

        # If still no API key, show error
        if not api_key:
            parser.error(
                "Claude API key is required for local server mode. Please either:\n"
                "  1. Create a '.claude-explain-key' file with your API key in the current directory\n"
                "  2. Specify a key file with --api-key-file"
            )

        # Test the API key before starting the server
        if DEBUG:
            print("\nTesting API key with Anthropic API...")
            try:
                client = get_anthropic_client(api_key)
                # Just instantiate the client to test the API key
                print("API key is valid!")
            except Exception as e:
                print(f"Warning: API key test failed: {str(e)}")
                print("The server will still start, but requests may fail.")

        run_local_server(args.host, args.port, api_key)
