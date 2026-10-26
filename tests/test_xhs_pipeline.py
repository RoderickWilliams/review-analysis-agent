# -*- coding: utf-8 -*-
"""小红书六章链路的离线测试：注入假 agent 与假 LLM，不联网。"""
import copy
import json


from reviewagent import pipeline


CAPTURE = {
    "platform": "小红书",
    "run_dir": "E:/tmp/xhs-run",
    "captured_at": "2026-10-26T22:00:00",
    "notes": [
        {
            "note_id": "n1",
            "title": "油皮粉底液实测",
            "desc": "用了三周，闷痘但遮瑕好",
            "text": "用了三周，闷痘但遮瑕好",
            "source_url": "https://www.xiaohongshu.com/explore/n1",
            "stats": {"liked": 120, "comment": 2},
            "images": [
                {"index": 0, "width": 1080, "height": 1440, "src": "https://img.example/1.jpg"},
                {"index": 1, "width": 1080, "height": 1080, "src": "https://img.example/2.jpg"},
            ],
        }
    ],
    "reviews": [
        {
            "review_text": "上脸两小时就开始闷痘，油皮真的受不了",
            "comment_id": "c1",
            "comment_like": 8,
            "note_id": "n1",
            "note_title": "油皮粉底液实测",
            "source_url": "https://www.xiaohongshu.com/explore/n1",
            "source_platform": "小红书",
        },
        {
            "review_text": "遮瑕力确实可以，但下午会斑驳",
            "comment_id": "c2",
            "comment_like": 2,
            "note_id": "n1",
            "note_title": "油皮粉底液实测",
            "source_url": "https://www.xiaohongshu.com/explore/n1",
            "source_platform": "小红书",
        },
    ],
    "stats": {"notes": 1, "notes_ok": 1, "comments": 2, "with_ocr": 1},
    "warnings": [],
    "meta": {},
}


class FakeAgent:
    def __init__(self, results=None):
        self.results = results or [
            {
                "sentiment_analysis": {"real_sentiment": "negative"},
                "validity_analysis": {"validity_label": "真实有效"},
                "final_analysis": {"trust_score": 42, "final_sentiment": "negative"},
            },
            {
                "sentiment_analysis": {"real_sentiment": "neutral"},
                "validity_analysis": {"validity_label": "真实有效"},
                "final_analysis": {"trust_score": 66, "final_sentiment": "neutral"},
            },
        ]
        self.calls = []

    def batch_analyze(self, reviews, product_name=""):
        self.calls.append(("batch_analyze", len(reviews), product_name))
        return [dict(item) for item in self.results]

    def generate_report(self, results, product_name=""):
        self.calls.append(("generate_report", len(results), product_name))
        return {"total_reviews": len(results), "suspicious_review_count": 0, "authentic_positive_rate": 0.0}


def make_llm(quote="上脸两小时就开始闷痘", point_statement="上脸闷痘"):
    def llm(prompt):
        if "improvements" in prompt:
            return json.dumps(
                {
                    "improvements": [
                        {
                            "pain_point_id": "pp-1",
                            "action": "把配方里的致痘油脂换掉",
                            "rationale": "闷痘是油皮最直接的流失原因",
                            "effort": 2,
                            "impact": 3,
                            "verification": "30 天油皮实测，闷痘率下降一半",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "pain_points": [
                    {
                        "statement": point_statement,
                        "category": "使用体验",
                        "severity": 3,
                        "evidence": [{"review_id": "c1", "quote": quote}],
                    }
                ]
            },
            ensure_ascii=False,
        )

    return llm


def test_analyze_xhs_builds_five_chapter_report(tmp_path):
    html_path = tmp_path / "report.html"
    result = pipeline.analyze_xhs(
        CAPTURE,
        agent=FakeAgent(),
        llm_call=make_llm(),
        save_history=False,
        output_path=str(html_path),
    )

    assert result["review_count"] == 2
    assert result["note_count"] == 1
    pain = result["pain_report"]
    assert pain["verified_count"] == 1
    assert pain["pain_points"][0]["evidence"][0]["review_id"] == "c1"
    improvements = result["improvement_report"]["improvements"]
    assert improvements and improvements[0]["priority"] == "P0"
    topics = result["topic_report"]["topics"]
    assert topics and topics[0]["pain_point_id"] == "pp-1"
    assert len(topics[0]["titles"]) == 3

    kit = result["content_kit"]
    assert kit["status"] == "ready"
    assert len(kit["brief"]["selling_points"]) == 1
    assert kit["brief"]["detail_page"]["section_count"] == 8
    assert kit["material_index"]["total_images"] == 2

    html_text = html_path.read_text(encoding="utf-8")
    for anchor in ("#overview", "#sentiment", "#pains", "#improve", "#topics", "#content"):
        assert anchor in html_text
    assert "上脸闷痘" in html_text
    assert "把配方里的致痘油脂换掉" in html_text
    assert "油皮粉底液实测" in html_text
    assert "内容生产包" in html_text
    assert "详情页 8 段" in html_text
    assert "15 秒短视频分镜" in html_text
    assert "素材索引" in html_text
    assert result["json_path"]
    payload = open(result["json_path"], encoding="utf-8").read()
    assert "pain_report" in payload
    assert "content_kit" in payload
    assert "material_index" in payload


def test_analyze_xhs_escapes_malicious_note_content(tmp_path):
    capture = copy.deepcopy(CAPTURE)
    capture["notes"][0]["title"] = '\"><img src=x onerror=alert(1)>'
    capture["notes"][0]["images"] = [
        {"index": 0, "width": 1080, "height": 1440, "src": "javascript:alert(1)"}
    ]
    html_path = tmp_path / "escape.html"
    pipeline.analyze_xhs(
        capture,
        agent=FakeAgent(),
        llm_call=make_llm(),
        save_history=False,
        output_path=str(html_path),
    )
    html_text = html_path.read_text(encoding="utf-8")
    assert "<img src=x onerror" not in html_text
    assert 'href="javascript:' not in html_text
    assert "&lt;img src=x onerror=alert(1)&gt;" in html_text


def test_analyze_xhs_rejects_fabricated_quote(tmp_path):
    html_path = tmp_path / "report.html"
    result = pipeline.analyze_xhs(
        CAPTURE,
        agent=FakeAgent(),
        llm_call=make_llm(quote="这句话原文里根本没有"),
        save_history=False,
        output_path=str(html_path),
    )
    assert result["pain_report"]["verified_count"] == 0
    assert result["pain_report"]["rejected_evidence"] == 1
    html_text = html_path.read_text(encoding="utf-8")
    assert "未进入榜单的痛点" in html_text


def test_analyze_xhs_without_reviews(tmp_path):
    capture = dict(CAPTURE)
    capture["reviews"] = []
    html_path = tmp_path / "empty.html"
    result = pipeline.analyze_xhs(
        capture,
        agent=FakeAgent(),
        llm_call=None,
        save_history=False,
        output_path=str(html_path),
    )
    assert result["review_count"] == 0
    assert result["pain_report"]["verified_count"] == 0
    assert "没有可分析的评论文本" in result["pain_report"]["errors"][0]
    assert html_path.exists()
