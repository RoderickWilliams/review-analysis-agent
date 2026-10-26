# -*- coding: utf-8 -*-
"""trust_report：字段兼容、重复检测、评分矛盾、突发与兜底。"""
from __future__ import annotations

import pytest


def test_empty_reviews_returns_neutral_report(trust_engine):
    report = trust_engine.generate_report([])
    assert report["overall_trust_score"] == 100
    assert "无评论数据" in report["summary"]


def test_extract_fields_reads_review_text_and_date():
    from reviewagent.trust_report import TrustReportEngine

    texts, ratings, timestamps = TrustReportEngine._extract_fields(
        [{"review_text": "续航不错", "rating": 4, "review_date": "2026-10-01"}]
    )
    assert texts == ["续航不错"]
    assert ratings == [4]
    assert timestamps == ["2026-10-01"]


def test_duplicate_detection_uses_review_text(trust_engine, duplicate_reviews):
    pytest.importorskip("sklearn")
    report = trust_engine.generate_report(duplicate_reviews)
    assert report["duplicate_groups"], "完全相同的两条评论应被归入同一重复组"
    assert len(report["duplicate_groups"][0]) == 2


def test_rating_sentiment_mismatch_reads_nested_sentiment(trust_engine):
    results = [
        {"rating": 5, "final_analysis": {"final_sentiment": "negative"}},
        {"rating": 1, "sentiment_analysis": {"real_sentiment": "positive"}},
        {"rating": 5, "final_analysis": {"final_sentiment": "positive"}},
    ]
    report = trust_engine.generate_report(
        [{"review_text": f"评论{i}", "rating": r["rating"]} for i, r in enumerate(results)],
        results,
    )
    assert report["mismatch_count"] == 2


def test_temporal_burst_detected(trust_engine):
    # 跨 4 天：前三天各 1 条，第四天 10 条；日均 3.25，阈值 9.75，触发突发
    reviews = [
        {"review_text": f"早期评论{i}", "rating": 5, "review_date": f"2026-09-{28 + i}"}
        for i in range(3)
    ]
    reviews += [
        {"review_text": f"集中好评{i}", "rating": 5, "review_date": "2026-10-01"}
        for i in range(10)
    ]
    report = trust_engine.generate_report(reviews)
    assert report["burst_detected"] is True


def test_single_day_cannot_judge_burst(trust_engine):
    # 只有一天的评论没有日均基线，引擎不判定为突发
    reviews = [
        {"review_text": f"好评内容{i}", "rating": 5, "review_date": "2026-10-01"}
        for i in range(5)
    ]
    report = trust_engine.generate_report(reviews)
    assert report["burst_detected"] is False


def test_report_has_all_keys(trust_engine, sample_reviews):
    report = trust_engine.generate_report(sample_reviews)
    assert set(report) >= {
        "overall_trust_score", "burst_detected", "duplicate_groups",
        "rating_anomaly", "length_uniformity_score", "repeated_phrases",
        "mismatch_count", "risk_level", "summary",
    }
    assert 0 <= report["overall_trust_score"] <= 100
    assert report["risk_level"] in ("low", "medium", "high")
