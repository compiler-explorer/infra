"""
Direct Anthropic API client that doesn't rely on the Anthropic library.
This module makes HTTP requests directly to the Anthropic API.
"""

import json
import logging
from typing import Any, Dict

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("direct_anthropic")

# Constants
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"  # Current Claude API version


def create_explanation(
    api_key: str, model: str, system_prompt: str, max_tokens: int, structured_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Creates an explanation by directly calling the Anthropic API.

    Args:
        api_key: The Anthropic API key
        model: Model name (e.g., "claude-3-haiku-20240307")
        system_prompt: System prompt for Claude
        max_tokens: Maximum tokens in the response
        structured_data: Structured data to explain

    Returns:
        Dict with status and explanation text
    """
    # Prepare headers
    headers = {
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }

    # Prepare the request body
    request_body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Explain the relationship between this source code and its assembly output.",
                    },
                    {"type": "json", "json": structured_data},
                ],
            }
        ],
    }

    try:
        logger.info(f"Making request to Anthropic API with model {model}")
        response = requests.post(
            API_URL,
            headers=headers,
            json=request_body,
            timeout=30,  # 30 second timeout
        )

        # Check for HTTP errors
        response.raise_for_status()

        # Parse the response
        result = response.json()

        if "content" in result and len(result["content"]) > 0:
            # Extract the explanation text
            content_blocks = result["content"]
            explanation_text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    explanation_text += block.get("text", "")

            return {"status": "success", "explanation": explanation_text}
        else:
            logger.error(f"Unexpected response format: {result}")
            return {"status": "error", "message": "Unexpected response format from Claude API"}

    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error when calling Claude API: {str(e)}")
        error_message = f"Error calling Claude API: {str(e)}"

        # Try to get more details if we have a response
        if hasattr(e, "response") and e.response is not None:
            try:
                error_details = e.response.json()
                error_message += f" - Details: {json.dumps(error_details)}"
            except Exception:
                # If we can't parse the JSON, just use the text
                error_message += f" - Response: {e.response.text}"

        return {"status": "error", "message": error_message}

    except Exception as e:
        logger.error(f"Unexpected error when calling Claude API: {str(e)}")
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


def test_api_key(api_key: str) -> bool:
    """
    Test if the API key is valid by making a simple request to the Claude API.

    Args:
        api_key: The API key to test

    Returns:
        True if the API key is valid, False otherwise
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }

    # Very small request just to test the API key
    simple_request = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "Hello"}],
    }

    try:
        logger.info("Testing API key with a simple request")
        response = requests.post(API_URL, headers=headers, json=simple_request, timeout=10)

        # If we get a 200 OK, the API key is valid
        if response.status_code == 200:
            logger.info("API key is valid")
            return True

        # If we get a 401, the API key is invalid
        if response.status_code == 401:
            logger.error("API key is invalid")
            return False

        # For other status codes, log the error and assume the key might be valid
        logger.warning(f"Unexpected status code when testing API key: {response.status_code}")
        return False

    except Exception as e:
        logger.error(f"Error testing API key: {str(e)}")
        return False
