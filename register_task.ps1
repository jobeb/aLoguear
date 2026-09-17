<#
.SYNOPSIS
    Registra (o actualiza) la tarea programada de Windows para una tarea de login guardada.

.PARAMETER TaskId
    Id de la tarea (tal como se guarda en tasks.json). Obligatorio.

.PARAMETER Time
    Hora de ejecución en formato HH:mm (24h). Por defecto 08:00.

.PARAMETER Days
    Lista de días separados por coma en inglés (Monday,Tuesday,Wednesday,
    Thursday,Friday,Saturday,Sunday). Por defecto, los 7 días.

.PARAMETER TaskName
    Nombre de la tarea en el Programador de tareas. Por defecto "AutoLogin_<TaskId>".

.PARAMETER RunnerExe
    Ruta a aLoguear-runner.exe (versión empaquetada). Si se indica, la tarea
    ejecuta ese .exe directamente y no hace falta tener Python instalado. Si
    se omite, se resuelve python.exe mediante el lanzador "py" (modo
    desarrollo, ejecutando run_login.py).

.PARAMETER StartDate
    Fecha de inicio de vigencia (YYYY-MM-DD). Vacío = sin límite. Se aplica
    como StartBoundary del desencadenador y además la comprueba el runner.

.PARAMETER EndDate
    Fecha de fin de vigencia (YYYY-MM-DD, inclusiva). Vacío = sin límite. Se
    aplica como EndBoundary del desencadenador y además la comprueba el runner.

.NOTES
    La contraseña se descifra con DPAPI ligado a tu usuario de Windows, por lo
    que la tarea se registra con inicio de sesión "Interactive": solo se
    ejecutará correctamente cuando tu cuenta esté conectada (no en segundo
    plano tras cerrar sesión).
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskId,
    [string]$Time = "08:00",
    [string]$Days = "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
    [string]$TaskName = "",
    [string]$RunnerExe = "",
    [string]$StartDate = "",
    [string]$EndDate = ""
)

$ErrorActionPreference = "Stop"

if (-not $TaskName) {
    $TaskName = "AutoLogin_$TaskId"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$dayList = $Days -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
if (-not $dayList -or $dayList.Count -eq 0) {
    throw "Debes indicar al menos un día en -Days."
}

if ($RunnerExe) {
    if (-not (Test-Path $RunnerExe)) {
        throw "No se encontró el ejecutable indicado en -RunnerExe: $RunnerExe"
    }
    $action = New-ScheduledTaskAction -Execute $RunnerExe -Argument "`"$TaskId`"" -WorkingDirectory (Split-Path $RunnerExe)
} else {
    # Resuelve la ruta real del intérprete de Python: primero el lanzador "py"
    # y, si no existe (Store Python, PATH directo...), python.exe del PATH.
    $runScript = Join-Path $scriptDir "run_login.py"
    $pythonExe = ""
    try {
        $pythonExe = (& py -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1).Trim()
    } catch {
        $pythonExe = ""
    }
    if (-not $pythonExe -or -not (Test-Path $pythonExe)) {
        $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($cmd) { $pythonExe = $cmd.Source }
    }
    if (-not $pythonExe -or -not (Test-Path $pythonExe)) {
        throw "No se pudo resolver python.exe (ni con el lanzador 'py' ni en el PATH). Instala Python o ajusta este script."
    }
    # Usa pythonw.exe (sin consola) si está disponible junto a python.exe
    $pythonwExe = Join-Path (Split-Path $pythonExe) "pythonw.exe"
    if (-not (Test-Path $pythonwExe)) {
        $pythonwExe = $pythonExe
    }
    $action = New-ScheduledTaskAction -Execute $pythonwExe -Argument "`"$runScript`" `"$TaskId`"" -WorkingDirectory $scriptDir
}
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $dayList -At $Time

# Vigencia por fechas: StartBoundary/EndBoundary del desencadenador. El runner
# vuelve a comprobarlas (por si la tarea se lanza a mano fuera de rango).
if ($StartDate -and $StartDate.Trim() -ne "") {
    try {
        $startDt = [datetime]::ParseExact($StartDate.Trim(), "yyyy-MM-dd", $null)
        $timeParts = $Time -split ":"
        $trigger.StartBoundary = $startDt.AddHours([int]$timeParts[0]).AddMinutes([int]$timeParts[1]).ToString("yyyy-MM-ddTHH:mm:ss")
    } catch {
        throw "StartDate no válida (usa YYYY-MM-DD): $StartDate"
    }
}
if ($EndDate -and $EndDate.Trim() -ne "") {
    try {
        $endDt = [datetime]::ParseExact($EndDate.Trim(), "yyyy-MM-dd", $null)
        # Fin de día inclusivo: el desencadenador deja de disparar al terminar ese día.
        $trigger.EndBoundary = $endDt.AddDays(1).ToString("yyyy-MM-ddTHH:mm:ss")
    } catch {
        throw "EndDate no válida (usa YYYY-MM-DD): $EndDate"
    }
}

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

$rangeMsg = ""
if (($StartDate -and $StartDate.Trim() -ne "") -or ($EndDate -and $EndDate.Trim() -ne "")) {
    $rangeMsg = " (vigencia: $($StartDate.Trim()) -> $($EndDate.Trim()))"
}
Write-Host "Tarea '$TaskName' registrada: se ejecutará a las $Time los días: $($dayList -join ', ')$rangeMsg (requiere sesión iniciada)."
