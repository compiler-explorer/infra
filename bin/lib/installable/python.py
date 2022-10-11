from __future__ import annotations

from typing import Dict, Any

from lib.installable.installable import Installable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


class PipInstallable(Installable):
    MV_URL = "https://raw.githubusercontent.com/brbsix/virtualenv-mv/master/virtualenv-mv"

    def __init__(self, install_context: InstallationContext, config: Dict[str, Any]):
        super().__init__(install_context, config)
        self.install_path = self.config_get("dir")
        self._setup_check_exe(self.install_path)
        self.package = self.config_get("package")
        self.python = self.config_get("python")

    def stage(self, staging: StagingDir) -> None:
        venv = staging.path / self.install_path
        self.install_context.check_output([self.python, "-mvenv", str(venv)])
        self.install_context.check_output([str(venv / "bin" / "pip"), "install", self.package])

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
            mv_script = staging.path / "virtualenv-mv"
            with mv_script.open("wb") as f:
                self.install_context.fetch_to(PipInstallable.MV_URL, f)
            mv_script.chmod(0o755)

            def mv_venv(source, dest):
                self.install_context.check_output([str(mv_script), str(source), str(dest)])

            self.install_context.move_from_staging(staging, self.install_path, do_staging_move=mv_venv)

    def __repr__(self) -> str:
        return f"PipInstallable({self.name}, {self.install_path})"
