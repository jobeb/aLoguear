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
DEFAULT_CONFIG_DIR = os.path.join(os.environ["LOCALAPPDATA"], "AutoLogin")
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


CONFIG_DIR = _resolve_config_dir()
TASKS_PATH = os.path.join(CONFIG_DIR, "tasks.json")
LOG_DIR = os.path.join(CONFIG_DIR, "logs")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
_OLD_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def get_config_dir() -> str:
    return CONFIG_DIR


def set_config_dir(new_dir: str) -> None:
    """Copia todos los datos (tareas, logs, ajustes) a `new_dir` y recuerda la
    ubicación mediante un archivo puntero en la carpeta por defecto. El
    proceso actual sigue usando la ruta antigua: hace falta reiniciar la app
    para que tenga efecto."""
    new_dir = os.path.abspath(new_dir)
    os.makedirs(new_dir, exist_ok=True)
    if os.path.isdir(CONFIG_DIR) and os.path.abspath(CONFIG_DIR) != new_dir:
        for name in os.listdir(CONFIG_DIR):
            if name == "location.txt":
                continue
            src = os.path.join(CONFIG_DIR, name)
            dst = os.path.join(new_dir, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
    os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)
    with open(_LOCATION_POINTER_PATH, "w", encoding="utf-8") as f:
        f.write(new_dir)


def load_settings() -> dict:
    """Configuración general de la app (no por tarea), p.ej. el tema."""
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(data: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    current = load_settings()
    current.update(data)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)


def _migrate_old_config() -> None:
    """Convierte el antiguo config.json (una sola tarea) al nuevo tasks.json."""
    if os.path.exists(TASKS_PATH) or not os.path.exists(_OLD_CONFIG_PATH):
        return
    with open(_OLD_CONFIG_PATH, "r", encoding="utf-8") as f:
        old = json.load(f)
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


def log_path(task_id: str) -> str:
    return os.path.join(LOG_DIR, f"{task_id}.log")


def screenshot_path(task_id: str) -> str:
    return os.path.join(LOG_DIR, f"{task_id}_error.png")


def scheduled_task_name(task_id: str) -> str:
    return f"AutoLogin_{task_id}"


def status_path(task_id: str) -> str:
    return os.path.join(LOG_DIR, f"{task_id}_status.json")


def session_state_path(task_id: str) -> str:
    return os.path.join(LOG_DIR, f"{task_id}_session.json")


def save_last_result(task_id: str, success: bool, message: str) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    data = {
        "success": success,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(status_path(task_id), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


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
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TASKS_PATH, "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, indent=2)


def load_tasks() -> list:
    """Devuelve la lista de tareas SIN descifrar la contraseña (para listarlas)."""
    _migrate_old_config()
    if not os.path.exists(TASKS_PATH):
        return []
    with open(TASKS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tasks", [])


def get_task(task_id: str) -> dict | None:
    """Devuelve una tarea con la contraseña ya descifrada, o None si no existe."""
    for task in load_tasks():
        if task["id"] == task_id:
            data = dict(task)
            data["password"] = crypto_utils.unprotect(base64.b64decode(data["password_enc"]))
            return data
    return None


def save_task(task_id: str | None, name: str, url: str, username: str, password: str,
              headless: bool, user_selector: str = "", pass_selector: str = "",
              submit_selector: str = "", schedule_time: str = "08:00",
              schedule_days: list | None = None, keep_alive: bool = False,
              keep_alive_interval_min: int = 5, keep_alive_duration_min: int = 60,
              active: bool = True) -> str:
    tasks = load_tasks()
    encrypted = crypto_utils.protect(password)
    entry_id = task_id or uuid.uuid4().hex[:8]
    entry = {
        "id": entry_id,
        "name": name,
        "url": url,
        "username": username,
        "password_enc": base64.b64encode(encrypted).decode("ascii"),
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
