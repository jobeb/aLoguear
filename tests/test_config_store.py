"""Tests de config_store con carpeta temporal (sin tocar %LOCALAPPDATA% real).

DPAPI solo existe en Windows: se sustituye crypto_utils.protect/unprotect por
un stub reversible para que estos tests corran en cualquier plataforma.
"""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config_store
import crypto_utils


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    def _fake_dir():
        return str(data_dir)

    monkeypatch.setattr(config_store, "_current_config_dir", _fake_dir)
    config_store._refresh_module_paths()

    def _fake_protect(plaintext: str) -> bytes:
        if not plaintext:
            raise ValueError("vacía")
        return b"ENC:" + plaintext.encode("utf-8")

    def _fake_unprotect(ciphertext: bytes) -> str:
        assert ciphertext.startswith(b"ENC:")
        return ciphertext[len(b"ENC:"):].decode("utf-8")

    monkeypatch.setattr(crypto_utils, "protect", _fake_protect)
    monkeypatch.setattr(crypto_utils, "unprotect", _fake_unprotect)
    return str(data_dir)


def test_save_and_get_task_roundtrip(isolated_store):
    task_id = config_store.save_task(
        task_id=None, name="Campus", url="https://campus.example.com",
        username="alumno", password="s3cr3t", headless=True,
        schedule_time="08:00", schedule_days=["Monday"], active=True,
    )
    assert task_id
    tasks = config_store.load_tasks()
    assert len(tasks) == 1
    # La contraseña NO queda en claro en el fichero.
    assert "s3cr3t" not in open(config_store._tasks_path(), encoding="utf-8").read()

    full = config_store.get_task(task_id)
    assert full["password"] == "s3cr3t"
    assert full["schedule_days"] == ["Monday"]


def test_save_task_without_password(isolated_store):
    task_id = config_store.save_task(
        task_id=None, name="X", url="https://x.example.com",
        username="u", password="", headless=True,
    )
    assert config_store.get_task(task_id)["password"] == ""


def test_update_task_keeps_single_entry(isolated_store):
    task_id = config_store.save_task(
        task_id=None, name="A", url="https://a.example.com",
        username="u", password="p1", headless=True,
    )
    config_store.save_task(
        task_id=task_id, name="A2", url="https://a.example.com",
        username="u", password="p2", headless=False,
    )
    assert len(config_store.load_tasks()) == 1
    full = config_store.get_task(task_id)
    assert full["name"] == "A2" and full["password"] == "p2" and full["headless"] is False


def test_delete_task(isolated_store):
    task_id = config_store.save_task(
        task_id=None, name="A", url="https://a.example.com",
        username="u", password="p", headless=True,
    )
    config_store.delete_task(task_id)
    assert config_store.load_tasks() == []
    assert config_store.get_task(task_id) is None


def test_corrupt_tasks_json_returns_empty(isolated_store):
    with open(config_store._tasks_path(), "w", encoding="utf-8") as f:
        f.write("{esto no es json")
    assert config_store.load_tasks() == []


def test_last_result_roundtrip(isolated_store):
    config_store.save_last_result("abc123", True, "Login OK")
    loaded = config_store.load_last_result("abc123")
    assert loaded["success"] is True and loaded["message"] == "Login OK"
    assert config_store.load_last_result("no-existe") is None


def test_settings_roundtrip(isolated_store):
    assert config_store.load_settings() == {}
    config_store.save_settings({"theme": "dark"})
    config_store.save_settings({"close_action": "tray"})
    assert config_store.load_settings() == {"theme": "dark", "close_action": "tray"}


def test_lock_path_lives_next_to_logs(isolated_store):
    assert config_store.lock_path("abc123").endswith("abc123.lock")
    assert os.path.dirname(config_store.lock_path("abc123")) == config_store._log_dir()


def test_password_enc_roundtrip_base64(isolated_store):
    task_id = config_store.save_task(
        task_id=None, name="A", url="https://a.example.com",
        username="u", password="ñandú-123", headless=True,
    )
    raw = next(t for t in config_store.load_tasks() if t["id"] == task_id)
    base64.b64decode(raw["password_enc"])  # no debe fallar: es base64 válido


def test_keep_alive_url_roundtrip(isolated_store):
    task_id = config_store.save_task(
        task_id=None, name="A", url="https://a.example.com",
        username="u", password="p", headless=True,
        keep_alive=True, keep_alive_url="https://a.example.com/mis-cursos",
    )
    assert config_store.get_task(task_id)["keep_alive_url"] == "https://a.example.com/mis-cursos"


def test_keep_alive_url_defaults_to_empty(isolated_store):
    task_id = config_store.save_task(
        task_id=None, name="A", url="https://a.example.com",
        username="u", password="p", headless=True,
    )
    assert config_store.get_task(task_id).get("keep_alive_url", "") == ""


def test_legacy_task_without_keep_alive_url(isolated_store):
    """Tareas guardadas antes de este campo no lo traen: .get() debe dar ''."""
    import json

    task_id = config_store.save_task(
        task_id=None, name="A", url="https://a.example.com",
        username="u", password="p", headless=True,
    )
    with open(config_store._tasks_path(), encoding="utf-8") as f:
        data = json.load(f)
    for t in data["tasks"]:
        if t["id"] == task_id:
            del t["keep_alive_url"]
    with open(config_store._tasks_path(), "w", encoding="utf-8") as f:
        json.dump(data, f)
    assert config_store.get_task(task_id).get("keep_alive_url", "") == ""


def test_keep_alive_time_window_roundtrip(isolated_store):
    task_id = config_store.save_task(
        task_id=None, name="A", url="https://a.example.com",
        username="u", password="p", headless=True,
        keep_alive=True, keep_alive_time_from="08:00", keep_alive_time_to="20:00",
    )
    full = config_store.get_task(task_id)
    assert full["keep_alive_time_from"] == "08:00"
    assert full["keep_alive_time_to"] == "20:00"


def test_keep_alive_time_window_defaults_to_empty(isolated_store):
    task_id = config_store.save_task(
        task_id=None, name="A", url="https://a.example.com",
        username="u", password="p", headless=True,
    )
    full = config_store.get_task(task_id)
    assert full.get("keep_alive_time_from", "") == ""
    assert full.get("keep_alive_time_to", "") == ""
