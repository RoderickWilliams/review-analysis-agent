"""独立 CLI：平台自动识别与参数传递（不依赖 object_resolver 的测试）。"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reviewagent_crawler_cli", ROOT / "crawler.py")
crawler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawler)


def test_xhslink_cn_is_detected_as_xhs():
    assert crawler.platform_from_url("https://xhslink.cn/o/7zUsGv1lB2l") == "xhs"
    assert crawler.platform_from_url("https://www.xhslink.cn/o/7zUsGv1lB2l") == "xhs"


def test_existing_platform_detection_is_unchanged():
    assert crawler.platform_from_url("https://xhslink.com/o/abc") == "xhs"
    assert crawler.platform_from_url("https://www.xiaohongshu.com/discovery/item/abc") == "xhs"
    assert crawler.platform_from_url("https://detail.tmall.com/item.htm?id=1") == "tmall"
    assert crawler.platform_from_url("https://item.taobao.com/item.htm?id=1") == "taobao"
    assert crawler.platform_from_url("https://e.tb.cn/h.abc") == "taobao"
    assert crawler.platform_from_url("https://item.jd.com/100.html") == "jd"


def test_cli_passes_detected_platform_into_collection(monkeypatch, tmp_path):
    from reviewagent import browser_collection

    captured = {}

    def fake_collect(source, limit, cancelled, **kwargs):
        captured.update(source)
        captured["limit"] = limit
        return [{"review_text": "一条真实评论", "comment_id": "c1"}]

    monkeypatch.setattr(browser_collection, "collect_source", fake_collect)
    out = tmp_path / "reviews.json"
    monkeypatch.setattr(sys, "argv", ["crawler.py", "--url", "https://xhslink.cn/o/7zUsGv1lB2l",
                                      "--out", str(out), "--quiet"])
    assert crawler.main() == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert captured["platform"] == "xhs"
    assert payload["platform"] == "xhs"
    assert payload["status"] == "ok"
    assert payload["count"] == 1
