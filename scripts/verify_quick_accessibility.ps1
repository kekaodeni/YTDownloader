param([Parameter(Mandatory=$true)][string]$Exe, [Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$Output = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path $Output | Out-Null
$AppDataPath = Join-Path $Output "app-data"
New-Item -ItemType Directory -Force -Path $AppDataPath | Out-Null
$SettingsJson = @{schema_version=4; download_directory=(Join-Path $Output "Videos"); auto_check_updates=$false} | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $AppDataPath "settings.json"), $SettingsJson, (New-Object Text.UTF8Encoding($false)))
$StartInfo = New-Object Diagnostics.ProcessStartInfo
$StartInfo.FileName = [IO.Path]::GetFullPath($Exe)
$StartInfo.Arguments = "--theme light --preview-page download-demo"
$StartInfo.UseShellExecute = $false
$StartInfo.CreateNoWindow = $true
$StartInfo.EnvironmentVariables["YT_DOWNLOADER_DATA_DIR"] = $AppDataPath
$StartInfo.EnvironmentVariables["YT_DOWNLOADER_VIDEOS_DIR"] = Join-Path $Output "Videos"
$TestProcess = [Diagnostics.Process]::Start($StartInfo)
$Results = New-Object Collections.Generic.List[string]
try {
    for ($Attempt=0; $Attempt -lt 100; $Attempt++) {
        $TestProcess.Refresh()
        if ($TestProcess.MainWindowHandle -ne [IntPtr]::Zero) { break }
        Start-Sleep -Milliseconds 100
    }
    if ($TestProcess.MainWindowHandle -eq [IntPtr]::Zero) { throw "Application window was not created" }
    $AppRoot = [Windows.Automation.AutomationElement]::FromHandle($TestProcess.MainWindowHandle)
    function Find-Control([string]$Name, [string]$Type) {
        $Nodes = $AppRoot.FindAll([Windows.Automation.TreeScope]::Descendants, [Windows.Automation.Condition]::TrueCondition)
        foreach ($Node in $Nodes) {
            if ($Node.Current.Name -eq $Name -and $Node.Current.ControlType.ProgrammaticName -eq ("ControlType."+$Type) -and -not $Node.Current.IsOffscreen) { return $Node }
        }
        throw "Accessible control was not found: $Name ($Type)"
    }
    function Invoke-Button([string]$Name) {
        $Button = Find-Control $Name "Button"
        ([Windows.Automation.InvokePattern]$Button.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern)).Invoke()
        Start-Sleep -Milliseconds 350
    }
    $Nodes = $AppRoot.FindAll([Windows.Automation.TreeScope]::Descendants, [Windows.Automation.Condition]::TrueCondition)
    $Inventory = foreach ($Node in $Nodes) { [PSCustomObject]@{name=$Node.Current.Name;type=$Node.Current.ControlType.ProgrammaticName;offscreen=$Node.Current.IsOffscreen} }
    $Inventory | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $Output "initial-controls.json") -Encoding UTF8
    Invoke-Button "历史记录"
    $Results.Add("history-navigation")
    if (Test-Path -LiteralPath (Join-Path $AppDataPath "history.db")) {
        try { $HistoryRow = Find-Control "界面验证样例，下载完成" "ListItem" } catch { $HistoryRow = $null }
        if ($null -ne $HistoryRow) {
            Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class OwnWindowInput { [StructLayout(LayoutKind.Sequential)] public struct Point {public int x; public int y;} [DllImport("user32.dll")] public static extern bool ScreenToClient(IntPtr h, ref Point p); [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l); }'
            $Bounds = $HistoryRow.Current.BoundingRectangle
            $Point = New-Object OwnWindowInput+Point
            $Point.x = [int]($Bounds.X + $Bounds.Width/2)
            $Point.y = [int]($Bounds.Y + $Bounds.Height/2)
            $null = [OwnWindowInput]::ScreenToClient($TestProcess.MainWindowHandle, [ref]$Point)
            $Location = [IntPtr](($Point.y -shl 16) -bor ($Point.x -band 65535))
            $null = [OwnWindowInput]::PostMessage($TestProcess.MainWindowHandle,0x204,[IntPtr]2,$Location)
            $null = [OwnWindowInput]::PostMessage($TestProcess.MainWindowHandle,0x205,[IntPtr]0,$Location)
            Start-Sleep -Milliseconds 350
            $null = Find-Control "复制链接" "MenuItem"
            $null = Find-Control "设置视频封面" "MenuItem"
            $null = [OwnWindowInput]::PostMessage($TestProcess.MainWindowHandle,0x100,[IntPtr]27,[IntPtr]0)
            $null = [OwnWindowInput]::PostMessage($TestProcess.MainWindowHandle,0x101,[IntPtr]27,[IntPtr]0)
            Start-Sleep -Milliseconds 250
            $Results.Add("history-context-menu-open-and-dismiss")
        }
    }
    Invoke-Button "设置"
    $Results.Add("settings-navigation")
    Invoke-Button "关于"
    $Results.Add("about-navigation")
    Invoke-Button "下载"
    $UrlField = Find-Control "YouTube 视频链接" "Edit"
    ([Windows.Automation.ValuePattern]$UrlField.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern)).SetValue("invalid")
    Invoke-Button "解析"
    $CopyReport = $null
    for ($Attempt=0; $Attempt -lt 150; $Attempt++) {
        try { $CopyReport = Find-Control "复制错误报告" "Button"; break } catch { Start-Sleep -Milliseconds 100 }
    }
    if ($null -eq $CopyReport) {
        $Nodes = $AppRoot.FindAll([Windows.Automation.TreeScope]::Descendants, [Windows.Automation.Condition]::TrueCondition)
        $Inventory = foreach ($Node in $Nodes) { [PSCustomObject]@{name=$Node.Current.Name;type=$Node.Current.ControlType.ProgrammaticName;offscreen=$Node.Current.IsOffscreen} }
        $Inventory | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $Output "failure-controls.json") -Encoding UTF8
        throw "Error dialog did not appear within 15 seconds"
    }
    $Results.Add("invalid-url-error-dialog")
    Invoke-Button "关闭"
    $Results.Add("dialog-close")
    $Results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Output "accessibility-results.json") -Encoding UTF8
    Invoke-Button "设置"
    Invoke-Button "浏览"
    Start-Sleep -Milliseconds 350
    $Desktop = [Windows.Automation.AutomationElement]::RootElement
    $ProcessCondition = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ProcessIdProperty, $TestProcess.Id)
    $OwnWindows = $Desktop.FindAll([Windows.Automation.TreeScope]::Children, $ProcessCondition)
    $PickerInventory = foreach ($OwnWindow in $OwnWindows) {
        $PickerNodes = $OwnWindow.FindAll([Windows.Automation.TreeScope]::Subtree, [Windows.Automation.Condition]::TrueCondition)
        foreach ($Node in $PickerNodes) { [PSCustomObject]@{name=$Node.Current.Name;type=$Node.Current.ControlType.ProgrammaticName;offscreen=$Node.Current.IsOffscreen;handle=$Node.Current.NativeWindowHandle} }
    }
    $PickerInventory | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $Output "picker-controls.json") -Encoding UTF8
    $Picker = $null
    foreach ($OwnWindow in $OwnWindows) {
        $PickerNodes = $OwnWindow.FindAll([Windows.Automation.TreeScope]::Subtree, [Windows.Automation.Condition]::TrueCondition)
        foreach ($Candidate in $PickerNodes) {
            if ($Candidate.Current.ControlType.ProgrammaticName -eq "ControlType.Window" -and $Candidate.Current.Name -eq "选择目录") { $Picker = $Candidate; break }
        }
    }
    if ($null -eq $Picker) { throw "Native directory picker was not found" }
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class PickerCancel { [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l); }'
    # IDCANCEL sent exclusively to our own native directory dialog.
    $null = [PickerCancel]::PostMessage([IntPtr]$Picker.Current.NativeWindowHandle, 0x111, [IntPtr]2, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 500
    $null = Find-Control "浏览" "Button"
    $Results.Add("native-directory-picker-open-and-cancel")
    $Results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Output "accessibility-results.json") -Encoding UTF8
    Write-Output ($Results -join ", ")
}
finally {
    $TestProcess.Refresh()
    if (-not $TestProcess.HasExited) {
        $null = $TestProcess.CloseMainWindow()
        if (-not $TestProcess.WaitForExit(4000)) { $TestProcess.Kill(); $TestProcess.WaitForExit() }
    }
}
