# -*- coding: utf-8 -*-
"""SQLite 存储层：历史记录、运行记录与评测结果。

原先的 `data/history.json` 全量读写改为单库多表；旧 JSON 会在首次连接时自动迁移，
迁移完成后原文件改名为 `history.json.migrated`，不重复导入。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from reviewagent import config

_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    source        TEXT,
    platform      TEXT,
    product_name  TEXT,
    product_url   TEXT,
    review_count  INTEGER DEFAULT 0,
    avg_trust_score REAL,
    html_report_path TEXT,
    payload       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_platform ON history(platform);

CREATE TABLE IF NOT EXISTS analyses (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    status        TEXT NOT NULL,
    input_text    TEXT,
    platform      TEXT,
    title         TEXT,
    report        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    meta        TEXT
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    dataset     TEXT,
    metrics     TEXT,
    report_path TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def db_path() -> Path:
    config.ensure_dirs()
    return Path(config.DB_PATH)


@contextmanager
def connect():
    conn = sqlite3.connect(str(db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _LOCK, connect() as conn:
        conn.executescript(SCHEMA)


def _migrate_legacy_json(conn: sqlite3.Connection) -> None:
    import os
    if os.environ.get("REVIEWAGENT_MIGRATE_LEGACY_HISTORY", "0") != "1":
        return
    legacy = Path(config.DATA_DIR) / "history.json"
    if not legacy.is_file():
        return
    try:
        records = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(records, list):
        return
    for rec in records:
        if isinstance(rec, dict) and rec.get("id"):
            _put(conn, rec, replace=False)
    try:
        legacy.rename(legacy.with_suffix(".json.migrated"))
    except OSError:
        pass


def _put(conn: sqlite3.Connection, record: Dict[str, Any], replace: bool = True) -> None:
    sql = (
        "INSERT OR REPLACE INTO history (id, created_at, source, platform, product_name, product_url,"
        " review_count, avg_trust_score, html_report_path, payload) VALUES (?,?,?,?,?,?,?,?,?,?)"
        if replace
        else
        "INSERT OR IGNORE INTO history (id, created_at, source, platform, product_name, product_url,"
        " review_count, avg_trust_score, html_report_path, payload) VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    conn.execute(
        sql,
        (
            record["id"],
            record.get("timestamp") or datetime.now().isoformat(),
            record.get("source"),
            record.get("platform"),
            record.get("product_name"),
            record.get("url"),
            int(record.get("review_count") or 0),
            record.get("avg_trust_score"),
            record.get("html_report_path"),
            json.dumps(record, ensure_ascii=False),
        ),
    )


def save_history_record(record: Dict[str, Any]) -> str:
    init_db()
    with _LOCK, connect() as conn:
        _migrate_legacy_json(conn)
        _put(conn, record)
    return record["id"]


def list_history(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    init_db()
    with _LOCK, connect() as conn:
        _migrate_legacy_json(conn)
        sql = "SELECT payload FROM history ORDER BY created_at DESC, id DESC"
        rows = conn.execute(sql + " LIMIT ?", (max(0, limit),)).fetchall() if limit is not None else conn.execute(sql).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            out.append(json.loads(row["payload"]))
        except ValueError:
            continue
    return out


def get_history(record_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT payload FROM history WHERE id=?", (record_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def delete_history(record_id: str) -> bool:
    init_db()
    with _LOCK, connect() as conn:
        cur = conn.execute("DELETE FROM history WHERE id=?", (record_id,))
        return cur.rowcount > 0


def clear_history() -> int:
    init_db()
    with _LOCK, connect() as conn:
        cur = conn.execute("DELETE FROM history")
        return cur.rowcount


def count_history() -> int:
    init_db()
    with _LOCK, connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM history").fetchone()[0])


# ── v2 对象分析任务 ──────────────────────────────────────────

def save_analysis(analysis: Dict[str, Any]) -> str:
    """保存或更新一条对象分析。report 列存完整 JSON。"""
    init_db()
    analysis_id = str(analysis["analysis_id"])
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    created_at = str(analysis.get("created_at") or now)
    updated_at = now
    analysis["created_at"] = created_at
    analysis["updated_at"] = updated_at
    obj = analysis.get("object") or {}
    report = analysis.get("report") or {}
    with _LOCK, connect() as conn:
        existing = conn.execute("SELECT status FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if existing is not None and existing["status"] == "trashed":
            raise ValueError("记录已清除，请先撤销清除")
        conn.execute(
            """
            INSERT INTO analyses (id, created_at, updated_at, status, input_text, platform, title, report)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at=excluded.updated_at,
                status=excluded.status,
                input_text=excluded.input_text,
                platform=excluded.platform,
                title=excluded.title,
                report=excluded.report
            """,
            (
                analysis_id,
                created_at,
                updated_at,
                str(analysis.get("status") or "ready"),
                str(analysis.get("input") or ""),
                str(obj.get("platform") or ""),
                str(obj.get("title") or ""),
                json.dumps(analysis, ensure_ascii=False),
            ),
        )
    return analysis_id


def get_analysis(analysis_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT report FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    if not row:
        return None
    try:
        item = json.loads(row["report"])
        return None if item.get("status") == "trashed" else item
    except ValueError:
        return None


def list_analyses(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    init_db()
    with _LOCK, connect() as conn:
        if limit is None:
            rows = conn.execute("SELECT report FROM analyses WHERE status != 'trashed' ORDER BY created_at DESC, id DESC").fetchall()
        else:
            rows = conn.execute("SELECT report FROM analyses ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            out.append(json.loads(row["report"]))
        except ValueError:
            continue
    return out


def update_analysis(analysis_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    """Merge progress atomically without overwriting concurrent cancellation state."""
    init_db()
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT report FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if row is None:
            raise ValueError("分析任务不存在")
        analysis = json.loads(row["report"])
        if analysis.get("status") == "trashed":
            raise ValueError("记录已清除")
        analysis.update(changes)
        analysis["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        conn.execute("UPDATE analyses SET report=?,status=?,updated_at=? WHERE id=?",
                     (json.dumps(analysis, ensure_ascii=False), analysis.get("status", "draft"), analysis["updated_at"], analysis_id))
    return analysis


def delete_analysis(analysis_id: str) -> bool:
    init_db()
    with _LOCK, connect() as conn:
        cur = conn.execute("DELETE FROM analyses WHERE id=?", (analysis_id,))
        return cur.rowcount > 0


def clear_analyses() -> int:
    init_db()
    with _LOCK, connect() as conn:
        cur = conn.execute("DELETE FROM analyses")
        return cur.rowcount


def trash_analyses(batch_id: str) -> int:
    """Hide saved analyses atomically; retain original records for explicit undo."""
    init_db()
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with _LOCK, connect() as conn:
        rows = conn.execute("SELECT id,status,report FROM analyses WHERE status != 'trashed'").fetchall()
        if any(row["status"] in {"queued", "running", "cancel_requested"} for row in rows):
            raise ValueError("存在运行中或待恢复的任务，请先结束任务并刷新记录")
        for row in rows:
            item = json.loads(row["report"])
            item["trash"] = {"batch_id": batch_id, "previous_status": item.get("status", "draft"), "cleared_at": stamp}
            item["status"] = "trashed"
            conn.execute("UPDATE analyses SET status='trashed', updated_at=?, report=? WHERE id=?", (stamp, json.dumps(item, ensure_ascii=False), row["id"]))
        return len(rows)


def restore_analyses(batch_id: str) -> int:
    init_db()
    restored = 0
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with _LOCK, connect() as conn:
        for row in conn.execute("SELECT id,report FROM analyses WHERE status='trashed'").fetchall():
            item = json.loads(row["report"])
            trash = item.get("trash") or {}
            if trash.get("batch_id") != batch_id:
                continue
            item["status"] = trash.get("previous_status", "draft")
            item["updated_at"] = stamp
            item.pop("trash", None)
            conn.execute("UPDATE analyses SET status=?,updated_at=?,report=? WHERE id=?", (item["status"], stamp, json.dumps(item, ensure_ascii=False), row["id"]))
            restored += 1
    return restored


def record_run(kind: str, status: str = "running", meta: Optional[Dict[str, Any]] = None) -> int:
    init_db()
    with _LOCK, connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (kind, status, started_at, meta) VALUES (?,?,?,?)",
            (kind, status, datetime.now().isoformat(), json.dumps(meta or {}, ensure_ascii=False)),
        )
        return int(cur.lastrowid)


def finish_run(run_id: int, status: str = "done", meta: Optional[Dict[str, Any]] = None) -> None:
    init_db()
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE runs SET status=?, finished_at=?, meta=? WHERE id=?",
            (status, datetime.now().isoformat(), json.dumps(meta or {}, ensure_ascii=False), run_id),
        )


def list_runs(limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    with _LOCK, connect() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def save_eval_result(dataset: str, metrics: Dict[str, Any], report_path: Optional[str] = None) -> int:
    init_db()
    with _LOCK, connect() as conn:
        cur = conn.execute(
            "INSERT INTO eval_runs (created_at, dataset, metrics, report_path) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), dataset, json.dumps(metrics, ensure_ascii=False), report_path),
        )
        return int(cur.lastrowid)
