# -*- coding: utf-8 -*-
"""产品改进方向：把已验证痛点交给 LLM 产出动作建议，再用确定性规则排优先级。

LLM 只负责“做什么”，优先级由 impact / effort 计算，避免模型随口给 P0。
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from reviewagent.insights.textutil import as_list, clamp_int, normalize_text, parse_json_any, truncate

IMPROVE_PROMPT_HEADER = """你是产品经理，正在根据小红书用户的真实抱怨制定改进计划。

## 输入
下面每条痛点都有 id、概括、严重度（1-3）、提及人数与代表原句。

## 输出 JSON（不要输出其他内容）
{"improvements": [
  {
    "pain_point_id": "pp-1",
    "action": "具体改什么，动产品/包装/详情页/客服流程，一句话能执行",
    "rationale": "为什么这样改能解决该痛点，不超过 60 字",
    "effort": 2,
    "impact": 3,
    "verification": "上线后怎么验证，比如看哪项指标或哪类反馈"
  }
]}

## 硬性规则
1. pain_point_id 必须是输入里出现过的 id，不得新造。
2. effort 1=一周内能改，2=一个迭代，3=需要改供应链或模具。
3. impact 1=少数人受益，2=明显改善，3=直接决定买不买/退不退货。
4. 一条痛点可以给一条最关键的改法；不要写“加强品控”这类无法执行的话。

## 痛点
"""


def priority_for(impact: int, effort: int) -> str:
    """确定性优先级：高影响低成本先做。"""
    impact = clamp_int(impact, 1, 3, 2)
    effort = clamp_int(effort, 1, 3, 2)
    if impact >= 3 and effort <= 2:
        return "P0"
    if impact >= 3 or impact + (3 - effort) >= 4:
        return "P1"
    return "P2"


def _format_points(points: Sequence[Dict[str, Any]]) -> str:
    lines = []
    for point in points:
        quotes = " / ".join(truncate(item.get("quote"), 50) for item in (point.get("evidence") or [])[:2])
        lines.append(
            f"- {point['id']}｜{point['category']}｜严重度 {point['severity']}｜"
            f"{point['frequency']} 人提及｜{point['statement']}"
            + (f"｜原句：{quotes}" if quotes else "")
        )
    return "\n".join(lines)


def generate_improvements(
    pain_points: Sequence[Dict[str, Any]],
    llm_call,
    *,
    max_items: int = 8,
) -> Dict[str, Any]:
    """只对已验证痛点生成改进建议，并按确定性规则排序。"""
    verified = [point for point in pain_points if point.get("verified")][: max(1, max_items)]
    if not verified:
        return {"improvements": [], "rejected": [], "error": "没有已验证的痛点，无法生成改进方向"}

    prompt = IMPROVE_PROMPT_HEADER + _format_points(verified)
    try:
        raw = llm_call(prompt)
    except Exception as exc:
        return {"improvements": [], "rejected": [], "error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    parsed = parse_json_any(raw)
    by_id = {point["id"]: point for point in verified}
    improvements: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    seen = set()
    for item in as_list(parsed, "improvements"):
        pid = normalize_text(item.get("pain_point_id"))
        action = truncate(item.get("action"), 120)
        if pid not in by_id:
            rejected.append({"pain_point_id": pid, "reason": "痛点 id 不在已验证清单内"})
            continue
        if not action:
            rejected.append({"pain_point_id": pid, "reason": "改进动作为空"})
            continue
        if pid in seen:
            rejected.append({"pain_point_id": pid, "reason": "同一痛点重复建议"})
            continue
        seen.add(pid)
        effort = clamp_int(item.get("effort"), 1, 3, 2)
        impact = clamp_int(item.get("impact"), 1, 3, 2)
        point = by_id[pid]
        improvements.append({
            "pain_point_id": pid,
            "pain_statement": point["statement"],
            "category": point["category"],
            "severity": point["severity"],
            "action": action,
            "rationale": truncate(item.get("rationale"), 120),
            "effort": effort,
            "impact": impact,
            "priority": priority_for(impact, effort),
            "verification": truncate(item.get("verification"), 120),
            "evidence": point.get("evidence") or [],
        })

    order = {"P0": 0, "P1": 1, "P2": 2}
    improvements.sort(key=lambda item: (order[item["priority"]], -item["impact"], -item["severity"]))
    return {"improvements": improvements, "rejected": rejected, "error": ""}


def render_improvements_markdown(improvements: Sequence[Dict[str, Any]]) -> str:
    lines = []
    for item in improvements:
        lines.append(f"### [{item['priority']}] {item['action']}")
        lines.append(f"- 对应痛点：{item['pain_statement']}（{item['category']}，严重度 {item['severity']}）")
        lines.append(f"- 理由：{item['rationale']}")
        lines.append(f"- 成本 {item['effort']}/3，影响 {item['impact']}/3")
        lines.append(f"- 验证：{item['verification']}")
        for evidence in (item.get("evidence") or [])[:2]:
            lines.append(f"- 原句：「{evidence.get('quote')}」— {evidence.get('source_url') or '来源缺失'}")
        lines.append("")
    return "\n".join(lines)