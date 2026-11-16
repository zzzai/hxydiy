param([Parameter(Mandatory=$true)][string]$ReportPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$syncIcon = New-Object System.Windows.Forms.NotifyIcon
try {
    $syncIcon.Icon = [System.Drawing.SystemIcons]::Warning
    $syncIcon.Visible = $true
    $syncIcon.Text = 'HXY member sync stopped'
    $syncIcon.ShowBalloonTip(10000, '荷小悦会员同步已停止',
        "已暂停后续同步；已完成部分和待核实结果见本机报告，不会自动重试：$ReportPath",
        [System.Windows.Forms.ToolTipIcon]::Warning)
    $syncUntil = [DateTime]::UtcNow.AddSeconds(10)
    while ([DateTime]::UtcNow -lt $syncUntil) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 100
    }
} finally {
    $syncIcon.Visible = $false
    $syncIcon.Dispose()
}
