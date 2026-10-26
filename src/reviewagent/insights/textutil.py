# -*- coding: utf-8 -*-
"""洞察引擎共用的小工具：文本归一化、中文分词、相似度、JSON 解析。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Set

_WS_RE = re.compile(r"\s+")
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\ufeff]")
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)

_STOPWORDS = {
    "这个", "那个", "就是", "感觉", "真的", "有点", "还是", "然后", "因为", "所以",
    "但是", "而且", "已经", "可以", "没有", "什么", "怎么", "比较", "非常", "一下",
    "用着", "用了", "买的", "东西", "产品", "用户", "评论", "自己", "觉得", "时候",
}


def normalize_text(value: Any) -> str:
    """压缩空白、去零宽字符；None 返回空串。用于“引语是否真的出现在原文里”。"""
    if value is None:
        return ""
    text = _ZERO_WIDTH_RE.sub("", str(value))
    return _WS_RE.sub(" ", text).strip()


def compact_text(value: Any) -> str:
    """去掉全部空白与标点，仅保留字词，用于宽松包含判断。"""
    return _PUNCT_RE.sub("", normalize_text(value)).lower()


def quote_in_text(quote: str, text: str, min_chars: int = 4) -> bool:
    """引语必须能在原文中找到（先严格归一化，再宽松到忽略标点）。"""
    quote = normalize_text(quote)
    text = normalize_text(text)
    if len(compact_text(quote)) < min_chars:
        return False
    if quote in text:
        return True
    return compact_text(quote) in compact_text(text)


def token_set(value: Any) -> Set[str]:
    """中文分词后的词集合；jieba 不可用时退回二元字组。"""
    text = normalize_text(value)
    if not text:
        return set()
    try:
        import jieba  # type: ignore

        words = [w.strip() for w in jieba.lcut(text)]
    except Exception:
        words = [text[i:i + 2] for i in range(max(len(text) - 1, 1))]
    tokens = {w for w in words if len(w) >= 2 and w not in _STOPWORDS and not w.isdigit()}
    if not tokens:
        tokens = {text[i:i + 2] for i in range(max(len(text) - 1, 1))}
    return tokens


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def truncate(value: Any, limit: int = 60) -> str:
    text = normalize_text(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_json_any(text: str) -> Optional[Any]:
    """解析 LLM 输出里的 JSON 对象或数组；失败返回 None。"""
    if not text or not isinstance(text, str):
        return None
    cleaned = _FENCE_RE.sub("", text).strip()
    for candidate in (cleaned,):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
    starts = [idx for idx in (cleaned.find("["), cleaned.find("{")) if idx >= 0]
    if not starts:
        return None
    start = min(starts)
    end = max(cleaned.rfind("]"), cleaned.rfind("}"))
    if end <= start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def as_list(value: Any, key: str = "") -> List[Dict[str, Any]]:
    """从解析结果里取对象数组，兼容 {"items": [...]} 包装。"""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if key and isinstance(value.get(key), list):
            return [item for item in value[key] if isinstance(item, dict)]
        for candidate in value.values():
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
    return []
