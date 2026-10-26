# -*- coding: utf-8 -*-
"""洞察引擎的离线测试：不调真实模型。"""
from __future__ import annotations

import json

from reviewagent.insights import (
    analyze_pain_points,
    build_topics,
    generate_improvements,
    priority_for,
    scan_risk_words,
)
from reviewagent.insights.pain_points import cluster_points, rank_points
from reviewagent.insights.textutil import parse_json_any, quote_in_text
from reviewagent.insights.topics import TEMPLATES, detect_audience


def _docs():
    return [
        {"review_id": "r1", "text": "油皮夏天用这个防晒太闷了，下午就闷出两颗痘。", "like": 12,
         "source_url": "https://x/1", "note_title": "油皮防晒"},
        {"review_id": "r2", "text": "同样油皮，用两天就长闭口，不会回购", "like": 5,
         "source_url": "https://x/2"},
        {"review_id": "r3", "text": "包装很好看，送人有面子", "like": 1, "source_url": "https://x/3"},
    ]


def _pain_llm(payload, error=None):
    calls = []

    def call(prompt):
        calls.append(prompt)
        if error:
            raise error
        return json.dumps(payload, ensure_ascii=False)
    call.calls = calls
    return call


# ── 文本工具 ──────────────────────────────────────────────────

def test_quote_matching_tolerates_spacing_and_punctuation():
    assert quote_in_text("下午就闷出两颗痘", "油皮夏天用这个防晒太闷了，下午就闷出两颗痘。")
    assert quote_in_text("闷 出 两 颗 痘", "下午就闷出两颗痘")
    assert not quote_in_text("完全编造的一句话", "下午就闷出两颗痘")
    assert quote_in_text("闷痘", "下午就闷出两颗痘") is False  # 过短的引语不认，防止碰巧命中


def test_parse_json_any_handles_fences_and_arrays():
    assert parse_json_any('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_any('前言 [{"a": 1}] 后记') == [{"a": 1}]
    assert parse_json_any("not json") is None


# ── 痛点提取与证据校验 ────────────────────────────────────────

def test_extract_keeps_verified_and_flags_fabricated_quotes():
    payload = {"pain_points": [
        {"statement": "油皮用着闷痘", "category": "人群不适配", "severity": 3,
         "evidence": [
             {"review_id": "r1", "quote": "下午就闷出两颗痘"},
             {"review_id": "r2", "quote": "这条原句不存在"},
             {"review_id": "r9", "quote": "下午就闷出两颗痘"},
         ]},
        {"statement": "包装与描述不符", "category": "包装", "severity": 1,
         "evidence": [{"review_id": "r3", "quote": "编造的包装破损"}]},
    ]}
    result = analyze_pain_points(_docs(), _pain_llm(payload))
    points = {point["statement"]: point for point in result["pain_points"]}
    assert points["油皮用着闷痘"]["verified"] is True
    assert points["油皮用着闷痘"]["frequency"] == 1
    assert len(points["油皮用着闷痘"]["evidence"]) == 1
    reasons = [item["reason"] for item in points["油皮用着闷痘"]["rejected_evidence"]]
    assert "引语在原文中找不到" in reasons and "评论编号不存在" in reasons
    assert points["包装与描述不符"]["verified"] is False
    assert result["verified_count"] == 1 and result["unverified_count"] == 1


def test_extract_batches_and_records_llm_errors():
    docs = _docs()
    calls = []

    def flaky(prompt):
        calls.append(prompt)
        if len(calls) == 2:
            raise RuntimeError("rate limited")
        return '{"pain_points": []}'

    result = analyze_pain_points(docs, flaky, batch_size=2)
    assert len(calls) == 2
    assert any("rate limited" in error for error in result["errors"])


def test_cluster_merges_same_category_and_keeps_evidence():
    points = [
        {"statement": "油皮用着闷痘", "category": "人群不适配", "severity": 2, "severity_label": "明显",
         "evidence": [{"review_id": "r1", "quote": "闷出两颗痘", "like": 3}], "rejected_evidence": [],
         "frequency": 1, "engagement": 2.0, "verified": True, "statements": ["油皮用着闷痘"]},
        {"statement": "油皮用着闷痘", "category": "人群不适配", "severity": 3, "severity_label": "严重",
         "evidence": [{"review_id": "r2", "quote": "长闭口", "like": 5}], "rejected_evidence": [],
         "frequency": 1, "engagement": 2.5, "verified": True, "statements": ["油皮用着闷痘"]},
    ]
    merged = cluster_points(points)
    assert len(merged) == 1
    assert merged[0]["severity"] == 3
    assert merged[0]["frequency"] == 2
    assert {item["review_id"] for item in merged[0]["evidence"]} == {"r1", "r2"}


def test_cluster_does_not_merge_across_categories():
    points = [
        {"statement": "油皮用着闷痘", "category": "人群不适配", "severity": 2, "severity_label": "明显",
         "evidence": [], "rejected_evidence": [], "frequency": 0, "engagement": 0, "verified": False,
         "statements": []},
        {"statement": "油皮用着闷痘", "category": "使用体验", "severity": 2, "severity_label": "明显",
         "evidence": [], "rejected_evidence": [], "frequency": 0, "engagement": 0, "verified": False,
         "statements": []},
    ]
    assert len(cluster_points(points)) == 2


def test_rank_puts_verified_first_and_assigns_ids():
    points = [
        {"statement": "未验证", "category": "其他", "severity": 3, "evidence": [], "rejected_evidence": [],
         "frequency": 0, "engagement": 0, "verified": False, "statements": ["未验证"]},
        {"statement": "已验证", "category": "质量", "severity": 2, "evidence": [{"review_id": "r1"}],
         "rejected_evidence": [], "frequency": 3, "engagement": 4.5, "verified": True, "statements": ["已验证"]},
    ]
    ranked = rank_points(points)
    assert ranked[0]["id"] == "pp-1" and ranked[0]["statement"] == "已验证"
    assert ranked[1]["id"] == "pp-2" and ranked[1]["rank"] == 2


# ── 改进方向 ──────────────────────────────────────────────────

def test_priority_rules_are_deterministic():
    assert priority_for(3, 1) == "P0"
    assert priority_for(3, 2) == "P0"
    assert priority_for(3, 3) == "P1"
    assert priority_for(2, 1) == "P1"
    assert priority_for(1, 3) == "P2"


def test_generate_improvements_rejects_unknown_ids_and_duplicates():
    points = [
        {"id": "pp-1", "statement": "闷痘", "category": "人群不适配", "severity": 3,
         "frequency": 2, "verified": True, "evidence": [{"quote": "闷出两颗痘", "source_url": "https://x/1"}]},
    ]
    payload = {"improvements": [
        {"pain_point_id": "pp-1", "action": "详情页标注肤质", "rationale": "减少错配",
         "effort": 1, "impact": 3, "verification": "退货率"},
        {"pain_point_id": "pp-1", "action": "重复建议", "effort": 1, "impact": 3},
        {"pain_point_id": "pp-9", "action": "凭空痛点", "effort": 1, "impact": 3},
        {"pain_point_id": "pp-1", "action": "", "effort": 1, "impact": 3},
    ]}
    result = generate_improvements(points, _pain_llm(payload))
    assert len(result["improvements"]) == 1
    item = result["improvements"][0]
    assert item["priority"] == "P0" and item["pain_statement"] == "闷痘"
    assert len(result["rejected"]) == 3


def test_generate_improvements_without_verified_points_returns_error():
    result = generate_improvements([{"id": "pp-1", "verified": False}], _pain_llm({}))
    assert result["improvements"] == [] and "没有已验证" in result["error"]


# ── 选题与风险词 ──────────────────────────────────────────────

def _points_for_topics():
    return [
        {"id": "pp-1", "statement": "油皮用着闷痘", "category": "人群不适配", "severity": 3,
         "frequency": 5, "verified": True, "evidence": [{"quote": "下午就闷出两颗痘", "source_url": "https://x/1"}]},
        {"id": "pp-2", "statement": "包装盒到手就压扁", "category": "包装", "severity": 2,
         "frequency": 3, "verified": True, "evidence": [{"quote": "盒子扁了", "source_url": "https://x/2"}]},
        {"id": "pp-3", "statement": "未验证的猜测", "category": "其他", "severity": 3,
         "frequency": 0, "verified": False, "evidence": []},
    ]


def test_build_topics_uses_verified_points_and_rotates_templates():
    result = build_topics(_points_for_topics(), limit=5)
    assert result["audience"] == "油皮"
    assert len(result["topics"]) == 2
    assert {topic["template_id"] for topic in result["topics"]} == {"test", "avoid"}
    for topic in result["topics"]:
        assert topic["pain_point_id"] in {"pp-1", "pp-2"}
        assert len(topic["titles"]) == 3 and all(len(title) <= 20 for title in topic["titles"])
        assert len(topic["cover"]) == 2 and all(len(line) <= 12 for line in topic["cover"])
        assert len(topic["sections"]) == 4
        assert len(topic["tags"]) == len(set(topic["tags"]))
        assert topic["evidence_quote"]


def test_build_topics_scans_risk_words_in_titles():
    point = {"id": "pp-1", "statement": "最有效的祛痘方案", "category": "效果", "severity": 3,
             "frequency": 9, "verified": True, "evidence": [{"quote": "用了就好", "source_url": "https://x/1"}]}
    result = build_topics([point], limit=1, templates=[TEMPLATES[0]])
    assert "最有效" in result["risk_hits"]
    assert result["topics"][0]["risk"]["level"] in {"中", "高"}


def test_detect_audience_prefers_specific_persona():
    assert detect_audience(["宿舍里用着不错", "学生党可以冲"]) == "学生党"
    assert detect_audience(["毫无线索的句子"]) == "目标用户"


def test_scan_risk_words_custom_list():
    result = scan_risk_words("这个绝对可靠", words=["绝对", "顶级"])
    assert result["words"] == ["绝对"] and result["level"] == "中"
    assert scan_risk_words("正常描述", words=["绝对"])["level"] == "低"