@echo off
rem Doble clic para lanzar aLoguear en modo desarrollo (sin compilar).
cd /d "%~dp0"
if exist gui_config.py goto lanzar
echo No se encuentra gui_config.py en "%~dp0"
pause
exit /b 1
:lanzar
py gui_config.py
if errorlevel 1 (
  echo.
  echo El programa termino con errores. Revisa el mensaje de arriba.
  pause
)
