# -*- coding: utf-8 -*-
"""用户痛点提取、证据校验、聚类与排序。

原则：
- 痛点必须带原文引语，引语要在评论正文（或笔记 OCR 文本）里逐字找到，
  找不到的引语记为 rejected，不进入榜单。
- 没有一条证据通过的痛点标 verified=False，排在榜单末尾且不参与选题。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence

from reviewagent.insights.textutil import (
    as_list,
    clamp_int,
    compact_text,
    jaccard,
    normalize_text,
    parse_json_any,
    quote_in_text,
    token_set,
    truncate,
)

CATEGORIES = ["使用体验", "质量", "效果", "价格", "服务", "物流", "包装", "人群不适配", "信息不符", "其他"]
SEVERITY_LABEL = {1: "轻微", 2: "明显", 3: "严重"}

PAIN_PROMPT_HEADER = """你是中文用户反馈研究分析师。下面是用户导入或从平台采集的评论（每条带编号、点赞数与来源链接）。

## 任务
只提取用户在真实使用中遇到的“痛点”，不要把好评、愿望、广告文案算成痛点。

## 输出 JSON（不要输出其他内容）
{"pain_points": [
  {
    "statement": "不超过 30 字的痛点概括，用用户自己的说法",
    "category": "使用体验|质量|效果|价格|服务|物流|包装|人群不适配|信息不符|其他",
    "severity": 1,
    "evidence": [{"review_id": "评论编号", "quote": "从该条评论原文逐字复制的一段，不超过 60 字，不得改写"}]
  }
]}

## 硬性规则
1. review_id 只能取下面出现过的编号；quote 必须是该条评论原文中连续出现的一段字符。
2. severity 取 1=轻微、2=明显、3=严重（影响使用或造成损失）。
3. 同一件事合并成一个痛点；不同品类问题分开列。
4. 没有可靠证据就不要输出该痛点。最多输出 12 条。

## 评论
"""


def _format_docs(docs: Sequence[Dict[str, Any]], limit: int = 300) -> str:
    lines = []
    for doc in docs:
        rid = str(doc.get("review_id") or "")
        if not rid:
            continue
        text = truncate(doc.get("text"), limit)
        meta = []
        if doc.get("like"):
            meta.append(f"点赞 {doc.get('like')}")
        if doc.get("note_title"):
            meta.append(f"笔记《{truncate(doc.get('note_title'), 24)}》")
        suffix = f"（{'，'.join(meta)}）" if meta else ""
        lines.append(f"[{rid}] {text}{suffix}")
    return "\n".join(lines)


def _doc_like(doc: Dict[str, Any]) -> int:
    for key in ("like", "likes", "comment_like"):
        try:
            value = int(doc.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value:
            return value
    return 0


def _validate_point(raw: Dict[str, Any], doc_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    statement = truncate(raw.get("statement"), 40)
    category = normalize_text(raw.get("category"))
    if category not in CATEGORIES:
        category = "其他"
    severity = clamp_int(raw.get("severity"), 1, 3, 2)

    evidence: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    seen = set()
    for item in raw.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("review_id") or "").strip()
        quote = normalize_text(item.get("quote"))
        doc = doc_map.get(rid)
        if doc is None:
            rejected.append({"review_id": rid, "quote": quote, "reason": "评论编号不存在"})
            continue
        if not quote:
            rejected.append({"review_id": rid, "quote": quote, "reason": "引语为空"})
            continue
        haystack = normalize_text(doc.get("text")) + " " + normalize_text(doc.get("ocr_text"))
        if not quote_in_text(quote, haystack):
            rejected.append({"review_id": rid, "quote": quote, "reason": "引语在原文中找不到"})
            continue
        key = (rid, compact_text(quote))
        if key in seen:
            continue
        seen.add(key)
        evidence.append({
            "review_id": rid,
            "quote": quote,
            "source_url": doc.get("source_url") or doc.get("url") or "",
            "platform": doc.get("platform") or "小红书",
            "note_id": doc.get("note_id") or "",
            "like": _doc_like(doc),
            "review_text": truncate(doc.get("text"), 160),
        })

    unique_reviews = {item["review_id"] for item in evidence}
    engagement = sum(1 + math.log1p(item.get("like") or 0) for item in evidence
                     if item["review_id"] in unique_reviews)
    return {
        "statement": statement,
        "category": category,
        "severity": severity,
        "severity_label": SEVERITY_LABEL[severity],
        "evidence": evidence,
        "frequency": len(unique_reviews),
        "engagement": round(engagement, 2),
        "verified": bool(evidence),
        "rejected_evidence": rejected,
        "statements": [statement] if statement else [],
    }


def extract_pain_points(
    docs: Sequence[Dict[str, Any]],
    llm_call,
    *,
    batch_size: int = 25,
    max_batches: int = 8,
) -> Dict[str, Any]:
    """按批调用 LLM 提取痛点，并逐条校验引语。"""
    usable = [doc for doc in docs if str(doc.get("review_id") or "").strip() and normalize_text(doc.get("text"))]
    doc_map = {str(doc["review_id"]).strip(): doc for doc in usable}
    points: List[Dict[str, Any]] = []
    errors: List[str] = []
    batches = 0
    if not usable:
        return {"points": [], "errors": ["没有可分析的评论文本"], "batches": 0, "docs": 0}

    for start in range(0, len(usable), max(1, batch_size)):
        if batches >= max_batches:
            break
        batch = usable[start:start + batch_size]
        prompt = PAIN_PROMPT_HEADER + _format_docs(batch)
        batches += 1
        try:
            raw = llm_call(prompt)
        except Exception as exc:  # 单批失败不拖垮整轮
            errors.append(f"第 {batches} 批提取失败：{type(exc).__name__}: {str(exc)[:160]}")
            continue
        parsed = parse_json_any(raw)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("pain_points"), list):
            errors.append(f"第 {batches} 批模型响应缺少痛点列表")
            continue
        for item in as_list(parsed, "pain_points"):
            point = _validate_point(item, doc_map)
            if point["statement"]:
                points.append(point)
    return {"points": points, "errors": errors, "batches": batches, "docs": len(usable)}


def _merge_into(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    target["severity"] = max(target["severity"], source["severity"])
    target["severity_label"] = SEVERITY_LABEL[target["severity"]]
    for statement in source.get("statements") or []:
        if statement and statement not in target["statements"]:
            target["statements"].append(statement)
    seen = {(item["review_id"], compact_text(item["quote"])) for item in target["evidence"]}
    for item in source.get("evidence") or []:
        key = (item["review_id"], compact_text(item["quote"]))
        if key not in seen:
            seen.add(key)
            target["evidence"].append(item)
    target["rejected_evidence"].extend(source.get("rejected_evidence") or [])
    target["verified"] = bool(target["evidence"])
    unique = {item["review_id"] for item in target["evidence"]}
    target["frequency"] = len(unique)
    target["engagement"] = round(sum(1 + math.log1p(item.get("like") or 0) for item in target["evidence"]), 2)


def cluster_points(points: Sequence[Dict[str, Any]], threshold: float = 0.45) -> List[Dict[str, Any]]:
    """把说法相近、品类相同的痛点合并；证据按评论去重。"""
    clusters: List[Dict[str, Any]] = []
    for point in sorted(points, key=lambda item: (-item.get("severity", 0), -item.get("frequency", 0))):
        tokens = token_set(point.get("statement"))
        merged = False
        for cluster in clusters:
            if cluster["category"] != point["category"]:
                continue
            same = normalize_text(cluster["statement"]) == normalize_text(point["statement"])
            if same or jaccard(tokens, token_set(cluster["statement"])) >= threshold:
                _merge_into(cluster, point)
                merged = True
                break
        if not merged:
            clusters.append({
                "statement": point["statement"],
                "category": point["category"],
                "severity": point["severity"],
                "severity_label": point["severity_label"],
                "evidence": list(point["evidence"]),
                "rejected_evidence": list(point["rejected_evidence"]),
                "frequency": point["frequency"],
                "engagement": point["engagement"],
                "verified": point["verified"],
                "statements": list(point.get("statements") or [point["statement"]]),
            })
    return clusters


def _score(point: Dict[str, Any]) -> float:
    frequency = max(1, int(point.get("frequency") or 0))
    engagement = max(0.0, float(point.get("engagement") or 0.0))
    severity = max(1, int(point.get("severity") or 1))
    return round(severity * (0.65 * math.log1p(frequency) + 0.35 * math.log1p(engagement)), 2)


def rank_points(points: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按证据强度排序，并分配稳定 id：pp-1 为榜首。"""
    ranked = []
    for point in points:
        item = dict(point)
        item["score"] = _score(item)
        ranked.append(item)
    ranked.sort(key=lambda item: (item["verified"], item["score"], item["frequency"]), reverse=True)
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
        item["id"] = f"pp-{index}"
    return ranked


def analyze_pain_points(docs: Sequence[Dict[str, Any]], llm_call, *, batch_size: int = 25) -> Dict[str, Any]:
    """完整链路：提取 → 合并 → 排序。"""
    extracted = extract_pain_points(docs, llm_call, batch_size=batch_size)
    clusters = cluster_points(extracted["points"])
    ranked = rank_points(clusters)
    verified = [item for item in ranked if item["verified"]]
    return {
        "pain_points": ranked,
        "verified_count": len(verified),
        "unverified_count": len(ranked) - len(verified),
        "rejected_evidence": sum(len(item.get("rejected_evidence") or []) for item in ranked),
        "errors": extracted["errors"],
        "batches": extracted["batches"],
        "docs": extracted["docs"],
    }
