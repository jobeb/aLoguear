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
    [string]$TaskName = ""
)

$ErrorActionPreference = "Stop"

if (-not $TaskName) {
    $TaskName = "AutoLogin_$TaskId"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript = Join-Path $scriptDir "run_login.py"

$dayList = $Days -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
if (-not $dayList -or $dayList.Count -eq 0) {
    throw "Debes indicar al menos un día en -Days."
}

# Resuelve la ruta real del intérprete de Python a través del lanzador "py",
# ya que python.exe no siempre está en el PATH del sistema.
$pythonExe = & py -c "import sys; print(sys.executable)"
if (-not $pythonExe -or -not (Test-Path $pythonExe)) {
    throw "No se pudo resolver python.exe mediante el lanzador 'py'. Instala Python o ajusta este script."
}
# Usa pythonw.exe (sin consola) si está disponible junto a python.exe
$pythonwExe = Join-Path (Split-Path $pythonExe) "pythonw.exe"
if (-not (Test-Path $pythonwExe)) {
    $pythonwExe = $pythonExe
}

$action = New-ScheduledTaskAction -Execute $pythonwExe -Argument "`"$runScript`" `"$TaskId`"" -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $dayList -At $Time
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Tarea '$TaskName' registrada: se ejecutará a las $Time los días: $($dayList -join ', ') (requiere sesión iniciada)."
