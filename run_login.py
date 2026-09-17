"""Abre la URL de una tarea guardada e inicia sesión con sus credenciales.

Uso: python run_login.py <task_id> [--no-keep-alive] [--detect-only]

--detect-only navega a la URL y busca los campos de usuario/contraseña/botón
sin rellenar ni enviar nada (para validar selectores sin arriesgar un
bloqueo por intento de login fallido).

Pensado para ejecutarse desde la GUI (botón "Probar ahora") o desde una
tarea programada de Windows. Registra el resultado en logs/<task_id>.log y,
si algo falla, guarda una captura (logs/<task_id>_error.png) para diagnosticarlo.

Si la tarea tiene activado "mantener sesión activa", tras un login exitoso
el proceso se queda recargando la página periódicamente (en vez de cerrar el
navegador enseguida) para evitar que el sitio cierre la sesión por
inactividad. --no-keep-alive lo desactiva puntualmente (lo usa la GUI al
pulsar "Probar ahora" para no bloquear la interfaz).
"""
import datetime
import os
import random
import subprocess
import sys
import time
import traceback
import urllib.parse

# Debe fijarse ANTES de importar playwright: en el .exe empaquetado (PyInstaller),
# Playwright resuelve la carpeta de navegadores de forma relativa a la carpeta
# temporal de extracción en vez de la caché habitual, y no encuentra el Chromium
# ya descargado con "playwright install". Forzamos siempre la ruta estándar.
def _default_browsers_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ms-playwright")


if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _default_browsers_path()

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

import config_store
import task_lock
from app_logic import _in_time_window

try:
    from win11toast import toast as _toast
except Exception:
    _toast = None

# Selectores probados en orden hasta encontrar el primero que exista en la página.
USER_SELECTOR_CANDIDATES = [
    "input[type='email']",
    "input[type='text'][name*='user' i]",
    "input[name*='user' i]",
    "input[id*='user' i]",
    "input[name*='email' i]",
    "input[id*='email' i]",
    "input[name*='login' i]",
    "input[id*='login' i]",
]
PASS_SELECTOR_CANDIDATES = [
    "input[type='password']",
]
SUBMIT_SELECTOR_CANDIDATES = [
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Iniciar sesión')",
    "button:has-text('Log in')",
    "button:has-text('Login')",
    "button:has-text('Sign in')",
    # Botones tipo <input type="button"> controlados por JS (comunes en Moodle/IOMAD)
    "input[type='button'][value*='entrar' i]",
    "input[type='button'][value*='iniciar' i]",
    "input[type='button'][value*='acceder' i]",
    "input[type='button'][value*='login' i]",
    "input[id*='entrar' i]",
    "input[id*='login' i]",
    "a:has-text('Iniciar sesión')",
]
# Botones de confirmación de cuadros de diálogo (SweetAlert y similares) que
# pueden aparecer al iniciar sesión, p.ej. "¿Cerrar tu otra sesión activa?".
DIALOG_CONFIRM_CANDIDATES = [
    ".swal2-confirm",
    ".swal-button--confirm",
    ".sweet-alert button.confirm",
]

_LOG_FILE = None
_DEFAULT_MAX_LOG_MB = 2
_LOG_LINES_KEPT_ON_ROTATE = 2000


def init_logging(task_id: str) -> None:
    global _LOG_FILE
    os.makedirs(config_store.LOG_DIR, exist_ok=True)
    _LOG_FILE = config_store.log_path(task_id)


def _rotate_log_if_needed() -> None:
    """Evita que el .log crezca sin límite: si supera el tamaño configurado
    (por defecto 2MB, ajustable en Configuración), se queda solo con las
    últimas líneas."""
    try:
        max_mb = config_store.load_settings().get("log_max_mb", _DEFAULT_MAX_LOG_MB)
        max_bytes = max(1, max_mb) * 1024 * 1024
        if os.path.getsize(_LOG_FILE) <= max_bytes:
            return
        with open(_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        with open(_LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines[-_LOG_LINES_KEPT_ON_ROTATE:])
    except OSError:
        pass


def log(message: str) -> None:
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{timestamp}] {message}"
    try:
        print(line)
    except Exception:
        pass  # sin consola en el .exe empaquetado (--windowed): no hay stdout
    if _LOG_FILE:
        if os.path.exists(_LOG_FILE):
            _rotate_log_if_needed()
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def find_first(page, explicit_selector: str, candidates: list[str], timeout_ms: int = 8000):
    selectors = [explicit_selector] if explicit_selector else candidates
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator, selector
        except PlaywrightTimeoutError:
            continue
        except PlaywrightError as exc:
            # Selector CSS inválido u otro error de sintaxis: no reintentar
            # el resto como si fuera "no encontrado", avisar en el log.
            log(f"Selector no válido '{selector}': {exc}")
            if explicit_selector:
                return None, None
            continue
    return None, None


def dismiss_dialog_if_present(page) -> bool:
    """Si aparece un cuadro de diálogo de confirmación (p.ej. sesión activa), lo acepta.

    El clic usa un timeout corto y tolera fallos: a veces la página ya está
    navegando (login correcto) justo cuando intentamos pulsar el diálogo, y
    el botón queda "detached"/inestable. Eso no debe tumbar el login."""
    btn, sel = find_first(page, "", DIALOG_CONFIRM_CANDIDATES, timeout_ms=2500)
    if not btn:
        return False
    try:
        btn.click(timeout=5000)
        log(f"Se detectó y aceptó un cuadro de diálogo (selector: {sel}).")
    except PlaywrightError as exc:
        log(
            f"Se detectó un cuadro de diálogo (selector: {sel}) pero no se pudo pulsar a tiempo "
            f"(probablemente la página ya estaba navegando tras un login correcto): {exc}"
        )
    return True


def collect_error_hints(page) -> str:
    hints = []
    for selector in [".loginerrors", ".alert-danger", ".error", "[role='alert']"]:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=1000):
                text = locator.inner_text().strip()
                if text:
                    hints.append(f"{selector}: {text}")
        except Exception:
            continue
    return " | ".join(hints)


def notify_failure(cfg: dict, message: str) -> None:
    """Muestra una notificación de Windows. No debe romper la ejecución si falla."""
    if _toast is None:
        return
    if not config_store.load_settings().get("notifications_enabled", True):
        return
    try:
        _toast(f"AutoLogin: {cfg.get('name', cfg.get('url', ''))}", message, duration="long")
    except Exception as exc:
        log(f"No se pudo mostrar la notificación de Windows: {exc}")


def ensure_chromium_installed() -> bool:
    """Descarga Chromium de Playwright si aún no está instalado (equivale a
    'playwright install chromium').

    En desarrollo usa 'python -m playwright'. En el .exe empaquetado
    (PyInstaller, sys.frozen) no hay intérprete Python, así que se invoca
    directamente el driver incluido (node + cli.js), que es lo mismo que
    ejecuta 'python -m playwright' por dentro."""
    try:
        log("Chromium no está instalado; descargándolo (puede tardar uno o dos minutos)...")
        if getattr(sys, "frozen", False):
            try:
                from playwright._impl._driver import compute_driver_executable, get_driver_env
            except Exception as exc:
                log(f"No se pudo localizar el instalador interno de Playwright: {exc}")
                return False
            try:
                driver_exe, driver_cli = compute_driver_executable()
            except Exception as exc:
                log(f"No se encontró el driver de Playwright dentro del .exe: {exc}")
                return False
            cmd = [driver_exe, driver_cli, "install", "chromium"]
            merged_env = os.environ.copy()
            try:
                merged_env.update(get_driver_env())
            except Exception:
                pass
            # PLAYWRIGHT_BROWSERS_PATH ya está en os.environ (se fijó al
            # arrancar); se propaga vía merged_env para que el driver
            # descargue en la misma carpeta que luego usa el launch.
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=600, env=merged_env,
            )
        else:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=600,
            )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            log(f"La descarga de Chromium terminó con errores: {detail}")
            return False
        log("Chromium instalado correctamente.")
        return True
    except Exception as exc:
        log(f"No se pudo instalar Chromium automáticamente: {exc}")
        return False


def backoff_wait(attempt: int, base: float = 5, cap: float = 60) -> None:
    """Espera progresiva entre reintentos (5s, 10s, 20s, ... hasta `cap`)."""
    time.sleep(min(base * (2 ** (attempt - 1)), cap))


def parse_iso_date(value: str) -> datetime.date | None:
    """Convierte 'YYYY-MM-DD' en date, o None si está vacío o es inválido."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def _in_schedule_range(cfg: dict, today: datetime.date) -> tuple[bool, str]:
    """Vigencia por fechas SIN avisar (para chequeos frecuentes del keep-alive,
    donde el aviso ya se dio una vez al arrancar)."""
    start_raw = (cfg.get("schedule_start_date") or "").strip()
    end_raw = (cfg.get("schedule_end_date") or "").strip()
    start = parse_iso_date(start_raw) if start_raw else None
    end = parse_iso_date(end_raw) if end_raw else None
    if start and today < start:
        return False, f"aún no vigente (empieza el {start.isoformat()})"
    if end and today > end:
        return False, f"vigencia terminada (terminó el {end.isoformat()})"
    return True, ""


def check_schedule_dates(cfg: dict, today: datetime.date | None = None) -> tuple[bool, str]:
    """Comprueba la vigencia por fechas de la tarea.

    Devuelve (dentro_de_vigencia, motivo). Sin fechas configuradas siempre
    está vigente. Una fecha inválida se ignora (no bloquea) pero se avisa."""
    today = today or datetime.date.today()
    start_raw = (cfg.get("schedule_start_date") or "").strip()
    end_raw = (cfg.get("schedule_end_date") or "").strip()
    if start_raw and parse_iso_date(start_raw) is None:
        log(f"AVISO: fecha de inicio '{start_raw}' no válida (se ignora, usa YYYY-MM-DD).")
    if end_raw and parse_iso_date(end_raw) is None:
        log(f"AVISO: fecha de fin '{end_raw}' no válida (se ignora, usa YYYY-MM-DD).")
    return _in_schedule_range(cfg, today)


def _is_http_url(url: str) -> bool:
    """Comprueba que sea una URL http(s) completa (para keep_alive_url)."""
    try:
        parsed = urllib.parse.urlparse((url or "").strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def goto_keep_alive_url(page, cfg: dict) -> bool:
    """Si la tarea define `keep_alive_url`, navega a ella tras el login para
    que el keep-alive mantenga la sesión en esa página de trabajo (p. ej. el
    curso o panel que interesa) en vez de en la del login.

    Devuelve True si no había URL o la navegación fue bien; False si la URL
    no era válida o no se pudo abrir (no es fatal: se sigue con la página
    actual y el mantenimiento la conserva igualmente)."""
    target = (cfg.get("keep_alive_url") or "").strip()
    if not target:
        return True
    if not _is_http_url(target):
        log(f"AVISO: keep_alive_url no válida ('{target}'): se mantiene la página actual.")
        return False
    try:
        log(f"Abriendo página de trabajo tras el login: {target}")
        page.goto(target, wait_until="load", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            pass
        log(f"Página de trabajo lista. URL actual: {page.url}")
        return True
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        log(f"AVISO: no se pudo abrir keep_alive_url ({exc}); se mantiene la página actual.")
        return False


def detect_only(page, cfg: dict) -> str:
    """Navega a la URL e intenta localizar los campos de login SIN rellenar
    ni enviar nada. Sirve para validar los selectores de una tarea nueva sin
    arriesgarse a un bloqueo por intento de login fallido."""
    log(f"Abriendo {cfg['url']} (solo detección, no se enviará ningún dato)")
    page.goto(cfg["url"], wait_until="load", timeout=30000)

    user_field, user_sel = find_first(page, cfg.get("user_selector", ""), USER_SELECTOR_CANDIDATES)
    log(f"Campo usuario: {'encontrado (' + user_sel + ')' if user_field else 'NO encontrado'}")

    pass_field, pass_sel = find_first(page, cfg.get("pass_selector", ""), PASS_SELECTOR_CANDIDATES)
    log(f"Campo contraseña: {'encontrado (' + pass_sel + ')' if pass_field else 'NO encontrado'}")

    submit_btn, submit_sel = find_first(
        page, cfg.get("submit_selector", ""), SUBMIT_SELECTOR_CANDIDATES, timeout_ms=3000
    )
    if submit_btn:
        log(f"Botón de envío: encontrado ({submit_sel})")
    else:
        log("Botón de envío: no encontrado (se usaría Enter en su lugar)")

    return "success" if (user_field and pass_field) else "failed"


def perform_login(page, cfg: dict, expect_login_form: bool = True):
    """Rellena el formulario y envía el login. Devuelve (estado, pass_sel):
    estado es 'success', 'failed' o 'closed' (la pestaña se cerró tras enviar,
    lo cual en varios sitios es una señal de éxito, no de fallo).

    Si expect_login_form=False (hay una sesión guardada de una ejecución
    anterior), primero comprueba con un timeout corto si el campo de
    contraseña sigue ahí; si no aparece, asume que la sesión guardada sigue
    siendo válida y no hace falta volver a iniciar sesión."""
    log(f"Abriendo {cfg['url']}")
    page.goto(cfg["url"], wait_until="load", timeout=30000)

    if not expect_login_form:
        _, quick_pass_sel = find_first(
            page, cfg.get("pass_selector", ""), PASS_SELECTOR_CANDIDATES, timeout_ms=4000
        )
        if not quick_pass_sel:
            log("Sesión reutilizada desde una ejecución anterior; no hizo falta volver a iniciar sesión.")
            return "success", None

    user_field, user_sel = find_first(page, cfg.get("user_selector", ""), USER_SELECTOR_CANDIDATES)
    if not user_field:
        log("ERROR: no se encontró el campo de usuario.")
        return "failed", None
    user_field.fill(cfg["username"])
    log(f"Usuario rellenado (selector: {user_sel})")

    pass_field, pass_sel = find_first(page, cfg.get("pass_selector", ""), PASS_SELECTOR_CANDIDATES)
    if not pass_field:
        log("ERROR: no se encontró el campo de contraseña.")
        return "failed", None
    pass_field.fill(cfg["password"])
    log(f"Contraseña rellenada (selector: {pass_sel})")

    submit_btn, submit_sel = find_first(
        page, cfg.get("submit_selector", ""), SUBMIT_SELECTOR_CANDIDATES, timeout_ms=3000
    )
    if submit_btn:
        submit_btn.click()
        log(f"Clic en botón de envío (selector: {submit_sel})")
    else:
        pass_field.press("Enter")
        log("No se encontró botón de envío; se envió con Enter.")

    try:
        # Algunos sitios cierran la pestaña de login tras un envío exitoso
        # (p.ej. abren el campus en una ventana nueva). Lo tratamos como
        # éxito en vez de un error.
        dismiss_dialog_if_present(page)

        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except PlaywrightTimeoutError:
            pass

        if dismiss_dialog_if_present(page):
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except PlaywrightTimeoutError:
                pass

        # En SPAs el formulario puede tardar en desaparecer tras un envío
        # correcto: espera explícita a que el campo de contraseña se oculte
        # antes de decidir entre éxito/fracaso (evita falsos positivos).
        still_on_login = False
        if pass_sel:
            try:
                page.locator(pass_sel).first.wait_for(state="hidden", timeout=4000)
                still_on_login = False
            except PlaywrightTimeoutError:
                try:
                    still_on_login = page.locator(pass_sel).first.is_visible()
                except PlaywrightError:
                    still_on_login = False

        if still_on_login:
            return "failed", pass_sel

        log(f"Login completado. URL final: {page.url}")
        return "success", pass_sel
    except PlaywrightError:
        if page.is_closed():
            log(
                "Login probablemente exitoso: la pestaña se cerró justo después de "
                "enviar el formulario (algunos sitios abren el destino en una ventana "
                "nueva y cierran la de login)."
            )
            return "closed", pass_sel
        raise


# Señales en URL/título de que hemos caído a una página de login.
_LOGIN_URL_HINTS = ("login", "signin", "sign-in", "log-in", "logon", "auth",
                    "sesion", "sesión", "acceder", "iniciar", "logout",
                    "expired", "expire", "timeout", "reauth")

# Textos visibles que delatan una sesión caducada (varios idiomas, en minúsculas).
_SESSION_EXPIRED_TEXTS = (
    "sesión expirada", "sesion expirada", "sesión caducada", "sesion caducada",
    "sesión ha expirado", "sesion ha expirado", "tu sesión ha finalizado",
    "sesión finalizada", "vuelva a iniciar sesión", "vuelve a iniciar sesión",
    "inicie sesión de nuevo", "session expired", "session has expired",
    "session timed out", "your session has ended", "sign in again",
    "log in again", "please log in", "please sign in",
    "authentication required", "sessão expirada",
)


def _any_password_visible(page, timeout_ms: int = 1500) -> bool:
    """Dice si hay algún campo de contraseña visible (señal genérica de login)."""
    try:
        return bool(page.locator("input[type='password']").first.is_visible(timeout=timeout_ms))
    except (PlaywrightError, PlaywrightTimeoutError):
        return False
    except Exception:
        return False


def _page_body_text(page, timeout_ms: int = 3000) -> str:
    """Texto visible de la página en minúsculas ('' si no se puede leer)."""
    try:
        return (page.locator("body").first.inner_text(timeout=timeout_ms) or "").lower()
    except (PlaywrightError, PlaywrightTimeoutError):
        return ""
    except Exception:
        return ""


def _same_page(url_a: str, url_b: str) -> bool:
    """Compara URLs ignorando el fragmento (#...) y la barra final."""
    def _norm(url: str) -> str:
        return (url or "").split("#")[0].rstrip("/") or ""
    return bool(_norm(url_a)) and _norm(url_a) == _norm(url_b)


def is_session_expired(page, pass_sel: str | None = None, home_url: str | None = None) -> bool:
    """Detecta sesión caducada con tres señales (en orden, de barata a cara):

    1. El campo de contraseña original vuelve a ser visible, o
    2. aparece cualquier campo de contraseña en una página DISTINTA a la que
       quedó tras el login (`home_url`), o
    3. la URL/título huele a login Y el cuerpo menciona caducidad de sesión.

    El ancla `home_url` evita falsos positivos (p. ej. un modal de "cambiar
    contraseña" sobre la propia página de trabajo).
    """
    if pass_sel:
        try:
            if page.locator(pass_sel).first.is_visible():
                return True
        except (PlaywrightError, PlaywrightTimeoutError):
            pass
        except Exception:
            pass
    try:
        current_url = page.url
    except Exception:
        current_url = ""
    if _any_password_visible(page):
        if home_url and _same_page(current_url, home_url):
            pass  # misma página: probablemente un formulario propio, no caducidad
        else:
            return True
    try:
        haystack = f"{current_url} {page.title()}".lower()
    except Exception:
        return False
    if not any(hint in haystack for hint in _LOGIN_URL_HINTS):
        return False
    body = _page_body_text(page)
    return bool(body) and any(text in body for text in _SESSION_EXPIRED_TEXTS)


def _jittered_interval(base_min: float, jitter_ratio: float = 0.15) -> float:
    """Intervalo con variación aleatoria ±jitter para no parecer un robot con
    cadencia exacta. Devuelve minutos."""
    jitter = random.uniform(-jitter_ratio, jitter_ratio)
    return max(1.0, base_min * (1 + jitter))


def _as_int(value, default: int) -> int:
    """Convierte a int con tolerancia (config corrupta no debe tumbar el runner)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _next_wait_min(interval_min: float, remaining_min: float | None = None) -> float:
    """Próxima espera con jitter, acotada al tiempo restante si hay deadline."""
    wait_min = _jittered_interval(interval_min)
    if remaining_min is not None:
        wait_min = min(wait_min, max(0.0, remaining_min))
    return wait_min


def _backoff_sleep(attempt: int, sleeper, base: float = 5, cap: float = 60) -> None:
    """Espera progresiva entre reintentos con `sleeper` inyectable (testeable)."""
    sleeper(min(base * (2 ** (attempt - 1)), cap))


_KEEPALIVE_QUANTUM_SEC = 60
_KEEPALIVE_MAX_CONSECUTIVE_FAILURES = 3


def _wait_interruptible(cfg: dict, total_sec: float, sleeper=time.sleep) -> tuple[bool, str]:
    """Espera `total_sec` por tramos revisando la vigencia por fechas.

    Devuelve (True, '') si se completó, o (False, motivo) si la vigencia
    terminó a mitad de la espera. No avisa por fechas inválidas (el aviso ya
    se dio al arrancar) para no ensuciar el log cada minuto.
    """
    ok, reason = _in_schedule_range(cfg, datetime.date.today())
    if not ok:
        return False, reason
    remaining = max(0.0, total_sec)
    while remaining > 0:
        chunk = min(_KEEPALIVE_QUANTUM_SEC, remaining)
        sleeper(chunk)
        remaining -= chunk
        ok, reason = _in_schedule_range(cfg, datetime.date.today())
        if not ok:
            return False, reason
    return True, ""


def _attempt_relogin(page, cfg: dict, max_retries: int = 3, sleeper=time.sleep):
    """Re-login con reintentos solo ante errores de red/navegación.

    Devuelve (status, pass_sel) con status 'success' | 'failed' | 'closed' |
    'network-error' (red caída tras agotar reintentos).
    """
    status, new_pass_sel, last_exc = None, None, None
    for attempt in range(1, max_retries + 1):
        try:
            status, new_pass_sel = perform_login(page, cfg)
            last_exc = None
            break
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            last_exc = exc
            log(f"Re-login, intento {attempt}/{max_retries} falló por red ({exc}); reintentando...")
            _backoff_sleep(attempt, sleeper)
    if last_exc is not None:
        return "network-error", None
    return status, new_pass_sel


def _keep_alive_summary(stats: dict, work_page: str = "") -> str:
    """Mensaje final del mantenimiento para el historial de la tarea."""
    elapsed = stats.get("elapsed_min", 0)
    refreshes = stats.get("refreshes", 0)
    relogins = stats.get("relogins", 0)
    reason = stats.get("end_reason", "finished")
    if reason == "failed":
        return (
            f"Mantenimiento de sesión detenido tras fallos repetidos "
            f"({refreshes} refrescos, {relogins} re-logins, {elapsed:.0f} min). "
            f"Revisa el log para ver el detalle."
        )
    base = (
        f"Login completado correctamente. Sesión mantenida {elapsed:.0f} min "
        f"({refreshes} refrescos, {relogins} re-logins)."
    )
    if work_page:
        base += f" Página de trabajo: {work_page}."
    if reason == "out-of-range":
        base += " Detenido al salir de vigencia."
    elif reason == "tab-closed":
        base += " La pestaña se cerró; mantenimiento detenido."
    return base


def keep_session_alive(page, cfg: dict, pass_sel: str | None = None,
                       session_path: str | None = None,
                       sleeper=time.sleep, clock=time.monotonic,
                       now_fn=None) -> dict:
    """Recarga la página periódicamente para evitar que el sitio cierre la
    sesión por inactividad. Si detecta que la sesión caducó, reintenta el
    login automáticamente con espera progresiva.

    - keep_alive_duration_min = 0 significa 'indefinidamente' (deadline real
      con reloj monotónico: el tiempo cuenta re-logins y todo).
    - La espera se trocea en tramos de 60 s revisando la vigencia por fechas.
    - Solo se abandona tras 3 ciclos con fallo CONSECUTIVOS (un ciclo sano
      resetea el contador); el abandono marca fallo en el historial.
    - keep_alive_time_from/to (HH:MM, opcional) limita el mantenimiento a una
      franja horaria; fuera de ella se espera sin actuar.
    - Tras cada re-login correcto se guarda la sesión para la próxima ejecución.

    Devuelve stats {refreshes, relogins, failures, started_at, elapsed_min,
    end_reason}: end_reason es 'finished' | 'out-of-range' | 'tab-closed' |
    'failed'. `sleeper`/`clock`/`now_fn` son inyectables para tests.
    """
    if now_fn is None:
        now_fn = datetime.datetime.now
    interval_min = max(1, _as_int(cfg.get("keep_alive_interval_min", 5), 5))
    duration_min = max(0, _as_int(cfg.get("keep_alive_duration_min", 60), 60))
    max_retries = 3
    frm = (cfg.get("keep_alive_time_from") or "").strip()
    to = (cfg.get("keep_alive_time_to") or "").strip()
    stats = {"refreshes": 0, "relogins": 0, "failures": 0,
             "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
             "elapsed_min": 0.0, "end_reason": "finished"}

    def _elapsed() -> float:
        elapsed = (clock() - start) / 60
        stats["elapsed_min"] = round(elapsed, 1)
        return elapsed

    def _failed_cycle(cycle_msg: str, stop_msg: str) -> bool:
        """Registra un ciclo con fallo; True si hay que abandonar."""
        nonlocal consecutive
        consecutive += 1
        stats["failures"] += 1
        log(f"{cycle_msg} (fallo {consecutive}/{_KEEPALIVE_MAX_CONSECUTIVE_FAILURES}).")
        if consecutive >= _KEEPALIVE_MAX_CONSECUTIVE_FAILURES:
            log(stop_msg)
            notify_failure(cfg, stop_msg)
            stats["end_reason"] = "failed"
            return True
        log("Se seguirá intentando en el próximo ciclo.")
        return False

    start = clock()
    try:
        home_url = page.url
    except Exception:
        home_url = None
    window_txt = f" en franja {frm}→{to}" if (frm or to) else ""
    if duration_min:
        log(f"Manteniendo la sesión activa: recarga ~cada {interval_min} min durante {duration_min} min{window_txt}.")
    else:
        log(f"Manteniendo la sesión activa: recarga ~cada {interval_min} min indefinidamente{window_txt}.")
    deadline = start + duration_min * 60 if duration_min else None

    consecutive = 0
    was_inside = None
    while True:
        now = clock()
        elapsed_min = _elapsed()
        if deadline is not None and now >= deadline:
            log(f"Fin del tiempo configurado para mantener la sesión activa ({elapsed_min:.0f} min).")
            stats["end_reason"] = "finished"
            return stats
        remaining = (deadline - now) / 60 if deadline is not None else None

        # Franja horaria: fuera de ella se espera sin refrescar ni contar fallos.
        try:
            inside = _in_time_window(now_fn().strftime("%H:%M"), frm, to)
        except Exception:
            inside = True
        if not inside:
            if was_inside is not False:
                log(f"Fuera de la franja horaria ({frm}→{to}); se espera sin refrescar.")
                was_inside = False
            ok, reason = _wait_interruptible(cfg, _KEEPALIVE_QUANTUM_SEC, sleeper)
            if not ok:
                log(f"Fin del mantenimiento de sesión: {reason}.")
                stats["end_reason"] = "out-of-range"
                return stats
            continue
        if was_inside is False:
            log("De nuevo dentro de la franja horaria: se reanuda el mantenimiento.")
        was_inside = True

        ok, reason = _wait_interruptible(cfg, _next_wait_min(interval_min, remaining) * 60, sleeper)
        if not ok:
            log(f"Fin del mantenimiento de sesión: {reason}.")
            stats["end_reason"] = "out-of-range"
            return stats

        refreshed = False
        for attempt in range(1, max_retries + 1):
            try:
                page.reload(wait_until="domcontentloaded", timeout=30000)
                refreshed = True
                break
            except PlaywrightError as exc:
                try:
                    closed = page.is_closed()
                except Exception:
                    closed = False
                if closed:
                    log("Se detiene el mantenimiento de sesión: la pestaña se cerró.")
                    stats["end_reason"] = "tab-closed"
                    return stats
                log(f"Intento {attempt}/{max_retries} de refresco falló ({exc}); reintentando...")
                _backoff_sleep(attempt, sleeper)

        if not refreshed:
            if _failed_cycle("No se pudo refrescar la sesión tras varios intentos",
                             "No se pudo refrescar la sesión tras varios intentos; se detuvo el mantenimiento."):
                return stats
            continue

        if not is_session_expired(page, pass_sel, home_url):
            consecutive = 0
            stats["refreshes"] += 1
            elapsed_min = _elapsed()
            remaining_txt = ""
            if deadline is not None:
                remaining_txt = f", quedan ~{max(0.0, (deadline - clock()) / 60):.0f} min"
            log(f"Sesión refrescada y sigue activa ({elapsed_min:.0f} min transcurridos{remaining_txt}).")
            continue

        log(f"La sesión parece haber caducado ({elapsed_min:.0f} min transcurridos); reintentando login...")
        status, new_pass_sel = _attempt_relogin(page, cfg, max_retries, sleeper)
        if status == "network-error":
            if _failed_cycle("El re-login falló por red tras varios intentos",
                             "No se pudo reintentar el login por fallos de red; se detuvo el mantenimiento."):
                return stats
            continue
        if status == "closed":
            log("No se puede seguir manteniendo la sesión activa: la pestaña se cerró durante el re-login.")
            stats["end_reason"] = "tab-closed"
            return stats
        if status == "failed":
            hints = collect_error_hints(page)
            if hints:
                log(f"Posible mensaje de error en la página: {hints}")
            if _failed_cycle("El re-login no tuvo éxito",
                             "El re-login falló en ciclos consecutivos; se detuvo el mantenimiento. Revisa las credenciales en la app."):
                return stats
            continue

        consecutive = 0
        stats["relogins"] += 1
        pass_sel = new_pass_sel or pass_sel
        if session_path:
            try:
                page.context.storage_state(path=session_path)
                log("Sesión actualizada tras el re-login correcto.")
            except Exception as exc:
                log(f"No se pudo actualizar la sesión guardada tras el re-login: {exc}")
        log("Re-login automático correcto; la sesión se ha restablecido.")


def main() -> int:
    if len(sys.argv) < 2:
        try:
            print("Uso: python run_login.py <task_id> [--no-keep-alive] [--detect-only]", file=sys.stderr)
        except Exception:
            pass
        return 2
    task_id = sys.argv[1]
    no_keep_alive = "--no-keep-alive" in sys.argv[2:]
    detect_only_mode = "--detect-only" in sys.argv[2:]
    init_logging(task_id)

    cfg = config_store.get_task(task_id)
    if not cfg:
        log(f"ERROR: no existe ninguna tarea guardada con id '{task_id}'.")
        return 1

    in_range, range_reason = check_schedule_dates(cfg)
    if not in_range and not detect_only_mode:
        # Fuera de vigencia: no es un fallo, simplemente no toca ejecutar.
        # Se registra como éxito para no pintar la fila en rojo ni notificar.
        message = f"Tarea omitida: {range_reason}."
        log(message)
        config_store.save_last_result(task_id, True, message)
        return 0

    screenshot_path = config_store.screenshot_path(task_id)
    session_path = config_store.session_state_path(task_id)
    has_saved_session = os.path.exists(session_path)

    browser = None
    # Lock anti-solape: si el keep-alive de una ejecución anterior sigue vivo
    # y Windows vuelve a disparar esta tarea, la segunda instancia se omite
    # (sin marcar fallo) en vez de pelear por la sesión. --detect-only no lo
    # necesita: es de solo lectura y no toca la sesión.
    lock_held = False
    if not detect_only_mode:
        acquired, info = task_lock.acquire(task_id)
        if not acquired:
            other_pid = info.get("pid", "?") if isinstance(info, dict) else "?"
            message = (
                f"Tarea omitida: ya hay otra ejecución en curso (PID {other_pid}); "
                "se evita solaparla para no pelear por la sesión."
            )
            log(message)
            config_store.save_last_result(task_id, True, message)
            return 0
        lock_held = True
        log("Lock anti-solape adquirido.")

    try:
        with sync_playwright() as p:
            launch_kwargs = dict(
                headless=cfg.get("headless", True),
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                browser = p.chromium.launch(**launch_kwargs)
            except PlaywrightError as exc:
                if "Executable doesn't exist" not in str(exc):
                    raise
                if not ensure_chromium_installed():
                    raise RuntimeError(
                        "No se encontró el navegador Chromium de Playwright y la descarga "
                        "automática falló. Revisa el log para ver el detalle, comprueba tu "
                        "conexión a internet y vuelve a pulsar 'Probar ahora'."
                    )
                try:
                    browser = p.chromium.launch(**launch_kwargs)
                except PlaywrightError as exc2:
                    raise RuntimeError(
                        f"No se pudo iniciar Chromium incluso tras descargarlo: {exc2}"
                    )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                storage_state=session_path if has_saved_session else None,
            )
            page = context.new_page()
            try:
                if detect_only_mode:
                    status = detect_only(page, cfg)
                    if status == "failed":
                        page.screenshot(path=screenshot_path)
                        log(f"Captura guardada en {screenshot_path}")
                    return 0 if status == "success" else 1

                # Reintenta el login inicial ante fallos de red/navegación (no ante
                # credenciales rechazadas, para no arriesgar bloqueos por reintentos).
                max_initial_retries = 3
                status = pass_sel = None
                last_exc = None
                for attempt in range(1, max_initial_retries + 1):
                    try:
                        status, pass_sel = perform_login(page, cfg, expect_login_form=not has_saved_session)
                        last_exc = None
                        break
                    except (PlaywrightTimeoutError, PlaywrightError) as exc:
                        last_exc = exc
                        if attempt < max_initial_retries:
                            log(
                                f"Intento {attempt}/{max_initial_retries} de login falló por un error "
                                f"de red/navegación ({exc}); reintentando..."
                            )
                            backoff_wait(attempt)
                if last_exc is not None:
                    raise last_exc

                if status == "failed":
                    hints = collect_error_hints(page)
                    page.screenshot(path=screenshot_path)
                    log("AVISO: tras enviar el formulario sigue visible el campo de contraseña.")
                    log(f"URL actual: {page.url} | Título: {page.title()}")
                    if hints:
                        log(f"Posible mensaje de error en la página: {hints}")
                    log(f"Captura guardada en {screenshot_path} (ábrela para ver qué muestra la página).")
                    message = "Login fallido: credenciales rechazadas o formulario seguía visible."
                    config_store.save_last_result(task_id, False, message)
                    if not no_keep_alive:
                        notify_failure(cfg, message)
                    return 1

                # Login correcto (o pestaña cerrada tras el envío, que en varios
                # sitios también significa éxito): si hay página de trabajo
                # configurada se navega a ella primero, para que la sesión que se
                # guarda (y el keep-alive después) quede ya en esa página.
                if status != "closed":
                    goto_keep_alive_url(page, cfg)
                try:
                    context.storage_state(path=session_path)
                except Exception as exc:
                    log(f"No se pudo guardar el estado de la sesión: {exc}")

                if status == "closed":
                    if cfg.get("keep_alive") and not no_keep_alive:
                        log("No se puede mantener la sesión activa: la pestaña ya está cerrada.")
                    config_store.save_last_result(task_id, True, "Login OK (la pestaña se cerró tras enviar el formulario).")
                    return 0

                work_page = (cfg.get("keep_alive_url") or "").strip()
                if cfg.get("keep_alive") and not no_keep_alive:
                    if not cfg.get("keep_alive_duration_min", 60):
                        log("AVISO: keep-alive indefinido (0:00): este proceso quedará vivo "
                            "recargando la página hasta que se detenga la tarea programada.")
                    stats = keep_session_alive(page, cfg, pass_sel, session_path=session_path)
                    ok = stats.get("end_reason") != "failed"
                    message = _keep_alive_summary(stats, work_page)
                    config_store.save_last_result(task_id, ok, message)
                    return 0
                message = "Login completado correctamente."
                if work_page:
                    message += f" Página de trabajo: {work_page}."
                config_store.save_last_result(task_id, True, message)
                return 0
            except Exception as exc:
                log(f"ERROR inesperado: {exc}")
                try:
                    log(traceback.format_exc().strip())
                except Exception:
                    pass
                try:
                    if not page.is_closed():
                        page.screenshot(path=screenshot_path)
                        log(f"Captura guardada en {screenshot_path}")
                except Exception:
                    pass
                message = f"Error inesperado: {exc}"
                config_store.save_last_result(task_id, False, message)
                if not no_keep_alive:
                    notify_failure(cfg, message)
                return 1
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as exc:
        # Fallos de arranque (Chromium ausente y no descargable, sync_playwright,
        # new_context...). Antes se propagaban y el .exe --windowed mostraba el
        # diálogo críptico "Unhandled exception in script / Failed to execute
        # script 'run_login'". Ahora se registran en el log y se devuelve 1
        # para que la GUI muestre un aviso legible en vez de ese diálogo.
        log(f"ERROR inesperado: {exc}")
        try:
            log(traceback.format_exc().strip())
        except Exception:
            pass
        message = f"Error inesperado: {exc}"
        try:
            config_store.save_last_result(task_id, False, message)
        except Exception:
            pass
        try:
            if not no_keep_alive:
                notify_failure(cfg, message)
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        return 1
    finally:
        if lock_held:
            task_lock.release(task_id)


if __name__ == "__main__":
    sys.exit(main())
