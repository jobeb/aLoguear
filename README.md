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

## Requisitos

- Windows 10/11.
- Python 3.11+ (si se ejecuta desde el código fuente).

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

## Licencia

Uso personal.
