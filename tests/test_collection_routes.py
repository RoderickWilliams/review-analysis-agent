"""Route regressions: no credentials, platform network or actual browser in unit cases."""
from types import SimpleNamespace

import pytest

from reviewagent import browser_collection, browser_session, config, public_collection


def test_public_success_does_not_require_login_or_browser(monkeypatch):
    monkeypatch.setattr(config, "SCRAPING_ENABLED", True)
    actual = [{"review_text": "真实接口样本", "comment_id": "fixture"}]
    monkeypatch.setattr(public_collection, "public_reviews", lambda *args, **kwargs: actual)
    def unexpected(*args, **kwargs):
        raise AssertionError("Public success must not launch a browser or login")
    monkeypatch.setattr(browser_collection, "open_driver", unexpected)
    monkeypatch.setattr(browser_collection.AutoLoginManager, "ensure_session", unexpected)
    assert browser_collection.collect_source({"platform": "jd", "url": "https://item.jd.com/123.html"}, 10, lambda: False) == actual


def test_hash_url_never_invents_a_numeric_sku():
    assert public_collection.product_id("https://item.jd.com/product/O6nIk1e7MelYrOF5hQnjow.html", "jd") == ""
    assert public_collection.product_id("https://item.jd.com/123456.html", "jd") == "123456"


def test_comment_payload_ignores_product_copy_and_preserves_unknown_rating():
    source = {"platform": "taobao", "url": "https://item.taobao.com/item.htm?id=123"}
    assert public_collection.comment_rows({"product": {"description": "好评商品", "content": "卖家文案"}}, "taobao") == []
    rows = public_collection.comment_rows({"data": {"rateList": [{"rateContent": "拉链卡顿", "rateDate": "2026-10-01"}]}}, "taobao")
    review = public_collection.normalize_comment(rows[0], source, "fixture")
    assert review["rating"] is None
    assert review["review_date"] == "2026-10-01"
    assert review["source_url"] == source["url"]


def test_edge_can_be_selected_without_changing_default_browser(monkeypatch, tmp_path):
    executable = tmp_path / "Microsoft/Edge/Application/msedge.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.setattr(config, "BROWSER_PREFERENCE", "edge")
    assert browser_session.default_browser() == ("edge", str(executable))


def test_explicit_public_denial_stops_without_browser_fallback(monkeypatch):
    class Response:
        status_code = 403
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Session:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs):
            assert kwargs["allow_redirects"] is False
            assert self.trust_env is False
            return Response()
    monkeypatch.setattr(public_collection.requests, "Session", Session)
    with pytest.raises(browser_collection.CollectionPaused) as exc:
        public_collection.public_reviews({"platform": "jd", "url": "https://item.jd.com/123456.html"}, 10, lambda: False)
    assert exc.value.code == "rate_limited"


def test_account_restriction_stops_remaining_links_of_same_platform(monkeypatch):
    from reviewagent import collection
    sources = [
        {"platform": "jd", "url": "https://item.jd.com/111.html"},
        {"platform": "jd", "url": "https://item.jd.com/222.html"},
        {"platform": "taobao", "url": "https://item.taobao.com/item.htm?id=333"},
    ]
    calls = []
    monkeypatch.setattr(collection, "_sources", lambda analysis: sources)
    def capture(source, limit, cancelled, **kwargs):
        calls.append(source["url"])
        if source["platform"] == "jd":
            raise browser_collection.CollectionPaused("平台账号异常", code="account_restricted")
        return [{"review_text": "这件衣服拉链卡顿，需要反复调整", "platform": "taobao", "comment_id": "fixture"}]
    monkeypatch.setattr(browser_collection, "collect_source", capture)
    record = {"reviews": [], "request": {"platforms": ["jd", "taobao"], "tier": "custom", "per_product_limit": 1}}
    result = collection.collect_into_analysis(record, lambda: False)
    assert calls == [sources[0]["url"], sources[2]["url"]]
    assert result["collection"]["sources"][1]["status"] == "platform_paused"
    assert len(result["reviews"]) == 1


def test_same_platform_concurrent_request_does_not_start_capture(monkeypatch):
    guard = browser_collection._platform_guards["jd"]
    guard.acquire()
    try:
        def unexpected(*args, **kwargs):
            raise AssertionError("Concurrent platform capture must not run")
        monkeypatch.setattr(browser_collection, "_collect_source", unexpected)
        with pytest.raises(browser_collection.CollectionPaused) as exc:
            browser_collection.collect_source({"platform": "jd"}, 10, lambda: False)
        assert exc.value.code == "platform_busy"
    finally:
        guard.release()
