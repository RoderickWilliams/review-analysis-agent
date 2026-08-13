# -*- coding: utf-8 -*-
"""
红旗检测引擎 (RedFlagEngine)
=============================
对单条评论进行可疑模式检测，包括：
- 促销语言（限时、抢购、优惠等）
- 空洞夸张用语（如"很好很好很好"重复堆砌）
- 奖励诱导指标（好评返现、试用等）
- 过度重复（同一字符连续重复 >5 次）
- 过短且高评分（<5 字 + 5 星）
- 内容无关（无任何产品相关关键词）
- 表情刷屏（emoji 数量过多）

可对单条评论检测，也可批量处理。
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional, Sequence, Union

# 模块日志器
logger = logging.getLogger(__name__)


class RedFlagEngine:
    """红旗检测引擎：识别单条评论中的可疑模式。"""

    # 促销语言关键词
    PROMOTIONAL_TERMS: List[str] = [
        "限时", "抢购", "优惠", "特价", "折扣", "秒杀",
        "包邮", "立减", "满减", "狂欢", "大促", "优惠券",
    ]

    # 奖励诱导关键词
    INCENTIVE_TERMS: List[str] = [
        "好评返现", "返现", "试用", "好评奖励", "免费试用",
        "刷单", "代金券", "好评有礼", "晒单返", "佣金",
    ]

    # 产品相关关键词（用于判断内容相关性，可按品类扩展）
    PRODUCT_KEYWORDS: List[str] = [
        "质量", "效果", "包装", "物流", "发货", "服务", "态度",
        "价格", "性价比", "材质", "大小", "尺寸", "颜色", "做工",
        "功能", "使用", "体验", "手感", "味道", "口感", "款式",
        "外观", "耐用", "正品", "客服", "配送", "安装",
    ]

    # 表情符号正则（覆盖常见 emoji 区段）
    EMOJI_PATTERN: re.Pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 表情符号
        "\U0001F300-\U0001F5FF"  # 符号和象形文字
        "\U0001F680-\U0001F6FF"  # 交通和地图符号
        "\U0001F1E0-\U0001F1FF"  # 旗帜
        "\U0001F900-\U0001F9FF"  # 补充表情符号
        "\U0001FA70-\U0001FAFF"  # 符号和象形文字扩展A
        "\U00002600-\U000026FF"  # 杂项符号
        "\U00002700-\U000027BF"  # 装饰符号
        "\U0001F018-\U0001F270"
        "]+",
        flags=re.UNICODE,
    )

    # 默认配置
    CONFIG: Dict[str, Any] = {
        "min_short_length": 5,         # 过短评论阈值（字符数）
        "short_high_rating": 5,        # 触发过短检测的高评分
        "emoji_spam_threshold": 5,     # 表情刷屏阈值（数量）
        "max_repeated_char": 5,        # 同一字符连续重复超过该次数则异常
        "superlative_min_repeat": 3,   # 空洞夸张：短语至少重复次数（含自身）
        "superlative_phrase_len": (2, 4),  # 空洞夸张：重复短语长度范围
        "irrelevant_min_length": 10,   # 内容无关检测的最小文本长度
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化引擎，可传入自定义配置覆盖默认配置。

        Args:
            config: 可选的配置字典，将与默认配置合并。
        """
        self.config: Dict[str, Any] = dict(self.CONFIG)
        if config:
            self.config.update(config)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def detect_red_flags(self, review_text: str, rating: int = 0) -> List[str]:
        """检测单条评论中的可疑模式。

        Args:
            review_text: 评论文本。
            rating: 评论评分（1-5），用于过短+高评分检测。

        Returns:
            红旗字符串列表，无红旗时返回空列表。
        """
        flags: List[str] = []

        # 输入校验
        if not isinstance(review_text, str) or not review_text.strip():
            return flags

        text = review_text.strip()
        try:
            # 1. 促销语言
            flags.extend(self._check_promotional(text))

            # 2. 奖励诱导
            flags.extend(self._check_incentive(text))

            # 3. 空洞夸张用语（重复堆砌）
            flags.extend(self._check_vague_superlative(text))

            # 4. 过度重复（同一字符连续重复）
            flags.extend(self._check_excessive_repetition(text))

            # 5. 过短且高评分
            flags.extend(self._check_too_short(text, rating))

            # 6. 内容无关（无产品关键词）
            flags.extend(self._check_irrelevant(text))

            # 7. 表情刷屏
            flags.extend(self._check_emoji_spam(text))
        except Exception as exc:
            logger.exception("红旗检测发生异常: %s", exc)

        return flags

    def batch_detect(
        self, reviews: Sequence[Union[str, Dict[str, Any]]]
    ) -> Dict[int, List[str]]:
        """批量检测所有评论的可疑模式。

        Args:
            reviews: 评论列表，元素可为纯文本字符串或 dict（含 text/rating 键）。

        Returns:
            评论索引 -> 红旗列表的映射。
        """
        results: Dict[int, List[str]] = {}
        if not reviews:
            return results

        for idx, review in enumerate(reviews):
            try:
                if isinstance(review, dict):
                    text = review.get("text") or review.get("content") or ""
                    rating = review.get("rating") or review.get("stars") or 0
                    try:
                        rating = int(rating)
                    except (TypeError, ValueError):
                        rating = 0
                else:
                    text = str(review) if review is not None else ""
                    rating = 0
                results[idx] = self.detect_red_flags(text, rating)
            except Exception as exc:
                logger.warning("第 %d 条评论红旗检测失败: %s", idx, exc)
                results[idx] = []
        return results

    # ------------------------------------------------------------------
    # 各项检测
    # ------------------------------------------------------------------
    def _check_promotional(self, text: str) -> List[str]:
        """检测促销语言。"""
        found = [term for term in self.PROMOTIONAL_TERMS if term in text]
        if found:
            return [f"包含促销语言：{'、'.join(found)}"]
        return []

    def _check_incentive(self, text: str) -> List[str]:
        """检测奖励诱导指标。"""
        found = [term for term in self.INCENTIVE_TERMS if term in text]
        if found:
            return [f"包含奖励诱导指标：{'、'.join(found)}"]
        return []

    def _check_vague_superlative(self, text: str) -> List[str]:
        """检测空洞夸张用语（短词组连续重复堆砌，如"很好很好很好"）。"""
        min_repeat = self.config["superlative_min_repeat"]
        lo, hi = self.config["superlative_phrase_len"]
        # 匹配长度在 [lo, hi] 的子串连续重复 >= (min_repeat) 次
        # 例如 min_repeat=3, 长度2-4：需要 \1 重复 2 次（共 3 次）
        pattern = re.compile(
            rf"(.{{{lo},{hi}}})\1{{{min_repeat - 1},}}"
        )
        match = pattern.search(text)
        if match:
            phrase = match.group(1)
            return [f"空洞夸张重复用语：『{phrase}』连续堆砌"]
        return []

    def _check_excessive_repetition(self, text: str) -> List[str]:
        """检测同一字符连续重复超过阈值（如 aaaaa、。。。。。。）。"""
        max_rep = self.config["max_repeated_char"]
        # (.) 匹配任意字符，\1 重复 max_rep 次（共 max_rep+1 次）
        pattern = re.compile(rf"(.)\1{{{max_rep},}}")
        matches = pattern.findall(text)
        if matches:
            char = matches[0]
            return [f"字符过度重复：『{char}』连续重复超过 {max_rep} 次"]
        return []

    def _check_too_short(self, text: str, rating: int) -> List[str]:
        """检测过短且高评分的评论。"""
        min_len = self.config["min_short_length"]
        high_rating = self.config["short_high_rating"]
        if len(text) < min_len and rating >= high_rating:
            return [
                f"评论过短且高评分：仅 {len(text)} 字却给 {rating} 星"
            ]
        return []

    def _check_irrelevant(self, text: str) -> List[str]:
        """检测内容无关（不含任何产品相关关键词）。"""
        min_len = self.config["irrelevant_min_length"]
        # 文本过短时不判定无关，避免与过短检测重复
        if len(text) < min_len:
            return []
        has_keyword = any(kw in text for kw in self.PRODUCT_KEYWORDS)
        if not has_keyword:
            return ["内容与产品无关：未出现任何产品相关关键词"]
        return []

    def _check_emoji_spam(self, text: str) -> List[str]:
        """检测表情刷屏。"""
        threshold = self.config["emoji_spam_threshold"]
        emojis = self.EMOJI_PATTERN.findall(text)
        # 统计 emoji 字符总数
        emoji_count = sum(len(e) for e in emojis)
        if emoji_count >= threshold:
            return [f"表情刷屏：检测到大量表情符号（{emoji_count} 个）"]
        return []


if __name__ == "__main__":
    # 简单自测示例
    engine = RedFlagEngine()
    test_cases = [
        ("限时抢购优惠包邮，质量很好很好很好", 5),
        ("好评返现，加微信领取", 5),
        ("哈哈哈哈哈哈哈哈东西不错", 4),
        ("好看", 5),
        ("今天天气真不错，出去玩了。", 5),
        ("质量很好，物流很快，包装也很用心，体验不错！😄😄😄😄😄😄", 5),
    ]
    for txt, rt in test_cases:
        flags = engine.detect_red_flags(txt, rt)
        print(f"[{rt}星] {txt}")
        for f in flags:
            print(f"    - {f}")
        if not flags:
            print("    - (无红旗)")
    print("\n批量检测示例：")
    batch = engine.batch_detect([
        {"text": "限时优惠", "rating": 5},
        {"text": "质量很好，效果明显", "rating": 4},
    ])
    print(batch)
