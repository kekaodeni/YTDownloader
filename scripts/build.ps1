[CmdletBinding()]
param(
    [switch]$SkipZip
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

& $Python (Join-Path $RepoRoot "scripts\generate_assets.py")
& $Python -m pytest
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

foreach ($Name in @("build", "dist", "release")) {
    $Target = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Name))
    if (-not $Target.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe build target: $Target"
    }
    if (Test-Path -LiteralPath $Target) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

Push-Location $RepoRoot
try {
    $OriginalPath = $env:PATH
    $env:PATH = (($env:PATH -split ";") | Where-Object { $_ -and $_ -notmatch "\\.cache\\codex-runtimes\\" }) -join ";"
    & $Python -m PyInstaller --clean --noconfirm "YTDownloader.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
}
finally {
    $env:PATH = $OriginalPath
    Pop-Location
}

$Dist = Join-Path $RepoRoot "dist\YTDownloader"
$Exe = Join-Path $Dist "YTDownloader.exe"
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { throw "Packaged executable was not created." }
$ThirdParty = Join-Path $Dist "third_party_licenses"
New-Item -ItemType Directory -Force -Path $ThirdParty | Out-Null
Get-ChildItem -LiteralPath (Join-Path $RepoRoot "licenses") -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $ThirdParty -Force
}
Copy-Item -LiteralPath (Join-Path $RepoRoot "THIRD_PARTY_NOTICES.md") -Destination $ThirdParty -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "assets\icons\LICENSE.txt") -Destination (Join-Path $ThirdParty "FLUENT-ICONS-MIT.txt") -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "vendor\sources\ffmpeg-source-089a48eb36.tar.gz") -Destination (Join-Path $ThirdParty "ffmpeg-source-089a48eb36.tar.gz")

$SmokeData = Join-Path $RepoRoot ".package-smoke-data"
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
    $Process = Start-Process -FilePath $Exe -ArgumentList "--smoke-test" -PassThru -WindowStyle Hidden
    if (-not $Process.WaitForExit(15000)) {
        $Process.Kill()
        throw "Packaged GUI smoke test timed out."
    }
    if ($Process.ExitCode -ne 0) { throw "Packaged GUI smoke test failed with exit code $($Process.ExitCode)." }
}
finally {
    $env:YT_DOWNLOADER_DATA_DIR = $PreviousData
    $env:YT_DOWNLOADER_VIDEOS_DIR = $PreviousVideos
}

$Manifest = Get-ChildItem -LiteralPath $Dist -File -Recurse | ForEach-Object {
    $Hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    [PSCustomObject]@{ SHA256 = $Hash.Hash.ToLowerInvariant(); Path = [System.IO.Path]::GetRelativePath($Dist, $_.FullName) }
}
$Manifest | Sort-Object Path | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Dist "SHA256SUMS.json") -Encoding UTF8

$Release = Join-Path $RepoRoot "release"
New-Item -ItemType Directory -Force -Path $Release | Out-Null
if (-not $SkipZip) {
    $Zip = Join-Path $Release "YTDownloader-0.1.0-win64.zip"
    Compress-Archive -LiteralPath $Dist -DestinationPath $Zip -CompressionLevel Optimal
    Get-FileHash -LiteralPath $Zip -Algorithm SHA256 | Format-List | Out-File -LiteralPath "$Zip.sha256.txt" -Encoding UTF8
}
Write-Host "Build ready: $Exe"
