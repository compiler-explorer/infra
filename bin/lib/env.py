from __future__ import annotations

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
    GPU_RUNNER = "gpu-runner"
    RUNNER = "runner"
    WINPROD = "winprod"
    WINSTAGING = "winstaging"
    WINTEST = "wintest"
    WINRUNNER = "winrunner"
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
        return self in (
            Environment.WINPROD,
            Environment.WINSTAGING,
            Environment.WINTEST,
            Environment.WINRUNNER,
        )

    @property
    def is_runner(self):
        """Runners build discovery for other environments and never serve traffic."""
        return self in (Environment.RUNNER, Environment.GPU_RUNNER, Environment.WINRUNNER)

    @property
    def discovery_required(self) -> bool:
        """Whether deploys here should insist a discovery has been run for the version.

        Runners produce discovery rather than consume it, and nothing produces one for wintest,
        which serves its own compiler set from the windows-docker properties.
        """
        if self.is_runner:
            return False
        return self != Environment.WINTEST

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

    @property
    def path_pattern(self) -> str:
        """Get the ALB path pattern for this environment."""
        if self == Environment.PROD:
            # Production uses the default listener (no path pattern)
            return ""
        return f"/{self.value}*"

    @property
    def min_instances(self) -> int:
        """Get the minimum number of instances for this environment."""
        if self.is_prod:
            return 2
        return 0


@dataclass(frozen=True)
class Config:
    env: Environment
