#!/usr/bin/env python3

# Ported from gen-props.ps1 to Python
import argparse

# Dictionary of compiler versions with their properties
# fmt: off
minimum_install_req = [
    {"MSVersionSemver": "14.20.27525", "MSVSVer": "2019", "MSVSShortVer": "16.0.16", "ZIPFile": "14.20.27508-14.20.27525.0"},
    {"MSVersionSemver": "14.21.27702.2", "MSVSVer": "2019", "MSVSShortVer": "16.1.0", "ZIPFile": "14.21.27702-14.21.27702.2"},
    {"MSVersionSemver": "14.22.27906", "MSVSVer": "2019", "MSVSShortVer": "16.2.1", "ZIPFile": "14.22.27905-14.22.27905.0"},
    {"MSVersionSemver": "14.23.28105.4", "MSVSVer": "2019", "MSVSShortVer": "16.3.2", "ZIPFile": "14.23.28105-14.23.28105.4"},
    {"MSVersionSemver": "14.24.28325", "MSVSVer": "2019", "MSVSShortVer": "16.4.16", "ZIPFile": "14.24.28314-14.24.28325.0"},
    {"MSVersionSemver": "14.25.28614", "MSVSVer": "2019", "MSVSShortVer": "16.5.4", "ZIPFile": "14.25.28610-14.25.28614.0"},
    {"MSVersionSemver": "14.26.28808.1", "MSVSVer": "2019", "MSVSShortVer": "16.6.3", "ZIPFile": "14.26.28801-14.26.28806.0"},
    {"MSVersionSemver": "14.27.29120", "MSVSVer": "2019", "MSVSShortVer": "16.7.28", "ZIPFile": "14.27.29110-14.27.29120.0"},
    {"MSVersionSemver": "14.28.29335", "MSVSVer": "2019", "MSVSShortVer": "16.8.3", "ZIPFile": "14.28.29333-14.28.29335.0"},
    {"MSVersionSemver": "14.28.29921", "MSVSVer": "2019", "MSVSShortVer": "16.9.16", "ZIPFile": "14.28.29910-14.28.29921.0"},
    {"MSVersionSemver": "14.29.30040-v2", "MSVSVer": "2019", "MSVSShortVer": "16.10.4", "ZIPFile": "14.29.30037-14.29.30040.0"},
    {"MSVersionSemver": "14.29.30153", "MSVSVer": "2019", "MSVSShortVer": "16.11.33", "ZIPFile": "14.29.30133-14.29.30153.0"},
    {"MSVersionSemver": "14.30.30715", "MSVSVer": "2022", "MSVSShortVer": "17.0.23", "ZIPFile": "14.30.30705-14.30.30715.0"},
    {"MSVersionSemver": "14.31.31108", "MSVSVer": "2022", "MSVSShortVer": "17.1.6", "ZIPFile": "14.31.31103-14.31.31107.0"},
    {"MSVersionSemver": "14.32.31342", "MSVSVer": "2022", "MSVSShortVer": "17.2.22", "ZIPFile": "14.32.31326-14.32.31342.0"},
    {"MSVersionSemver": "14.33.31631", "MSVSVer": "2022", "MSVSShortVer": "17.3.4", "ZIPFile": "14.33.31629-14.33.31630.0"},
    {"MSVersionSemver": "14.34.31948", "MSVSVer": "2022", "MSVSShortVer": "17.4.14", "ZIPFile": "14.34.31933-14.34.31948.0"},
    {"MSVersionSemver": "14.35.32217.1", "MSVSVer": "2022", "MSVSShortVer": "17.5.4", "ZIPFile": "14.35.32215-14.35.32217.1"},
    {"MSVersionSemver": "14.36.32544", "MSVSVer": "2022", "MSVSShortVer": "17.6.11", "ZIPFile": "14.36.32532-14.36.32544.0"},
    {"MSVersionSemver": "14.37.32826.1", "MSVSVer": "2022", "MSVSShortVer": "17.7.7", "ZIPFile": "14.37.32822-14.37.32826.1"},
    {"MSVersionSemver": "14.38.33133", "MSVSVer": "2022", "MSVSShortVer": "17.8.3", "ZIPFile": "14.38.33130-14.38.33133.0"},
    {"MSVersionSemver": "14.39.33519", "MSVSVer": "2022", "MSVSShortVer": "17.9.7", "ZIPFile": "14.39.33519-14.39.33523.0"},
    {"MSVersionSemver": "14.40.33807", "MSVSVer": "2022", "MSVSShortVer": "17.10.3", "ZIPFile": "14.40.33807-14.40.33811.0"},
    # See https://github.com/compiler-explorer/compiler-explorer/issues/7745#issuecomment-2923042678
    # this came from a previously pre-release
    # {"MSVersionSemver": "14.41.33923", "MSVSVer": "2022", "MSVSShortVer": "17.11.0", "ZIPFile": "14.41.33923-14.41.33923.0"},
    {"MSVersionSemver": "14.41.34120", "MSVSVer": "2022", "MSVSShortVer": "17.11.6", "ZIPFile": "14.41.34120-14.41.34123.0"},
    {"MSVersionSemver": "14.42.34433", "MSVSVer": "2022", "MSVSShortVer": "17.12.7", "ZIPFile": "14.42.34433-14.42.34441.0"},
  # {"MSVersionSemver": "14.43.34433", "MSVSVer": "2022", "MSVSShortVer": "17.12.13", "ZIPFile": "14.42.34433-14.42.34444.0"},
    {"MSVersionSemver": "14.43.34808", "MSVSVer": "2022", "MSVSShortVer": "17.13.6", "ZIPFile": "14.43.34808-14.43.34810.0"},
    {"MSVersionSemver": "14.44.35207", "MSVSVer": "2022", "MSVSShortVer": "17.14.19", "ZIPFile": "14.44.35207-14.44.35219.0"},
]
# fmt: on

latest = minimum_install_req[-1]

# Path constants
ROOT_DIR = "Z:/compilers/msvc"

SUB_PATH_X86_CL = "bin/Hostx64/x86/cl.exe"
SUB_PATH_X64_CL = "bin/Hostx64/x64/cl.exe"
SUB_PATH_ARM64_CL = "bin/Hostx64/arm64/cl.exe"

SDK_LIB_ROOT = "Z:/compilers/windows-kits-10/lib/10.0.22621.0"
SDK_INCLUDE_ROOT = "Z:/compilers/windows-kits-10/include/10.0.22621.0"

SDK_PATHS_X86 = ["ucrt/x86", "um/x86"]
SDK_PATHS_X64 = ["ucrt/x64", "um/x64"]
SDK_PATHS_ARM64 = ["ucrt/arm64", "um/arm64"]

LIB_SUB_PATHS_X86 = ["lib", "lib/x86", "atlmfc/lib/x86", "ifc/x86"]
LIB_SUB_PATHS_X64 = ["lib", "lib/x64", "atlmfc/lib/x64", "ifc/x64"]
LIB_SUB_PATHS_ARM64 = ["lib", "lib/arm64", "atlmfc/lib/arm64", "ifc/arm64"]

INCLUDE_SUB_PATHS = ["include"]
SDK_INCLUDE_PATHS = ["cppwinrt", "shared", "ucrt", "um", "winrt"]


def write_compiler_props(zip_file, compiler_id, compiler_semver, name_suffix):
    """
    Write compiler properties for a specific compiler version.
    """
    compiler_root = f"{ROOT_DIR}/{zip_file}"
    x86_exe = f"{compiler_root}/{SUB_PATH_X86_CL}"
    x64_exe = f"{compiler_root}/{SUB_PATH_X64_CL}"
    arm64_exe = f"{compiler_root}/{SUB_PATH_ARM64_CL}"

    # x86 compiler
    print("")
    base_prop = f"compiler.{compiler_id}_x86"

    print(f"{base_prop}.exe={x86_exe}")

    lib_path = ""
    for path in LIB_SUB_PATHS_X86:
        lib_path += f"{compiler_root}/{path};"
    for path in SDK_PATHS_X86:
        lib_path += f"{SDK_LIB_ROOT}/{path};"

    print(f"{base_prop}.libPath={lib_path}")

    include_path = ""
    for path in INCLUDE_SUB_PATHS:
        include_path += f"{compiler_root}/{path};"
    for path in SDK_INCLUDE_PATHS:
        include_path += f"{SDK_INCLUDE_ROOT}/{path};"
    print(f"{base_prop}.includePath={include_path}")
    print(f"{base_prop}.name=x86 {name_suffix}")
    print(f"{base_prop}.semver={compiler_semver}")

    # amd64 compiler
    print("")
    base_prop = f"compiler.{compiler_id}_x64"
    print(f"{base_prop}.exe={x64_exe}")

    lib_path = ""
    for path in LIB_SUB_PATHS_X64:
        lib_path += f"{compiler_root}/{path};"
    for path in SDK_PATHS_X64:
        lib_path += f"{SDK_LIB_ROOT}/{path};"

    print(f"{base_prop}.libPath={lib_path}")

    include_path = ""
    for path in INCLUDE_SUB_PATHS:
        include_path += f"{compiler_root}/{path};"
    for path in SDK_INCLUDE_PATHS:
        include_path += f"{SDK_INCLUDE_ROOT}/{path};"
    print(f"{base_prop}.includePath={include_path}")

    print(f"{base_prop}.name=x64 {name_suffix}")
    print(f"{base_prop}.semver={compiler_semver}")

    # arm64 compiler
    print("")
    base_prop = f"compiler.{compiler_id}_arm64"
    print(f"{base_prop}.exe={arm64_exe}")

    lib_path = ""
    for path in LIB_SUB_PATHS_ARM64:
        lib_path += f"{compiler_root}/{path};"
    for path in SDK_PATHS_ARM64:
        lib_path += f"{SDK_LIB_ROOT}/{path};"

    print(f"{base_prop}.libPath={lib_path}")

    include_path = ""
    for path in INCLUDE_SUB_PATHS:
        include_path += f"{compiler_root}/{path};"
    for path in SDK_INCLUDE_PATHS:
        include_path += f"{SDK_INCLUDE_ROOT}/{path};"
    print(f"{base_prop}.includePath={include_path}")

    print(f"{base_prop}.name=arm64 {name_suffix}")
    print(f"{base_prop}.semver={compiler_semver}")


def main():
    """
    Main function to process compiler versions and generate properties.
    """
    parser = argparse.ArgumentParser(description="Generate compiler properties for MSVC compilers.")
    parser.add_argument("--prefix", default="vcpp", help="Prefix to use for compiler IDs (default: vcpp)")
    args = parser.parse_args()

    prefix = args.prefix

    for version in minimum_install_req:
        semvers = version["ZIPFile"].split("-")
        assert len(semvers) == 2
        vsvernums = version["MSVSShortVer"].split(".")
        assert len(vsvernums) >= 2
        compiler_semver = semvers[1]
        compiler_vernums = compiler_semver.split(".")
        assert len(compiler_vernums) > 1
        main_ver = int(compiler_vernums[0]) + 5

        compiler_id = f"{prefix}_v{main_ver}_{compiler_vernums[1]}_VS{vsvernums[0]}_{vsvernums[1]}"

        name_suffix = f"msvc v{main_ver}.{compiler_vernums[1]} VS{vsvernums[0]}.{vsvernums[1]}"
        write_compiler_props(version["ZIPFile"], compiler_id, compiler_semver, name_suffix)

        if version == latest:
            print()
            print("#" * 40)
            print('# Latest version: may be a duplicate but this is to always have a "latest" in the drop down')
            # will break when we get a new major version, but maybe ok?
            name_suffix = f"msvc v{main_ver}.latest"
            write_compiler_props(latest["ZIPFile"], f"{prefix}_v{main_ver}_latest", compiler_semver, name_suffix)
            print("#" * 40)


if __name__ == "__main__":
    main()
