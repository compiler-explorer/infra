"""Discovery file management utilities for Compiler Explorer."""

from __future__ import annotations

import boto3
import botocore.exceptions


def s3_key_for_discovery(environment: str, version: str) -> str:
    """Get the S3 key for discovery file for a given environment and version."""
    if environment == "prod":
        return f"dist/discovery/release/{version}.json"
    else:
        return f"dist/discovery/{environment}/{version}.json"


def discovery_exists(environment: str, version: str) -> bool:
    """Check if a discovery json file exists for the given environment and version."""
    try:
        boto3.client("s3").head_object(Bucket="compiler-explorer", Key=s3_key_for_discovery(environment, version))
        return True
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def copy_discovery_to_prod(source_environment: str, version: str) -> bool:
    """Copy discovery file from source environment to prod, making it safe for production.

    Args:
        source_environment: Source environment (e.g., "staging", "beta")
        version: Version string

    Returns:
        True if successful, False if source discovery doesn't exist.

    Raises:
        Exception: If the copy operation fails for reasons other than source not found.
    """
    s3_client = boto3.client("s3")
    source_key = s3_key_for_discovery(source_environment, version)
    prod_key = s3_key_for_discovery("prod", version)

    # S3 configuration for discovery files
    s3_config = {"ACL": "public-read", "StorageClass": "REDUCED_REDUNDANCY"}

    try:
        # Check if source discovery exists
        s3_client.head_object(Bucket="compiler-explorer", Key=source_key)

        # Copy from source to prod
        print(f"Copying discovery file from {source_environment} to prod for version {version}")
        s3_client.copy_object(
            Bucket="compiler-explorer",
            CopySource={"Bucket": "compiler-explorer", "Key": source_key},
            Key=prod_key,
            **s3_config,
        )
        print("✓ Discovery file copied successfully")
        return True
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        # Re-raise any other S3 errors (permissions, network, etc.)
        print(f"❌ Failed to copy discovery file: {e}")
        raise
