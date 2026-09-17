"""Lógica pura de aLoguear (sin Tkinter): validaciones, formatos y helpers.

Se extrajo de `gui_config.py` para poder testearla en CI sin necesidad de
interfaz gráfica. `gui_config.py` re-exporta estos nombres para mantener
compatibilidad hacia atrás.
"""
import datetime
import hashlib
import json
import re
import urllib.parse
import urllib.request

from version import __version__ as APP_VERSION, GITHUB_REPO

_NET_DATE_RE = re.compile(r"/Date\((\d+)\)/")


def _parse_version(text: str) -> tuple:
    text = text.strip().lstrip("vV")
    parts = re.findall(r"\d+", text)
    return tuple(int(p) for p in parts) or (0,)


def check_for_update() -> tuple[str, str, str | None, str | None] | None:
    """Consulta el último release de GitHub. Devuelve (version, html_url,
    asset_zip_url, asset_sha256_url) si hay una versión más nueva que la
    instalada, o None (sin release, sin conexión, o ya estamos al día).
    No debe lanzar excepciones nunca."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "aLoguear-update-check"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest_tag = data.get("tag_name", "")
        if not latest_tag:
            return None
        if _parse_version(latest_tag) > _parse_version(APP_VERSION):
            html_url = data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest"
            asset_url = None
            sha_url = None
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.endswith("-win64.zip"):
                    asset_url = asset.get("browser_download_url")
                elif name.endswith("-win64.zip.sha256"):
                    sha_url = asset.get("browser_download_url")
            return latest_tag, html_url, asset_url, sha_url
    except Exception:
        pass
    return None


def _sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_sha256_file(text: str) -> str | None:
    """Extrae el hash de un fichero .sha256 ('<hash>  <nombre>' o solo hash)."""
    text = (text or "").strip().split()[0] if (text or "").strip() else ""
    if re.fullmatch(r"[0-9a-fA-F]{64}", text or ""):
        return text.lower()
    return None


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

_EXPORT_FIELDS = [
    "name", "url", "username", "headless", "user_selector", "pass_selector",
    "submit_selector", "schedule_time", "schedule_days",
    "schedule_start_date", "schedule_end_date", "keep_alive",
    "keep_alive_interval_min", "keep_alive_duration_min", "keep_alive_url",
    "keep_alive_time_from", "keep_alive_time_to", "active",
]


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


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_VALID_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


def _normalize_schedule_time(value: str) -> str:
    value = (value or "").strip()
    if _TIME_RE.match(value):
        return value
    return "08:00"


def _normalize_schedule_days(value) -> list:
    if not isinstance(value, list):
        return []
    return [d for d in value if d in _VALID_DAYS]


def _parse_int_safe(value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(str(value or "").strip() or default)
    except (ValueError, TypeError):
        return default
    return max(minimum, min(maximum, number))


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _normalize_iso_date(value: str) -> str:
    """Normaliza una fecha de vigencia a 'YYYY-MM-DD' o '' si vacía/inválida."""
    value = (value or "").strip()
    if not value:
        return ""
    if not _ISO_DATE_RE.match(value):
        return ""
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return ""
    return value


def _validity_display(start: str, end: str) -> str:
    """Texto corto de vigencia para la lista: '—' si siempre vigente."""
    start = (start or "").strip()
    end = (end or "").strip()

    def _short(iso: str) -> str:
        try:
            d = datetime.date.fromisoformat(iso)
            return d.strftime("%d/%m/%y")
        except ValueError:
            return "?"

    if not start and not end:
        return "—"
    if start and end:
        return f"{_short(start)}→{_short(end)}"
    if start:
        return f"≥{_short(start)}"
    return f"≤{_short(end)}"


_DATE_SORT_RE = re.compile(r"(\d{2})/(\d{2})\s+(\d{2}):(\d{2})")


def _date_sort_key(text: str) -> tuple:
    """Clave cronológica para 'dd/mm HH:MM' (con posible icono ✓/✗ delante).
    Lo que no parece fecha (—, Pausada, …) va al final/principio de forma estable."""
    if not isinstance(text, str):
        return (1, 0, 0, 0, 0)
    m = _DATE_SORT_RE.search(text)
    if not m:
        return (1, 0, 0, 0, 0)
    try:
        day, month, hour, minute = map(int, m.groups())
        return (0, month, day, hour, minute)
    except ValueError:
        return (1, 0, 0, 0, 0)


def filter_tasks(tasks: list, query: str) -> list:
    """Filtra tareas por nombre o URL (insensible a mayúsculas). Pura y testeable."""
    query = (query or "").strip().lower()
    if not query:
        return list(tasks)
    return [
        t for t in tasks
        if query in (t.get("name") or "").lower() or query in (t.get("url") or "").lower()
    ]


def count_tasks(tasks: list) -> tuple[int, int]:
    """Devuelve (total, activas)."""
    total = len(tasks)
    active = sum(1 for t in tasks if t.get("active", True))
    return total, active


_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _normalize_hhmm_optional(value: str) -> str:
    """Normaliza una hora de franja a 'HH:MM' o '' si vacía/inválida.

    Acepta '8:05' (lo pasa a '08:05'); rechaza horas imposibles ('25:00').
    """
    value = (value or "").strip()
    if not value:
        return ""
    m = _HHMM_RE.match(value)
    if not m:
        return ""
    try:
        hour, minute = int(m.group(1)), int(m.group(2))
    except ValueError:
        return ""
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return ""
    return f"{hour:02d}:{minute:02d}"


def _in_time_window(now: str, frm: str, to: str) -> bool:
    """Dice si 'now' (HH:MM) cae dentro de la franja [frm, to).

    Lados vacíos = abiertos (sin límite). Permite franjas nocturnas
    (22:00→06:00) y frm == to se interpreta como día completo.
    """
    now = (now or "").strip()
    frm = (frm or "").strip()
    to = (to or "").strip()
    if not frm and not to:
        return True
    if frm and not to:
        return now >= frm
    if to and not frm:
        return now < to
    if frm == to:
        return True
    if frm <= to:
        return frm <= now < to
    return now >= frm or now < to  # franja nocturna que cruza medianoche
