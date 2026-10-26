# -*- coding: utf-8 -*-
"""store：历史记录 CRUD 与顺序。"""
from __future__ import annotations

from reviewagent import store


def _rec(rid: str, ts: str, name: str = "测试品") -> dict:
    return {"id": rid, "timestamp": ts, "product_name": name, "review_count": 3}


def test_save_and_get():
    store.save_history_record(_rec("a1", "2026-10-01T10:00:00"))
    got = store.get_history("a1")
    assert got["product_name"] == "测试品"


def test_list_is_newest_first():
    store.save_history_record(_rec("old", "2026-10-01T10:00:00"))
    store.save_history_record(_rec("new", "2026-10-02T10:00:00"))
    ids = [r["id"] for r in store.list_history()]
    assert ids.index("new") < ids.index("old")


def test_list_limit():
    for i in range(3):
        store.save_history_record(_rec(f"r{i}", f"2026-10-0{i + 1}T10:00:00"))
    assert len(store.list_history(limit=2)) == 2


def test_delete_and_count():
    store.save_history_record(_rec("d1", "2026-10-01T10:00:00"))
    assert store.count_history() == 1
    assert store.delete_history("d1") is True
    assert store.delete_history("d1") is False
    assert store.count_history() == 0


def test_clear_history():
    store.save_history_record(_rec("c1", "2026-10-01T10:00:00"))
    store.save_history_record(_rec("c2", "2026-10-02T10:00:00"))
    assert store.clear_history() == 2
    assert store.list_history() == []


def test_record_run_lifecycle():
    run_id = store.record_run("analyze", meta={"url": "https://example.com"})
    store.finish_run(run_id, status="done")
    runs = store.list_runs()
    assert runs[0]["status"] == "done"
