from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from functools import partial
from pathlib import Path
from typing import Optional, Callable, Dict, List, Any, Union

from lib.installation_context import InstallationContext
from lib.library_build_config import LibraryBuildConfig
from lib.library_builder import LibraryBuilder
from lib.rust_library_builder import RustLibraryBuilder
from lib.staging import StagingDir

_LOGGER = logging.getLogger(__name__)

SimpleJsonType = (int, float, str, bool)


class Installable:
    _check_link: Optional[Callable[[], bool]]
    check_env: Dict
    check_file: Optional[str]
    check_call: List[str]

    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        self.install_context = install_context
        self.config = config
        self.target_name = str(self.config.get("name", "(unnamed)"))
        self.context = self.config_get("context", [])
        self.name = f'{"/".join(self.context)} {self.target_name}'
        self.is_library = False
        self.language = False
        if len(self.context) > 0:
            self.is_library = self.context[0] == "libraries"
            self.language = self.context[1]
        self.depends_by_name = self.config.get("depends", [])
        self.depends: List[Installable] = []
        self.install_always = self.config.get("install_always", False)
        self._check_link = None
        self.build_config = LibraryBuildConfig(config)
        self.check_env = {}
        self.check_file = None
        self.check_call = []
        self.check_stderr_on_stdout = self.config.get("check_stderr_on_stdout", False)
        self.install_path = ""
        self.after_stage_script = self.config_get("after_stage_script", [])
        self._logger = logging.getLogger(self.name)
        self.install_path_symlink = self.config_get("symlink", False)

    def to_json_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if isinstance(value, SimpleJsonType)}

    def to_json(self) -> str:
        return json.dumps(self.to_json_dict())

    def _setup_check_exe(self, path_name: str) -> None:
        self.check_env = dict([x.replace("%PATH%", path_name).split("=", 1) for x in self.config_get("check_env", [])])

        check_file = self.config_get("check_file", "")
        if check_file:
            self.check_file = os.path.join(path_name, check_file)
        else:
            self.check_call = command_config(self.config_get("check_exe"))
            self.check_call[0] = os.path.join(path_name, self.check_call[0])

    def _setup_check_link(self, source: str, link: str) -> None:
        self._check_link = partial(self.install_context.check_link, source, link)

    def link(self, all_installables: Dict[str, Installable]):
        try:
            self.depends = [all_installables[dep] for dep in self.depends_by_name]
        except KeyError as ke:
            self._logger.error("Unable to find dependency %s in %s", ke, all_installables)
            raise
        dep_re = re.compile("%DEP([0-9]+)%")

        def dep_n(match):
            return str(self.install_context.destination / self.depends[int(match.group(1))].install_path)

        for k in self.check_env.keys():
            self.check_env[k] = dep_re.sub(dep_n, self.check_env[k])

    def find_dependee(self, name: str) -> Installable:
        for i in self.depends:
            if i.name == name:
                return i
        raise RuntimeError(f"Missing dependee {name} - did you forget to add it as a dependency?")

    def verify(self) -> bool:
        return True

    def should_install(self) -> bool:
        return self.install_always or not self.is_installed()

    def should_build(self):
        return (
            self.is_library
            and self.build_config.build_type != "manual"
            and self.build_config.build_type != "none"
            and self.build_config.build_type != ""
        )

    def install(self) -> None:
        self._logger.debug("Ensuring dependees are installed")
        for dependee in self.depends:
            if not dependee.is_installed():
                self._logger.info("Installing required dependee %s", dependee)
                dependee.install()
        self._logger.debug("Dependees installed")

    def is_installed(self) -> bool:
        if self.check_file is None and not self.check_call:
            return True

        if self._check_link and not self._check_link():
            self._logger.debug("Check link returned false")
            return False

        if self.check_file:
            res = (self.install_context.destination / self.check_file).is_file()
            self._logger.debug(
                'Check file for "%s" returned %s', self.install_context.destination / self.check_file, res
            )
            return res

        try:
            res_call = self.install_context.check_output(
                self.check_call, env=self.check_env, stderr_on_stdout=self.check_stderr_on_stdout
            )
            self._logger.debug("Check call returned %s", res_call)
            return True
        except FileNotFoundError:
            self._logger.debug("File not found for %s", self.check_call)
            return False
        except subprocess.CalledProcessError:
            self._logger.debug("Got an error for %s", self.check_call)
            return False

    def config_get(self, config_key: str, default: Optional[Any] = None) -> Any:
        if config_key not in self.config and default is None:
            raise RuntimeError(f"Missing required key '{config_key}' in {self.name}")
        return self.config.get(config_key, default)

    def __repr__(self) -> str:
        return f"Installable({self.name})"

    @property
    def sort_key(self):
        return self.context, [
            (int(num) if num else 0, non) for num, non in re.findall(r"([0-9]+)|([^0-9]+)", self.target_name)
        ]

    @property
    def nightly_like(self) -> bool:
        return False

    def build(self, buildfor):
        if not self.is_library:
            raise RuntimeError("Nothing to build")

        if self.build_config.build_type == "":
            raise RuntimeError("No build_type")

        if self.build_config.build_type in ["cmake", "make"]:
            sourcefolder = os.path.join(self.install_context.destination, self.install_path)
            builder = LibraryBuilder(
                _LOGGER,
                self.language,
                self.context[-1],
                self.target_name,
                sourcefolder,
                self.install_context,
                self.build_config,
            )
            if self.build_config.build_type == "cmake":
                return builder.makebuild(buildfor)
            elif self.build_config.build_type == "make":
                return builder.makebuild(buildfor)
        elif self.build_config.build_type == "cargo":
            builder = RustLibraryBuilder(
                _LOGGER, self.language, self.context[-1], self.target_name, self.install_context, self.build_config
            )
            return builder.makebuild(buildfor)
        else:
            raise RuntimeError("Unsupported build_type")

    def squash_to(self, destination_image: Path):
        destination_image.parent.mkdir(parents=True, exist_ok=True)
        source_folder = self.install_context.destination / self.install_path
        temp_image = destination_image.with_suffix(".tmp")
        temp_image.unlink(missing_ok=True)
        self._logger.info("Squashing %s...", source_folder)
        self.install_context.check_call(
            [
                "mksquashfs",
                str(source_folder),
                str(temp_image),
                "-progress",
                "-comp",
                "zstd",
                "-Xcompression-level",
                "19",
            ]
        )
        temp_image.replace(destination_image)


class SingleFileInstallable(Installable):
    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self.url = self.config_get("url")
        self.filename = self.config_get("filename")
        self._setup_check_exe(self.install_path)

    def stage(self, staging: StagingDir) -> None:
        out_path = staging.path / self.install_path
        out_path.mkdir()
        out_file_path = out_path / self.filename
        with out_file_path.open("wb") as f:
            self.install_context.fetch_to(self.url, f)
        out_file_path.chmod(0o755)

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

    def __repr__(self) -> str:
        return f"SingleFileInstallable({self.name}, {self.install_path})"


def command_config(config: Union[List[str], str]) -> List[str]:
    if isinstance(config, str):
        return config.split(" ")
    return config
