[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv (Join-Path $Repo '.venv')
    } else {
        & python -c "import sys; assert sys.version_info[:2] == (3, 12), 'Python 3.12 is required'"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required' }
        & python -m venv (Join-Path $Repo '.venv')
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 environment creation failed' }
}
& $Python -m pip install -r (Join-Path $Repo 'requirements-dev-snapshot.txt') -r (Join-Path $Repo 'requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $Python -m pip install --no-deps --no-build-isolation -e $Repo
if ($LASTEXITCODE -ne 0) { throw 'Editable project installation failed' }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed' }
Write-Output 'Development environment restored.'
