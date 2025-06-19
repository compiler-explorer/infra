from dataclasses import dataclass
from enum import Enum

# Environments that support blue-green deployment
BLUE_GREEN_ENABLED_ENVIRONMENTS = [
    "beta",
    "prod",
    "staging",
    "gpu",
    "wintest",
    "winstaging",
    "winprod",
    "aarch64staging",
    "aarch64prod",
]


class Environment(Enum):
    PROD = "prod"
    BETA = "beta"
    STAGING = "staging"
    GPU = "gpu"
    RUNNER = "runner"
    WINPROD = "winprod"
    WINSTAGING = "winstaging"
    WINTEST = "wintest"
    AARCH64PROD = "aarch64prod"
    AARCH64STAGING = "aarch64staging"

    @property
    def keep_builds(self):
        return self in (
            Environment.PROD,
            Environment.BETA,
            Environment.STAGING,
            Environment.GPU,
            Environment.WINPROD,
            Environment.WINSTAGING,
            Environment.WINTEST,
            Environment.AARCH64PROD,
            Environment.AARCH64STAGING,
        )

    @property
    def is_windows(self):
        return self in (Environment.WINPROD, Environment.WINSTAGING, Environment.WINTEST)

    @property
    def is_prod(self):
        return self in (Environment.PROD, Environment.GPU, Environment.WINPROD, Environment.AARCH64PROD)

    @property
    def branch_name(self) -> str:
        return "release" if self == Environment.PROD else self.value

    @property
    def version_key(self) -> str:
        return f"version/{self.branch_name}"

    @property
    def supports_blue_green(self) -> bool:
        return self.value in BLUE_GREEN_ENABLED_ENVIRONMENTS


@dataclass(frozen=True)
class Config:
    env: Environment
