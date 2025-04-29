import functools
import json
import os
import re
from datetime import datetime, timezone

import boto3


# AWS clients are initialized on demand with caching to make testing easier
@functools.cache
def get_s3_client():
    """Get or initialize S3 client"""
    return boto3.client("s3")


@functools.cache
def get_lb_client():
    """Get or initialize load balancer client"""
    return boto3.client("elbv2")


@functools.cache
def get_as_client():
    """Get or initialize AutoScaling client"""
    return boto3.client("autoscaling")


# Environment configuration based on bin/lib/env.py
ENVIRONMENTS = [
    # Production environments
    {
        "name": "prod",
        "description": "Production",
        "url": "godbolt.org",
        "load_balancer": os.environ.get("PROD_LB_ARN"),
        "is_production": True,
        "version_key": "version/release",  # S3 path where version is stored
    },
    {
        "name": "gpu",
        "description": "GPU",
        "url": "godbolt.org/gpu",
        "load_balancer": os.environ.get("GPU_LB_ARN"),
        "is_production": True,
        "version_key": "version/gpu",
    },
    {
        "name": "aarch64prod",
        "description": "ARM64 Production",
        "url": "godbolt.org/aarch64prod",
        "load_balancer": os.environ.get("ARM_PROD_LB_ARN"),
        "is_production": True,
        "version_key": "version/aarch64prod",
    },
    {
        "name": "winprod",
        "description": "Windows Production",
        "url": "godbolt.org/winprod",
        "load_balancer": os.environ.get("WIN_PROD_LB_ARN"),
        "is_production": True,
        "version_key": "version/winprod",
    },
    # Non-production environments
    {
        "name": "staging",
        "description": "Staging",
        "url": "godbolt.org/staging",
        "load_balancer": os.environ.get("STAGING_LB_ARN"),
        "is_production": False,
        "version_key": "version/staging",
    },
    {
        "name": "beta",
        "description": "Beta",
        "url": "godbolt.org/beta",
        "load_balancer": os.environ.get("BETA_LB_ARN"),
        "is_production": False,
        "version_key": "version/beta",
    },
    {
        "name": "aarch64staging",
        "description": "ARM64 Staging",
        "url": "godbolt.org/aarch64staging",
        "load_balancer": os.environ.get("ARM_STAGING_LB_ARN"),
        "is_production": False,
        "version_key": "version/aarch64staging",
    },
    {
        "name": "winstaging",
        "description": "Windows Staging",
        "url": "godbolt.org/winstaging",
        "load_balancer": os.environ.get("WIN_STAGING_LB_ARN"),
        "is_production": False,
        "version_key": "version/winstaging",
    },
]


def create_response(status_code=200, body=None, headers=None):
    """Create a standardized API response"""
    # Default CORS headers for browser access
    default_headers = {
        "Access-Control-Allow-Origin": "*",  # More permissive for testing
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    # Merge with content-type for JSON responses
    if headers:
        response_headers = {**default_headers, **headers}
    else:
        response_headers = default_headers

    # Add content type for non-empty responses
    if body and "Content-Type" not in response_headers:
        response_headers["Content-Type"] = "application/json"

    response = {
        "statusCode": status_code,
        "headers": response_headers,
    }

    # Add body if provided
    if body is not None:
        if isinstance(body, dict) or isinstance(body, list):
            response["body"] = json.dumps(body)
        else:
            response["body"] = body

    return response


def handle_error(error, is_internal=False):
    """Centralized error handler that logs and creates error responses"""
    if is_internal:
        print(f"Unexpected error: {str(error)}")
        return create_response(status_code=500, body={"error": "Internal server error"})
    else:
        print(f"Error: {str(error)}")
        return create_response(status_code=500, body={"error": str(error)})


def lambda_handler(event, _context):
    """Handle Lambda invocation from API Gateway"""
    try:
        # Handle preflight OPTIONS request
        if event.get("httpMethod") == "OPTIONS":
            return create_response(status_code=200, body="")

        # Collect status for all environments
        environments_status = []

        for env in ENVIRONMENTS:
            status = get_environment_status(env)
            environments_status.append(status)

        # Return JSON response
        return create_response(
            status_code=200,
            body={"environments": environments_status, "timestamp": datetime.now(timezone.utc).isoformat()},
        )
    except (ValueError, TypeError, KeyError, boto3.exceptions.Boto3Error) as e:
        return handle_error(e)
    except Exception as e:
        # Handle unexpected errors while still returning a proper response
        return handle_error(e, is_internal=True)


def extract_version_from_key(key_str):
    """Extract clean version number from an S3 key

    For paths like 'dist/gh/main/12345.tar.xz' or 'dist/gh/feature/branch/12345.tar.xz',
    returns 'gh-12345'.
    We use 'gh-' prefix to indicate GitHub build numbers, following CLI tool conventions.
    """
    # Handle empty or None key
    if not key_str:
        return "unknown"

    # Extract build number from dist/gh/**/{number}.tar.xz format
    # This handles branch names with slashes (e.g., 'mg/wasming')
    path_match = re.search(r"dist/gh/(.+)/(\d+)[.][^/]+$", key_str)
    if path_match:
        return f"gh-{path_match.group(2)}"

    # For any other unexpected formats, just keep the original
    return key_str


def handle_version_parse_error(version_str, error, is_internal=False):
    """Handle errors during version parsing with appropriate fallback values"""
    error_type = "Unexpected error" if is_internal else "Error"
    print(f"{error_type} parsing version '{version_str}': {str(error)}")

    if is_internal:
        # For unexpected errors, use completely safe defaults
        return {
            "type": "Unknown",
            "version": "Unknown",
            "version_num": "unknown",
            "hash": "unknown",
            "hash_short": "unknown",
            "hash_url": None,
        }
    else:
        # For known error types, try to extract some meaningful information
        return {
            "type": "GitHub",
            "version": extract_version_from_key(version_str),
            "version_num": version_str.split("/")[-1].split(".")[0] if "/" in version_str else "unknown",
            "hash": "unknown",
            "hash_short": "unknown",
            "hash_url": None,
        }


def handle_hash_fetch_error(info_key, error, is_internal=False):
    """Handle errors when fetching commit hash information"""
    error_type = "Unexpected error" if is_internal else "Error"
    print(f"{error_type} fetching hash from {info_key}: {str(error)}")

    return {"hash": "unknown", "hash_short": "unknown", "hash_url": None}


def parse_version_info(version_str):
    """Parse version information to extract branch, version number, and commit hash"""
    try:
        # Initialize with defaults
        version_info = {
            "type": "GitHub",  # All builds are GitHub builds now
            "version": "unknown",
            "version_num": "unknown",
            "branch": "unknown",
            "hash": "unknown",
            "hash_short": "unknown",
            "hash_url": None,
        }

        if not version_str:
            return version_info

        # Expected format: dist/gh/{branch}/{build_num}.tar.xz, where branch may contain slashes
        path_match = re.match(r"dist/gh/(.+)/(\d+)[.][^/]+$", version_str)
        if path_match:
            branch = path_match.group(1)
            build_num = path_match.group(2)

            # Update version info with extracted details
            version_info["branch"] = branch
            version_info["version_num"] = build_num
            version_info["version"] = f"gh-{build_num}"

            # Get commit hash information
            info_key = f"dist/gh/{branch}/{build_num}.txt"
            hash_info = fetch_commit_hash(info_key)
            if hash_info:
                version_info.update(hash_info)
        else:
            # If not in the expected format, just use the original
            # but still try to get a clean version display
            version_info["version"] = extract_version_from_key(version_str)

        return version_info
    except Exception as e:
        # Fall back to safe defaults for unexpected errors
        return handle_version_parse_error(version_str, e, is_internal=True)


@functools.lru_cache(maxsize=128)
def fetch_commit_hash(info_key):
    """Fetch and validate commit hash from S3

    This function is cached using LRU cache since the S3 files containing commit hashes
    are treated as immutable. Once we've read a hash, we don't need to fetch it again.
    """
    if not info_key:
        return None

    try:
        release_info = get_s3_client().get_object(Bucket="compiler-explorer", Key=info_key)
        commit_hash = release_info["Body"].read().decode("utf-8").strip()

        # Validate that this looks like a git hash (40 hex chars)
        if re.match(r"^[0-9a-f]{40}$", commit_hash):
            return {
                "hash": commit_hash,
                "hash_short": commit_hash[:7],
                "hash_url": f"https://github.com/compiler-explorer/compiler-explorer/tree/{commit_hash}",
            }
        return None
    except Exception as e:
        # Log error and return
        print(f"Error fetching hash from {info_key}: {str(e)}")
        return None


def handle_environment_error(env_name, error, is_internal=False):
    """Handle and log errors specific to environment status"""
    error_type = "Unexpected error" if is_internal else "Error"
    print(f"{error_type} fetching version for {env_name}: {str(error)}")

    return {
        "version": "Unknown",
        "raw_version": "Error",
        "version_info": {
            "type": "Unknown",
            "version": "Unknown",
            "version_num": "unknown",
            "hash": "unknown",
            "hash_short": "unknown",
            "hash_url": None,
        },
    }


def handle_lb_error(env_name, error, is_internal=False):
    """Handle and log errors specific to load balancer status"""
    error_type = "Unexpected error" if is_internal else "Error"
    print(f"{error_type} fetching load balancer status for {env_name}: {str(error)}")

    error_msg = "Internal error" if is_internal else str(error)
    return {"status": "Unknown", "status_type": "secondary", "error": error_msg}


def get_asg_status(env_name):
    """Get AutoScaling group status for a given environment name

    Returns:
        dict: Contains desired_capacity, min_size, max_size, and is_deliberate_shutdown (True if desired=0)
    """
    try:
        # Get ASG with matching name
        response = get_as_client().describe_auto_scaling_groups(AutoScalingGroupNames=[env_name])

        if not response["AutoScalingGroups"]:
            print(f"No AutoScaling group found for environment: {env_name}")
            return {"is_deliberate_shutdown": False}

        asg = response["AutoScalingGroups"][0]
        return {
            "desired_capacity": asg["DesiredCapacity"],
            "min_size": asg["MinSize"],
            "max_size": asg["MaxSize"],
            "is_deliberate_shutdown": asg["DesiredCapacity"] == 0 and asg["MinSize"] == 0,
        }
    except Exception as e:
        print(f"Error fetching ASG status for {env_name}: {str(e)}")
        return {"is_deliberate_shutdown": False}


def get_environment_status(env):
    """Get status information for a given environment"""
    status = {
        "name": env["name"],
        "description": env["description"],
        "url": env["url"],
        "is_production": env["is_production"],
    }

    # Get version from S3
    try:
        version_key = env["version_key"]
        version_obj = get_s3_client().get_object(Bucket="compiler-explorer", Key=version_key)
        raw_version = version_obj["Body"].read().decode("utf-8").strip()
        status["raw_version"] = raw_version  # Store the raw version for debugging
        version_info = parse_version_info(raw_version)
        status["version"] = version_info["version"]  # Use the cleaned up version
        status["version_info"] = version_info
    except (boto3.exceptions.Boto3Error, KeyError, ValueError) as e:
        status.update(handle_environment_error(env["name"], e))
    except Exception as e:
        status.update(handle_environment_error(env["name"], e, is_internal=True))

    # Check load balancer status if ARN is provided
    if env.get("load_balancer"):
        try:
            lb_status = get_lb_client().describe_target_health(TargetGroupArn=env["load_balancer"])

            healthy_targets = 0
            total_targets = 0

            for target in lb_status.get("TargetHealthDescriptions", []):
                total_targets += 1
                if target.get("TargetHealth", {}).get("State") == "healthy":
                    healthy_targets += 1

            # Get ASG status to determine if this is deliberate shutdown or an issue
            asg_status = get_asg_status(env["name"])
            is_deliberate_shutdown = asg_status["is_deliberate_shutdown"]

            # Determine status based on healthy targets and ASG desired capacity
            if is_deliberate_shutdown:
                status_text = "Shut down" if total_targets == 0 else "Shutting down"
                status_type = "secondary"  # Muted color for deliberate shutdown
            elif healthy_targets > 0:
                status_text = "Online"
                status_type = "success"
            else:
                status_text = "Offline"
                status_type = "danger"  # Alarm color for unintentional offline

            status["health"] = {
                "healthy_targets": healthy_targets,
                "total_targets": total_targets,
                "desired_capacity": asg_status.get("desired_capacity", 0),
                "status": status_text,
                "status_type": status_type,
            }
        except (boto3.exceptions.Boto3Error, KeyError, ValueError) as e:
            status["health"] = handle_lb_error(env["name"], e)
        except Exception as e:
            status["health"] = handle_lb_error(env["name"], e, is_internal=True)
    else:
        status["health"] = {"status": "Unknown", "status_type": "secondary", "error": "No load balancer configured"}

    return status
