import boto3
import json
from datetime import datetime, UTC
import os
import re

# Configure AWS resources
s3_client = boto3.client("s3")
lb_client = boto3.client("elbv2")
ec2_client = boto3.client("ec2")

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


def lambda_handler(event, _context):
    """Handle Lambda invocation from API Gateway"""
    try:
        # CORS headers for browser access
        headers = {
            "Access-Control-Allow-Origin": "*",  # More permissive for testing
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }

        # Handle preflight OPTIONS request
        if event.get("httpMethod") == "OPTIONS":
            return {"statusCode": 200, "headers": headers, "body": ""}

        # Collect status for all environments
        environments_status = []

        for env in ENVIRONMENTS:
            status = get_environment_status(env)
            environments_status.append(status)

        # Return JSON response
        return {
            "statusCode": 200,
            "headers": {**headers, "Content-Type": "application/json"},
            "body": json.dumps({"environments": environments_status, "timestamp": datetime.now(UTC).isoformat()}),
        }
    except (ValueError, TypeError, KeyError, boto3.exceptions.Boto3Error) as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {**headers, "Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Handle unexpected errors while still returning a proper response
        print(f"Unexpected error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {**headers, "Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error"}),
        }


def extract_version_from_key(key_str):
    """Extract clean version number from an S3 key"""
    # Try to extract a version number from a path like 'dist/gh/main/14618.tar.xz'
    # or directly from 'gh-14618.tar.xz'

    # First, check for a gh-XXXX format
    gh_match = re.search(r"gh-(\d+)", key_str)
    if gh_match:
        return f"gh-{gh_match.group(1)}"

    # Then look for a version number in a path like dist/gh/main/14618.tar.xz
    path_match = re.search(r"dist/gh/[^/]+/(\d+)[.][^/]+$", key_str)
    if path_match:
        return f"gh-{path_match.group(1)}"

    # Generic pattern for version number at the end of a path
    generic_path_match = re.search(r"/(\d+)[.][^/]+$", key_str)
    if generic_path_match:
        return f"gh-{generic_path_match.group(1)}"

    # For other formats, just use the filename without extension
    filename = key_str.split("/")[-1]
    if "." in filename:
        return filename.split(".")[0]

    return key_str


def parse_version_info(version_str):
    """Parse version information to extract branch, version number, and commit hash"""
    try:
        # Get the full release info from S3
        version_info = {}

        # Set the clean version number - removing any paths and extensions
        cleaned_version = extract_version_from_key(version_str)
        version_info["version"] = cleaned_version

        # Extract basic version string and determine branch from path
        # Extract branch from S3 path if possible (dist/gh/BRANCH/1234.tar.xz)
        branch_match = re.match(r"dist/gh/([^/]+)/\d+[.][^/]+$", version_str)
        branch = branch_match.group(1) if branch_match else "unknown"
        version_info["branch"] = branch

        if "gh-" in cleaned_version:
            version_info["type"] = "GitHub"
            version_num = cleaned_version.split("-")[1] if "-" in cleaned_version else "unknown"
            version_info["version_num"] = version_num
        else:
            # Even if the cleaned version doesn't have 'gh-', the original might still be a GitHub build
            # Set default type based on the raw version string pattern
            if "dist/gh/" in version_str:
                version_info["type"] = "GitHub"
                # Try to extract the build number from the path
                build_match = re.search(r"/(\d+)[.][^/]+$", version_str)
                if build_match:
                    version_info["version_num"] = build_match.group(1)
                else:
                    version_info["version_num"] = "unknown"
            else:
                version_info["type"] = "Unknown"
                version_info["version_num"] = "unknown"

        # Try to determine the correct info file path
        info_key = None

        # Parse the S3 path pattern which looks like: dist/gh/main/14618.tar.xz
        path_match = re.match(r"dist/gh/([^/]+)/(\d+)[.][^/]+$", version_str)
        if path_match:
            branch = path_match.group(1)
            build_num = path_match.group(2)
            info_key = f"dist/gh/{branch}/{build_num}.txt"
            print(f"Determined info key from path: {info_key}")

            # Also update the version info to accurately reflect this is a GitHub build
            version_info["type"] = "GitHub"
            version_info["version"] = f"gh-{build_num}"
            version_info["version_num"] = build_num
        elif "gh-" in version_str:
            # Extract GitHub version if it's embedded in the path
            match = re.search(r"(gh-\d+)", version_str)
            if match:
                info_key = f"dist/gh/{match.group(1)}.txt"

        if info_key:
            try:
                print(f"Looking for info file at: {info_key}")
                release_info = s3_client.get_object(Bucket="compiler-explorer", Key=info_key)
                commit_hash = release_info["Body"].read().decode("utf-8").strip()

                # Validate that this looks like a git hash (40 hex chars)
                if re.match(r"^[0-9a-f]{40}$", commit_hash):
                    version_info["hash"] = commit_hash
                    version_info["hash_short"] = commit_hash[:7]
                    version_info[
                        "hash_url"
                    ] = f"https://github.com/compiler-explorer/compiler-explorer/tree/{commit_hash}"
                else:
                    version_info["hash"] = "unknown"
                    version_info["hash_short"] = "unknown"
                    version_info["hash_url"] = None
            except (boto3.exceptions.Boto3Error, KeyError, ValueError) as e:
                print(f"Error fetching hash from {info_key}: {str(e)}")
                version_info["hash"] = "unknown"
                version_info["hash_short"] = "unknown"
                version_info["hash_url"] = None
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"Unexpected error fetching hash from {info_key}: {str(e)}")
                version_info["hash"] = "unknown"
                version_info["hash_short"] = "unknown"
                version_info["hash_url"] = None
        else:
            version_info["hash"] = "unknown"
            version_info["hash_short"] = "unknown"
            version_info["hash_url"] = None

        return version_info
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
        print(f"Error parsing version '{version_str}': {str(e)}")
        return {
            "type": "GitHub",
            "version": extract_version_from_key(version_str),
            "version_num": version_str.split("/")[-1].split(".")[0] if "/" in version_str else "unknown",
            "hash": "unknown",
            "hash_short": "unknown",
            "hash_url": None,
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Fall back to safe defaults for unexpected errors
        print(f"Unexpected error parsing version '{version_str}': {str(e)}")
        return {
            "type": "Unknown",
            "version": "Unknown",
            "version_num": "unknown",
            "hash": "unknown",
            "hash_short": "unknown",
            "hash_url": None,
        }


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
        version_obj = s3_client.get_object(Bucket="compiler-explorer", Key=version_key)
        raw_version = version_obj["Body"].read().decode("utf-8").strip()
        status["raw_version"] = raw_version  # Store the raw version for debugging
        version_info = parse_version_info(raw_version)
        status["version"] = version_info["version"]  # Use the cleaned up version
        status["version_info"] = version_info
    except (boto3.exceptions.Boto3Error, KeyError, ValueError) as e:
        print(f"Error fetching version for {env['name']}: {str(e)}")
        status["version"] = "Unknown"
        status["raw_version"] = "Error"
        status["version_info"] = {
            "type": "Unknown",
            "version": "Unknown",
            "version_num": "unknown",
            "hash": "unknown",
            "hash_short": "unknown",
            "hash_url": None,
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Unexpected error fetching version for {env['name']}: {str(e)}")
        status["version"] = "Unknown"
        status["raw_version"] = "Error"
        status["version_info"] = {
            "type": "Unknown",
            "version": "Unknown",
            "version_num": "unknown",
            "hash": "unknown",
            "hash_short": "unknown",
            "hash_url": None,
        }

    # Check load balancer status if ARN is provided
    if env.get("load_balancer"):
        try:
            lb_status = lb_client.describe_target_health(TargetGroupArn=env["load_balancer"])

            healthy_targets = 0
            total_targets = 0

            for target in lb_status.get("TargetHealthDescriptions", []):
                total_targets += 1
                if target.get("TargetHealth", {}).get("State") == "healthy":
                    healthy_targets += 1

            status["health"] = {
                "healthy_targets": healthy_targets,
                "total_targets": total_targets,
                "status": "Online" if healthy_targets > 0 else "Offline",
            }
        except (boto3.exceptions.Boto3Error, KeyError, ValueError) as e:
            print(f"Error fetching load balancer status for {env['name']}: {str(e)}")
            status["health"] = {"status": "Unknown", "error": str(e)}
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Unexpected error fetching load balancer status for {env['name']}: {str(e)}")
            status["health"] = {"status": "Unknown", "error": "Internal error"}
    else:
        status["health"] = {"status": "Unknown", "error": "No load balancer configured"}

    return status
