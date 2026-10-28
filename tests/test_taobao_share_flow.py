"""The exact share input and URL must reach collection, including after redirect."""
from types import SimpleNamespace

import pytest

from reviewagent import object_resolver
from reviewagent.collection import _sources

SHORT = "https://e.tb.cn/h.jV8c4fYCZACJcJD?tk=3ihYTyugyvu"
SHARE = "【淘宝】大促价保 " + SHORT + " CZ009 「folkmanis背包鼠手偶毛绒玩具仿真老鼠公仔玩偶1-3岁早教儿童礼物」 点击链接直接打开 或者 淘宝搜索直接打开"


@pytest.mark.parametrize("value", [SHORT, SHARE])
def test_exact_taobao_share_reaches_collection_without_resolved_redirect(monkeypatch, value):
    monkeypatch.setattr(object_resolver, "_request", lambda url: SimpleNamespace(url=url))
    product = object_resolver.resolve_object(value)
    assert product["platform"] == "taobao"
    assert product["status"] == "needs_capture"
    record = {"object": product, "request": {"platforms": ["taobao"], "selected_urls": [SHORT]}}
    assert _sources(record) == [product]


def test_redirected_product_stays_selected_by_original_share_link(monkeypatch):
    canonical = "https://detail.tmall.com/item.htm?id=123456789"
    monkeypatch.setattr(object_resolver, "_request", lambda url: SimpleNamespace(url=canonical))
    product = object_resolver.resolve_object(SHARE)
    assert product["platform"] == "tmall"
    assert product["input_url"] == SHORT
    assert product["url"] == canonical
    record = {"object": product, "request": {"platforms": ["taobao"], "selected_urls": [SHORT]}}
    assert _sources(record) == [product]


def test_login_redirect_keeps_original_product_share_link(monkeypatch):
    monkeypatch.setattr(object_resolver, "_request", lambda url: SimpleNamespace(url="https://login.taobao.com/member/login.jhtml"))
    product = object_resolver.resolve_object(SHORT)
    assert product["url"] == SHORT
    assert product["platform"] == "taobao"


def test_lookalike_short_link_host_is_not_accepted():
    assert object_resolver.detect_platform("https://e.tb.cn.evil.example/item.htm?id=123") == "unknown"


def test_previously_failed_share_record_can_resume_with_correct_platform():
    product = {"url": SHORT, "platform": "unknown", "status": "needs_link", "gaps": [{"code": "unsupported_host"}]}
    record = {"object": product, "request": {"platforms": ["taobao"], "selected_urls": [SHORT]}}
    assert _sources(record) == [product]
    assert product["platform"] == "taobao"
    assert product["gaps"] == []
