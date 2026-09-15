<#
.SYNOPSIS
    Devuelve en JSON la próxima ejecución programada de cada tarea AutoLogin_*.
#>
$results = @(Get-ScheduledTask -TaskName "AutoLogin_*" -ErrorAction SilentlyContinue |
    Get-ScheduledTaskInfo -ErrorAction SilentlyContinue |
    ForEach-Object {
        [PSCustomObject]@{
            TaskId      = ($_.TaskName -replace '^AutoLogin_', '')
            NextRunTime = $_.NextRunTime
        }
    })

ConvertTo-Json -InputObject $results -Compress
