[CmdletBinding()]
param(
    [switch]$SkipZip,
    [switch]$ValidationOnly,
    [ValidatePattern("^[a-zA-Z0-9_-]+$")]
    [string]$ValidationName = "package-validation"
)

$ErrorActionPreference = "Stop"
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Missing .venv. Create it with Python 3.12 and install requirements-dev.txt."
}
$Required = @(
    (Join-Path $RepoRoot "vendor\tools\ffmpeg\ffmpeg.exe"),
    (Join-Path $RepoRoot "vendor\tools\ffmpeg\ffprobe.exe"),
    (Join-Path $RepoRoot "vendor\tools\deno\deno.exe"),
    (Join-Path $RepoRoot "vendor\sources\ffmpeg-source-089a48eb36.tar.gz")
)
foreach ($Path in $Required) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing locked release resource: $Path`nRun .\scripts\prepare_tools.ps1 first."
    }
}

$Version = (& $Python -c "from yt_downloader import __version__; print(__version__)").Trim()
$SourceCommit = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $SourceCommit) {
    throw "Unable to determine the source commit for BUILD-INFO.json."
}
$TrustedKeyCount = (& $Python -c "from yt_downloader.updates.trusted_keys import PRODUCTION_TRUSTED_KEYS; print(len(PRODUCTION_TRUSTED_KEYS))").Trim()
if (-not $ValidationOnly -and [int]$TrustedKeyCount -eq 0) {
    throw "Production update trust is not configured. Use -ValidationOnly until an approved production public key is embedded."
}
# Scratch builds and test data are outside the checkout and bounded per task.
. (Join-Path $PSScriptRoot 'dev-staging.ps1')
$Session = New-DevSession 'build'
$Success = $false
$PreviousPyinstallerConfig = $env:PYINSTALLER_CONFIG_DIR
try {
$env:PYINSTALLER_CONFIG_DIR = Join-Path $Session.Path 'pyinstaller-cache'
$ValidationRoot = $Session.Path
$BuildRoot = Join-Path $Session.Path 'build'
$DistRoot = Join-Path $Session.Path 'dist'
$SmokeData = Join-Path $Session.Path 'smoke-data'
$TestTemp = Join-Path $Session.Path 'pytest'
New-Item -ItemType Directory -Force -Path $TestTemp | Out-Null
if (-not $ValidationOnly) {
    & $Python (Join-Path $RepoRoot 'scripts\generate_assets.py')
    if ($LASTEXITCODE -ne 0) { throw 'Asset generation failed' }
}
$OriginalTemp = $env:TEMP
$OriginalTmp = $env:TMP
$env:TEMP = $TestTemp
$env:TMP = $TestTemp
try {
    & $Python -m pytest --basetemp (Join-Path $TestTemp "run") -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
}
finally {
    $env:TEMP = $OriginalTemp
    $env:TMP = $OriginalTmp
}

Push-Location $RepoRoot
try {
    $OriginalPath = $env:PATH
    $HostRuntimeMarker = if ($env:YT_DOWNLOADER_HOST_RUNTIME_MARKER) {
        $env:YT_DOWNLOADER_HOST_RUNTIME_MARKER
    } else {
        "[\\/].cache[\\/](host-runtimes|codex-runtimes)[\\/]"
    }
    $env:PATH = (($env:PATH -split ";") | Where-Object { $_ -and $_ -notmatch $HostRuntimeMarker }) -join ";"
    & $Python -m PyInstaller --clean --noconfirm --workpath (Join-Path $BuildRoot "app") --distpath $DistRoot "YTDownloader.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
    $UpdaterDistRoot = Join-Path $BuildRoot "updater-dist"
    & $Python -m PyInstaller --clean --noconfirm --workpath (Join-Path $BuildRoot "updater") --distpath $UpdaterDistRoot "YTDownloaderUpdater.spec"
    if ($LASTEXITCODE -ne 0) { throw "Updater PyInstaller build failed" }
}
finally {
    $env:PATH = $OriginalPath
    Pop-Location
}

$Dist = Join-Path $DistRoot "YTDownloader"
$Exe = Join-Path $Dist "YTDownloader.exe"
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { throw "Packaged executable was not created." }
$UpdaterSource = Join-Path $UpdaterDistRoot "YTDownloaderUpdater.exe"
if (-not (Test-Path -LiteralPath $UpdaterSource -PathType Leaf)) { throw "Packaged updater executable was not created." }
$HelperLayout = if ([version]$Version -ge [version]'0.5.0') { 'internal-v1' } else { 'legacy-root' }
$UpdaterRelative = if ($HelperLayout -eq 'internal-v1') { "_internal\updater\YTDownloaderUpdater.exe" } else { "YTDownloaderUpdater.exe" }
$UpdaterExe = Join-Path $Dist $UpdaterRelative
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $UpdaterExe) | Out-Null
Copy-Item -LiteralPath $UpdaterSource -Destination $UpdaterExe -Force
$ExeBytes = [System.IO.File]::ReadAllBytes($Exe)
$PeOffset = [System.BitConverter]::ToInt32($ExeBytes, 0x3c)
$Subsystem = [System.BitConverter]::ToUInt16($ExeBytes, $PeOffset + 24 + 68)
if ($Subsystem -ne 2) { throw "Packaged executable is not a Windows GUI application (subsystem=$Subsystem)." }
$UpdaterBytes = [System.IO.File]::ReadAllBytes($UpdaterExe)
$UpdaterPeOffset = [System.BitConverter]::ToInt32($UpdaterBytes, 0x3c)
$UpdaterSubsystem = [System.BitConverter]::ToUInt16($UpdaterBytes, $UpdaterPeOffset + 24 + 68)
if ($UpdaterSubsystem -ne 2) { throw "Packaged updater is not a Windows GUI application (subsystem=$UpdaterSubsystem)." }
$ThirdParty = Join-Path $Dist "third_party_licenses"
New-Item -ItemType Directory -Force -Path $ThirdParty | Out-Null
Get-ChildItem -LiteralPath (Join-Path $RepoRoot "licenses") -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $ThirdParty -Force
}
Copy-Item -LiteralPath (Join-Path $RepoRoot "THIRD_PARTY_NOTICES.md") -Destination $ThirdParty -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "assets\icons\LICENSE.txt") -Destination (Join-Path $ThirdParty "FLUENT-ICONS-MIT.txt") -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "vendor\sources\ffmpeg-source-089a48eb36.tar.gz") -Destination (Join-Path $ThirdParty "ffmpeg-source-089a48eb36.tar.gz")
& $Python (Join-Path $RepoRoot "scripts\collect_runtime_licenses.py") $ThirdParty
if ($LASTEXITCODE -ne 0) { throw "Runtime license collection failed." }

$ToolVersions = Get-Content -LiteralPath (Join-Path $RepoRoot "tools.lock.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$BuildInfo = [ordered]@{
    app_version = $Version
    source_commit = $SourceCommit
    built_at_utc = [DateTime]::UtcNow.ToString("o")
    validation_only = [bool]$ValidationOnly
    updater_protocol = if ($HelperLayout -eq 'internal-v1') { 2 } else { 1 }
    helper_layout = $HelperLayout
    updater_version = $Version
    supported_update_protocols = if ($HelperLayout -eq 'internal-v1') { @(2) } else { @(1, 2) }
    tools = $ToolVersions
}
$BuildInfo | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Dist "BUILD-INFO.json") -Encoding UTF8

$PreviousData = $env:YT_DOWNLOADER_DATA_DIR
$PreviousVideos = $env:YT_DOWNLOADER_VIDEOS_DIR
$env:YT_DOWNLOADER_DATA_DIR = $SmokeData
$env:YT_DOWNLOADER_VIDEOS_DIR = Join-Path $SmokeData "Videos"
try {
    $SelfTest = Start-Process -FilePath $Exe -ArgumentList "--self-test" -PassThru -WindowStyle Hidden
    if (-not $SelfTest.WaitForExit(60000)) {
        $SelfTest.Kill()
        throw "Packaged offline self-test timed out."
    }
    if ($SelfTest.ExitCode -ne 0) { throw "Packaged offline self-test failed with exit code $($SelfTest.ExitCode)." }
    $SelfTestReport = Join-Path $SmokeData "cache\package-self-test.json"
    if (-not (Test-Path -LiteralPath $SelfTestReport -PathType Leaf)) {
        throw "Packaged offline self-test did not create its report."
    }
    $SelfTestResult = Get-Content -LiteralPath $SelfTestReport -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($SelfTestResult.status -ne "ok" -or $SelfTestResult.app_version -ne $Version) {
        throw "Packaged offline self-test report is invalid."
    }
    $MetadataProcessTest = Start-Process -FilePath $Exe -ArgumentList "--metadata-process-self-test" -PassThru -WindowStyle Hidden
    if (-not $MetadataProcessTest.WaitForExit(60000)) {
        $MetadataProcessTest.Kill()
        throw "Packaged metadata helper process self-test timed out."
    }
    if ($MetadataProcessTest.ExitCode -ne 0) {
        throw "Packaged metadata helper process self-test failed with exit code $($MetadataProcessTest.ExitCode)."
    }
    Write-Host "MANUAL VERIFICATION REQUIRED: packaged GUI smoke test skipped by headless release policy."
}
finally {
    $env:YT_DOWNLOADER_DATA_DIR = $PreviousData
    $env:YT_DOWNLOADER_VIDEOS_DIR = $PreviousVideos
}

$Manifest = Get-ChildItem -LiteralPath $Dist -File -Recurse | Where-Object { $_.Name -ne "SHA256SUMS.json" } | ForEach-Object {
    $Hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    $RelativePath = $_.FullName.Substring($Dist.Length).TrimStart([char[]]"\/")
    $RelativePath = $RelativePath.Replace("\", "/")
    [PSCustomObject]@{ SHA256 = $Hash.Hash.ToLowerInvariant(); Path = $RelativePath }
}
$Manifest | Sort-Object Path | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Dist "SHA256SUMS.json") -Encoding UTF8
& $Python -c "import sys; from pathlib import Path; from yt_downloader.updates.archive import SafePackageExtractor; SafePackageExtractor.validate_tree(Path(sys.argv[1]), expected_version=sys.argv[2])" $Dist $Version
if ($LASTEXITCODE -ne 0) { throw "Packaged ownership validation failed." }

if ($ValidationOnly) {
    $Artifacts = Join-Path $RepoRoot "release"
    New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null
    $Zip = Join-Path $Artifacts "YTDownloader-$Version-validation-only-win64.zip"
    if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip -Force }
    if (Test-Path -LiteralPath "$Zip.sha256.txt") { Remove-Item -LiteralPath "$Zip.sha256.txt" -Force }
    Compress-Archive -LiteralPath $Dist -DestinationPath $Zip -CompressionLevel Optimal
    $ZipHash = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
    "$ZipHash *$([System.IO.Path]::GetFileName($Zip))" | Set-Content -LiteralPath "$Zip.sha256.txt" -Encoding ASCII
    Write-Host "Validation-only ZIP: $Zip"
} elseif (-not $SkipZip) {
    $Release = Join-Path $RepoRoot "release"
    New-Item -ItemType Directory -Force -Path $Release | Out-Null
    $Zip = Join-Path $Release "YTDownloader-$Version-win64.zip"
    if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip -Force }
    if (Test-Path -LiteralPath "$Zip.sha256.txt") { Remove-Item -LiteralPath "$Zip.sha256.txt" -Force }
    Compress-Archive -LiteralPath $Dist -DestinationPath $Zip -CompressionLevel Optimal
    $ZipHash = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
    "$ZipHash *$([System.IO.Path]::GetFileName($Zip))" | Set-Content -LiteralPath "$Zip.sha256.txt" -Encoding ASCII
}
if ($SkipZip -and -not $ValidationOnly) {
    # Explicitly requested non-ZIP output is a deliverable, not scratch.
    $Output = Join-Path $RepoRoot 'dist'
    if (Test-Path -LiteralPath (Join-Path $Output 'YTDownloader')) { throw 'dist/YTDownloader already exists; refusing overwrite' }
    New-Item -ItemType Directory -Force -Path $Output | Out-Null
    Move-Item -LiteralPath $Dist -Destination $Output
    Write-Host "Build ready: $Output"
} else { Write-Host "Build ready: $Zip" }
$Success = $true
} finally {
    $env:PYINSTALLER_CONFIG_DIR = $PreviousPyinstallerConfig
    Close-DevSession $Session $Success
}
