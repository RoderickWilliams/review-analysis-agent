# -*- coding: utf-8 -*-
"""Scrapling 后端的解析、拦截识别与流水线分发测试（不联网、不启动浏览器）。"""
import json

import pytest

from reviewagent.scrapers import scrapling_backend as sb


HTML = """<html><body>
<div class="review-item">
  <p class="review-text">用了两周，续航给力</p>
  <span class="rating" title="4分"></span>
  <span class="user">张三</span>
  <time datetime="2026-10-01">10月1日</time>
  <span class="sku">黑色 256G</span>
  <a class="link" href="/r/1">详情</a>
</div>
<div class="review-item">
  <p class="review-text">质量太差，客服不理人</p>
  <span class="rating" title="1分"></span>
  <span class="user">李四</span>
  <time datetime="2026/10/02">10月2日</time>
  <span class="sku">白色</span>
  <a class="link" href="/r/2">详情</a>
</div>
<div class="review-item">
  <p class="review-text">用了两周，续航给力</p>
  <span class="rating" title="4分"></span>
  <span class="user">张三</span>
</div>
</body></html>"""

SELECTORS = {
    "platform": "taobao",
    "platform_name": "淘宝",
    "item": "div.review-item",
    "fields": {
        "review_text": "p.review-text::text",
        "rating": "span.rating::attr(title)",
        "reviewer_name": "span.user::text",
        "review_date": "time::attr(datetime)",
        "sku": "span.sku::text",
        "review_permalink": "a.link::attr(href)",
    },
}


class _Resp:
    def __init__(self, status, html, url="https://example.com/item/1"):
        self.status = status
        self.html_content = html
        self.url = url


def test_extract_reviews_fields_and_dedupe():
    pytest.importorskip("scrapling")
    reviews = sb.extract_reviews(HTML, SELECTORS, source_url="https://example.com/item/1", product_id="p1")
    assert len(reviews) == 2  # 第三条与第一条文本、昵称都相同，被去重
    first = reviews[0]
    assert first["review_text"] == "用了两周，续航给力"
    assert first["rating"] == 4
    assert first["reviewer_name"] == "张三"
    assert first["review_date"] == "2026-10-01"
    assert first["sku"] == "黑色 256G"
    assert first["review_permalink"] == "/r/1"
    assert first["platform"] == "淘宝"
    assert first["source_platform"] == "taobao"
    assert first["source_url"] == "https://example.com/item/1"
    assert first["product_id"] == "p1"
    assert first["extraction_method"] == "scrapling"
    assert first["is_demo"] is False


def test_extract_accepts_fetched_page_and_limit():
    pytest.importorskip("scrapling")
    page = sb.FetchedPage(url="https://example.com/item/1", status=200, html=HTML, mode="http")
    assert len(sb.extract_reviews(page, SELECTORS)) == 2
    assert len(sb.extract_reviews(HTML, SELECTORS, limit=1)) == 1


def test_extract_skips_empty_text():
    pytest.importorskip("scrapling")
    html = '<div class="review-item"><p class="review-text">   </p></div>'
    assert sb.extract_reviews(html, SELECTORS) == []


def test_rating_and_date_normalization():
    assert sb._parse_rating("4.5分") == 4.5
    assert sb._parse_rating("5") == 5
    assert sb._parse_rating("五星") is None
    assert sb._parse_rating("0") is None
    assert sb._parse_rating("6") is None
    assert sb._parse_rating("4.5/5", r"(\d+(?:\.\d+)?)/5") == 4.5
    assert sb._parse_date("2026年10月1日") == "2026-10-01"
    assert sb._parse_date("2026/10/02") == "2026-10-02"
    assert sb._parse_date("10月2日") == "10月2日"
    assert sb._parse_date("") == ""


def test_selector_map_validation(tmp_path):
    with pytest.raises(ValueError):
        sb.load_selector_map({"item": "div"})
    with pytest.raises(ValueError):
        sb.load_selector_map({"fields": {"review_text": "p::text"}})
    with pytest.raises(FileNotFoundError):
        sb.load_selector_map(tmp_path / "missing.json")
    path = tmp_path / "s.json"
    path.write_text(json.dumps(SELECTORS, ensure_ascii=False), encoding="utf-8")
    assert sb.load_selector_map(path)["platform"] == "taobao"


def test_parse_raises_when_scrapling_missing(monkeypatch):
    monkeypatch.setattr(sb, "SCRAPLING_AVAILABLE", False)
    with pytest.raises(sb.ScraplingUnavailable):
        sb.parse("<html></html>")
    with pytest.raises(sb.ScraplingUnavailable):
        sb.fetch("https://example.com/1")


def test_fetch_http_returns_page(monkeypatch):
    monkeypatch.setattr(sb, "_require_fetch", lambda: None)
    monkeypatch.setattr(sb, "_fetch_http", lambda url, timeout: _Resp(200, "<html>ok</html>"))
    page = sb.fetch("https://example.com/1", mode="http")
    assert page.status == 200
    assert page.html == "<html>ok</html>"
    assert page.mode == "http"


def test_fetch_auto_upgrades_on_challenge(monkeypatch):
    monkeypatch.setattr(sb, "_require_fetch", lambda: None)
    monkeypatch.setattr(sb, "_fetch_http", lambda url, timeout: _Resp(403, "<html>Just a moment...</html>"))
    monkeypatch.setattr(sb, "_fetch_stealth", lambda url, timeout, sel, headless: _Resp(200, "<html>real</html>"))
    page = sb.fetch("https://example.com/1", mode="auto")
    assert page.status == 200
    assert page.html == "<html>real</html>"
    assert page.mode == "auto:stealth"


def test_fetch_auto_keeps_http_when_clean(monkeypatch):
    calls = []
    monkeypatch.setattr(sb, "_require_fetch", lambda: None)
    monkeypatch.setattr(sb, "_fetch_http", lambda url, timeout: _Resp(200, "<html>ok</html>"))
    monkeypatch.setattr(sb, "_fetch_stealth", lambda *a, **k: calls.append(1))
    page = sb.fetch("https://example.com/1", mode="auto")
    assert page.mode == "http"
    assert calls == []


def test_fetch_rejects_unknown_mode(monkeypatch):
    monkeypatch.setattr(sb, "_require_fetch", lambda: None)
    with pytest.raises(ValueError):
        sb.fetch("https://example.com/1", mode="magic")


def test_stealth_failure_becomes_scrapling_unavailable(monkeypatch):
    monkeypatch.setattr(sb, "_require_fetch", lambda: None)
    monkeypatch.setattr(sb, "_fetch_http", lambda url, timeout: _Resp(403, "Just a moment"))
    monkeypatch.setattr(sb, "_fetch_stealth", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no browser")))
    with pytest.raises(sb.ScraplingUnavailable) as excinfo:
        sb.fetch("https://example.com/1", mode="auto")
    assert "Chromium" in str(excinfo.value)


def test_pipeline_dispatch_scrapling(monkeypatch, tmp_path):
    from reviewagent import config, pipeline

    monkeypatch.setattr(config, "SCRAPING_ENABLED", True)
    monkeypatch.setattr(config, "SCRAPER_BACKEND", "scrapling")
    monkeypatch.setattr(config, "SCRAPLING_SELECTORS", str(tmp_path / "s.json"))
    monkeypatch.setattr(config, "SCRAPLING_FETCH_MODE", "http")
    monkeypatch.setattr(config, "SCRAPLING_TIMEOUT", 5.0)
    monkeypatch.setattr(sb, "fetch_reviews", lambda *a, **k: [{"review_text": "好用", "product_name": "某手机"}])
    reviews, name = pipeline.collect_reviews("https://example.com/item/1", max_reviews=10)
    assert name == "某手机"
    assert reviews == [{"review_text": "好用", "product_name": "某手机"}]


def test_pipeline_scrapling_requires_selectors(monkeypatch):
    from reviewagent import config, pipeline

    monkeypatch.setattr(config, "SCRAPING_ENABLED", True)
    monkeypatch.setattr(config, "SCRAPER_BACKEND", "scrapling")
    monkeypatch.setattr(config, "SCRAPLING_SELECTORS", "")
    with pytest.raises(RuntimeError, match="选择器配置"):
        pipeline.collect_reviews("https://example.com/item/1")


def test_pipeline_unknown_backend(monkeypatch):
    from reviewagent import config, pipeline

    monkeypatch.setattr(config, "SCRAPING_ENABLED", True)
    monkeypatch.setattr(config, "SCRAPER_BACKEND", "selenium")
    with pytest.raises(RuntimeError, match="未知抓取后端"):
        pipeline.collect_reviews("https://example.com/item/1")
