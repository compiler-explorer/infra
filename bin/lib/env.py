from dataclasses import dataclass
from enum import Enum


class Environment(Enum):
    PROD = "prod"
    BETA = "beta"
    STAGING = "staging"
    GPU = "gpu"
    RUNNER = "runner"

    @property
    def keep_builds(self):
        return self in (Environment.PROD, Environment.BETA, Environment.STAGING, Environment.GPU)

    @property
    def is_prod(self):
        return self in (Environment.PROD, Environment.GPU)

    @property
    def branch_name(self) -> str:
        return "release" if self == Environment.PROD else self.value

    @property
    def version_key(self) -> str:
        return f"version/{self.branch_name}"


@dataclass(frozen=True)
class Config:
    env: Environment
