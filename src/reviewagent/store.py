# -*- coding: utf-8 -*-
"""SQLite 存储层：历史记录、运行记录与评测结果。

原先的 `data/history.json` 全量读写改为单库多表；旧 JSON 会在首次连接时自动迁移，
迁移完成后原文件改名为 `history.json.migrated`，不重复导入。
"""
from __future__ import annotations

import json
import sqlite3
import threading
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


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with _LOCK, connect() as conn:
        conn.executescript(SCHEMA)


def _migrate_legacy_json(conn: sqlite3.Connection) -> None:
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
        rows = conn.execute(sql).fetchall()
    if limit is not None:
        rows = rows[:limit]
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
