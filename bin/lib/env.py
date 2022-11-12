from dataclasses import dataclass
from enum import Enum


class Environment(Enum):
    PROD = "prod"
    BETA = "beta"
    STAGING = "staging"
    RUNNER = "runner"


class EnvironmentNoRunner(Enum):
    PROD = "prod"
    BETA = "beta"
    STAGING = "staging"


class EnvironmentNoProd(Enum):
    BETA = "beta"
    STAGING = "staging"


@dataclass(frozen=True)
class Config:
    env: Environment
