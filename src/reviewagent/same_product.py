# -*- coding: utf-8 -*-
"""同款 / 近似款匹配：只比较已经拿到的对象，不编造候选。

当前阶段没有登录采集通道，所以这里不做“自动跨平台搜索”。它做三件事：
1. 把同一 SPU 下的不同规格列成同款候选；
2. 把用户补充的链接按品牌、型号词、标题、类目逐项比较；
3. 每个候选都给出匹配等级、分数、理由和缺失字段，匹配不了就写“不确定”。

价格、销量、评论数不在商品页稳定字段里，统一返回 None，并在
unavailable_fields 中说明；不能用它们排序或去重。
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

LEVEL_LABELS = {
    "exact": "同款",
    "similar": "近似款",
    "competitor": "竞品",
    "uncertain": "不确定",
}
LEVEL_RANK = {"exact": 0, "similar": 1, "competitor": 2, "uncertain": 3}

GENERIC_WORDS = {
    "商品", "产品", "正品", "官方", "旗舰", "旗舰店", "专卖", "专营", "自营",
    "新款", "新品", "包邮", "现货", "预售", "礼盒", "套装", "组合", "同款",
    "男", "女", "男士", "女士", "通用", "家用", "便携", "大容量", "官方旗舰店",
    "京东", "天猫", "淘宝", "小红书", "商城", "店铺", "下单", "购买",
    "支持", "赠", "送", "含", "装", "版", "款", "系列",
}

UNIT_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:ml|毫升|g|克|kg|千克|斤|寸|英寸|cm|厘米|mm|毫米|"
    r"件|瓶|盒|袋|包|支|片|粒|枚|条|双|只|套|箱|罐|桶|升|l)",
    re.I,
)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", _clean(text)).lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _strip_noise(text: str, brand: str = "") -> str:
    """去掉品牌、营销词、规格数字，留下可比较的型号/系列词。"""
    value = _normalize(text)
    if brand:
        value = value.replace(_normalize(brand), " ")
    value = UNIT_PATTERN.sub(" ", value)
    for word in sorted(GENERIC_WORDS, key=len, reverse=True):
        value = value.replace(_normalize(word), " ")
    value = re.sub(r"\b(?:19|20)\d{2}\s*年?\b", " ", value)
    value = re.sub(r"[【】\[\]（）()<>《》]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _ngrams(run: str) -> Iterable[str]:
    run = run.strip()
    if not run:
        return
    if len(run) <= 4:
        yield run
        return
    for size in (2, 3, 4):
        for index in range(0, len(run) - size + 1):
            yield run[index:index + size]


def semantic_tokens(text: str, brand: str = "") -> List[str]:
    """抽取用于比较的型号/系列 token（中文 2–4 字片段 + 字母数字型号）。"""
    value = _strip_noise(text, brand)
    tokens: List[str] = []
    for chunk in value.split():
        if re.fullmatch(r"[a-z0-9][a-z0-9._+-]*", chunk):
            if len(chunk) >= 2 and chunk not in {"www", "com", "html"}:
                tokens.append(chunk)
            continue
        if _has_cjk(chunk):
            tokens.extend(_ngrams(chunk))
    seen: set = set()
    out: List[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _token_overlap(primary_tokens: Sequence[str], candidate_tokens: Sequence[str]) -> float:
    a, b = set(primary_tokens), set(candidate_tokens)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def _title_similarity(a: str, b: str) -> float:
    left, right = _normalize(a), _normalize(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _category_set(value: Any) -> set:
    if isinstance(value, list):
        return {_clean(part) for part in value if _clean(part)}
    if value:
        return {_clean(value)}
    return set()


def _platform_id(obj: Dict[str, Any]) -> str:
    return _clean(obj.get("platform_id") or obj.get("object_id") or obj.get("sku_id"))


def _url(obj: Dict[str, Any]) -> str:
    return _clean(obj.get("url") or obj.get("source_url"))


def _platform(obj: Dict[str, Any]) -> str:
    return _clean(obj.get("platform") or "")


def _same_product_key(obj_a: Dict[str, Any], obj_b: Dict[str, Any]) -> bool:
    if _url(obj_a) and _url(obj_a) == _url(obj_b):
        return True
    return bool(
        _platform_id(obj_a)
        and _platform_id(obj_a) == _platform_id(obj_b)
        and _platform(obj_a) == _platform(obj_b)
    )


def _brand_of(obj: Dict[str, Any]) -> str:
    return _clean(obj.get("brand") or "")


def _primary_terms(primary: Dict[str, Any]) -> List[str]:
    return semantic_tokens(_clean(primary.get("title")), _brand_of(primary))


def _human_tokens(tokens: Sequence[str], limit: int = 4) -> str:
    seen: List[str] = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return "、".join(seen[:limit])


def _classify(
    score: float,
    *,
    same_spu: bool,
    brand_left: str,
    brand_right: str,
    title_sim: float,
    token_sim: float,
) -> str:
    if same_spu:
        return "exact"
    if brand_left and brand_right and brand_left != brand_right:
        if score >= 0.5 or title_sim >= 0.35:
            return "competitor"
        return "uncertain"
    if brand_left and brand_right and brand_left == brand_right:
        if score >= 0.78 and title_sim >= 0.62:
            return "exact"
        if score >= 0.5 or title_sim >= 0.45 or token_sim >= 0.45:
            return "similar"
        return "uncertain"
    if score >= 0.78 and title_sim >= 0.7:
        return "exact"
    if score >= 0.5 or token_sim >= 0.55:
        return "similar"
    return "uncertain"


def compare_objects(primary: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """给两个对象打匹配分。返回 score / level / reasons / mismatches。"""
    brand_a = _brand_of(primary)
    brand_b = _brand_of(candidate)
    title_a = _clean(primary.get("title"))
    title_b = _clean(candidate.get("title") or candidate.get("name"))
    same_spu = _same_product_key(primary, candidate)

    title_sim = _title_similarity(title_a, title_b)
    tokens_a = _primary_terms(primary)
    tokens_b = semantic_tokens(title_b, brand_b)
    token_sim = _token_overlap(tokens_a, tokens_b)
    category_a = _category_set(primary.get("category"))
    category_b = _category_set(candidate.get("category"))
    category_overlap = bool(category_a & category_b)
    shop_a = _clean(primary.get("shop"))
    shop_b = _clean(candidate.get("shop"))

    reasons: List[str] = []
    mismatches: List[str] = []
    if same_spu:
        score = 1.0
        reasons.append("平台商品 ID 相同，或链接指向同一商品")
    else:
        score = 0.45 * title_sim + 0.35 * token_sim
        if brand_a and brand_b:
            if brand_a == brand_b:
                score += 0.14
                reasons.append(f"品牌一致：{brand_a}")
            else:
                score -= 0.12
                mismatches.append(f"品牌不同：{brand_a} / {brand_b}")
        elif brand_a or brand_b:
            score += 0.02
        if category_overlap:
            score += 0.06
            reasons.append("类目一致")
        elif category_a and category_b:
            mismatches.append("类目不同")
        if shop_a and shop_b and shop_a == shop_b:
            score += 0.03
            reasons.append(f"店铺一致：{shop_a}")
        if title_sim >= 0.55:
            reasons.append(f"标题相似度 {title_sim:.2f}")
        if token_sim >= 0.35:
            common = sorted(set(tokens_a) & set(tokens_b), key=len, reverse=True)
            reasons.append(f"型号/系列词重合：{_human_tokens(common)}")
        if title_sim < 0.2 and token_sim == 0:
            mismatches.append("标题与型号词都没有可比对的重合")

    score = max(0.0, min(1.0, round(score, 2)))
    level = _classify(
        score,
        same_spu=same_spu,
        brand_left=brand_a,
        brand_right=brand_b,
        title_sim=title_sim,
        token_sim=token_sim,
    )
    return {
        "score": score,
        "level": level,
        "level_label": LEVEL_LABELS[level],
        "reasons": reasons,
        "mismatches": mismatches,
        "signals": {
            "same_platform_id": same_spu,
            "title_similarity": round(title_sim, 2),
            "token_overlap": round(token_sim, 2),
            "category_overlap": category_overlap,
            "brand_left": brand_a,
            "brand_right": brand_b,
        },
    }


def _candidate_record(
    obj: Dict[str, Any],
    *,
    source: str,
    comparison: Dict[str, Any],
    note: str = "",
) -> Dict[str, Any]:
    platform_id = _platform_id(obj)
    url = _url(obj)
    candidate_id = f"cand-{platform_id or abs(hash(url)) % 10_000_000}"
    return {
        "candidate_id": candidate_id,
        "source": source,
        "source_label": "同 SPU 规格" if source == "spu_variant" else "用户补充链接",
        "match_level": comparison["level"],
        "match_label": comparison["level_label"],
        "match_score": comparison["score"],
        "match_reasons": comparison["reasons"],
        "mismatches": comparison["mismatches"],
        "signals": comparison["signals"],
        "platform": _platform(obj),
        "platform_label": _clean(obj.get("platform_label") or _platform(obj)),
        "platform_id": platform_id,
        "title": _clean(obj.get("title")),
        "brand": _brand_of(obj),
        "shop": _clean(obj.get("shop")),
        "url": url,
        "image_url": _clean(obj.get("image_url")),
        "price": None,
        "sales": None,
        "review_count": None,
        "unavailable_fields": ["price", "sales", "review_count"],
        "note": note,
        "evidence": [
            {
                "type": "product_page",
                "title": _clean(obj.get("title")) or url,
                "url": url,
                "quote": _clean(obj.get("title")),
            }
        ] if url or _clean(obj.get("title")) else [],
    }


def _variant_object(primary: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "platform": primary.get("platform"),
        "platform_label": primary.get("platform_label"),
        "platform_id": _clean(variant.get("sku_id")),
        "title": _clean(variant.get("title")),
        "brand": primary.get("brand"),
        "shop": primary.get("shop"),
        "category": primary.get("category") or [],
        "url": _clean(variant.get("url")),
        "image_url": _clean(variant.get("image_url")),
    }


def _dedupe(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for candidate in candidates:
        key = (candidate.get("platform"), candidate.get("platform_id") or candidate.get("url"))
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _search_keywords(primary: Dict[str, Any], limit: int = 4) -> List[str]:
    brand = _brand_of(primary)
    title = _clean(primary.get("title"))
    terms = [token for token in _primary_terms(primary) if len(token) >= 2]
    keywords: List[str] = []
    if brand and terms:
        keywords.append(f"{brand} {terms[0]}")
    if title and len(title) > 4:
        keywords.append(title[:24])
    if brand:
        keywords.append(brand)
    seen: set = set()
    result: List[str] = []
    for keyword in keywords:
        keyword = _clean(keyword)
        if keyword and keyword not in seen:
            seen.add(keyword)
            result.append(keyword)
    return result[:limit]


def build_same_products(
    primary: Dict[str, Any],
    extra_objects: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """构建同款/近似款候选，返回候选列表与汇总。"""
    primary = primary or {}
    extra_objects = list(extra_objects or [])
    candidates: List[Dict[str, Any]] = []
    notes: List[str] = []

    for variant in primary.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        if _clean(variant.get("sku_id")) and _clean(variant.get("sku_id")) == _platform_id(primary):
            continue
        variant_obj = _variant_object(primary, variant)
        comparison = compare_objects(primary, variant_obj)
        comparison["level"] = "exact"
        comparison["level_label"] = LEVEL_LABELS["exact"]
        comparison["score"] = max(comparison["score"], 0.9)
        comparison["reasons"].insert(0, "同一 SPU 下的不同规格")
        candidate = _candidate_record(
            variant_obj,
            source="spu_variant",
            comparison=comparison,
            note="同一 SPU；颜色/容量/套装不同，可作为同款样本。",
        )
        if variant.get("color") or variant.get("size"):
            candidate["spec"] = " / ".join(
                part for part in (_clean(variant.get("color")), _clean(variant.get("size"))) if part
            )
        candidates.append(candidate)

    for obj in extra_objects:
        if not isinstance(obj, dict):
            continue
        if _same_product_key(primary, obj):
            notes.append(f"补充链接与主商品重复，已跳过：{_url(obj) or _clean(obj.get('title'))}")
            continue
        comparison = compare_objects(primary, obj)
        candidate = _candidate_record(
            obj,
            source="user_link",
            comparison=comparison,
            note="用户补充的链接，按同一套规则比较；未采集评论。",
        )
        if _clean(obj.get("status")) in {"needs_capture", "needs_link"} and not _clean(obj.get("title")):
            candidate["match_level"] = "uncertain"
            candidate["match_label"] = LEVEL_LABELS["uncertain"]
            candidate["match_score"] = 0.15
            candidate["match_reasons"] = ["只识别到链接，商品页没有返回标题和品牌"]
            candidate["mismatches"] = ["缺少可比对字段，不能判断是否同款"]
            candidate["note"] = "待采集商品详情后才能判断。"
        candidates.append(candidate)

    candidates = _dedupe(candidates)
    candidates.sort(key=lambda item: (LEVEL_RANK.get(item.get("match_level"), 9), -float(item.get("match_score") or 0)))

    counts = {level: 0 for level in LEVEL_LABELS}
    for candidate in candidates:
        counts[candidate["match_level"]] = counts.get(candidate["match_level"], 0) + 1
    platforms = sorted({candidate.get("platform_label") for candidate in candidates if candidate.get("platform_label")})
    if _platform(primary):
        platforms.insert(0, _clean(primary.get("platform_label")) or _platform(primary))
    platforms = list(dict.fromkeys(platforms))

    sibling_count = max(0, len(primary.get("variants") or []) - 1)
    summary = {
        "total_candidates": len(candidates),
        "shown": len(candidates),
        "exact": counts.get("exact", 0),
        "similar": counts.get("similar", 0),
        "competitor": counts.get("competitor", 0),
        "uncertain": counts.get("uncertain", 0),
        "sibling_variants": sibling_count,
        "user_supplied": sum(1 for c in candidates if c.get("source") == "user_link"),
        "platforms": platforms,
        "auto_discovery": "unavailable",
        "auto_discovery_reason": "当前没有登录采集通道，不会自动跨平台搜索同款；候选只来自同一 SPU 与用户补充链接。",
        "search_keywords": _search_keywords(primary),
        "notes": notes,
    }
    gaps: List[Dict[str, str]] = []
    if not candidates:
        gaps.append(
            {
                "code": "no_same_product_candidates",
                "label": "没有同款候选",
                "detail": "主商品没有返回其他规格，也没有补充链接。可以粘贴同款链接，或按关键词人工搜索。",
                "severity": "medium",
            }
        )
    if not summary["platforms"]:
        gaps.append(
            {
                "code": "no_candidate_platforms",
                "label": "没有可比较的平台",
                "detail": "候选列表为空，跨平台覆盖无法计算。",
                "severity": "medium",
            }
        )
    summary["gaps"] = gaps
    return {"candidates": candidates, "summary": summary}


def normalize_object(value: Dict[str, Any]) -> Dict[str, Any]:
    """兼容不同来源的对象字典，补齐匹配器需要的字段。"""
    obj = dict(value or {})
    obj["title"] = _clean(obj.get("title") or obj.get("name"))
    obj["brand"] = _clean(obj.get("brand"))
    obj["shop"] = _clean(obj.get("shop"))
    obj["platform"] = _clean(obj.get("platform"))
    obj["platform_id"] = _platform_id(obj)
    obj["url"] = _url(obj)
    if isinstance(obj.get("category"), str):
        obj["category"] = [part for part in re.split(r"[,/ >]+", obj["category"]) if part]
    elif not isinstance(obj.get("category"), list):
        obj["category"] = []
    return obj
