param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$PrivateRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$PackageSha256
)
$ErrorActionPreference = 'Stop'
$syncPackage = $PSScriptRoot
$syncRoot = (Resolve-Path -LiteralPath $PrivateRoot).Path
$syncPython = (Resolve-Path -LiteralPath $PythonPath).Path
$syncManifest = Join-Path $syncPackage 'package-manifest.json'
if ((Get-FileHash -LiteralPath $syncManifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $PackageSha256) {
    throw 'Package manifest mismatch'
}
if ($syncRoot.Contains('"') -or $syncPackage.Contains('"') -or $syncPython.Contains('"')) {
    throw 'Invalid quoted path'
}
$syncIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$syncSid = $syncIdentity.User.Value
$syncAllowed = @($syncSid, 'S-1-5-18', 'S-1-5-32-544')
foreach ($syncPath in @($syncRoot, $syncPackage)) {
    foreach ($syncRule in (Get-Acl -LiteralPath $syncPath).Access) {
        $syncRuleSid = $syncRule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        if ($syncRule.AccessControlType -eq 'Allow' -and $syncAllowed -notcontains $syncRuleSid) {
            throw 'Private directory has an unexpected access grant'
        }
    }
}
$syncName = 'HXY-MemberSync-Controlled'
if (Get-ScheduledTask -TaskName $syncName -ErrorAction SilentlyContinue) {
    throw 'Task already exists; inspect it before replacement'
}
$syncArgs = '-B "' + (Join-Path $syncPackage 'session.py') + '" --root "' + $syncRoot + '" --package-sha256 ' + $PackageSha256
$syncAction = New-ScheduledTaskAction -Execute $syncPython -Argument $syncArgs -WorkingDirectory $syncPackage
$syncTrigger = @((New-ScheduledTaskTrigger -Daily -At '10:00'), (New-ScheduledTaskTrigger -AtLogOn -User $syncIdentity.Name))
$syncPrincipal = New-ScheduledTaskPrincipal -UserId $syncIdentity.Name -LogonType Interactive -RunLevel Limited
$syncSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 25)
Register-ScheduledTask -TaskName $syncName -Action $syncAction -Trigger $syncTrigger -Principal $syncPrincipal -Settings $syncSettings -Description 'Verified additive member sync; no model calls; halt and notify on failures' | Out-Null
Get-ScheduledTask -TaskName $syncName | Select-Object TaskName, State
