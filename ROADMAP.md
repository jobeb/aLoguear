# Mejoras futuras para aLoguear

Lista priorizada de mejoras posibles. `P1` = alto valor / bajo coste,
`P2` = valor medio, `P3` = ideas a largo plazo.

## Robustez del runner

- **P1 – Verificación post-login configurable por tarea**: hoy el éxito se infiere
  porque el campo password desaparece. Añadir campo opcional "URL o texto que
  confirma login correcto" (p. ej. que la URL contenga `/campus` o aparezca el
  texto "Mis cursos") para eliminar falsos positivos en más sitios.
- **P1 – Límite de ejecuciones solapadas**: si una tarea programada tarda más que
  su intervalo (keep-alive largo), Windows puede lanzar otra instancia y pelear
  por la sesión. Guardar un lock (`logs/<id>.lock`) y salir si ya hay una
  ejecución viva.
- **P2 – Modo headless "anti-detección" opcional**: rotar user-agent y viewport
  por tarea para sitios que bloquean automatización.
- **P2 – Reintentar solo ante errores de red**: ya se hace en el login inicial;
  extender la distinción red-vs-credenciales al re-login del keep-alive para no
  reintentar con contraseña errónea (riesgo de bloqueo de cuenta).

## Programación y vigencia

- **P1 – Vista "próximas ejecuciones" real**: `list_next_runs.ps1` solo lee el
  Scheduler; combinarlo con la vigencia (no mostrar próxima si está fuera de
  rango o pausada) y avisos de "esta tarea ya no volverá a ejecutarse".
- **P1 – Limpieza/auto-pausado al expirar**: al detectar fin de vigencia,
  pausar la tarea (unregister) automáticamente en vez de solo omitir ejecuciones.
- **P2 – Varias horas al día por tarea**: hoy solo una hora; permitir lista de
  horas (varios triggers semanales en el mismo `ScheduledTask`).
- **P2 – Calendario visual para vigencia**: sustituir los `Entry` YYYY-MM-DD por
  un mini-calendario (`tkcalendar` es dependencia nueva; valorar si compensa) o
  al menos botones "hoy / +30 días / limpiar".

## Keep-alive

- **P2 – Heartbeat configurable**: elegir entre recarga completa, `fetch` ligero
  o navegación a una URL "ping" del sitio (algunos campus penalizan recargas
  totales frecuentes).
- **P2 – Horario de keep-alive**: limitar el mantenimiento a una franja horaria
  (p. ej. solo 8:00–20:00) en vez de duración desde el login.
- **P3 – Keep-alive cooperativo**: un solo proceso que mantiene varias tareas a
  la vez en pestañas del mismo navegador (menos procesos de Chromium colgados).

## Seguridad

- **P1 – Cifrar `*_session.json`**: hoy la sesión reutilizada está en claro.
  Cifrarla con DPAPI igual que la contraseña (descifrar a fichero temporal solo
  durante la ejecución y borrarlo al salir).
- **P2 – Bloqueo de export con contraseña maestra**: pedir confirmación y
  advertencia más visible al exportar con contraseñas; opción de export cifrado
  con contraseña (p. ej. Fernet) para mover entre equipos sin texto plano.
- **P2 – Verificar firma/hash también en descarga inicial de Chromium**: hoy se
  confía en el CDN de Playwright por HTTPS; documentar o fijar versión de
  navegador conocida.

## UX de la GUI

- **P1 – Estado de vigencia en la lista**: colorear o marcar tareas no vigentes
  todavía / expiradas (hoy solo se ve el rango en texto).
- **P1 – Log en vivo al "Probar ahora"**: mostrar la salida del runner en una
  ventana con scroll en tiempo real en vez de obligar a abrir el fichero.
- **P2 – Asistente de primera tarea**: wizard paso a paso (URL → detectar →
  credenciales → horario → probar) para usuarios no técnicos.
- **P2 – Atajos y multi-selección**: activar/pausar/eliminar varias tareas a la
  vez desde la lista.
- **P3 – Trocear `gui_config.py` (~2100 líneas)**: separar estilo/tray/update/
  scheduler en módulos para poder testear sin Tkinter.

## Observabilidad

- **P1 – Historial de ejecuciones** (no solo la última): guardar las últimas N
  ejecuciones por tarea con fecha, duración y motivo, y mostrarlas en la GUI.
- **P2 – Notificación también en éxito recuperado**: avisar cuando un re-login
  automático salva la sesión, no solo cuando falla.
- **P2 – Estadística semanal**: "esta tarea falló X de Y veces esta semana" para
  detectar sitios que cambiaron su formulario.

## Empaquetado y CI

- **P1 – Tests automáticos en CI**: pruebas unitarias de `config_store`,
  validaciones de la GUI pura y parseo de fechas + `compileall` (ya existe el
  paso) antes de permitir una release.
- **P2 – Versionado automático**: derivar `version.py` del tag en CI en vez de
  mantenerlo a mano (hoy pueden divergir y el workflow falla).
- **P3 – Firma de código**: certificado para eliminar el aviso SmartScreen (tiene
  coste anual; alternativa: documentar el proceso actual, ya hecho en README).
