[CmdletBinding()]
param(
    [string]$CacheDirectory = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'dev-staging.ps1')
$Session = New-DevSession 'prepare-tools'
$Success = $false
try {
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$LockPath = Join-Path $RepoRoot "tools.lock.json"
$Lock = Get-Content -LiteralPath $LockPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $CacheDirectory) {
    $CacheDirectory = Join-Path $Session.Path "downloads"
}
$CacheDirectory = [System.IO.Path]::GetFullPath($CacheDirectory)
$VendorRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "vendor\tools"))
$SourceRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "vendor\sources"))
$LicenseRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "licenses"))
New-Item -ItemType Directory -Force -Path $CacheDirectory, $VendorRoot, $SourceRoot, $LicenseRoot | Out-Null

function Get-LockedArtifact {
    param([object]$Entry, [string]$HashProperty = "sha256", [string]$UrlProperty = "url", [string]$ArchiveProperty = "archive")
    $Destination = Join-Path $CacheDirectory ([string]$Entry.$ArchiveProperty)
    $Expected = ([string]$Entry.$HashProperty).ToLowerInvariant()
    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        $Temporary = "$Destination.download"
        Write-Host "Downloading $($Entry.$UrlProperty)"
        Invoke-WebRequest -UseBasicParsing -Uri ([string]$Entry.$UrlProperty) -OutFile $Temporary
        Move-Item -LiteralPath $Temporary -Destination $Destination -Force
    }
    $Actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) {
        throw "SHA256 mismatch for $Destination`nExpected: $Expected`nActual:   $Actual"
    }
    return $Destination
}

$DenoArchive = Get-LockedArtifact $Lock.deno
$FfmpegArchive = Get-LockedArtifact $Lock.ffmpeg
$FfmpegSource = Get-LockedArtifact $Lock.ffmpeg "source_sha256" "source_url" "source_archive"

$StageRoot = Join-Path $Session.Path 'extract'
New-Item -ItemType Directory -Path $StageRoot | Out-Null
    $DenoStage = Join-Path $StageRoot "deno"
    $FfmpegStage = Join-Path $StageRoot "ffmpeg"
    Expand-Archive -LiteralPath $DenoArchive -DestinationPath $DenoStage -Force
    Expand-Archive -LiteralPath $FfmpegArchive -DestinationPath $FfmpegStage -Force
    $DenoExe = Get-ChildItem -LiteralPath $DenoStage -Filter "deno.exe" -File -Recurse | Select-Object -First 1
    $FfmpegExe = Get-ChildItem -LiteralPath $FfmpegStage -Filter "ffmpeg.exe" -File -Recurse | Select-Object -First 1
    $FfprobeExe = Get-ChildItem -LiteralPath $FfmpegStage -Filter "ffprobe.exe" -File -Recurse | Select-Object -First 1
    $FfmpegLicense = Get-ChildItem -LiteralPath $FfmpegStage -Filter "LICENSE.txt" -File -Recurse | Select-Object -First 1
    if (-not $DenoExe -or -not $FfmpegExe -or -not $FfprobeExe -or -not $FfmpegLicense) {
        throw "A locked archive does not contain the required executable or license."
    }
    $DenoTarget = Join-Path $VendorRoot "deno"
    $FfmpegTarget = Join-Path $VendorRoot "ffmpeg"
    foreach ($Target in @($DenoTarget, $FfmpegTarget)) {
        $ResolvedTarget = [System.IO.Path]::GetFullPath($Target)
        if (-not $ResolvedTarget.StartsWith($VendorRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe tool target: $ResolvedTarget"
        }
        if (Test-Path -LiteralPath $ResolvedTarget) {
            Remove-Item -LiteralPath $ResolvedTarget -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $ResolvedTarget | Out-Null
    }
    Copy-Item -LiteralPath $DenoExe.FullName -Destination (Join-Path $DenoTarget "deno.exe")
    Copy-Item -LiteralPath $FfmpegExe.FullName -Destination (Join-Path $FfmpegTarget "ffmpeg.exe")
    Copy-Item -LiteralPath $FfprobeExe.FullName -Destination (Join-Path $FfmpegTarget "ffprobe.exe")
    Copy-Item -LiteralPath $FfmpegLicense.FullName -Destination (Join-Path $LicenseRoot "FFMPEG-GPL.txt") -Force
    Copy-Item -LiteralPath $FfmpegSource -Destination (Join-Path $SourceRoot $Lock.ffmpeg.source_archive) -Force
    Copy-Item -LiteralPath $LockPath -Destination (Join-Path $VendorRoot "VERSIONS.json") -Force
& (Join-Path $VendorRoot "deno\deno.exe") --version
& (Join-Path $VendorRoot "ffmpeg\ffmpeg.exe") -version | Select-Object -First 1
Write-Host "Locked tools are ready in $VendorRoot"


$Success = $true
} finally { Close-DevSession $Session $Success }
