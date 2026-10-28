"""淘宝/天猫手机短链：最终 URL 不含 ID 时，用可信字段重建规范采集入口。"""
from types import SimpleNamespace

from reviewagent import object_resolver

SHARE = "【淘宝】大促价保 https://e.tb.cn/h.jUVuziuunaR8cSd?tk=UgrkTB2KzVv CZ001 「Folkmanis小浣熊玩偶娃娃毛绒婴儿仿真玩具礼物早教手偶抱睡公仔」"


def fake_request(url, **kwargs):
    return SimpleNamespace(url="https://detail.tmall.com/item.htm?app=chrome&bxsign=abc",
                           text='<link rel="canonical" href="https://detail.tmall.com/item.htm?id=568742960823&app=chrome&bxsign=abc">')


def no_id_request(url, **kwargs):
    return SimpleNamespace(url="https://detail.tmall.com/item.htm?app=chrome&bxsign=abc",
                           text="<html><body>价格 408 元，客服电话 13800138000，编码 12345</body></html>")


def test_canonical_link_rebuilds_entry_and_drops_mobile_params(monkeypatch):
    monkeypatch.setattr(object_resolver, "_request", fake_request)
    data = object_resolver.resolve_object(SHARE)
    assert data["url"] == "https://detail.tmall.com/item.htm?id=568742960823"
    assert "app=chrome" not in data["url"] and "bxsign" not in data["url"]
    assert data["input_url"] == "https://e.tb.cn/h.jUVuziuunaR8cSd?tk=UgrkTB2KzVv"
    assert data["platform"] in {"taobao", "tmall"}
    assert data["platform_id"] == "568742960823"


def test_embedded_item_id_is_trusted_context(monkeypatch):
    def request(url, **kwargs):
        return SimpleNamespace(url="https://detail.tmall.com/item.htm",
                               text='<script>window.__DATA__ = {"itemId": "568742960823", "title": "示例"}</script>')
    monkeypatch.setattr(object_resolver, "_request", request)
    data = object_resolver.resolve_object(SHARE)
    assert data["url"] == "https://detail.tmall.com/item.htm?id=568742960823"


def test_random_numbers_are_not_treated_as_item_id(monkeypatch):
    monkeypatch.setattr(object_resolver, "_request", no_id_request)
    data = object_resolver.resolve_object(SHARE)
    assert data["url"].startswith("https://e.tb.cn/")
    assert not data["platform_id"]
    assert any("不含商品 ID" in item for item in data["warnings"])


def test_short_digit_sequences_are_ignored(monkeypatch):
    def request(url, **kwargs):
        return SimpleNamespace(url="https://detail.tmall.com/item.htm",
                               text='<a href="https://detail.tmall.com/item.htm?id=12345">短编号</a>')
    monkeypatch.setattr(object_resolver, "_request", request)
    data = object_resolver.resolve_object(SHARE)
    assert data["url"].startswith("https://e.tb.cn/")


def test_final_url_with_id_is_kept(monkeypatch):
    def request(url, **kwargs):
        return SimpleNamespace(url="https://detail.tmall.com/item.htm?id=568742960823&spm=a1",
                               text="<html></html>")
    monkeypatch.setattr(object_resolver, "_request", request)
    data = object_resolver.resolve_object(SHARE)
    assert data["url"].startswith("https://detail.tmall.com/item.htm?id=568742960823")
    assert data["platform_id"] == "568742960823"
