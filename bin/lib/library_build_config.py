from typing import Optional, Dict, Any

class LibraryBuildConfig:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.build_type = self.config_get("build_type", "")
        self.build_fixed_arch = self.config_get("build_fixed_arch", "")
        self.build_fixed_stdlib = self.config_get("build_fixed_stdlib", "")
        self.lib_type = self.config_get("lib_type", "static")
        self.staticliblink = self.config_get("staticliblink", [])
        self.sharedliblink = self.config_get("sharedliblink", [])
        self.url = "None"
        self.description = ""
        self.configure_flags = self.config_get("configure_flags", [])
        self.prebuild_script = self.config_get("prebuild_script", [])
        self.extra_cmake_arg = self.config_get("extra_cmake_arg", [])
        self.extra_make_arg = self.config_get("extra_make_arg", [])
        self.make_targets = self.config_get("make_targets", [])
        self.make_utility = self.config_get("make_utility", "make")
        self.package_extra_copy = self.config_get("package_extra_copy", [])
        self.skip_compilers = self.config_get("skip_compilers", [])

    def config_get(self, config_key: str, default: Optional[Any] = None) -> Any:
        if config_key not in self.config and default is None:
            raise RuntimeError(f"Missing required key '{config_key}'")
        return self.config.get(config_key, default)
