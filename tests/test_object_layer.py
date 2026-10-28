# -*- coding: utf-8 -*-
"""v2 对象层：链接识别、京东商品页解析、同款匹配、报告骨架与 API。

这些测试不联网：京东解析通过 monkeypatch 替换 _request，其他平台只验证
「识别链接但不猜内容」的边界。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from reviewagent.object_resolver import detect_platform, extract_url, resolve_object
from reviewagent.report_builder import build_analysis_report
from reviewagent.same_product import build_same_products, compare_objects


JD_HTML = """
<html><body><script>
window._itemOnly = ({payload});
window._isLogin = false;
</script></body></html>
""".replace(
    "{payload}",
    json.dumps(
        {
            "item": {
                "skuName": "测试手机 12GB+256GB 曜石黑",
                "brandName": "测试品牌",
                "brandId": "99",
                "venderID": "123",
                "warestatus": "1",
                "category": ["手机通讯", "手机", "智能手机"],
                "image": ["//img.example.com/main.jpg"],
                "newColorSize": [
                    {"color": "曜石黑", "size": "12GB+256GB", "skuId": "1002", "imagePath": "//img.example.com/black.jpg"},
                    {"color": "月光白", "size": "12GB+256GB", "skuId": "1003"},
                ],
            },
            "shopName": "测试旗舰店",
        },
        ensure_ascii=False,
    ),
)


def _primary():
    return {
        "input": "https://item.jd.com/1001.html",
        "input_type": "url",
        "platform": "jd",
        "platform_label": "京东",
        "status": "resolved",
        "status_label": "已解析商品对象",
        "platform_id": "1001",
        "url": "https://item.jd.com/1001.html",
        "title": "测试手机 12GB+256GB 曜石黑",
        "brand": "测试品牌",
        "model": "测试手机",
        "key_specs": {"颜色": "曜石黑", "尺寸": "12GB+256GB"},
        "shop": "测试旗舰店",
        "category": ["手机通讯", "手机", "智能手机"],
        "image_url": "https://img.example.com/main.jpg",
        "variants": [
            {"sku_id": "1002", "color": "曜石黑", "size": "12GB+256GB", "title": "测试手机 · 曜石黑 / 12GB+256GB"},
            {"sku_id": "1003", "color": "月光白", "size": "12GB+256GB", "title": "测试手机 · 月光白 / 12GB+256GB"},
        ],
        "metadata_score": 100,
        "confidence": 0.99,
        "confidence_label": "高",
        "parser": "jd_item_only",
        "fetched_at": "2026-10-27T05:00:00+08:00",
        "evidence": [
            {
                "id": "ev-object-1",
                "type": "product_page",
                "title": "测试手机",
                "url": "https://item.jd.com/1001.html",
                "quote": "测试手机 12GB+256GB 曜石黑",
                "fields": ["title", "brand", "shop"],
            }
        ],
        "gaps": [{"code": "jd_reviews_unavailable", "label": "没有评论正文", "detail": "未抓取评论", "severity": "high"}],
        "warnings": [],
        "next_actions": [{"label": "补评论样本", "detail": "粘贴评论"}],
    }


# ── 链接识别与对象解析 ────────────────────────────────────────

def test_extract_url_and_platform():
    text = "【京东】测试手机 https://item.jd.com/1001.html 复制链接"
    assert extract_url(text) == "https://item.jd.com/1001.html"
    assert detect_platform("https://item.jd.com/1001.html") == "jd"
    assert detect_platform("https://detail.tmall.com/item.htm?id=1") == "tmall"
    assert detect_platform("https://www.xiaohongshu.com/explore/abc123") == "xhs"
    assert detect_platform("https://example.com/x") == "unknown"


def test_product_name_returns_search_links_not_invented_object():
    obj = resolve_object("测试手机 12GB+256GB")
    assert obj["status"] == "needs_link"
    assert obj["platform"] == "unknown"
    assert obj["title"] == ""
    assert obj["search_urls"]
    assert any(item["platform"] == "京东" and "search.jd.com" in item["url"] for item in obj["search_urls"])
    assert obj["gaps"][0]["code"] == "keyword_no_search"


def test_jd_parser_reads_public_page(monkeypatch):
    import reviewagent.object_resolver as resolver

    monkeypatch.setattr(
        resolver,
        "_request",
        lambda url, allow_redirects=True: SimpleNamespace(status_code=200, text=JD_HTML),
    )
    obj = resolve_object("https://item.jd.com/1001.html")
    assert obj["status"] == "resolved"
    assert obj["platform_id"] == "1001"
    assert obj["title"] == "测试手机 12GB+256GB 曜石黑"
    assert obj["brand"] == "测试品牌"
    assert obj["shop"] == "测试旗舰店"
    assert len(obj["variants"]) == 2
    assert obj["variants"][0]["url"].endswith("/1002.html")
    assert any(gap["code"] == "jd_reviews_unavailable" for gap in obj["gaps"])
    assert obj["message"].startswith("已从京东商品页解析")


def test_tmall_and_xhs_links_are_recognized_but_not_guessed():
    tmall = resolve_object("https://detail.tmall.com/item.htm?id=123456")
    assert tmall["platform"] == "tmall"
    assert tmall["status"] == "needs_capture"
    assert tmall["title"] == ""
    assert tmall["platform_id"] == "123456"

    xhs = resolve_object("https://www.xiaohongshu.com/explore/64f0abc")
    assert xhs["platform"] == "xhs"
    assert xhs["status"] == "needs_capture"
    assert xhs["title"] == ""


# ── 同款匹配 ──────────────────────────────────────────────────

def test_same_url_is_exact():
    primary = _primary()
    candidate = dict(primary)
    result = compare_objects(primary, candidate)
    assert result["level"] == "exact"
    assert result["score"] == 1.0
    assert any("同一商品" in reason for reason in result["reasons"])


def test_different_brand_is_competitor_not_same():
    primary = _primary()
    candidate = {
        "title": "测试手机 12GB+256GB 曜石黑",
        "brand": "别的品牌",
        "platform": "jd",
        "platform_id": "2001",
        "url": "https://item.jd.com/2001.html",
        "category": ["手机通讯", "手机", "智能手机"],
    }
    result = compare_objects(primary, candidate)
    assert result["level"] == "competitor"
    assert any("品牌不同" in item for item in result["mismatches"])


def test_same_spu_variants_keep_distinct_specs_and_unknown_extra_identity():
    primary = _primary()
    extra = {
        "title": "测试手机 12GB+256GB 曜石黑",
        "brand": "测试品牌",
        "platform": "tmall",
        "platform_id": "3001",
        "url": "https://detail.tmall.com/item.htm?id=3001",
        "category": ["手机通讯", "手机", "智能手机"],
        "status": "needs_capture",
    }
    result = build_same_products(primary, [extra])
    assert result["summary"]["total_candidates"] == 3
    assert result["summary"]["exact"] == 1
    assert result["summary"]["variant"] == 1
    assert result["summary"]["sibling_variants"] == 1
    assert result["summary"]["user_supplied"] == 1
    assert result["summary"]["auto_discovery"] == "not_started"
    assert all(candidate["price"] is None for candidate in result["candidates"])
    assert all(candidate["review_count"] is None for candidate in result["candidates"])
    statuses = {candidate["platform_id"]: candidate["match_level"] for candidate in result["candidates"]}
    assert statuses["3001"] == "uncertain"


# ── 报告骨架 ──────────────────────────────────────────────────

def test_report_without_reviews_is_honest_metadata_only():
    primary = _primary()
    match_result = build_same_products(primary)
    built = build_analysis_report(
        primary,
        match_result,
        ownership="own",
        input_text=primary["input"],
        tier="standard",
        window_months=12,
        reviews=[],
    )
    report = built["report"]
    assert built["status"] == "ready"
    assert report["stage"] == "metadata_only"
    assert report["dashboard"]["score"] is None
    assert report["dashboard"]["risk"] == "unknown"
    assert report["dashboard"]["review_count"] == 0
    assert report["diagnosis"]["status"] == "insufficient_data"
    assert report["pain_points"]["items"] == []
    assert report["improvements"]["items"] == []
    assert report["topics"]["items"] == []
    assert report["ops_plan"]["groups"] == []
    assert report["method"]["llm_used"] is False
    assert any(gap["code"] == "no_reviews_captured" for gap in report["gaps"])
    assert report["evidence"]
    assert report["competitors"]["items"]
    first = report["competitors"]["items"][0]
    assert first["match_reasons"] == first["reasons"]
    assert first["price"] is None


# ── API：解析、创建、读取、行动清单 ───────────────────────────

@pytest.fixture()
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from reviewagent.http_api import app
    from reviewagent import store

    store.clear_analyses()
    with TestClient(app) as test_client:
        yield test_client
    store.clear_analyses()


def test_analysis_api_round_trip(client, monkeypatch):
    monkeypatch.setattr("reviewagent.object_resolver.resolve_object", lambda text: _primary())

    created = client.post(
        "/v1/analysis",
        json={
            "input": "https://item.jd.com/1001.html",
            "ownership": "own",
            "tier": "standard",
            "window_months": 12,
            "reviews": [],
            "save": True,
        },
    )
    assert created.status_code == 200
    body = created.json()
    analysis_id = body["analysis_id"]
    assert body["status"] == "draft"
    assert body["report"]["dashboard"]["score"] is None
    assert body["report"]["object"]["title"] == "测试手机 12GB+256GB 曜石黑"
    assert "xx" not in json.dumps(body, ensure_ascii=False).lower()

    detail = client.get(f"/v1/analysis/{analysis_id}")
    assert detail.status_code == 200
    assert detail.json()["report"]["stage"] == "metadata_only"

    report = client.get(f"/v1/analysis/{analysis_id}/report")
    assert report.status_code == 200
    assert report.json()["analysis_id"] == analysis_id

    csv_resp = client.get(f"/v1/analysis/{analysis_id}/actions.csv")
    assert csv_resp.status_code == 200
    assert csv_resp.content.startswith("\ufeff".encode("utf-8"))
    assert "优先级,动作,依据" in csv_resp.text

    evidence_id = body["report"]["evidence"][0]["id"]
    evidence = client.get(f"/v1/analysis/{analysis_id}/evidence/{evidence_id}")
    assert evidence.status_code == 200
    assert evidence.json()["id"] == evidence_id


def test_object_resolve_endpoint(client, monkeypatch):
    monkeypatch.setattr("reviewagent.object_resolver.resolve_object", lambda text: _primary())
    resp = client.post("/v1/object/resolve", json={"input": "https://item.jd.com/1001.html"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"]["status"] == "resolved"
    assert body["match_summary"]["exact"] == 1
