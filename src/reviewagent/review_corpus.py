"""本地语料库：正负样本对照，学习"模板化/刷评"与"真实用户表达"的差别。

只保存评论正文与判定，不保存作者身份；按正文去重，追加写入。
标签：suspicious（疑似模板/刷评）、fake（明确刷评）、authentic（真人评论，不应误判）。
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path

from reviewagent import config

_LOCK = threading.Lock()
LABELS = {"suspicious", "fake", "authentic"}


def corpus_path() -> Path:
    return Path(config.DATA_DIR) / "template_review_corpus.jsonl"


def _key(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()[:24]


def _read_rows() -> list[dict]:
    path = corpus_path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("key"):
            row["label"] = row.get("label") or row.get("verdict") or "suspicious"
            rows.append(row)
    return rows


def _append(rows: list[dict]) -> int:
    if not rows:
        return 0
    path = corpus_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    with _LOCK:
        keys = {row.get("key") for row in _read_rows()}
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                text = (row.get("text") or "").strip()
                if not text:
                    continue
                key = _key(text)
                if key in keys:
                    continue
                keys.add(key)
                added += 1
                handle.write(json.dumps({
                    "key": key,
                    "text": text[:500],
                    "rating": row.get("rating"),
                    "date": row.get("date") or "",
                    "platform": row.get("platform") or "",
                    "label": row.get("label") or "suspicious",
                    "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }, ensure_ascii=False) + "\n")
    return added


def append_flagged(reviews, results) -> int:
    """把模型判为 suspicious / fake 的评论写入语库（负样本）。"""
    verdicts = {}
    for item in results or []:
        final = item.get("final_analysis") or {}
        if final.get("final_validity") in {"suspicious", "fake"}:
            verdicts[item.get("review_id")] = final.get("final_validity")
    rows = []
    for review in reviews or []:
        if review.get("review_id") in verdicts:
            rows.append({"text": review.get("review_text"), "rating": review.get("rating"),
                         "date": review.get("review_date"), "platform": review.get("platform"),
                         "label": verdicts[review.get("review_id")]})
    return _append(rows)


def add_examples(rows: list[dict], label: str) -> int:
    """人工补充样本；label 取 suspicious / fake / authentic。"""
    if label not in LABELS:
        raise ValueError("未知标签：%s" % label)
    prepared = [{**row, "label": label} for row in rows]
    return _append(prepared)


def load_examples(limit: int = 6, label: str | None = None) -> list[dict]:
    rows = _read_rows()
    seen, out = set(), []
    for row in reversed(rows):
        if label and row.get("label") != label:
            continue
        text = (row.get("text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(row)
        if len(out) >= limit:
            break
    return list(reversed(out))


def format_examples(negative: int = 4, positive: int = 3) -> str:
    """给有效性提示词用的对照样本：哪些像模板/刷评，哪些是真人表达。"""
    bad = load_examples(negative, label="suspicious") + load_examples(negative, label="fake")
    good = load_examples(positive, label="authentic")
    sections = []
    if bad:
        lines = ["## 疑似模板/刷评样本（只作语言对照，不代表本条结论）"]
        for index, row in enumerate(bad[:negative], 1):
            lines.append("%d. 「%s」" % (index, (row.get("text") or "")[:120]))
        sections.append("\n".join(lines))
    if good:
        lines = ["## 真实用户样本（有具体体验或用个人语气，不要因为重复用词就判模板）"]
        for index, row in enumerate(good[:positive], 1):
            lines.append("%d. 「%s」" % (index, (row.get("text") or "")[:120]))
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
