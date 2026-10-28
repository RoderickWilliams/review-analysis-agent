"""Navigation-abort recovery without real browser or platform requests."""
from types import SimpleNamespace

import pytest

from reviewagent.browser_session import BrowserNavigationError, _CdpDriver


def aborted(*args, **kwargs):
    raise RuntimeError("net::ERR_ABORTED")


def test_abort_after_redirect_does_not_navigate_again(monkeypatch):
    tab = SimpleNamespace(url="https://login.taobao.com/member/login.jhtml", get=aborted,
                          run_js=lambda *a, **k: pytest.fail("Do not replace a login page"))
    driver = _CdpDriver(SimpleNamespace(), tab)
    monkeypatch.setattr(driver, "_wait_for_document", lambda seconds: True)
    driver.get("https://e.tb.cn/example")


def test_blank_abort_has_exactly_one_fallback(monkeypatch):
    calls = []
    def run_js(script, *args, **kwargs):
        if "return {url:" in script:
            return {"url": "about:blank", "text": 0}
        calls.append(((script, *args), kwargs))
    tab = SimpleNamespace(url="about:blank", get=aborted,
                          run_js=run_js)
    driver = _CdpDriver(SimpleNamespace(), tab)
    states = iter([False, True])
    monkeypatch.setattr(driver, "_wait_for_document", lambda seconds: next(states))
    driver.get("https://e.tb.cn/example")
    assert len(calls) == 1
    assert calls[0][0][1] == "https://e.tb.cn/example"


def test_failed_fallback_stops_without_loop(monkeypatch):
    calls = []
    def run_js(script, *args, **kwargs):
        if "return {url:" in script:
            return {"url": "about:blank", "text": 0}
        calls.append((script, *args))
    tab = SimpleNamespace(url="about:blank", get=aborted,
                          run_js=run_js)
    driver = _CdpDriver(SimpleNamespace(), tab)
    monkeypatch.setattr(driver, "_wait_for_document", lambda seconds: False)
    with pytest.raises(BrowserNavigationError) as error:
        driver.get("https://e.tb.cn/example")
    assert error.value.code == "navigation_aborted"
    assert len(calls) == 1


def test_nonblank_abort_does_not_reload_platform_page(monkeypatch):
    def run_js(script, *args, **kwargs):
        if "return {url:" in script:
            return {"url": "https://passport.taobao.com/iv/normal_validate.htm", "text": 20}
        pytest.fail("Do not reload identity verification")
    tab = SimpleNamespace(url="https://passport.taobao.com/iv/normal_validate.htm", get=aborted,
                          run_js=run_js)
    driver = _CdpDriver(SimpleNamespace(), tab)
    monkeypatch.setattr(driver, "_wait_for_document", lambda seconds: False)
    with pytest.raises(BrowserNavigationError):
        driver.get("https://e.tb.cn/example")
