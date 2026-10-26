# -*- coding: utf-8 -*-
"""宣传文案的风险词扫描。

词表只覆盖广告法里的绝对化用语与常见夸大承诺，用于发布前提醒，
不替代平台审核；命中不代表违规，需要人工看上下文。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_WORDS = [
    "最有效", "最好", "最佳", "最强", "最低价", "全网最低", "第一品牌", "国家级",
    "绝对安全", "绝对有效", "100%有效", "百分百有效", "零风险", "无副作用",
    "根治", "永久", "一劳永逸", "万能", "包治", "立竿见影", "立刻见效",
    "史无前例", "顶级", "极致", "唯一", "独家配方", "祖传秘方", "纯天然无添加",
    "假一赔十", "无效退款", "稳赚不赔", "秒杀全网", "闭眼入", "绝绝子",
]


def load_words(path: Optional[str] = None) -> List[str]:
    """读取自定义词表；未配置或读取失败时用内置表。"""
    target = path or os.environ.get("REVIEWAGENT_RISK_WORDS", "")
    if target and os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                words = [str(item).strip() for item in data if str(item).strip()]
                if words:
                    return words
            if isinstance(data, dict) and isinstance(data.get("words"), list):
                return [str(item).strip() for item in data["words"] if str(item).strip()]
        except Exception:
            pass
    return list(DEFAULT_WORDS)


def scan_risk_words(text: str, words: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """返回命中的风险词与位置；同一词只报第一次。"""
    content = str(text or "")
    table = list(words) if words is not None else load_words()
    hits: List[Dict[str, Any]] = []
    seen = set()
    for word in table:
        word = str(word).strip()
        if not word or word in seen:
            continue
        index = content.find(word)
        if index >= 0:
            seen.add(word)
            hits.append({"word": word, "index": index})
    hits.sort(key=lambda item: item["index"])
    level = "高" if len(hits) >= 3 else ("中" if hits else "低")
    return {"hits": hits, "words": [item["word"] for item in hits], "level": level}
