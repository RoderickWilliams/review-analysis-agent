"""Regression contracts for data integrity, recoverable tasks, imports and exports.

All model responses are explicit test doubles. These tests do not measure model quality.
"""
import copy
import json
import threading
from types import SimpleNamespace

import pytest

from reviewagent import analysis_tasks as tasks, store
from reviewagent.import_reviews import parse_upload
from reviewagent.review_data import normalize_reviews, summarize_results
from reviewagent.sentiment_agent_core import ReviewAnalysisAgent
from tests.fakes import FakeLLMClient, FINAL_RESULT, fake_result, response_for_prompt


class InlinePool:
    def submit(self, function, *args):
        function(*args)


def record(reviews=None):
    return tasks.create_record({"input": "离线测试数据集", "reviews": reviews or [], "save": True})


def test_missing_values_stay_unknown_and_native_ids_are_namespaced():
    items = normalize_reviews([
        {"review_text": "好", "comment_id": "same", "platform": "jd"},
        {"review_text": "好", "comment_id": "same", "platform": "taobao"},
    ])
    assert items[0]["review_id"] != items[1]["review_id"]
    assert items[0]["rating"] is None
    assert items[0]["review_date"] == ""
    with pytest.raises(ValueError, match="缺少正文"):
        normalize_reviews([{}])
    with pytest.raises(ValueError, match="评分"):
        normalize_reviews([{"review_text": "好", "rating": 6}])


def test_failed_and_unknown_rows_do_not_inflate_statistics():
    successful = fake_result({"review_text": "质量不行", "rating": 1})
    successful["final_analysis"]["final_sentiment"] = "negative"
    successful["sentiment_analysis"]["is_sarcastic"] = True
    unknown = copy.deepcopy(successful)
    unknown["final_analysis"].update(final_validity="unknown", trust_score=None)
    stats = summarize_results([successful, unknown, {"status": "failed", "final_analysis": {}}])
    assert stats["successful_count"] == 2
    assert stats["failed_count"] == 1
    assert stats["sentiment_distribution"] == {"positive": 0, "negative": 2, "neutral": 0}
    assert stats["sarcastic_count"] == 2
    assert stats["avg_trust_score"] == 88


def test_schema_failure_is_preserved_as_failure_without_neutral_fallback():
    agent = ReviewAnalysisAgent(client=FakeLLMClient(error=RuntimeError("timeout")))
    result = agent.batch_analyze([{"review_text": "实际评论"}])[0]
    assert result["status"] == "failed"
    assert result["final_analysis"] == {}
    assert result["error"]["code"] == "network"
    assert summarize_results([result])["avg_trust_score"] is None


def test_cancel_stops_future_rows_and_preserves_completed_results(monkeypatch):
    monkeypatch.setenv("REVIEWAGENT_ANALYSIS_WORKERS", "1")
    event = threading.Event()
    client = FakeLLMClient()
    agent = ReviewAnalysisAgent(client=client)
    results = agent.batch_analyze(
        [{"review_text": "第一条"}, {"review_text": "第二条"}],
        should_cancel=event.is_set,
        on_result=lambda *args: event.set(),
    )
    assert results[0]["status"] == "succeeded"
    assert results[1]["status"] == "pending"
    assert len(client.calls) == 3


def test_one_character_reviews_have_similarity_counts(agent):
    assert agent.similar_counts(["好", "好", "差"]) == [1, 1, 0]


def test_import_mapping_keeps_raw_text_and_reports_invalid_rows():
    payload = "正文列,星级列,日期列\n用了两周续航不错,5,\n,4,2026-10-01\n".encode()
    preview = parse_upload("reviews.csv", payload, {"review_text": "正文列", "rating": "星级列", "review_date": "日期列"})
    assert len(preview["reviews"]) == 1
    assert preview["reviews"][0]["review_date"] == ""
    assert preview["errors"][0]["row"] == 3
    assert parse_upload("unknown.csv", "未知列\n一条原文\n".encode())["needs_mapping"]


def test_task_persists_originals_resumes_successes_and_invalidates_edited_row(monkeypatch):
    monkeypatch.setattr(tasks, "_pool", InlinePool())
    monkeypatch.setattr(tasks, "_insights", lambda *args: {})
    analysis = record([{"review_text": "用了两周，续航很强", "review_id": "resume-r1"}])
    original = copy.deepcopy(analysis["reviews"])
    client = FakeLLMClient()
    agent = ReviewAnalysisAgent(client=client)
    completed = tasks.start(analysis["analysis_id"], agent=agent)
    assert completed["status"] == "completed"
    assert completed["reviews"] == original
    assert completed["results"][0]["review_id"] == "resume-r1"
    assert len(client.calls) == 3
    tasks.start(analysis["analysis_id"], agent=agent)
    assert len(client.calls) == 3
    edited = [{**original[0], "review_text": "修改后的实际原文"}]
    updated = tasks.attach_reviews(analysis["analysis_id"], edited)
    assert updated["results"] == []
    assert not updated.get("enrichment")


def test_restart_marks_task_interrupted_without_restarting_model():
    analysis = record([{"review_text": "一条原文"}])
    store.update_analysis(analysis["analysis_id"], {"status": "running"})
    restored = tasks.get_record(analysis["analysis_id"])
    assert restored["status"] == "interrupted"
    assert restored["reviews"][0]["review_text"] == "一条原文"


def test_deep_insights_keep_verifiable_quotes(monkeypatch):
    monkeypatch.setattr(tasks, "_pool", InlinePool())
    analysis = record([{"review_text": "用了两周，杯盖接缝一直漏水", "review_id": "leak-1"}])
    class InsightAgent(ReviewAnalysisAgent):
        def _call_llm(self, prompt, temperature=0.0):
            if "## 情绪分类体系" in prompt or "## 有效性分类体系" in prompt or "## 交叉验证规则" in prompt:
                return json.dumps(response_for_prompt(prompt), ensure_ascii=False)
            if '"improvements"' in prompt:
                return json.dumps({"improvements": [{"pain_point_id": "pp-1", "action": "调整杯盖密封接缝", "rationale": "对应漏水原文", "effort": 2, "impact": 3, "verification": "记录复测漏水次数"}]}, ensure_ascii=False)
            return json.dumps({"pain_points": [{"statement": "杯盖接缝漏水", "category": "质量", "severity": 3, "evidence": [{"review_id": "leak-1", "quote": "杯盖接缝一直漏水"}]}]}, ensure_ascii=False)
    agent = InsightAgent(client=FakeLLMClient())
    completed = tasks.start(analysis["analysis_id"], agent=agent)
    assert completed["status"] == "completed"
    assert completed["report"]["pain_points"]["items"][0]["verified"]
    planned = tasks.start(analysis["analysis_id"], "operations")
    assert planned["report"]["actions"][0]["evidence_ids"] == ["leak-1"]


def test_html_export_escapes_originals_and_includes_unfinished_rows(tmp_path):
    from reviewagent.report_generator import HTMLReportGenerator
    gen = HTMLReportGenerator()
    output = tmp_path / "report.html"
    gen.generate([{"review_text": '<img src=x onerror="alert(1)">', "status": "failed", "final_analysis": {}}], {}, str(output), product_name="<script>bad</script>")
    html = output.read_text(encoding="utf-8")
    assert "<script>bad" not in html
    assert "<img src=x" not in html
    assert "&lt;img" in html
    assert "分析未完成" in html


def test_key_failover_is_per_request_and_bounded(monkeypatch):
    pytest.importorskip("openai")
    from reviewagent.llm import RotatingClient
    calls = []
    def fake_openai(api_key, **kwargs):
        def create(**request):
            calls.append(api_key)
            if api_key == "test-channel-a":
                error = RuntimeError("limited")
                error.status_code = 429
                raise error
            return "response"
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr("openai.OpenAI", fake_openai)
    client = RotatingClient(["test-channel-a", "test-channel-b"], None, 1, 0)
    assert client.chat.completions.create(model="test", messages=[]) == "response"
    assert calls == ["test-channel-a", "test-channel-b"]


def test_api_preserves_payload_and_exports_formula_safe_csv(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from reviewagent.http_api import app
    with TestClient(app) as client:
        created = client.post("/v1/analysis", json={"input": "离线数据", "reviews": [{"review_text": "=SUM(1,2)"}]}).json()
        aid = created["analysis_id"]
        saved = client.patch(f"/v1/analysis/{aid}", json={"ownership": "competitor", "window_months": 6})
        assert saved.status_code == 200
        assert saved.json()["reviews"] == created["reviews"]
        csv = client.get(f"/v1/analysis/{aid}/reviews.csv")
        assert "'=SUM(1,2)" in csv.text
        assert client.post("/v1/analysis", json={"input": "无效样本", "reviews": [{}]}).status_code == 422
        monkeypatch.setenv("REVIEWAGENT_ACCESS_TOKEN", "test-access-only")
        assert client.get("/v1/analysis").status_code == 401
        assert client.get("/v1/analysis", headers={"Authorization": "Bearer test-access-only"}).status_code == 200
