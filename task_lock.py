"""Lock anti-solape: evita que dos ejecuciones de la misma tarea corran a la vez.

Si una tarea con keep-alive largo sigue viva y Windows dispara de nuevo su
tarea programada, la segunda instancia saldría a pelear por la sesión
(cookies, Chromium, re-logins). Con este lock (`logs/<id>.lock`, con PID y
marca de tiempo), la segunda instancia detecta que ya hay una ejecución viva
y se omite sin marcar fallo ni notificar.

Un lock se considera obsoleto (stale) y se reemplaza si:
- el PID que lo dejó ya no está vivo (p. ej. el proceso murió sin limpiar), o
- tiene más de `stale_after_sec` (por defecto 24 h) aunque el PID exista
  (protección ante reutilización de PIDs por el SO).

No depende de Tkinter: es testeable en CI.
"""
import contextlib
import datetime
import json
import os

STALE_AFTER_SEC = 24 * 3600


def lock_path(task_id: str, log_dir: str | None = None) -> str:
    """Ruta del fichero de lock de una tarea."""
    if log_dir is None:
        import config_store
        log_dir = config_store._log_dir()
    return os.path.join(log_dir, f"{task_id}.lock")


def is_pid_running(pid: int) -> bool:
    """Comprueba si un PID sigue vivo, sin lanzar excepciones nunca."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            pass
        # Fallback sin ctypes: tasklist (más lento, pero solo en casos raros).
        try:
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=10,
            )
            return str(pid) in (result.stdout or "")
        except Exception:
            # Si no podemos comprobarlo, pecamos de prudentes: lo damos por vivo
            # para no pisar una ejecución que quizá siga en curso.
            return True
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return True
        return True


def _read_lock(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _lock_is_stale(info: dict | None, stale_after_sec: int) -> bool:
    """Un lock corrupto/ilegible se trata como obsoleto (se puede reemplazar)."""
    if not isinstance(info, dict):
        return True
    try:
        started = datetime.datetime.fromisoformat(info.get("started_at", ""))
        age = (datetime.datetime.now() - started).total_seconds()
    except (ValueError, TypeError):
        return True
    if age > stale_after_sec:
        return True
    pid = info.get("pid")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return True
    return not is_pid_running(pid)


def acquire(task_id: str, log_dir: str | None = None,
            stale_after_sec: int = STALE_AFTER_SEC) -> tuple[bool, dict | None]:
    """Intenta tomar el lock de `task_id`.

    Devuelve (True, None) si lo consiguió, o (False, info) si otra ejecución
    sigue viva (info es el contenido del lock ajeno, o None si ilegible).
    """
    path = lock_path(task_id, log_dir)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    payload = json.dumps({
        "pid": os.getpid(),
        "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    # Creación atómica: falla si el fichero ya existe.
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        return True, None
    except FileExistsError:
        pass
    except OSError:
        # Sin permiso de escritura u otro problema: no bloquear la ejecución.
        return True, None

    existing = _read_lock(path)
    if not _lock_is_stale(existing, stale_after_sec):
        return False, existing
    # Obsoleto: reemplazarlo (el dueño murió sin limpiar o es antiquísimo).
    try:
        os.remove(path)
    except OSError:
        return False, existing
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        return True, None
    except OSError:
        # Otro proceso se nos adelantó al reemplazarlo.
        return False, _read_lock(path)


def release(task_id: str, log_dir: str | None = None) -> None:
    """Libera el lock si es nuestro; nunca lanza excepciones."""
    path = lock_path(task_id, log_dir)
    try:
        info = _read_lock(path)
        if info is not None and int(info.get("pid", -1)) != os.getpid():
            return
    except (TypeError, ValueError):
        return
    except Exception:
        pass
    try:
        os.remove(path)
    except OSError:
        pass


@contextlib.contextmanager
def held_task_lock(task_id: str, log_dir: str | None = None,
                   stale_after_sec: int = STALE_AFTER_SEC):
    """Context manager: adquiere el lock y lo libera al salir.

    Yields (acquired, info) con el mismo significado que `acquire()`.
    """
    acquired, info = acquire(task_id, log_dir, stale_after_sec)
    try:
        yield acquired, info
    finally:
        if acquired:
            release(task_id, log_dir)
