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

    traditional_enabled: bool = True  # whether the old-style explicit "squash" is enabled
    image_dir: Path = Path("/efs/squash-images")
    compression: str = "zstd"
    # Compression level for squashfs, default picked after playing with a 1.4G GCC on my 8 CPU laptop:
    # lvl: tims : final size
    #  1 : 1.3s : 455MB
    #  2 : 1.5s : 441MB
    #  5 : 5.6s : 417MB
    #  7 : 5.7s : 404MB
    #  9 :  12s : 401MB
    # 10 :  24s : 400MB
    # 12 :  26s : 399MB
    # 15 :  96s : 375MB
    # 19 : 290s : 368MB
    # Seems a decent tradeoff
    compression_level: int = 7
    mksquashfs_path: str = "/usr/bin/mksquashfs"

    model_config = ConfigDict(frozen=True, extra="forbid")


class CefsConfig(BaseModel):
    """Configuration for CEFS (Compiler Explorer FileSystem) v2."""

    enabled: bool = False
    mount_point: Path = Path("/cefs")
    image_dir: Path = Path("/efs/cefs-images")
    local_temp_dir: Path = Path("/tmp/ce-cefs-temp")

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

    def with_cli_overrides(
        self,
        force_cefs: bool = False,
        force_traditional: bool = False,
        cefs_temp_dir: Path | None = None,
    ) -> Config:
        """Create a new Config with CLI overrides applied.

        Args:
            force_cefs: Force CEFS enabled, overriding config
            force_traditional: Force CEFS disabled, overriding config
            cefs_temp_dir: Override local temp directory for CEFS

        Returns:
            New Config instance with overrides applied
        """

        if force_cefs and force_traditional:
            raise ValueError("Cannot specify both --force-cefs and --force-traditional")

        config_dict = self.model_dump()
        if force_cefs:
            config_dict["cefs"]["enabled"] = True
            _LOGGER.info("CLI override: Forcing CEFS enabled")

        if force_traditional:
            config_dict["cefs"]["enabled"] = False
            _LOGGER.info("CLI override: Forcing traditional NFS installation")

        if cefs_temp_dir:
            config_dict["cefs"]["local_temp_dir"] = cefs_temp_dir
            _LOGGER.info("CLI override: CEFS temp dir = %s", cefs_temp_dir)

        return self.__class__.model_validate(config_dict)
