# -*- coding: utf-8 -*-
"""小红书洞察引擎：痛点提取、改进方向、宣传选题、内容生产包。

所有模块只做纯计算，LLM 通过可注入的 `llm_call(prompt) -> str` 调用，
便于离线测试与替换模型。
"""
from __future__ import annotations

from reviewagent.insights.pain_points import (  # noqa: F401
    analyze_pain_points,
    cluster_points,
    extract_pain_points,
    rank_points,
)
from reviewagent.insights.improvements import generate_improvements, priority_for  # noqa: F401
from reviewagent.insights.topics import build_topics, detect_audience, TEMPLATES  # noqa: F401
from reviewagent.insights.content_kit import build_content_kit  # noqa: F401
from reviewagent.insights.risk_words import scan_risk_words  # noqa: F401

__all__ = [
    "analyze_pain_points",
    "cluster_points",
    "extract_pain_points",
    "rank_points",
    "generate_improvements",
    "priority_for",
    "build_topics",
    "detect_audience",
    "scan_risk_words",
    "build_content_kit",
    "TEMPLATES",
]
