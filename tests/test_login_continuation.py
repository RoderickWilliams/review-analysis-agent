"""Login handoff regressions; no browser, credentials or network requests."""
from types import SimpleNamespace

import pytest

from reviewagent import auto_login, browser_collection, browser_session


@pytest.fixture()
def result_page(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_login, "COOKIE_DIR", str(tmp_path))
    return SimpleNamespace(
        current_url="https://login.taobao.com/member/login.jhtml",
        get_cookies=lambda: [{"name": name, "value": "fixture"} for name in ("unb", "cookie2")],
        find_elements=lambda *args: [SimpleNamespace(is_displayed=lambda: True, text="测试账号")],
        execute_script=lambda script: "ready",
    )


def test_login_result_with_session_and_account_is_not_stuck_by_login_url(result_page):
    assert browser_collection._page_state(result_page, "taobao") == "login_complete"


def test_visible_verification_still_stops_authenticated_account(result_page):
    result_page.execute_script = lambda script: "verification_required"
    assert browser_collection._page_state(result_page, "taobao") == "verification_required"


def test_cookie_alone_cannot_confirm_login(result_page):
    result_page.find_elements = lambda *args: []
    result_page.execute_script = lambda script: False
    assert not auto_login.AutoLoginManager()._is_login_success(result_page, "taobao", allow_login_result=True)


def test_account_status_check_is_not_reported_as_qr_login(result_page):
    result_page.current_url = "https://passport.taobao.com/iv/normal_validate.htm"
    result_page.find_elements = lambda *args: []
    result_page.execute_script = lambda script: False if script.startswith("return /") else "ready"
    assert browser_collection._page_state(result_page, "taobao") == "identity_verification"


def test_completed_identity_check_still_needs_session_evidence(result_page):
    result_page.current_url = "https://passport.taobao.com/iv/normal_validate.htm"
    result_page.find_elements = lambda *args: []
    result_page.get_cookies = lambda: []
    result_page.execute_script = lambda script: True if script.startswith("return /") else "ready"
    assert browser_collection._page_state(result_page, "taobao") == "identity_verification"


@pytest.mark.parametrize("url", ["about:blank", "chrome://newtab/", "chrome://new-tab-page/"])
def test_blank_browser_page_never_enters_collection(url):
    page = SimpleNamespace(current_url=url, execute_script=lambda script: pytest.fail("blank page must be rejected before DOM inspection"))
    assert browser_collection._page_state(page, "taobao") == "blank_page"


def test_cdp_false_navigation_is_not_treated_as_success():
    tab = SimpleNamespace(url="about:blank", get=lambda *args, **kwargs: False)
    driver = browser_session._CdpDriver(SimpleNamespace(), tab)
    with pytest.raises(browser_session.BrowserNavigationError) as exc:
        driver.get("https://e.tb.cn/example")
    assert exc.value.code == "navigation_failed"


def test_cdp_navigation_error_is_safely_classified_without_full_url():
    def fail(*args, **kwargs):
        raise RuntimeError("net::ERR_NAME_NOT_RESOLVED at https://example.invalid/?secret=token")
    driver = browser_session._CdpDriver(SimpleNamespace(), SimpleNamespace(url="about:blank", get=fail))
    with pytest.raises(browser_session.BrowserNavigationError) as exc:
        driver.get("https://example.invalid/?secret=token")
    assert exc.value.code == "navigation_dns_failed"
    assert "secret" not in str(exc.value)


def test_login_can_follow_only_owned_trusted_product_tab():
    login = SimpleNamespace(tab_id="login", url="https://login.taobao.com/member/login.jhtml")
    product = SimpleNamespace(tab_id="product", url="https://item.taobao.com/item.htm?id=123")
    hostile = SimpleNamespace(tab_id="hostile", url="https://taobao.com.evil.example/item.htm?id=123")
    browser = SimpleNamespace(get_tabs=lambda: [login, hostile, product])
    driver = browser_session._CdpDriver(browser, login)
    assert driver.follow_login_tab("taobao") is True
    assert driver.tab is product


@pytest.mark.parametrize("final_state,expected_error", [("ready", None), ("needs_login", "login_redirect_loop")])
def test_login_continuation_returns_to_product_once(monkeypatch, tmp_path, final_state, expected_error):
    monkeypatch.setattr(auto_login, "COOKIE_DIR", str(tmp_path))
    states = iter(["needs_login", "login_complete", final_state])
    monkeypatch.setattr(browser_collection, "_page_state", lambda *args: next(states))
    monkeypatch.setattr(browser_collection, "_wait", lambda *args: None)
    monkeypatch.setattr(auto_login.AutoLoginManager, "_is_login_success", lambda *args, **kwargs: True)
    markers = []
    monkeypatch.setattr(browser_collection, "record_authenticated", lambda *args: markers.append(True))
    navigations, events = [], []
    driver = SimpleNamespace(window_handles=["fixture"], get=navigations.append, follow_login_tab=lambda platform: True)
    if expected_error:
        with pytest.raises(browser_collection.CollectionPaused) as exc:
            browser_collection._await_access(driver, "taobao", "https://item.taobao.com/item.htm?id=123", lambda: False, lambda *event: events.append(event))
        assert exc.value.code == expected_error
    else:
        browser_collection._await_access(driver, "taobao", "https://item.taobao.com/item.htm?id=123", lambda: False, lambda *event: events.append(event))
    assert navigations == ["https://item.taobao.com/item.htm?id=123"]
    assert markers == [True]
    assert any(event[0] == "authenticated" for event in events)
