<#
.SYNOPSIS
    Elimina la tarea programada de Windows asociada a un id de tarea, si existe.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskId
)

$TaskName = "AutoLogin_$TaskId"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Tarea programada '$TaskName' eliminada."
} else {
    Write-Host "No había ninguna tarea programada '$TaskName' registrada."
}
