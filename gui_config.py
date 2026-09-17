"""GUI para gestionar varias tareas de login automático (URL + credenciales +
programación), cada una registrable como su propia tarea programada de Windows.

Guarda las tareas cifradas (DPAPI) en %LOCALAPPDATA%\\AutoLogin\\tasks.json.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from tkinter import filedialog, messagebox, ttk

import config_store
from version import __version__ as APP_VERSION, GITHUB_REPO

# Lógica pura (validaciones, formatos) vive en app_logic para poder testearla
# sin Tkinter; aquí se re-exporta para mantener compatibilidad.
from app_logic import (
    _EXPORT_FIELDS,
    _NET_DATE_RE,
    _parse_int_safe,
    _parse_sha256_file,
    _parse_version,
    _sha256_of_file,
    _validity_display,
    _date_sort_key,
    _days_display,
    _format_net_date,
    _is_valid_url,
    _last_result_display,
    _normalize_iso_date,
    _normalize_schedule_days,
    _normalize_schedule_time,
    DAY_LABELS,
    DAYS,
    check_for_update,
)

try:
    import pystray
    from PIL import Image as PILImage
except Exception:
    pystray = None
    PILImage = None

try:
    from win11toast import toast as _tray_toast
except Exception:
    _tray_toast = None

FONT = "Segoe UI"
TITLE_FONT_SIZE = 17
SECTION_FONT_SIZE = 10
FIELD_FONT_SIZE = 9
BASE_FONT_SIZE = 10

# Paleta de colores: se rellena en tiempo de ejecución según el tema claro/oscuro
# de Windows (ver _detect_windows_dark_mode / _apply_palette), pero se definen
# aquí con valores de tema claro por defecto para que el módulo sea importable
# sin haber llamado antes a _apply_palette().
BG = "#edf1f5"
CARD_BG = "#ffffff"
INNER_BG = "#f4f6fa"
BORDER = "#dfe6ee"
BORDER_STRONG = "#cbd5e1"
TEXT = "#1e293b"
MUTED = "#64748b"
ACCENT = "#0d9488"
ACCENT_DARK = "#0f766e"
ACCENT_LIGHT = "#ccfbf1"
ACCENT_SOFT = "#e6f7f4"
HEADER_BG = "#0f766e"
HEADER_FG = "#ffffff"
HEADER_MUTED = "#cbf3ec"
SUCCESS = "#0f7d3c"
SUCCESS_BG = "#e5f6ec"
DANGER = "#b3261e"
DANGER_LIGHT = "#fdecea"
INFO_BG = "#e8f1fe"
INFO_FG = "#1d4ed8"
SECONDARY_BG = "#e8efed"
SECONDARY_HOVER = "#dbe7e4"
SECONDARY_PRESS = "#c9dcd8"
DISABLED_BG = "#a9d9d2"
DISABLED_FG = "#eafaf7"
ZEBRA_BG = "#f8fafc"
FOCUS_RING = "#0d9488"


def _detect_windows_dark_mode() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return False


# --- Arranque automático con Windows (HKCU\...\Run) ---

_STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_VALUE_NAME = "aLoguear"


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --start-minimized'
    script = os.path.abspath(__file__)
    pythonw = sys.executable
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(candidate):
        pythonw = candidate
    return f'"{pythonw}" "{script}" --start-minimized'


def is_startup_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_REG_PATH) as key:
            winreg.QueryValueEx(key, _STARTUP_VALUE_NAME)
        return True
    except Exception:
        return False


def set_startup_enabled(enabled: bool) -> None:
    import winreg
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _STARTUP_REG_PATH, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(key, _STARTUP_VALUE_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, _STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass


def _apply_palette(dark: bool) -> None:
    global BG, CARD_BG, INNER_BG, BORDER, BORDER_STRONG, TEXT, MUTED, ACCENT, ACCENT_DARK, ACCENT_LIGHT
    global ACCENT_SOFT, HEADER_BG, HEADER_FG, HEADER_MUTED
    global SUCCESS, SUCCESS_BG, DANGER, DANGER_LIGHT, INFO_BG, INFO_FG
    global SECONDARY_BG, SECONDARY_HOVER, SECONDARY_PRESS
    global DISABLED_BG, DISABLED_FG, ZEBRA_BG, FOCUS_RING
    if dark:
        BG = "#12161f"
        CARD_BG = "#1d2330"
        INNER_BG = "#262e40"
        BORDER = "#333c52"
        BORDER_STRONG = "#45506b"
        TEXT = "#e8edf7"
        MUTED = "#94a3b8"
        ACCENT = "#2dd4bf"
        ACCENT_DARK = "#5eead4"
        ACCENT_LIGHT = "#163b38"
        ACCENT_SOFT = "#1a2e2d"
        HEADER_BG = "#0d2b29"
        HEADER_FG = "#f0fdfa"
        HEADER_MUTED = "#8fd0c7"
        SUCCESS = "#4ade80"
        SUCCESS_BG = "#143326"
        DANGER = "#f87171"
        DANGER_LIGHT = "#3a2427"
        INFO_BG = "#1a2b4d"
        INFO_FG = "#93c5fd"
        SECONDARY_BG = "#2b3a39"
        SECONDARY_HOVER = "#33443f"
        SECONDARY_PRESS = "#3b4f4a"
        DISABLED_BG = "#1f4542"
        DISABLED_FG = "#5f7d78"
        ZEBRA_BG = "#222a3c"
        FOCUS_RING = "#2dd4bf"
    else:
        BG = "#edf1f5"
        CARD_BG = "#ffffff"
        INNER_BG = "#f4f6fa"
        BORDER = "#dfe6ee"
        BORDER_STRONG = "#cbd5e1"
        TEXT = "#1e293b"
        MUTED = "#64748b"
        ACCENT = "#0d9488"
        ACCENT_DARK = "#0f766e"
        ACCENT_LIGHT = "#ccfbf1"
        ACCENT_SOFT = "#e6f7f4"
        HEADER_BG = "#0f766e"
        HEADER_FG = "#ffffff"
        HEADER_MUTED = "#cbf3ec"
        SUCCESS = "#0f7d3c"
        SUCCESS_BG = "#e5f6ec"
        DANGER = "#b3261e"
        DANGER_LIGHT = "#fdecea"
        INFO_BG = "#e8f1fe"
        INFO_FG = "#1d4ed8"
        SECONDARY_BG = "#e8efed"
        SECONDARY_HOVER = "#dbe7e4"
        SECONDARY_PRESS = "#c9dcd8"
        DISABLED_BG = "#a9d9d2"
        DISABLED_FG = "#eafaf7"
        ZEBRA_BG = "#f8fafc"
        FOCUS_RING = "#0d9488"


# (Definidos en app_logic; se importan arriba para uso y re-export.)
# Espera a que este proceso (aLoguear.exe) termine, copia los archivos nuevos
# encima de los actuales (reintentando mientras el .exe siga bloqueado) y
# vuelve a abrir la app. Se lanza desprendido justo antes de cerrar la app.
# Todo queda registrado en update.log junto al .exe; si la copia fracasa se
# crea update.failed para avisar en el próximo arranque (nada es silencioso).
_UPDATE_BAT_TEMPLATE = """@echo off
setlocal EnableDelayedExpansion

set "ULOG={log}"
set "UFLAG={flag}"

echo [%date% %time%] Actualizador iniciado. Esperando fin del proceso {pid}... > "%ULOG%"

:waitloop
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)
echo [%date% %time%] Proceso terminado. Copiando archivos... >> "%ULOG%"

set RETRIES=0
:copyloop
copy /y "{src}\\aLoguear.exe" "{dest}\\aLoguear.exe" >> "%ULOG%" 2>&1
if errorlevel 1 (
    set /a RETRIES+=1
    echo [%date% %time%] aLoguear.exe bloqueado, reintento !RETRIES!/{retries}... >> "%ULOG%"
    if !RETRIES! GEQ {retries} goto giveup
    timeout /t 1 /nobreak >nul
    goto copyloop
)

copy /y "{src}\\aLoguear-runner.exe" "{dest}\\aLoguear-runner.exe" >> "%ULOG%" 2>&1
if errorlevel 1 echo [%date% %time%] AVISO: no se pudo copiar aLoguear-runner.exe (puede estar en uso por una tarea). >> "%ULOG%"
copy /y "{src}\\register_task.ps1" "{dest}\\register_task.ps1" >> "%ULOG%" 2>&1
copy /y "{src}\\unregister_task.ps1" "{dest}\\unregister_task.ps1" >> "%ULOG%"
copy /y "{src}\\list_next_runs.ps1" "{dest}\\list_next_runs.ps1" >> "%ULOG%" 2>&1

echo [%date% %time%] Copia OK. Reiniciando la app... >> "%ULOG%"
del "%UFLAG%" 2>nul
start "" "{dest}\\aLoguear.exe"
goto :eof

:giveup
echo [%date% %time%] ERROR: no se pudo copiar aLoguear.exe tras {retries} intentos; no se aplica la actualizacion. >> "%ULOG%"
echo error > "%UFLAG%"
"""

_UPDATE_MAX_COPY_RETRIES = 30


def _update_log_path() -> str:
    """Ruta del registro del actualizador, junto al .exe instalado."""
    return os.path.join(_script_dir_global(), "update.log")


def _update_failed_flag_path() -> str:
    """Fichero que deja el .bat si no pudo aplicar la actualización."""
    return os.path.join(_script_dir_global(), "update.failed")


def _read_update_log_tail(max_lines: int = 12) -> str:
    try:
        with open(_update_log_path(), "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:]).strip()
    except OSError:
        return ""


# (Definidos en app_logic; se importan arriba para uso y re-export.)
class ToolTip:
    """Tooltip flotante que aparece al pasar el ratón sobre un widget.

    Se reposiciona para no salirse de la ventana de la aplicación (ni por la
    derecha/abajo ni por la izquierda/arriba), en vez de simplemente aparecer
    pegada al widget y quedar cortada o fuera de la vista.
    """

    DELAY_MS = 450

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if self.tip_window is not None or not self.text:
            return
        tw = tk.Toplevel(self.widget)
        self.tip_window = tw
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        # Tooltip adaptado al tema para que se lea bien en claro y oscuro.
        try:
            is_dark = _detect_windows_dark_mode() if "_detect_windows_dark_mode" in globals() else False
        except Exception:
            is_dark = False
        # Se infiere el tema por el fondo actual de la app.
        dark_active = BG.startswith("#1") or BG.startswith("#0")
        bg = "#1e293b" if not dark_active else "#f1f5f9"
        fg = "#f8fafc" if not dark_active else "#0f172a"
        label = tk.Label(
            tw, text=self.text, justify="left", background=bg, foreground=fg,
            font=(FONT, 9), padx=9, pady=6, wraplength=260,
            borderwidth=1, relief="solid",
        )
        try:
            label.configure(highlightbackground=BORDER_STRONG)
        except Exception:
            pass
        label.pack()
        tw.update_idletasks()

        root = self.widget.winfo_toplevel()
        win_left = root.winfo_rootx()
        win_top = root.winfo_rooty()
        win_right = win_left + root.winfo_width()
        win_bottom = win_top + root.winfo_height()
        tip_w = tw.winfo_reqwidth()
        tip_h = tw.winfo_reqheight()

        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2 - tip_w // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

        # No dejar que se salga de la ventana de la app por ningún lado.
        x = max(win_left, min(x, win_right - tip_w))
        if y + tip_h > win_bottom:
            y = self.widget.winfo_rooty() - tip_h - 6  # mostrarla encima del widget
        y = max(win_top, min(y, win_bottom - tip_h))

        tw.wm_geometry(f"+{x}+{y}")

    def _hide(self, _event=None):
        self._cancel()
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None


APP_NAME = "aLoguear"
if getattr(sys, "frozen", False):
    ASSETS_DIR = os.path.join(sys._MEIPASS, "assets")
else:
    ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _script_dir_global() -> str:
    """Directorio donde viven los .ps1 (y, en modo empaquetado, los .exe
    hermanos): junto al .exe si está congelado, o junto a este .py si no."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _unblock_ps_scripts(script_dir: str) -> None:
    """Quita la marca "descargado de Internet" (Zone.Identifier) de los .ps1
    junto al ejecutable. Si no se quita, la directiva RemoteSigned que suele
    venir forzada por GPO bloquea su ejecución aunque se lancen con
    -ExecutionPolicy Bypass: esa directiva de Machine/GPO tiene prioridad
    sobre el flag pasado por línea de comandos."""
    for name in ("register_task.ps1", "unregister_task.ps1", "list_next_runs.ps1"):
        try:
            os.remove(os.path.join(script_dir, name) + ":Zone.Identifier")
        except OSError:
            pass


def _runner_command(*args) -> list:
    """Comando para ejecutar run_login.py, tanto en modo desarrollo (con
    Python) como empaquetado (usa el .exe hermano aLoguear-runner.exe)."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        return [os.path.join(exe_dir, "aLoguear-runner.exe"), *args]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return [sys.executable, os.path.join(script_dir, "run_login.py"), *args]


def _runner_cwd() -> str:
    """Directorio de trabajo correcto para el runner (el del proyecto/scripts,
    no el del intérprete de Python)."""
    return _script_dir_global()


# (Validaciones y formatos puros definidos en app_logic; importados arriba.)
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        # Nitidez en pantallas HiDPI de Windows.
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            self.tk.call("tk", "scaling", 1.15)
        except Exception:
            pass
        self.title(f"{APP_NAME} v{APP_VERSION} — Gestor de accesos automáticos")
        self.resizable(True, True)
        self.minsize(600, 680)

        self.current_task_id = None
        self.tray_icon = None
        self._tray_hint_shown = False

        _unblock_ps_scripts(_script_dir_global())

        self._setup_style()
        self.configure(bg=BG)
        self._set_app_icon()
        self.protocol("WM_DELETE_WINDOW", self._on_close_button)

        # --- Cabecera ---
        header = ttk.Frame(self, style="Header.TFrame")
        header.pack(fill="x")
        top_row = ttk.Frame(header, style="Header.TFrame")
        top_row.pack(fill="x", padx=22, pady=(18, 0))
        top_row.grid_columnconfigure(0, weight=1)

        header_left = ttk.Frame(top_row, style="Header.TFrame")
        header_left.grid(row=0, column=0, sticky="w")
        if self._logo_img is not None:
            logo_lbl = ttk.Label(header_left, image=self._logo_img, style="Header.TFrame")
            logo_lbl.pack(side="left", padx=(0, 12))
        title_box = ttk.Frame(header_left, style="Header.TFrame")
        title_box.pack(side="left")
        title_row = ttk.Frame(title_box, style="Header.TFrame")
        title_row.pack(anchor="w")
        ttk.Label(title_row, text=APP_NAME, style="Header.TLabel").pack(side="left")
        ttk.Label(
            title_row, text=f"  v{APP_VERSION}  ", style="Version.TLabel"
        ).pack(side="left", padx=(10, 0), pady=(3, 0))
        ttk.Label(
            title_box, text="Accesos web automáticos · tareas programadas de Windows",
            style="SubHeader.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        settings_btn = ttk.Button(
            top_row, text="⚙  Configuración", style="HeaderIcon.TButton",
            command=self.open_settings,
        )
        settings_btn.grid(row=0, column=1, sticky="e", padx=(12, 0))
        ToolTip(settings_btn, "Configuración de la app (tema, arranque, notificaciones, datos).")

        # Franja de aire bajo la cabecera para separarla del contenido.
        spacer = ttk.Frame(header, style="Header.TFrame")
        spacer.pack(fill="x", pady=(14, 0))

        # --- Aviso de actualización disponible (oculto hasta comprobarlo) ---
        self.update_banner = ttk.Frame(self, style="UpdateBanner.TFrame")
        self._update_url = None
        self._update_asset_url = None
        self._update_sha_url = None
        self.update_label = ttk.Label(self.update_banner, text="", style="UpdateBanner.TLabel")
        self.update_label.pack(side="left", padx=(16, 8), pady=6)
        self.update_now_btn = ttk.Button(
            self.update_banner, text="⬇  Actualizar ahora", style="UpdateBanner.TButton",
            command=self._start_update_download,
        )
        self.update_now_btn.pack(side="left", padx=(0, 6))
        self.update_link_btn = ttk.Button(
            self.update_banner, text="Ver novedades", style="UpdateBannerLink.TButton",
            command=lambda: webbrowser.open(self._update_url) if self._update_url else None,
        ).pack(side="left")
        self.after(800, self._start_update_check)
        self.after(1500, self._check_failed_update)

        # --- Contenedor con scroll (para que la ventana no dependa de caber
        #     entera en pantalla) ---
        scroll_container = ttk.Frame(self, style="TFrame")
        scroll_container.pack(fill="both", expand=True)
        self.scroll_container = scroll_container

        canvas = tk.Canvas(scroll_container, bg=BG, highlightthickness=0)
        self.canvas = canvas
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        outer = ttk.Frame(canvas, padding=(20, 18, 20, 18), style="TFrame")
        outer_window = canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.grid_columnconfigure(0, weight=1)

        def _on_outer_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(outer_window, width=event.width)

        outer.bind("<Configure>", _on_outer_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        row = 0

        # --- Lista de tareas guardadas ---
        list_card = ttk.Labelframe(outer, text="  ①  Tareas guardadas  ", style="Card.TLabelframe", padding=16)
        list_card.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        row += 1
        list_card.grid_columnconfigure(0, weight=1)

        add_row = ttk.Frame(list_card, style="Card.TFrame")
        add_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        add_row.grid_columnconfigure(0, weight=1)

        search_row = ttk.Frame(add_row, style="Card.TFrame")
        search_row.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        search_row.grid_columnconfigure(1, weight=1)
        ttk.Label(search_row, text="🔍", style="Card.TLabel").grid(row=0, column=0, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_task_list())
        search_entry = ttk.Entry(
            search_row, textvariable=self.search_var, style="Search.TEntry",
        )
        search_entry.grid(row=0, column=1, sticky="ew")
        ToolTip(search_entry, "Filtrar la lista por nombre o URL.")
        self._search_placeholder = "Buscar por nombre o URL…"
        self._search_has_placeholder = False

        def _search_focus_in(_e=None):
            if self._search_has_placeholder:
                search_entry.delete(0, "end")
                search_entry.configure(foreground=TEXT)
                self._search_has_placeholder = False

        def _search_focus_out(_e=None):
            if not self.search_var.get():
                search_entry.insert(0, self._search_placeholder)
                self._search_has_placeholder = True

        search_entry.bind("<FocusIn>", _search_focus_in)
        search_entry.bind("<FocusOut>", _search_focus_out)
        _search_focus_out()

        # El placeholder no debe filtrar: se ignora en _refresh_task_list().
        orig_get = self.search_var.get

        def _search_get(*a, **k):
            val = orig_get(*a, **k)
            if self._search_has_placeholder and val == self._search_placeholder:
                return ""
            return val

        self.search_var.get = _search_get  # type: ignore[method-assign]

        list_btns = ttk.Frame(add_row, style="Card.TFrame")
        list_btns.grid(row=0, column=1, sticky="e")

        export_btn = ttk.Button(
            list_btns, text="⤓  Exportar", style="IconGhost.TButton", command=self.on_export_tasks
        )
        export_btn.pack(side="left", padx=(0, 6))
        ToolTip(export_btn, "Exportar todas las tareas a un archivo (para respaldo o mover a otro equipo).")

        import_btn = ttk.Button(
            list_btns, text="⤒  Importar", style="IconGhost.TButton", command=self.on_import_tasks
        )
        import_btn.pack(side="left", padx=(0, 6))
        ToolTip(import_btn, "Importar tareas desde un archivo exportado antes.")

        add_btn = ttk.Button(
            list_btns, text="＋  Nueva tarea", style="AccentSmall.TButton", command=self.on_new_task
        )
        add_btn.pack(side="left")
        ToolTip(add_btn, "Limpia el formulario para crear una tarea nueva desde cero.")

        self.tree = ttk.Treeview(
            list_card, columns=("time", "days", "validity", "last", "next"), show="tree headings", height=6,
            selectmode="extended", style="Card.Treeview"
        )
        self._sort_column = None
        self._sort_reverse = False
        self.tree.heading("#0", text="NOMBRE", command=lambda: self._sort_tree("#0"))
        self.tree.heading("time", text="HORA", command=lambda: self._sort_tree("time"))
        self.tree.heading("days", text="DÍAS", command=lambda: self._sort_tree("days"))
        self.tree.heading("validity", text="VIGENCIA", command=lambda: self._sort_tree("validity"))
        self.tree.heading("last", text="ÚLTIMA", command=lambda: self._sort_tree("last"))
        self.tree.heading("next", text="PRÓXIMA", command=lambda: self._sort_tree("next"))
        self.tree.column("#0", width=170, minwidth=140, stretch=True)
        self.tree.column("time", width=58, minwidth=52, anchor="center", stretch=False)
        self.tree.column("days", width=92, minwidth=80, anchor="center", stretch=False)
        self.tree.column("validity", width=105, minwidth=95, anchor="center", stretch=False)
        self.tree.column("last", width=105, minwidth=95, anchor="center", stretch=False)
        self.tree.column("next", width=110, minwidth=100, anchor="center", stretch=False)
        self.tree.tag_configure("fail_row", background=DANGER_LIGHT)
        self.tree.tag_configure("paused_row", foreground=MUTED)
        self.tree.tag_configure("even_row", background=ZEBRA_BG)
        self.tree.tag_configure("ok_row", foreground=SUCCESS)

        tree_scroll_x = ttk.Scrollbar(list_card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=tree_scroll_x.set)
        self.tree.grid(row=1, column=0, sticky="ew")
        tree_scroll_x.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        # Atajos de la lista: Supr elimina, Ctrl+A selecciona todo, Esc limpia.
        # Se ligan al Treeview (no globales) para no robar Ctrl+A a los campos.
        self.tree.bind("<Delete>", self._on_list_delete_key)
        self.tree.bind("<Control-a>", self._on_list_select_all_key)
        self.tree.bind("<Control-A>", self._on_list_select_all_key)
        self.tree.bind("<Escape>", self._on_list_escape_key)

        self.list_count_var = tk.StringVar(value="")
        ttk.Label(list_card, textvariable=self.list_count_var, style="Count.TLabel").grid(
            row=3, column=0, sticky="w", pady=(8, 0)
        )

        self.empty_hint = ttk.Label(
            list_card,
            text="Sin tareas todavía.\nPulsa «＋ Nueva tarea», rellena el formulario y pulsa Guardar.",
            style="Muted.TLabel", justify="center",
        )

        # --- Acciones en lote (solo visible con 2+ tareas seleccionadas) ---
        self.batch_bar = ttk.Frame(list_card, style="Card.TFrame")
        self.batch_bar.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.batch_bar.grid_columnconfigure(0, weight=1)
        self.batch_label = ttk.Label(self.batch_bar, text="", style="Count.TLabel")
        self.batch_label.grid(row=0, column=0, sticky="w")
        batch_btns = ttk.Frame(self.batch_bar, style="Card.TFrame")
        batch_btns.grid(row=0, column=1, sticky="e")
        self.batch_activate_btn = ttk.Button(
            batch_btns, text="▶  Activar", style="IconGhost.TButton",
            command=self.on_batch_activate,
        )
        self.batch_activate_btn.pack(side="left", padx=(0, 6))
        ToolTip(self.batch_activate_btn, "Activar y programar en Windows las tareas seleccionadas.")
        self.batch_pause_btn = ttk.Button(
            batch_btns, text="⏸  Pausar", style="IconGhost.TButton",
            command=self.on_batch_pause,
        )
        self.batch_pause_btn.pack(side="left", padx=(0, 6))
        ToolTip(self.batch_pause_btn, "Pausar las tareas seleccionadas (quitan su tarea de Windows).")
        self.batch_delete_btn = ttk.Button(
            batch_btns, text="🗑  Eliminar", style="IconDanger.TButton",
            command=self.on_batch_delete,
        )
        self.batch_delete_btn.pack(side="left")
        ToolTip(self.batch_delete_btn, "Eliminar las tareas seleccionadas (atajo: Supr).")
        self.batch_bar.grid_remove()
        ttk.Label(
            list_card,
            text="Consejo: Ctrl+clic o Mayús+clic para elegir varias · Ctrl+A todas · Supr eliminar · Esc limpiar",
            style="Muted.TLabel",
        ).grid(row=6, column=0, sticky="w", pady=(6, 0))

        # --- Detalles de acceso ---
        form_card = ttk.Labelframe(outer, text="  ②  Detalles de acceso  ", style="Card.TLabelframe", padding=16)
        form_card.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        row += 1
        form_card.grid_columnconfigure(0, weight=1)

        frow = 0
        mode_row = ttk.Frame(form_card, style="Card.TFrame")
        mode_row.grid(row=frow, column=0, sticky="ew", pady=(0, 12))
        mode_row.grid_columnconfigure(0, weight=1)
        self.mode_label = ttk.Label(mode_row, text="＋  Nueva tarea", style="Mode.TLabel")
        self.mode_label.grid(row=0, column=0, sticky="w")
        self.mode_badge = ttk.Label(mode_row, text="SIN GUARDAR", style="ModeBadge.TLabel")
        self.mode_badge.grid(row=0, column=1, sticky="e", padx=(0, 8))
        self.log_btn = ttk.Button(
            mode_row, text="≣  Log", style="IconGhost.TButton", command=self.on_view_log
        )
        self.log_btn.grid(row=0, column=2, sticky="e", padx=(0, 6))
        ToolTip(self.log_btn, "Ver el registro (log) completo de esta tarea.")
        self.screenshot_btn = ttk.Button(
            mode_row, text="◉  Captura", style="IconGhost.TButton", command=self.on_view_screenshot
        )
        self.screenshot_btn.grid(row=0, column=3, sticky="e", padx=(0, 6))
        ToolTip(self.screenshot_btn, "Ver la última captura de pantalla guardada de un login fallido.")
        self.duplicate_btn = ttk.Button(
            mode_row, text="⧉  Duplicar", style="IconGhost.TButton", command=self.on_duplicate_task
        )
        self.duplicate_btn.grid(row=0, column=4, sticky="e", padx=(0, 6))
        ToolTip(self.duplicate_btn, "Duplicar esta tarea como una tarea nueva (sin guardar todavía).")
        self.delete_btn = ttk.Button(
            mode_row, text="🗑  Eliminar", style="IconDanger.TButton", command=self.on_delete_task
        )
        self.delete_btn.grid(row=0, column=5, sticky="e")
        ToolTip(self.delete_btn, "Eliminar esta tarea y su tarea programada de Windows.")
        frow += 1

        ttk.Label(form_card, text="NOMBRE DE LA TAREA", style="Field.TLabel").grid(
            row=frow, column=0, sticky="w", pady=(0, 4)
        )
        frow += 1
        self.name_var = tk.StringVar()
        ttk.Entry(form_card, textvariable=self.name_var).grid(row=frow, column=0, sticky="ew", pady=(0, 12))
        frow += 1

        ttk.Label(form_card, text="URL DE LA PÁGINA", style="Field.TLabel").grid(
            row=frow, column=0, sticky="w", pady=(0, 4)
        )
        frow += 1
        self.url_var = tk.StringVar()
        ttk.Entry(form_card, textvariable=self.url_var).grid(row=frow, column=0, sticky="ew", pady=(0, 12))
        frow += 1

        ttk.Label(form_card, text="USUARIO", style="Field.TLabel").grid(row=frow, column=0, sticky="w", pady=(0, 4))
        frow += 1
        self.user_var = tk.StringVar()
        ttk.Entry(form_card, textvariable=self.user_var).grid(row=frow, column=0, sticky="ew", pady=(0, 12))
        frow += 1

        ttk.Label(form_card, text="CONTRASEÑA", style="Field.TLabel").grid(
            row=frow, column=0, sticky="w", pady=(0, 4)
        )
        frow += 1
        pass_row = ttk.Frame(form_card, style="Card.TFrame")
        pass_row.grid(row=frow, column=0, sticky="ew", pady=(0, 2))
        pass_row.grid_columnconfigure(0, weight=1)
        self.pass_var = tk.StringVar()
        self.pass_entry = ttk.Entry(pass_row, textvariable=self.pass_var, show="•")
        self.pass_entry.grid(row=0, column=0, sticky="ew")
        self.show_pass_var = tk.BooleanVar(value=False)
        self.show_pass_btn = ttk.Button(
            pass_row, text="Mostrar", style="IconGhost.TButton",
            command=self._toggle_password_button,
        )
        self.show_pass_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))
        ToolTip(self.show_pass_btn, "Mostrar / ocultar la contraseña.")
        frow += 1
        frow += 1

        self.active_var = tk.BooleanVar(value=True)
        active_chk = ttk.Checkbutton(
            form_card, text="Tarea activa  ·  se programa en Windows",
            variable=self.active_var, style="Card.TCheckbutton"
        )
        active_chk.grid(row=frow, column=0, sticky="w", pady=(8, 3))
        ToolTip(
            active_chk,
            "Si la desactivas, se quita la tarea programada de Windows pero se conserva "
            "toda la configuración guardada para poder reactivarla más adelante.",
        )
        frow += 1

        self.headless_var = tk.BooleanVar(value=True)
        headless_chk = ttk.Checkbutton(
            form_card, text="Ejecutar en segundo plano (sin ventana visible)",
            variable=self.headless_var, style="Card.TCheckbutton"
        )
        headless_chk.grid(row=frow, column=0, sticky="w", pady=(0, 3))
        ToolTip(
            headless_chk,
            "Si está marcado, el navegador no se muestra en pantalla al ejecutar la tarea.\n"
            "Desmárcalo para verlo mientras ajustas o pruebas los selectores.",
        )
        frow += 1

        self.keep_alive_var = tk.BooleanVar(value=False)
        keep_alive_chk = ttk.Checkbutton(
            form_card, text="Mantener la sesión activa tras iniciar sesión",
            variable=self.keep_alive_var, style="Card.TCheckbutton",
            command=self._toggle_keep_alive
        )
        keep_alive_chk.grid(row=frow, column=0, sticky="w", pady=(0, 3))
        ToolTip(
            keep_alive_chk,
            "Tras iniciar sesión, recarga la página periódicamente para evitar que el "
            "sitio cierre la sesión por inactividad (y reintenta el login si caduca).\n"
            "Ojo: duración 0:00 = indefinido, el runner queda vivo para siempre y ocupa "
            "su tarea programada.",
        )
        frow += 1
        self._keep_alive_row = frow
        frow += 1

        self.keep_alive_frame = ttk.Labelframe(
            form_card, text="  Mantener sesión  ", style="Inner.TLabelframe", padding=12
        )
        self.keep_alive_frame.grid_columnconfigure(0, weight=1)
        ttk.Label(self.keep_alive_frame, text="Refrescar cada", style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.keep_alive_interval_var = tk.StringVar(value="5")
        ttk.Spinbox(
            self.keep_alive_frame, from_=1, to=120, width=5, textvariable=self.keep_alive_interval_var
        ).grid(row=0, column=1, padx=(8, 6))
        ttk.Label(self.keep_alive_frame, text="min", style="Card.TLabel").grid(
            row=0, column=2, sticky="w"
        )

        ttk.Label(self.keep_alive_frame, text="Dejar de mantenerla tras", style="Card.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )
        duration_row = ttk.Frame(self.keep_alive_frame, style="Card.TFrame")
        duration_row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.keep_alive_duration_hour_var = tk.StringVar(value="01")
        ttk.Spinbox(
            duration_row, from_=0, to=23, width=4, format="%02.0f",
            textvariable=self.keep_alive_duration_hour_var, wrap=True
        ).grid(row=0, column=0)
        ttk.Label(duration_row, text=":", style="Card.TLabel").grid(row=0, column=1, padx=4)
        self.keep_alive_duration_min_var = tk.StringVar(value="00")
        ttk.Spinbox(
            duration_row, from_=0, to=59, width=4, format="%02.0f",
            textvariable=self.keep_alive_duration_min_var, wrap=True
        ).grid(row=0, column=2)
        ttk.Label(duration_row, text="h : min   ·   0:00 = indefinido", style="Muted.TLabel").grid(
            row=0, column=3, sticky="w", padx=(10, 0)
        )

        ttk.Label(
            self.keep_alive_frame, text="PÁGINA DE TRABAJO (OPCIONAL)", style="Field.TLabel"
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.keep_alive_url_var = tk.StringVar(value="")
        ka_url_entry = ttk.Entry(self.keep_alive_frame, textvariable=self.keep_alive_url_var)
        ka_url_entry.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        ToolTip(
            ka_url_entry,
            "Tras iniciar sesión, abrir este enlace y mantener la sesión en él "
            "(p. ej. la página del curso o panel que te interesa).\n"
            "Vacío = quedarse en la página del login.",
        )
        ttk.Label(
            self.keep_alive_frame, text="https://…  ·  vacío = página del login",
            style="Muted.TLabel",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        # self.keep_alive_frame se muestra/oculta con _toggle_keep_alive(); empieza oculto.

        self.adv_expanded = tk.BooleanVar(value=False)
        self.adv_toggle_btn = ttk.Button(
            form_card, text="▸  Avanzado (opcional): selectores CSS", style="Link.TButton",
            command=self._toggle_advanced
        )
        self.adv_toggle_btn.grid(row=frow, column=0, sticky="w", pady=(10, 0))
        ToolTip(
            self.adv_toggle_btn,
            "Indica manualmente los selectores CSS del formulario de login si la "
            "detección automática no encuentra bien los campos o el botón.",
        )
        frow += 1
        self._adv_row = frow
        frow += 1

        self.adv = ttk.Labelframe(form_card, text="  Selectores CSS  ", style="Inner.TLabelframe", padding=12)
        self.adv.grid_columnconfigure(1, weight=1)

        ttk.Label(self.adv, text="Campo usuario", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        self.user_sel_var = tk.StringVar()
        ttk.Entry(self.adv, textvariable=self.user_sel_var).grid(row=0, column=1, sticky="ew", pady=5)

        ttk.Label(self.adv, text="Campo contraseña", style="Field.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        self.pass_sel_var = tk.StringVar()
        ttk.Entry(self.adv, textvariable=self.pass_sel_var).grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Label(self.adv, text="Botón enviar", style="Field.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        self.submit_sel_var = tk.StringVar()
        ttk.Entry(self.adv, textvariable=self.submit_sel_var).grid(row=2, column=1, sticky="ew", pady=5)

        ttk.Label(
            self.adv, text="Vacío = detección automática. Solo rellena si la web no se detecta bien.",
            style="Muted.TLabel"
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        # self.adv se muestra/oculta con _toggle_advanced(); empieza contraído.

        # --- Programación ---
        sched = ttk.Labelframe(outer, text="  ③  Programación  ", style="Card.TLabelframe", padding=16)
        sched.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        row += 1
        sched.grid_columnconfigure(1, weight=1)

        ttk.Label(sched, text="HORA", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        time_frame = ttk.Frame(sched, style="Card.TFrame")
        time_frame.grid(row=0, column=1, sticky="w")
        self.hour_var = tk.StringVar(value="08")
        self.minute_var = tk.StringVar(value="00")
        ttk.Spinbox(
            time_frame, from_=0, to=23, width=4, format="%02.0f",
            textvariable=self.hour_var, wrap=True
        ).grid(row=0, column=0)
        ttk.Label(time_frame, text=":", style="Card.TLabel").grid(row=0, column=1, padx=4)
        ttk.Spinbox(
            time_frame, from_=0, to=59, width=4, format="%02.0f",
            textvariable=self.minute_var, wrap=True
        ).grid(row=0, column=2)
        ttk.Label(time_frame, text="24 h", style="Muted.TLabel").grid(row=0, column=3, padx=(10, 0))

        ttk.Label(sched, text="DÍAS", style="Field.TLabel").grid(row=1, column=0, sticky="nw", padx=(0, 12), pady=(14, 0))
        days_frame = ttk.Frame(sched, style="Card.TFrame")
        days_frame.grid(row=1, column=1, sticky="w", pady=(14, 0))
        self.day_vars = {}
        for i, (label, day_name) in enumerate(DAYS):
            var = tk.BooleanVar(value=True)
            self.day_vars[day_name] = var
            ttk.Checkbutton(
                days_frame, text=label, variable=var, style="Day.TCheckbutton"
            ).grid(row=0, column=i, padx=(0, 6) if i < len(DAYS) - 1 else (0, 0))

        ttk.Label(sched, text="VIGENCIA", style="Field.TLabel").grid(
            row=2, column=0, sticky="nw", padx=(0, 12), pady=(14, 0)
        )
        validity_frame = ttk.Frame(sched, style="Card.TFrame")
        validity_frame.grid(row=2, column=1, sticky="w", pady=(14, 0))
        self.start_date_var = tk.StringVar(value="")
        self.end_date_var = tk.StringVar(value="")
        start_entry = ttk.Entry(validity_frame, textvariable=self.start_date_var, width=14)
        start_entry.grid(row=0, column=0)
        ToolTip(start_entry, "Fecha de inicio (YYYY-MM-DD). Vacío = sin límite.")
        ttk.Label(validity_frame, text="→", style="Card.TLabel").grid(row=0, column=1, padx=6)
        end_entry = ttk.Entry(validity_frame, textvariable=self.end_date_var, width=14)
        end_entry.grid(row=0, column=2)
        ToolTip(end_entry, "Fecha de fin (YYYY-MM-DD). Vacío = sin límite.")
        ttk.Label(
            validity_frame, text="Formato YYYY-MM-DD · vacío = siempre vigente",
            style="Muted.TLabel"
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        ttk.Label(sched, text="Vigencia", style="Card.TLabel").grid(
            row=2, column=0, sticky="nw", padx=(0, 8), pady=(10, 0)
        )
        validity_frame = ttk.Frame(sched, style="Card.TFrame")
        validity_frame.grid(row=2, column=1, sticky="w", pady=(10, 0))
        self.start_date_var = tk.StringVar(value="")
        self.end_date_var = tk.StringVar(value="")
        start_entry = ttk.Entry(validity_frame, textvariable=self.start_date_var, width=12)
        start_entry.grid(row=0, column=0)
        ToolTip(start_entry, "Fecha de inicio (YYYY-MM-DD). Vacío = sin límite.")
        ttk.Label(validity_frame, text="→", style="Card.TLabel").grid(row=0, column=1, padx=5)
        end_entry = ttk.Entry(validity_frame, textvariable=self.end_date_var, width=12)
        end_entry.grid(row=0, column=2)
        ToolTip(end_entry, "Fecha de fin (YYYY-MM-DD). Vacío = sin límite.")
        ttk.Label(
            validity_frame, text="YYYY-MM-DD, vacío = siempre vigente",
            style="Muted.TLabel"
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # --- Guardar / Probar ---
        action_card = ttk.Labelframe(outer, text="  ④  Acciones  ", style="Card.TLabelframe", padding=16)
        action_card.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        row += 1
        action_card.grid_columnconfigure(0, weight=1)
        btn_frame = ttk.Frame(action_card, style="Card.TFrame")
        btn_frame.grid(row=0, column=0, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        btn_frame.grid_columnconfigure(2, weight=1)

        self.save_btn = ttk.Button(
            btn_frame, text="💾  Guardar y programar", style="Accent.TButton", command=self.on_save
        )
        self.save_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ToolTip(self.save_btn, "Guarda esta tarea y crea/actualiza su tarea programada en Windows.")
        self.test_btn = ttk.Button(
            btn_frame, text="▶  Probar ahora", style="Secondary.TButton", command=self.on_test
        )
        self.test_btn.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ToolTip(self.test_btn, "Guarda esta tarea y ejecuta un login de prueba ahora mismo.")
        self.detect_btn = ttk.Button(
            btn_frame, text="🔍  Solo detectar", style="Secondary.TButton", command=self.on_detect_only
        )
        self.detect_btn.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ToolTip(
            self.detect_btn,
            "Comprueba si encuentra los campos de usuario/contraseña/botón SIN enviar "
            "nada (útil para validar selectores en un sitio nuevo sin arriesgarte a un "
            "bloqueo por intento de login fallido).",
        )

        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(
            action_card, textvariable=self.status_var, style="Info.TLabel",
            wraplength=560, justify="left",
        )
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self._status_visible = False
        self.status_label.grid_remove()
        row += 1

        # --- Pie ---
        footer = ttk.Frame(self, style="Footer.TFrame", padding=(20, 8, 20, 10))
        footer.pack(fill="x", side="bottom")
        self.footer_status_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.footer_status_var, style="Footer.TLabel").pack(side="left")
        ttk.Label(footer, text=f"v{APP_VERSION}", style="Footer.TLabel").pack(side="right")
        self.footer_status_var.set("Listo")

        self._refresh_task_list()
        self._clear_form()

        self.update_idletasks()
        # Ventana centrada y con tamaño inicial generoso pero acotado a la pantalla.
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        content_width = outer.winfo_reqwidth() + scrollbar.winfo_reqwidth() + 8
        win_w = max(640, min(content_width + 40, screen_w - 60, 760))
        content_height = outer.winfo_reqheight()
        win_h = max(640, min(content_height + 170, screen_h - 80, 920))
        pos_x = max(0, (screen_w - win_w) // 2)
        pos_y = max(0, (screen_h - win_h) // 2 - 20)
        self.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

    # --- Icono ---

    def _apply_titlebar_theme(self):
        """Oscurece la barra de título nativa de Windows si toca tema oscuro
        (si no, se queda blanca aunque el resto de la ventana esté oscuro)."""
        if not self.is_dark:
            return
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (20 en Win10 2004+, 19 en versiones previas)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
        except Exception:
            pass

    def _set_app_icon(self):
        self._logo_img = None
        ico_path = os.path.join(ASSETS_DIR, "icon.ico")
        png_path = os.path.join(ASSETS_DIR, "icon_48.png")
        try:
            if os.path.exists(ico_path):
                self.iconbitmap(ico_path)
        except tk.TclError:
            pass
        try:
            if os.path.exists(png_path):
                self._logo_img = tk.PhotoImage(file=png_path)
                self.iconphoto(True, self._logo_img)
        except tk.TclError:
            pass

    # --- Bandeja del sistema ---

    def _on_close_button(self):
        close_action = config_store.load_settings().get("close_action", "tray")
        if pystray is not None and close_action == "tray":
            self._minimize_to_tray()
        else:
            self.destroy()

    def _minimize_to_tray(self):
        self.withdraw()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            if _tray_toast is not None:
                try:
                    _tray_toast(
                        APP_NAME,
                        "Sigue ejecutándose en la bandeja del sistema. Clic derecho en su "
                        "icono para abrirla de nuevo o salir del todo.",
                        duration="short",
                    )
                except Exception:
                    pass
        if self.tray_icon is None:
            self._start_tray_icon()

    def _start_tray_icon(self):
        icon_path = os.path.join(ASSETS_DIR, "icon.png")
        try:
            image = PILImage.open(icon_path) if os.path.exists(icon_path) else PILImage.new(
                "RGBA", (64, 64), (79, 70, 229, 255)
            )
        except Exception:
            image = PILImage.new("RGBA", (64, 64), (79, 70, 229, 255))
        menu = pystray.Menu(
            pystray.MenuItem("Abrir aLoguear", self._tray_open, default=True),
            pystray.MenuItem("Salir", self._tray_quit),
        )
        self.tray_icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _tray_open(self, icon=None, item=None):
        self.after(0, self._restore_from_tray)

    def _restore_from_tray(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_quit(self, icon=None, item=None):
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        self.after(0, self.destroy)

    # --- Actualizaciones ---

    def _start_update_check(self):
        threading.Thread(target=self._run_update_check, daemon=True).start()

    def _run_update_check(self):
        result = check_for_update()
        if result:
            self.after(0, lambda: self._show_update_banner(*result))

    def _show_update_banner(self, latest_version: str, url: str, asset_url: str | None,
                              sha_url: str | None = None):
        self._update_url = url
        self._update_asset_url = asset_url
        self._update_sha_url = sha_url
        self.update_label.configure(text=f"🔔  Hay una nueva versión disponible: {latest_version} (tienes {APP_VERSION})")
        can_self_update = getattr(sys, "frozen", False) and asset_url
        if can_self_update:
            self.update_now_btn.pack(side="left", padx=(0, 6), before=self.update_link_btn)
        else:
            self.update_now_btn.pack_forget()
        self.update_banner.pack(fill="x", before=self.scroll_container)

    def _start_update_download(self):
        if not self._update_asset_url:
            return
        self.update_now_btn.configure(state="disabled", text="Descargando...")
        threading.Thread(target=self._download_and_apply_update, daemon=True).start()

    def _download_and_apply_update(self):
        try:
            tmp_dir = tempfile.mkdtemp(prefix="aloguear_update_")
            zip_path = os.path.join(tmp_dir, "update.zip")
            self.after(0, lambda: self.update_now_btn.configure(text="Descargando..."))
            req = urllib.request.Request(
                self._update_asset_url, headers={"User-Agent": "aLoguear-updater"}
            )
            with urllib.request.urlopen(req, timeout=600) as resp, open(zip_path, "wb") as f:
                shutil.copyfileobj(resp, f)

            # Verificación SHA256: bloquea la instalación si no coincide.
            expected_hash = None
            sha_url = getattr(self, "_update_sha_url", None)
            if sha_url:
                try:
                    sha_req = urllib.request.Request(
                        sha_url, headers={"User-Agent": "aLoguear-updater"}
                    )
                    with urllib.request.urlopen(sha_req, timeout=30) as resp:
                        expected_hash = _parse_sha256_file(resp.read().decode("utf-8", errors="ignore"))
                except Exception as exc:
                    raise RuntimeError(f"No se pudo obtener el hash SHA256 oficial: {exc}")
                if not expected_hash:
                    raise RuntimeError("El fichero .sha256 oficial no tiene un formato válido.")
                actual_hash = _sha256_of_file(zip_path)
                if actual_hash != expected_hash:
                    raise RuntimeError(
                        "El hash SHA256 descargado no coincide con el oficial. "
                        "Se bloquea la actualización por seguridad."
                    )
            else:
                raise RuntimeError(
                    "Este release no publica fichero .sha256; por seguridad no se aplica "
                    "la auto-actualización. Descárgala manual desde 'Ver novedades'."
                )

            extract_dir = os.path.join(tmp_dir, "extracted")
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(extract_dir)
            except zipfile.BadZipFile:
                raise RuntimeError(
                    "Lo descargado no es un .zip válido (¿corte de conexión?). "
                    "Reinténtalo o descárgalo a mano desde 'Ver novedades'."
                )
            if not os.path.exists(os.path.join(extract_dir, "aLoguear.exe")):
                for name in os.listdir(extract_dir):
                    sub = os.path.join(extract_dir, name)
                    if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "aLoguear.exe")):
                        extract_dir = sub
                        break
                else:
                    raise RuntimeError("El .zip descargado no contiene aLoguear.exe")
            if not os.path.exists(os.path.join(extract_dir, "aLoguear-runner.exe")):
                raise RuntimeError("El .zip descargado no contiene aLoguear-runner.exe")

            install_dir = os.path.dirname(sys.executable)
            # Comprobación de escritura ANTES de cerrar la app: si no podemos
            # escribir junto al .exe, avisamos ahora en vez de cerrar en vano.
            try:
                probe = os.path.join(install_dir, "update.write_test")
                with open(probe, "w", encoding="utf-8") as f:
                    f.write("ok")
                os.remove(probe)
            except OSError as exc:
                raise RuntimeError(
                    f"No hay permiso de escritura en la carpeta de instalación "
                    f"({install_dir}): {exc}. Ejecuta la app como administrador "
                    f"o descarga la nueva versión a mano desde 'Ver novedades'."
                )

            bat_path = os.path.join(tmp_dir, "update.bat")
            with open(bat_path, "w", encoding="mbcs") as f:
                f.write(_UPDATE_BAT_TEMPLATE.format(
                    pid=os.getpid(), src=extract_dir, dest=install_dir,
                    log=_update_log_path(), flag=_update_failed_flag_path(),
                    retries=_UPDATE_MAX_COPY_RETRIES,
                ))
            try:
                subprocess.Popen(
                    ["cmd.exe", "/c", bat_path],
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                )
            except Exception as exc:
                raise RuntimeError(f"No se pudo lanzar el instalador (update.bat): {exc}")
            self.after(0, lambda: self.update_now_btn.configure(text="Instalando..."))
            self.after(0, self._quit_for_update)
        except Exception as exc:
            self.after(0, lambda: self._update_download_failed(str(exc)))

    def _quit_for_update(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        try:
            self.destroy()
        except Exception:
            pass
        # Red de seguridad: destroy() no siempre termina el proceso (un hilo
        # o componente COM puede dejarlo colgado y entonces el .bat esperaría
        # eternamente sin instalar nada). Este vigilante garantiza la salida.
        threading.Thread(target=self._force_exit_watchdog, daemon=True).start()

    @staticmethod
    def _force_exit_watchdog():
        import time as _time
        _time.sleep(5)
        os._exit(0)

    def _update_download_failed(self, message: str):
        self.update_now_btn.configure(state="normal", text="⬇  Actualizar ahora")
        messagebox.showerror(
            "Error al actualizar",
            f"No se pudo descargar/aplicar la actualización automáticamente:\n{message}\n\n"
            "Puedes descargarla a mano desde 'Ver novedades'.",
        )

    def _check_failed_update(self):
        """Si el .bat de una actualización anterior dejó update.failed, avisa
        con el registro y ofrece la descarga manual. (Antes estos fallos eran
        totalmente silenciosos: la app se cerraba y no pasaba nada.)"""
        try:
            if not os.path.exists(_update_failed_flag_path()):
                return
        except Exception:
            return
        try:
            os.remove(_update_failed_flag_path())
        except OSError:
            pass
        detail = _read_update_log_tail(12)
        message = (
            "La actualización automática anterior no pudo aplicarse "
            "(normalmente porque el .exe estaba bloqueado o el antivirus la interceptó).\n"
            f"Tu versión actual sigue intacta: {APP_VERSION}.\n"
        )
        if detail:
            message += f"\nRegistro del instalador (update.log):\n{detail}\n"
        else:
            message += "\nNo hay registro (update.log) con más detalle.\n"
        message += "\n¿Abrir la página de descargas para actualizar a mano?"
        if messagebox.askyesno("Actualización no aplicada", message):
            webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")

    # --- Estilo ---

    def _resolve_dark_mode(self, setting: str) -> bool:
        if setting == "dark":
            return True
        if setting == "light":
            return False
        return _detect_windows_dark_mode()  # "auto" o valor desconocido

    def _setup_style(self):
        self.theme_setting = config_store.load_settings().get("theme", "auto")
        self.is_dark = self._resolve_dark_mode(self.theme_setting)
        self._build_style()
        self._apply_titlebar_theme()

    def set_theme(self, setting: str):
        """Cambia el tema en caliente (sin reiniciar) y lo recuerda para la
        próxima vez que se abra la app."""
        self.theme_setting = setting
        config_store.save_settings({"theme": setting})
        self.is_dark = self._resolve_dark_mode(setting)
        self._build_style()
        self._apply_titlebar_theme()
        self.configure(bg=BG)
        if getattr(self, "canvas", None) is not None:
            self.canvas.configure(bg=BG)
        if getattr(self, "tree", None) is not None:
            self.tree.tag_configure("fail_row", background=DANGER_LIGHT)
            self.tree.tag_configure("paused_row", foreground=MUTED)
            self.tree.tag_configure("even_row", background=ZEBRA_BG)
            self.tree.tag_configure("ok_row", foreground=SUCCESS)
        # Reaplicar el estado visible para que coja los nuevos colores.
        if getattr(self, "status_var", None) is not None and self.status_var.get():
            current_style = str(getattr(self.status_label, "cget", lambda *_: "")("style") or "")
            kind = "success" if "Success" in current_style else "danger" if "Danger" in current_style else "info"
            self._set_status(kind, self.status_var.get())

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title(f"{APP_NAME} — Configuración")
        win.resizable(False, False)
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        win.bind("<Escape>", lambda _e: win.destroy())

        body = ttk.Frame(win, style="TFrame", padding=18)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Configuración", style="Card.TLabel").pack(anchor="w")
        ttk.Label(
            body, text="Ajustes generales de la aplicación.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        card = ttk.Labelframe(body, text="  ◐  Apariencia  ", style="Card.TLabelframe", padding=14)
        card.pack(fill="x")

        ttk.Label(card, text="Tema", style="Card.TLabel").pack(anchor="w", pady=(0, 6))

        theme_var = tk.StringVar(value=getattr(self, "theme_setting", "auto"))

        def _pick(value):
            theme_var.set(value)
            self.set_theme(value)
            win.configure(bg=BG)
            body.configure(style="TFrame")

        for value, label in (
            ("auto", "Automático (según Windows)"),
            ("light", "Claro"),
            ("dark", "Oscuro"),
        ):
            ttk.Radiobutton(
                card, text=label, value=value, variable=theme_var,
                command=lambda v=value: _pick(v), style="Card.TRadiobutton",
            ).pack(anchor="w", pady=2)

        # --- Comportamiento ---
        settings = config_store.load_settings()
        behavior_card = ttk.Labelframe(
            body, text="  ⚙  Comportamiento  ", style="Card.TLabelframe", padding=14
        )
        behavior_card.pack(fill="x", pady=(12, 0))

        startup_var = tk.BooleanVar(value=is_startup_enabled())

        def _toggle_startup():
            try:
                set_startup_enabled(startup_var.get())
            except Exception as exc:
                messagebox.showerror(
                    "No se pudo cambiar el arranque automático",
                    f"No se pudo actualizar el registro de Windows:\n{exc}",
                )
                startup_var.set(is_startup_enabled())

        ttk.Checkbutton(
            behavior_card, text="Iniciar con Windows (minimizada en la bandeja)",
            variable=startup_var, style="Card.TCheckbutton", command=_toggle_startup,
        ).pack(anchor="w", pady=2)

        notif_var = tk.BooleanVar(value=settings.get("notifications_enabled", True))
        ttk.Checkbutton(
            behavior_card, text="Notificaciones de Windows si falla una tarea",
            variable=notif_var, style="Card.TCheckbutton",
            command=lambda: config_store.save_settings({"notifications_enabled": notif_var.get()}),
        ).pack(anchor="w", pady=2)

        ttk.Label(behavior_card, text="Al cerrar la ventana (✕)", style="Card.TLabel").pack(
            anchor="w", pady=(8, 2)
        )
        close_var = tk.StringVar(value=settings.get("close_action", "tray"))
        for value, label in (
            ("tray", "Minimizar a la bandeja del sistema"),
            ("exit", "Salir de la app"),
        ):
            ttk.Radiobutton(
                behavior_card, text=label, value=value, variable=close_var,
                style="Card.TRadiobutton",
                command=lambda: config_store.save_settings({"close_action": close_var.get()}),
            ).pack(anchor="w", pady=2)

        # --- Datos ---
        data_card = ttk.Labelframe(body, text="  🗂  Datos  ", style="Card.TLabelframe", padding=14)
        data_card.pack(fill="x", pady=(12, 0))

        ttk.Label(data_card, text="Tamaño máximo de cada log (MB)", style="Card.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        def _save_log_mb(*_args):
            try:
                config_store.save_settings({"log_max_mb": int(log_mb_var.get() or 2)})
            except ValueError:
                pass

        log_mb_var = tk.StringVar(value=str(settings.get("log_max_mb", 2)))
        log_mb_row = ttk.Frame(data_card, style="Card.TFrame")
        log_mb_row.pack(anchor="w", pady=(0, 10))
        log_mb_spin = ttk.Spinbox(
            log_mb_row, from_=1, to=50, width=5, textvariable=log_mb_var, command=_save_log_mb,
        )
        log_mb_spin.pack(side="left")
        log_mb_spin.bind("<FocusOut>", _save_log_mb)
        log_mb_spin.bind("<Return>", _save_log_mb)
        ttk.Label(log_mb_row, text="MB", style="Card.TLabel").pack(side="left", padx=(6, 0))

        ttk.Label(data_card, text="Carpeta de datos", style="Card.TLabel").pack(anchor="w", pady=(0, 4))
        path_var = tk.StringVar(value=config_store.get_config_dir())
        ttk.Entry(data_card, textvariable=path_var, state="readonly", width=42).pack(
            anchor="w", pady=(0, 6)
        )

        def _change_folder():
            new_dir = filedialog.askdirectory(
                title="Elige la nueva carpeta para los datos de aLoguear",
                initialdir=config_store.get_config_dir(),
            )
            if not new_dir:
                return
            try:
                config_store.set_config_dir(new_dir)
            except OSError as exc:
                messagebox.showerror("No se pudo mover la carpeta", str(exc))
                return
            path_var.set(new_dir)
            messagebox.showinfo(
                "Carpeta cambiada",
                f"Los datos se copiaron a:\n{new_dir}\n\n"
                "Cierra y vuelve a abrir aLoguear para que la app empiece a usar "
                "esa carpeta (los datos originales no se han borrado).",
            )

        ttk.Button(data_card, text="Cambiar carpeta…", style="Secondary.TButton", command=_change_folder).pack(
            anchor="w"
        )

        ttk.Button(body, text="Cerrar", style="Accent.TButton", command=win.destroy).pack(
            anchor="e", pady=(16, 0)
        )

        win.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - win.winfo_reqwidth()) // 2)
        y = self.winfo_rooty() + 60
        win.geometry(f"+{x}+{y}")

    def _build_style(self):
        _apply_palette(self.is_dark)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("Inner.TFrame", background=INNER_BG)
        style.configure("Footer.TFrame", background=CARD_BG)

        # Cabecera: fondo profundo con buen contraste en ambos temas.
        style.configure("Header.TFrame", background=HEADER_BG)
        style.configure(
            "Header.TLabel", background=HEADER_BG, foreground=HEADER_FG,
            font=(FONT, TITLE_FONT_SIZE, "bold"),
        )
        style.configure(
            "SubHeader.TLabel", background=HEADER_BG, foreground=HEADER_MUTED,
            font=(FONT, 9),
        )
        style.configure(
            "Version.TLabel", background=HEADER_FG, foreground=HEADER_BG,
            font=(FONT, 8, "bold"), padding=(8, 2),
        )
        style.configure(
            "HeaderIcon.TButton", font=(FONT, 10), padding=(10, 6),
            background=HEADER_BG, foreground=HEADER_FG,
            borderwidth=1, relief="solid", bordercolor=HEADER_FG,
        )
        style.map(
            "HeaderIcon.TButton",
            background=[("active", ACCENT_DARK), ("pressed", ACCENT_DARK)],
            foreground=[("active", "#ffffff")],
        )

        # Banner de actualización: ámbar legible también en oscuro.
        banner_bg = "#fff7e0" if not self.is_dark else "#3a2f10"
        banner_fg = "#8a6100" if not self.is_dark else "#fcd34d"
        banner_border = "#e0c26a" if not self.is_dark else "#8a6100"
        style.configure("UpdateBanner.TFrame", background=banner_bg)
        style.configure(
            "UpdateBanner.TLabel", background=banner_bg, foreground=banner_fg,
            font=(FONT, 9, "bold"),
        )
        style.configure(
            "UpdateBanner.TButton", font=(FONT, 8, "bold"), padding=(10, 4),
            background=banner_fg, foreground=banner_bg if self.is_dark else "white",
            borderwidth=0, relief="flat",
        )
        style.map("UpdateBanner.TButton", background=[("active", ACCENT_DARK)])
        style.configure(
            "UpdateBannerLink.TButton", font=(FONT, 8), padding=(8, 4),
            background=banner_bg, foreground=banner_fg, borderwidth=1,
            relief="solid", bordercolor=banner_border,
        )

        style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT, BASE_FONT_SIZE))
        style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT, font=(FONT, BASE_FONT_SIZE))
        style.configure(
            "Field.TLabel", background=CARD_BG, foreground=MUTED,
            font=(FONT, FIELD_FONT_SIZE, "bold"),
        )
        style.configure("Muted.TLabel", background=CARD_BG, foreground=MUTED, font=(FONT, 8))
        style.configure("Footer.TLabel", background=CARD_BG, foreground=MUTED, font=(FONT, 8))
        style.configure("Count.TLabel", background=CARD_BG, foreground=MUTED, font=(FONT, 8, "bold"))
        # Mensajes de estado: se muestran como "pastilla" con fondo propio.
        style.configure(
            "Success.TLabel", background=SUCCESS_BG, foreground=SUCCESS,
            font=(FONT, 9, "bold"), padding=(10, 8),
        )
        style.configure(
            "Danger.TLabel", background=DANGER_LIGHT, foreground=DANGER,
            font=(FONT, 9, "bold"), padding=(10, 8),
        )
        style.configure(
            "Info.TLabel", background=INFO_BG, foreground=INFO_FG,
            font=(FONT, 9, "bold"), padding=(10, 8),
        )
        style.configure(
            "Mode.TLabel", background=CARD_BG, foreground=ACCENT_DARK,
            font=(FONT, 11, "bold"),
        )
        style.configure(
            "ModeBadge.TLabel", background=ACCENT_SOFT, foreground=ACCENT_DARK,
            font=(FONT, 8, "bold"), padding=(8, 4),
        )

        style.configure(
            "Card.TLabelframe", background=CARD_BG, bordercolor=BORDER,
            relief="solid", borderwidth=1
        )
        style.configure(
            "Card.TLabelframe.Label", background=CARD_BG, foreground=ACCENT_DARK,
            font=(FONT, SECTION_FONT_SIZE, "bold")
        )
        style.configure(
            "Inner.TLabelframe", background=INNER_BG, bordercolor=BORDER,
            relief="solid", borderwidth=1
        )
        style.configure(
            "Inner.TLabelframe.Label", background=CARD_BG, foreground=MUTED,
            font=(FONT, 9, "bold")
        )

        style.configure(
            "TCheckbutton", background=BG, foreground=TEXT, font=(FONT, BASE_FONT_SIZE)
        )
        style.configure(
            "Card.TCheckbutton", background=CARD_BG, foreground=TEXT, font=(FONT, BASE_FONT_SIZE)
        )
        style.configure(
            "Day.TCheckbutton", background=INNER_BG, foreground=TEXT,
            font=(FONT, 9, "bold"), padding=(7, 5),
            bordercolor=BORDER, relief="solid", borderwidth=1,
        )
        for st in ("TCheckbutton", "Card.TCheckbutton"):
            style.map(st, background=[("active", CARD_BG)], foreground=[("active", ACCENT)])
        style.map(
            "Day.TCheckbutton",
            background=[("active", ACCENT_SOFT), ("selected", ACCENT_LIGHT)],
            foreground=[("active", ACCENT_DARK), ("selected", ACCENT_DARK)],
            bordercolor=[("selected", ACCENT), ("active", ACCENT)],
        )

        style.configure(
            "Card.TRadiobutton", background=CARD_BG, foreground=TEXT, font=(FONT, BASE_FONT_SIZE)
        )
        style.map("Card.TRadiobutton", background=[("active", CARD_BG)], foreground=[("active", ACCENT)])

        style.configure(
            "TEntry", fieldbackground=CARD_BG, foreground=TEXT,
            bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
            padding=9, relief="solid", borderwidth=1, insertcolor=TEXT,
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", FOCUS_RING)],
            lightcolor=[("focus", FOCUS_RING)],
            darkcolor=[("focus", FOCUS_RING)],
        )
        style.configure(
            "Search.TEntry", fieldbackground=INNER_BG, foreground=TEXT,
            bordercolor=BORDER, padding=8, relief="solid", borderwidth=1,
        )
        style.map("Search.TEntry", bordercolor=[("focus", FOCUS_RING)])

        style.configure(
            "TSpinbox", fieldbackground=CARD_BG, foreground=TEXT,
            bordercolor=BORDER, arrowsize=13, padding=6, insertcolor=TEXT,
        )
        style.map("TSpinbox", bordercolor=[("focus", FOCUS_RING)])
        style.configure(
            "TScrollbar", background=BG, troughcolor=BG, bordercolor=BG,
            arrowcolor=MUTED, relief="flat",
        )
        style.map("TScrollbar", background=[("active", BORDER)])

        # Botones principales: más altos y con jerarquía clara.
        style.configure(
            "Accent.TButton", font=(FONT, 10, "bold"), padding=(18, 10),
            background=ACCENT, foreground="white", borderwidth=0, relief="flat",
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", DISABLED_BG), ("active", ACCENT_DARK), ("pressed", ACCENT_DARK)],
            foreground=[("disabled", DISABLED_FG)],
        )

        style.configure(
            "Secondary.TButton", font=(FONT, 10), padding=(18, 10),
            background=SECONDARY_BG, foreground=TEXT, borderwidth=1,
            relief="solid", bordercolor=BORDER,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", SECONDARY_HOVER), ("pressed", SECONDARY_PRESS)],
            bordercolor=[("active", BORDER_STRONG)],
        )

        style.configure(
            "AccentSmall.TButton", font=(FONT, 9, "bold"), padding=(12, 7),
            background=ACCENT, foreground="white", borderwidth=0, relief="flat",
        )
        style.map(
            "AccentSmall.TButton",
            background=[("active", ACCENT_DARK), ("pressed", ACCENT_DARK)],
        )

        style.configure(
            "IconDanger.TButton", font=(FONT, 10), padding=(7, 5),
            background=CARD_BG, foreground=DANGER, borderwidth=1,
            relief="solid", bordercolor=BORDER,
        )
        style.map(
            "IconDanger.TButton",
            background=[("active", DANGER_LIGHT)],
            bordercolor=[("active", DANGER)],
        )

        style.configure(
            "IconGhost.TButton", font=(FONT, 10), padding=(7, 5),
            background=CARD_BG, foreground=ACCENT_DARK, borderwidth=1,
            relief="solid", bordercolor=BORDER,
        )
        style.map(
            "IconGhost.TButton",
            background=[("active", ACCENT_SOFT)],
            bordercolor=[("active", ACCENT)],
        )

        style.configure(
            "Ghost.TButton", font=(FONT, 9), padding=(12, 7),
            background=CARD_BG, foreground=ACCENT_DARK, borderwidth=1,
            relief="solid", bordercolor=BORDER,
        )
        style.map(
            "Ghost.TButton",
            background=[("active", ACCENT_SOFT)],
            bordercolor=[("active", ACCENT)],
        )

        style.configure(
            "GhostDanger.TButton", font=(FONT, 9), padding=(12, 7),
            background=CARD_BG, foreground=DANGER, borderwidth=1,
            relief="solid", bordercolor=BORDER,
        )
        style.map(
            "GhostDanger.TButton",
            background=[("active", DANGER_LIGHT)],
            bordercolor=[("active", DANGER)],
        )

        style.configure(
            "Link.TButton", font=(FONT, 9), padding=(2, 6),
            background=CARD_BG, foreground=ACCENT_DARK, borderwidth=0, relief="flat",
        )
        style.map("Link.TButton", background=[("active", CARD_BG)], foreground=[("active", ACCENT)])

        # Tabla: filas más altas, cabecera sutil y selección visible.
        style.configure(
            "Card.Treeview", background=CARD_BG, fieldbackground=CARD_BG,
            foreground=TEXT, rowheight=30, font=(FONT, 9), borderwidth=0,
        )
        style.configure(
            "Card.Treeview.Heading", background=INNER_BG, foreground=MUTED,
            font=(FONT, 8, "bold"), relief="flat", borderwidth=0, padding=(6, 8),
        )
        style.map(
            "Card.Treeview",
            background=[("selected", ACCENT_LIGHT)],
            foreground=[("selected", ACCENT_DARK)],
        )
        style.map(
            "Card.Treeview.Heading",
            background=[("active", ACCENT_SOFT)],
            foreground=[("active", ACCENT_DARK)],
        )

    # --- Utilidades de UI ---

    def _set_status(self, kind: str, message: str):
        """Muestra el mensaje de estado como pastilla de color (info/éxito/error).
        Si el mensaje está vacío, oculta la pastilla para no dejar huecos raros."""
        styles = {"success": "Success.TLabel", "danger": "Danger.TLabel", "info": "Info.TLabel"}
        if not message:
            self.status_var.set("")
            if getattr(self, "status_label", None) is not None:
                self.status_label.grid_remove()
            self._status_visible = False
            return
        self.status_var.set(message)
        if getattr(self, "status_label", None) is not None:
            self.status_label.configure(style=styles.get(kind, "Info.TLabel"))
            self.status_label.grid()
            self._status_visible = True
        if getattr(self, "footer_status_var", None) is not None:
            short = message if len(message) <= 90 else message[:87] + "…"
            self.footer_status_var.set(short)

    def _toggle_password(self):
        self.pass_entry.configure(show="" if self.show_pass_var.get() else "•")

    def _toggle_password_button(self):
        showing = self.show_pass_var.get()
        self.show_pass_var.set(not showing)
        self.pass_entry.configure(show="" if not showing else "•")
        self.show_pass_btn.configure(text="Ocultar" if not showing else "Mostrar")

    def _toggle_keep_alive(self):
        if self.keep_alive_var.get():
            self.keep_alive_frame.grid(row=self._keep_alive_row, column=0, sticky="ew", pady=(4, 4))
        else:
            self.keep_alive_frame.grid_remove()
        self._resize_to_content()

    def _toggle_advanced(self):
        expanded = not self.adv_expanded.get()
        self.adv_expanded.set(expanded)
        if expanded:
            self.adv.grid(row=self._adv_row, column=0, sticky="ew", pady=(10, 0))
            self.adv_toggle_btn.configure(text="▾  Avanzado: selectores CSS (opcional)")
        else:
            self.adv.grid_remove()
            self.adv_toggle_btn.configure(text="▸  Avanzado (opcional): selectores CSS")
        self._resize_to_content()

    def _resize_to_content(self):
        # El contenido vive dentro de un canvas con scroll, así que basta con
        # dejar que su <Configure> recalcule la scrollregion; no hace falta
        # redimensionar la ventana.
        self.update_idletasks()

    # --- Lista de tareas ---

    def _refresh_task_list(self, select_id: str | None = None,
                           select_ids: list | None = None):
        self.tree.delete(*self.tree.get_children())
        all_tasks = config_store.load_tasks()
        query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        if query:
            tasks = [
                t for t in all_tasks
                if query in (t.get("name") or "").lower() or query in (t.get("url") or "").lower()
            ]
        else:
            tasks = all_tasks
        active_ids = []
        for index, task in enumerate(tasks):
            active = task.get("active", True)
            last_result = config_store.load_last_result(task["id"])
            tags = []
            if index % 2 == 1:
                tags.append("even_row")
            if last_result and not last_result.get("success"):
                tags.append("fail_row")
            elif last_result and last_result.get("success"):
                tags.append("ok_row")
            if not active:
                tags.append("paused_row")
            status_dot = "⏸ " if not active else ("● " if last_result and not last_result.get("success") else "")
            self.tree.insert(
                "", "end", iid=task["id"],
                text=f"{status_dot}{task.get('name') or task.get('url', '')}",
                values=(
                    task.get("schedule_time", ""),
                    _days_display(task.get("schedule_days", [])),
                    _validity_display(
                        task.get("schedule_start_date", ""),
                        task.get("schedule_end_date", ""),
                    ),
                    _last_result_display(last_result),
                    "Pausada" if not active else "…",
                ),
                tags=tuple(tags),
            )
            if active:
                active_ids.append(task["id"])
        targets = list(select_ids) if select_ids is not None else ([select_id] if select_id else [])
        for tid in targets:
            if self.tree.exists(tid):
                self.tree.selection_add(tid)
        for tid in targets:
            if self.tree.exists(tid):
                self.tree.see(tid)
                break
        self._update_batch_bar()

        total = len(all_tasks)
        shown = len(tasks)
        active_count = sum(1 for t in all_tasks if t.get("active", True))
        if hasattr(self, "list_count_var"):
            if query:
                self.list_count_var.set(f"{shown} de {total} tareas  ·  {active_count} activas")
            elif total == 0:
                self.list_count_var.set("0 tareas — crea la primera abajo")
            else:
                self.list_count_var.set(f"{total} tarea(s)  ·  {active_count} activa(s)")
        if hasattr(self, "footer_status_var") and not getattr(self, "_status_visible", False):
            self.footer_status_var.set(
                f"{total} tarea(s) · {active_count} activa(s)" if total else "Sin tareas — listo para crear la primera"
            )

        if tasks:
            self.empty_hint.grid_remove()
        else:
            self.empty_hint.configure(
                text="Ningún resultado para esa búsqueda." if query
                else "Sin tareas todavía.\nPulsa «＋ Nueva tarea», rellena el formulario y pulsa Guardar."
            )
            self.empty_hint.grid(row=4, column=0, sticky="n", pady=(12, 4))
        self._resize_to_content()

        if active_ids:
            threading.Thread(target=self._fetch_next_runs, args=(active_ids,), daemon=True).start()

    def _fetch_next_runs(self, task_ids: list):
        script_dir = _script_dir_global()
        ps_script = os.path.join(script_dir, "list_next_runs.ps1")
        next_runs = {}
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script],
                cwd=script_dir, capture_output=True, text=True, timeout=20,
            )
            data = json.loads(result.stdout or "[]")
            if isinstance(data, dict):
                data = [data]
            for entry in data:
                next_runs[entry.get("TaskId")] = entry.get("NextRunTime")
        except Exception:
            pass
        self.after(0, lambda: self._apply_next_runs(task_ids, next_runs))

    def _apply_next_runs(self, task_ids: list, next_runs: dict):
        for task_id in task_ids:
            if not self.tree.exists(task_id):
                continue
            self.tree.set(task_id, "next", _format_net_date(next_runs.get(task_id)))

    def _sort_tree(self, col: str):
        reverse = self._sort_column == col and not self._sort_reverse
        children = list(self.tree.get_children(""))

        def sort_key(iid):
            value = self.tree.item(iid, "text") if col == "#0" else self.tree.set(iid, col)
            if col in ("last", "next"):
                return _date_sort_key(value if isinstance(value, str) else "")
            return value.lower() if isinstance(value, str) else value

        children.sort(key=sort_key, reverse=reverse)
        for index, iid in enumerate(children):
            self.tree.move(iid, "", index)
        self._sort_column = col
        self._sort_reverse = reverse

    def _selected_ids(self) -> list:
        """Ids de las tareas actualmente seleccionadas en la lista (0, 1 o N)."""
        try:
            return list(self.tree.selection())
        except Exception:
            return []

    def _update_batch_bar(self):
        """Muestra la barra de lote solo cuando hay 2+ tareas seleccionadas."""
        if not hasattr(self, "batch_bar"):
            return
        ids = self._selected_ids()
        if len(ids) >= 2:
            self.batch_label.configure(text=f"{len(ids)} seleccionadas — el formulario no se toca")
            self.batch_bar.grid()
        else:
            self.batch_bar.grid_remove()

    def _on_list_delete_key(self, _event=None):
        ids = self._selected_ids()
        if len(ids) >= 2:
            self.on_batch_delete()
        elif len(ids) == 1:
            self.on_delete_task()
        return "break"

    def _on_list_select_all_key(self, _event=None):
        self.tree.selection_set(self.tree.get_children(""))
        return "break"

    def _on_list_escape_key(self, _event=None):
        self.tree.selection_remove(self.tree.selection())
        self._update_batch_bar()
        return "break"

    def _on_tree_select(self, _event=None):
        selection = self._selected_ids()
        self._update_batch_bar()
        if len(selection) != 1:
            # Con 0 o N>1 seleccionadas no se toca el formulario: la edición
            # y los botones Guardar/Probar siguen actuando sobre la tarea
            # individual abierta (current_task_id), y el lote va por su barra.
            return
        task_id = selection[0]
        if task_id == self.current_task_id:
            # Ya es la tarea abierta (p.ej. reselección tras refrescar la
            # lista al terminar Guardar/Probar): no recargar el formulario,
            # o se perdería el mensaje de resultado que se acaba de mostrar.
            return
        data = config_store.get_task(task_id)
        if not data:
            return
        self.current_task_id = task_id
        self._populate_form(data)

    def on_new_task(self):
        self.tree.selection_remove(self.tree.selection())
        self._update_batch_bar()
        self._clear_form()

    # --- Exportar / importar ---

    def on_export_tasks(self):
        tasks = config_store.load_tasks()
        if not tasks:
            messagebox.showinfo("Nada que exportar", "No hay tareas guardadas todavía.")
            return
        include_passwords = messagebox.askyesno(
            "Exportar tareas",
            f"Se exportarán {len(tasks)} tarea(s).\n\n"
            "¿Incluir las contraseñas en el archivo? Se guardarían SIN CIFRAR, en texto "
            "plano, así que trata el archivo exportado con cuidado (solo así podrán "
            "reutilizarse en otro equipo; si eliges que no, tendrás que volver a "
            "escribirlas después de importar).",
        )
        path = filedialog.asksaveasfilename(
            title="Exportar tareas", defaultextension=".json",
            initialfile="aLoguear-tareas.json", filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        export_tasks = []
        for task in tasks:
            entry = {field: task.get(field) for field in _EXPORT_FIELDS}
            if include_passwords:
                full = config_store.get_task(task["id"])
                entry["password"] = full.get("password", "") if full else ""
            export_tasks.append(entry)
        data = {
            "app": APP_NAME,
            "version": APP_VERSION,
            "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "passwords_included": include_passwords,
            "tasks": export_tasks,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            messagebox.showerror("Error al exportar", str(exc))
            return
        messagebox.showinfo("Tareas exportadas", f"Se exportaron {len(export_tasks)} tarea(s) a:\n{path}")

    def on_import_tasks(self):
        path = filedialog.askopenfilename(title="Importar tareas", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Error al importar", f"No se pudo leer el archivo:\n{exc}")
            return
        tasks = data.get("tasks", []) if isinstance(data, dict) else []
        if not isinstance(tasks, list) or not tasks:
            messagebox.showinfo("Nada que importar", "El archivo no contiene tareas.")
            return
        tasks = [t for t in tasks if isinstance(t, dict)]
        if not tasks:
            messagebox.showinfo("Nada que importar", "El archivo no contiene tareas válidas.")
            return
        if not messagebox.askyesno(
            "Importar tareas",
            f"Se importarán {len(tasks)} tarea(s) como tareas nuevas (no se sobrescribe "
            "nada existente), pausadas por seguridad. Después tendrás que revisarlas y "
            "pulsar 'Guardar' en cada una para activarlas y programarlas en Windows.",
        ):
            return
        imported = 0
        missing_password = 0
        skipped = 0
        for entry in tasks:
            url = str(entry.get("url", "") or "").strip()
            if not url or not _is_valid_url(url):
                skipped += 1
                continue
            password = entry.get("password", "") or ""
            if not isinstance(password, str):
                password = str(password)
            if not password:
                missing_password += 1
            raw_ka_url = str(entry.get("keep_alive_url", "") or "").strip()
            ka_url = raw_ka_url if _is_valid_url(raw_ka_url) else ""
            try:
                config_store.save_task(
                    task_id=None,
                    name=str(entry.get("name", "") or url)[:200],
                    url=url,
                    username=str(entry.get("username", "") or ""),
                    password=password,
                    headless=bool(entry.get("headless", True)),
                    user_selector=str(entry.get("user_selector", "") or ""),
                    pass_selector=str(entry.get("pass_selector", "") or ""),
                    submit_selector=str(entry.get("submit_selector", "") or ""),
                    schedule_time=_normalize_schedule_time(str(entry.get("schedule_time", "08:00"))),
                    schedule_days=_normalize_schedule_days(entry.get("schedule_days")),
                    schedule_start_date=_normalize_iso_date(str(entry.get("schedule_start_date", ""))),
                    schedule_end_date=_normalize_iso_date(str(entry.get("schedule_end_date", ""))),
                    keep_alive=bool(entry.get("keep_alive", False)),
                    keep_alive_interval_min=_parse_int_safe(
                        entry.get("keep_alive_interval_min", 5), 5, 1, 120
                    ),
                    keep_alive_duration_min=_parse_int_safe(
                        entry.get("keep_alive_duration_min", 60), 60, 0, 24 * 60
                    ),
                    keep_alive_url=ka_url,
                    active=False,
                )
            except Exception:
                skipped += 1
                continue
            imported += 1
        self._refresh_task_list()
        message = f"Se importaron {imported} tarea(s), quedaron pausadas."
        if missing_password:
            message += f"\n{missing_password} no traían contraseña: complétala y pulsa Guardar."
        if skipped:
            message += f"\n{skipped} entrada(s) se omitieron por URL no válida o datos corruptos."
        messagebox.showinfo("Tareas importadas", message)

    def on_delete_task(self):
        if not self.current_task_id:
            messagebox.showinfo("Nada que eliminar", "Selecciona primero una tarea de la lista.")
            return
        task = config_store.get_task(self.current_task_id)
        name = task.get("name", self.current_task_id) if task else self.current_task_id
        if not messagebox.askyesno(
            "Eliminar tarea",
            f"¿Eliminar la tarea '{name}'? También se quitará su tarea programada de Windows, si existe.",
        ):
            return
        task_id = self.current_task_id
        config_store.delete_task(task_id)
        self._clear_form()
        self._refresh_task_list()
        threading.Thread(target=self._unregister_task, args=(task_id,), daemon=True).start()

    def _unregister_task(self, task_id: str):
        script_dir = _script_dir_global()
        ps_script = os.path.join(script_dir, "unregister_task.ps1")
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script, "-TaskId", task_id],
            cwd=script_dir, capture_output=True, text=True,
        )

    # --- Acciones en lote ---

    def _set_task_active(self, task_id: str, active: bool) -> bool:
        """Activa/pausa una tarea conservando todos sus campos (incluida la
        contraseña descifrada). Devuelve False si la tarea ya no existe."""
        data = config_store.get_task(task_id)
        if not data:
            return False
        config_store.save_task(
            task_id=task_id,
            name=data.get("name", ""),
            url=data.get("url", ""),
            username=data.get("username", ""),
            password=data.get("password", ""),
            headless=data.get("headless", True),
            user_selector=data.get("user_selector", ""),
            pass_selector=data.get("pass_selector", ""),
            submit_selector=data.get("submit_selector", ""),
            schedule_time=data.get("schedule_time", "08:00"),
            schedule_days=data.get("schedule_days") or [],
            schedule_start_date=data.get("schedule_start_date", ""),
            schedule_end_date=data.get("schedule_end_date", ""),
            keep_alive=data.get("keep_alive", False),
            keep_alive_interval_min=data.get("keep_alive_interval_min", 5),
            keep_alive_duration_min=data.get("keep_alive_duration_min", 60),
            keep_alive_url=data.get("keep_alive_url", ""),
            active=active,
        )
        return True

    def _sync_schedule_one(self, task_id: str, active: bool) -> bool:
        """Registra o quita UNA tarea en el Programador de Windows (bloqueante,
        para usar desde hilos de fondo). Devuelve True si el .ps1 salió con 0."""
        script_dir = _script_dir_global()
        if active:
            data = config_store.get_task(task_id)
            if not data:
                return False
            ps_script = os.path.join(script_dir, "register_task.ps1")
            args = [
                "-TaskId", task_id,
                "-Time", data.get("schedule_time", "08:00"),
                "-Days", ",".join(data.get("schedule_days") or []),
            ]
            if data.get("schedule_start_date"):
                args += ["-StartDate", data["schedule_start_date"]]
            if data.get("schedule_end_date"):
                args += ["-EndDate", data["schedule_end_date"]]
            if getattr(sys, "frozen", False):
                args += ["-RunnerExe", os.path.join(script_dir, "aLoguear-runner.exe")]
        else:
            ps_script = os.path.join(script_dir, "unregister_task.ps1")
            args = ["-TaskId", task_id]
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script, *args],
            cwd=script_dir, capture_output=True, text=True,
        )
        return result.returncode == 0

    def on_batch_activate(self):
        self._batch_set_active(True)

    def on_batch_pause(self):
        self._batch_set_active(False)

    def _batch_set_active(self, active: bool):
        ids = [i for i in self._selected_ids() if self.tree.exists(i)]
        if len(ids) < 2:
            return
        for task_id in ids:
            self._set_task_active(task_id, active)
        self._refresh_task_list(select_ids=ids)
        self._set_status(
            "info",
            f"{'Activando' if active else 'Pausando'} {len(ids)} tareas en Windows…",
        )
        threading.Thread(
            target=self._batch_sync_thread, args=(ids, active), daemon=True,
        ).start()

    def _batch_sync_thread(self, task_ids: list, active: bool):
        ok_count = 0
        for task_id in task_ids:
            try:
                if self._sync_schedule_one(task_id, active):
                    ok_count += 1
            except Exception:
                pass
        failed = len(task_ids) - ok_count
        if failed:
            message = (
                f"Se {'activaron' if active else 'pausaron'} {ok_count}/{len(task_ids)} en la lista; "
                f"{failed} no se pudieron {'programar' if active else 'quitar'} en Windows."
            )
            self.after(0, lambda: self._batch_done(False, task_ids, message))
        else:
            action = "activadas y programadas" if active else "pausadas"
            message = f"✓ {len(task_ids)} tareas {action} correctamente."
            self.after(0, lambda: self._batch_done(True, task_ids, message))

    def _batch_done(self, ok: bool, task_ids: list, message: str):
        self._refresh_task_list(select_ids=[t for t in task_ids if self.tree.exists(t)])
        self._set_status("success" if ok else "danger", message)
        if not ok:
            messagebox.showwarning("Acción en lote", message)

    def on_batch_delete(self):
        ids = [i for i in self._selected_ids() if self.tree.exists(i)]
        if len(ids) < 2:
            return
        names = []
        for task_id in ids:
            task = config_store.get_task(task_id)
            names.append(task.get("name", task_id) if task else task_id)
        preview = "\n".join(f"• {n}" for n in names[:8])
        if len(names) > 8:
            preview += f"\n…y {len(names) - 8} más"
        if not messagebox.askyesno(
            "Eliminar tareas",
            f"¿Eliminar estas {len(ids)} tareas? También se quitarán sus tareas "
            f"programadas de Windows, si existen.\n\n{preview}",
        ):
            return
        for task_id in ids:
            try:
                config_store.delete_task(task_id)
            except Exception:
                pass
        if self.current_task_id in ids:
            self._clear_form()
        else:
            self._set_status("", "")
        self._refresh_task_list()
        self._set_status("info", f"Eliminando {len(ids)} tareas de Windows…")
        threading.Thread(target=self._batch_unregister_thread, args=(ids,), daemon=True).start()

    def _batch_unregister_thread(self, task_ids: list):
        for task_id in task_ids:
            try:
                self._unregister_task(task_id)
            except Exception:
                pass
        self.after(
            0,
            lambda: self._set_status("success", f"✓ {len(task_ids)} tareas eliminadas."),
        )

    def _refresh_screenshot_button(self):
        if self.current_task_id and os.path.exists(config_store.screenshot_path(self.current_task_id)):
            self.screenshot_btn.grid()
        else:
            self.screenshot_btn.grid_remove()

    def _refresh_log_button(self):
        if self.current_task_id and os.path.exists(config_store.log_path(self.current_task_id)):
            self.log_btn.grid()
        else:
            self.log_btn.grid_remove()

    def on_view_log(self):
        if not self.current_task_id:
            return
        path = config_store.log_path(self.current_task_id)
        if not os.path.exists(path):
            messagebox.showinfo("Sin registro", "Todavía no hay ningún log guardado para esta tarea.")
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError as exc:
            messagebox.showerror("Error al leer el log", str(exc))
            return

        win = tk.Toplevel(self)
        win.title(f"Registro — {self.name_var.get() or self.current_task_id}")
        win.geometry("760x540")
        win.minsize(560, 400)
        win.configure(bg=BG)
        win.transient(self)

        header_row = ttk.Frame(win, style="TFrame", padding=(14, 12, 14, 0))
        header_row.pack(fill="x")
        ttk.Label(
            header_row,
            text=f"Registro de «{self.name_var.get() or self.current_task_id}»",
            style="Card.TLabel",
        ).pack(side="left")
        ttk.Label(header_row, text=f"{len(content.splitlines())} líneas", style="Muted.TLabel").pack(side="right")

        text_frame = ttk.Frame(win, style="TFrame", padding=14)
        text_frame.pack(fill="both", expand=True)
        text_frame.grid_columnconfigure(0, weight=1)
        text_frame.grid_rowconfigure(0, weight=1)

        text = tk.Text(
            text_frame, wrap="word", font=("Consolas", 9),
            background=CARD_BG, foreground=TEXT, insertbackground=TEXT,
            relief="solid", borderwidth=1, padx=10, pady=10,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=FOCUS_RING,
        )
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns", padx=(8, 0))

        text.insert("1.0", content)
        text.configure(state="disabled")
        text.see("end")

        def _download_log():
            task_id = self.current_task_id or "tarea"
            initial = f"aLoguear-{task_id}.log"
            dest = filedialog.asksaveasfilename(
                defaultextension=".log",
                filetypes=[("Archivos de registro", "*.log"), ("Todos los archivos", "*.*")],
                initialfile=initial,
                title="Guardar copia del log completo",
            )
            if not dest:
                return
            try:
                shutil.copyfile(path, dest)
            except OSError as exc:
                messagebox.showerror("Error al guardar", f"No se pudo guardar la copia del log:\n{exc}")
                return
            messagebox.showinfo(
                "Log guardado",
                f"Copia del log guardada en:\n{dest}\n\nYa puedes adjuntar ese archivo al informar del error.",
            )

        btn_row = ttk.Frame(win, style="TFrame", padding=(14, 0, 14, 14))
        btn_row.pack(fill="x")
        ttk.Button(
            btn_row, text="Abrir carpeta de registros", style="Secondary.TButton",
            command=lambda: os.startfile(os.path.dirname(path)),
        ).pack(side="left")
        download_btn = ttk.Button(
            btn_row, text="⬇  Descargar log completo", style="Secondary.TButton",
            command=_download_log,
        )
        download_btn.pack(side="left", padx=(8, 0))
        ToolTip(download_btn, "Guarda una copia del log completo donde quieras para poder enviarla al informar de un error.")
        ttk.Button(btn_row, text="Cerrar", style="Accent.TButton", command=win.destroy).pack(side="right")

    def on_view_screenshot(self):
        if not self.current_task_id:
            return
        path = config_store.screenshot_path(self.current_task_id)
        if not os.path.exists(path):
            messagebox.showinfo("Sin captura", "No hay ninguna captura de error guardada para esta tarea.")
            return
        os.startfile(path)

    def on_duplicate_task(self):
        if not self.current_task_id:
            return
        data = config_store.get_task(self.current_task_id)
        if not data:
            return
        data["name"] = f"Copia de {data.get('name') or data.get('url', '')}"
        self.tree.selection_remove(self.tree.selection())
        self.current_task_id = None
        self._populate_form(data)
        self.mode_label.configure(text="＋  Nueva tarea (copia sin guardar)")
        self.mode_badge.configure(text="COPIA SIN GUARDAR")
        self.delete_btn.grid_remove()
        self.duplicate_btn.grid_remove()
        self.screenshot_btn.grid_remove()
        self.log_btn.grid_remove()
        self._set_status("info", "Revisa los datos y pulsa Guardar para crear la copia como tarea independiente.")

    def _clear_form(self):
        self.current_task_id = None
        self.name_var.set("")
        self.url_var.set("")
        self.user_var.set("")
        self.pass_var.set("")
        self.show_pass_var.set(False)
        if hasattr(self, "show_pass_btn"):
            self.show_pass_btn.configure(text="Mostrar")
        self.active_var.set(True)
        self.headless_var.set(True)
        self.keep_alive_var.set(False)
        self.keep_alive_interval_var.set("5")
        self.keep_alive_duration_hour_var.set("01")
        self.keep_alive_duration_min_var.set("00")
        self.keep_alive_url_var.set("")
        self.keep_alive_frame.grid_remove()
        self.user_sel_var.set("")
        self.pass_sel_var.set("")
        self.submit_sel_var.set("")
        self.hour_var.set("08")
        self.minute_var.set("00")
        for var in self.day_vars.values():
            var.set(True)
        self.start_date_var.set("")
        self.end_date_var.set("")
        self._set_status("", "")
        self.mode_label.configure(text="＋  Nueva tarea")
        self.mode_badge.configure(text="SIN GUARDAR")
        self.delete_btn.grid_remove()
        self.duplicate_btn.grid_remove()
        self.screenshot_btn.grid_remove()
        self.log_btn.grid_remove()

    def _populate_form(self, data: dict):
        self.name_var.set(data.get("name", ""))
        self.url_var.set(data.get("url", ""))
        self.user_var.set(data.get("username", ""))
        self.pass_var.set(data.get("password", ""))
        self.show_pass_var.set(False)
        if hasattr(self, "show_pass_btn"):
            self.show_pass_btn.configure(text="Mostrar")
        self.pass_entry.configure(show="•")
        self.active_var.set(data.get("active", True))
        self.headless_var.set(data.get("headless", True))
        self.keep_alive_var.set(data.get("keep_alive", False))
        self.keep_alive_interval_var.set(str(data.get("keep_alive_interval_min", 5)))
        self.keep_alive_url_var.set((data.get("keep_alive_url") or "").strip())
        duration_total = data.get("keep_alive_duration_min", 60)
        try:
            duration_total = int(duration_total)
        except (TypeError, ValueError):
            duration_total = 60
        self.keep_alive_duration_hour_var.set(f"{duration_total // 60:02d}")
        self.keep_alive_duration_min_var.set(f"{duration_total % 60:02d}")
        if self.keep_alive_var.get():
            self.keep_alive_frame.grid(row=self._keep_alive_row, column=0, sticky="ew", pady=(4, 4))
        else:
            self.keep_alive_frame.grid_remove()
        self.user_sel_var.set(data.get("user_selector", ""))
        self.pass_sel_var.set(data.get("pass_selector", ""))
        self.submit_sel_var.set(data.get("submit_selector", ""))
        if any([data.get("user_selector"), data.get("pass_selector"), data.get("submit_selector")]):
            if not self.adv_expanded.get():
                self._toggle_advanced()
        elif self.adv_expanded.get():
            self._toggle_advanced()

        schedule_time = data.get("schedule_time", "08:00")
        if ":" in schedule_time:
            hour, minute = schedule_time.split(":", 1)
            self.hour_var.set(hour.zfill(2))
            self.minute_var.set(minute.zfill(2))

        schedule_days = data.get("schedule_days") or [name for _, name in DAYS]
        for day_name, var in self.day_vars.items():
            var.set(day_name in schedule_days)

        self.start_date_var.set(_normalize_iso_date(data.get("schedule_start_date", "")))
        self.end_date_var.set(_normalize_iso_date(data.get("schedule_end_date", "")))

        self._set_status("", "")
        short_name = (data.get('name') or data.get('url', ''))[:40]
        self.mode_label.configure(text=f"✎  Editando: {short_name}")
        self.mode_badge.configure(text="ACTIVA" if data.get("active", True) else "PAUSADA")
        self.delete_btn.grid()
        self.duplicate_btn.grid()
        self._refresh_screenshot_button()
        self._refresh_log_button()

    # --- Guardar / validar ---

    def _selected_days(self) -> list:
        return [day_name for day_name, var in self.day_vars.items() if var.get()]

    def _schedule_time_str(self) -> str:
        hour = _parse_int_safe(self.hour_var.get(), 8, 0, 23)
        minute = _parse_int_safe(self.minute_var.get(), 0, 0, 59)
        self.hour_var.set(f"{hour:02d}")
        self.minute_var.set(f"{minute:02d}")
        return f"{hour:02d}:{minute:02d}"

    def _keep_alive_values(self) -> tuple[int, int]:
        interval = _parse_int_safe(self.keep_alive_interval_var.get(), 5, 1, 120)
        hours = _parse_int_safe(self.keep_alive_duration_hour_var.get(), 1, 0, 23)
        minutes = _parse_int_safe(self.keep_alive_duration_min_var.get(), 0, 0, 59)
        self.keep_alive_interval_var.set(str(interval))
        self.keep_alive_duration_hour_var.set(f"{hours:02d}")
        self.keep_alive_duration_min_var.set(f"{minutes:02d}")
        return interval, hours * 60 + minutes

    def _validate(self) -> bool:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Falta la URL", "Introduce la URL de la página.")
            return False
        if not _is_valid_url(url):
            messagebox.showerror(
                "URL no válida", "Introduce una URL completa http(s)://, p.ej. https://ejemplo.com/login."
            )
            return False
        if not self.user_var.get().strip():
            messagebox.showerror("Falta el usuario", "Introduce el usuario.")
            return False
        if not self.pass_var.get():
            messagebox.showerror("Falta la contraseña", "Introduce la contraseña.")
            return False
        if not self._selected_days():
            messagebox.showerror("Sin días seleccionados", "Elige al menos un día de la semana.")
            return False
        start = self.start_date_var.get().strip()
        end = self.end_date_var.get().strip()
        if start and not _normalize_iso_date(start):
            messagebox.showerror("Fecha de inicio no válida", "Usa el formato YYYY-MM-DD o déjala vacía.")
            return False
        if end and not _normalize_iso_date(end):
            messagebox.showerror("Fecha de fin no válida", "Usa el formato YYYY-MM-DD o déjala vacía.")
            return False
        if start and end and _normalize_iso_date(start) > _normalize_iso_date(end):
            messagebox.showerror(
                "Rango no válido", "La fecha de inicio no puede ser posterior a la de fin."
            )
            return False
        ka_url = self.keep_alive_url_var.get().strip()
        if ka_url and not _is_valid_url(ka_url):
            messagebox.showerror(
                "Página de trabajo no válida",
                "La página de trabajo debe ser una URL completa http(s):// o déjala vacía.",
            )
            return False
        try:
            self._schedule_time_str()
            self._keep_alive_values()
        except Exception:
            messagebox.showerror("Hora no válida", "Revisa la hora y los valores de keep-alive.")
            return False
        return True

    def _save(self) -> bool:
        if not self._validate():
            return False
        name = self.name_var.get().strip() or self.url_var.get().strip()
        interval_min, duration_min = self._keep_alive_values()
        if self.keep_alive_var.get() and duration_min == 0:
            proceed = messagebox.askyesno(
                "Mantener sesión indefinidamente",
                "Has puesto 0:00 (= indefinido): el proceso del runner quedará vivo "
                "para siempre recargando la página y ocupará su tarea programada.\n\n"
                "¿Seguro que quieres guardarlo así?",
            )
            if not proceed:
                return False
        try:
            task_id = config_store.save_task(
                task_id=self.current_task_id,
                name=name,
                url=self.url_var.get().strip(),
                username=self.user_var.get().strip(),
                password=self.pass_var.get(),
                headless=self.headless_var.get(),
                user_selector=self.user_sel_var.get().strip(),
                pass_selector=self.pass_sel_var.get().strip(),
                submit_selector=self.submit_sel_var.get().strip(),
                schedule_time=self._schedule_time_str(),
                schedule_days=self._selected_days(),
                schedule_start_date=_normalize_iso_date(self.start_date_var.get()),
                schedule_end_date=_normalize_iso_date(self.end_date_var.get()),
                keep_alive=self.keep_alive_var.get(),
                keep_alive_interval_min=interval_min,
                keep_alive_duration_min=duration_min,
                keep_alive_url=self.keep_alive_url_var.get().strip(),
                active=self.active_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("No se pudo guardar", f"No se pudo guardar la tarea:\n{exc}")
            return False
        self.current_task_id = task_id
        self.name_var.set(name)
        self._refresh_task_list(select_id=task_id)
        return True

    def on_save(self):
        if not self._save():
            return
        active = self.active_var.get()
        self._set_status("info", "Guardando y programando…" if active else "Guardando y pausando…")
        self.save_btn.configure(state="disabled")
        threading.Thread(
            target=self._save_and_sync_schedule_thread,
            args=(
                self.current_task_id, active, self._schedule_time_str(), self._selected_days(),
                _normalize_iso_date(self.start_date_var.get()),
                _normalize_iso_date(self.end_date_var.get()),
            ),
            daemon=True,
        ).start()

    def _save_and_sync_schedule_thread(self, task_id: str, active: bool, time_str: str, days: list,
                                       start_date: str = "", end_date: str = ""):
        script_dir = _script_dir_global()
        if active:
            ps_script = os.path.join(script_dir, "register_task.ps1")
            args = ["-TaskId", task_id, "-Time", time_str, "-Days", ",".join(days)]
            if start_date:
                args += ["-StartDate", start_date]
            if end_date:
                args += ["-EndDate", end_date]
            if getattr(sys, "frozen", False):
                runner_exe = os.path.join(script_dir, "aLoguear-runner.exe")
                args += ["-RunnerExe", runner_exe]
        else:
            ps_script = os.path.join(script_dir, "unregister_task.ps1")
            args = ["-TaskId", task_id]
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script, *args],
            cwd=script_dir, capture_output=True, text=True,
        )
        ok = result.returncode == 0
        if ok and active:
            message = f"✓ Tarea guardada y programada: {time_str} los días {', '.join(days)}."
        elif ok:
            message = "✓ Tarea guardada y pausada (sin tarea programada en Windows)."
        else:
            detail = (result.stderr or result.stdout or "").strip()
            action = "programar" if active else "pausar"
            message = f"✗ Tarea guardada, pero no se pudo {action} en Windows." + (
                f" Detalle: {detail}" if detail else ""
            )
        self.after(0, lambda: self._save_done(ok, message))

    def _save_done(self, ok: bool, message: str):
        self.save_btn.configure(state="normal")
        self._refresh_task_list(select_id=self.current_task_id)
        self._set_status("success" if ok else "danger", message)
        if not ok:
            messagebox.showwarning("Resultado de la programación", message)

    # --- Probar ahora ---

    def on_test(self):
        if not self._save():
            return
        self._set_status("info", "Ejecutando prueba de login… esto puede tardar unos segundos.")
        self.test_btn.configure(state="disabled")
        threading.Thread(target=self._run_test, args=(self.current_task_id,), daemon=True).start()

    def _run_test(self, task_id: str):
        cmd = _runner_command(task_id, "--no-keep-alive")
        result = subprocess.run(
            cmd, cwd=_runner_cwd(), capture_output=True, text=True,
        )
        ok = result.returncode == 0
        message = "✓ Login ejecutado correctamente." if ok else (
            "✗ El login terminó con errores. Revisa el log en "
            f"{config_store.log_path(task_id)}"
        )
        self.after(0, lambda: self._test_done(ok, message))

    def _test_done(self, ok: bool, message: str):
        self.test_btn.configure(state="normal")
        self._refresh_task_list(select_id=self.current_task_id)
        self._refresh_screenshot_button()
        self._refresh_log_button()
        self._set_status("success" if ok else "danger", message)
        if not ok:
            messagebox.showwarning("Resultado de la prueba", message)

    # --- Probar detección (sin enviar nada) ---

    def on_detect_only(self):
        if not self._save():
            return
        self._set_status("info", "Comprobando los selectores (no se enviará nada)…")
        self.detect_btn.configure(state="disabled")
        threading.Thread(target=self._run_detect_only, args=(self.current_task_id,), daemon=True).start()

    def _run_detect_only(self, task_id: str):
        cmd = _runner_command(task_id, "--detect-only")
        result = subprocess.run(
            cmd, cwd=_runner_cwd(), capture_output=True, text=True,
        )
        ok = result.returncode == 0
        message = "✓ Se encontraron los campos de usuario y contraseña." if ok else (
            "✗ No se encontraron todos los campos. Revisa el log para ver el detalle "
            "y ajusta los selectores CSS en Avanzado si hace falta."
        )
        self.after(0, lambda: self._detect_only_done(ok, message))

    def _detect_only_done(self, ok: bool, message: str):
        self.detect_btn.configure(state="normal")
        self._refresh_log_button()
        self._set_status("success" if ok else "danger", message)
        if not ok:
            messagebox.showwarning("Resultado de la detección", message)


if __name__ == "__main__":
    app = App()
    if "--start-minimized" in sys.argv[1:]:
        app.withdraw()
        if pystray is not None:
            app._start_tray_icon()
    app.mainloop()
