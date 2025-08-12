#!/usr/bin/env python3
"""Configuration management for CE infrastructure.

Handles loading configuration from YAML files to control behavior
of ce_install and other tools.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from lib.config_safe_loader import ConfigSafeLoader

_LOGGER = logging.getLogger(__name__)


class SquashfsConfig(BaseModel):
    """Configuration for squashfs creation and management."""

    enabled: bool = True
    image_dir: Path = Path("/efs/squash-images")
    compression: str = "zstd"
    compression_level: int = 19
    mksquashfs_path: str = "/usr/bin/mksquashfs"

    model_config = ConfigDict(frozen=True, extra="forbid")


class CefsConfig(BaseModel):
    """Configuration for CEFS (Compiler Explorer FileSystem) v2."""

    enabled: bool = False
    mount_point: str = "/cefs"
    image_dir: Path = Path("/efs/cefs-images")

    model_config = ConfigDict(frozen=True, extra="forbid")


class Config(BaseModel):
    """Main CE infrastructure configuration."""

    squashfs: SquashfsConfig = SquashfsConfig()
    cefs: CefsConfig = CefsConfig()

    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def load(cls, config_path: Path) -> Config:
        """Load configuration from config path.

        Args:
            config_path: Path to the configuration file (e.g., /opt/compiler-explorer/config.yaml)

        Returns:
            Config instance with loaded values, or defaults if file doesn't exist

        Raises:
            ValidationError: If config contains invalid values or unknown keys
        """
        if not config_path.exists():
            _LOGGER.debug("Config file %s does not exist, using defaults", config_path)
            return cls()

        try:
            with config_path.open(encoding="utf-8") as config_file:
                config_data = yaml.load(config_file, Loader=ConfigSafeLoader)

            if config_data is None:
                _LOGGER.warning("Config file %s is empty, using defaults", config_path)
                return cls()

            return cls.model_validate(config_data)

        except ValidationError as e:
            _LOGGER.error("Invalid config in %s: %s", config_path, e)
            raise
        except Exception as e:
            _LOGGER.error("Failed to load config from %s: %s", config_path, e)
            raise
