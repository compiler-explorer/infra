# Downloads Windows SDK offline layouts and extracts fxc.exe / d3dcompiler_47.dll
# for each requested SDK version into an output folder named after the SDK
# version (e.g. fxc/10.0.22621.755/<arch>/).
#
# winsdksetup.exe /installpath refuses to run when another Windows SDK is
# already present on the host (it forces a merged install into the existing
# location). msiexec /a (administrative install) silently triggers UAC even
# with /qn, which hangs the script behind a hidden consent dialog. To avoid
# both we:
#   1. winsdksetup.exe /layout <dir>   -- download the offline payload only,
#      no install, no elevation needed.
#   2. Read the layout's Installers\*.msi via the WindowsInstaller COM API
#      (read-only, no elevation) to learn which external .cab each file is in.
#   3. expand.exe extracts those specific cab members into a staging dir.
#   4. The extracted PE files self-identify their architecture (PE Machine
#      field) and SDK version (FileVersionInfo), so we place them under
#      fxc/<sdk-version>/<arch>/ without parsing the MSI Directory table.
#
# Add new versions to the $versions table below as Microsoft releases them.
# The official downloads page (with current installer fwlinks) is
# https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/.

# FXC has been largely unmaintained for a while, so we only pull a few SDKs
# from major versions of Windows.
# 10.0.19041 - Windows 10 20H1 and 20H2.
# 10.0.26100 - Windows 11 24H2 and 23H2.
#
# The 8.1 SDK (the last to support Windows 7) is gone: its winsdksetup.exe
# /layout fails in Apply because the standalone SDK MSI payloads 404 on
# Microsoft's CDN, so there is no way to acquire fxc.exe from it anymore.

$versions = (
    (New-Object PSObject -Property @{ Label = "10.0.19041"; Url = "https://go.microsoft.com/fwlink/?linkid=2311805" }),
    (New-Object PSObject -Property @{ Label = "10.0.26100"; Url = "https://go.microsoft.com/fwlink/?linkid=2361308" })
)

# This script is destructive to $Env:TEMP and is designed to run on a GH action
# runner; the package-fxc.yaml workflow invokes it and the AWS credentials in
# the environment let Write-S3Object upload the resulting archives.
$download_path = "$Env:TEMP/download/winsdk"
$layout_root   = "$Env:TEMP/layout/winsdk"
$extract_root  = "$Env:TEMP/extract/winsdk"
$output_root   = "$Env:TEMP/fxc"
$archives      = "$Env:TEMP/archives"
$architectures = @("x64", "x86", "arm64")

function To-Native {
    Param ([string] $p)
    return ($p -replace '/', '\')
}

function Download {
    Param (
        [string] $label,
        [string] $url
    )

    $versionPath = "$download_path/$label"
    $filepath = "$versionPath/winsdksetup.exe"

    if (!(Test-Path -Path $filepath)) {
        New-Item -ItemType Directory -Force $versionPath | Out-Null
        Write-Host "Downloading Windows SDK $label from $url"
        Invoke-WebRequest -Uri $url -OutFile $filepath
    }
    return $filepath
}

function Get-Layout {
    Param (
        [string] $label
    )

    $installer = "$download_path/$label/winsdksetup.exe"
    $layoutPath = (New-Item -ItemType Directory -Force "$layout_root/$label").FullName
    $logPath = Join-Path $layoutPath "layout.log"

    # If the layout directory already has Installers\*.msi assume it's good.
    $installersDir = Join-Path $layoutPath "Installers"
    if (Test-Path $installersDir) {
        $existing = Get-ChildItem $installersDir -Filter *.msi -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "Reusing cached layout at $layoutPath"
            return $layoutPath
        }
    }

    $args = @(
        "/quiet",
        "/norestart",
        "/ceip", "off",
        "/layout", (To-Native $layoutPath),
        "/log", (To-Native $logPath),
        "/features", "+"
    )

    Write-Host "Downloading SDK $label layout to $layoutPath"
    $proc = Start-Process -Wait -PassThru -FilePath $installer -ArgumentList $args
    if ($proc.ExitCode -ne 0) {
        if (Test-Path $logPath) {
            # winsdksetup dumps its entire variable table near the end, which
            # buries the real failure under ~100 lines. Print the whole log
            # minus that noise so the Acquire/Apply error is visible.
            Write-Host "--- layout.log ---"
            Get-Content $logPath |
                Where-Object { $_ -notmatch '(?i): Variable: ' } |
                ForEach-Object { Write-Host $_ }
            Write-Host "--- end layout.log ---"
        }
        throw "winsdksetup.exe /layout for $label exited with code $($proc.ExitCode). Full log: $logPath"
    }
    return $layoutPath
}

function Get-MsiCabMap {
    # Returns array of [PSCustomObject]@{ LastSequence; Cabinet } sorted ascending.
    Param ($Db)
    $view = $Db.GetType().InvokeMember('OpenView', 'InvokeMethod', $null, $Db,
        @("SELECT LastSequence, Cabinet FROM Media ORDER BY LastSequence"))
    $view.GetType().InvokeMember('Execute', 'InvokeMethod', $null, $view, $null) | Out-Null
    $list = @()
    while ($true) {
        $rec = $view.GetType().InvokeMember('Fetch', 'InvokeMethod', $null, $view, $null)
        if ($null -eq $rec) { break }
        $list += [PSCustomObject]@{
            LastSequence = $rec.GetType().InvokeMember('IntegerData', 'GetProperty', $null, $rec, @(1))
            Cabinet      = $rec.GetType().InvokeMember('StringData',  'GetProperty', $null, $rec, @(2))
        }
    }
    $view.GetType().InvokeMember('Close', 'InvokeMethod', $null, $view, $null) | Out-Null
    return $list
}

function Get-MsiFileMatches {
    # Returns array of [PSCustomObject]@{ Key; LongName; Sequence; Cabinet }
    # for File rows whose long filename matches one of $Names.
    Param ($Db, [string[]] $Names, $CabMap)
    $view = $Db.GetType().InvokeMember('OpenView', 'InvokeMethod', $null, $Db,
        @("SELECT File, FileName, Sequence FROM File"))
    $view.GetType().InvokeMember('Execute', 'InvokeMethod', $null, $view, $null) | Out-Null
    $list = @()
    while ($true) {
        $rec = $view.GetType().InvokeMember('Fetch', 'InvokeMethod', $null, $view, $null)
        if ($null -eq $rec) { break }
        $key  = $rec.GetType().InvokeMember('StringData',  'GetProperty', $null, $rec, @(1))
        $name = $rec.GetType().InvokeMember('StringData',  'GetProperty', $null, $rec, @(2))
        $seq  = $rec.GetType().InvokeMember('IntegerData', 'GetProperty', $null, $rec, @(3))
        $long = if ($name -match '\|') { ($name -split '\|', 2)[1] } else { $name }
        if ($Names -notcontains $long) { continue }
        $cab = ($CabMap | Where-Object { $_.LastSequence -ge $seq } | Select-Object -First 1).Cabinet
        if (-not $cab) { continue }
        $list += [PSCustomObject]@{
            Key      = $key
            LongName = $long
            Sequence = $seq
            Cabinet  = $cab
        }
    }
    $view.GetType().InvokeMember('Close', 'InvokeMethod', $null, $view, $null) | Out-Null
    return $list
}

function Extract-FilesFromMsi {
    # Reads $MsiPath via WindowsInstaller COM (no elevation) and uses
    # expand.exe to pull every File row whose long filename is in $Names out
    # of the appropriate external cab (located next to $MsiPath). Returns
    # the full paths of the extracted (and renamed) files.
    Param (
        [string]   $MsiPath,
        [string[]] $Names,
        [string]   $TargetDir
    )

    New-Item -ItemType Directory -Force $TargetDir | Out-Null
    $cabDir = Split-Path -Parent $MsiPath

    $installer = New-Object -ComObject WindowsInstaller.Installer
    try {
        $db = $installer.GetType().InvokeMember(
            'OpenDatabase', 'InvokeMethod', $null, $installer, @($MsiPath, 0))
        $cabMap  = Get-MsiCabMap -Db $db
        $matches = Get-MsiFileMatches -Db $db -Names $Names -CabMap $cabMap
    } finally {
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($installer) | Out-Null
    }

    if (-not $matches) {
        throw "No File rows matching $($Names -join ', ') found in $MsiPath"
    }

    $extracted = @()
    $byCab = $matches | Group-Object Cabinet
    foreach ($group in $byCab) {
        $cabName = $group.Name
        # External cabs sit next to the MSI; embedded cabs start with '#'.
        # The SDK Tools MSIs use external cabs, but guard just in case.
        if ($cabName.StartsWith('#')) {
            throw "MSI $MsiPath uses embedded cab $cabName; embedded extraction is not implemented."
        }
        $cabPath = Join-Path $cabDir $cabName
        if (!(Test-Path $cabPath)) {
            throw "Cab $cabPath referenced by $MsiPath is missing from the layout."
        }
        foreach ($m in $group.Group) {
            # expand.exe stores the cab member under its File-key (e.g.
            # "fil483fc95478d089ca653c1e8394cae57b"); we rename to long name.
            $expandArgs = @(
                (To-Native $cabPath),
                "-F:$($m.Key)",
                (To-Native $TargetDir)
            )
            $proc = Start-Process -Wait -PassThru -FilePath "expand.exe" `
                -ArgumentList $expandArgs -NoNewWindow `
                -RedirectStandardOutput ([System.IO.Path]::GetTempFileName())
            if ($proc.ExitCode -ne 0) {
                throw "expand.exe failed (exit $($proc.ExitCode)) extracting $($m.Key) from $cabPath"
            }
            $rawPath = Join-Path $TargetDir $m.Key
            if (!(Test-Path $rawPath)) {
                throw "expand.exe did not produce $rawPath"
            }
            # Multiple File rows may share a long filename (e.g. one
            # d3dcompiler_47.dll per arch); disambiguate with the File key.
            $finalPath = Join-Path $TargetDir "$($m.Key)__$($m.LongName)"
            Move-Item -Force $rawPath $finalPath
            $extracted += $finalPath
        }
    }
    return $extracted
}

function Get-PEArchitecture {
    Param ([string] $Path)
    $fs = [System.IO.File]::OpenRead($Path)
    try {
        $br = New-Object System.IO.BinaryReader($fs)
        $fs.Position = 0x3c
        $peOffset = $br.ReadInt32()
        $fs.Position = $peOffset
        $sig = $br.ReadUInt32()  # 'PE\0\0'
        if ($sig -ne 0x00004550) {
            throw "Not a PE file: $Path"
        }
        $machine = $br.ReadUInt16()
    } finally {
        $fs.Dispose()
    }
    switch ($machine) {
        0x014c  { return 'x86' }
        0x8664  { return 'x64' }
        0xAA64  { return 'arm64' }
        0x01c4  { return 'arm' }
        default { throw ("Unknown PE Machine 0x{0:X4} in {1}" -f $machine, $Path) }
    }
}

function Get-MsisContainingFiles {
    # Returns the MSIs under $InstallersDir whose File table contains at
    # least one row whose long filename matches any of $Names. This lets us
    # cope with the fact that the MSI carrying fxc.exe is named differently
    # across SDK generations:
    #   * 8.1:   "Windows Software Development Kit for Windows Store Apps-x86_en-us.msi"
    #   * 10+:   "Windows SDK for Windows Store Apps Tools-x86_en-us.msi"
    Param ([string] $InstallersDir, [string[]] $Names)

    $installer = New-Object -ComObject WindowsInstaller.Installer
    try {
        $hits = @()
        foreach ($msi in Get-ChildItem $InstallersDir -Filter '*.msi') {
            $db = $null
            try {
                $db = $installer.GetType().InvokeMember(
                    'OpenDatabase', 'InvokeMethod', $null, $installer, @($msi.FullName, 0))
            } catch { continue }
            $view = $db.GetType().InvokeMember(
                'OpenView', 'InvokeMethod', $null, $db, @("SELECT FileName FROM File"))
            $view.GetType().InvokeMember('Execute', 'InvokeMethod', $null, $view, $null) | Out-Null
            $hit = $false
            while ($true) {
                $rec = $view.GetType().InvokeMember('Fetch', 'InvokeMethod', $null, $view, $null)
                if ($null -eq $rec) { break }
                $name = $rec.GetType().InvokeMember('StringData', 'GetProperty', $null, $rec, @(1))
                $long = if ($name -match '\|') { ($name -split '\|', 2)[1] } else { $name }
                if ($Names -contains $long) { $hit = $true; break }
            }
            $view.GetType().InvokeMember('Close', 'InvokeMethod', $null, $view, $null) | Out-Null
            if ($hit) { $hits += $msi.FullName }
        }
        return $hits
    } finally {
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($installer) | Out-Null
    }
}

function Extract-FxcFromLayout {
    Param (
        [string] $label,
        [string] $layoutPath
    )

    $installersDir = Join-Path $layoutPath "Installers"
    if (!(Test-Path $installersDir)) {
        throw "No Installers directory in layout: $installersDir"
    }

    $wanted = @('fxc.exe', 'd3dcompiler_47.dll')

    # Different SDK generations ship fxc.exe in differently-named MSIs (and
    # the 8.1 SDK additionally duplicates them across a couple of Cert Kit
    # MSIs). Scan every MSI in the layout and extract from any that carry a
    # wanted file. The PE-header arch check downstream dedupes copies.
    $candidateMsis = Get-MsisContainingFiles -InstallersDir $installersDir -Names $wanted
    if (-not $candidateMsis) {
        throw "No MSI under $installersDir contains $($wanted -join ' or ')"
    }

    $extractDir = (New-Item -ItemType Directory -Force "$extract_root/$label").FullName
    # Wipe stale extractions so disambiguation doesn't pick up old keys.
    Get-ChildItem $extractDir -ErrorAction SilentlyContinue | Remove-Item -Force -Recurse

    $files = @()
    foreach ($msiPath in $candidateMsis) {
        Write-Host "  extracting from $(Split-Path -Leaf $msiPath)"
        $files += Extract-FilesFromMsi -MsiPath $msiPath -Names $wanted -TargetDir $extractDir
    }

    # Use the caller-supplied label as the output directory name. SDK
    # binaries' FileVersionInfo doesn't track the SDK Kit Version (e.g. 8.1
    # SDK fxc.exe reports 6.3.9600.x, and 10.x SDKs report a build that
    # doesn't match the canonical "10.0.NNNNN" path users expect), so the
    # label is the most reliable identifier.
    Write-Host "Laying out under $output_root/$label"

    foreach ($arch in $architectures) {
        $dstDir = "$output_root/$label/$arch"
        $placed = @{}
        foreach ($f in $files) {
            $leaf = Split-Path -Leaf $f
            $longName = ($leaf -split '__', 2)[1]
            if ($wanted -notcontains $longName) { continue }
            try { $fileArch = Get-PEArchitecture $f } catch { continue }
            if ($fileArch -ne $arch) { continue }
            if ($placed.ContainsKey($longName)) { continue }
            if (-not (Test-Path $dstDir)) {
                New-Item -ItemType Directory -Force $dstDir | Out-Null
            }
            Copy-Item -Force $f (Join-Path $dstDir $longName)
            Write-Host "  ($arch) copied $longName"
            $placed[$longName] = $true
        }
        foreach ($needed in @('fxc.exe', 'd3dcompiler_47.dll')) {
            if (-not $placed.ContainsKey($needed)) {
                Write-Host "  ($arch) MISSING $needed (not present in MSI for this arch)"
            }
        }
    }

    # Tidy: drop the extracted staging dir to keep disk usage down.
    Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue
}

function Zip-Fxc {
    Param (
        [string] $label
    )

    New-Item -ItemType Directory -Force $archives | Out-Null

    $labelDir = "$output_root/$label"
    if (!(Test-Path $labelDir)) {
        Write-Host "  no output directory to archive at $labelDir"
        return
    }

    $zipPath = "$archives/fxc-$label.zip"
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    Write-Host "  archiving $labelDir -> $zipPath"
    Compress-Archive -DestinationPath $zipPath -Path $labelDir

    $key = "opt-nonfree/fxc/fxc-$label.zip"
    Write-Host "  uploading $zipPath -> s3://compiler-explorer/$key"
    Write-S3Object -BucketName compiler-explorer -Key $key -File $zipPath
    Write-Host "  uploaded fxc-$label !"
}

New-Item -ItemType Directory -Force $download_path | Out-Null
New-Item -ItemType Directory -Force $layout_root   | Out-Null
New-Item -ItemType Directory -Force $extract_root  | Out-Null
New-Item -ItemType Directory -Force $output_root   | Out-Null
New-Item -ItemType Directory -Force $archives      | Out-Null

$failures = @()
foreach ($version in $versions) {
    $label = $version.Label
    Write-Host ""
    Write-Host "=== Windows SDK $label ==="

    try {
        Download   -label $label -url $version.Url | Out-Null
        $layoutPath = Get-Layout -label $label
        Extract-FxcFromLayout -label $label -layoutPath $layoutPath
        Zip-Fxc -label $label
    } catch {
        Write-Host "ERROR packaging SDK ${label}: $($_.Exception.Message)"
        $failures += $label
    }
}

Write-Host ""
Write-Host "fxc.exe / d3dcompiler_47.dll extracted under $output_root"
Write-Host "archives written to $archives"

if ($failures) {
    Write-Host ""
    Write-Host "Failed SDK versions: $($failures -join ', ')"
    exit 1
}
