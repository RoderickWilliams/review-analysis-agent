# -*- coding: utf-8 -*-
"""离线评测：数据集加载、分类指标、双标一致性与规则基线。

用途是给分析内核一个可复现的评分台阶，而不是替代人工判断：

    reviewagent eval --dataset data/eval/sample.jsonl --baseline rules --out eval.json
    reviewagent eval --dataset data/eval/sample.jsonl --predictions preds.json

数据集为 JSON Lines（每行一个 JSON 对象）或 JSON 数组，字段：

    {"id": "r1", "text": "评论正文", "rating": 5, "date": "2026-01-01",
     "sentiment": "真诚好评", "validity": "真实有效"}

sentiment / validity 使用内核的中文类别名（见 sentiment_agent_core 的枚举）；
字段可缺省，缺省的维度不参与对应指标计算。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# 与内核一致的中文类别名
SENTIMENT_LABELS = [
    "真诚好评",
    "直接差评",
    "客观中性",
    "反讽阴阳怪气",
    "明褒暗贬",
    "隐性抱怨",
    "高分低评",
    "低分高评",
    "评分极端文本中性",
]
VALIDITY_LABELS = [
    "真实有效",
    "模板化好评",
    "套话堆砌",
    "批量复制",
    "时间集中异常",
    "内容偏移",
    "用户行为异常",
    "AI生成",
]

_POSITIVE_WORDS = ("好", "不错", "满意", "喜欢", "给力", "推荐", "值得", "舒服", "清晰", "耐用")
_NEGATIVE_WORDS = ("差", "烂", "垃圾", "失望", "退货", "坏", "卡", "慢", "贵", "后悔", "难用")
_SARCASM_MARKERS = ("呵呵", "真好", "真棒", "太好了", "谢谢啊", "省得", "冥想", "修行", "环保", "佩服")
_TEMPLATE_PHRASES = ("好评", "物流很快", "客服很好", "下次再来", "一如既往", "物超所值", "值得购买")


# ── 数据集 ────────────────────────────────────────────────

def load_dataset(path: str | Path) -> List[Dict[str, Any]]:
    """读取 JSONL / JSON 数组数据集，逐行校验并返回记录列表。"""
    p = Path(path)
    if not p.exists():
        raise ValueError(f"数据集不存在: {p}")
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError("数据集为空")
    if raw.startswith("["):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"数据集 JSON 解析失败: {exc}") from exc
        if not isinstance(data, list):
            raise ValueError("数据集 JSON 顶层必须是数组")
        records = data
    else:
        records = []
        for lineno, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"第 {lineno} 行 JSON 解析失败: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"第 {lineno} 行必须是 JSON 对象")
            records.append(item)

    items: List[Dict[str, Any]] = []
    for index, record in enumerate(records):
        text = str(record.get("text") or record.get("review_text") or "").strip()
        if not text:
            raise ValueError(f"第 {index + 1} 条记录缺少 text")
        rating = record.get("rating")
        try:
            rating = int(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating = None
        item = {
            "id": str(record.get("id") or f"item-{index + 1}"),
            "text": text,
            "rating": rating,
            "date": str(record.get("date") or record.get("review_date") or ""),
        }
        for label in ("sentiment", "validity"):
            value = record.get(label)
            if value:
                item[label] = str(value)
        items.append(item)
    return items


# ── 指标 ──────────────────────────────────────────────────

def cohen_kappa(labels_a: Sequence[Any], labels_b: Sequence[Any]) -> float:
    """两套标注的 Cohen's kappa；完全一致返回 1.0，随机水平为 0。"""
    if len(labels_a) != len(labels_b):
        raise ValueError("两套标注长度必须一致")
    if not labels_a:
        raise ValueError("标注为空，无法计算 kappa")
    total = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / total
    counts_a = Counter(labels_a)
    counts_b = Counter(labels_b)
    expected = sum(
        (counts_a[label] / total) * (counts_b[label] / total)
        for label in set(counts_a) | set(counts_b)
    )
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def classification_metrics(
    gold: Sequence[Any],
    pred: Sequence[Any],
    labels: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """多分类指标：准确率、逐类 P/R/F1、macro/weighted F1 与混淆矩阵。"""
    if len(gold) != len(pred):
        raise ValueError("gold 与 pred 长度必须一致")
    label_list = list(labels) if labels else sorted({str(v) for v in gold} | {str(v) for v in pred})
    total = len(gold)
    per_label: Dict[str, Dict[str, float]] = {}
    confusion: Dict[str, Dict[str, int]] = {label: {other: 0 for other in label_list} for label in label_list}

    correct = 0
    for g, p in zip(gold, pred):
        g, p = str(g), str(p)
        if g == p:
            correct += 1
        if g not in confusion:
            confusion[g] = {other: 0 for other in label_list}
        confusion[g][p] = confusion[g].get(p, 0) + 1

    for label in label_list:
        tp = confusion.get(label, {}).get(label, 0)
        support = sum(confusion.get(label, {}).values())
        predicted = sum(row.get(label, 0) for row in confusion.values())
        precision = _safe_div(tp, predicted)
        recall = _safe_div(tp, support)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        per_label[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
            "predicted": predicted,
        }

    active = [label for label in label_list if per_label[label]["support"] > 0]
    macro_f1 = _safe_div(sum(per_label[label]["f1"] for label in active), len(active))
    weighted_f1 = _safe_div(
        sum(per_label[label]["f1"] * per_label[label]["support"] for label in label_list),
        total,
    )
    return {
        "samples": total,
        "accuracy": round(_safe_div(correct, total), 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "labels": active,
        "per_label": per_label,
        "confusion_matrix": confusion,
    }


# ── 预测 ──────────────────────────────────────────────────

def rules_predict(items: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    """零成本规则基线：只做词表与模板短语匹配，用于给评测提供下限参照。"""
    predictions = []
    for item in items:
        text = str(item.get("text", ""))
        rating = item.get("rating")
        positive = any(word in text for word in _POSITIVE_WORDS)
        negative = any(word in text for word in _NEGATIVE_WORDS)
        if any(marker in text for marker in _SARCASM_MARKERS):
            sentiment = "反讽阴阳怪气"
        elif positive and negative:
            sentiment = "客观中性"
        elif positive and (rating is None or rating >= 4):
            sentiment = "真诚好评"
        elif negative and (rating is None or rating <= 3):
            sentiment = "直接差评"
        elif rating is not None and rating >= 4 and negative:
            sentiment = "高分低评"
        else:
            sentiment = "客观中性"

        if len(text) < 10 or any(phrase in text for phrase in _TEMPLATE_PHRASES):
            validity = "模板化好评"
        else:
            validity = "真实有效"
        predictions.append({"sentiment": sentiment, "validity": validity})
    return predictions


def predictions_from_results(results: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    """把 pipeline 的分析结果映射成评测用的预测标签。"""
    predictions = []
    for result in results:
        sentiment_part = result.get("sentiment_analysis") or {}
        validity_part = result.get("validity_analysis") or {}
        final_part = result.get("final_analysis") or {}
        sentiment = (
            final_part.get("final_sentiment")
            or sentiment_part.get("sentiment_label")
            or sentiment_part.get("sentiment_category")
            or ""
        )
        validity = validity_part.get("validity_label") or validity_part.get("validity_category") or ""
        predictions.append({"sentiment": str(sentiment), "validity": str(validity)})
    return predictions


def evaluate(
    items: Sequence[Dict[str, Any]],
    predictions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """按数据集里存在的标注维度计算指标；缺标注的维度返回 null。"""
    if len(items) != len(predictions):
        raise ValueError("items 与 predictions 数量必须一致")
    report: Dict[str, Any] = {"samples": len(items), "dimensions": {}}
    for dimension, label_set in (("sentiment", SENTIMENT_LABELS), ("validity", VALIDITY_LABELS)):
        pairs = [
            (item[dimension], str(pred.get(dimension) or ""))
            for item, pred in zip(items, predictions)
            if item.get(dimension)
        ]
        if not pairs:
            report["dimensions"][dimension] = None
            continue
        gold = [gold_label for gold_label, _ in pairs]
        pred_labels = [pred_label for _, pred_label in pairs]
        report["dimensions"][dimension] = classification_metrics(gold, pred_labels, labels=label_set)
    if report["dimensions"].get("validity"):
        invalid_total = sum(1 for pred in predictions if pred.get("validity") and pred["validity"] != "真实有效")
        report["invalid_rate"] = round(_safe_div(invalid_total, len(predictions)), 4)
    return report


def load_predictions(path: str | Path) -> List[Dict[str, Any]]:
    """读取预测文件：JSON 数组，或 pipeline 结果数组。"""
    p = Path(path)
    if not p.exists():
        raise ValueError(f"预测文件不存在: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"预测文件解析失败: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("results") or data.get("predictions") or []
    if not isinstance(data, list):
        raise ValueError("预测文件顶层必须是数组")
    return data


def evaluate_dataset(
    dataset_path: str | Path,
    predictions_path: str | Path | None = None,
    baseline: str = "rules",
) -> Dict[str, Any]:
    """加载数据集、产生预测并计算指标。baseline 可选 rules / none。"""
    items = load_dataset(dataset_path)
    if predictions_path:
        raw = load_predictions(predictions_path)
        predictions = raw if raw and "sentiment_analysis" not in (raw[0] or {}) else predictions_from_results(raw)
    elif baseline == "rules":
        predictions = rules_predict(items)
    elif baseline in ("none", ""):
        predictions = [{} for _ in items]
    else:
        raise ValueError(f"未知基线: {baseline}")
    report = evaluate(items, predictions)
    report["dataset"] = str(dataset_path)
    report["baseline"] = baseline if not predictions_path else "predictions-file"
    return report
