# -*- coding: utf-8 -*-
"""内容生产包（content_kit）的离线测试：不调用模型、不联网。"""
from __future__ import annotations

from reviewagent.insights.content_kit import build_content_kit

NOTES = [
    {
        "note_id": "n1",
        "title": "油皮粉底液实测：上脸两小时就闷痘",
        "type": "normal",
        "tags": ["油皮", "粉底液", "实测"],
        "stats": {"liked": 120, "collected": 40, "comment": 8},
        "source_url": "https://www.xiaohongshu.com/explore/n1",
        "images": [
            {"index": 0, "width": 1080, "height": 1440, "src": "https://img.example/1.jpg"},
            {"index": 1, "width": 1080, "height": 1080, "src": "https://img.example/2.jpg"},
        ],
    },
    {
        "note_id": "n2",
        "title": "油皮底妆怎么选？看这 3 个细节",
        "type": "video",
        "tags": ["油皮", "底妆", "选购"],
        "stats": {"liked": 30, "collected": 12, "comment": 2},
        "source_url": "https://www.xiaohongshu.com/explore/n2",
        "images": [],
    },
]

PAINS = [
    {
        "id": "pp-1",
        "rank": 1,
        "statement": "上脸两小时就闷痘",
        "category": "使用体验",
        "severity": 3,
        "verified": True,
        "evidence": [{
            "review_id": "c1",
            "quote": "上脸两小时就开始闷痘，油皮真的受不了",
            "source_url": "https://www.xiaohongshu.com/explore/n1",
            "like": 8,
        }],
    },
    {
        "id": "pp-2",
        "rank": 2,
        "statement": "下午会斑驳",
        "category": "效果",
        "severity": 2,
        "verified": True,
        "evidence": [{
            "review_id": "c2",
            "quote": "遮瑕力可以，但下午会斑驳",
            "source_url": "https://www.xiaohongshu.com/explore/n1",
            "like": 2,
        }],
    },
    {
        "id": "pp-3",
        "rank": 3,
        "statement": "价格偏高",
        "category": "价格",
        "severity": 1,
        "verified": True,
        "evidence": [{
            "review_id": "c3",
            "quote": "好用但价格偏高，学生党要想想",
            "source_url": "https://www.xiaohongshu.com/explore/n1",
            "like": 1,
        }],
    },
    {
        "id": "pp-4",
        "rank": 4,
        "statement": "未验证的说法",
        "category": "其他",
        "severity": 2,
        "verified": False,
        "evidence": [],
    },
]


def _kit():
    return build_content_kit(
        "轻透粉底液",
        notes=NOTES,
        pain_points=PAINS,
        improvements=[{"id": "im-1", "priority": "P0"}],
        topics=[{"id": "tp-1"}],
        audience="油皮",
    )


def test_content_kit_builds_brief_and_eight_sections():
    kit = _kit()
    assert kit["status"] == "ready"
    assert kit["audience"] == "油皮"
    assert len(kit["brief"]["selling_points"]) == 3
    assert kit["brief"]["detail_page"]["section_count"] == 8
    assert [item["no"] for item in kit["brief"]["detail_page"]["sections"]] == list(range(1, 9))
    assert kit["brief"]["short_video"]["duration_seconds"] == 15
    assert len(kit["brief"]["short_video"]["beats"]) == 5
    assert [item["code"] for item in kit["brief"]["multilingual"]["languages"]] == ["en"]
    assert kit["brief"]["multilingual"]["status"].startswith("待翻译")
    assert kit["brief"]["hero_image"]["ratios"][0]["ratio"] == "1:1"
    assert "根治" in kit["claim_guard"]["forbidden_terms"]
    assert kit["claim_guard"]["allowed_evidence_claims"]


def test_content_kit_indexes_images_with_ratios_and_low_confidence():
    kit = _kit()
    material = kit["material_index"]
    assert material["total_images"] == 2
    assert material["notes_with_images"] == 1
    assert material["low_confidence"] is True
    assert material["entries"][0]["ratio"] == "0.75"
    assert material["entries"][0]["orientation"] == "竖图"
    assert material["entries"][1]["orientation"] == "方图"
    assert material["cover_candidates"]


def test_content_kit_style_card_is_text_only_and_layered_cards_have_no_render():
    kit = _kit()
    style = kit["style_card"]
    assert style["status"] == "text_signals_only"
    assert style["observed"]["median_title_length"] > 0
    assert style["recommendations"]["palette"] is None
    assert style["low_confidence"] is True
    layered = kit["layered_cards"]
    assert layered["status"] == "schema_only_no_render"
    assert len(layered["cards"]) == 3


def test_content_kit_without_verified_pains_is_insufficient():
    kit = build_content_kit(
        "未知产品",
        notes=[],
        pain_points=[{"id": "pp-1", "statement": "没有证据", "verified": False}],
    )
    assert kit["status"] == "insufficient_evidence"
    assert kit["brief"]["selling_points"] == []
    assert kit["brief"]["detail_page"]["section_count"] == 8
    assert kit["material_index"]["total_images"] == 0
    assert any("没有已验证痛点" in item for item in kit["warnings"])
