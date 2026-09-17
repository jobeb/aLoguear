"""Tests del keep-alive reescrito (deadline real, espera troceada, fallos
consecutivos, guardado tras re-login, resultado honesto, detección ampliada
y franja horaria). Todo con página falsa y reloj inyectado: rapidísimos."""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import run_login
from run_login import (
    USER_SELECTOR_CANDIDATES,
    SUBMIT_SELECTOR_CANDIDATES,
    DIALOG_CONFIRM_CANDIDATES,
)

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except Exception:  # pragma: no cover - CI siempre instala playwright
    class PlaywrightError(Exception):
        pass

    class PlaywrightTimeoutError(Exception):
        pass


INVISIBLE = set(SUBMIT_SELECTOR_CANDIDATES) | set(DIALOG_CONFIRM_CANDIDATES) | {
    ".loginerrors", ".alert-danger", ".error", "[role='alert']",
}


class FakeLocator:
    def __init__(self, page, selector):
        self._page = page
        self._selector = selector

    @property
    def first(self):
        return self

    def _visible(self):
        sel = self._selector
        if sel == "body":
            return True
        if sel in INVISIBLE:
            return False
        if "password" in sel.lower():
            return self._page.password_visible
        return True

    def is_visible(self, timeout=None):
        return self._visible()

    def wait_for(self, state=None, timeout=None):
        vis = self._visible()
        if state == "visible" and not vis:
            raise PlaywrightTimeoutError(f"{self._selector} no visible")
        if state == "hidden" and vis:
            raise PlaywrightTimeoutError(f"{self._selector} sigue visible")

    def fill(self, value):
        self._page.filled[self._selector] = value
        if "password" in self._selector.lower() and self._page.cure_on_fill:
            # Simula que el login cura la página: desaparece el formulario.
            self._page.password_visible = False

    def press(self, _key):
        pass

    def click(self, timeout=None):
        pass

    def inner_text(self, timeout=None):
        if self._selector == "body":
            return self._page.body_text
        return ""


class FakeContext:
    def __init__(self, page):
        self._page = page
        self.saved_to = []

    def storage_state(self, path=None):
        self.saved_to.append(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{}")


class FakePage:
    def __init__(self, url="https://app.example.com/panel", password_visible=False,
                 body_text="", reload_fail_times=0, cure_on_fill=False):
        self.url = url
        self.password_visible = password_visible
        self.body_text = body_text
        self.reload_fail_times = reload_fail_times
        self.cure_on_fill = cure_on_fill
        self.filled = {}
        self.goto_calls = []
        self.reload_calls = 0
        self.context = FakeContext(self)

    def title(self):
        return "Panel"

    def locator(self, selector):
        return FakeLocator(self, selector)

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        self.url = url

    def reload(self, wait_until=None, timeout=None):
        self.reload_calls += 1
        if self.reload_fail_times > 0:
            self.reload_fail_times -= 1
            raise PlaywrightError("red caída")
        return None

    def wait_for_load_state(self, state, timeout=None):
        pass

    def is_closed(self):
        return False


class FakeClock:
    """Cada lectura avanza `step` segundos de mentira."""

    def __init__(self, step=30.0):
        self.t = 0.0
        self.step = step

    def __call__(self):
        self.t += self.step
        return self.t


class NowSequence:
    """now_fn que devuelve horas en orden y repite la última."""

    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def __call__(self):
        value = self.values[min(len(self.calls), len(self.values) - 1)]
        self.calls.append(value)
        return datetime.datetime(2026, 9, 17, int(value[:2]), int(value[3:5]))


def base_cfg(**over):
    cfg = {
        "url": "https://app.example.com/",
        "username": "u",
        "password": "p",
        "keep_alive_interval_min": 5,
        "keep_alive_duration_min": 10,
    }
    cfg.update(over)
    return cfg


def noop(_seconds):
    pass


# --- helpers puros ---

def test_next_wait_min_caps_to_remaining():
    assert run_login._next_wait_min(5, 0.2) <= 0.2 + 1e-9
    assert run_login._next_wait_min(5, 0.0) == 0.0
    assert run_login._next_wait_min(5) >= 1.0


def test_wait_interruptible_out_of_range_no_sleeps():
    sleeps = []
    ok, reason = run_login._wait_interruptible(
        {"schedule_end_date": "2000-01-01"}, 300, sleeps.append
    )
    assert ok is False and "2000-01-01" in reason
    assert sleeps == []


def test_wait_interruptible_sleeps_in_quanta():
    sleeps = []
    ok, reason = run_login._wait_interruptible({}, 90, sleeps.append)
    assert (ok, reason) == (True, "")
    assert sleeps == [60, 30]


def test_summary_shapes():
    base = {"elapsed_min": 58.0, "refreshes": 11, "relogins": 1}
    ok_msg = run_login._keep_alive_summary({**base, "end_reason": "finished"}, "https://x/y")
    assert "58 min" in ok_msg and "11 refrescos" in ok_msg and "https://x/y" in ok_msg
    bad_msg = run_login._keep_alive_summary({**base, "end_reason": "failed"})
    assert "detenido" in bad_msg and "Revisa el log" in bad_msg
    assert "vigencia" in run_login._keep_alive_summary({**base, "end_reason": "out-of-range"})
    assert "cerró" in run_login._keep_alive_summary({**base, "end_reason": "tab-closed"})


# --- detección ---

def test_expired_password_on_other_page():
    page = FakePage(url="https://app.example.com/login", password_visible=True)
    assert run_login.is_session_expired(page, "input[type='password']",
                                        home_url="https://app.example.com/panel") is True


def test_password_modal_on_same_page_is_not_expired():
    page = FakePage(url="https://app.example.com/panel", password_visible=True)
    assert run_login.is_session_expired(page, None,
                                        home_url="https://app.example.com/panel") is False


def test_expired_text_with_login_url():
    page = FakePage(url="https://app.example.com/login",
                    body_text="Tu sesión ha expirado, vuelve a iniciar sesión")
    assert run_login.is_session_expired(page, None, home_url="https://app.example.com/panel") is True


def test_login_url_without_expired_text_is_not_expired():
    page = FakePage(url="https://app.example.com/login", body_text="Bienvenido al portal")
    assert run_login.is_session_expired(page, None, home_url="https://app.example.com/panel") is False


def test_healthy_page():
    page = FakePage()
    assert run_login.is_session_expired(page, "input[type='password']",
                                        home_url="https://app.example.com/panel") is False


# --- bucle principal ---

def test_finished_by_deadline_counts_refreshes(monkeypatch):
    monkeypatch.setattr(run_login, "notify_failure", lambda cfg, msg: None)
    page = FakePage()
    stats = run_login.keep_session_alive(
        page, base_cfg(), "input[type='password']",
        sleeper=noop, clock=FakeClock(), now_fn=lambda: datetime.datetime(2026, 9, 17, 10, 0),
    )
    assert stats["end_reason"] == "finished"
    assert stats["refreshes"] >= 1
    assert stats["failures"] == 0 and stats["relogins"] == 0
    assert page.reload_calls == stats["refreshes"]


def test_consecutive_failures_reset_by_healthy_cycle(monkeypatch):
    monkeypatch.setattr(run_login, "notify_failure", lambda cfg, msg: None)
    page = FakePage(reload_fail_times=5)  # ciclo 1 falla (3 intentos), ciclo 2 se cura
    stats = run_login.keep_session_alive(
        page, base_cfg(keep_alive_duration_min=30), "input[type='password']",
        sleeper=noop, clock=FakeClock(), now_fn=lambda: datetime.datetime(2026, 9, 17, 10, 0),
    )
    assert stats["end_reason"] == "finished"
    assert stats["failures"] == 1
    assert stats["refreshes"] >= 1


def test_abandon_after_three_consecutive_failures(monkeypatch):
    notified = []
    monkeypatch.setattr(run_login, "notify_failure", lambda cfg, msg: notified.append(msg))
    page = FakePage(reload_fail_times=999)
    stats = run_login.keep_session_alive(
        page, base_cfg(keep_alive_duration_min=60), "input[type='password']",
        sleeper=noop, clock=FakeClock(), now_fn=lambda: datetime.datetime(2026, 9, 17, 10, 0),
    )
    assert stats["end_reason"] == "failed"
    assert stats["failures"] == 3
    assert len(notified) == 1


def test_relogin_cures_and_saves_session(tmp_path, monkeypatch):
    monkeypatch.setattr(run_login, "notify_failure", lambda cfg, msg: None)
    session_file = str(tmp_path / "s.json")
    page = FakePage(url="https://app.example.com/login", password_visible=True,
                    cure_on_fill=True)
    stats = run_login.keep_session_alive(
        page, base_cfg(), "input[type='password']", session_path=session_file,
        sleeper=noop, clock=FakeClock(), now_fn=lambda: datetime.datetime(2026, 9, 17, 10, 0),
    )
    assert stats["relogins"] == 1
    assert stats["end_reason"] == "finished"
    assert page.context.saved_to == [session_file]
    assert page.filled.get("input[type='password']") == "p"


def test_outside_window_waits_without_refreshing(monkeypatch):
    monkeypatch.setattr(run_login, "notify_failure", lambda cfg, msg: None)
    now = NowSequence(["07:30", "07:45", "08:05", "08:05", "08:05", "08:05"])
    page = FakePage()
    stats = run_login.keep_session_alive(
        page, base_cfg(keep_alive_time_from="08:00", keep_alive_time_to="20:00"),
        "input[type='password']", sleeper=noop, clock=FakeClock(), now_fn=now,
    )
    assert stats["end_reason"] == "finished"
    assert page.reload_calls >= 1
    assert page.reload_calls < len(now.calls)  # hubo iteraciones solo esperando
