param([Parameter(Mandatory=$true)][string]$PrivateRoot)
$ErrorActionPreference = 'Stop'
# Windows PowerShell must not autoload the incompatible PowerShell 7 security module.
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$syncItem = Get-Item -LiteralPath $PrivateRoot
if (-not $syncItem.PSIsContainer -or ($syncItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Private root must be a normal directory'
}
$syncSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$syncAllowed = @($syncSid, 'S-1-5-18', 'S-1-5-32-544')
foreach ($syncRule in (Get-Acl -LiteralPath $PrivateRoot).Access) {
    $syncRuleSid = $syncRule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    if ($syncRule.AccessControlType -eq 'Allow' -and $syncAllowed -notcontains $syncRuleSid) {
        throw 'Private directory has an unexpected access grant'
    }
}
