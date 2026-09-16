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
- Opción de "mantener la sesión activa" tras el login, con reintentos y re-login
  automático si la sesión caduca.
- Reutilización de sesión (cookies) entre ejecuciones para no repetir logins innecesarios.
- Historial del resultado de la última ejecución y notificaciones de Windows si falla.
- Exportar/importar tareas (con o sin contraseñas) para respaldo o mover la configuración
  a otro equipo.
- Icono en la bandeja del sistema: cerrar la ventana la minimiza en vez de salir.
- Comprobación de actualizaciones y, en la versión portable, actualización con un clic
  (descarga la nueva versión y se reemplaza sola).
- Modo oscuro/claro (automático según Windows, o manual desde ⚙ Configuración).
- Buscador y ordenación por columnas en la lista de tareas.
- Visor de log integrado y modo "solo detección" (comprueba los selectores sin enviar
  ningún dato, para configurar un sitio nuevo sin arriesgarte a un bloqueo).
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

## Instalación desde el código fuente

```bash
pip install -r requirements.txt
playwright install chromium
python gui_config.py
```

## Estructura

| Archivo | Función |
|---|---|
| `gui_config.py` | Interfaz gráfica (Tkinter) para crear y gestionar tareas. |
| `run_login.py` | Ejecuta el login de una tarea (usado por la GUI y por la tarea programada). |
| `config_store.py` | Persistencia de tareas, resultados y sesión guardada. |
| `crypto_utils.py` | Cifrado/descifrado de contraseñas con DPAPI. |
| `register_task.ps1` / `unregister_task.ps1` | Alta/baja de la tarea en el Programador de tareas de Windows. |
| `list_next_runs.ps1` | Consulta la próxima ejecución programada de cada tarea. |

## Notas de seguridad

- Las tareas programadas usan `LogonType Interactive`: solo corren con tu sesión iniciada (exigencia de DPAPI).
- La sesión reutilizada (`logs/*_session.json`) se guarda en claro: quien copie ese fichero hereda tu sesión.
- Exportar con contraseñas las deja en texto plano: custodia ese `.json`.
- La auto-actualización verifica el `.sha256` oficial y se bloquea si no coincide o si el release no lo publica.
- Duración keep-alive `0:00` = indefinido: el runner queda vivo recargando y ocupa su tarea programada.

## Licencia

MIT — ver `LICENSE`.
