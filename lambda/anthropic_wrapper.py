"""
This module provides a safe wrapper around the Anthropic API client.
It handles different versions of the Anthropic library and ensures
compatibility.
"""

import logging
from typing import Any, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anthropic_wrapper")

try:
    import anthropic
    from anthropic import Anthropic

    logger.info(f"Successfully imported Anthropic library version {anthropic.__version__}")
except ImportError:
    logger.error("Failed to import anthropic library. Make sure it's installed.")
    Anthropic = None
    anthropic = None


def create_anthropic_client(api_key: str) -> Optional[Any]:
    """
    Creates an Anthropic client with the given API key,
    handling different versions safely.

    Args:
        api_key: The Anthropic API key to use

    Returns:
        An Anthropic client instance, or None if client creation failed
    """
    if not Anthropic:
        logger.error("Anthropic library is not available")
        return None

    try:
        logger.info("Creating Anthropic client...")

        # First try with minimal parameters
        try:
            client = Anthropic(api_key=api_key)
            logger.info("Successfully created Anthropic client with minimal parameters")
            return client
        except TypeError as e:
            logger.warning(f"Error creating client with minimal parameters: {e}")

            # If that fails, try with **{}
            try:
                # This is a hack to work around any potential keyword argument issues
                client = Anthropic(api_key=api_key, **{})
                logger.info("Successfully created Anthropic client with empty kwargs")
                return client
            except TypeError as e:
                logger.warning(f"Error creating client with empty kwargs: {e}")

                # Last resort - create without any parameters and set api_key directly
                try:
                    client = object.__new__(Anthropic)
                    client.api_key = api_key
                    logger.info("Created raw client and set api_key directly")
                    return client
                except Exception as e:
                    logger.error(f"Failed to create client with direct instantiation: {e}")
                    return None

    except Exception as e:
        logger.error(f"Unexpected error creating Anthropic client: {e}")
        return None


def generate_explanation(
    client: Any, model: str, system_prompt: str, max_tokens: int, structured_data: Dict[str, Any]
) -> Optional[str]:
    """
    Generates an explanation using the Anthropic API.

    Args:
        client: The Anthropic client
        model: The model to use (e.g., "claude-3-haiku-20240307")
        system_prompt: The system prompt
        max_tokens: Maximum tokens in the response
        structured_data: The data to explain

    Returns:
        The explanation text, or None if generation failed
    """
    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
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
        )

        explanation = message.content[0].text
        return explanation
    except Exception as e:
        logger.error(f"Error generating explanation: {e}")
        return None
