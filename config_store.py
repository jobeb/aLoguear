"""Lectura/escritura de las tareas de login guardadas en %LOCALAPPDATA%\\AutoLogin.

Cada tarea es un login independiente (URL + credenciales + selectores +
programación) identificado por un id corto, para poder tener varias tareas
programadas en paralelo.
"""
import base64
import datetime
import json
import os
import shutil
import uuid

import crypto_utils

# La carpeta de datos por defecto es fija; si el usuario la cambia desde
# Configuración, la ubicación real se guarda en un archivo puntero dentro de
# esta carpeta por defecto (para poder encontrarla aunque se haya movido).
def _default_config_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "AutoLogin")


DEFAULT_CONFIG_DIR = _default_config_dir()
_LOCATION_POINTER_PATH = os.path.join(DEFAULT_CONFIG_DIR, "location.txt")


def _resolve_config_dir() -> str:
    try:
        if os.path.exists(_LOCATION_POINTER_PATH):
            with open(_LOCATION_POINTER_PATH, "r", encoding="utf-8") as f:
                custom = f.read().strip()
            if custom and os.path.isdir(custom):
                return custom
    except OSError:
        pass
    return DEFAULT_CONFIG_DIR


def _current_config_dir() -> str:
    """Resuelve la carpeta efectiva en cada llamada (respeta cambios sin reinicio)."""
    return _resolve_config_dir()


def _tasks_path() -> str:
    return os.path.join(_current_config_dir(), "tasks.json")


def _log_dir() -> str:
    return os.path.join(_current_config_dir(), "logs")


def _settings_path() -> str:
    return os.path.join(_current_config_dir(), "settings.json")


def _old_config_path() -> str:
    return os.path.join(_current_config_dir(), "config.json")


# Constantes históricas (compatibilidad): se refrescan en set_config_dir().
# El código nuevo debe preferir get_config_dir() / _tasks_path() / etc.
CONFIG_DIR = _resolve_config_dir()
TASKS_PATH = os.path.join(CONFIG_DIR, "tasks.json")
LOG_DIR = os.path.join(CONFIG_DIR, "logs")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
_OLD_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def _refresh_module_paths() -> None:
    global CONFIG_DIR, TASKS_PATH, LOG_DIR, SETTINGS_PATH, _OLD_CONFIG_PATH
    CONFIG_DIR = _current_config_dir()
    TASKS_PATH = os.path.join(CONFIG_DIR, "tasks.json")
    LOG_DIR = os.path.join(CONFIG_DIR, "logs")
    SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
    _OLD_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def get_config_dir() -> str:
    return _current_config_dir()


def set_config_dir(new_dir: str) -> None:
    """Copia todos los datos (tareas, logs, ajustes) a `new_dir` y recuerda la
    ubicación mediante un archivo puntero en la carpeta por defecto."""
    current = _current_config_dir()
    new_dir = os.path.abspath(new_dir)
    os.makedirs(new_dir, exist_ok=True)
    if os.path.isdir(current) and os.path.abspath(current) != new_dir:
        for name in os.listdir(current):
            if name == "location.txt":
                continue
            src = os.path.join(current, name)
            dst = os.path.join(new_dir, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
    os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)
    tmp_pointer = _LOCATION_POINTER_PATH + ".tmp"
    with open(tmp_pointer, "w", encoding="utf-8") as f:
        f.write(new_dir)
    os.replace(tmp_pointer, _LOCATION_POINTER_PATH)
    _refresh_module_paths()


def load_settings() -> dict:
    """Configuración general de la app (no por tarea), p.ej. el tema."""
    path = _settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    config_dir = _current_config_dir()
    os.makedirs(config_dir, exist_ok=True)
    current = load_settings()
    current.update(data)
    path = _settings_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    os.replace(tmp, path)


def _migrate_old_config() -> None:
    """Convierte el antiguo config.json (una sola tarea) al nuevo tasks.json."""
    try:
        tasks_path = _tasks_path()
        old_path = _old_config_path()
        if os.path.exists(tasks_path) or not os.path.exists(old_path):
            return
        with open(old_path, "r", encoding="utf-8") as f:
            old = json.load(f)
        if not isinstance(old, dict):
            return
        entry = {
            "id": uuid.uuid4().hex[:8],
            "name": old.get("url", "Tarea migrada"),
            "url": old.get("url", ""),
            "username": old.get("username", ""),
            "password_enc": old.get("password_enc", ""),
            "headless": old.get("headless", True),
            "user_selector": old.get("user_selector", ""),
            "pass_selector": old.get("pass_selector", ""),
            "submit_selector": old.get("submit_selector", ""),
            "schedule_time": old.get("schedule_time", "08:00"),
            "schedule_days": old.get("schedule_days", []),
        }
        _write_tasks([entry])
    except (OSError, json.JSONDecodeError, ValueError):
        pass


def log_path(task_id: str) -> str:
    return os.path.join(_log_dir(), f"{task_id}.log")


def screenshot_path(task_id: str) -> str:
    return os.path.join(_log_dir(), f"{task_id}_error.png")


def scheduled_task_name(task_id: str) -> str:
    return f"AutoLogin_{task_id}"


def status_path(task_id: str) -> str:
    return os.path.join(_log_dir(), f"{task_id}_status.json")


def session_state_path(task_id: str) -> str:
    return os.path.join(_log_dir(), f"{task_id}_session.json")


def save_last_result(task_id: str, success: bool, message: str) -> None:
    log_dir = _log_dir()
    os.makedirs(log_dir, exist_ok=True)
    data = {
        "success": success,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    path = status_path(task_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def load_last_result(task_id: str) -> dict | None:
    path = status_path(task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _write_tasks(tasks: list) -> None:
    config_dir = _current_config_dir()
    os.makedirs(config_dir, exist_ok=True)
    path = _tasks_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, indent=2)
    os.replace(tmp, path)


def load_tasks() -> list:
    """Devuelve la lista de tareas SIN descifrar la contraseña (para listarlas)."""
    _migrate_old_config()
    path = _tasks_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    tasks = data.get("tasks", [])
    return tasks if isinstance(tasks, list) else []


def get_task(task_id: str) -> dict | None:
    """Devuelve una tarea con la contraseña ya descifrada, o None si no existe."""
    for task in load_tasks():
        if not isinstance(task, dict) or task.get("id") != task_id:
            continue
        data = dict(task)
        password_enc = data.get("password_enc", "")
        if not password_enc:
            data["password"] = ""
            return data
        try:
            data["password"] = crypto_utils.unprotect(base64.b64decode(password_enc))
        except Exception:
            data["password"] = ""
        return data
    return None


def save_task(task_id: str | None, name: str, url: str, username: str, password: str,
              headless: bool, user_selector: str = "", pass_selector: str = "",
              submit_selector: str = "", schedule_time: str = "08:00",
              schedule_days: list | None = None, keep_alive: bool = False,
              keep_alive_interval_min: int = 5, keep_alive_duration_min: int = 60,
              active: bool = True) -> str:
    tasks = load_tasks()
    if password:
        encrypted = crypto_utils.protect(password)
        password_enc = base64.b64encode(encrypted).decode("ascii")
    else:
        password_enc = ""
    entry_id = task_id or uuid.uuid4().hex[:8]
    entry = {
        "id": entry_id,
        "name": name,
        "url": url,
        "username": username,
        "password_enc": password_enc,
        "headless": headless,
        "user_selector": user_selector,
        "pass_selector": pass_selector,
        "submit_selector": submit_selector,
        "schedule_time": schedule_time,
        "schedule_days": schedule_days if schedule_days is not None else [],
        "keep_alive": keep_alive,
        "keep_alive_interval_min": keep_alive_interval_min,
        "keep_alive_duration_min": keep_alive_duration_min,
        "active": active,
    }
    for i, t in enumerate(tasks):
        if t["id"] == entry_id:
            tasks[i] = entry
            break
    else:
        tasks.append(entry)
    _write_tasks(tasks)
    return entry_id


def delete_task(task_id: str) -> None:
    tasks = [t for t in load_tasks() if t["id"] != task_id]
    _write_tasks(tasks)
