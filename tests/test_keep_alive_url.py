"""Tests de la página de trabajo post-login (keep_alive_url).

goto_keep_alive_url navega tras el login para que el keep-alive mantenga la
sesión en esa página en vez de en la del login. Se testea con una página
falsa; no necesita navegador.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import run_login

try:
    from playwright.sync_api import Error as PlaywrightError
except Exception:  # pragma: no cover - CI siempre instala playwright
    class PlaywrightError(Exception):
        pass


class FakePage:
    def __init__(self, goto_exc=None):
        self.url = "https://login.example.com/"
        self.goto_calls = []
        self.load_state_calls = []
        self._goto_exc = goto_exc

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        if self._goto_exc is not None:
            raise self._goto_exc
        self.url = url

    def wait_for_load_state(self, state, timeout=None):
        self.load_state_calls.append(state)


def test_is_http_url():
    assert run_login._is_http_url("https://curso.example.com/mis-cursos")
    assert run_login._is_http_url("http://intranet.local/panel")
    assert not run_login._is_http_url("")
    assert not run_login._is_http_url("ftp://x.example.com")
    assert not run_login._is_http_url("curso.example.com")
    assert not run_login._is_http_url(None)


def test_no_url_no_navigation():
    page = FakePage()
    assert run_login.goto_keep_alive_url(page, {}) is True
    assert run_login.goto_keep_alive_url(page, {"keep_alive_url": "  "}) is True
    assert page.goto_calls == []


def test_valid_url_navigates():
    page = FakePage()
    cfg = {"keep_alive_url": "https://curso.example.com/mis-cursos"}
    assert run_login.goto_keep_alive_url(page, cfg) is True
    assert page.goto_calls == ["https://curso.example.com/mis-cursos"]
    assert page.url == "https://curso.example.com/mis-cursos"


def test_invalid_url_skips_without_navigating():
    page = FakePage()
    assert run_login.goto_keep_alive_url(page, {"keep_alive_url": "no-es-url"}) is False
    assert page.goto_calls == []


def test_navigation_error_is_not_fatal():
    page = FakePage(goto_exc=PlaywrightError("timeout de red"))
    cfg = {"keep_alive_url": "https://curso.example.com/"}
    assert run_login.goto_keep_alive_url(page, cfg) is False
    assert page.goto_calls == ["https://curso.example.com/"]
