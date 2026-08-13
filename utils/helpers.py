# -*- coding: utf-8 -*-
"""
通用工具函数模块
====================
提供 JSON 解析、徽章渲染、文本截断、可信度颜色计算、
CSV 导入导出、时间戳生成等通用工具函数。

所有函数均经过健壮性设计，能优雅处理异常输入。
"""

import csv
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

# ─────────────────────────────────────────────
# 模块日志器
# ─────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 常量定义
# ─────────────────────────────────────────────

# 评分徽章颜色映射（背景色, 前景色）
_RATING_BADGE_COLORS: Dict[int, tuple] = {
    5: ("#14532d", "#86efac"),  # 深绿底 / 浅绿字
    4: ("#1a4300", "#bef264"),  # 暗绿底 / 黄绿字
    3: ("#1c1400", "#fde68a"),  # 暗黄底 / 浅黄字
    2: ("#431407", "#fdba74"),  # 暗橙底 / 浅橙字
    1: ("#450a0a", "#fca5a5"),  # 暗红底 / 浅红字
}

# 情绪徽章颜色映射（背景色, 前景色）
_SENTIMENT_BADGE_COLORS: Dict[str, tuple] = {
    "positive": ("#14532d", "#86efac"),
    "negative": ("#450a0a", "#fca5a5"),
    "neutral":  ("#1c1917", "#d6d3d1"),
    "mixed":    ("#1c1400", "#fde68a"),
    "sarcastic": ("#450a0a", "#fca5a5"),
    "authentic_positive": ("#14532d", "#86efac"),
    "direct_negative":    ("#450a0a", "#fca5a5"),
    "objective_neutral":  ("#1c1917", "#d6d3d1"),
    "sarcasm":            ("#450a0a", "#fca5a5"),
    "backhanded_praise":  ("#431407", "#fdba74"),
    "implicit_complaint":  ("#431407", "#fdba74"),
    "high_rating_negative": ("#450a0a", "#fca5a5"),
    "low_rating_positive":  ("#1c1400", "#fde68a"),
    "extreme_neutral":     ("#1c1917", "#d6d3d1"),
}

# 可信度颜色区间（连续区间，支持浮点数）
# 0-30: 红色 | 31-50: 橙色 | 51-70: 灰色 | 71-100: 绿色
_TRUST_COLOR_RANGES = [
    (0, 30, "#ef4444"),    # 红色：高风险
    (30, 50, "#f97316"),   # 橙色：中风险
    (50, 70, "#9ca3af"),   # 灰色：一般
    (70, 100, "#22c55e"),  # 绿色：可信
]

# CSV 导出默认列名
_CSV_EXPORT_COLUMNS = [
    "review_text",
    "rating",
    "platform",
    "sentiment_label",
    "is_sarcastic",
    "confidence",
    "validity_label",
    "final_sentiment",
    "final_validity",
    "trust_score",
    "risk_level",
    "summary",
    "similar_count",
]

# CSV 加载支持的列名（按优先级排序）
_CSV_LOAD_COLUMNS = [
    "review_text",
    "rating",
    "platform",
    "product_name",
    "timestamp",
    "user_id",
]


# ═══════════════════════════════════════════════════════════════
# JSON 解析
# ═══════════════════════════════════════════════════════════════

def parse_json_safe(text: str) -> Dict[str, Any]:
    """
    从 LLM 输出中安全解析 JSON。

    依次尝试以下策略：
    1. 去除 markdown 代码块标记（```json ... ``` 或 ``` ... ```）
    2. 直接 json.loads
    3. 提取第一个 ``{`` 到最后一个 ``}``` 的子串再解析
    4. 使用正则匹配 JSON 对象

    参数:
        text: LLM 返回的原始文本

    返回:
        解析后的字典。解析失败时返回 ``{"error": "...", "raw": text}``。
    """
    if not text or not isinstance(text, str):
        return {"error": "输入为空或非字符串", "raw": str(text) if text else ""}

    cleaned = text.strip()

    # 策略1：去除 markdown 代码块标记
    # 匹配开头的 ```json 或 ```（含可能的空白）
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    # 匹配结尾的 ```
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    # 策略2：直接解析
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    # 策略3：提取第一个 { 到最后一个 } 的子串
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_substr = cleaned[first_brace:last_brace + 1]
        try:
            return json.loads(json_substr)
        except (json.JSONDecodeError, ValueError):
            pass

    # 策略4：正则匹配 JSON 对象（贪婪模式，跨行匹配）
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            pass

    # 所有策略均失败
    logger.warning("JSON 解析失败，原始文本: %s", cleaned[:200])
    return {"error": "JSON 解析失败", "raw": cleaned[:500]}


# ═══════════════════════════════════════════════════════════════
# 徽章渲染
# ═══════════════════════════════════════════════════════════════

def format_rating_badge(rating: Union[int, float, str]) -> str:
    """
    根据评分返回彩色徽章 HTML。

    评分与颜色映射：
        5 星 → 绿色
        4 星 → 黄绿色
        3 星 → 黄色
        2 星 → 橙色
        1 星 → 红色

    参数:
        rating: 用户评分（1-5），支持整数、浮点数或字符串

    返回:
        HTML ``<span>`` 标签字符串，包含内联样式
    """
    try:
        rating_int = int(float(rating))
    except (ValueError, TypeError):
        rating_int = 0

    # 限制在 1-5 范围
    rating_int = max(1, min(5, rating_int)) if rating_int > 0 else 0

    if rating_int == 0:
        bg, fg = "#1c1917", "#d6d3d1"
        label = "N/A"
    else:
        bg, fg = _RATING_BADGE_COLORS.get(rating_int, ("#1c1917", "#d6d3d1"))
        label = f"{'★' * rating_int}{'☆' * (5 - rating_int)}"

    return (
        f'<span style="background:{bg}; color:{fg}; padding:3px 12px; '
        f'border-radius:20px; font-size:0.8rem; font-weight:600;">'
        f'{label}</span>'
    )


def format_sentiment_badge(sentiment: str, is_sarcastic: bool = False) -> str:
    """
    根据情绪标签返回彩色徽章 HTML。

    支持中英文情绪标签，包括：
    positive / negative / neutral / mixed / sarcastic，
    以及真诚好评、直接差评、反讽阴阳怪气等中文细分类。

    参数:
        sentiment: 情绪标签（英文或中文）
        is_sarcastic: 是否为反讽评论，为 True 时追加「反讽」标记

    返回:
        HTML ``<span>`` 标签字符串，包含内联样式
    """
    if not sentiment:
        sentiment = "unknown"

    sentiment_lower = str(sentiment).lower().strip()

    # 查找颜色映射
    bg, fg = _SENTIMENT_BADGE_COLORS.get(
        sentiment_lower,
        _SENTIMENT_BADGE_COLORS.get(sentiment_lower.replace(" ", "_"), ("#1c1917", "#d6d3d1")),
    )

    # 构建显示文本
    display_text = str(sentiment)
    if is_sarcastic and "反讽" not in display_text and "sarcas" not in sentiment_lower:
        display_text = f"{display_text} · 反讽"

    return (
        f'<span style="background:{bg}; color:{fg}; padding:3px 12px; '
        f'border-radius:20px; font-size:0.8rem; font-weight:600;">'
        f'{display_text}</span>'
    )


# ═══════════════════════════════════════════════════════════════
# 文本处理
# ═══════════════════════════════════════════════════════════════

def truncate_text(text: str, max_len: int = 50) -> str:
    """
    截断文本，超出最大长度时添加省略号（``...``）。

    参数:
        text: 原始文本
        max_len: 最大字符长度，默认 50

    返回:
        截断后的文本。若原文本长度不超过 ``max_len`` 则原样返回。
    """
    if not text or not isinstance(text, str):
        return ""

    if max_len <= 0:
        return text

    if len(text) <= max_len:
        return text

    # 截断并添加省略号
    return text[:max_len] + "..."


# ═══════════════════════════════════════════════════════════════
# 可信度颜色
# ═══════════════════════════════════════════════════════════════

def calculate_trust_color(score: Union[int, float]) -> str:
    """
    根据可信度评分返回对应的十六进制颜色。

    评分区间与颜色：
        0 - 30  → 红色（``#ef4444``，高风险）
        31 - 50 → 橙色（``#f97316``，中风险）
        51 - 70 → 灰色（``#9ca3af``，一般）
        71 - 100 → 绿色（``#22c55e``，可信）

    参数:
        score: 可信度评分（0-100）

    返回:
        十六进制颜色字符串（如 ``#22c55e``）
    """
    try:
        score_num = float(score)
    except (ValueError, TypeError):
        score_num = 0.0

    # 限制在 0-100 范围
    score_num = max(0, min(100, score_num))

    for low, high, color in _TRUST_COLOR_RANGES:
        if low <= score_num <= high:
            return color

    # 默认返回灰色
    return "#9ca3af"


# ═══════════════════════════════════════════════════════════════
# CSV 导入导出
# ═══════════════════════════════════════════════════════════════

def export_to_csv(results: List[Dict[str, Any]], filepath: str) -> str:
    """
    将分析结果导出为 CSV 文件。

    自动从嵌套字典中提取以下字段：
    review_text, rating, platform, sentiment_label, is_sarcastic,
    confidence, validity_label, final_sentiment, final_validity,
    trust_score, risk_level, summary, similar_count。

    参数:
        results: 分析结果列表，每条为包含 sentiment_analysis /
                 validity_analysis / final_analysis 子字典的字典
        filepath: 输出 CSV 文件路径

    返回:
        实际保存的文件路径。失败时返回空字符串。

    Raises:
        ValueError: 当 results 为空时
    """
    if not results:
        raise ValueError("结果列表为空，无法导出 CSV")

    # 确保输出目录存在
    output_dir = os.path.dirname(os.path.abspath(filepath))
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    try:
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_EXPORT_COLUMNS, extrasaction="ignore")
            writer.writeheader()

            for result in results:
                # 从嵌套结构中提取字段
                sentiment = result.get("sentiment_analysis", {}) or {}
                validity = result.get("validity_analysis", {}) or {}
                final = result.get("final_analysis", {}) or {}

                row = {
                    "review_text": truncate_text(result.get("review_text", ""), max_len=500),
                    "rating": result.get("rating", ""),
                    "platform": result.get("platform", ""),
                    "sentiment_label": sentiment.get("sentiment_label", ""),
                    "is_sarcastic": sentiment.get("is_sarcastic", ""),
                    "confidence": sentiment.get("confidence", ""),
                    "validity_label": validity.get("validity_label", ""),
                    "final_sentiment": final.get("final_sentiment", ""),
                    "final_validity": final.get("final_validity", ""),
                    "trust_score": final.get("trust_score", ""),
                    "risk_level": final.get("risk_level", ""),
                    "summary": final.get("summary", ""),
                    "similar_count": result.get("similar_count", ""),
                }
                writer.writerow(row)

        logger.info("CSV 导出成功: %s（共 %d 条）", filepath, len(results))
        return filepath

    except (IOError, OSError) as e:
        logger.error("CSV 导出失败: %s", e)
        raise


def load_reviews_from_csv(filepath: str) -> List[Dict[str, Any]]:
    """
    从 CSV 文件加载评论数据。

    支持以下列名（不区分大小写）：
    review_text, rating, platform, product_name, timestamp, user_id

    参数:
        filepath: CSV 文件路径

    返回:
        评论字典列表。每条字典包含从 CSV 读取的字段。

    Raises:
        FileNotFoundError: 当文件不存在时
        ValueError: 当文件为空或格式错误时
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV 文件不存在: {filepath}")

    reviews: List[Dict[str, Any]] = []

    try:
        with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                raise ValueError(f"CSV 文件为空或无表头: {filepath}")

            # 构建列名映射（不区分大小写）
            field_map: Dict[str, str] = {}
            for field in reader.fieldnames:
                field_lower = field.strip().lower()
                for target in _CSV_LOAD_COLUMNS:
                    if field_lower == target:
                        field_map[field] = target
                        break

            if not field_map:
                raise ValueError(
                    f"CSV 文件未包含任何有效列名，"
                    f"需要以下列之一: {', '.join(_CSV_LOAD_COLUMNS)}"
                )

            for row_num, row in enumerate(reader, start=2):
                review: Dict[str, Any] = {}
                for csv_col, target_col in field_map.items():
                    value = row.get(csv_col, "")
                    if value is None:
                        value = ""
                    value = str(value).strip()

                    # 评分字段转换为整数
                    if target_col == "rating":
                        try:
                            review[target_col] = int(float(value)) if value else 0
                        except (ValueError, TypeError):
                            review[target_col] = 0
                    else:
                        review[target_col] = value

                # 确保必须包含 review_text
                if "review_text" not in review:
                    review["review_text"] = ""

                # 跳过空评论
                if review["review_text"]:
                    reviews.append(review)

    except UnicodeDecodeError:
        # 尝试 GBK 编码回退
        logger.warning("UTF-8 解码失败，尝试 GBK 编码: %s", filepath)
        try:
            with open(filepath, "r", encoding="gbk", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 将列名标准化：小写 + 去空格 + 空格转下划线
                    review = {
                        k.lower().strip().replace(" ", "_"): v
                        for k, v in row.items()
                        if v
                    }
                    if review.get("review_text"):
                        if "rating" in review:
                            try:
                                review["rating"] = int(float(review["rating"]))
                            except (ValueError, TypeError):
                                review["rating"] = 0
                        reviews.append(review)
        except Exception as e:
            raise ValueError(f"CSV 文件编码读取失败: {e}")

    logger.info("CSV 加载成功: %s（共 %d 条评论）", filepath, len(reviews))
    return reviews


# ═══════════════════════════════════════════════════════════════
# 时间戳
# ═══════════════════════════════════════════════════════════════

def get_timestamp(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    获取格式化的当前时间戳字符串。

    参数:
        fmt: 时间格式字符串，默认 ``%Y-%m-%d %H:%M:%S``
             常用格式：
             - ``%Y%m%d_%H%M%S``（用于文件名）
             - ``%Y-%m-%dT%H:%M:%S``（ISO 格式）
             - ``%Y年%m月%d日 %H:%M``（中文格式）

    返回:
        格式化后的时间字符串
    """
    return datetime.now().strftime(fmt)


# ═══════════════════════════════════════════════════════════════
# 模块自测
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 测试 parse_json_safe
    print("=== parse_json_safe 测试 ===")
    test_cases = [
        '{"sentiment": "positive", "confidence": 0.95}',
        '```json\n{"sentiment": "negative"}\n```',
        '分析结果如下：\n{"sentiment": "neutral"}\n以上是分析。',
        '',
        '这不是JSON',
    ]
    for tc in test_cases:
        print(f"  输入: {tc[:50]}...")
        print(f"  输出: {parse_json_safe(tc)}")
        print()

    # 测试 format_rating_badge
    print("=== format_rating_badge 测试 ===")
    for r in [5, 4, 3, 2, 1, 0, "invalid"]:
        print(f"  {r}: {format_rating_badge(r)}")

    # 测试 format_sentiment_badge
    print("\n=== format_sentiment_badge 测试 ===")
    for s, sarc in [("positive", False), ("negative", False), ("sarcastic", True), ("neutral", False)]:
        print(f"  {s} (反讽={sarc}): {format_sentiment_badge(s, sarc)}")

    # 测试 truncate_text
    print("\n=== truncate_text 测试 ===")
    print(f"  '{'这是一段很长的评论文字用于测试截断功能'}' -> '{truncate_text('这是一段很长的评论文字用于测试截断功能', 10)}'")

    # 测试 calculate_trust_color
    print("\n=== calculate_trust_color 测试 ===")
    for score in [0, 15, 30, 45, 60, 75, 90, 100]:
        print(f"  {score}: {calculate_trust_color(score)}")

    # 测试 get_timestamp
    print(f"\n=== get_timestamp ===")
    print(f"  默认: {get_timestamp()}")
    print(f"  文件名格式: {get_timestamp('%Y%m%d_%H%M%S')}")
