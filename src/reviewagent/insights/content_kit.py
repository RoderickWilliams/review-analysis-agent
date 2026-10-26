# -*- coding: utf-8 -*-
"""内容生产包：把评论洞察转成可执行的电商内容 brief、素材索引与分层卡片。

输入只使用已经过证据校验的痛点、选题与采集到的笔记元数据，输出的是
“给设计和运营执行的骨架”，不是成品文案，也不生成图片：

- brief：主图 3 个卖点方向、详情页 8 段、15 秒短视频分镜、英文本地化清单；
- material_index：笔记图片元数据（宽高、比例、来源、互动量），供选封面；
- style_card：只从标题/标签/类型做文本风格统计，明确不伪造色板与字体；
- layered_cards：主图/详情页/封面的图层与安全区，交给设计或生图工具；
- claim_guard：可引用的用户原话、必须由产品方确认的参数、禁用绝对化表述。

所有卖点都绑定“用户问题”，而不是替产品宣称功效。评论只能证明有人遇到
这个问题，不能证明产品能解决它；这一点写进 claim_guard 并在报告里显示。
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from typing import Any, Dict, List, Sequence

from reviewagent.insights.risk_words import DEFAULT_WORDS, scan_risk_words
from reviewagent.insights.textutil import normalize_text, truncate

LANGUAGES = [
    {"code": "en", "name": "English"},
]

DETAIL_TITLES = [
    "买家最在意的那个问题",
    "谁在用、什么时候用",
    "卖点一：先回应一个具体场景",
    "卖点二：把可核对的部分拍清楚",
    "卖点三：给一个不适用边界",
    "结构与材质细节",
    "对比与避坑",
    "售后与下一步",
]

FORBIDDEN_EXTRA = [
    "治疗", "治愈", "防癌", "降血压", "降血糖", "消炎", "杀菌",
    "百分百", "全网第一", "销量第一", "国家级认证", "权威认证",
]


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clip(value: Any, limit: int) -> str:
    return truncate(normalize_text(value), limit)


def _evidence(point: Dict[str, Any], limit: int = 2) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in (point.get("evidence") or [])[: max(1, limit)]:
        if not isinstance(raw, dict):
            continue
        items.append({
            "review_id": str(raw.get("review_id") or ""),
            "quote": _clip(raw.get("quote"), 120),
            "source_url": str(raw.get("source_url") or ""),
            "note_id": str(raw.get("note_id") or ""),
            "like": _int(raw.get("like")),
        })
    return items


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _benefit_angle(point: Dict[str, Any]) -> str:
    category = normalize_text(point.get("category"))
    statement = _clip(point.get("statement"), 30)
    table = {
        "使用体验": f"把「{statement}」还原成一个真实使用动作，主图先让用户认出自己的场景",
        "效果": f"用可观察的使用结果回应「{statement}」，不写疗效、不写前后对比",
        "质量": f"用结构、接缝、材质近景回应「{statement}」，参数必须由产品方提供",
        "价格": f"解释价格构成与耐用性，回应「{statement}」，不写绝对低价",
        "人群不适配": f"明确写清适用与不适用人群，回应「{statement}」",
        "信息不符": f"把详情页容易被误解的参数前置，回应「{statement}」",
        "服务": f"把售后流程写清楚，回应「{statement}」，不承诺没有依据的时效",
        "物流": f"把发货与包装信息写清楚，回应「{statement}」，不承诺绝对时效",
        "包装": f"用包装细节与开箱步骤回应「{statement}」",
    }
    return table.get(category, f"用一个真实场景回应「{statement}」，不替产品下结论")


def _selling_points(
    product_name: str,
    audience: str,
    pain_points: Sequence[Dict[str, Any]],
    limit: int = 3,
) -> List[Dict[str, Any]]:
    verified = [point for point in pain_points if point.get("verified")]
    if not verified:
        return []
    picked: List[Dict[str, Any]] = []
    seen_categories = set()
    for point in verified:
        category = normalize_text(point.get("category")) or "其他"
        if category in seen_categories:
            continue
        seen_categories.add(category)
        picked.append(point)
        if len(picked) >= limit:
            break
    for point in verified:
        if len(picked) >= limit:
            break
        if point not in picked:
            picked.append(point)

    result: List[Dict[str, Any]] = []
    for index, point in enumerate(picked, start=1):
        evidence = _evidence(point)
        statement = _clip(point.get("statement"), 30)
        result.append({
            "id": f"sp-{index}",
            "pain_point_id": point.get("id") or f"pp-{index}",
            "pain_statement": statement,
            "category": normalize_text(point.get("category")) or "其他",
            "severity": _safe_int(point.get("severity"), 2),
            "angle": _benefit_angle(point),
            "headline_direction": f"{audience}先看：{statement}怎么处理",
            "proof_quote": evidence[0]["quote"] if evidence else "",
            "evidence": evidence,
            "do_not_claim": [
                "不要写『根治』『永久』『100% 改善』",
                "不要把这条评论写成产品功效证明",
                "没有产品参数时，不要补写材质、认证或实验数据",
            ],
        })
    return result


def _hero_image(
    product_name: str,
    audience: str,
    selling_points: Sequence[Dict[str, Any]],
    top_pain: str,
) -> Dict[str, Any]:
    return {
        "goal": "让目标人群在第一眼确认“这条内容写的是我的场景”，再给一个可核对的产品细节",
        "ratios": [
            {"ratio": "1:1", "size": "1080x1080", "use": "淘宝/京东主图"},
            {"ratio": "3:4", "size": "1080x1440", "use": "小红书封面与详情页首屏"},
            {"ratio": "16:9", "size": "1920x1080", "use": "详情页头图与视频封面"},
        ],
        "scene_hint": f"把「{_clip(top_pain, 26)}」放进一个真实使用动作；没有拍过的场景不要补拍",
        "headline_directions": [
            f"{audience}先看：{_clip(top_pain, 20)}怎么处理",
            f"{product_name}的选择题：先核对这 {max(1, len(selling_points))} 个细节",
            f"别只看主图：{_clip(top_pain, 20)}的人还要看这一段",
        ],
        "selling_point_ids": [item["id"] for item in selling_points],
        "status": "待拍摄/待设计",
        "note": "主图文字只写场景与可核对信息；产品功效、参数、认证必须由产品方确认。",
    }


def _detail_page(
    product_name: str,
    audience: str,
    selling_points: Sequence[Dict[str, Any]],
    top_pain: str,
    top_quote: str,
) -> Dict[str, Any]:
    sections: List[Dict[str, Any]] = []
    for index, title in enumerate(DETAIL_TITLES, start=1):
        section: Dict[str, Any] = {
            "no": index,
            "title": title,
            "purpose": "",
            "copy_hint": "",
            "evidence": [],
            "must_confirm": False,
        }
        if index == 1:
            section["purpose"] = "用买家原话开场，先让读者确认问题，不急着介绍产品"
            section["copy_hint"] = (
                f"引用「{_clip(top_quote, 80)}」，再补一句这个场景的边界"
                if top_quote else "用真实用户原话开场；没有可核对的原话就留空，不要编造"
            )
            section["evidence"] = [{"quote": _clip(top_quote, 120)}] if top_quote else []
        elif index == 2:
            section["purpose"] = "写清谁在什么场景下用，以及什么情况不适合"
            section["copy_hint"] = f"人群写成「{audience}」，场景写具体动作；不适用人群单独列一条"
            section["must_confirm"] = True
        elif 3 <= index <= 5:
            point = selling_points[index - 3] if index - 3 < len(selling_points) else {}
            section["purpose"] = "把一条用户问题转成一个可拍摄的卖点段落"
            if point:
                section["copy_hint"] = point.get("angle", "")
                section["evidence"] = point.get("evidence") or []
                section["pain_point_id"] = point.get("pain_point_id", "")
            else:
                section["copy_hint"] = "可用卖点不足 3 条：这一段留空，等产品方补参数或补拍细节"
        elif index == 6:
            section["purpose"] = "用近景拍清材质、结构、尺寸与做工，不靠形容词"
            section["copy_hint"] = "拍接缝、拉链、标签、尺寸参照物；没有参数就写“以实物为准”，不编数字"
            section["must_confirm"] = True
        elif index == 7:
            section["purpose"] = "主动写清不适用场景与对比边界，降低误解和退货"
            section["copy_hint"] = f"回应「{_clip(top_pain or '真实使用场景', 26)}」，写一条不适合的人；不贬低竞品"
        else:
            section["purpose"] = "给售后、使用说明与下一步动作，不制造虚假紧迫感"
            section["copy_hint"] = "写清退换/保修/使用步骤；没有政策就留空，不写“最后一天”"
            section["must_confirm"] = True
        sections.append(section)
    return {
        "section_count": len(sections),
        "sections": sections,
        "status": "8 段骨架已生成，产品参数与售后政策待补",
    }


def _short_video(
    product_name: str,
    audience: str,
    selling_points: Sequence[Dict[str, Any]],
    top_pain: str,
    top_quote: str,
) -> Dict[str, Any]:
    first = selling_points[0] if selling_points else {}
    beats = [
        {
            "start": 0,
            "end": 3,
            "shot": "近景：手部或使用中的产品，画面留出字幕位",
            "voiceover": (
                f"「{_clip(top_quote, 70)}」——先别急着下单。"
                if top_quote else "先别急着下单，先看这个细节。"
            ),
            "on_screen": "先看这个细节",
            "evidence": [{"quote": _clip(top_quote, 120)}] if top_quote else [],
        },
        {
            "start": 3,
            "end": 6,
            "shot": "中景：目标人群的真实使用动作，不摆拍没用过的场景",
            "voiceover": f"如果你也是{audience}，这个场景大概率不陌生。",
            "on_screen": f"写给{audience}",
            "evidence": [],
        },
        {
            "start": 6,
            "end": 10,
            "shot": "产品近景 + 一个可核对的结构/细节",
            "voiceover": f"这条内容要回答的是：{_clip(first.get('pain_statement') or top_pain or '这个产品到底适不适合你', 30)}。",
            "on_screen": "把细节拍清楚",
            "evidence": first.get("evidence") or [],
        },
        {
            "start": 10,
            "end": 13,
            "shot": "特写：接缝/材质/标签/尺寸参照，避免只拍氛围",
            "voiceover": "参数、材质、适用人群，能核对的部分放在这一段。",
            "on_screen": "能核对，再决定",
            "evidence": [],
        },
        {
            "start": 13,
            "end": 15,
            "shot": "产品全貌 + 详情页引导，不写倒计时",
            "voiceover": "想看完整细节，去详情页；先收藏，别急着买。",
            "on_screen": "详情页看完整参数",
            "evidence": [],
        },
    ]
    return {
        "duration_seconds": 15,
        "beats": beats,
        "status": "分镜骨架，需按真实产品补拍",
        "compliance": [
            "不使用前后对比图制造效果承诺",
            "不写绝对化用语、限时倒计时或虚假库存",
            "用户原话只作为问题证据，不作为产品功效证明",
        ],
    }


def _multilingual(product_name: str, audience: str, top_tags: Sequence[str]) -> Dict[str, Any]:
    glossary = [
        {"term": product_name, "translation": "", "note": "品牌名/型号不译，待确认官方译名"},
        {"term": audience, "translation": "", "note": "人群词按目标市场改写，不直译"},
    ]
    for tag in top_tags[:3]:
        glossary.append({"term": tag, "translation": "", "note": "类目词，优先用平台既有译法"})
    return {
        "status": "待翻译（本次只给清单，不产出译文）",
        "languages": [
            {
                "code": item["code"],
                "name": item["name"],
                "status": "待翻译",
                "fields": ["标题", "3 个卖点", "详情页 8 段", "15 秒字幕", "参数与单位", "售后政策"],
            }
            for item in LANGUAGES
        ],
        "glossary": glossary,
        "checklist": [
            "先锁定品牌名、型号、单位与认证的官方译法，再翻译正文",
            "英文文案找英语母语者复核；以后增加语种时逐语种单独复核，不用一份译文套多个市场",
            "功效与绝对化表述按目标市场法规重写，不逐字直译",
            "尺寸、重量、容量保留公制，必要时补当地常用单位",
            "售后、保修、退换规则按当地政策重写，不直接沿用中文",
            "翻译完成后回填 glossary，保证同一产品在不同页面用词一致",
        ],
    }


def _note_engagement(note: Dict[str, Any]) -> int:
    stats = note.get("stats") or {}
    return _int(stats.get("liked")) + 2 * _int(stats.get("collected")) + 3 * _int(stats.get("comment"))


def _ratio_text(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return ""
    return f"{round(width / height, 3):g}"


def _orientation(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "未知"
    if width > height * 1.08:
        return "横图"
    if height > width * 1.08:
        return "竖图"
    return "方图"


def _material_index(notes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    notes_with_images = 0
    for note in notes:
        images = note.get("images") or []
        if not isinstance(images, list) or not images:
            continue
        notes_with_images += 1
        engagement = _note_engagement(note)
        for pos, image in enumerate(images):
            if not isinstance(image, dict):
                continue
            src = str(image.get("src") or image.get("url") or "").strip()
            width = _safe_int(image.get("width"))
            height = _safe_int(image.get("height"))
            index = _safe_int(image.get("index"), pos)
            entries.append({
                "id": f"img-{note.get('note_id') or 'note'}-{index}",
                "note_id": str(note.get("note_id") or ""),
                "note_title": _clip(note.get("title"), 40),
                "source_url": str(note.get("source_url") or ""),
                "src": src,
                "index": index,
                "width": width,
                "height": height,
                "ratio": _ratio_text(width, height),
                "orientation": _orientation(width, height),
                "note_engagement": engagement,
                "note_stats": dict(note.get("stats") or {}),
            })
    entries.sort(key=lambda item: (-int(item.get("note_engagement") or 0), item.get("note_id", ""), item.get("index", 0)))
    total = len(entries)
    low_confidence = notes_with_images < 3
    return {
        "total_images": total,
        "notes_with_images": notes_with_images,
        "entries": entries[:40],
        "cover_candidates": entries[:3],
        "confidence": "low" if low_confidence else "ok",
        "low_confidence": low_confidence,
        "note": "只记录采集端返回的图片元数据，未下载、未识别图片内容；src 是远程地址，可能过期。",
    }


def _style_card(notes: Sequence[Dict[str, Any]], audience: str) -> Dict[str, Any]:
    tags: Counter = Counter()
    types: Counter = Counter()
    title_lengths: List[int] = []
    digit_titles = 0
    question_titles = 0
    bracket_titles = 0
    for note in notes:
        for tag in note.get("tags") or []:
            tag = normalize_text(tag).lstrip("#")
            if tag:
                tags[tag] += 1
        note_type = normalize_text(note.get("type")) or "未知"
        types[note_type] += 1
        title = normalize_text(note.get("title"))
        if title:
            title_lengths.append(len(title))
            if re.search(r"\d", title):
                digit_titles += 1
            if "?" in title or "？" in title:
                question_titles += 1
            if any(mark in title for mark in ("【", "】", "[", "]", "｜", "|")):
                bracket_titles += 1
    top_tags = [{"tag": tag, "count": total} for tag, total in tags.most_common(8)]
    return {
        "status": "text_signals_only",
        "audience": audience,
        "note_count": len(notes),
        "low_confidence": len(notes) < 3,
        "observed": {
            "top_tags": top_tags,
            "note_types": [{"type": key, "count": value} for key, value in types.most_common()],
            "median_title_length": round(statistics.median(title_lengths), 1) if title_lengths else 0,
            "title_traits": {
                "含数字": digit_titles,
                "含问句": question_titles,
                "含括注/分隔": bracket_titles,
            },
        },
        "recommendations": {
            "canvas": "小红书封面 1080x1440（3:4）；电商主图 1080x1080（1:1）",
            "layout": "产品占画面 45–60%，主标题最多 2 行，底部留一条用户原话或参数；先保证手机缩略图能读清",
            "palette": None,
            "typography": None,
            "basis": "通用版式建议，不是从样本图片提取；样本只有文字与图片元数据",
        },
        "limitations": [
            "未下载图片、未调用视觉模型，色板、字体、真实版式没有从样本提取",
            f"样本笔记 {len(notes)} 篇，少于 3 篇时风格判断按低置信处理",
            "标题结构只是文本统计，不代表平台算法偏好或爆款因果",
        ],
    }


def _layers(canvas: str) -> List[Dict[str, Any]]:
    if canvas == "cover":
        product_box = "x 18% / y 26% / w 64% / h 54%"
        headline_box = "x 8% / y 8% / w 84% / h 18%"
    elif canvas == "detail":
        product_box = "x 52% / y 16% / w 42% / h 68%"
        headline_box = "x 6% / y 14% / w 42% / h 20%"
    else:
        product_box = "x 18% / y 20% / w 64% / h 60%"
        headline_box = "x 8% / y 8% / w 84% / h 16%"
    return [
        {"id": "background", "type": "image", "z": 0, "content": "真实使用场景或品牌纯色底", "safe_area": "全画布"},
        {"id": "product", "type": "image", "z": 10, "content": "产品抠图", "box": product_box},
        {"id": "headline", "type": "text", "z": 20, "content": "主标题：人群 + 场景（2 行内）", "box": headline_box},
        {"id": "subhead", "type": "text", "z": 30, "content": "副标题：痛点 + 可核对的动作", "box": "主标题下方，最多 2 行"},
        {"id": "evidence", "type": "text", "z": 40, "content": "用户原话短句（发布前核对原文）", "box": "底部安全区内"},
        {"id": "logo", "type": "image", "z": 50, "content": "品牌 logo（如有）", "box": "左上或右下，避开平台角标"},
    ]


def _layered_cards() -> Dict[str, Any]:
    cards = [
        {"id": "main", "name": "电商主图", "canvas": {"width": 1080, "height": 1080, "ratio": "1:1"}, "layers": _layers("main")},
        {"id": "detail", "name": "详情页头图", "canvas": {"width": 1920, "height": 1080, "ratio": "16:9"}, "layers": _layers("detail")},
        {"id": "cover", "name": "小红书封面", "canvas": {"width": 1080, "height": 1440, "ratio": "3:4"}, "layers": _layers("cover")},
    ]
    return {
        "status": "schema_only_no_render",
        "cards": cards,
        "note": "只给图层、安全区与占位文案，不生成图片；由设计或生图工具按品牌规范填充。",
    }


def _claim_guard(pain_points: Sequence[Dict[str, Any]], copy_blob: str) -> Dict[str, Any]:
    verified = [point for point in pain_points if point.get("verified")]
    allowed = []
    seen = set()
    for point in verified:
        for raw in (point.get("evidence") or [])[:2]:
            quote = _clip(raw.get("quote"), 120)
            key = normalize_text(quote)
            if not quote or key in seen:
                continue
            seen.add(key)
            allowed.append({
                "claim": f"用户原话：「{quote}」",
                "scope": "只能证明该用户遇到了这个问题，不能证明产品功效",
                "source_url": str(raw.get("source_url") or ""),
            })
    forbidden = []
    for word in list(DEFAULT_WORDS) + FORBIDDEN_EXTRA:
        word = normalize_text(word)
        if word and word not in forbidden:
            forbidden.append(word)
    risk = scan_risk_words(copy_blob, forbidden)
    return {
        "allowed_evidence_claims": allowed[:8],
        "needs_product_confirmation": [
            "3 个卖点对应的材质、参数、认证与实测数据",
            "详情页第 6 段的材质、结构与尺寸",
            "售后、保修、退换政策与发货时效",
            "英文译文与目标市场法规复核",
        ],
        "forbidden_terms": forbidden,
        "risk_hits": risk.get("words") or [],
        "risk_level": risk.get("level") or "低",
        "notes": [
            "评论只能证明用户问题，不能证明产品能解决；卖点必须由产品方确认",
            "不写绝对化、医疗、永久、100% 等表述；不编造销量、排名、认证",
            "用户原话要保留出处；裁剪引语时不能改变原意",
        ],
    }


def build_content_kit(
    product_name: str,
    *,
    notes: Sequence[Dict[str, Any]],
    pain_points: Sequence[Dict[str, Any]],
    improvements: Sequence[Dict[str, Any]] = (),
    topics: Sequence[Dict[str, Any]] = (),
    audience: str = "",
    max_selling_points: int = 3,
) -> Dict[str, Any]:
    """把已验证痛点与采集元数据拼成内容生产包；不调用模型、不生成图片。"""
    notes = list(notes or [])
    pains = list(pain_points or [])
    verified = [point for point in pains if point.get("verified")]
    audience = normalize_text(audience) or "目标用户"
    top = verified[0] if verified else {}
    top_pain = _clip(top.get("statement"), 30)
    top_quote = ""
    evidence = _evidence(top, 1) if top else []
    if evidence:
        top_quote = evidence[0]["quote"]

    selling_points = _selling_points(product_name, audience, pains, limit=max(1, max_selling_points))
    style = _style_card(notes, audience)
    top_tags = [item["tag"] for item in style.get("observed", {}).get("top_tags", [])]
    scene = top_pain or "真实使用场景"
    brief = {
        "status": "ready" if verified else "insufficient_evidence",
        "selling_points": selling_points,
        "hero_image": _hero_image(product_name, audience, selling_points, scene),
        "detail_page": _detail_page(product_name, audience, selling_points, scene, top_quote),
        "short_video": _short_video(product_name, audience, selling_points, scene, top_quote),
        "multilingual": _multilingual(product_name, audience, top_tags),
    }
    material = _material_index(notes)
    layered = _layered_cards()

    copy_parts = []
    copy_parts.extend(brief["hero_image"].get("headline_directions") or [])
    for point in selling_points:
        copy_parts.append(point.get("headline_direction", ""))
    copy_parts.extend(beat.get("on_screen", "") for beat in brief["short_video"].get("beats") or [])
    guard = _claim_guard(pains, " ".join(part for part in copy_parts if part))

    warnings: List[str] = []
    if not verified:
        warnings.append("没有已验证痛点：内容包只给骨架，不生成卖点，也不编造用户原话")
    if not material.get("total_images"):
        warnings.append("采集结果没有图片元数据：素材索引为空，封面只能人工选")
    if style.get("low_confidence"):
        warnings.append("样本少于 3 篇：风格卡按低置信处理，不要当成平台规律")
    if guard.get("risk_hits"):
        warnings.append("内容草稿命中风险词：" + "、".join(guard["risk_hits"][:5]))
    warnings.append("产品参数、认证、售后政策未提供：详情页第 6/8 段必须人工补，不能由评论推断")
    warnings.append("未接入视觉模型：色板、字体、真实版式没有从图片提取")

    status = "ready" if verified else "insufficient_evidence"
    summary = (
        f"内容生产包：{len(selling_points)} 个卖点方向、"
        f"{brief['detail_page']['section_count']} 段详情、"
        f"{len(brief['short_video']['beats'])} 个分镜、"
        f"{len(brief['multilingual']['languages'])} 份英文清单、"
        f"{material.get('total_images', 0)} 张素材元数据"
    )
    return {
        "version": 1,
        "status": status,
        "product_name": product_name,
        "audience": audience,
        "source": {
            "notes": len(notes),
            "verified_pains": len(verified),
            "improvements": len(list(improvements or [])),
            "topics": len(list(topics or [])),
        },
        "brief": brief,
        "material_index": material,
        "style_card": style,
        "layered_cards": layered,
        "claim_guard": guard,
        "warnings": warnings,
        "summary": summary,
    }
