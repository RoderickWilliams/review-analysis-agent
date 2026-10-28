"""Behavioral contracts for strict grouping, editable drafts and recoverable history."""
import copy
import threading

import pytest

from reviewagent import analysis_tasks as tasks, config, store
from reviewagent.import_reviews import parse_upload
from reviewagent.operations import build_operations
from reviewagent.product_groups import assign_groups, compare_identity
from reviewagent.review_data import normalize_reviews, summarize_results
from tests.fakes import FakeLLMClient, fake_result
from reviewagent.sentiment_agent_core import ReviewAnalysisAgent


def _identity(**changes):
    return {"brand": "Folkmanis", "model": "2644", "key_specs": {"尺寸": "10cm"}, "specs_confirmed": True, **changes}


def test_titles_or_spu_never_override_different_specs_or_missing_identity():
    primary = _identity(title="同一个标题", platform_id="same-spu")
    assert compare_identity(primary, _identity(key_specs={"尺寸": "20cm"}))["level"] == "variant"
    assert not compare_identity(primary, _identity(model="2576"))["merge_allowed"]
    assert not compare_identity(primary, _identity(key_specs={}))["merge_allowed"]
    assert not compare_identity(primary, _identity(specs_confirmed=False))["merge_allowed"]
    assert compare_identity(primary, _identity())["merge_allowed"]


def test_confirmed_same_specs_merge_but_unknown_selected_skus_stay_separate():
    first = _identity(url="https://item.jd.com/123.html", title="测试商品", reviews_scope="selected_spec")
    second = _identity(url="https://detail.tmall.com/item.htm?id=456", title="测试商品", reviews_scope="selected_spec")
    reviews = normalize_reviews([
        {"review_text": "尺寸适合手指，动作灵活", "platform": "jd", "source_url": first["url"], "comment_id": "a"},
        {"review_text": "指套偏紧，使用时需调整", "platform": "tmall", "source_url": second["url"], "comment_id": "b"},
    ])
    analysis = {"object": first, "candidates": [second], "reviews": reviews, "results": [], "request": {}}
    groups = assign_groups(analysis)
    assert len(groups) == 1 and groups[0]["status"] == "confirmed"
    first["reviews_scope"] = second["reviews_scope"] = "unknown"
    groups = assign_groups(analysis)
    assert len(groups) == 2
    assert all(group["status"] == "pending_identity" for group in groups)


def _operator_record():
    return {"enrichment": {"pain_points": {"items": [{"id": "g-pp-1", "group_id": "g", "group_title": "2644 · 10cm",
            "statement": "指套偏紧", "verified": True,
            "evidence": [{"review_id": "fixture-1", "quote": "指套偏紧", "source_url": "https://example.com/review"}]}]},
            "improvements": {"items": []}}}


def test_operator_drafts_have_evidence_and_preserve_human_edits_on_regeneration():
    record = _operator_record()
    record["enrichment"].update(build_operations(record))
    drafts = record["enrichment"]["drafts"]
    kinds = {d["kind"] for d in drafts}
    assert kinds == {"selling_point", "support_script", "content_topic"}
    assert "schedule" not in kinds
    assert all(d["evidence_ids"] == ["fixture-1"] and d["scheduled_date"] == "" for d in drafts)
    drafts[0].update(title="人工标题", body="已核对后的人工草稿", edited=True)
    record["enrichment"]["actions"][0].update(owner="运营", label="人工调整动作", edited=True)
    regenerated = build_operations(record)
    assert regenerated["drafts"][0]["body"] == "已核对后的人工草稿"
    assert regenerated["actions"][0]["owner"] == "运营"
    assert regenerated["actions"][0]["label"] == "人工调整动作"


def test_pending_and_cancelled_are_not_failed_or_neutral():
    stats = summarize_results([{"status": "pending"}, {"status": "cancelled"}, {"status": "failed"}])
    assert (stats["pending_count"], stats["cancelled_count"], stats["failed_count"]) == (1, 1, 1)
    assert stats["sentiment_distribution"] == {"positive": 0, "negative": 0, "neutral": 0}


def test_ignored_mapping_preserves_original_column_without_using_it():
    preview = parse_upload("reviews.csv", "review_text,rating,source_platform\n实际使用原文,9,jd\n".encode(), {"rating": "", "platform": ""})
    review = preview["reviews"][0]
    assert review["rating"] is None and review["platform"] == "manual"
    assert review["raw_fields"]["rating"] == "9"


@pytest.fixture()
def api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from reviewagent.http_api import app
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "isolated.sqlite")
    store.init_db()
    with TestClient(app) as client:
        yield client


def test_source_confirmation_invalidates_old_model_context_but_keeps_previous_result(api):
    analysis = tasks.create_record({"input": "Folkmanis", "reviews": [{"review_text": "指套偏紧"}], "save": True})
    previous = {**analysis["reviews"][0], **fake_result(analysis["reviews"][0]), "status": "succeeded"}
    analysis["results"] = [previous]
    store.save_analysis(analysis)
    response = api.patch(f"/v1/analysis/{analysis['analysis_id']}/source-identity", json={
        "brand": "Folkmanis", "model": "2644", "key_specs": {"尺寸": "10cm"},
        "specs_confirmed": True, "reviews_scope": "selected_spec", "title": "Mini Fox"})
    assert response.status_code == 200
    data = response.json()
    assert data["groups"][0]["status"] == "confirmed"
    assert data["results"][0]["status"] == "pending"
    assert data["results"][0]["previous_analysis"]["final_analysis"] == previous["final_analysis"]
    assert data["report"]["statistics"]["successful_count"] == 0


def test_clear_and_undo_restore_raw_results_and_drafts_and_block_stale_writes(api):
    analysis = tasks.create_record({"input": "隔离历史样本", "reviews": [{"review_text": "原始评论"}], "save": True})
    analysis["enrichment"] = {"actions": [{"id": "a", "owner": "运营"}], "drafts": [{"id": "d", "body": "人工稿", "edited": True}]}
    store.save_analysis(analysis)
    old = copy.deepcopy(analysis)
    cleared = api.delete("/v1/analysis").json()
    assert cleared["cleared"] == 1
    assert api.get(f"/v1/analysis/{analysis['analysis_id']}").status_code == 404
    with pytest.raises(ValueError):
        store.save_analysis(old)
    assert api.post("/v1/analysis/restore", json={"batch_id": cleared["batch_id"]}).json()["restored"] == 1
    restored = store.get_analysis(analysis["analysis_id"])
    assert restored["reviews"] == old["reviews"]
    assert restored["enrichment"] == old["enrichment"]


def test_settings_cannot_overwrite_a_job_started_during_link_resolution(api, monkeypatch):
    analysis = tasks.create_record({"input": "隔离竞态样本", "reviews": [], "save": True})
    entered, release = threading.Event(), threading.Event()
    def resolve(link):
        entered.set()
        assert release.wait(3)
        return {"url": link, "title": "测试候选", "platform": "jd"}
    monkeypatch.setattr("reviewagent.object_resolver.resolve_object", resolve)
    monkeypatch.setattr(tasks, "_pool", type("HoldingPool", (), {"submit": lambda *args: None})())
    responses = []
    thread = threading.Thread(target=lambda: responses.append(api.patch(f"/v1/analysis/{analysis['analysis_id']}", json={"extra_links": ["https://item.jd.com/123.html"]})))
    thread.start()
    try:
        assert entered.wait(3)
        tasks.start(analysis["analysis_id"], "operations")
        release.set()
        thread.join(3)
        assert not thread.is_alive()
        assert responses[0].status_code == 409
        assert store.get_analysis(analysis["analysis_id"])["status"] == "queued"
    finally:
        release.set()
        thread.join(3)
        with tasks._lock:
            tasks._active.pop(analysis["analysis_id"], None)


def test_long_csv_field_is_a_client_error(api):
    content = ("review_text\n" + "原" * 140000).encode()
    response = api.post("/v1/import/preview", files={"file": ("long.csv", content, "text/csv")})
    assert response.status_code == 400


def test_draft_edits_and_formula_safe_export_keep_evidence(api):
    analysis = tasks.create_record({"input": "隔离草稿样本", "reviews": [{"review_text": "指套偏紧", "review_id": "fixture-1"}], "save": True})
    analysis["enrichment"] = _operator_record()["enrichment"]
    analysis["enrichment"].update(build_operations(analysis))
    store.save_analysis(analysis)
    draft = analysis["enrichment"]["drafts"][0]
    response = api.patch(f"/v1/analysis/{analysis['analysis_id']}/drafts/{draft['id']}", json={"title": "=SUM(1,2)", "body": "人工编辑", "channel": "详情页", "scheduled_date": "2026-11-01"})
    assert response.status_code == 200
    saved = response.json()["report"]["drafts"][0]
    assert saved["body"] == "人工编辑" and saved["evidence_ids"] == ["fixture-1"]
    exported = api.get(f"/v1/analysis/{analysis['analysis_id']}/drafts.csv")
    assert "'=SUM(1,2)" in exported.text
    assert "fixture-1" in exported.text


def test_selective_generation_keeps_other_drafts_and_does_not_create_actions():
    record = _operator_record()
    first = build_operations(record, "selling_point")
    assert set(first) == {"drafts"}
    assert {item["kind"] for item in first["drafts"]} == {"selling_point"}
    first["drafts"][0].update(body="人工编辑保留", edited=True)
    record["enrichment"].update(first)
    second = build_operations(record, "support_script")
    assert set(second) == {"drafts"}
    assert {item["kind"] for item in second["drafts"]} == {"selling_point", "support_script"}
    assert next(item for item in second["drafts"] if item["kind"] == "selling_point")["body"] == "人工编辑保留"
    actions = build_operations(record, "actions")
    assert set(actions) == {"actions", "ops_plan"}
    assert record["enrichment"]["drafts"] == first["drafts"]


def test_selective_generation_requires_verified_evidence():
    with pytest.raises(ValueError):
        build_operations({"enrichment": {}}, "content_topic")


def test_model_generation_is_scoped_to_requested_kind_and_keeps_evidence():
    import json
    record = _operator_record()
    class Agent:
        model = "fixture-model"
        def _call_llm(self, prompt):
            item = build_operations(record, "support_script")["drafts"][0]
            return json.dumps({"items": [{"id": item["id"], "title": "核对指套尺寸",
                "body": "请提供手指尺寸，以便核对适用规格。", "channel": "客服"}]})
    from reviewagent.operations import generate_operations
    data = generate_operations(record, "support_script", Agent())
    assert set(data) == {"drafts"}
    assert data["drafts"][0]["evidence_ids"] == ["fixture-1"]
    assert data["drafts"][0]["generation_method"] == "model"
    assert data["drafts"][0]["body"] == "请提供手指尺寸，以便核对适用规格。"
