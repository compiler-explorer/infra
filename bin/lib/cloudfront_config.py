"""CloudFront invalidation configuration for different environments.

To find the CloudFront distribution IDs:
1. Check terraform/cloudfront.tf for the distribution definitions
2. Use AWS CLI: aws cloudfront list-distributions
3. Check AWS Console: CloudFront -> Distributions

Each distribution configuration should include:
- distribution_id: The CloudFront distribution ID (e.g., "E1ABCDEF123456")
- domain: The domain name (for logging/documentation)
- paths: List of paths to invalidate (["/*"] for all content)
"""

from typing import Dict, List

from lib.env import Environment

# CloudFront invalidation configuration
# Maps environment to a list of CloudFront distributions and their paths to invalidate
CLOUDFRONT_INVALIDATION_CONFIG: Dict[Environment, List[Dict[str, any]]] = {
    Environment.PROD: [
        {
            "distribution_id": "EFCZGUFIBB1UY",
            "domain": "godbolt.org",
            "paths": ["/*"],
        },
        {
            "distribution_id": "E1CWN4N5AVFK4D",
            "domain": "compiler-explorer.com",
            "paths": ["/*"],
        },
        {
            "distribution_id": "E3MS24ZJS8QSX7",
            "domain": "godbo.lt",
            "paths": ["/*"],
        },
    ],
    Environment.BETA: [
        {
            "distribution_id": "EFCZGUFIBB1UY",
            "domain": "godbolt.org",
            "paths": ["/beta/*"],
        },
        {
            "distribution_id": "E1CWN4N5AVFK4D",
            "domain": "compiler-explorer.com",
            "paths": ["/beta/*"],
        },
        {
            "distribution_id": "E3MS24ZJS8QSX7",
            "domain": "godbo.lt",
            "paths": ["/beta/*"],
        },
    ],
    Environment.STAGING: [
        {
            "distribution_id": "EFCZGUFIBB1UY",
            "domain": "godbolt.org",
            "paths": ["/staging/*"],
        },
        {
            "distribution_id": "E1CWN4N5AVFK4D",
            "domain": "compiler-explorer.com",
            "paths": ["/staging/*"],
        },
        {
            "distribution_id": "E3MS24ZJS8QSX7",
            "domain": "godbo.lt",
            "paths": ["/staging/*"],
        },
    ],
    Environment.GPU: [
        {
            "distribution_id": "EFCZGUFIBB1UY",
            "domain": "godbolt.org",
            "paths": ["/gpu/*"],
        },
        {
            "distribution_id": "E1CWN4N5AVFK4D",
            "domain": "compiler-explorer.com",
            "paths": ["/gpu/*"],
        },
        {
            "distribution_id": "E3MS24ZJS8QSX7",
            "domain": "godbo.lt",
            "paths": ["/gpu/*"],
        },
    ],
    Environment.RUNNER: [
    ],
    Environment.WINPROD: [
        {
            "distribution_id": "EFCZGUFIBB1UY",
            "domain": "godbolt.org",
            "paths": ["/winprod/*"],
        },
        {
            "distribution_id": "E1CWN4N5AVFK4D",
            "domain": "compiler-explorer.com",
            "paths": ["/winprod/*"],
        },
        {
            "distribution_id": "E3MS24ZJS8QSX7",
            "domain": "godbo.lt",
            "paths": ["/winprod/*"],
        },
    ],
    Environment.WINSTAGING: [
        {
            "distribution_id": "EFCZGUFIBB1UY",
            "domain": "godbolt.org",
            "paths": ["/winstaging/*"],
        },
        {
            "distribution_id": "E1CWN4N5AVFK4D",
            "domain": "compiler-explorer.com",
            "paths": ["/winstaging/*"],
        },
        {
            "distribution_id": "E3MS24ZJS8QSX7",
            "domain": "godbo.lt",
            "paths": ["/winstaging/*"],
        },
    ],
    Environment.WINTEST: [
    ],
    Environment.AARCH64PROD: [
    ],
    Environment.AARCH64STAGING: [
    ],
}