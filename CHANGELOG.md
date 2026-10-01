# Changelog

## 1.7.0
- Nuevo modo de keep-alive `Petición directa al servidor` (`request`, ahora recomendado): latido con `page.context.request` usando las cookies de la sesión, sin tocar la pestaña visible ni ejecutar JS (solo descarga el HTML). Tráfico real que renueva la inactividad en el servidor con transferencia mínima y sin registrar conexiones nuevas; con intervalo corto (2-5 min) aguanta plataformas que echan por inactividad en 10-30 min, donde el modo ligero (cero peticiones) no puede funcionar. Misma doble confirmación anti falso positivo y re-login que el resto de modos; 6 tests nuevos.
- Nueva opción por tarea `Si el equipo estaba apagado, ejecutar en cuanto sea posible` (equivale al `StartWhenAvailable` del Programador de tareas).
- La lista distingue tareas en marcha: fila en verde con 🟢, ESTADO `🟢 En marcha`, columna ▶ a ⏹ y contador, con sondeo cada 5 s; pulsar ⏹ avisa en vez de relanzar.
- Corrección en `find_first`: si la página se cerró (p. ej. ventana cerrada a mano), se propaga como error de navegación con reintentos en vez de informar "campo no encontrado" y "selector no válido" por cada candidato.
- Corrección en la rama de login fallido: la captura y la URL/título van protegidas si la página ya estaba cerrada (antes dejaban un traceback ruidoso).
- Corrección: el filtro de búsqueda ya no revienta al arrancar (`tree` aún no existe) y el runner de `Probar ahora` ya no ensucia la consola de la app.

## 1.6.2
- Pausar/reactivar, por fin visible: botón ⏸/▶ en la cabecera del formulario (sin tocar el resto ni pasar por Guardar), barra de lote disponible con 1 sola tarea seleccionada y nueva columna ESTADO en la lista (Activa/Pausada).
- Pausar detiene el mantenimiento en curso: si la tarea tiene un runner vivo, pregunta y lo detiene (proceso + Chromium hijo) limpiando su lock; antes seguía corriendo hasta agotar su duración.
- Instancia única de la GUI: si ya hay una app abierta, la segunda avisa con el PID y sale en vez de duplicar la ventana (el lock huérfano se reemplaza solo).

## 1.6.1
- Corrección real del redimensionado en modo visible: la 1.6.0 usaba `viewport=None` (se ignora y queda el fijo 1280x720); ahora usa `no_viewport=True`, que es lo que Playwright documenta para que la página siga a la ventana al maximizar/achicar.
- El runner detecta la pestaña cerrada también durante la espera entre ciclos y termina en ~60 s liberando el lock (antes retenía el lock hasta el siguiente ciclo y el siguiente intento decía "ya hay otra ejecución en curso").
- La GUI al salir mata de verdad el runner de prueba (`terminate → espera → kill`) y para el icono de bandeja; ya no quedan procesos colgados al cerrar la app.

## 1.6.0
- Nuevo modo de keep-alive `Visitar página de trabajo` (`work`): navegación completa a `keep_alive_url` (o a la página tras el login si no hay) en cada ciclo. Para sitios donde la sesión se sigue cerrando con `fetch` (XHR ignorado) o `reload` (recarga lo que haya): vuelve siempre a una URL conocida-buena, re-ejecuta su JS y renueva tokens; si caduca, re-login automático igual que el resto de modos.
- Corrección: en modo visible el viewport de Playwright era fijo (1280x720) y la página no se redimensionaba al maximizar/achicar la ventana; ahora usa `viewport=None` para que siga a la ventana (en headless se mantiene fijo para capturas deterministas).

## 1.5.2
- Nuevo modo de keep-alive `Toque ligero al servidor` (ahora por defecto): petición mínima con las cookies de la sesión, sin recargar ni navegar. Mantiene viva la sesión en plataformas que miden la inactividad en el servidor (p. ej. Moodle) sin registrar conexiones nuevas; si la respuesta parece una página de login, confirma antes de reconectar. El modo `Solo actividad local` queda para sitios con temporizador JavaScript (no mantiene sesiones de servidor).
- Corrección: en modo fetch la caducidad confirmada ya no pasa además por la rama de recarga (evita una recarga doble antes del re-login).

## 1.5.1
- Keep-alive con modos por tarea: `Ligero` (por defecto, también para tareas antiguas) mantiene la sesión con actividad mínima de ratón/scroll sin recargar la página, así la plataforma no registra una conexión nueva en cada intervalo; `Recarga completa` conserva el comportamiento anterior para sitios que lo exijan. El modo ligero solo reconecta tras doble confirmación (anti falso positivo: un campo de contraseña transitorio ya no provoca un re-login cada ciclo).
- `Probar ahora` ejecuta una prueba real con keep-alive en segundo plano (igual que la tarea programada): el botón cambia a `Detener prueba` mientras corre y la app no deja runners colgados al salir.
- El modo se guarda por tarea y se conserva al importar/exportar y en las acciones en lote; 3 tests nuevos del modo ligero.

## 1.5.0
- Keep-alive renovado: deadline con reloj monotónico, espera en tramos de 60 s con vigencia reactiva, abandono solo tras 3 fallos consecutivos (un ciclo sano resetea), sesión guardada tras cada re-login, historial honesto (fallo con motivo si abandona), detección de caducidad ampliada (textos multilingües + ancla a la página post-login) y franja horaria opcional por tarea (admite nocturnas); 16 tests nuevos con página falsa.
- Ejecución al instante: columna ▶ en cada fila de tareas (clic para ejecutar) más botón «▶ Ejecutar» en la barra; usa la configuración guardada sin tocar el formulario, con estado ⏳ mientras corre y aviso si ya está en curso.
- Actualización manual: eliminado el botón de auto-actualización (no funcionaba); el aviso de nueva versión abre la release en el navegador para descargar, con limpieza del código muerto y docs actualizadas.

## 1.4.0
- Versión visible en el título de la ventana principal.
- Página de trabajo post-login (`keep_alive_url`, opcional por tarea): tras iniciar sesión el runner abre ese enlace y el keep-alive mantiene la sesión en él en vez de en la página del login; con tooltip, validación http(s) en la GUI, import/export y aviso no fatal si no se puede abrir.
- Lock anti-solape: el runner toma `logs/<id>.lock` (PID + hora) y si ya hay una ejecución viva se omite sin marcar fallo ni notificar; los locks de procesos muertos o corruptos se reemplazan; `--detect-only` no necesita lock.
- Acciones en lote: la lista permite multi-selección (`extended`) con barra de lote (Activar / Pausar / Eliminar), confirmación con vista previa, sincronización con el Programador por hilo de fondo y atajos (Supr, Ctrl+A, Esc + consejo visible).
- Tests y módulos: nueva lógica pura en `app_logic.py` (antes duplicada en `gui_config.py`) y `task_lock.py` testeables sin Tkinter; suite `tests/` (lógica, lock, config_store, vigencia y página de trabajo); workflow `tests.yml` en push/PR y gate de tests en `release.yml` antes de empaquetar.
- Interfaz renovada: cabecera con versión, tarjetas por sección, tabla con zebra e iconos de estado, buscador con placeholder, contador de tareas, etiquetas de campo en mayúsculas, botón Mostrar/Ocultar contraseña, insignia NUEVA/ACTIVA/PAUSADA, mensajes de estado como pastillas de color, pie con resumen, diálogos centrados/modales y tooltips adaptados al tema; paleta y tipografías refinadas en claro/oscuro.

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
