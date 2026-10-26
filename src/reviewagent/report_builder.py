# -*- coding: utf-8 -*-
"""报告骨架：用真实对象元数据生成可核对的结构化报告。

这个阶段没有登录采集，也没有调用 LLM。因此报告只写三件有证据的事：
1. 对象是谁（标题、品牌、店铺、平台 ID、链接）；
2. 同款/近似款候选有哪些，凭什么这样判断；
3. 哪些数据还没有，下一步补什么。

没有评论就不计算口碑分、风险等级、痛点和运营建议；字段返回 None 或空数组，
不用 0 分、0 个痛点或模板文案冒充分析结果。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

REPORT_VERSION = "v2-skeleton-1"
OWNERSHIP_LABELS = {"own": "自家商品", "competitor": "竞品"}
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    import re

    text = re.sub(r"\s+", " ", str(value)).strip()
    return text


def _unique(items: Iterable[Dict[str, Any]], key_fields: tuple) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for item in items:
        key = tuple(_clean(item.get(field)) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _object_type(obj: Dict[str, Any]) -> str:
    if obj.get("input_type") == "keyword":
        return "keyword"
    if obj.get("platform") == "xhs":
        return "note"
    if obj.get("platform_id"):
        return "product"
    return "unknown"


def _object_summary(obj: Dict[str, Any], ownership: str) -> Dict[str, Any]:
    object_type = _object_type(obj)
    reviews_available = False
    return {
        "type": object_type,
        "type_label": "商品" if object_type == "product" else "笔记" if object_type == "note" else "关键词",
        "platform": _clean(obj.get("platform")),
        "platform_label": _clean(obj.get("platform_label")),
        "platform_id": _clean(obj.get("platform_id")),
        "title": _clean(obj.get("title")),
        "brand": _clean(obj.get("brand")),
        "shop": _clean(obj.get("shop")),
        "url": _clean(obj.get("url")),
        "image_url": _clean(obj.get("image_url")),
        "category": list(obj.get("category") or []),
        "variants": list(obj.get("variants") or []),
        "variant_count": len(obj.get("variants") or []),
        "status": _clean(obj.get("status")),
        "status_label": _clean(obj.get("status_label")),
        "confidence": obj.get("confidence"),
        "confidence_label": _clean(obj.get("confidence_label")),
        "metadata_score": obj.get("metadata_score"),
        "parser": _clean(obj.get("parser")),
        "fetched_at": _clean(obj.get("fetched_at")),
        "ownership": ownership,
        "ownership_label": OWNERSHIP_LABELS.get(ownership, ownership),
        "reviews_available": reviews_available,
    }


def _merge_gaps(primary: Dict[str, Any], match_summary: Dict[str, Any], review_count: int) -> List[Dict[str, Any]]:
    gaps: List[Dict[str, Any]] = []
    for gap in list(primary.get("gaps") or []) + list(match_summary.get("gaps") or []):
        if isinstance(gap, dict):
            gaps.append(dict(gap))
    if review_count == 0:
        gaps.append(
            {
                "code": "no_reviews_captured",
                "label": "评论未采集",
                "detail": "本阶段只解析商品页，没有登录采集评论；口碑分、风险、痛点和运营建议都缺少原始样本。",
                "severity": "high",
            }
        )
    gaps = _unique(gaps, ("code", "detail"))
    gaps.sort(key=lambda item: SEVERITY_RANK.get(_clean(item.get("severity")), 9))
    return gaps


def _next_actions(
    primary: Dict[str, Any],
    match_summary: Dict[str, Any],
    gaps: List[Dict[str, Any]],
    review_count: int,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for action in primary.get("next_actions") or []:
        if isinstance(action, dict) and _clean(action.get("label")):
            actions.append(
                {
                    "priority": "P0",
                    "label": _clean(action.get("label")),
                    "detail": _clean(action.get("detail")),
                    "kind": "input",
                }
            )
    if review_count == 0:
        actions.append(
            {
                "priority": "P0",
                "label": "补评论样本",
                "detail": "把商品评论粘贴进来，或开启登录采集；有原始评论后才能计算情绪、有效样本、痛点与运营动作。",
                "kind": "data",
            }
        )
    if not match_summary.get("total_candidates"):
        actions.append(
            {
                "priority": "P1",
                "label": "补同款或近似款链接",
                "detail": "当前候选只来自同一 SPU；补充跨平台链接后，才能比较不同平台的口碑差异。",
                "kind": "input",
            }
        )
    if any(gap.get("code") == "jd_reviews_unavailable" for gap in gaps):
        actions.append(
            {
                "priority": "P1",
                "label": "确认评论采集方式",
                "detail": "京东评论接口需要平台风控签名；下一步要么接入已登录的只读采集，要么由用户提供评论样本。",
                "kind": "method",
            }
        )
    keywords = list(match_summary.get("search_keywords") or [])
    if keywords:
        actions.append(
            {
                "priority": "P2",
                "label": "按关键词人工找同款",
                "detail": "可用关键词：" + "；".join(keywords),
                "kind": "search",
            }
        )
    return actions


def _coverage(
    primary: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
    tier: str,
    window_months: int,
) -> Dict[str, Any]:
    platforms: List[Dict[str, Any]] = []
    if primary.get("platform"):
        platforms.append(
            {
                "platform": _clean(primary.get("platform")),
                "label": _clean(primary.get("platform_label")) or _clean(primary.get("platform")),
                "role": "主商品",
                "object_count": 1,
                "review_count": 0,
                "status": "object_only",
                "status_label": "已解析对象，未采集评论",
            }
        )
    for candidate in candidates:
        platform = _clean(candidate.get("platform"))
        label = _clean(candidate.get("platform_label")) or platform
        existing = next((item for item in platforms if item.get("platform") == platform), None)
        if existing:
            existing["object_count"] += 1
            continue
        platforms.append(
            {
                "platform": platform,
                "label": label,
                "role": "候选",
                "object_count": 1,
                "review_count": 0,
                "status": "object_only",
                "status_label": "仅有对象信息，未采集评论",
            }
        )
    for review in reviews:
        platform = _clean(review.get("platform"))
        if not platform:
            continue
        match = next(
            (item for item in platforms if platform in {item.get("platform"), item.get("label")}),
            None,
        )
        if match:
            match["review_count"] += 1
    for item in platforms:
        if item["review_count"]:
            item["status"] = "reviews_present"
            item["status_label"] = "已有评论，未做完整分析"
    return {
        "mode": "anonymous",
        "tier": tier,
        "window_months": window_months,
        "platforms": platforms,
        "object_count": 1 + len(candidates),
        "review_count": len(reviews),
        "note": "本阶段不登录、不采集评论；平台覆盖只统计已经解析到的对象，不代表评论样本覆盖。",
    }


def _trust_block(reviews: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not reviews:
        return None
    try:
        from reviewagent.trust_report import TrustReportEngine

        report = TrustReportEngine().generate_report(reviews)
    except Exception as exc:  # 不让统计失败拖垮对象报告
        return {
            "status": "error",
            "status_label": "可信度计算失败",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "status": "available",
        "status_label": "已计算",
        "overall_trust_score": report.get("overall_trust_score"),
        "risk_level": report.get("risk_level"),
        "burst_detected": report.get("burst_detected"),
        "duplicate_groups": report.get("duplicate_groups") or [],
        "rating_anomaly": report.get("rating_anomaly"),
        "mismatch_count": report.get("mismatch_count"),
        "summary": report.get("summary"),
        "signals": report.get("signals") or [],
    }


def _diagnosis_summary(primary: Dict[str, Any], trust: Optional[Dict[str, Any]], review_count: int) -> str:
    if review_count == 0:
        return (
            "评论样本为 0，因此没有口碑总分、风险等级和情绪分布。"
            "当前只确认了商品对象与同规格候选，不能据此判断用户满意或不满。"
        )
    if trust and trust.get("status") == "available":
        return (
            f"已收到 {review_count} 条评论，可信度分 {trust.get('overall_trust_score')}，"
            f"风险等级 {trust.get('risk_level')}。情绪分布与痛点需要完整分析后才能生成。"
        )
    return f"已收到 {review_count} 条评论，但可信度计算未完成；不用占位数字代替。"


def _overview_conclusion(primary: Dict[str, Any], candidates: List[Dict[str, Any]], review_count: int) -> str:
    title = _clean(primary.get("title")) or _clean(primary.get("input")) or "当前对象"
    brand = _clean(primary.get("brand"))
    platform = _clean(primary.get("platform_label")) or _clean(primary.get("platform"))
    name = f"{brand} {title}".strip() if brand and brand not in title else title
    if review_count == 0:
        return (
            f"已确认{platform}对象「{name}」，并找到 {len(candidates)} 个同 SPU 规格候选。"
            "评论尚未采集，报告停在对象与候选层，不生成口碑结论。"
        )
    return (
        f"已确认{platform}对象「{name}」，找到 {len(candidates)} 个同款/近似款候选，"
        f"并收到 {review_count} 条评论；情绪与痛点结论需要完整分析后补充。"
    )


def build_analysis_report(
    primary: Dict[str, Any],
    match_result: Optional[Dict[str, Any]] = None,
    *,
    ownership: str = "own",
    input_text: str = "",
    tier: str = "standard",
    window_months: int = 12,
    reviews: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """生成对象层报告。返回值可直接 JSON 序列化。"""
    primary = dict(primary or {})
    match_result = match_result or {"candidates": [], "summary": {}}
    candidates = list(match_result.get("candidates") or [])
    match_summary = dict(match_result.get("summary") or {})
    reviews = list(reviews or [])
    review_count = len(reviews)
    trust = _trust_block(reviews)
    gaps = _merge_gaps(primary, match_summary, review_count)
    actions = _next_actions(primary, match_summary, gaps, review_count)
    coverage = _coverage(primary, candidates, reviews, tier, window_months)
    object_data = _object_summary(primary, ownership)
    object_data["reviews_available"] = review_count > 0

    evidence: List[Dict[str, Any]] = []
    for index, item in enumerate(primary.get("evidence") or []):
        if not isinstance(item, dict):
            continue
        evidence.append(
            {
                "id": _clean(item.get("id")) or f"ev-object-{index + 1}",
                "type": _clean(item.get("type")) or "object",
                "title": _clean(item.get("title")) or _clean(primary.get("title")) or "对象页",
                "url": _clean(item.get("url")) or _clean(primary.get("url")),
                "quote": _clean(item.get("quote")) or _clean(primary.get("title")),
                "fields": list(item.get("fields") or []),
                "fetched_at": _clean(item.get("fetched_at")) or _clean(primary.get("fetched_at")),
            }
        )
    for candidate in candidates:
        for item in candidate.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            evidence.append(
                {
                    "id": "",
                    "type": _clean(item.get("type")) or "product_page",
                    "title": _clean(item.get("title")) or _clean(candidate.get("title")) or "候选页",
                    "url": _clean(item.get("url")) or _clean(candidate.get("url")),
                    "quote": _clean(item.get("quote")),
                    "fields": ["candidate"],
                    "fetched_at": "",
                }
            )
    evidence = _unique(evidence, ("url", "quote"))
    for index, item in enumerate(evidence):
        if not item.get("id"):
            item["id"] = f"ev-{index + 1}"

    status = "metadata_only" if review_count == 0 else "partial"
    status_label = "仅对象元数据" if review_count == 0 else "已有评论，分析未完成"
    data_status = {
        "status": status,
        "status_label": status_label,
        "object_resolved": bool(primary.get("title") or primary.get("platform_id")),
        "reviews_captured": review_count,
        "llm_used": False,
        "note": "对象与候选来自公开页面；评论为空时所有口碑指标返回 null，不用占位数字。",
    }

    dashboard = {
        "score": None,
        "score_label": "未计算",
        "score_note": "需要评论样本与情绪分析",
        "valid_samples": None,
        "review_count": review_count,
        "sample_note": "原始评论条数；有效样本需去重与可信度计算后确定",
        "risk": "unknown" if not trust else trust.get("risk_level", "unknown"),
        "risk_label": "未评估" if not trust else str(trust.get("risk_level") or "unknown"),
        "pain_count": None,
        "pain_note": "评论未分析",
        "opportunity_count": None,
        "opportunity_note": "痛点未生成",
        "candidate_count": len(candidates),
        "candidate_note": "同款 + 近似款候选",
        "coverage_platforms": len(coverage["platforms"]),
        "coverage_note": "已解析对象的平台数，不是评论覆盖",
    }

    competitors = {
        "status": "available" if candidates else "empty",
        "status_label": "已列出候选" if candidates else "没有候选",
        "summary": match_summary.get("auto_discovery_reason") or "候选只来自同一 SPU 与用户补充链接。",
        "items": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "match_level": candidate.get("match_level"),
                "match_label": candidate.get("match_label"),
                "match_score": candidate.get("match_score"),
                "title": candidate.get("title"),
                "platform_label": candidate.get("platform_label"),
                "url": candidate.get("url"),
                "match_reasons": candidate.get("match_reasons") or [],
                "reasons": candidate.get("match_reasons") or [],
                "mismatches": candidate.get("mismatches") or [],
                "price": None,
                "sales": None,
                "review_count": None,
            }
            for candidate in candidates
        ],
    }

    report = {
        "version": REPORT_VERSION,
        "generated_at": _now(),
        "stage": status,
        "stage_label": status_label,
        "input": _clean(input_text) or _clean(primary.get("input")),
        "object": object_data,
        "data_status": data_status,
        "dashboard": dashboard,
        "overview": {
            "status": "available",
            "conclusion": _overview_conclusion(primary, candidates, review_count),
            "bullets": [
                {"label": "对象", "value": f"{object_data['platform_label']} · {object_data['title'] or '未解析标题'}"},
                {"label": "商品 ID", "value": object_data["platform_id"] or "无"},
                {"label": "同款候选", "value": f"{len(candidates)} 个" if candidates else "0 个"},
                {"label": "评论样本", "value": f"{review_count} 条" if review_count else "未采集"},
                {"label": "报告阶段", "value": status_label},
            ],
            "data_status": data_status,
        },
        "diagnosis": {
            "status": "insufficient_data" if review_count == 0 else "partial",
            "status_label": "缺少评论" if review_count == 0 else "已有评论，分析部分完成",
            "summary": _diagnosis_summary(primary, trust, review_count),
            "score": None,
            "risk": dashboard["risk"],
            "review_count": review_count,
            "trust": trust,
            "signals": [],
            "reasons": [
                "当前报告只覆盖商品页对象层。",
                "情绪 9 类、有效性 8 类与痛点抽取需要原始评论，不能用商品标题代替。",
            ] if review_count == 0 else ["可信度已计算；情绪分类与痛点抽取尚未运行。"],
        },
        "pain_points": {
            "status": "insufficient_data",
            "status_label": "未生成",
            "summary": "没有评论原文，无法抽取痛点；空列表不代表没有痛点。",
            "items": [],
        },
        "improvements": {
            "status": "insufficient_data",
            "status_label": "未生成",
            "summary": "改进方向必须由痛点与证据支撑；当前没有评论证据。",
            "items": [],
        },
        "topics": {
            "status": "insufficient_data",
            "status_label": "未生成",
            "summary": "内容选题需要人群、痛点与场景；当前只有商品信息。",
            "items": [],
        },
        "content_kit": {
            "status": "insufficient_data",
            "status_label": "未生成",
            "summary": "主图 brief、详情页 8 段与 15 秒脚本都依赖评论证据，暂不生成。",
            "data": None,
        },
        "competitors": competitors,
        "ops_plan": {
            "status": "insufficient_data",
            "status_label": "未生成",
            "summary": "运营方案需要痛点、转化证据与商家数据；当前样本不足。",
            "groups": [],
        },
        "actions": [],
        "next_actions": actions,
        "coverage": coverage,
        "same_products": {
            "summary": match_summary,
            "items": candidates,
        },
        "gaps": gaps,
        "evidence": evidence,
        "method": {
            "resolver": _clean(primary.get("parser")) or "none",
            "matching": "品牌 + 型号/系列词 + 标题相似度 + 类目；同 SPU 直接标同款",
            "llm_used": False,
            "review_analysis": "not_run" if review_count == 0 else "trust_only",
            "report_version": REPORT_VERSION,
            "limitations": [
                "未登录，评论接口未接入。",
                "价格、销量、评论数未从商品页稳定取得，统一为 null。",
                "同款候选只来自同一 SPU 与用户补充链接，没有自动跨平台搜索。",
            ],
        },
    }
    return {
        "status": "ready" if primary.get("status") in {"resolved", "partial"} else "needs_input",
        "status_label": "报告已生成" if primary.get("status") in {"resolved", "partial"} else "需要补充输入",
        "object": primary,
        "candidates": candidates,
        "match_summary": match_summary,
        "report": report,
    }
