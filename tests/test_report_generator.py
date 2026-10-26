# -*- coding: utf-8 -*-
"""report_generator：离线生成 HTML，包含产品名与统计。"""
from __future__ import annotations

from reviewagent.report_generator import HTMLReportGenerator

from tests.fakes import fake_result


def test_generate_writes_html(tmp_path):
    reviews = [
        {"review_text": "很好用", "rating": 5},
        {"review_text": "太差了", "rating": 1},
    ]
    results = [fake_result(r) for r in reviews]
    report = {
        "authentic_positive_rate": 0.5,
        "key_findings": ["续航是亮点"],
        "top_complaints": ["客服响应慢"],
        "recommendations": ["补强售后"],
        "fake_review_risk": "low",
    }
    out = tmp_path / "report.html"
    path = HTMLReportGenerator().generate(results, report, output_path=str(out), product_name="测试手机")
    html = open(path, encoding="utf-8").read()
    assert "测试手机" in html
    assert "可信" in html
    assert out.stat().st_size > 1000


def test_extract_stats_average_trust():
    reviews = [
        {"review_text": "a", "rating": 5},
        {"review_text": "b", "rating": 1},
    ]
    results = [fake_result(r) for r in reviews]
    stats = HTMLReportGenerator()._extract_stats(results, {})
    assert stats["total"] == 2
    assert stats["avg_trust"] == 88
