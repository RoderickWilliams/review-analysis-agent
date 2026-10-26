# -*- coding: utf-8 -*-
"""sentiment_agent_core：解析、三步分析、错误回传与批量。"""
from __future__ import annotations

from reviewagent.sentiment_agent_core import ReviewAnalysisAgent

from tests.fakes import FakeLLMClient


def test_parse_json_accepts_fenced_output(agent):
    raw = "```json\n{\"a\": 1}\n```"
    assert agent._parse_json(raw) == {"a": 1}


def test_parse_json_extracts_braces(agent):
    assert agent._parse_json('prefix {"b": 2} suffix') == {"b": 2}


def test_parse_json_bad_input(agent):
    parsed = agent._parse_json("not json at all")
    assert parsed["error"] == "JSON解析失败"


def test_analyze_sentiment(agent, fake_client):
    result = agent.analyze_sentiment("续航很强", 5, "淘宝")
    assert result["sentiment_label"] == "真实好评"
    assert result["is_sarcastic"] is False
    assert len(fake_client.calls) == 1


def test_comprehensive_analysis(agent, fake_client):
    result = agent.comprehensive_analysis("续航很强", 5, "淘宝", "手机")
    assert set(result) >= {
        "review_text", "rating", "platform",
        "sentiment_analysis", "validity_analysis", "final_analysis",
    }
    assert result["final_analysis"]["trust_score"] == 88
    assert len(fake_client.calls) == 3


def test_llm_network_error_returns_structured_error():
    client = FakeLLMClient(error=RuntimeError("connect timeout"))
    agent = ReviewAnalysisAgent(model="test-model", client=client)
    result = agent.analyze_sentiment("任意评论", 3)
    assert result["error_type"] == "network"


def test_batch_analyze_counts_similar_neighbours(agent):
    reviews = [
        {"review_text": "质量很好，物流很快，下次还来", "rating": 5},
        {"review_text": "质量很好，物流很快，下次还来", "rating": 5},
        {"review_text": "完全不同的内容，讲的是包装盒设计", "rating": 4},
    ]
    results = agent.batch_analyze(reviews, product_name="测试品")
    assert len(results) == 3
    assert results[0]["similar_count"] >= 1
    assert results[2]["similar_count"] == 0


def test_generate_report_returns_statistics(agent):
    reviews = [
        {"review_text": "很好用", "rating": 5},
        {"review_text": "太差了", "rating": 1},
    ]
    results = agent.batch_analyze(reviews, product_name="测试品")
    report = agent.generate_report(results, product_name="测试品")
    assert report["total_reviews"] == 2
    assert report["sentiment_distribution"]["positive"] == 2
    assert report["suspicious_review_count"] == 0
