"""Tests de la vigencia por fechas del runner (run_login.check_schedule_dates).

run_login importa playwright al cargarse; CI instala requirements, así que la
importación debe funcionar en Windows. Si playwright no está disponible, estos
tests se omiten en vez de fallar.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

run_login = pytest = None
try:
    import run_login  # noqa: F401
except Exception:
    run_login = None

import pytest

pytestmark = pytest.mark.skipif(run_login is None, reason="playwright no disponible")


def _cfg(start="", end=""):
    return {"schedule_start_date": start, "schedule_end_date": end}


def test_no_dates_always_in_range():
    ok, reason = run_login.check_schedule_dates(_cfg(), today=datetime.date(2026, 9, 17))
    assert ok and reason == ""


def test_inside_range():
    ok, _ = run_login.check_schedule_dates(
        _cfg("2026-01-01", "2026-12-31"), today=datetime.date(2026, 9, 17)
    )
    assert ok


def test_before_start():
    ok, reason = run_login.check_schedule_dates(
        _cfg("2026-10-01", ""), today=datetime.date(2026, 9, 17)
    )
    assert not ok and "2026-10-01" in reason


def test_after_end():
    ok, reason = run_login.check_schedule_dates(
        _cfg("", "2026-01-01"), today=datetime.date(2026, 9, 17)
    )
    assert not ok and "2026-01-01" in reason


def test_invalid_dates_are_ignored_not_blocking():
    ok, _ = run_login.check_schedule_dates(
        _cfg("no-fecha", "tampoco"), today=datetime.date(2026, 9, 17)
    )
    assert ok


def test_parse_iso_date():
    assert run_login.parse_iso_date("2026-09-17") == datetime.date(2026, 9, 17)
    assert run_login.parse_iso_date("") is None
    assert run_login.parse_iso_date("17/09/2026") is None
