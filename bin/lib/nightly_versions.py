from __future__ import annotations

from collections import defaultdict
from typing import Any

from lib.amazon import dynamodb_client
from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.library_platform import LibraryPlatform


class NightlyVersions:
    version_table_name: str = "nightly-version"
    exe_table_name: str = "nightly-exe"
    props_loaded: bool = False

    ada: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    assembly: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    c: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    circle: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    circt: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    clean: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cpp_for_opencl: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cpp: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cppx: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cppx_blue: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cppx_gold: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    d: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    dart: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    fortran: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    go: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    hlsl: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    ispc: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    javascript: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    mlir: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    nim: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    objc: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    objcpp: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    pony: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    racket: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    rust: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    swift: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    zig: dict[str, dict[str, Any]] = defaultdict(lambda: {})

    def __init__(self, logger):
        self.logger = logger

    def load_ce_properties(self):
        platform = LibraryPlatform.Linux
        if not self.props_loaded:
            [self.ada, _] = get_properties_compilers_and_libraries("ada", self.logger, platform, False)
            [self.assembly, _] = get_properties_compilers_and_libraries("assembly", self.logger, platform, False)
            [self.c, _] = get_properties_compilers_and_libraries("c", self.logger, platform, False)
            [self.circle, _] = get_properties_compilers_and_libraries("circle", self.logger, platform, False)
            [self.circt, _] = get_properties_compilers_and_libraries("circt", self.logger, platform, False)
            [self.clean, _] = get_properties_compilers_and_libraries("clean", self.logger, platform, False)
            [self.cpp_for_opencl, _] = get_properties_compilers_and_libraries(
                "cpp_for_opencl", self.logger, platform, False
            )
            [self.cpp, _] = get_properties_compilers_and_libraries("c++", self.logger, platform, False)
            [self.cppx, _] = get_properties_compilers_and_libraries("cppx", self.logger, platform, False)
            [self.cppx_blue, _] = get_properties_compilers_and_libraries("cppx_blue", self.logger, platform, False)
            [self.cppx_gold, _] = get_properties_compilers_and_libraries("cppx_gold", self.logger, platform, False)
            [self.d, _] = get_properties_compilers_and_libraries("d", self.logger, platform, False)
            [self.dart, _] = get_properties_compilers_and_libraries("dart", self.logger, platform, False)
            [self.fortran, _] = get_properties_compilers_and_libraries("fortran", self.logger, platform, False)
            [self.go, _] = get_properties_compilers_and_libraries("go", self.logger, platform, False)
            [self.hlsl, _] = get_properties_compilers_and_libraries("hlsl", self.logger, platform, False)
            [self.ispc, _] = get_properties_compilers_and_libraries("ispc", self.logger, platform, False)
            [self.javascript, _] = get_properties_compilers_and_libraries("javascript", self.logger, platform, False)
            [self.mlir, _] = get_properties_compilers_and_libraries("mlir", self.logger, platform, False)
            [self.nim, _] = get_properties_compilers_and_libraries("nim", self.logger, platform, False)
            [self.objc, _] = get_properties_compilers_and_libraries("objc", self.logger, platform, False)
            [self.objcpp, _] = get_properties_compilers_and_libraries("objc++", self.logger, platform, False)
            [self.pony, _] = get_properties_compilers_and_libraries("pony", self.logger, platform, False)
            [self.racket, _] = get_properties_compilers_and_libraries("racket", self.logger, platform, False)
            [self.rust, _] = get_properties_compilers_and_libraries("rust", self.logger, platform, False)
            [self.swift, _] = get_properties_compilers_and_libraries("swift", self.logger, platform, False)
            [self.zig, _] = get_properties_compilers_and_libraries("zig", self.logger, platform, False)

            self.props_loaded = True

    def as_assembly_compiler(self, exe: str):
        if exe.endswith("/g++"):
            return exe[:-3] + "as"
        if exe.endswith("/clang++"):
            return exe[:-7] + "llvm-mc"
        return exe

    def as_ada_compiler(self, exe: str):
        if exe.endswith("/g++"):
            return exe[:-3] + "gnat"
        return exe

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

    def collect_compiler_ids_for(self, ids: set, exe: str, compilers: dict[str, dict[str, Any]]):
        for compiler_id in compilers:
            compiler = compilers[compiler_id]
            if "exe" in compiler and exe == compiler["exe"]:
                ids.add(compiler_id)

    def get_compiler_ids(self, exe: str):
        self.load_ce_properties()

        ids: set = set()

        ada_exe = self.as_ada_compiler(exe)
        c_exe = self.as_c_compiler(exe)
        fortran_exe = self.as_fortran_compiler(exe)
        assembly_exe = self.as_assembly_compiler(exe)

        self.collect_compiler_ids_for(ids, ada_exe, self.ada)
        self.collect_compiler_ids_for(ids, assembly_exe, self.assembly)
        self.collect_compiler_ids_for(ids, c_exe, self.c)
        self.collect_compiler_ids_for(ids, exe, self.circle)
        self.collect_compiler_ids_for(ids, exe, self.circt)
        self.collect_compiler_ids_for(ids, exe, self.clean)
        self.collect_compiler_ids_for(ids, c_exe, self.cpp_for_opencl)
        self.collect_compiler_ids_for(ids, exe, self.cpp)
        self.collect_compiler_ids_for(ids, exe, self.cppx)
        self.collect_compiler_ids_for(ids, exe, self.cppx_blue)
        self.collect_compiler_ids_for(ids, exe, self.cppx_gold)
        self.collect_compiler_ids_for(ids, exe, self.d)
        self.collect_compiler_ids_for(ids, exe, self.dart)
        self.collect_compiler_ids_for(ids, fortran_exe, self.fortran)
        self.collect_compiler_ids_for(ids, exe, self.go)
        self.collect_compiler_ids_for(ids, exe, self.hlsl)
        self.collect_compiler_ids_for(ids, exe, self.ispc)
        self.collect_compiler_ids_for(ids, exe, self.javascript)
        self.collect_compiler_ids_for(ids, exe, self.mlir)
        self.collect_compiler_ids_for(ids, exe, self.nim)
        self.collect_compiler_ids_for(ids, c_exe, self.objc)
        self.collect_compiler_ids_for(ids, exe, self.objcpp)
        self.collect_compiler_ids_for(ids, exe, self.pony)
        self.collect_compiler_ids_for(ids, exe, self.racket)
        self.collect_compiler_ids_for(ids, exe, self.rust)
        self.collect_compiler_ids_for(ids, exe, self.swift)
        self.collect_compiler_ids_for(ids, exe, self.zig)

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
