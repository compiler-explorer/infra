
# 14.20.27525         16.0.16
# 14.21.27702.2       16.1.0
# 14.22.27906         16.2.1
# 14.23.28105.4       16.3.2
# 14.24.28325         16.4.16
# 14.25.28614         16.5.4
# 14.26.28808.1       16.6.3
# 14.27.29120         16.7.28
# 14.28.29335         16.8.3
# 14.28.29921         16.9.16
# 14.29.30040-v2      16.10.4
# 14.29.30153         16.11.33

# 14.30.30715         17.0.23
# 14.31.31108         17.1.6
# 14.33.31631         17.3.4
# 14.35.32217.1
# 14.37.32826.1
# 14.32.31342         17.2.22*
# 14.34.31948         17.4.14*
# 14.36.32544         17.6.11*
# 14.38.33133         17.8.3*
# 14.39.33321-Pre

$minimumInstallReq = (
    (New-Object PSObject -Property @{ MSVersionSemver="14.14.26428.1"; MSVSVer=""; MSVSShortVer=""; ZIPFile=""; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.15.26726"; MSVSVer=""; MSVSShortVer=""; ZIPFile=""; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.16.27051"; MSVSVer=""; MSVSShortVer=""; ZIPFile=""; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.20.27525"; MSVSVer="2019"; MSVSShortVer="16.0.16"; ZIPFile="14.20.27508-14.20.27525.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.21.27702.2"; MSVSVer="2019"; MSVSShortVer="16.1.0"; ZIPFile="14.21.27702-14.21.27702.2"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.22.27906"; MSVSVer="2019"; MSVSShortVer="16.2.1"; ZIPFile="14.22.27905-14.22.27905.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.23.28105.4"; MSVSVer="2019"; MSVSShortVer="16.3.2"; ZIPFile="14.23.28105-14.23.28105.4"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.24.28325"; MSVSVer="2019"; MSVSShortVer="16.4.16"; ZIPFile="14.24.28314-14.24.28325.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.25.28614"; MSVSVer="2019"; MSVSShortVer="16.5.4"; ZIPFile="14.25.28610-14.25.28614.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.26.28808.1"; MSVSVer="2019"; MSVSShortVer="16.6.3"; ZIPFile="14.26.28801-14.26.28806.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.27.29120"; MSVSVer="2019"; MSVSShortVer="16.7.28"; ZIPFile="14.27.29110-14.27.29120.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.28.29335"; MSVSVer="2019"; MSVSShortVer="16.8.3"; ZIPFile="14.28.29333-14.28.29335.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.28.29921"; MSVSVer="2019"; MSVSShortVer="16.9.16"; ZIPFile="14.28.29910-14.28.29921.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.29.30040-v2"; MSVSVer="2019"; MSVSShortVer="16.10.4"; ZIPFile="14.29.30037-14.29.30040.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.29.30153"; MSVSVer="2019"; MSVSShortVer="16.11.33"; ZIPFile="14.29.30133-14.29.30153.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.30.30715"; MSVSVer="2022"; MSVSShortVer="17.0.23"; ZIPFile="14.30.30705-14.30.30715.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.31.31108"; MSVSVer="2022"; MSVSShortVer="17.1.6"; ZIPFile="14.31.31103-14.31.31107.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.32.31342"; MSVSVer="2022"; MSVSShortVer="17.2.22"; ZIPFile="14.32.31326-14.32.31342.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.33.31631"; MSVSVer="2022"; MSVSShortVer="17.3.4"; ZIPFile="14.33.31629-14.33.31630.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.34.31948"; MSVSVer="2022"; MSVSShortVer="17.4.14"; ZIPFile="14.34.31933-14.34.31948.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.35.32217.1"; MSVSVer="2022"; MSVSShortVer="17.5.4"; ZIPFile="14.35.32215-14.35.32217.1"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.36.32544"; MSVSVer="2022"; MSVSShortVer="17.6.11"; ZIPFile="14.36.32532-14.36.32544.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.37.32826.1"; MSVSVer="2022"; MSVSShortVer="17.7.7"; ZIPFile="14.37.32822-14.37.32826.1"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.38.33133"; MSVSVer="2022"; MSVSShortVer="17.8.3"; ZIPFile="14.38.33130-14.38.33133.0"; }),
    # (New-Object PSObject -Property @{ MSVersionSemver="14.39.33321-Pre"; MSVSVer=""; MSVSShortVer=""; ZIPFile=""; })
    (New-Object PSObject -Property @{ MSVersionSemver="14.39.33519"; MSVSVer="2022"; MSVSShortVer="17.9.7"; ZIPFile="14.39.33519-14.39.33523.0"; }),
    (New-Object PSObject -Property @{ MSVersionSemver="14.40.33807"; MSVSVer="2022"; MSVSShortVer="17.10.3"; ZIPFile="14.40.33807-14.40.33811.0"; })
    # Matt added this without really understanding, it's as of 2024/07/01 the "latest"
    # I found the "MSVSShortVer" numbers by looking in the installer manually. I hope there's an easier way to work this out.
    # I commented it out as this script will give it the wrong name, but it's useful to generate the basics.
    #(New-Object PSObject -Property @{ MSVersionSemver="14.41.33923"; MSVSVer="2022"; MSVSShortVer="17.11.0"; ZIPFile="14.41.33923-14.41.33923.0"; })

)

$RootDir = "Z:/compilers/msvc"

$subPathX86CL = "bin/Hostx64/x86/cl.exe"
$subPathX64CL = "bin/Hostx64/x64/cl.exe"
$subPathArm64CL = "bin/Hostx64/arm64/cl.exe"

$sdkLibRoot = "Z:/compilers/windows-kits-10/lib/10.0.22621.0"
$sdkIncludeRoot = "Z:/compilers/windows-kits-10/include/10.0.22621.0"

$sdkPathsX86 = ("ucrt/x86", "um/x86")
$sdkPathsX64 = ("ucrt/x64", "um/x64")
$sdkPathsArm64 = ("ucrt/arm64", "um/arm64")

$libSubPathsX86 = ("lib", "lib/x86", "atlmfc/lib/x86", "ifc/x86")
$libSubPathsX64 = ("lib", "lib/x64", "atlmfc/lib/x64", "ifc/x64")
$libSubPathsArm64 = ("lib", "lib/arm64", "atlmfc/lib/arm64", "ifc/arm64")

$includeSubPaths = ("include")
$sdkIncludePaths = ("cppwinrt", "shared", "ucrt", "um", "winrt")

function WriteCompilerProps {
    Param(
        [string] $ZIPFile,
        [string] $CompilerID,
        [string] $CompilerSemver,
        [string] $NameSuffix
    )

    $compilerRoot = "$RootDir/$ZIPFile"
    $x86exe = "$compilerRoot/$subPathX86CL"
    $x64exe = "$compilerRoot/$subPathX64CL"
    $arm64exe = "$compilerRoot/$subPathArm64CL"

    # x86 compiler
    Write-Output ""
    $baseProp = "compiler." + $CompilerID + "_x86"

    Write-Output "$baseProp.exe=$x86exe"

    $libPath = ""
    foreach ($path in $libSubPathsX86) {
        $libPath = $libPath + "$compilerRoot/$path" + ";"
    }
    foreach ($path in $sdkPathsX86) {
        $libPath = $libPath + "$sdkLibRoot/$path" + ";"
    }

    Write-Output "$baseProp.libPath=$libPath"

    $includePath = ""
    foreach ($path in $includeSubPaths) {
        $includePath = $includePath + "$compilerRoot/$path" + ";"
    }
    foreach ($path in $sdkIncludePaths) {
        $includePath = $includePath + "$sdkIncludeRoot/$path" + ";"
    }
    Write-Output "$baseProp.includePath=$includePath"
    Write-Output "$baseProp.name=x86 $NameSuffix"
    Write-Output "$baseProp.semver=$CompilerSemver"

    # amd64 compiler
    Write-Output ""

    $baseProp = "compiler." + $CompilerID + "_x64"
    Write-Output "$baseProp.exe=$x64exe"

    $libPath = ""
    foreach ($path in $libSubPathsX64) {
        $libPath = $libPath + "$compilerRoot/$path" + ";"
    }
    foreach ($path in $sdkPathsX64) {
        $libPath = $libPath + "$sdkLibRoot/$path" + ";"
    }

    Write-Output "$baseProp.libPath=$libPath"

    $includePath = ""
    foreach ($path in $includeSubPaths) {
        $includePath = $includePath + "$compilerRoot/$path" + ";"
    }
    foreach ($path in $sdkIncludePaths) {
        $includePath = $includePath + "$sdkIncludeRoot/$path" + ";"
    }
    Write-Output "$baseProp.includePath=$includePath"

    Write-Output "$baseProp.name=x64 $NameSuffix"
    Write-Output "$baseProp.semver=$CompilerSemver"

    # arm64 compiler
    Write-Output ""

    $baseProp = "compiler." + $CompilerID + "_arm64"
    Write-Output "$baseProp.exe=$arm64exe"

    $libPath = ""
    foreach ($path in $libSubPathsArm64) {
        $libPath = $libPath + "$compilerRoot/$path" + ";"
    }
    foreach ($path in $sdkPathsArm64) {
        $libPath = $libPath + "$sdkLibRoot/$path" + ";"
    }

    Write-Output "$baseProp.libPath=$libPath"

    $includePath = ""
    foreach ($path in $includeSubPaths) {
        $includePath = $includePath + "$compilerRoot/$path" + ";"
    }
    foreach ($path in $sdkIncludePaths) {
        $includePath = $includePath + "$sdkIncludeRoot/$path" + ";"
    }
    Write-Output "$baseProp.includePath=$includePath"

    Write-Output "$baseProp.name=arm64 $NameSuffix"
    Write-Output "$baseProp.semver=$CompilerSemver"
}


foreach ($version in $minimumInstallReq) {
    if ($version.ZIPFile -ne "") {
        $semvers = $version.ZIPFile.Split("-")
        $vsvernums = $version.MSVSShortVer.Split(".")
        $compilerSemver = $semvers[1]
        $compilerVernums = $compilerSemver.Split(".")
        $mainVer = [int]$compilerVernums[0]
        $mainVer = $mainVer + 5

        $nameSuffix = "msvc v" + $mainVer + "." + $compilerVernums[1] + " VS" + $vsvernums[0] + "." + $vsvernums[1]
        $compilerID = "vcpp_v" + $mainVer + "_" + $compilerVernums[1] + "_VS" + $vsvernums[0] + "_" + $vsvernums[1]
        WriteCompilerProps -ZIPFile $version.ZIPFile -CompilerID $compilerID -CompilerSemver $compilerSemver -NameSuffix $nameSuffix
    }
}
