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
    algol68: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    analysis: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    android_java: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    android_kotlin: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    assembly: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    c: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    c3: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    carbon: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    circle: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    circt: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    clean: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    clojure: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cmakescript: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    co2: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cobol: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cpp2_cppfront: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cpp_for_opencl: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cpp: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cppx: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cppx_blue: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cppx_gold: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    crystal: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    csharp: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cuda: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    cutedsl: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    d: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    dart: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    erlang: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    fortran: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    fsharp: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    gimple: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    glsl: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    go: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    haskell: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    hlsl: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    hook: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    hylo: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    il: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    ispc: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    java: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    javascript: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    julia: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    kotlin: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    lean: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    llvm: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    llvm_mir: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    lua: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    mach: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    mlir: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    modula2: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    mojo: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    nim: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    nix: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    numba: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    objc: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    objcpp: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    ocaml: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    odin: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    openclc: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    pascal: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    perl: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    pony: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    ptx: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    python: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    racket: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    raku: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    razorforge: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    ruby: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    rust: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    sail: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    scala: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    sfpi: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    slang: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    snowball: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    solidity: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    spice: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    spirv: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    sway: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    swift: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    tablegen: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    triton: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    typescript: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    v: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    vala: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    vb: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    vyper: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    wasm: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    ylc: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    yul: dict[str, dict[str, Any]] = defaultdict(lambda: {})
    zig: dict[str, dict[str, Any]] = defaultdict(lambda: {})

    def __init__(self, logger):
        self.logger = logger

    def load_ce_properties(self):
        platform = LibraryPlatform.Linux
        if not self.props_loaded:
            [self.ada, _] = get_properties_compilers_and_libraries("ada", self.logger, platform, False)
            [self.algol68, _] = get_properties_compilers_and_libraries("algol68", self.logger, platform, False)
            [self.analysis, _] = get_properties_compilers_and_libraries("analysis", self.logger, platform, False)
            [self.android_java, _] = get_properties_compilers_and_libraries(
                "android-java", self.logger, platform, False
            )
            [self.android_kotlin, _] = get_properties_compilers_and_libraries(
                "android-kotlin", self.logger, platform, False
            )
            [self.assembly, _] = get_properties_compilers_and_libraries("assembly", self.logger, platform, False)
            [self.c, _] = get_properties_compilers_and_libraries("c", self.logger, platform, False)
            [self.c3, _] = get_properties_compilers_and_libraries("c3", self.logger, platform, False)
            [self.carbon, _] = get_properties_compilers_and_libraries("carbon", self.logger, platform, False)
            [self.circle, _] = get_properties_compilers_and_libraries("circle", self.logger, platform, False)
            [self.circt, _] = get_properties_compilers_and_libraries("circt", self.logger, platform, False)
            [self.clean, _] = get_properties_compilers_and_libraries("clean", self.logger, platform, False)
            [self.clojure, _] = get_properties_compilers_and_libraries("clojure", self.logger, platform, False)
            [self.cmakescript, _] = get_properties_compilers_and_libraries("cmakescript", self.logger, platform, False)
            [self.co2, _] = get_properties_compilers_and_libraries("co2", self.logger, platform, False)
            [self.cobol, _] = get_properties_compilers_and_libraries("cobol", self.logger, platform, False)
            [self.cpp2_cppfront, _] = get_properties_compilers_and_libraries(
                "cpp2_cppfront", self.logger, platform, False
            )
            [self.cpp_for_opencl, _] = get_properties_compilers_and_libraries(
                "cpp_for_opencl", self.logger, platform, False
            )
            [self.cpp, _] = get_properties_compilers_and_libraries("c++", self.logger, platform, False)
            [self.cppx, _] = get_properties_compilers_and_libraries("cppx", self.logger, platform, False)
            [self.cppx_blue, _] = get_properties_compilers_and_libraries("cppx_blue", self.logger, platform, False)
            [self.cppx_gold, _] = get_properties_compilers_and_libraries("cppx_gold", self.logger, platform, False)
            [self.crystal, _] = get_properties_compilers_and_libraries("crystal", self.logger, platform, False)
            [self.csharp, _] = get_properties_compilers_and_libraries("csharp", self.logger, platform, False)
            [self.cuda, _] = get_properties_compilers_and_libraries("cuda", self.logger, platform, False)
            [self.cutedsl, _] = get_properties_compilers_and_libraries("cutedsl", self.logger, platform, False)
            [self.d, _] = get_properties_compilers_and_libraries("d", self.logger, platform, False)
            [self.dart, _] = get_properties_compilers_and_libraries("dart", self.logger, platform, False)
            [self.erlang, _] = get_properties_compilers_and_libraries("erlang", self.logger, platform, False)
            [self.fortran, _] = get_properties_compilers_and_libraries("fortran", self.logger, platform, False)
            [self.fsharp, _] = get_properties_compilers_and_libraries("fsharp", self.logger, platform, False)
            [self.gimple, _] = get_properties_compilers_and_libraries("gimple", self.logger, platform, False)
            [self.glsl, _] = get_properties_compilers_and_libraries("glsl", self.logger, platform, False)
            [self.go, _] = get_properties_compilers_and_libraries("go", self.logger, platform, False)
            [self.haskell, _] = get_properties_compilers_and_libraries("haskell", self.logger, platform, False)
            [self.hlsl, _] = get_properties_compilers_and_libraries("hlsl", self.logger, platform, False)
            [self.hook, _] = get_properties_compilers_and_libraries("hook", self.logger, platform, False)
            [self.hylo, _] = get_properties_compilers_and_libraries("hylo", self.logger, platform, False)
            [self.il, _] = get_properties_compilers_and_libraries("il", self.logger, platform, False)
            [self.ispc, _] = get_properties_compilers_and_libraries("ispc", self.logger, platform, False)
            [self.java, _] = get_properties_compilers_and_libraries("java", self.logger, platform, False)
            [self.javascript, _] = get_properties_compilers_and_libraries("javascript", self.logger, platform, False)
            [self.julia, _] = get_properties_compilers_and_libraries("julia", self.logger, platform, False)
            [self.kotlin, _] = get_properties_compilers_and_libraries("kotlin", self.logger, platform, False)
            [self.lean, _] = get_properties_compilers_and_libraries("lean", self.logger, platform, False)
            [self.llvm, _] = get_properties_compilers_and_libraries("llvm", self.logger, platform, False)
            [self.llvm_mir, _] = get_properties_compilers_and_libraries("llvm_mir", self.logger, platform, False)
            [self.lua, _] = get_properties_compilers_and_libraries("lua", self.logger, platform, False)
            [self.mach, _] = get_properties_compilers_and_libraries("mach", self.logger, platform, False)
            [self.mlir, _] = get_properties_compilers_and_libraries("mlir", self.logger, platform, False)
            [self.modula2, _] = get_properties_compilers_and_libraries("modula2", self.logger, platform, False)
            [self.mojo, _] = get_properties_compilers_and_libraries("mojo", self.logger, platform, False)
            [self.nim, _] = get_properties_compilers_and_libraries("nim", self.logger, platform, False)
            [self.nix, _] = get_properties_compilers_and_libraries("nix", self.logger, platform, False)
            [self.numba, _] = get_properties_compilers_and_libraries("numba", self.logger, platform, False)
            [self.objc, _] = get_properties_compilers_and_libraries("objc", self.logger, platform, False)
            [self.objcpp, _] = get_properties_compilers_and_libraries("objc++", self.logger, platform, False)
            [self.ocaml, _] = get_properties_compilers_and_libraries("ocaml", self.logger, platform, False)
            [self.odin, _] = get_properties_compilers_and_libraries("odin", self.logger, platform, False)
            [self.openclc, _] = get_properties_compilers_and_libraries("openclc", self.logger, platform, False)
            [self.pascal, _] = get_properties_compilers_and_libraries("pascal", self.logger, platform, False)
            [self.perl, _] = get_properties_compilers_and_libraries("perl", self.logger, platform, False)
            [self.pony, _] = get_properties_compilers_and_libraries("pony", self.logger, platform, False)
            [self.ptx, _] = get_properties_compilers_and_libraries("ptx", self.logger, platform, False)
            [self.python, _] = get_properties_compilers_and_libraries("python", self.logger, platform, False)
            [self.racket, _] = get_properties_compilers_and_libraries("racket", self.logger, platform, False)
            [self.raku, _] = get_properties_compilers_and_libraries("raku", self.logger, platform, False)
            [self.razorforge, _] = get_properties_compilers_and_libraries("razorforge", self.logger, platform, False)
            [self.ruby, _] = get_properties_compilers_and_libraries("ruby", self.logger, platform, False)
            [self.rust, _] = get_properties_compilers_and_libraries("rust", self.logger, platform, False)
            [self.sail, _] = get_properties_compilers_and_libraries("sail", self.logger, platform, False)
            [self.scala, _] = get_properties_compilers_and_libraries("scala", self.logger, platform, False)
            [self.sfpi, _] = get_properties_compilers_and_libraries("sfpi", self.logger, platform, False)
            [self.slang, _] = get_properties_compilers_and_libraries("slang", self.logger, platform, False)
            [self.snowball, _] = get_properties_compilers_and_libraries("snowball", self.logger, platform, False)
            [self.solidity, _] = get_properties_compilers_and_libraries("solidity", self.logger, platform, False)
            [self.spice, _] = get_properties_compilers_and_libraries("spice", self.logger, platform, False)
            [self.spirv, _] = get_properties_compilers_and_libraries("spirv", self.logger, platform, False)
            [self.sway, _] = get_properties_compilers_and_libraries("sway", self.logger, platform, False)
            [self.swift, _] = get_properties_compilers_and_libraries("swift", self.logger, platform, False)
            [self.tablegen, _] = get_properties_compilers_and_libraries("tablegen", self.logger, platform, False)
            [self.triton, _] = get_properties_compilers_and_libraries("triton", self.logger, platform, False)
            [self.typescript, _] = get_properties_compilers_and_libraries("typescript", self.logger, platform, False)
            [self.v, _] = get_properties_compilers_and_libraries("v", self.logger, platform, False)
            [self.vala, _] = get_properties_compilers_and_libraries("vala", self.logger, platform, False)
            [self.vb, _] = get_properties_compilers_and_libraries("vb", self.logger, platform, False)
            [self.vyper, _] = get_properties_compilers_and_libraries("vyper", self.logger, platform, False)
            [self.wasm, _] = get_properties_compilers_and_libraries("wasm", self.logger, platform, False)
            [self.ylc, _] = get_properties_compilers_and_libraries("ylc", self.logger, platform, False)
            [self.yul, _] = get_properties_compilers_and_libraries("yul", self.logger, platform, False)
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
        for compiler_id, compiler in compilers.items():
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
        self.collect_compiler_ids_for(ids, exe, self.algol68)
        self.collect_compiler_ids_for(ids, exe, self.analysis)
        self.collect_compiler_ids_for(ids, exe, self.android_java)
        self.collect_compiler_ids_for(ids, exe, self.android_kotlin)
        self.collect_compiler_ids_for(ids, assembly_exe, self.assembly)
        self.collect_compiler_ids_for(ids, c_exe, self.c)
        self.collect_compiler_ids_for(ids, exe, self.c3)
        self.collect_compiler_ids_for(ids, exe, self.carbon)
        self.collect_compiler_ids_for(ids, exe, self.circle)
        self.collect_compiler_ids_for(ids, exe, self.circt)
        self.collect_compiler_ids_for(ids, exe, self.clean)
        self.collect_compiler_ids_for(ids, exe, self.clojure)
        self.collect_compiler_ids_for(ids, exe, self.cmakescript)
        self.collect_compiler_ids_for(ids, exe, self.co2)
        self.collect_compiler_ids_for(ids, exe, self.cobol)
        self.collect_compiler_ids_for(ids, exe, self.cpp2_cppfront)
        self.collect_compiler_ids_for(ids, c_exe, self.cpp_for_opencl)
        self.collect_compiler_ids_for(ids, exe, self.cpp)
        self.collect_compiler_ids_for(ids, exe, self.cppx)
        self.collect_compiler_ids_for(ids, exe, self.cppx_blue)
        self.collect_compiler_ids_for(ids, exe, self.cppx_gold)
        self.collect_compiler_ids_for(ids, exe, self.crystal)
        self.collect_compiler_ids_for(ids, exe, self.csharp)
        self.collect_compiler_ids_for(ids, exe, self.cuda)
        self.collect_compiler_ids_for(ids, exe, self.cutedsl)
        self.collect_compiler_ids_for(ids, exe, self.d)
        self.collect_compiler_ids_for(ids, exe, self.dart)
        self.collect_compiler_ids_for(ids, exe, self.erlang)
        self.collect_compiler_ids_for(ids, fortran_exe, self.fortran)
        self.collect_compiler_ids_for(ids, exe, self.fsharp)
        self.collect_compiler_ids_for(ids, c_exe, self.gimple)
        self.collect_compiler_ids_for(ids, exe, self.glsl)
        self.collect_compiler_ids_for(ids, exe, self.go)
        self.collect_compiler_ids_for(ids, exe, self.haskell)
        self.collect_compiler_ids_for(ids, c_exe, self.hlsl)
        self.collect_compiler_ids_for(ids, exe, self.hook)
        self.collect_compiler_ids_for(ids, exe, self.hylo)
        self.collect_compiler_ids_for(ids, exe, self.il)
        self.collect_compiler_ids_for(ids, exe, self.ispc)
        self.collect_compiler_ids_for(ids, exe, self.java)
        self.collect_compiler_ids_for(ids, exe, self.javascript)
        self.collect_compiler_ids_for(ids, exe, self.julia)
        self.collect_compiler_ids_for(ids, exe, self.kotlin)
        self.collect_compiler_ids_for(ids, exe, self.lean)
        self.collect_compiler_ids_for(ids, exe, self.llvm)
        self.collect_compiler_ids_for(ids, exe, self.llvm_mir)
        self.collect_compiler_ids_for(ids, exe, self.lua)
        self.collect_compiler_ids_for(ids, exe, self.mach)
        self.collect_compiler_ids_for(ids, exe, self.mlir)
        self.collect_compiler_ids_for(ids, exe, self.modula2)
        self.collect_compiler_ids_for(ids, exe, self.mojo)
        self.collect_compiler_ids_for(ids, exe, self.nim)
        self.collect_compiler_ids_for(ids, exe, self.nix)
        self.collect_compiler_ids_for(ids, exe, self.numba)
        self.collect_compiler_ids_for(ids, c_exe, self.objc)
        self.collect_compiler_ids_for(ids, exe, self.objcpp)
        self.collect_compiler_ids_for(ids, exe, self.ocaml)
        self.collect_compiler_ids_for(ids, exe, self.odin)
        self.collect_compiler_ids_for(ids, c_exe, self.openclc)
        self.collect_compiler_ids_for(ids, exe, self.pascal)
        self.collect_compiler_ids_for(ids, exe, self.perl)
        self.collect_compiler_ids_for(ids, exe, self.pony)
        self.collect_compiler_ids_for(ids, exe, self.ptx)
        self.collect_compiler_ids_for(ids, exe, self.python)
        self.collect_compiler_ids_for(ids, exe, self.racket)
        self.collect_compiler_ids_for(ids, exe, self.raku)
        self.collect_compiler_ids_for(ids, exe, self.razorforge)
        self.collect_compiler_ids_for(ids, exe, self.ruby)
        self.collect_compiler_ids_for(ids, exe, self.rust)
        self.collect_compiler_ids_for(ids, exe, self.sail)
        self.collect_compiler_ids_for(ids, exe, self.scala)
        self.collect_compiler_ids_for(ids, exe, self.sfpi)
        self.collect_compiler_ids_for(ids, exe, self.slang)
        self.collect_compiler_ids_for(ids, exe, self.snowball)
        self.collect_compiler_ids_for(ids, exe, self.solidity)
        self.collect_compiler_ids_for(ids, exe, self.spice)
        self.collect_compiler_ids_for(ids, exe, self.spirv)
        self.collect_compiler_ids_for(ids, exe, self.sway)
        self.collect_compiler_ids_for(ids, exe, self.swift)
        self.collect_compiler_ids_for(ids, exe, self.tablegen)
        self.collect_compiler_ids_for(ids, exe, self.triton)
        self.collect_compiler_ids_for(ids, exe, self.typescript)
        self.collect_compiler_ids_for(ids, exe, self.v)
        self.collect_compiler_ids_for(ids, exe, self.vala)
        self.collect_compiler_ids_for(ids, exe, self.vb)
        self.collect_compiler_ids_for(ids, exe, self.vyper)
        self.collect_compiler_ids_for(ids, exe, self.wasm)
        self.collect_compiler_ids_for(ids, exe, self.ylc)
        self.collect_compiler_ids_for(ids, exe, self.yul)
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
