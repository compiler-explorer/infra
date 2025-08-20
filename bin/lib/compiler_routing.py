"""Compiler routing management for DynamoDB queue mappings."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import requests

from lib.amazon import dynamodb_client

LOGGER = logging.getLogger(__name__)
COMPILER_ROUTING_TABLE = "CompilerRouting"

# Environment routing configuration
# Determines whether each environment uses SQS queues or direct URL forwarding
ENVIRONMENT_ROUTING_CONFIG = {
    "prod": "queue",
    "staging": "queue",
    "beta": "queue",
    "gpu": "url",
    "winprod": "url",
    "winstaging": "url",
    "wintest": "url",
    "aarch64prod": "url",
    "aarch64staging": "url",
    "runner": "url",
}


class CompilerRoutingError(Exception):
    """Base exception for compiler routing operations."""

    pass


def get_environment_routing_strategy(environment: str) -> str:
    """Get the routing strategy for a specific environment.

    Args:
        environment: Environment name

    Returns:
        Routing strategy: "queue" or "url"
    """
    return ENVIRONMENT_ROUTING_CONFIG.get(environment, "queue")


def create_composite_key(environment: str, compiler_id: str) -> str:
    """Create a composite key for environment-specific compiler routing.

    Args:
        environment: Environment name
        compiler_id: Compiler identifier

    Returns:
        Composite key in format "environment#compiler_id"
    """
    return f"{environment}#{compiler_id}"


def parse_composite_key(composite_key: str) -> tuple[str, str]:
    """Parse a composite key back into environment and compiler ID.

    Args:
        composite_key: Composite key in format "environment#compiler_id"

    Returns:
        Tuple of (environment, compiler_id)
    """
    if "#" in composite_key:
        parts = composite_key.split("#", 1)
        return parts[0], parts[1]
    else:
        # Legacy format - assume unknown environment
        return "unknown", composite_key


def construct_environment_url(compiler_id: str, environment: str, is_cmake: bool = False) -> str:
    """Construct the direct environment URL for a compiler.

    Args:
        compiler_id: Compiler identifier
        environment: Environment name
        is_cmake: Whether this is a cmake compilation request

    Returns:
        Full URL for direct forwarding
    """
    if environment == "prod":
        base_url = "https://godbolt.org"
    else:
        base_url = f"https://godbolt.org/{environment}"

    endpoint = "cmake" if is_cmake else "compile"
    return f"{base_url}/api/compiler/{compiler_id}/{endpoint}"


def fetch_discovery_compilers(environment: str, version: str | None = None) -> dict[str, dict[str, Any]]:
    """Fetch compiler data from the live API endpoints.

    Args:
        environment: Environment name (prod, staging, beta, etc.)
        version: Version string (unused, kept for compatibility)

    Returns:
        Dictionary mapping compiler IDs to their configuration data

    Raises:
        CompilerRoutingError: If API cannot be fetched or parsed
    """
    # aarch64 environments are execution-only and don't have their own compilers
    # They receive work from other environments, so skip compiler fetch
    if environment in ["aarch64prod", "aarch64staging"]:
        LOGGER.info(f"Skipping compiler fetch for {environment} - execution-only environment without compilers")
        return {}

    try:
        # Map environment to API URL with fields parameter to reduce bandwidth
        if environment == "prod":
            api_url = "https://godbolt.org/api/compilers?fields=id,exe"
        else:
            api_url = f"https://godbolt.org/{environment}/api/compilers?fields=id,exe"

        LOGGER.info(f"Fetching compiler list from {api_url}")

        # Fetch compiler data from API with JSON Accept header
        headers = {"Accept": "application/json"}

        # Retry logic with exponential backoff for 503 errors
        max_retries = 3
        retry_delay = 2
        last_exception = None

        for attempt in range(max_retries):
            try:
                response = requests.get(api_url, headers=headers, timeout=30)
                response.raise_for_status()
                break  # Success, exit retry loop
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 503:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2**attempt)  # Exponential backoff: 2, 4, 8 seconds
                        LOGGER.warning(
                            f"Got 503 error from {api_url}, attempt {attempt + 1}/{max_retries}. "
                            f"Retrying in {wait_time} seconds..."
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        LOGGER.error(f"Failed to fetch from {api_url} after {max_retries} attempts")
                        raise
                else:
                    # Not a 503, don't retry
                    raise
        else:
            # All retries failed
            if last_exception:
                raise last_exception

        compilers_list = response.json()

        # Convert list to dictionary keyed by compiler ID, filtering out /dev/null compilers
        compilers = {}
        skipped_count = 0
        for compiler_data in compilers_list:
            compiler_id = compiler_data.get("id")
            exe_path = compiler_data.get("exe", "")

            # Skip compilers with /dev/null in exe path (not real compilers for this environment)
            if "/dev/null" in exe_path:
                skipped_count += 1
                continue

            if compiler_id:
                compilers[compiler_id] = compiler_data

        LOGGER.info(f"Found {len(compilers)} compilers from API (skipped {skipped_count} /dev/null compilers)")
        return compilers

    except json.JSONDecodeError as e:
        raise CompilerRoutingError(f"Failed to parse compiler API JSON: {e}") from e
    except requests.exceptions.RequestException as e:
        raise CompilerRoutingError(f"Failed to fetch compiler API: {e}") from e
    except Exception as e:
        raise CompilerRoutingError(f"Unexpected error fetching compilers: {e}") from e


def get_current_routing_table(environment: str | None = None) -> dict[str, dict[str, Any]]:
    """Get current compiler routing mappings from DynamoDB.

    Args:
        environment: Optional environment filter. If provided, only returns entries for that environment.

    Returns:
        Dictionary mapping compiler IDs to their routing data

    Raises:
        CompilerRoutingError: If table scan fails
    """
    try:
        if environment:
            LOGGER.info(f"Scanning {COMPILER_ROUTING_TABLE} table for environment {environment}")
        else:
            LOGGER.info(f"Scanning {COMPILER_ROUTING_TABLE} table for all environments")

        paginator = dynamodb_client.get_paginator("scan")
        page_iterator = paginator.paginate(TableName=COMPILER_ROUTING_TABLE)

        routing_data = {}
        item_count = 0

        for page in page_iterator:
            for item in page.get("Items", []):
                composite_key = item.get("compilerId", {}).get("S")
                if composite_key:
                    # Parse the composite key to get environment and compiler ID
                    key_environment, compiler_id = parse_composite_key(composite_key)

                    # Skip if filtering by environment and this doesn't match
                    if environment and key_environment != environment:
                        continue

                    # Convert DynamoDB item format to regular dict
                    routing_data[compiler_id] = {
                        "queueName": item.get("queueName", {}).get("S", ""),
                        "environment": item.get("environment", {}).get("S", key_environment),
                        "lastUpdated": item.get("lastUpdated", {}).get("S", ""),
                        "routingType": item.get("routingType", {}).get("S", "queue"),
                        "targetUrl": item.get("targetUrl", {}).get("S", ""),
                        "compositeKey": composite_key,  # Store for reference
                    }
                    item_count += 1

        LOGGER.info(f"Found {item_count} compiler routing entries")
        return routing_data

    except Exception as e:
        raise CompilerRoutingError(f"Failed to scan routing table: {e}") from e


def generate_queue_name(compiler_data: dict[str, Any], environment: str) -> str:
    """Generate appropriate queue name for a compiler.

    Args:
        compiler_data: Compiler configuration from discovery
        environment: Target environment name

    Returns:
        Queue name string
    """
    # Check if compiler has remote execution configuration
    has_remote = bool(compiler_data.get("remote"))

    if has_remote:
        # Remote compilers go to specialized queues
        # For now, map to gpu queue, but this could be more sophisticated
        if environment == "prod":
            return "gpu-compilation-queue"
        else:
            return f"{environment}-gpu-compilation-queue"
    else:
        # Local compilers go to environment-specific queues
        if environment == "prod":
            return "prod-compilation-queue"
        else:
            return f"{environment}-compilation-queue"


def generate_routing_info(compiler_data: dict[str, Any], environment: str) -> dict[str, str]:
    """Generate complete routing information for a compiler.

    Args:
        compiler_data: Compiler configuration from discovery
        environment: Target environment name

    Returns:
        Dictionary with routing information (queueName, routingType, targetUrl)
    """
    routing_strategy = get_environment_routing_strategy(environment)
    compiler_id = compiler_data.get("id", "")

    if routing_strategy == "url":
        return {
            "queueName": "",  # Empty for URL routing
            "routingType": "url",
            "targetUrl": construct_environment_url(compiler_id, environment, False),  # Default to compile endpoint
        }
    else:
        return {
            "queueName": generate_queue_name(compiler_data, environment),
            "routingType": "queue",
            "targetUrl": "",  # Empty for queue routing
        }


def calculate_routing_changes(
    current_compilers: dict[str, dict[str, Any]], existing_table: dict[str, dict[str, Any]], environment: str
) -> tuple[dict[str, dict[str, Any]], set[str], dict[str, dict[str, Any]]]:
    """Calculate what changes need to be made to the routing table.

    Args:
        current_compilers: Compilers from discovery file
        existing_table: Current routing table contents
        environment: Target environment

    Returns:
        Tuple of (items_to_add, items_to_delete, items_to_update)
    """
    items_to_add = {}
    items_to_delete = set()
    items_to_update = {}

    current_time = datetime.now(UTC).isoformat()

    # Find compilers to add or update
    for compiler_id, compiler_data in current_compilers.items():
        routing_info = generate_routing_info(compiler_data, environment)
        composite_key = create_composite_key(environment, compiler_id)

        new_routing_data = {
            "compilerId": composite_key,  # Use composite key for DynamoDB
            "queueName": routing_info["queueName"],
            "environment": environment,
            "lastUpdated": current_time,
            "routingType": routing_info["routingType"],
            "targetUrl": routing_info["targetUrl"],
        }

        if compiler_id not in existing_table:
            # New compiler to add
            items_to_add[compiler_id] = new_routing_data
        else:
            # Check if existing entry needs update
            existing_data = existing_table[compiler_id]
            if (
                existing_data.get("queueName") != routing_info["queueName"]
                or existing_data.get("environment") != environment
                or existing_data.get("routingType") != routing_info["routingType"]
                or existing_data.get("targetUrl") != routing_info["targetUrl"]
            ):
                items_to_update[compiler_id] = new_routing_data

    # Find compilers to delete (exist in table but not in current discovery)
    # Only delete entries for the current environment
    for compiler_id, routing_data in existing_table.items():
        if compiler_id not in current_compilers:
            # Use the stored composite key for deletion
            composite_key = routing_data.get("compositeKey", create_composite_key(environment, compiler_id))
            items_to_delete.add(composite_key)

    return items_to_add, items_to_delete, items_to_update


def batch_write_items(items_to_write: dict[str, dict[str, Any]]) -> None:
    """Write items to DynamoDB using batch operations.

    Args:
        items_to_write: Dictionary of compiler ID to routing data

    Raises:
        CompilerRoutingError: If batch write fails
    """
    if not items_to_write:
        return

    try:
        # DynamoDB batch_write_item can handle up to 25 items per request
        batch_size = 25
        item_list = list(items_to_write.items())

        for i in range(0, len(item_list), batch_size):
            batch = item_list[i : i + batch_size]
            put_requests = []

            for _compiler_id, routing_data in batch:
                # Convert to DynamoDB item format
                put_requests.append(
                    {
                        "PutRequest": {
                            "Item": {
                                "compilerId": {"S": routing_data["compilerId"]},
                                "queueName": {"S": routing_data["queueName"]},
                                "environment": {"S": routing_data["environment"]},
                                "lastUpdated": {"S": routing_data["lastUpdated"]},
                                "routingType": {"S": routing_data["routingType"]},
                                "targetUrl": {"S": routing_data["targetUrl"]},
                            }
                        }
                    }
                )

            LOGGER.info(f"Writing batch of {len(put_requests)} items to {COMPILER_ROUTING_TABLE}")

            response = dynamodb_client.batch_write_item(RequestItems={COMPILER_ROUTING_TABLE: put_requests})

            # Handle unprocessed items (due to throttling, etc.)
            unprocessed = response.get("UnprocessedItems", {})
            if unprocessed:
                LOGGER.warning(f"Failed to process {len(unprocessed)} items, retrying...")
                # Simple retry for unprocessed items
                dynamodb_client.batch_write_item(RequestItems=unprocessed)

    except Exception as e:
        raise CompilerRoutingError(f"Failed to batch write items: {e}") from e


def batch_delete_items(items_to_delete: set[str]) -> None:
    """Delete items from DynamoDB using batch operations.

    Args:
        items_to_delete: Set of composite keys to delete

    Raises:
        CompilerRoutingError: If batch delete fails
    """
    if not items_to_delete:
        return

    try:
        # DynamoDB batch_write_item can handle up to 25 items per request
        batch_size = 25
        item_list = list(items_to_delete)

        for i in range(0, len(item_list), batch_size):
            batch = item_list[i : i + batch_size]
            delete_requests = []

            for composite_key in batch:
                delete_requests.append({"DeleteRequest": {"Key": {"compilerId": {"S": composite_key}}}})

            LOGGER.info(f"Deleting batch of {len(delete_requests)} items from {COMPILER_ROUTING_TABLE}")

            response = dynamodb_client.batch_write_item(RequestItems={COMPILER_ROUTING_TABLE: delete_requests})

            # Handle unprocessed items
            unprocessed = response.get("UnprocessedItems", {})
            if unprocessed:
                LOGGER.warning(f"Failed to process {len(unprocessed)} deletions, retrying...")
                dynamodb_client.batch_write_item(RequestItems=unprocessed)

    except Exception as e:
        raise CompilerRoutingError(f"Failed to batch delete items: {e}") from e


def update_compiler_routing_table(
    environment: str, version: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """Update the compiler routing table for a specific environment.

    Args:
        environment: Environment name (prod, staging, beta, etc.)
        version: Version string (unused, kept for compatibility)
        dry_run: If True, only show what would be changed without making changes

    Returns:
        Dictionary with counts of changes made: {"added": N, "updated": N, "deleted": N}

    Raises:
        CompilerRoutingError: If update fails
    """
    try:
        LOGGER.info(f"Updating compiler routing table for {environment}")

        # Fetch current compiler data from API
        current_compilers = fetch_discovery_compilers(environment)

        # Get existing routing table contents for this environment only
        existing_table = get_current_routing_table(environment)

        # Calculate what changes are needed
        items_to_add, items_to_delete, items_to_update = calculate_routing_changes(
            current_compilers, existing_table, environment
        )

        # Combine items to add and update for batch writing
        items_to_write = {**items_to_add, **items_to_update}

        # Log what will be changed
        LOGGER.info(f"Changes for {environment}:")
        LOGGER.info(f"  Items to add: {len(items_to_add)}")
        LOGGER.info(f"  Items to update: {len(items_to_update)}")
        LOGGER.info(f"  Items to delete: {len(items_to_delete)}")

        if dry_run:
            LOGGER.info("DRY RUN - No changes will be made")
            return {"added": len(items_to_add), "updated": len(items_to_update), "deleted": len(items_to_delete)}

        # Apply changes to DynamoDB
        if items_to_write:
            batch_write_items(items_to_write)

        if items_to_delete:
            batch_delete_items(items_to_delete)

        LOGGER.info(f"Successfully updated compiler routing table for {environment}")
        return {"added": len(items_to_add), "updated": len(items_to_update), "deleted": len(items_to_delete)}

    except Exception as e:
        if isinstance(e, CompilerRoutingError):
            raise
        else:
            raise CompilerRoutingError(f"Failed to update routing table: {e}") from e


def get_routing_table_stats() -> dict[str, Any]:
    """Get statistics about the current routing table.

    Returns:
        Dictionary with table statistics

    Raises:
        CompilerRoutingError: If stats collection fails
    """
    try:
        routing_data = get_current_routing_table()

        # Calculate statistics
        total_compilers = len(routing_data)
        environments = set()
        queue_counts: dict[str, int] = {}
        routing_type_counts = {"queue": 0, "url": 0}

        for _compiler_id, data in routing_data.items():
            env = data.get("environment", "unknown")
            queue = data.get("queueName", "unknown")
            routing_type = data.get("routingType", "queue")

            environments.add(env)
            if queue:  # Only count non-empty queue names
                queue_counts[queue] = queue_counts.get(queue, 0) + 1

            routing_type_counts[routing_type] = routing_type_counts.get(routing_type, 0) + 1

        return {
            "total_compilers": total_compilers,
            "environments": sorted(list(environments)),
            "environment_count": len(environments),
            "queue_distribution": queue_counts,
            "routing_types": routing_type_counts,
        }

    except Exception as e:
        raise CompilerRoutingError(f"Failed to get table statistics: {e}") from e


def lookup_compiler_queue(compiler_id: str) -> str | None:
    """Look up the queue name for a specific compiler.

    Args:
        compiler_id: Compiler identifier

    Returns:
        Queue name if found, None otherwise

    Raises:
        CompilerRoutingError: If lookup fails
    """
    try:
        response = dynamodb_client.get_item(TableName=COMPILER_ROUTING_TABLE, Key={"compilerId": {"S": compiler_id}})

        item = response.get("Item")
        if item:
            return item.get("queueName", {}).get("S")
        else:
            return None

    except Exception as e:
        raise CompilerRoutingError(f"Failed to lookup compiler queue: {e}") from e


def lookup_compiler_routing(compiler_id: str, environment: str | None = None) -> dict[str, str] | None:
    """Look up complete routing information for a specific compiler.

    Args:
        compiler_id: Compiler identifier
        environment: Environment to look in. If None, tries to find in any environment.

    Returns:
        Dictionary with routing information or None if not found

    Raises:
        CompilerRoutingError: If lookup fails
    """
    try:
        # If environment is specified, try composite key first
        if environment:
            composite_key = create_composite_key(environment, compiler_id)
            response = dynamodb_client.get_item(
                TableName=COMPILER_ROUTING_TABLE, Key={"compilerId": {"S": composite_key}}
            )

            item = response.get("Item")
            if item:
                return {
                    "queueName": item.get("queueName", {}).get("S", ""),
                    "environment": item.get("environment", {}).get("S", environment),
                    "routingType": item.get("routingType", {}).get("S", "queue"),
                    "targetUrl": item.get("targetUrl", {}).get("S", ""),
                }

        # Fallback: try legacy format (without environment prefix)
        response = dynamodb_client.get_item(TableName=COMPILER_ROUTING_TABLE, Key={"compilerId": {"S": compiler_id}})

        item = response.get("Item")
        if item:
            return {
                "queueName": item.get("queueName", {}).get("S", ""),
                "environment": item.get("environment", {}).get("S", "unknown"),
                "routingType": item.get("routingType", {}).get("S", "queue"),
                "targetUrl": item.get("targetUrl", {}).get("S", ""),
            }
        else:
            return None

    except Exception as e:
        raise CompilerRoutingError(f"Failed to lookup compiler routing: {e}") from e
