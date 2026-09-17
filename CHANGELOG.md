# Changelog

## 1.4.0
- Versión visible en el título de la ventana principal.
- Página de trabajo post-login (`keep_alive_url`, opcional por tarea): tras iniciar sesión el runner abre ese enlace y el keep-alive mantiene la sesión en él en vez de en la página del login; con tooltip, validación http(s) en la GUI, import/export y aviso no fatal si no se puede abrir.
- Lock anti-solape: el runner toma `logs/<id>.lock` (PID + hora) y si ya hay una ejecución viva se omite sin marcar fallo ni notificar; los locks de procesos muertos o corruptos se reemplazan; `--detect-only` no necesita lock.
- Acciones en lote: la lista permite multi-selección (`extended`) con barra de lote (Activar / Pausar / Eliminar), confirmación con vista previa, sincronización con el Programador por hilo de fondo y atajos (Supr, Ctrl+A, Esc + consejo visible).
- Tests y módulos: nueva lógica pura en `app_logic.py` (antes duplicada en `gui_config.py`) y `task_lock.py` testeables sin Tkinter; suite `tests/` (lógica, lock, config_store, vigencia y página de trabajo); workflow `tests.yml` en push/PR y gate de tests en `release.yml` antes de empaquetar.
- Interfaz renovada: cabecera con versión, tarjetas numeradas (①②③④), tabla con zebra e iconos de estado, buscador con placeholder, contador de tareas, etiquetas de campo en mayúsculas, botón Mostrar/Ocultar contraseña, insignia NUEVA/ACTIVA/PAUSADA, mensajes de estado como pastillas de color, pie con resumen, diálogos centrados/modales y tooltips adaptados al tema; paleta y tipografías refinadas en claro/oscuro.

## 1.3.6
- Actualizador: sin fallos silenciosos. Comprueba permiso de escritura antes de cerrar, registra todo en `update.log`, reintenta la copia 30 veces, deja `update.failed` si no puede aplicar y avisa en el próximo arranque con opción de descarga manual; salida del proceso garantizada con vigilante (`os._exit`).
- Vigencia por fechas (`schedule_start_date`/`schedule_end_date`): columna Vigencia en la lista, validación inicio ≤ fin, el runner se omite fuera de rango sin marcar fallo, `register_task.ps1` fija Start/EndBoundary.
- Keep-alive mejorado: jitter en recargas, detección de caducidad por campo password + pistas en URL/título, re-login con reintentos y backoff (máx. 3 re-logins), respeta fin de vigencia a mitad de ejecución, log de tiempo restante.
- `run_login`: la auto-descarga de Chromium funciona también en el .exe empaquetado (usa el driver interno en modo `frozen` en vez de `python -m playwright`); los fallos de arranque ya no muestran el diálogo `Unhandled exception in script`, se registran en el log y devuelven código 1.
- `gui_config`: el visor de log añade el botón `Descargar log completo` para guardar una copia y enviarla al informar de un error.

## 1.3.5
- `config_store`: rutas resueltas en cada llamada, tolera `tasks.json` corrupto y `password_enc` ausente/inválido, escritura atómica (`.tmp` + `os.replace`), `LOCALAPPDATA` con fallback.
- `crypto_utils`: rechaza cifrar cadena vacía (se guarda como `""` sin DPAPI).
- `gui_config`: valida URL http(s), hora y keep-alive sin reventar; importa solo entradas con URL válida y normaliza hora/días; cwd del runner corregido; orden cronológico en Última/Próxima; auto-update verifica SHA256 y bloquea si falla; aviso de keep-alive indefinido.
- `run_login`: selectores inválidos logueados sin tumbar, espera a `hidden` del campo password (anti-falsos positivos en SPA), instala Chromium con `python -m playwright` (sin API privada), traceback completo en log, aviso de keep-alive indefinido.
- `register_task.ps1`: fallback a `python.exe` del PATH si falta el lanzador `py`.
- `release.yml`: chequeo tag == `version.py` + `compileall`.
- `requirements.txt` pineados; licencia MIT (`LICENSE`).
