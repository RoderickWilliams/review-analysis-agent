"""本地语料库：积累已标记的模板化/疑似刷评评论，作为有效性分析的参考样本。

只保存评论语言特征，不保存作者身份信息；按正文去重，追加写入。
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path

from reviewagent import config

_LOCK = threading.Lock()


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
            rows.append(row)
    return rows


def append_flagged(reviews, results) -> int:
    """把模型判为 suspicious / fake 的评论写入语库；返回新增条数。"""
    verdicts = {}
    for item in results or []:
        final = item.get("final_analysis") or {}
        if final.get("final_validity") in {"suspicious", "fake"}:
            verdicts[item.get("review_id")] = final.get("final_validity")
    if not verdicts:
        return 0
    path = corpus_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    with _LOCK:
        keys = {row.get("key") for row in _read_rows()}
        with path.open("a", encoding="utf-8") as handle:
            for review in reviews or []:
                if review.get("review_id") not in verdicts:
                    continue
                text = (review.get("review_text") or "").strip()
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
                    "rating": review.get("rating"),
                    "date": review.get("review_date") or "",
                    "platform": review.get("platform") or "",
                    "verdict": verdicts[review.get("review_id")],
                    "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }, ensure_ascii=False) + "\n")
    return added


def load_examples(limit: int = 6) -> list[dict]:
    rows = _read_rows()
    seen, out = set(), []
    for row in reversed(rows):
        text = (row.get("text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(row)
        if len(out) >= limit:
            break
    return list(reversed(out))


def format_examples(limit: int = 6) -> str:
    rows = load_examples(limit)
    if not rows:
        return ""
    lines = ["## 参考样本（历史标记的模板化或疑似刷评评论，只用于对照语言特征，不代表本条评论的结论）"]
    for index, row in enumerate(rows, 1):
        lines.append("%d. 「%s」 → %s" % (index, (row.get("text") or "")[:120], row.get("verdict") or "suspicious"))
    return "\n".join(lines)
