"""Tests de la lógica pura (app_logic): sin Tkinter, multiplataforma."""
import datetime
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app_logic


def test_parse_version():
    assert app_logic._parse_version("v1.3.5") == (1, 3, 5)
    assert app_logic._parse_version("1.3.5") == (1, 3, 5)
    assert app_logic._parse_version("V2.0") == (2, 0)
    assert app_logic._parse_version("") == (0,)
    assert app_logic._parse_version("v1.10.2") > app_logic._parse_version("v1.9.9")


def test_normalize_schedule_time():
    assert app_logic._normalize_schedule_time("08:00") == "08:00"
    assert app_logic._normalize_schedule_time(" 23:59 ") == "23:59"
    assert app_logic._normalize_schedule_time("24:00") == "08:00"
    assert app_logic._normalize_schedule_time("8:00") == "08:00"
    assert app_logic._normalize_schedule_time("") == "08:00"
    assert app_logic._normalize_schedule_time("abc") == "08:00"


def test_normalize_schedule_days():
    assert app_logic._normalize_schedule_days(["Monday", "X", "Friday"]) == ["Monday", "Friday"]
    assert app_logic._normalize_schedule_days("Monday") == []
    assert app_logic._normalize_schedule_days(None) == []
    assert app_logic._normalize_schedule_days([]) == []


def test_parse_int_safe():
    assert app_logic._parse_int_safe("5", 5, 1, 120) == 5
    assert app_logic._parse_int_safe("  9 ", 5, 1, 120) == 9
    assert app_logic._parse_int_safe("", 5, 1, 120) == 5
    assert app_logic._parse_int_safe("abc", 5, 1, 120) == 5
    assert app_logic._parse_int_safe(None, 5, 1, 120) == 5
    assert app_logic._parse_int_safe("999", 5, 1, 120) == 120
    assert app_logic._parse_int_safe("-3", 5, 1, 120) == 1


def test_is_valid_url():
    assert app_logic._is_valid_url("https://ejemplo.com/login")
    assert app_logic._is_valid_url("http://localhost:8000/x")
    assert not app_logic._is_valid_url("ftp://ejemplo.com")
    assert not app_logic._is_valid_url("ejemplo.com")
    assert not app_logic._is_valid_url("")
    assert not app_logic._is_valid_url("https://")


def test_normalize_iso_date():
    assert app_logic._normalize_iso_date("2026-01-15") == "2026-01-15"
    assert app_logic._normalize_iso_date(" 2026-01-15 ") == "2026-01-15"
    assert app_logic._normalize_iso_date("") == ""
    assert app_logic._normalize_iso_date("15/01/2026") == ""
    assert app_logic._normalize_iso_date("2026-02-30") == ""  # día imposible
    assert app_logic._normalize_iso_date("no-fecha") == ""


def test_validity_display():
    assert app_logic._validity_display("", "") == "—"
    assert app_logic._validity_display("2026-01-01", "2026-06-30") == "01/01/26→30/06/26"
    assert app_logic._validity_display("2026-01-01", "") == "≥01/01/26"
    assert app_logic._validity_display("", "2026-06-30") == "≤30/06/26"


def test_days_display():
    assert app_logic._days_display(["Monday", "Friday"]) == "LuVi"
    assert app_logic._days_display([]) == "-"
    assert "LuMaMiJuVi" in app_logic._days_display(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    )


def test_last_result_display():
    assert app_logic._last_result_display(None) == "—"
    ok = app_logic._last_result_display({"success": True, "timestamp": "2026-09-17T08:00:00"})
    assert ok.startswith("✓") and "17/09" in ok
    fail = app_logic._last_result_display({"success": False, "timestamp": "2026-09-17T08:00:00"})
    assert fail.startswith("✗")


def test_format_net_date():
    assert app_logic._format_net_date(None) == "—"
    assert app_logic._format_net_date("") == "—"
    assert app_logic._format_net_date("no-es-fecha") == "—"
    # 0 ms = epoch; solo comprobamos que no devuelve "—" y tiene forma de fecha.
    out = app_logic._format_net_date("/Date(0)/")
    assert out != "—" and ":" in out


def test_date_sort_key_orders_chronologically():
    keys = [
        app_logic._date_sort_key("✓ 17/09 08:00"),
        app_logic._date_sort_key("✓ 18/09 08:00"),
        app_logic._date_sort_key("—"),
        app_logic._date_sort_key("Pausada"),
    ]
    assert keys[0] < keys[1] < keys[2]
    assert keys[2] == keys[3] == (1, 0, 0, 0, 0)


def test_parse_sha256_file():
    good = "ab" * 32
    assert app_logic._parse_sha256_file(f"{good}  aLoguear.zip") == good
    assert app_logic._parse_sha256_file(good.upper()) == good
    assert app_logic._parse_sha256_file("no-es-un-hash") is None
    assert app_logic._parse_sha256_file("") is None


def test_sha256_of_file(tmp_path):
    target = tmp_path / "hola.txt"
    target.write_bytes(b"hola")
    import hashlib
    assert app_logic._sha256_of_file(str(target)) == hashlib.sha256(b"hola").hexdigest()


def _fake_urlopen(payload: dict):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def _open(req, timeout=6):
        return _Resp()

    return _open


def test_check_for_update_newer(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({
        "tag_name": "v99.0.0",
        "html_url": "https://example.com/rel",
        "assets": [
            {"name": "aLoguear-v99.0.0-win64.zip", "browser_download_url": "https://ex/a.zip"},
            {"name": "aLoguear-v99.0.0-win64.zip.sha256", "browser_download_url": "https://ex/a.sha"},
        ],
    }))
    result = app_logic.check_for_update()
    assert result is not None
    assert result[0] == "v99.0.0" and result[2] == "https://ex/a.zip"


def test_check_for_update_up_to_date(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen({
        "tag_name": "v0.0.1", "html_url": "x", "assets": [],
    }))
    assert app_logic.check_for_update() is None


def test_check_for_update_no_network(monkeypatch):
    def _boom(req, timeout=6):
        raise OSError("sin red")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert app_logic.check_for_update() is None


def test_filter_and_count_tasks():
    tasks = [
        {"name": "Campus", "url": "https://campus.example.com", "active": True},
        {"name": "Banco", "url": "https://banco.example.com", "active": False},
    ]
    assert app_logic.filter_tasks(tasks, "") == tasks
    assert app_logic.filter_tasks(tasks, "campus")[0]["name"] == "Campus"
    assert app_logic.filter_tasks(tasks, "BANCO")[0]["name"] == "Banco"
    assert app_logic.filter_tasks(tasks, "nada") == []
    assert app_logic.count_tasks(tasks) == (2, 1)
