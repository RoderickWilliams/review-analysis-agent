"""京东评论接口在专用浏览器会话里读取（纯 requests 会被 444 拒绝）。"""
import json

from reviewagent import browser_collection as bc


class FakeDriver:
    def __init__(self, pages):
        self.pages = list(pages)
        self.urls = []

    def get(self, url):
        self.urls.append(url)

    def execute_script(self, script, *args):
        page = self.pages.pop(0) if self.pages else ""
        return page if isinstance(page, str) else json.dumps(page, ensure_ascii=False)


def test_jd_browser_reviews_pages_until_empty(monkeypatch):
    monkeypatch.setattr(bc, "_wait", lambda seconds, cancelled: None)
    driver = FakeDriver([
        {"comments": [{"id": 1, "content": "好评", "creationTime": "2026-01-01"}]},
        {"comments": [{"id": 2, "content": "一般", "creationTime": "2026-01-02"}]},
        {"comments": []},
    ])
    rows = bc._jd_browser_reviews(driver, "100078467468", 50, lambda: False, None)
    assert [row["id"] for row in rows] == [1, 2]
    assert [row["_jd_page"] for row in rows] == [1, 2]
    assert "productId=100078467468" in driver.urls[0]
    assert "page=1" in driver.urls[1]


def test_jd_browser_reviews_stops_on_forbidden_body(monkeypatch):
    monkeypatch.setattr(bc, "_wait", lambda seconds, cancelled: None)
    driver = FakeDriver(["<html>The Request Forbidden</html>"])
    assert bc._jd_browser_reviews(driver, "1", 10, lambda: False, None) == []

def test_jd_collection_opens_headless_browser(monkeypatch):
    captured = {}

    class FakeBrowser(FakeDriver):
        def start_review_listener(self):
            return None

        def quit(self):
            return None

    def fake_open(platform, headless=False):
        captured["platform"] = platform
        captured["headless"] = headless
        return FakeBrowser([
            {"comments": [{"id": 1, "content": "好评", "creationTime": "2026-01-01", "guid": "g1"}]},
            {"comments": []},
        ])

    from reviewagent import config
    monkeypatch.setattr(config, "SCRAPING_ENABLED", True)
    monkeypatch.setattr(bc, "open_driver", fake_open)
    monkeypatch.setattr(bc, "_wait", lambda seconds, cancelled: None)
    from reviewagent import public_collection
    monkeypatch.setattr(public_collection, "public_reviews", lambda *args, **kwargs: [])

    source = {"platform": "jd", "url": "https://item.jd.com/100078467468.html", "title": "测试商品"}
    rows = bc._collect_source(source, 10, lambda: False)
    assert captured["headless"] is True
    assert len(rows) == 1

def test_normalize_comment_keeps_source_locator():
    from reviewagent.public_collection import normalize_comment

    review = normalize_comment({"id": "c1", "content": "一条评论", "creationTime": "2026-01-01"},
                               {"platform": "jd", "url": "https://item.jd.com/1.html"},
                               "owned_browser_jd_api", locator={"kind": "jd_comment_api", "page": 2})
    assert review["source_locator"] == {"kind": "jd_comment_api", "page": 2}
