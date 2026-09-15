"""GUI para gestionar varias tareas de login automático (URL + credenciales +
programación), cada una registrable como su propia tarea programada de Windows.

Guarda las tareas cifradas (DPAPI) en %LOCALAPPDATA%\\AutoLogin\\tasks.json.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import config_store

_NET_DATE_RE = re.compile(r"/Date\((\d+)\)/")

DAYS = [
    ("Lu", "Monday"),
    ("Ma", "Tuesday"),
    ("Mi", "Wednesday"),
    ("Ju", "Thursday"),
    ("Vi", "Friday"),
    ("Sá", "Saturday"),
    ("Do", "Sunday"),
]
DAY_LABELS = {name: label for label, name in DAYS}

FONT = "Segoe UI"

BG = "#f3f4f8"
CARD_BG = "#ffffff"
BORDER = "#e3e5ee"
TEXT = "#1f2330"
MUTED = "#6b7280"
ACCENT = "#4f46e5"
ACCENT_DARK = "#4338ca"
ACCENT_LIGHT = "#eef0ff"
SUCCESS = "#0f7d3c"
DANGER = "#b3261e"
DANGER_LIGHT = "#fdecea"


def _days_display(day_names: list) -> str:
    return "".join(DAY_LABELS.get(d, "") for _, d in DAYS if d in day_names) or "-"


def _last_result_display(result: dict | None) -> str:
    if not result:
        return "—"
    icon = "✓" if result.get("success") else "✗"
    ts = result.get("timestamp", "")
    try:
        dt = datetime.datetime.fromisoformat(ts)
        ts_display = dt.strftime("%d/%m %H:%M")
    except ValueError:
        ts_display = ts
    return f"{icon} {ts_display}"


def _format_net_date(raw: str | None) -> str:
    """Convierte el formato /Date(ms)/ que usa ConvertTo-Json en PowerShell 5.1
    a texto legible dd/mm HH:MM."""
    if not raw:
        return "—"
    m = _NET_DATE_RE.match(raw)
    if not m:
        return "—"
    try:
        dt = datetime.datetime.fromtimestamp(int(m.group(1)) / 1000)
    except (ValueError, OSError):
        return "—"
    return dt.strftime("%d/%m %H:%M")


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
        label = tk.Label(
            tw, text=self.text, justify="left", background="#1f2330", foreground="white",
            font=(FONT, 8), padx=7, pady=4, wraplength=220,
        )
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
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.resizable(True, True)
        self.minsize(480, 560)
        self.configure(bg=BG)

        self.current_task_id = None

        self._setup_style()
        self._set_app_icon()

        # --- Cabecera ---
        header = ttk.Frame(self, style="Header.TFrame")
        header.pack(fill="x")
        header_row = ttk.Frame(header, style="Header.TFrame")
        header_row.pack(anchor="w", padx=20, pady=(16, 0))
        if self._logo_img is not None:
            ttk.Label(header_row, image=self._logo_img, style="Header.TFrame").pack(side="left", padx=(0, 10))
        ttk.Label(header_row, text=APP_NAME, style="Header.TLabel").pack(side="left")
        ttk.Label(
            header, text="Gestiona accesos web y prográmalos como tareas de Windows",
            style="SubHeader.TLabel"
        ).pack(anchor="w", padx=20, pady=(2, 16))

        # --- Contenedor con scroll (para que la ventana no dependa de caber
        #     entera en pantalla) ---
        scroll_container = ttk.Frame(self, style="TFrame")
        scroll_container.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        outer = ttk.Frame(canvas, padding=(16, 14, 16, 16), style="TFrame")
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
        list_card = ttk.Labelframe(outer, text="  Tareas guardadas  ", style="Card.TLabelframe", padding=12)
        list_card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        row += 1
        list_card.grid_columnconfigure(0, weight=1)

        add_row = ttk.Frame(list_card, style="Card.TFrame")
        add_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        add_row.grid_columnconfigure(0, weight=1)
        add_btn = ttk.Button(
            add_row, text="➕  Añadir tarea", style="AccentSmall.TButton", command=self.on_new_task
        )
        add_btn.grid(row=0, column=0, sticky="e")
        ToolTip(add_btn, "Limpia el formulario para crear una tarea nueva desde cero.")

        self.tree = ttk.Treeview(
            list_card, columns=("time", "days", "last", "next"), show="tree headings", height=5,
            selectmode="browse", style="Card.Treeview"
        )
        self.tree.heading("#0", text="Nombre")
        self.tree.heading("time", text="Hora")
        self.tree.heading("days", text="Días")
        self.tree.heading("last", text="Última ejecución")
        self.tree.heading("next", text="Próxima ejecución")
        self.tree.column("#0", width=140, stretch=True)
        self.tree.column("time", width=48, anchor="center", stretch=False)
        self.tree.column("days", width=85, anchor="center", stretch=False)
        self.tree.column("last", width=100, anchor="center", stretch=False)
        self.tree.column("next", width=105, anchor="center", stretch=False)
        self.tree.tag_configure("fail_row", background=DANGER_LIGHT)
        self.tree.tag_configure("paused_row", foreground=MUTED)

        tree_scroll_x = ttk.Scrollbar(list_card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=tree_scroll_x.set)
        self.tree.grid(row=1, column=0, sticky="ew")
        tree_scroll_x.grid(row=2, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        self.empty_hint = ttk.Label(
            list_card, text="No hay tareas todavía. Pulsa \"Añadir tarea\" para crear la primera.",
            style="Muted.TLabel"
        )

        # --- Detalles de acceso ---
        form_card = ttk.Labelframe(outer, text="  Detalles de acceso  ", style="Card.TLabelframe", padding=12)
        form_card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        row += 1
        form_card.grid_columnconfigure(0, weight=1)

        frow = 0
        mode_row = ttk.Frame(form_card, style="Card.TFrame")
        mode_row.grid(row=frow, column=0, sticky="ew", pady=(0, 10))
        mode_row.grid_columnconfigure(0, weight=1)
        self.mode_label = ttk.Label(mode_row, text="🆕  Nueva tarea", style="Mode.TLabel")
        self.mode_label.grid(row=0, column=0, sticky="w")
        self.screenshot_btn = ttk.Button(
            mode_row, text="🖼", style="IconGhost.TButton", width=3, command=self.on_view_screenshot
        )
        self.screenshot_btn.grid(row=0, column=1, sticky="e", padx=(0, 6))
        ToolTip(self.screenshot_btn, "Ver la última captura de pantalla guardada de un login fallido.")
        self.duplicate_btn = ttk.Button(
            mode_row, text="📋", style="IconGhost.TButton", width=3, command=self.on_duplicate_task
        )
        self.duplicate_btn.grid(row=0, column=2, sticky="e", padx=(0, 6))
        ToolTip(self.duplicate_btn, "Duplicar esta tarea como una tarea nueva (sin guardar todavía).")
        self.delete_btn = ttk.Button(
            mode_row, text="🗑", style="IconDanger.TButton", width=3, command=self.on_delete_task
        )
        self.delete_btn.grid(row=0, column=3, sticky="e")
        ToolTip(self.delete_btn, "Eliminar esta tarea y su tarea programada de Windows.")
        frow += 1

        ttk.Label(form_card, text="Nombre de la tarea", style="Card.TLabel").grid(
            row=frow, column=0, sticky="w", pady=(0, 3)
        )
        frow += 1
        self.name_var = tk.StringVar()
        ttk.Entry(form_card, textvariable=self.name_var).grid(row=frow, column=0, sticky="ew", pady=(0, 10))
        frow += 1

        ttk.Label(form_card, text="URL de la página", style="Card.TLabel").grid(
            row=frow, column=0, sticky="w", pady=(0, 3)
        )
        frow += 1
        self.url_var = tk.StringVar()
        ttk.Entry(form_card, textvariable=self.url_var).grid(row=frow, column=0, sticky="ew", pady=(0, 10))
        frow += 1

        ttk.Label(form_card, text="Usuario", style="Card.TLabel").grid(row=frow, column=0, sticky="w", pady=(0, 3))
        frow += 1
        self.user_var = tk.StringVar()
        ttk.Entry(form_card, textvariable=self.user_var).grid(row=frow, column=0, sticky="ew", pady=(0, 10))
        frow += 1

        ttk.Label(form_card, text="Contraseña", style="Card.TLabel").grid(
            row=frow, column=0, sticky="w", pady=(0, 3)
        )
        frow += 1
        self.pass_var = tk.StringVar()
        self.pass_entry = ttk.Entry(form_card, textvariable=self.pass_var, show="•")
        self.pass_entry.grid(row=frow, column=0, sticky="ew", pady=(0, 3))
        frow += 1

        self.show_pass_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form_card, text="Mostrar contraseña", variable=self.show_pass_var,
            command=self._toggle_password, style="Card.TCheckbutton"
        ).grid(row=frow, column=0, sticky="w", pady=(0, 8))
        frow += 1

        self.active_var = tk.BooleanVar(value=True)
        active_chk = ttk.Checkbutton(
            form_card, text="Tarea activa (programada en Windows)",
            variable=self.active_var, style="Card.TCheckbutton"
        )
        active_chk.grid(row=frow, column=0, sticky="w", pady=(0, 4))
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
        headless_chk.grid(row=frow, column=0, sticky="w", pady=(0, 4))
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
        keep_alive_chk.grid(row=frow, column=0, sticky="w", pady=(0, 4))
        ToolTip(
            keep_alive_chk,
            "Tras iniciar sesión, recarga la página periódicamente para evitar que el "
            "sitio cierre la sesión por inactividad (y reintenta el login si caduca).",
        )
        frow += 1
        self._keep_alive_row = frow
        frow += 1

        self.keep_alive_frame = ttk.Frame(form_card, style="Card.TFrame")
        ttk.Label(self.keep_alive_frame, text="Refrescar cada", style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.keep_alive_interval_var = tk.StringVar(value="5")
        ttk.Spinbox(
            self.keep_alive_frame, from_=1, to=120, width=4, textvariable=self.keep_alive_interval_var
        ).grid(row=0, column=1, padx=(6, 4))
        ttk.Label(self.keep_alive_frame, text="min", style="Card.TLabel").grid(
            row=0, column=2, sticky="w"
        )

        ttk.Label(self.keep_alive_frame, text="Dejar de mantenerla tras", style="Card.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )
        duration_row = ttk.Frame(self.keep_alive_frame, style="Card.TFrame")
        duration_row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.keep_alive_duration_hour_var = tk.StringVar(value="01")
        ttk.Spinbox(
            duration_row, from_=0, to=23, width=3, format="%02.0f",
            textvariable=self.keep_alive_duration_hour_var, wrap=True
        ).grid(row=0, column=0)
        ttk.Label(duration_row, text=":", style="Card.TLabel").grid(row=0, column=1, padx=3)
        self.keep_alive_duration_min_var = tk.StringVar(value="00")
        ttk.Spinbox(
            duration_row, from_=0, to=59, width=3, format="%02.0f",
            textvariable=self.keep_alive_duration_min_var, wrap=True
        ).grid(row=0, column=2)
        ttk.Label(duration_row, text="horas:min (0:00 = indefinido)", style="Muted.TLabel").grid(
            row=0, column=3, sticky="w", padx=(8, 0)
        )
        # self.keep_alive_frame se muestra/oculta con _toggle_keep_alive(); empieza oculto.

        self.adv_expanded = tk.BooleanVar(value=False)
        self.adv_toggle_btn = ttk.Button(
            form_card, text="▶  Avanzado (opcional): selectores CSS", style="Link.TButton",
            command=self._toggle_advanced
        )
        self.adv_toggle_btn.grid(row=frow, column=0, sticky="w", pady=(6, 0))
        ToolTip(
            self.adv_toggle_btn,
            "Indica manualmente los selectores CSS del formulario de login si la "
            "detección automática no encuentra bien los campos o el botón.",
        )
        frow += 1
        self._adv_row = frow
        frow += 1

        self.adv = ttk.Labelframe(form_card, text="Selectores CSS", style="Inner.TLabelframe", padding=10)
        self.adv.grid_columnconfigure(1, weight=1)

        ttk.Label(self.adv, text="Usuario", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.user_sel_var = tk.StringVar()
        ttk.Entry(self.adv, textvariable=self.user_sel_var).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(self.adv, text="Contraseña", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.pass_sel_var = tk.StringVar()
        ttk.Entry(self.adv, textvariable=self.pass_sel_var).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(self.adv, text="Botón enviar", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.submit_sel_var = tk.StringVar()
        ttk.Entry(self.adv, textvariable=self.submit_sel_var).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(
            self.adv, text="Déjalos vacíos para detección automática.",
            style="Muted.TLabel"
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        # self.adv se muestra/oculta con _toggle_advanced(); empieza contraído.

        # --- Programación ---
        sched = ttk.Labelframe(outer, text="  Programación de la tarea  ", style="Card.TLabelframe", padding=12)
        sched.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        row += 1

        ttk.Label(sched, text="Hora", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        time_frame = ttk.Frame(sched, style="Card.TFrame")
        time_frame.grid(row=0, column=1, sticky="w")
        self.hour_var = tk.StringVar(value="08")
        self.minute_var = tk.StringVar(value="00")
        ttk.Spinbox(
            time_frame, from_=0, to=23, width=3, format="%02.0f",
            textvariable=self.hour_var, wrap=True
        ).grid(row=0, column=0)
        ttk.Label(time_frame, text=":", style="Card.TLabel").grid(row=0, column=1, padx=3)
        ttk.Spinbox(
            time_frame, from_=0, to=59, width=3, format="%02.0f",
            textvariable=self.minute_var, wrap=True
        ).grid(row=0, column=2)

        ttk.Label(sched, text="Días", style="Card.TLabel").grid(row=1, column=0, sticky="nw", padx=(0, 8), pady=(10, 0))
        days_frame = ttk.Frame(sched, style="Card.TFrame")
        days_frame.grid(row=1, column=1, sticky="w", pady=(10, 0))
        self.day_vars = {}
        for i, (label, day_name) in enumerate(DAYS):
            var = tk.BooleanVar(value=True)
            self.day_vars[day_name] = var
            ttk.Checkbutton(
                days_frame, text=label, variable=var, style="Day.TCheckbutton"
            ).grid(row=0, column=i, padx=2)

        # --- Guardar / Probar ---
        btn_frame = ttk.Frame(outer, style="TFrame")
        btn_frame.grid(row=row, column=0, pady=(0, 10))
        row += 1

        self.save_btn = ttk.Button(
            btn_frame, text="💾  Guardar", style="Accent.TButton", command=self.on_save
        )
        self.save_btn.grid(row=0, column=0, padx=(0, 8))
        ToolTip(self.save_btn, "Guarda esta tarea y crea/actualiza su tarea programada en Windows.")
        self.test_btn = ttk.Button(
            btn_frame, text="▶  Probar ahora", style="Secondary.TButton", command=self.on_test
        )
        self.test_btn.grid(row=0, column=1)
        ToolTip(self.test_btn, "Guarda esta tarea y ejecuta un login de prueba ahora mismo.")

        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(outer, textvariable=self.status_var, style="Success.TLabel", wraplength=430)
        self.status_label.grid(row=row, column=0, sticky="w", pady=(0, 0))
        row += 1

        self._refresh_task_list()
        self._clear_form()

        self.update_idletasks()
        content_width = outer.winfo_reqwidth() + scrollbar.winfo_reqwidth() + 4
        content_height = outer.winfo_reqheight()
        max_height = min(content_height, self.winfo_screenheight() - 120, 760)
        self.geometry(f"{max(content_width, 480)}x{max(max_height, 480)}")

    # --- Icono ---

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

    # --- Estilo ---

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD_BG)

        style.configure("Header.TFrame", background=ACCENT)
        style.configure("Header.TLabel", background=ACCENT, foreground="white", font=(FONT, 16, "bold"))
        style.configure("SubHeader.TLabel", background=ACCENT, foreground="#e3e2ff", font=(FONT, 9))

        style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT, 10))
        style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT, font=(FONT, 10))
        style.configure("Muted.TLabel", background=CARD_BG, foreground=MUTED, font=(FONT, 8))
        style.configure("Success.TLabel", background=BG, foreground=SUCCESS, font=(FONT, 9, "bold"))
        style.configure("Danger.TLabel", background=BG, foreground=DANGER, font=(FONT, 9, "bold"))
        style.configure("Info.TLabel", background=CARD_BG, foreground=ACCENT_DARK, font=(FONT, 9, "bold"))
        style.configure("Mode.TLabel", background=CARD_BG, foreground=ACCENT_DARK, font=(FONT, 11, "bold"))

        style.configure(
            "Card.TLabelframe", background=CARD_BG, bordercolor=BORDER,
            relief="solid", borderwidth=1
        )
        style.configure(
            "Card.TLabelframe.Label", background=CARD_BG, foreground=ACCENT,
            font=(FONT, 10, "bold")
        )
        style.configure(
            "Inner.TLabelframe", background="#f8f9fd", bordercolor=BORDER,
            relief="solid", borderwidth=1
        )
        style.configure(
            "Inner.TLabelframe.Label", background="#f8f9fd", foreground=MUTED,
            font=(FONT, 9, "bold")
        )

        style.configure(
            "TCheckbutton", background=BG, foreground=TEXT, font=(FONT, 10)
        )
        style.configure(
            "Card.TCheckbutton", background=CARD_BG, foreground=TEXT, font=(FONT, 10)
        )
        style.configure(
            "Day.TCheckbutton", background=CARD_BG, foreground=TEXT, font=(FONT, 9)
        )
        for st in ("TCheckbutton", "Card.TCheckbutton", "Day.TCheckbutton"):
            style.map(st, background=[("active", CARD_BG)], foreground=[("active", ACCENT)])

        style.configure(
            "TEntry", fieldbackground="white", foreground=TEXT,
            bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
            padding=7, relief="solid"
        )
        style.map("TEntry", bordercolor=[("focus", ACCENT)])

        style.configure(
            "TSpinbox", fieldbackground="white", foreground=TEXT,
            bordercolor=BORDER, arrowsize=12, padding=4
        )

        # Botones
        style.configure(
            "Accent.TButton", font=(FONT, 9, "bold"), padding=(14, 8),
            background=ACCENT, foreground="white", borderwidth=0, relief="flat"
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", "#c9c8e8"), ("active", ACCENT_DARK), ("pressed", ACCENT_DARK)],
            foreground=[("disabled", "#f1f1fb")],
        )

        style.configure(
            "Secondary.TButton", font=(FONT, 9), padding=(14, 8),
            background="#e9eaf2", foreground=TEXT, borderwidth=0, relief="flat"
        )
        style.map("Secondary.TButton", background=[("active", "#dcdeed"), ("pressed", "#cfd1e6")])

        style.configure(
            "AccentSmall.TButton", font=(FONT, 8, "bold"), padding=(9, 4),
            background=ACCENT, foreground="white", borderwidth=0, relief="flat"
        )
        style.map(
            "AccentSmall.TButton",
            background=[("active", ACCENT_DARK), ("pressed", ACCENT_DARK)],
        )

        style.configure(
            "IconDanger.TButton", font=(FONT, 9), padding=(4, 2),
            background=CARD_BG, foreground=DANGER, borderwidth=1,
            relief="solid", bordercolor=BORDER
        )
        style.map(
            "IconDanger.TButton",
            background=[("active", DANGER_LIGHT)],
            bordercolor=[("active", DANGER)],
        )

        style.configure(
            "IconGhost.TButton", font=(FONT, 9), padding=(4, 2),
            background=CARD_BG, foreground=ACCENT_DARK, borderwidth=1,
            relief="solid", bordercolor=BORDER
        )
        style.map(
            "IconGhost.TButton",
            background=[("active", ACCENT_LIGHT)],
            bordercolor=[("active", ACCENT)],
        )

        style.configure(
            "Ghost.TButton", font=(FONT, 9), padding=(10, 5),
            background=CARD_BG, foreground=ACCENT_DARK, borderwidth=1,
            relief="solid", bordercolor=BORDER
        )
        style.map(
            "Ghost.TButton",
            background=[("active", ACCENT_LIGHT)],
            bordercolor=[("active", ACCENT)],
        )

        style.configure(
            "GhostDanger.TButton", font=(FONT, 9), padding=(10, 5),
            background=CARD_BG, foreground=DANGER, borderwidth=1,
            relief="solid", bordercolor=BORDER
        )
        style.map(
            "GhostDanger.TButton",
            background=[("active", DANGER_LIGHT)],
            bordercolor=[("active", DANGER)],
        )

        style.configure(
            "Link.TButton", font=(FONT, 9), padding=(0, 4),
            background=CARD_BG, foreground=ACCENT_DARK, borderwidth=0, relief="flat"
        )
        style.map("Link.TButton", background=[("active", CARD_BG)], foreground=[("active", ACCENT)])

        # Treeview
        style.configure(
            "Card.Treeview", background="white", fieldbackground="white",
            foreground=TEXT, rowheight=26, font=(FONT, 9), borderwidth=0
        )
        style.configure(
            "Card.Treeview.Heading", background=ACCENT_LIGHT, foreground=ACCENT_DARK,
            font=(FONT, 9, "bold"), relief="flat", borderwidth=0
        )
        style.map(
            "Card.Treeview",
            background=[("selected", ACCENT_LIGHT)],
            foreground=[("selected", ACCENT_DARK)],
        )
        style.map("Card.Treeview.Heading", background=[("active", ACCENT_LIGHT)])

    # --- Utilidades de UI ---

    def _toggle_password(self):
        self.pass_entry.configure(show="" if self.show_pass_var.get() else "•")

    def _toggle_keep_alive(self):
        if self.keep_alive_var.get():
            self.keep_alive_frame.grid(row=self._keep_alive_row, column=0, sticky="w", pady=(0, 8))
        else:
            self.keep_alive_frame.grid_remove()
        self._resize_to_content()

    def _toggle_advanced(self):
        expanded = not self.adv_expanded.get()
        self.adv_expanded.set(expanded)
        if expanded:
            self.adv.grid(row=self._adv_row, column=0, sticky="ew", pady=(8, 0))
            self.adv_toggle_btn.configure(text="▼  Avanzado (opcional): selectores CSS")
        else:
            self.adv.grid_remove()
            self.adv_toggle_btn.configure(text="▶  Avanzado (opcional): selectores CSS")
        self._resize_to_content()

    def _resize_to_content(self):
        # El contenido vive dentro de un canvas con scroll, así que basta con
        # dejar que su <Configure> recalcule la scrollregion; no hace falta
        # redimensionar la ventana.
        self.update_idletasks()

    # --- Lista de tareas ---

    def _refresh_task_list(self, select_id: str | None = None):
        self.tree.delete(*self.tree.get_children())
        tasks = config_store.load_tasks()
        active_ids = []
        for task in tasks:
            active = task.get("active", True)
            last_result = config_store.load_last_result(task["id"])
            tags = []
            if last_result and not last_result.get("success"):
                tags.append("fail_row")
            if not active:
                tags.append("paused_row")
            self.tree.insert(
                "", "end", iid=task["id"],
                text=task.get("name") or task.get("url", ""),
                values=(
                    task.get("schedule_time", ""),
                    _days_display(task.get("schedule_days", [])),
                    _last_result_display(last_result),
                    "Pausada" if not active else "…",
                ),
                tags=tuple(tags),
            )
            if active:
                active_ids.append(task["id"])
        if select_id and self.tree.exists(select_id):
            self.tree.selection_set(select_id)
            self.tree.see(select_id)

        if tasks:
            self.empty_hint.grid_remove()
        else:
            self.empty_hint.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._resize_to_content()

        if active_ids:
            threading.Thread(target=self._fetch_next_runs, args=(active_ids,), daemon=True).start()

    def _fetch_next_runs(self, task_ids: list):
        script_dir = os.path.dirname(os.path.abspath(__file__))
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

    def _on_tree_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        task_id = selection[0]
        data = config_store.get_task(task_id)
        if not data:
            return
        self.current_task_id = task_id
        self._populate_form(data)

    def on_new_task(self):
        self.tree.selection_remove(self.tree.selection())
        self._clear_form()

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
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ps_script = os.path.join(script_dir, "unregister_task.ps1")
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script, "-TaskId", task_id],
            cwd=script_dir, capture_output=True, text=True,
        )

    def _refresh_screenshot_button(self):
        if self.current_task_id and os.path.exists(config_store.screenshot_path(self.current_task_id)):
            self.screenshot_btn.grid()
        else:
            self.screenshot_btn.grid_remove()

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
        self.mode_label.configure(text="🆕  Nueva tarea (copia sin guardar)")
        self.delete_btn.grid_remove()
        self.duplicate_btn.grid_remove()
        self.screenshot_btn.grid_remove()
        self.status_var.set("Revisa los datos y pulsa Guardar para crear la copia como tarea independiente.")

    def _clear_form(self):
        self.current_task_id = None
        self.name_var.set("")
        self.url_var.set("")
        self.user_var.set("")
        self.pass_var.set("")
        self.active_var.set(True)
        self.headless_var.set(True)
        self.keep_alive_var.set(False)
        self.keep_alive_interval_var.set("5")
        self.keep_alive_duration_hour_var.set("01")
        self.keep_alive_duration_min_var.set("00")
        self.keep_alive_frame.grid_remove()
        self.user_sel_var.set("")
        self.pass_sel_var.set("")
        self.submit_sel_var.set("")
        self.hour_var.set("08")
        self.minute_var.set("00")
        for var in self.day_vars.values():
            var.set(True)
        self.status_var.set("")
        self.mode_label.configure(text="🆕  Nueva tarea")
        self.delete_btn.grid_remove()
        self.duplicate_btn.grid_remove()
        self.screenshot_btn.grid_remove()

    def _populate_form(self, data: dict):
        self.name_var.set(data.get("name", ""))
        self.url_var.set(data.get("url", ""))
        self.user_var.set(data.get("username", ""))
        self.pass_var.set(data.get("password", ""))
        self.active_var.set(data.get("active", True))
        self.headless_var.set(data.get("headless", True))
        self.keep_alive_var.set(data.get("keep_alive", False))
        self.keep_alive_interval_var.set(str(data.get("keep_alive_interval_min", 5)))
        duration_total = data.get("keep_alive_duration_min", 60)
        self.keep_alive_duration_hour_var.set(f"{duration_total // 60:02d}")
        self.keep_alive_duration_min_var.set(f"{duration_total % 60:02d}")
        if self.keep_alive_var.get():
            self.keep_alive_frame.grid(row=self._keep_alive_row, column=0, sticky="w", pady=(0, 8))
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

        self.status_var.set("")
        self.mode_label.configure(text=f"✏️  Editando: {data.get('name') or data.get('url', '')}")
        self.delete_btn.grid()
        self.duplicate_btn.grid()
        self._refresh_screenshot_button()

    # --- Guardar / validar ---

    def _selected_days(self) -> list:
        return [day_name for day_name, var in self.day_vars.items() if var.get()]

    def _schedule_time_str(self) -> str:
        return f"{int(self.hour_var.get()):02d}:{int(self.minute_var.get()):02d}"

    def _validate(self) -> bool:
        if not self.url_var.get().strip():
            messagebox.showerror("Falta la URL", "Introduce la URL de la página.")
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
        return True

    def _save(self) -> bool:
        if not self._validate():
            return False
        name = self.name_var.get().strip() or self.url_var.get().strip()
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
            keep_alive=self.keep_alive_var.get(),
            keep_alive_interval_min=int(self.keep_alive_interval_var.get() or 5),
            keep_alive_duration_min=(
                int(self.keep_alive_duration_hour_var.get() or 0) * 60
                + int(self.keep_alive_duration_min_var.get() or 0)
            ),
            active=self.active_var.get(),
        )
        self.current_task_id = task_id
        self.name_var.set(name)
        self._refresh_task_list(select_id=task_id)
        return True

    def on_save(self):
        if not self._save():
            return
        active = self.active_var.get()
        self.status_label.configure(style="Info.TLabel")
        self.status_var.set("Guardando y programando..." if active else "Guardando y pausando...")
        self.save_btn.configure(state="disabled")
        threading.Thread(
            target=self._save_and_sync_schedule_thread,
            args=(self.current_task_id, active, self._schedule_time_str(), self._selected_days()),
            daemon=True,
        ).start()

    def _save_and_sync_schedule_thread(self, task_id: str, active: bool, time_str: str, days: list):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if active:
            ps_script = os.path.join(script_dir, "register_task.ps1")
            args = ["-TaskId", task_id, "-Time", time_str, "-Days", ",".join(days)]
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
        self.status_label.configure(style="Success.TLabel" if ok else "Danger.TLabel")
        self.status_var.set(message)
        if not ok:
            messagebox.showwarning("Resultado de la programación", message)

    # --- Probar ahora ---

    def on_test(self):
        if not self._save():
            return
        self.status_label.configure(style="Info.TLabel")
        self.status_var.set("Ejecutando prueba de login...")
        self.test_btn.configure(state="disabled")
        threading.Thread(target=self._run_test, args=(self.current_task_id,), daemon=True).start()

    def _run_test(self, task_id: str):
        result = subprocess.run(
            [sys.executable, "run_login.py", task_id, "--no-keep-alive"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True,
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
        self.status_label.configure(style="Success.TLabel" if ok else "Danger.TLabel")
        self.status_var.set(message)
        if not ok:
            messagebox.showwarning("Resultado de la prueba", message)


if __name__ == "__main__":
    App().mainloop()
