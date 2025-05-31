import logging
import time
from typing import List, Optional

from lib.amazon import cloudfront_client
from lib.cloudfront_config import CLOUDFRONT_INVALIDATION_CONFIG
from lib.env import Config

logger = logging.getLogger(__name__)


def create_cloudfront_invalidation(
    distribution_id: str, paths: List[str], caller_reference: Optional[str] = None
) -> str:
    """Create a CloudFront invalidation for the specified distribution and paths.
    
    Args:
        distribution_id: The CloudFront distribution ID
        paths: List of paths to invalidate (e.g., ["/*"] for all content)
        caller_reference: Optional unique string to prevent duplicate invalidations
        
    Returns:
        The invalidation ID
    """
    if not caller_reference:
        caller_reference = f"ce-refresh-{int(time.time())}"
    
    response = cloudfront_client.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {
                "Quantity": len(paths),
                "Items": paths,
            },
            "CallerReference": caller_reference,
        },
    )
    
    return response["Invalidation"]["Id"]


def wait_for_invalidation(distribution_id: str, invalidation_id: str, timeout: int = 600) -> bool:
    """Wait for a CloudFront invalidation to complete.
    
    Args:
        distribution_id: The CloudFront distribution ID
        invalidation_id: The invalidation ID to wait for
        timeout: Maximum time to wait in seconds
        
    Returns:
        True if completed successfully, False if timeout
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        response = cloudfront_client.get_invalidation(
            DistributionId=distribution_id,
            Id=invalidation_id,
        )
        
        status = response["Invalidation"]["Status"]
        if status == "Completed":
            return True
        
        logger.info(f"Invalidation {invalidation_id} status: {status}")
        time.sleep(10)
    
    return False


def invalidate_cloudfront_distributions(cfg: Config) -> None:
    """Invalidate CloudFront distributions for the given environment.
    
    Args:
        cfg: Configuration object containing environment information
    """
    invalidations = CLOUDFRONT_INVALIDATION_CONFIG.get(cfg.env, [])
    
    if not invalidations:
        logger.info(f"No CloudFront distributions configured for environment {cfg.env.value}")
        return
    
    print(f"\nCreating CloudFront invalidations for {cfg.env.value} environment...")
    
    for config in invalidations:
        distribution_id = config["distribution_id"]
        domain = config["domain"]
        paths = config["paths"]
        
        if distribution_id.startswith("EXAMPLE_"):
            print(f"  ⚠️  Skipping {domain} - distribution ID not configured")
            continue
        
        try:
            print(f"  Creating invalidation for {domain} (distribution {distribution_id})...")
            invalidation_id = create_cloudfront_invalidation(distribution_id, paths)
            print(f"    ✓ Invalidation created: {invalidation_id}")
            print(f"    Paths: {', '.join(paths)}")
        except Exception as e:
            print(f"    ✗ Failed to create invalidation: {e}")
            logger.error(f"Failed to create CloudFront invalidation for {distribution_id}: {e}")