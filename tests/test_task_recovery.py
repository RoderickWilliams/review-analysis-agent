"""服务重启后的僵尸任务恢复：只改状态，保护活动任务，不改数据。"""
from reviewagent import analysis_tasks as tasks, store


def make_record(status, reviews=None):
    analysis = tasks.create_record({"input": "离线恢复测试", "reviews": reviews or [], "save": True})
    store.update_analysis(analysis["analysis_id"], {"status": status, "status_label": status})
    return analysis["analysis_id"]


def test_stale_tasks_become_interrupted_and_keep_reviews():
    analysis_id = make_record("running", [{"review_text": "一条真实原文"}])
    assert tasks.recover_interrupted() == [analysis_id]
    record = store.get_analysis(analysis_id)
    assert record["status"] == "interrupted"
    assert record["status_label"] == "任务已中断，可继续"
    assert record["reviews"][0]["review_text"] == "一条真实原文"


def test_active_task_is_not_touched(monkeypatch):
    analysis_id = make_record("running")
    monkeypatch.setitem(tasks._active, analysis_id, object())
    assert tasks.recover_interrupted() == []
    assert store.get_analysis(analysis_id)["status"] == "running"


def test_recovery_then_history_reset_works():
    make_record("cancel_requested")
    tasks.recover_interrupted()
    result = tasks.clear_saved_records()
    assert result["cleared"] >= 1
    assert store.list_analyses() == []
