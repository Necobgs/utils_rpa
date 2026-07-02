import logging
import sys
import types

import pytest

import utils_rpa.anti_captcha as ac

# ── Sanidade / helpers ────────────────────────────────────────────────────────

def test_module_exposes_public_functions():
    assert hasattr(ac, "cloudflare_solver_selenium")
    assert hasattr(ac, "cloudflare_solver_playwright")
    assert hasattr(ac, "image_to_text")


def test_extract_sitekey_from_src():
    assert ac._extract_sitekey_from_src("https://x/?sitekey=ABC&foo=1") == "ABC"
    assert ac._extract_sitekey_from_src("https://x/sem-chave") is None
    assert ac._extract_sitekey_from_src("") is None


def test_resolve_api_key_priority(monkeypatch):
    logger = logging.getLogger("test_api_key")
    monkeypatch.setenv("ANTICAPTCHA_KEY", "env-key")
    assert ac._resolve_api_key(None, logger) == "env-key"
    assert ac._resolve_api_key("explicit", logger) == "explicit"


def test_resolve_api_key_empty_logs_warning(monkeypatch, caplog):
    monkeypatch.delenv("ANTICAPTCHA_KEY", raising=False)
    logger = logging.getLogger("test_api_key_empty")
    with caplog.at_level(logging.WARNING, logger="test_api_key_empty"):
        assert ac._resolve_api_key(None, logger) == ""
    assert any("ANTICAPTCHA_KEY" in m for m in caplog.messages)


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _FakeSeleniumElement:
    def __init__(self, displayed=True):
        self._displayed = displayed

    def is_displayed(self):
        return self._displayed


class _FakeDriver:
    def __init__(self, success_visible=True):
        self.success_visible = success_visible

    def find_element(self, by, selector):
        if self.success_visible:
            return _FakeSeleniumElement(True)
        raise RuntimeError("elemento não encontrado")


class _FakePlaywrightElement:
    def __init__(self, visible=True):
        self._visible = visible

    def is_visible(self):
        return self._visible


class _FakePage:
    def __init__(self, success_visible=True):
        self.success_visible = success_visible
        self.url = "http://example/challenge"

    def query_selector(self, selector):
        if self.success_visible:
            return _FakePlaywrightElement(True)
        return None


@pytest.fixture
def _fake_selenium(monkeypatch):
    """Injeta um módulo selenium falso para o import lazy de ``By``."""

    class By:
        XPATH = "xpath"
        ID = "id"

    by_mod = types.ModuleType("selenium.webdriver.common.by")
    by_mod.By = By

    monkeypatch.setitem(sys.modules, "selenium", types.ModuleType("selenium"))
    monkeypatch.setitem(sys.modules, "selenium.webdriver", types.ModuleType("selenium.webdriver"))
    monkeypatch.setitem(
        sys.modules, "selenium.webdriver.common", types.ModuleType("selenium.webdriver.common")
    )
    monkeypatch.setitem(sys.modules, "selenium.webdriver.common.by", by_mod)
    return By


# ── Selenium ────────────────────────────────────────────────────────────────

def test_selenium_returns_true_when_success_visible(_fake_selenium):
    driver = _FakeDriver(success_visible=True)
    assert ac.cloudflare_solver_selenium(driver, api_key="k") is True


def test_selenium_returns_false_when_nothing_detected(_fake_selenium, monkeypatch):
    monkeypatch.setattr(ac.time, "sleep", lambda _s: None)
    driver = _FakeDriver(success_visible=False)
    result = ac.cloudflare_solver_selenium(
        driver, api_key="k", timeout_captcha_detect=2
    )
    assert result is False


# ── Playwright ────────────────────────────────────────────────────────────────

def test_playwright_returns_true_when_success_visible():
    page = _FakePage(success_visible=True)
    assert ac.cloudflare_solver_playwright(page, api_key="k") is True


def test_playwright_returns_false_when_nothing_detected(monkeypatch):
    monkeypatch.setattr(ac.time, "sleep", lambda _s: None)
    page = _FakePage(success_visible=False)
    result = ac.cloudflare_solver_playwright(
        page, api_key="k", timeout_captcha_detect=2
    )
    assert result is False
