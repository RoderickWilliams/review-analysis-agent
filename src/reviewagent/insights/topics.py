# -*- coding: utf-8 -*-
"""小红书宣传选题：从已验证痛点生成结构化选题模板。

选题是“可复用的骨架 + 本次痛点素材”，标题/封面/正文由模板确定性拼装，
风险词扫描后给出提示；不直接生成成品文案，避免模型编造功效。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from reviewagent.insights.risk_words import scan_risk_words
from reviewagent.insights.textutil import normalize_text, truncate

TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "test",
        "name": "真人实测",
        "angle": "用具体使用场景验证一个卖点，给出可复现的结论",
        "title_patterns": [
            "{audience}实测：{topic}，{n}天真实感受",
            "{topic}值不值？{audience}{n}次后说结论",
            "{audience}实测{topic}，避雷版",
        ],
        "cover": ["{audience}实测", "{topic}"],
        "sections": ["使用场景：在哪、怎么用、用了多久", "真实变化：可观察的细节与对比", "优点和局限：各说一条，别只讲好", "适合谁：什么情况别买"],
        "tags": ["实测", "真实测评", "使用体验"],
    },
    {
        "id": "avoid",
        "name": "避坑清单",
        "angle": "把用户踩过的坑整理成可核对的清单，先给判断再给理由",
        "title_patterns": [
            "买{topic}前，{audience}先看这{n}个坑",
            "{topic}踩坑实录：{audience}忽略了{n}点",
            "{audience}别乱买{topic}，先看避坑清单",
        ],
        "cover": ["{topic}避坑", "{n}个细节"],
        "sections": ["坑一：症状与原句", "坑二：为什么会被忽略", "怎么核对：下单前可查的证据", "已经踩了怎么办"],
        "tags": ["避坑", "选购指南", "踩雷"],
    },
    {
        "id": "howto",
        "name": "教程攻略",
        "angle": "把一个具体做法拆成可照做的步骤，解决一个高频困扰",
        "title_patterns": [
            "{audience}必看：{topic}的{n}步做法",
            "{topic}怎么做不翻车？{audience}版步骤",
            "{audience}搞定{topic}，照做{n}步",
        ],
        "cover": ["{topic}教程", "{n}步搞定"],
        "sections": ["准备：需要什么、不需要什么", "步骤：按顺序做，每步给判断标准", "常见错法：为什么照做还是失败", "什么时候该停：边界与替代方案"],
        "tags": ["教程", "方法", "步骤"],
    },
    {
        "id": "compare",
        "name": "对比选购",
        "angle": "在同一预算或同一需求下横向比较，给出取舍条件",
        "title_patterns": [
            "{topic}怎么选？{audience}看{n}个标准",
            "同价位{topic}对比，{audience}选哪个",
            "{audience}选{topic}，只看{n}项",
        ],
        "cover": ["{topic}怎么选", "{n}项对比"],
        "sections": ["先定需求：什么场景必须满足", "对比维度：参数之外的体验差异", "取舍：贵的那部分值不值", "结论：什么人选哪个"],
        "tags": ["选购", "对比", "怎么选"],
    },
    {
        "id": "persona",
        "name": "人群定制",
        "angle": "只对一个具体人群说话，用他们的场景和语言",
        "title_patterns": [
            "写给{audience}：{topic}建议",
            "{audience}的{topic}，哪里不一样",
            "{audience}别跟风买{topic}",
        ],
        "cover": ["写给{audience}", "{topic}"],
        "sections": ["你的场景：和大众用法差在哪", "你的限制：预算/时间/空间", "针对你的做法：三步调整", "哪些通用建议对你不适用"],
        "tags": ["人群", "定制", "场景"],
    },
    {
        "id": "checklist",
        "name": "清单盘点",
        "angle": "把一个决策拆成可勾选的清单，降低收藏门槛",
        "title_patterns": [
            "{topic}自查清单，{audience}存下来",
            "{audience}买{topic}前，先过{n}条",
            "一张{topic}清单，{audience}少花冤枉钱",
        ],
        "cover": ["{topic}清单", "存下慢慢看"],
        "sections": ["买前：三个必须确认的信息", "买时：两个容易被绕过的细节", "买后：出现什么情况要退", "回看：下次怎么更快判断"],
        "tags": ["清单", "收藏", "自查"],
    },
]

_AUDIENCE_LEXICON = {
    "学生党": ["学生", "宿舍", "上课", "校园", "考试"],
    "通勤上班族": ["通勤", "上班", "地铁", "办公室", "加班"],
    "宝妈": ["宝宝", "孩子", "宝妈", "孕期", "带娃"],
    "敏感肌": ["敏感肌", "泛红", "过敏", "刺痛"],
    "油皮": ["油皮", "出油", "混油", "闷痘"],
    "干皮": ["干皮", "起皮", "卡粉", "紧绷"],
    "健身人群": ["健身", "运动", "跑步", "撸铁", "出汗"],
    "租房党": ["租房", "出租屋", "搬家", "小户型"],
    "新手": ["新手", "第一次", "入门", "小白"],
    "熬夜党": ["熬夜", "晚睡", "黑眼圈", "作息"],
}


def detect_audience(texts: Iterable[str]) -> str:
    """按人群词命中次数选一个最具体的人群；都不中时用“目标用户”。"""
    blob = " ".join(normalize_text(text) for text in texts)
    best, best_score = "目标用户", 0
    for audience, keywords in _AUDIENCE_LEXICON.items():
        score = sum(blob.count(word) for word in keywords)
        if score > best_score:
            best, best_score = audience, score
    return best


_AUDIENCE_WORDS = {word for keywords in _AUDIENCE_LEXICON.values() for word in keywords}
_LEAD_NOISE = ("用着", "用了", "用完", "用后", "买来", "入手", "感觉", "觉得", "就是", "有点", "比较", "非常", "太", "很", "就", "才")


def _topic_from_point(point: Dict[str, Any]) -> str:
    """从痛点概括里抽出适合放进标题的短名词，去掉人群词与口头前缀。"""
    statement = normalize_text(point.get("statement"))
    statement = statement.split("，")[-1]
    statement = re.sub(r"^用[^，。]{0,6}?(天|次|周|个月|月)", "", statement)
    for word in _AUDIENCE_WORDS:
        if statement.startswith(word):
            statement = statement[len(word):]
    for _ in range(3):
        for prefix in _LEAD_NOISE:
            if statement.startswith(prefix) and len(statement) - len(prefix) >= 2:
                statement = statement[len(prefix):]
    for suffix in ("的问题", "问题", "的情况"):
        if statement.endswith(suffix) and len(statement) > len(suffix) + 2:
            statement = statement[: -len(suffix)]
    return truncate(statement or point.get("category") or "产品体验", 12)


def _fit(value: str, limit: int) -> str:
    text = normalize_text(value)
    return text if len(text) <= limit else text[:limit]


def build_topics(
    pain_points: Sequence[Dict[str, Any]],
    *,
    limit: int = 10,
    templates: Optional[Sequence[Dict[str, Any]]] = None,
    audience: Optional[str] = None,
    texts: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """按排名把已验证痛点轮流套进模板，生成可直接改写的小红书选题。"""
    pool = list(templates or TEMPLATES)
    verified = [point for point in pain_points if point.get("verified")]
    audience = audience or detect_audience(texts or [point.get("statement", "") for point in verified])
    topics: List[Dict[str, Any]] = []
    for index, point in enumerate(verified[: max(1, limit)]):
        template = pool[index % len(pool)]
        topic = _topic_from_point(point)
        n = max(3, min(int(point.get("frequency") or 3), 7))
        context = {"audience": audience, "topic": topic, "n": n}
        titles = [_fit(pattern.format(**context), 20) for pattern in template["title_patterns"]]
        cover = [_fit(line.format(**context), 12) for line in template["cover"]]
        sections = [f"## {heading}" for heading in template["sections"]]
        evidence = (point.get("evidence") or [{}])[0]
        tags = []
        for tag in list(template["tags"]) + [point.get("category", ""), audience]:
            tag = normalize_text(tag)
            if tag and tag not in tags:
                tags.append(tag)
        risk_text = " ".join(titles + cover + tags)
        risk = scan_risk_words(risk_text)
        topics.append({
            "id": f"tp-{index + 1}",
            "template_id": template["id"],
            "template_name": template["name"],
            "angle": template["angle"],
            "pain_point_id": point["id"],
            "pain_statement": point["statement"],
            "audience": audience,
            "titles": titles,
            "cover": cover,
            "sections": sections,
            "tags": tags[:10],
            "evidence_quote": evidence.get("quote", ""),
            "source_url": evidence.get("source_url", ""),
            "risk": risk,
        })
    return {
        "audience": audience,
        "topics": topics,
        "risk_hits": sorted({word for topic in topics for word in topic["risk"]["words"]}),
        "summary": f"根据 {len(verified)} 条已验证痛点生成 {len(topics)} 个选题，覆盖 {len({t['template_id'] for t in topics})} 种模板",
    }