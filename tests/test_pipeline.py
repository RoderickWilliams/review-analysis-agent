# -*- coding: utf-8 -*-
"""pipeline：注入分析器后跑通全链路，产物与摘要都要可用。"""
from __future__ import annotations

import json
import os

import pytest

from reviewagent.pipeline import analyze_reviews, summarize


def test_empty_reviews_raises():
    with pytest.raises(ValueError):
        analyze_reviews([], "测试品", save_history=False)


def test_full_pipeline_with_injected_agent(sample_reviews, fake_agent):
    result = analyze_reviews(
        sample_reviews, "测试手机", save_history=False, agent=fake_agent
    )

    assert result["review_count"] == len(sample_reviews)
    assert result["report"]["total_reviews"] == len(sample_reviews)
    assert os.path.isfile(result["html_report_path"])
    assert os.path.isfile(result["json_path"])

    payload = json.loads(open(result["json_path"], encoding="utf-8").read())
    assert payload["product_name"] == "测试手机"
    assert "report" in payload and "trust_report" in payload
    assert payload["trust_report"]["overall_trust_score"] <= 100
    assert len(fake_agent.batch_calls) == 1


def test_pipeline_saves_history_when_requested(sample_reviews, fake_agent):
    from reviewagent import store

    result = analyze_reviews(
        sample_reviews, "测试手机", save_history=True, agent=fake_agent
    )
    assert result["record_id"]
    record = store.get_history(result["record_id"])
    assert record["product_name"] == "测试手机"
    assert record["review_count"] == len(sample_reviews)


def test_summarize_mentions_trust_score(sample_reviews, fake_agent):
    result = analyze_reviews(
        sample_reviews, "测试手机", save_history=False, agent=fake_agent
    )
    text = summarize(result)
    assert "Trust Score" in text
    assert "测试手机" in text or "分析完成" in text
