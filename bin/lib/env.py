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


@dataclass(frozen=True)
class Config:
    env: Environment
