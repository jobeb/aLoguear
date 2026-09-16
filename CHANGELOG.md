# Changelog

## 1.3.5
- `config_store`: rutas resueltas en cada llamada, tolera `tasks.json` corrupto y `password_enc` ausente/inválido, escritura atómica (`.tmp` + `os.replace`), `LOCALAPPDATA` con fallback.
- `crypto_utils`: rechaza cifrar cadena vacía (se guarda como `""` sin DPAPI).
- `gui_config`: valida URL http(s), hora y keep-alive sin reventar; importa solo entradas con URL válida y normaliza hora/días; cwd del runner corregido; orden cronológico en Última/Próxima; auto-update verifica SHA256 y bloquea si falla; aviso de keep-alive indefinido.
- `run_login`: selectores inválidos logueados sin tumbar, espera a `hidden` del campo password (anti-falsos positivos en SPA), instala Chromium con `python -m playwright` (sin API privada), traceback completo en log, aviso de keep-alive indefinido.
- `register_task.ps1`: fallback a `python.exe` del PATH si falta el lanzador `py`.
- `release.yml`: chequeo tag == `version.py` + `compileall`.
- `requirements.txt` pineados; licencia MIT (`LICENSE`).
