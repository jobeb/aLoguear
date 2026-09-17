# aLoguear

Aplicación de escritorio para Windows que inicia sesión automáticamente en páginas web
(usuario/contraseña) y programa esos inicios de sesión como tareas periódicas del
Programador de tareas de Windows. Pensada para plataformas que exigen mantener una
sesión activa (por ejemplo, campus virtuales de formación).

## Características

- Gestión de varias tareas de login independientes desde una sola ventana.
- Contraseñas cifradas con DPAPI (ligadas al usuario de Windows, nunca en texto plano).
- Detección automática de los campos de usuario/contraseña/botón de envío, con selectores
  CSS manuales como respaldo.
- Programación por hora y días de la semana, integrada con el Programador de tareas de
  Windows (crear, actualizar, pausar y eliminar desde la propia app).
- Vigencia por fechas: cada tarea puede tener fecha de inicio y fin (YYYY-MM-DD);
  fuera de rango el runner se omite sin marcar fallo, y el Programador de Windows
  también deja de dispararla.
- Opción de "mantener la sesión activa" tras el login, con recargas con jitter,
  deadline real, espera por tramos con fin de vigencia reactivo, re-login con
  reintentos (abandona solo tras 3 fallos seguidos), sesión guardada en cada
  re-login, resultado honesto en el historial y franja horaria opcional
  (p. ej. solo de 8:00 a 20:00, admite nocturno).
- Reutilización de sesión (cookies) entre ejecuciones para no repetir logins innecesarios.
- Historial del resultado de la última ejecución y notificaciones de Windows si falla.
- Exportar/importar tareas (con o sin contraseñas) para respaldo o mover la configuración
  a otro equipo.
- Icono en la bandeja del sistema: cerrar la ventana la minimiza en vez de salir.
- Comprobación de actualizaciones con aviso y descarga manual desde el navegador.
- Modo oscuro/claro (automático según Windows, o manual desde ⚙ Configuración).
- Buscador y ordenación por columnas en la lista de tareas.
- Visor de log integrado y modo "solo detección" (comprueba los selectores sin enviar
  ningún dato, para configurar un sitio nuevo sin arriesgarte a un bloqueo).
- Lock anti-solape: si una ejecución (p. ej. keep-alive largo) sigue viva, la siguiente
  no la pisa: se omite sin marcar fallo.
- Página de trabajo opcional: tras el login, abre un enlace de la plataforma (p. ej.
  tu curso o panel) y mantiene la sesión en él durante el keep-alive.
- Acciones en lote: selecciona varias tareas (Ctrl+clic / Mayús+clic) para activarlas,
  pausarlas o eliminarlas de una vez (atajos: Supr, Ctrl+A, Esc).
- Rotación de logs y espera progresiva entre reintentos.
- Sección de **Configuración** (⚙): arranque automático con Windows, activar/desactivar
  notificaciones, elegir qué hace el botón de cerrar (bandeja o salir), tamaño máximo de
  log y carpeta donde se guardan los datos.

## Requisitos

- Windows 10/11.
- Python 3.11+ (si se ejecuta desde el código fuente; la versión portable no lo necesita).

## Descarga (versión portable)

Descarga el `.zip` de la [última versión](https://github.com/jobeb/aLoguear/releases/latest),
descomprímelo donde quieras y ejecuta `aLoguear.exe`. No hace falta instalar nada más:
la app descarga Chromium sola la primera vez que hace falta.

Cada release incluye también un archivo `.sha256` con la huella del `.zip`, por si quieres
verificar que la descarga no se corrompió o alteró:

```powershell
Get-FileHash aLoguear-vX.Y.Z-win64.zip -Algorithm SHA256
# compara el resultado con el contenido del .sha256 adjunto
```

> **Aviso de Windows SmartScreen**: al ejecutar `aLoguear.exe` por primera vez, Windows
> puede mostrar "Windows protegió tu PC" porque el ejecutable no está firmado con un
> certificado de editor (esto es normal en proyectos personales/de código abierto sin
> firma comercial). Para continuar: pulsa **"Más información"** y luego
> **"Ejecutar de todas formas"**. Este aviso solo aparece la primera vez que se ejecuta
> ese archivo en el equipo.

## Actualizar a una versión nueva

Cuando haya una versión nueva, la app muestra un aviso con el botón
**"⬇ Descargar actualización"**, que abre la página de la release en el
navegador. Descarga el `.zip`, cierra la app y descomprímelo encima de tu
carpeta actual (puedes verificar el `.sha256` adjunto como se explica arriba).

## Instalación desde el código fuente

```bash
pip install -r requirements.txt
playwright install chromium
python gui_config.py
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```

## Estructura

| Archivo | Función |
|---|---|
| `gui_config.py` | Interfaz gráfica (Tkinter) para crear y gestionar tareas. |
| `app_logic.py` | Validaciones y formatos puros de la GUI (sin Tkinter, con tests). |
| `task_lock.py` | Lock anti-solape (`logs/<id>.lock`) para no solapar ejecuciones. |
| `tests/` | Suite pytest (lógica, lock, config_store, vigencia). |
| `run_login.py` | Ejecuta el login de una tarea (usado por la GUI y por la tarea programada). |
| `config_store.py` | Persistencia de tareas, resultados y sesión guardada. |
| `crypto_utils.py` | Cifrado/descifrado de contraseñas con DPAPI. |
| `register_task.ps1` / `unregister_task.ps1` | Alta/baja de la tarea en el Programador de tareas de Windows. |
| `list_next_runs.ps1` | Consulta la próxima ejecución programada de cada tarea. |

## Notas de seguridad

- Las tareas programadas usan `LogonType Interactive`: solo corren con tu sesión iniciada (exigencia de DPAPI).
- La sesión reutilizada (`logs/*_session.json`) se guarda en claro: quien copie ese fichero hereda tu sesión.
- Exportar con contraseñas las deja en texto plano: custodia ese `.json`.
- Descarga las actualizaciones solo desde la página oficial de releases del proyecto.
- Duración keep-alive `0:00` = indefinido: el runner queda vivo recargando y ocupa su tarea programada.

## Licencia

MIT — ver `LICENSE`.
