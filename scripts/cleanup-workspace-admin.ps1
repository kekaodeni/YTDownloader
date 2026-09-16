#Requires -RunAsAdministrator
[CmdletBinding(SupportsShouldProcess=$true)]
param()
$ErrorActionPreference = 'Stop'
$Repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$Target = [IO.Path]::GetFullPath((Join-Path $Repo '.tool-stage'))
if ([string]::IsNullOrWhiteSpace($Target) -or $Target -cne (Join-Path $Repo '.tool-stage') -or $Target -eq $Repo) {
    throw 'Refusing cleanup outside the exact audited .tool-stage directory.'
}
$Forbidden = @($Repo, '.git', 'src', 'tests', 'docs', 'scripts', 'vendor') | ForEach-Object {
    if ($_ -eq $Repo) { $Repo } else { Join-Path $Repo $_ }
}
if ($Forbidden -contains $Target) { throw 'Refusing a protected project path.' }
if (-not (Test-Path -LiteralPath $Target)) { Write-Output 'Nothing to clean.'; exit 0 }
# Never traverse a junction/symlink into a protected directory.
function Assert-NoLinks([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point refused: $Path" }
    if ($item.PSIsContainer) {
        foreach ($child in Get-ChildItem -LiteralPath $Path -Force) { Assert-NoLinks $child.FullName }
    }
}
Assert-NoLinks $Target
if (-not $PSCmdlet.ShouldProcess($Target, 'Permanently remove audited temporary staging')) { return }
$BeforeFree = ([IO.DriveInfo]::new('D:\')).AvailableFreeSpace
$BeforeBytes = (Get-ChildItem -LiteralPath $Target -File -Recurse -Force | Measure-Object Length -Sum).Sum
& takeown.exe /F $Target /A /R /D Y
if ($LASTEXITCODE -ne 0) { throw 'takeown failed' }
$Sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $Target /grant:r "*$($Sid):(OI)(CI)F" /T /Q
if ($LASTEXITCODE -ne 0) { throw 'icacls failed' }
Assert-NoLinks $Target
Remove-Item -LiteralPath $Target -Recurse -Force
if (Test-Path -LiteralPath $Target) { throw 'Staging still exists' }
$AfterFree = ([IO.DriveInfo]::new('D:\')).AvailableFreeSpace
Write-Output "Deleted file bytes: $BeforeBytes"
Write-Output "D: available-space increase: $($AfterFree-$BeforeFree) bytes"
Write-Output 'STAGING CLEANUP = PASS'
