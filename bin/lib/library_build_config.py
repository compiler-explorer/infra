from typing import Optional, BinaryIO, Sequence, Collection, List, Union, Dict, Any

class LibraryBuildConfig:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.build_type = self.config_get("build_type", "")
        self.build_fixed_arch = self.config_get("build_fixed_arch", "")
        self.build_fixed_stdlib = self.config_get("build_fixed_stdlib", "")
        self.lib_type = self.config_get("lib_type", "static")
        self.staticliblink = []
        self.sharedliblink = []
        self.url = "None"
        self.description = ""
        self.prebuildscript = self.config_get("prebuildscript", [])
        self.extra_cmake_arg = self.config_get("extra_cmake_arg", [])
        self.make_targets = self.config_get("make_targets", [])

    def config_get(self, config_key: str, default: Optional[Any] = None) -> Any:
        if config_key not in self.config and default is None:
            raise RuntimeError(f"Missing required key '{config_key}' in {self.name}")
        return self.config.get(config_key, default)
