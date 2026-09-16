function New-DevSession([string]$Kind) {
    if ($Kind -notmatch '^[a-z0-9-]+$') { throw 'Invalid session kind' }
    $Root = Join-Path ([IO.Path]::GetTempPath()) "YTDownloader\dev-staging\$Kind"
    $Checkout = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\') + '\'
    if ([IO.Path]::GetFullPath($Root).StartsWith($Checkout, [StringComparison]::OrdinalIgnoreCase)) { throw 'TEMP must be outside the checkout' }
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    $LockPath = Join-Path $Root '.active'
    $Lock = [IO.File]::Open($LockPath, 'CreateNew', 'ReadWrite', 'None')
    try {
        foreach ($Old in Get-ChildItem -LiteralPath $Root -Directory -Filter 'session-*') {
            if ($Old.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked scratch directory refused' }
            Remove-Item -LiteralPath $Old.FullName -Recurse -Force
        }
        $Work = Join-Path $Root ('session-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $Work | Out-Null
        return @{ Path = $Work; Lock = $Lock; Root = $Root }
    } catch {
        if ($Lock) { $Lock.Dispose() }
        if (Test-Path -LiteralPath $LockPath) { Remove-Item -LiteralPath $LockPath -Force }
        throw
    }
}
function Close-DevSession($Session, [bool]$Success) {
    $LockPath = Join-Path $Session.Root '.active'
    try {
        $ExpectedParent = [IO.Path]::GetFullPath($Session.Root)
        if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Session.Path)) -ne $ExpectedParent) { throw 'Invalid scratch path' }
        if ($Success) { Remove-Item -LiteralPath $Session.Path -Recurse -Force }
        else { Write-Warning "Diagnostic scratch retained: $($Session.Path)" }
    } finally {
        $Session.Lock.Dispose()
        if (Test-Path -LiteralPath $LockPath) { Remove-Item -LiteralPath $LockPath -Force }
    }
}
