"""Offline cases for owned profiles and source checkpoints. No real login."""
import json
from types import SimpleNamespace

import pytest

from reviewagent import auto_login, browser_session, collection
from reviewagent.browser_collection import CollectionPaused, _allowed_url


def test_profile_lease_cannot_be_shared_and_is_released(tmp_path):
    profile = tmp_path / "profile"
    first = browser_session._ProfileLease(profile)
    try:
        with pytest.raises(browser_session.BrowserProfileBusy):
            browser_session._ProfileLease(profile)
    finally:
        first.close()
    second = browser_session._ProfileLease(profile)
    second.close()
    second.close()


def test_owned_driver_quit_is_idempotent_even_when_browser_fails():
    closed = []
    def fail_quit():
        closed.append("driver")
        raise RuntimeError("fixture closed")
    owned = browser_session.OwnedDriver(SimpleNamespace(quit=fail_quit), SimpleNamespace(close=lambda: closed.append("lease")))
    with pytest.raises(RuntimeError):
        owned.quit()
    owned.quit()
    assert closed == ["driver", "lease"]


def test_marker_stores_no_cookie_and_platform_profiles_are_separate(monkeypatch, tmp_path):
    monkeypatch.setattr(browser_session.config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(browser_session, "default_browser", lambda: ("chrome", "unused"))
    profile = browser_session.profile_directory("taobao", "chrome")
    profile.mkdir(parents=True)
    browser_session.record_authenticated(SimpleNamespace(_profile_directory=profile), "tmall")
    assert browser_session.has_saved_session("taobao")
    assert not browser_session.has_saved_session("jd")
    assert browser_session.profile_directory("tmall", "chrome") == profile
    marker = json.loads((profile / ".reviewagent-session.json").read_text(encoding="utf-8"))
    assert set(marker) == {"platform", "last_confirmed_at", "state"}


def test_expired_profile_verification_opens_interactive_window(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_login, "COOKIE_DIR", str(tmp_path))
    monkeypatch.setattr(auto_login, "has_saved_session", lambda platform: True)
    calls = []
    manager = auto_login.AutoLoginManager()
    def fake_login(platform, **kwargs):
        calls.append(kwargs.get("headless", False))
        headless = kwargs.get("headless", False)
        return {"success": not headless, "status": "needs_login" if headless else "authenticated"}
    monkeypatch.setattr(manager, "auto_login", fake_login)
    assert manager.ensure_session("jd")["success"]
    assert calls == [True, False]


@pytest.mark.parametrize("url,allowed", [
    ("https://item.jd.com/123.html", True),
    ("https://jd.com.evil.example/123.html", False),
    ("https://example.com/?next=jd.com", False),
    ("https://user:secret@item.jd.com/123.html", False),
    ("https://item.jd.com:8443/123.html", False),
    ("http://item.jd.com/123.html", False),
])
def test_collection_source_stays_on_trusted_https_hosts(url, allowed):
    assert _allowed_url(url, "jd") is allowed


def _record():
    return {"object": {"platform": "jd", "url": "https://item.jd.com/123.html"},
            "request": {"platforms": ["jd"], "window_months": 12, "tier": "custom", "per_product_limit": 1}, "reviews": []}


def test_interrupted_source_keeps_delivered_batch(monkeypatch):
    from reviewagent import browser_collection
    snapshots = []
    def capture(source, limit, cancelled, *, on_batch=None, **kwargs):
        on_batch([{"review_text": "杯盖接缝存在漏水，旋紧后仍然没有改善", "platform": "jd", "comment_id": "fixture-1"}])
        raise CollectionPaused("验证后再继续", code="verification_required")
    monkeypatch.setattr(browser_collection, "collect_source", capture)
    result = collection.collect_into_analysis(_record(), lambda: False,
              on_checkpoint=lambda record: snapshots.append(json.loads(json.dumps(record))))
    assert len(result["reviews"]) == 1
    assert result["collection"]["gaps"][0]["code"] == "verification_required"
    assert any(len(record.get("reviews", [])) == 1 for record in snapshots)


def test_retry_skips_completed_source(monkeypatch):
    from reviewagent import browser_collection
    calls = []
    def capture(source, limit, cancelled, **kwargs):
        calls.append(source["url"])
        return [{"review_text": "杯盖接缝存在漏水，旋紧后仍然没有改善", "platform": "jd", "comment_id": "fixture-1"}]
    monkeypatch.setattr(browser_collection, "collect_source", capture)
    record = collection.collect_into_analysis(_record(), lambda: False)
    retried = collection.collect_into_analysis(record, lambda: False)
    assert len(calls) == 1
    assert len(retried["reviews"]) == 1


def test_empty_platforms_never_launch_collection(monkeypatch):
    from reviewagent import browser_collection
    def unexpected(*args, **kwargs):
        pytest.fail("No source should be opened")
    monkeypatch.setattr(browser_collection, "collect_source", unexpected)
    record = _record()
    record["request"]["platforms"] = []
    with pytest.raises(ValueError):
        collection.collect_into_analysis(record, lambda: False)
