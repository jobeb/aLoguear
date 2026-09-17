# Changelog

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
