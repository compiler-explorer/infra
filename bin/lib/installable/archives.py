from __future__ import annotations

import functools
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from lib.amazon import list_compilers
from lib.installable.installable import Installable, command_config
from lib.installation_context import InstallationContext, is_windows
from lib.staging import StagingDir

import re

VERSIONED_RE = re.compile(r"^(.*)-([0-9.]+)$")


class S3TarballInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.subdir = self.config_get("subdir", "")
        last_context = self.context[-1]
        if self.subdir:
            default_s3_path_prefix = f"{self.subdir}-{last_context}-{self.target_name}"
            default_path_name = f"{self.subdir}/{last_context}-{self.target_name}"
            default_untar_dir = f"{last_context}-{self.target_name}"
        else:
            default_s3_path_prefix = f"{last_context}-{self.target_name}"
            default_path_name = f"{last_context}-{self.target_name}"
            default_untar_dir = default_path_name
        s3_path_prefix = self.config_get("s3_path_prefix", default_s3_path_prefix)
        self.install_path = self.config_get("path_name", default_path_name)
        self.untar_dir = self.config_get("untar_dir", default_untar_dir)
        compression = self.config_get("compression", "xz")
        if compression == "xz":
            self.s3_path = f"{s3_path_prefix}.tar.xz"
            self.decompress_flag = "J"
        elif compression == "gz":
            self.s3_path = f"{s3_path_prefix}.tar.gz"
            self.decompress_flag = "z"
        elif compression == "bz2":
            self.s3_path = f"{s3_path_prefix}.tar.bz2"
            self.decompress_flag = "j"
        else:
            raise RuntimeError(f"Unknown compression {compression}")
        self.strip = self.config_get("strip", False)
        self._setup_check_exe(self.install_path)

    def stage(self, staging: StagingDir) -> None:
        self.install_context.fetch_s3_and_pipe_to(staging, self.s3_path, ["tar", f"{self.decompress_flag}xf", "-"])
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)

        self.install_context.run_script(staging, self.s3_path, self.after_stage_script)

    def verify(self) -> bool:
        if not super().verify():
            return False
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            return self.install_context.compare_against_staging(staging, self.untar_dir, self.install_path)

    def install(self) -> None:
        super().install()
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            if self.subdir:
                self.install_context.make_subdir(self.subdir)
            elif self.install_path:
                self.install_context.make_subdir(self.install_path)

            self.install_context.move_from_staging(staging, self.untar_dir, self.install_path)

    def __repr__(self) -> str:
        return f"S3TarballInstallable({self.name}, {self.install_path})"


class NightlyInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.subdir = self.config_get("subdir", "")
        self.strip = self.config_get("strip", False)
        compiler_name = self.config_get("compiler_name", f"{self.context[-1]}-{self.target_name}")
        current = s3_available_compilers()
        if compiler_name not in current:
            raise RuntimeError(f"Unable to find nightlies for {compiler_name}")
        most_recent = max(current[compiler_name])
        self._logger.info("Most recent %s is %s", compiler_name, most_recent)
        path_name_prefix = self.config_get("path_name_prefix", compiler_name)
        s3_name = self.config_get("s3_name", compiler_name)
        self.s3_path = f"{s3_name}-{most_recent}"
        self.local_path = f"{path_name_prefix}-{most_recent}"
        self.install_path = os.path.join(self.subdir, f"{path_name_prefix}-{most_recent}")
        self.compiler_pattern = os.path.join(self.subdir, f"{path_name_prefix}-*")
        self.path_name_symlink = self.config_get("symlink", os.path.join(self.subdir, f"{path_name_prefix}"))
        self.num_to_keep = self.config_get("num_to_keep", 5)
        self._setup_check_exe(self.install_path)
        self._setup_check_link(self.install_path, self.path_name_symlink)

    @property
    def nightly_like(self) -> bool:
        return True

    def stage(self, staging: StagingDir) -> None:
        self.install_context.fetch_s3_and_pipe_to(staging, f"{self.s3_path}.tar.xz", ["tar", "Jxf", "-"])
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)
        self.install_context.run_script(staging, staging.path / self.local_path, self.after_stage_script)

    def verify(self) -> bool:
        if not super().verify():
            return False
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            return self.install_context.compare_against_staging(staging, self.local_path, self.install_path)

    def should_install(self) -> bool:
        return True

    def install(self) -> None:
        super().install()
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)

            # Do this first, and add one for the file we haven't yet installed... (then dry run works)
            num_to_keep = self.num_to_keep + 1
            all_versions = list(sorted(self.install_context.glob(self.compiler_pattern)))
            for to_remove in all_versions[:-num_to_keep]:
                self.install_context.remove_dir(to_remove)

            self.install_context.move_from_staging(staging, self.local_path, self.install_path)
            self.install_context.set_link(Path(self.install_path), self.path_name_symlink)

    def __repr__(self) -> str:
        return f"NightlyInstallable({self.name}, {self.install_path})"


class TarballInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self.untar_path = self.config_get("untar_dir", self.install_path)
        if self.config_get("create_untar_dir", False):
            self.untar_to = self.untar_path
        else:
            self.untar_to = "."
        self.url = self.config_get("url")
        if self.config_get("compression") == "xz":
            decompress_flag = "J"
        elif self.config_get("compression") == "gz":
            decompress_flag = "z"
        elif self.config_get("compression") == "bz2":
            decompress_flag = "j"
        elif self.config_get("compression") == "tar":
            decompress_flag = ""
        else:
            raise RuntimeError(f'Unknown compression {self.config_get("compression")}')
        self.configure_command = command_config(self.config_get("configure_command", []))
        self.tar_cmd = ["tar", f"{decompress_flag}xf", "-"]
        strip_components = self.config_get("strip_components", 0)
        if strip_components:
            self.tar_cmd += ["--strip-components", str(strip_components)]
        extract_only = self.config_get("extract_only", "")
        if extract_only:
            self.tar_cmd += [extract_only]
        self.strip = self.config_get("strip", False)
        self._setup_check_exe(self.install_path)
        if self.install_path_symlink:
            self._setup_check_link(self.install_path, self.install_path_symlink)
        self.remove_older_pattern = self.config_get("remove_older_pattern", "")
        self.num_to_keep = self.config_get("num_to_keep", 5)

    def stage(self, staging: StagingDir) -> None:
        self.install_context.fetch_url_and_pipe_to(staging, f"{self.url}", self.tar_cmd, self.untar_to)
        if self.configure_command:
            self.install_context.stage_command(staging, self.configure_command)
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)
        if not (staging.path / self.untar_path).is_dir():
            raise RuntimeError(f"After unpacking, {self.untar_path} was not a directory")
        self.install_context.run_script(staging, staging.path / self.untar_to, self.after_stage_script)

    def verify(self) -> bool:
        if not super().verify():
            return False
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            return self.install_context.compare_against_staging(staging, self.untar_path, self.install_path)

    def install(self) -> None:
        super().install()
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)

            if self.remove_older_pattern:
                # Do this first, and add one for the file we haven't yet installed... (then dry run works)
                num_to_keep = self.num_to_keep + 1
                all_versions = list(sorted(self.install_context.glob(self.remove_older_pattern)))
                for to_remove in all_versions[:-num_to_keep]:
                    self.install_context.remove_dir(to_remove)

            self.install_context.move_from_staging(staging, self.untar_path, self.install_path)
            if self.install_path_symlink:
                self.install_context.set_link(Path(self.install_path), self.install_path_symlink)

    def __repr__(self) -> str:
        return f"TarballInstallable({self.name}, {self.install_path})"


class NightlyTarballInstallable(TarballInstallable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)

        if not self.install_path_symlink:
            self.install_path_symlink = f"{self.install_path}"

        if not self.remove_older_pattern:
            self.remove_older_pattern = f"{self.install_path}-*"

        today = datetime.today().strftime("%Y%m%d")
        self.install_path = f"{self.install_path}-{today}"

        # redo exe checks
        self._setup_check_exe(self.install_path)
        self._setup_check_link(self.install_path, self.install_path_symlink)

    @property
    def nightly_like(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"NightlyTarballInstallable({self.name}, {self.install_path})"


class ZipArchiveInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.url = self.config_get("url")
        self.install_path = self.config_get("dir")
        self.extract_into_folder = self.config_get("extract_into_folder", False)
        self.folder_to_rename = self.config_get("folder", None if not self.extract_into_folder else "tmp")
        self.configure_command = command_config(self.config_get("configure_command", []))
        self.strip = self.config_get("strip", False)
        self._setup_check_exe(self.install_path)
        if self.install_path_symlink:
            self._setup_check_link(self.install_path, self.install_path_symlink)

    def stage(self, staging: StagingDir) -> None:
        # Unzip does not support stdin piping so we need to create a file
        with (staging.path / "distribution.zip").open("wb") as fd:
            self.install_context.fetch_to(self.url, fd)
            if not is_windows():
                unzip_cmd = ["unzip", "-q", fd.name]
            else:
                unzip_cmd = ["tar", "-xf", fd.name]
            if self.extract_into_folder:
                unzip_cmd.extend(["-d", self.folder_to_rename])
            self.install_context.stage_command(staging, unzip_cmd)
            if self.folder_to_rename != self.install_path:
                if not is_windows():
                    self.install_context.stage_command(staging, ["mv", self.folder_to_rename, self.install_path])
                else:
                    self.install_context.stage_command(
                        staging, ["cmd", "/C", "rename", self.folder_to_rename, self.install_path]
                    )

        if self.configure_command:
            self.install_context.stage_command(staging, self.configure_command)
        if self.strip:
            self.install_context.strip_exes(staging, self.strip)
        full_install_path = staging.path / self.install_path
        if not full_install_path.is_dir():
            raise RuntimeError(f"After unpacking, {self.install_path} was not a directory")
        self.install_context.run_script(staging, full_install_path, self.after_stage_script)

    def verify(self) -> bool:
        if not super().verify():
            return False
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            return self.install_context.compare_against_staging(staging, self.install_path)

    def install(self) -> None:
        super().install()
        with self.install_context.new_staging_dir() as staging:
            self.stage(staging)
            self.install_context.move_from_staging(staging, self.install_path)
            if self.install_path_symlink:
                self.install_context.set_link(Path(self.install_path), self.install_path_symlink)

    def __repr__(self) -> str:
        return f"ZipArchiveInstallable({self.name}, {self.install_path})"


@functools.lru_cache(maxsize=1)
def s3_available_compilers():
    compilers = defaultdict(lambda: [])
    for compiler in list_compilers():
        match = VERSIONED_RE.match(compiler)
        if match:
            compilers[match.group(1)].append(match.group(2))
    return compilers


class RestQueryTarballInstallable(TarballInstallable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        document = self.install_context.fetch_rest_query(self.config_get("url"))
        query = self.config_get("query")
        try:
            # pylint: disable-next=eval-used
            self.url = eval(query, {}, dict(document=document))
        except Exception:
            self._logger.exception("Exception evaluating query '%s' for %s", query, self)
            raise
        if not self.url:
            self._logger.warning("No installation candidate found")
        else:
            self._logger.info("resolved to %s", self.url)

    def should_install(self) -> bool:
        if not self.url:
            return False
        return super().should_install()

    def __repr__(self) -> str:
        return f"RestQueryTarballInstallable({self.name}, {self.install_path})"
