"""Shared input rules and deterministic statistics for every entry point."""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

POLARITIES = {"positive", "negative", "neutral"}
VALIDITIES = {"authentic", "suspicious", "fake", "unknown"}
MAX_TEXT_LENGTH = 20000


def normalize_review(item: Any, index: int = 0) -> Dict[str, Any]:
    if isinstance(item, str):
        item = {"review_text": item}
    if not isinstance(item, dict):
        raise ValueError(f"第 {index + 1} 条评论必须是文本或对象")
    text = next((item.get(k) for k in ("review_text", "text", "content", "comment") if item.get(k) is not None), "")
    if not isinstance(text, str) or not text.strip() or text.strip().lower() in {"nan", "null", "none"}:
        raise ValueError(f"第 {index + 1} 条评论缺少正文")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).strip()
    if not text:
        raise ValueError(f"第 {index + 1} 条评论缺少正文")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"第 {index + 1} 条评论超过 {MAX_TEXT_LENGTH} 字符")
    rating = item.get("rating")
    if isinstance(rating, bool):
        raise ValueError(f"第 {index + 1} 条评分必须为 1–5 或留空")
    if rating is None or rating == "" or rating == 0 or str(rating).lower() == "nan":
        rating = None
    else:
        try:
            number = float(rating)
        except (ValueError, TypeError):
            raise ValueError(f"第 {index + 1} 条评分必须为 1–5 或留空") from None
        if not math.isfinite(number) or not number.is_integer() or not 1 <= number <= 5:
            raise ValueError(f"第 {index + 1} 条评分必须为 1–5 或留空")
        rating = int(number)
    date = item.get("review_date") or item.get("date") or item.get("published_at") or item.get("timestamp") or ""
    if date:
        if isinstance(date, (int, float)) and not isinstance(date, bool):
            try:
                date = datetime.fromtimestamp(date / 1000 if date > 1e11 else date, tz=timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                raise ValueError(f"第 {index + 1} 条日期无效") from None
        date = str(date).strip()
        try:
            datetime.fromisoformat(date.replace("Z", "+00:00").replace("/", "-"))
        except ValueError:
            raise ValueError(f"第 {index + 1} 条日期需使用 YYYY-MM-DD 或 ISO 时间格式") from None
    platform = str(item.get("source_platform") or item.get("platform") or "manual").strip()
    platform = {"京东": "jd", "淘宝": "taobao", "天猫": "tmall", "淘宝/天猫": "taobao", "小红书": "xhs"}.get(platform, platform)
    result = dict(item)
    result.update(review_text=text, rating=rating, review_date=date, platform=platform, source_platform=platform)
    result["source_url"] = str(item.get("source_url") or item.get("url") or "")
    result["imported_at"] = item.get("imported_at") or datetime.now().astimezone().isoformat(timespec="seconds")
    identity = item.get("review_id")
    if not identity and item.get("comment_id"):
        identity = "review_" + hashlib.sha256(f"{platform}|{result['source_url']}|{item['comment_id']}".encode()).hexdigest()[:20]
    if not identity:
        raw = "|".join(str(x) for x in (platform, result["source_url"], item.get("reviewer_name", ""), date, text, index))
        identity = "review_" + hashlib.sha256(raw.encode()).hexdigest()[:20]
    result["review_id"] = str(identity)
    return result


def normalize_reviews(items: List[Any], *, strict: bool = True) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError("评论必须是列表")
    if len(items) > 5000:
        raise ValueError("单次最多处理 5000 条评论，请分批导入")
    result, identities = [], set()
    for index, item in enumerate(items):
        try:
            review = normalize_review(item, index)
            if review["review_id"] in identities:
                raise ValueError("评论编号重复，请为每条评论提供唯一 review_id")
            identities.add(review["review_id"])
            result.append(review)
        except ValueError:
            if strict:
                raise
    return result


def result_succeeded(result: Any) -> bool:
    if not isinstance(result, dict) or result.get("status") in {"failed", "pending", "cancelled"}:
        return False
    final = result.get("final_analysis")
    if not isinstance(final, dict) or final.get("error"):
        return False
    score = final.get("trust_score")
    return (
        final.get("final_sentiment") in POLARITIES
        and final.get("final_validity") in VALIDITIES
        and ((score is None and final.get("final_validity") == "unknown")
             or (isinstance(score, (int, float)) and not isinstance(score, bool)
                 and math.isfinite(score) and 0 <= score <= 100))
    )


def summarize_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    successful = [r for r in results if result_succeeded(r)]
    sentiment = {key: 0 for key in ("positive", "negative", "neutral")}
    validity = {key: 0 for key in ("authentic", "suspicious", "fake", "unknown")}
    for result in successful:
        final = result["final_analysis"]
        sentiment[final["final_sentiment"]] += 1
        validity[final["final_validity"]] += 1
    total = len(successful)
    scores = [r["final_analysis"]["trust_score"] for r in successful if r["final_analysis"].get("trust_score") is not None]
    positive_authentic = sum(r["final_analysis"]["final_sentiment"] == "positive" and r["final_analysis"]["final_validity"] == "authentic" for r in successful)
    return {
        "total": len(results), "successful_count": total,
        "failed_count": sum(not result_succeeded(r) and r.get("status") not in {"pending", "cancelled"} for r in results),
        "pending_count": sum(r.get("status") == "pending" for r in results),
        "cancelled_count": sum(r.get("status") == "cancelled" for r in results),
        "sentiment_distribution": sentiment, "validity_distribution": validity,
        "sarcastic_count": sum(bool((r.get("sentiment_analysis") or {}).get("is_sarcastic")) for r in successful),
        "suspicious_count": validity["suspicious"] + validity["fake"],
        "avg_trust_score": round(sum(scores) / len(scores), 1) if scores else None,
        "authentic_positive_rate": round(100 * positive_authentic / total, 1) if total else None,
    }


def csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value
