$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Create the project .venv and install development requirements first.'
}
Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller --noconfirm --distpath (Join-Path $ProjectRoot 'build/browser-bridge') --workpath (Join-Path $ProjectRoot 'build/browser-bridge-work') (Join-Path $ProjectRoot 'YTDownloaderBridge.spec')
    if ($LASTEXITCODE -ne 0) { throw 'Browser Bridge build failed.' }
    & $Python (Join-Path $ProjectRoot 'scripts/bundle_browser_extensions.py') --resources (Join-Path $ProjectRoot 'browser-extension') --package (Join-Path $ProjectRoot 'build/browser-bridge')
    if ($LASTEXITCODE -ne 0) { throw 'Browser extension asset build failed.' }
    Write-Host 'Bridge built. Return to Toolbox > Browser extension > Configure connection.'
} finally { Pop-Location }
