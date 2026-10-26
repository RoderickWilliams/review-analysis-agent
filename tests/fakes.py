# -*- coding: utf-8 -*-
"""测试替身：不联网的 LLM 客户端与流水线分析器。"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional


SENTIMENT_RESULT: Dict[str, Any] = {
    "sentiment_category": "positive_authentic",
    "sentiment_label": "真实好评",
    "confidence": 0.92,
    "is_sarcastic": False,
    "real_sentiment": "positive",
    "key_phrases": ["续航给力", "充电快"],
    "reasoning": "具体描述使用体验，语气自然。",
}

VALIDITY_RESULT: Dict[str, Any] = {
    "is_valid": True,
    "validity_category": "authentic",
    "validity_label": "真实可信",
    "specificity_score": 0.85,
    "authenticity_score": 0.9,
    "red_flags": [],
    "reasoning": "包含具体细节。",
}

FINAL_RESULT: Dict[str, Any] = {
    "final_sentiment": "positive",
    "final_validity": "authentic",
    "trust_score": 88,
    "risk_level": "low",
    "cross_validation": {"consistent": True, "note": "情绪与有效性一致"},
    "summary": "真实好评。",
    "recommendation": "可作为有效反馈。",
}

BATCH_REPORT: Dict[str, Any] = {
    "authentic_positive_rate": 0.6,
    "sentiment_distribution": {"positive": 3, "negative": 1, "neutral": 1},
    "suspicious_review_count": 0,
    "key_findings": ["续航是主要好评点", "售后问题集中在客服响应"],
    "top_complaints": ["地铁断流", "客服不理人"],
    "fake_review_risk": "low",
    "recommendations": ["补强信号表现说明", "公示售后响应时效"],
}


def response_for_prompt(prompt: str) -> Dict[str, Any]:
    if "情绪分类体系" in prompt:
        return SENTIMENT_RESULT
    if "有效性分类" in prompt:
        return VALIDITY_RESULT
    if "交叉验证规则" in prompt:
        return FINAL_RESULT
    if "产品口碑分析报告" in prompt:
        return BATCH_REPORT
    return {"note": "unrecognized prompt"}


class _FakeCompletions:
    def __init__(self, parent: "FakeLLMClient") -> None:
        self._parent = parent

    def create(self, **kwargs: Any):
        self._parent.calls.append(kwargs)
        if self._parent.error is not None:
            raise self._parent.error
        prompt = kwargs["messages"][-1]["content"]
        payload = response_for_prompt(prompt)
        text = json.dumps(payload, ensure_ascii=False)
        if self._parent.wrap_in_fence:
            text = "```json\n" + text + "\n```"
        message = SimpleNamespace(content=text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeLLMClient:
    """模拟 openai.OpenAI：只需要 chat.completions.create。"""

    def __init__(self, error: Optional[Exception] = None, wrap_in_fence: bool = False) -> None:
        self.error = error
        self.wrap_in_fence = wrap_in_fence
        self.calls: List[Dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=_FakeCompletions(self))


def fake_result(review: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "review_text": review.get("review_text", ""),
        "rating": review.get("rating", 0),
        "platform": review.get("platform", "未知"),
        "sentiment_analysis": dict(SENTIMENT_RESULT),
        "validity_analysis": dict(VALIDITY_RESULT),
        "final_analysis": dict(FINAL_RESULT),
        "timestamp": "2026-10-26T12:00:00",
    }


class FakeAgent:
    """模拟 ReviewAnalysisAgent，供 pipeline 测试注入。"""

    def __init__(self) -> None:
        self.batch_calls: List[Dict[str, Any]] = []
        self.report_calls: List[Dict[str, Any]] = []

    def batch_analyze(self, reviews: List[Dict], product_name: str = "") -> List[Dict]:
        self.batch_calls.append({"reviews": reviews, "product_name": product_name})
        return [fake_result(r) for r in reviews]

    def generate_report(self, batch_results: List[Dict], product_name: str = "") -> Dict:
        self.report_calls.append({"results": batch_results, "product_name": product_name})
        report = dict(BATCH_REPORT)
        report["total_reviews"] = len(batch_results)
        return report
