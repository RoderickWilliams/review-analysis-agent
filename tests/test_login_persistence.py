"""Login regression cases; no real browser, credential or platform requests."""
import json
import time
from types import SimpleNamespace

import pytest

from reviewagent import auto_login
from reviewagent.scrapers import login_manager


@pytest.mark.parametrize("module,manager_type", [
    (auto_login, auto_login.AutoLoginManager),
    (login_manager, login_manager.LoginManager),
])
def test_saved_at_is_not_a_platform_expiry(monkeypatch, tmp_path, module, manager_type):
    monkeypatch.setattr(module, "COOKIE_DIR", str(tmp_path))
    record = {"saved_at": time.time() - 90 * 86400, "cookies": {"fixture": "fake"}}
    cookie_file = tmp_path / "jd_cookies.json"
    cookie_file.write_text(json.dumps(record), encoding="utf-8")
    manager = manager_type()
    assert manager.load_cookies("jd") == {"fixture": "fake"}
    record["expires_at"] = time.time() - 1
    cookie_file.write_text(json.dumps(record), encoding="utf-8")
    assert manager.load_cookies("jd") is None


@pytest.mark.parametrize("url,has_cookies,has_account,expected", [
    ("https://www.jd.com/", True, True, True),
    ("https://jd.com.evil.example/", True, True, False),
    ("https://evil.example/?next=jd.com", True, True, False),
    ("https://passport.jd.com/new/login.aspx", True, True, False),
    ("https://www.jd.com/", False, True, False),
    ("https://www.jd.com/", True, False, False),
])
def test_login_requires_trusted_host_session_and_account_ui(url, has_cookies, has_account, expected):
    manager = auto_login.AutoLoginManager.__new__(auto_login.AutoLoginManager)
    element = SimpleNamespace(is_displayed=lambda: True, text="fixture-user")
    driver = SimpleNamespace(
        current_url=url,
        get_cookies=lambda: [{"name": name, "value": "fake"} for name in ("pt_key", "pt_pin")] if has_cookies else [],
        find_elements=lambda *args: [element] if has_account else [],
    )
    assert manager._is_login_success(driver, "jd") is expected


def test_timeout_closes_only_created_driver(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_login, "COOKIE_DIR", str(tmp_path))
    closed = []
    driver = SimpleNamespace(get=lambda url: None, quit=lambda: closed.append(True))
    manager = auto_login.AutoLoginManager()
    monkeypatch.setattr(manager, "_get_driver", lambda: driver)
    result = manager.auto_login("jd", timeout=0)
    assert result["success"] is False
    assert closed == [True]
