from collections import defaultdict
from typing import Any, Dict
from lib.amazon import dynamodb_client
from lib.amazon_properties import get_properties_compilers_and_libraries

class NightlyVersions:
    version_table_name: str = "nightly-version"
    exe_table_name: str = "nightly-exe"
    props_loaded: bool = False
    cpp: Dict[str, Dict[str, Any]] = defaultdict(lambda: {})
    c: Dict[str, Dict[str, Any]] = defaultdict(lambda: {})
    fortran: Dict[str, Dict[str, Any]] = defaultdict(lambda: {})
    rust: Dict[str, Dict[str, Any]] = defaultdict(lambda: {})
    swift: Dict[str, Dict[str, Any]] = defaultdict(lambda: {})
    clean: Dict[str, Dict[str, Any]] = defaultdict(lambda: {})

    def __init__(self, logger):
        self.logger = logger

    def load_ce_properties(self):
        if not self.props_loaded:
            [self.cpp, _] = get_properties_compilers_and_libraries("c++", self.logger)
            [self.c, _] = get_properties_compilers_and_libraries("c", self.logger)
            [self.fortran, _] = get_properties_compilers_and_libraries("fortran", self.logger)
            [self.rust, _] = get_properties_compilers_and_libraries("rust", self.logger)
            [self.swift, _] = get_properties_compilers_and_libraries("swift", self.logger)
            [self.clean, _] = get_properties_compilers_and_libraries("clean", self.logger)
            self.props_loaded = True

    def as_c_compiler(self, exe: str):
        if exe.endswith("/g++"):
            return exe[:-3] + "gcc"
        if exe.endswith("/clang++"):
            return exe[:-2]
        return exe

    def as_fortran_compiler(self, exe: str):
        if exe.endswith("/g++"):
            return exe[:-3] + "gfortran"
        return exe

    def collect_compiler_ids_for(self, ids: set, exe: str, compilers: Dict[str, Dict[str, Any]]):
        for compiler_id in compilers:
            compiler = compilers[compiler_id]
            if exe == compiler["exe"]:
                ids.add(compiler_id)

    def get_compiler_ids(self, exe: str):
        self.load_ce_properties()

        ids = set()

        self.collect_compiler_ids_for(ids, exe, self.cpp)
        self.collect_compiler_ids_for(ids, exe, self.rust)
        self.collect_compiler_ids_for(ids, exe, self.swift)
        self.collect_compiler_ids_for(ids, exe, self.clean)

        cexe = self.as_c_compiler(exe)
        self.collect_compiler_ids_for(ids, cexe, self.c)

        fortranexe = self.as_fortran_compiler(exe)
        self.collect_compiler_ids_for(ids, fortranexe, self.fortran)

        return ids

    def update_version(self, exe: str, modified: str, version: str, full_version: str):
        compiler_ids = self.get_compiler_ids(exe)
        if len(compiler_ids) == 0:
            self.logger.warning(f"No compiler ids found for {exe} - not saving compiler version info to AWS")
            return

        dynamodb_client.put_item(
            TableName=self.version_table_name,
            Item={
                "exe": {"S": exe},
                "modified": {"N": modified},
                "version": {"S": version},
                "full_version": {"S": full_version},
            },
        )

        for compiler_id in compiler_ids:
            dynamodb_client.put_item(
                TableName=self.exe_table_name,
                Item={
                    "id": {"S": compiler_id},
                    "exe": {"S": exe},
                },
            )

        return

    def get_version(self, exe: str):
        result = dynamodb_client.get_item(
            TableName=self.version_table_name,
            Key={"exe": {"S": exe}},
            ConsistentRead=True,
        )
        item = result.get("Item")
        if item:
            return {
                "exe": item["exe"]["S"],
                "version": item["version"]["S"],
                "full_version": item["full_version"]["S"],
                "modified": item["modified"]["N"],
            }
        else:
            return None
