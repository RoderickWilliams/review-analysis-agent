# -*- coding: utf-8 -*-
"""
信任报告引擎 (TrustReportEngine)
=================================
综合分析评论数据，生成可信度报告，包含：
- 时间突发检测（temporal burst）
- TF-IDF 重复检测（余弦相似度 > 0.85）
- 评分分布异常分析
- 评论长度均匀度评分
- 短语重复检测（n-gram 频率分析）
- 评分与情感矛盾统计

依赖：scikit-learn (TF-IDF，可选；未安装时重复检测降级，其余分析仍可用)
"""

from __future__ import annotations

import re
import logging
import statistics
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

# scikit-learn 用于 TF-IDF 重复检测；未安装时优雅降级（其余分析仍可用）
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SKLEARN_AVAILABLE: bool = True
except ImportError:  # pragma: no cover - 依赖缺失时的兜底
    _SKLEARN_AVAILABLE = False
    TfidfVectorizer = None  # type: ignore
    cosine_similarity = None  # type: ignore

# 模块日志器
logger = logging.getLogger(__name__)


class TrustReportEngine:
    """信任报告引擎：对评论集合进行多维可信度分析并生成综合报告。"""

    # 引擎配置：可按需调整阈值
    CONFIG: Dict[str, Any] = {
        "duplicate_threshold": 0.85,      # 重复检测的余弦相似度阈值
        "burst_multiplier": 3.0,          # 突发检测：单日评论数超过日均的倍数
        "rating_anomaly_ratio": 0.8,      # 评分异常：单档评分占比超过该比例即可疑
        "ngram_size": 4,                  # 短语重复检测的 n-gram 大小
        "max_repeated_phrases": 20,       # 返回的重复短语最大数量
        # 信任分扣减权重
        "penalty_burst": 15,
        "penalty_per_dup_group": 10,
        "penalty_dup_cap": 25,
        "penalty_rating_anomaly": 15,
        "penalty_uniformity": 15,
        "penalty_per_phrase": 5,
        "penalty_phrase_cap": 20,
        "penalty_per_mismatch": 3,
        "penalty_mismatch_cap": 15,
        # 风险等级阈值
        "risk_low_threshold": 70,
        "risk_medium_threshold": 40,
    }

    # 支持的时间字符串格式
    _TS_FORMATS: List[str] = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
        "%Y%m%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%d/%m/%Y",
    ]

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化引擎，可传入自定义配置覆盖默认配置。

        Args:
            config: 可选的配置字典，将与默认配置合并。
        """
        # 拷贝默认配置，避免修改类属性
        self.config: Dict[str, Any] = dict(self.CONFIG)
        if config:
            self.config.update(config)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def generate_report(
        self,
        reviews: List[Any],
        analysis_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """生成综合信任报告。

        Args:
            reviews: 评论列表，元素可为 dict（含 text/rating/timestamp 等键）或纯文本字符串。
            analysis_results: 可选的情感分析结果列表，每项为 dict，含 rating 与 sentiment 字段，
                              用于统计评分-情感矛盾。

        Returns:
            包含整体信任分、各项检测结果与风险等级的字典。
        """
        # 初始化默认结果
        report: Dict[str, Any] = {
            "overall_trust_score": 100,
            "burst_detected": False,
            "duplicate_groups": [],
            "rating_anomaly": False,
            "length_uniformity_score": 0.0,
            "repeated_phrases": [],
            "mismatch_count": 0,
            "risk_level": "low",
            "summary": "",
        }

        if not reviews:
            report["summary"] = "无评论数据可供分析。"
            return report

        analysis_results = analysis_results or []

        try:
            # 从评论中提取文本、评分、时间戳
            texts, ratings, timestamps = self._extract_fields(reviews)

            # 1. 时间突发检测
            burst_detected, date_counts = self._detect_temporal_burst(timestamps)
            report["burst_detected"] = burst_detected

            # 2. TF-IDF 重复检测
            duplicate_groups = self._detect_duplicates(texts)
            report["duplicate_groups"] = duplicate_groups

            # 3. 评分分布异常分析
            rating_anomaly, distribution = self._analyze_rating_distribution(ratings)
            report["rating_anomaly"] = rating_anomaly

            # 4. 长度均匀度评分
            uniformity_score = self._analyze_length_uniformity(texts)
            report["length_uniformity_score"] = uniformity_score

            # 5. 短语重复检测
            repeated_phrases = self._detect_phrase_repetition(texts)
            report["repeated_phrases"] = repeated_phrases

            # 6. 评分-情感矛盾统计
            # 优先使用 analysis_results，其次回退到 reviews 自带的评分
            mismatch_count = self._rating_sentiment_mismatch(
                analysis_results if analysis_results else self._build_mismatch_input(reviews)
            )
            report["mismatch_count"] = mismatch_count

            # 计算综合信任分
            trust_score = self._compute_trust_score(
                burst_detected=burst_detected,
                duplicate_groups=duplicate_groups,
                rating_anomaly=rating_anomaly,
                uniformity_score=uniformity_score,
                repeated_phrases=repeated_phrases,
                mismatch_count=mismatch_count,
            )
            report["overall_trust_score"] = trust_score
            report["risk_level"] = self._risk_level(trust_score)
            report["summary"] = self._build_summary(
                report=report,
                date_counts=date_counts,
                distribution=distribution,
                total_reviews=len(reviews),
            )
        except Exception as exc:  # 兜底异常处理，保证不抛出
            logger.exception("生成信任报告时发生异常: %s", exc)
            report["summary"] = f"报告生成过程中出现异常: {exc}"
            report["risk_level"] = "high"
            report["overall_trust_score"] = 0

        return report

    # ------------------------------------------------------------------
    # 内部辅助：字段提取
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_fields(
        reviews: List[Any],
    ) -> Tuple[List[str], List[int], List[Any]]:
        """从评论列表中统一提取文本、评分与时间戳。"""
        texts: List[str] = []
        ratings: List[int] = []
        timestamps: List[Any] = []
        for r in reviews:
            if isinstance(r, dict):
                # 兼容多种字段命名
                text = r.get("text") or r.get("content") or r.get("review") or ""
                rating = r.get("rating") or r.get("stars") or 0
                ts = r.get("timestamp") or r.get("date") or r.get("time")
                texts.append(str(text) if text is not None else "")
                try:
                    ratings.append(int(rating))
                except (TypeError, ValueError):
                    ratings.append(0)
                timestamps.append(ts)
            else:
                # 纯文本评论
                texts.append(str(r) if r is not None else "")
                ratings.append(0)
                timestamps.append(None)
        return texts, ratings, timestamps

    @staticmethod
    def _build_mismatch_input(reviews: List[Any]) -> List[Dict[str, Any]]:
        """当未提供 analysis_results 时，从评论中构造最简的矛盾分析输入。"""
        items: List[Dict[str, Any]] = []
        for r in reviews:
            if isinstance(r, dict):
                items.append({
                    "rating": r.get("rating") or r.get("stars") or 0,
                    "sentiment": r.get("sentiment"),
                })
        return items

    # ------------------------------------------------------------------
    # 1. 时间突发检测
    # ------------------------------------------------------------------
    def _detect_temporal_burst(
        self, timestamps: List[Any]
    ) -> Tuple[bool, Dict[str, int]]:
        """检测评论时间突发（时间聚集）。

        按日期分组统计评论数，若某一天的评论数超过日均评论数的 3 倍，则判定为突发。

        Args:
            timestamps: 时间戳列表，可为 datetime 或字符串。

        Returns:
            (是否检测到突发, 每日评论计数字典)
        """
        if not timestamps:
            return False, {}

        date_counts: Dict[str, int] = defaultdict(int)
        parsed_dates: List[datetime] = []

        for ts in timestamps:
            dt = self._parse_timestamp(ts)
            if dt is None:
                continue
            date_key = dt.strftime("%Y-%m-%d")
            date_counts[date_key] += 1
            parsed_dates.append(dt)

        if not date_counts:
            return False, {}

        # 仅有一天有评论时无法判定突发
        if len(date_counts) == 1:
            return False, dict(date_counts)

        # 按完整日期跨度（含空缺日）计算日均，更能反映聚集程度
        parsed_dates.sort()
        span_days = (parsed_dates[-1] - parsed_dates[0]).days + 1
        span_days = max(span_days, 1)
        total_reviews = sum(date_counts.values())
        daily_avg = total_reviews / span_days

        threshold = daily_avg * self.config["burst_multiplier"]
        burst_detected = any(
            count > threshold for count in date_counts.values()
        )
        return burst_detected, dict(date_counts)

    def _parse_timestamp(self, ts: Any) -> Optional[datetime]:
        """将时间戳解析为 datetime，支持多种格式与已解析的 datetime 对象。"""
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, (int, float)):
            # 兼容 Unix 时间戳（秒/毫秒）
            try:
                value = float(ts)
                if value > 1e12:  # 毫秒级
                    value /= 1000.0
                return datetime.fromtimestamp(value)
            except (OSError, OverflowError, ValueError):
                return None
        if isinstance(ts, str):
            ts_str = ts.strip()
            for fmt in self._TS_FORMATS:
                try:
                    return datetime.strptime(ts_str, fmt)
                except ValueError:
                    continue
            # 最后尝试 ISO 8601 解析
            try:
                return datetime.fromisoformat(ts_str.replace("Z", ""))
            except ValueError:
                return None
        return None

    # ------------------------------------------------------------------
    # 2. TF-IDF 重复检测
    # ------------------------------------------------------------------
    def _detect_duplicates(self, texts: List[str]) -> List[List[int]]:
        """基于 TF-IDF + 余弦相似度矩阵检测重复评论。

        使用字符级 n-gram TF-IDF 向量化，计算两两余弦相似度，
        相似度 > 阈值（默认 0.85）的评论归为同一重复组（并查集分组）。

        Args:
            texts: 评论文本列表。

        Returns:
            重复组列表，每组为评论索引列表（仅保留 size >= 2 的组）。
        """
        if not texts or len(texts) < 2:
            return []

        # scikit-learn 未安装时无法执行 TF-IDF 检测，优雅降级
        if not _SKLEARN_AVAILABLE:
            logger.warning("scikit-learn 未安装，无法执行 TF-IDF 重复检测。")
            return []

        try:
            # 过滤空文本，记录原始索引
            valid_pairs = [
                (i, t)
                for i, t in enumerate(texts)
                if isinstance(t, str) and t.strip()
            ]
            if len(valid_pairs) < 2:
                return []

            valid_indices = [p[0] for p in valid_pairs]
            valid_texts = [p[1] for p in valid_pairs]

            # 字符级 n-gram 适配中英文，无需分词
            vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(2, 4),
                lowercase=False,
            )
            tfidf_matrix = vectorizer.fit_transform(valid_texts)

            # 计算余弦相似度矩阵
            sim_matrix = cosine_similarity(tfidf_matrix)

            threshold = self.config["duplicate_threshold"]

            # 并查集：将相似评论归并到同一组
            n = len(valid_indices)
            parent = list(range(n))

            def find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]  # 路径压缩
                    x = parent[x]
                return x

            def union(x: int, y: int) -> None:
                rx, ry = find(x), find(y)
                if rx != ry:
                    parent[rx] = ry

            for i in range(n):
                for j in range(i + 1, n):
                    if sim_matrix[i][j] > threshold:
                        union(i, j)

            # 收集分组
            groups: Dict[int, List[int]] = defaultdict(list)
            for i in range(n):
                root = find(i)
                groups[root].append(valid_indices[i])

            # 仅保留至少 2 条的组，并按组大小降序
            duplicate_groups = sorted(
                (g for g in groups.values() if len(g) >= 2),
                key=lambda g: len(g),
                reverse=True,
            )
            return duplicate_groups
        except Exception as exc:
            logger.warning("重复检测失败: %s", exc)
            return []

    # ------------------------------------------------------------------
    # 3. 评分分布异常分析
    # ------------------------------------------------------------------
    def _analyze_rating_distribution(
        self, ratings: List[int]
    ) -> Tuple[bool, Dict[str, float]]:
        """检查评分分布是否异常。

        当 5 星占比或 1 星占比超过阈值（默认 80%）时，判定分布异常（可疑）。

        Args:
            ratings: 评分列表（1-5）。

        Returns:
            (是否异常, 各评分占比字典)
        """
        if not ratings:
            return False, {}

        try:
            total = len(ratings)
            counter = Counter(ratings)
            ratio = self.config["rating_anomaly_ratio"]

            five_star_ratio = counter.get(5, 0) / total
            one_star_ratio = counter.get(1, 0) / total
            anomaly = five_star_ratio > ratio or one_star_ratio > ratio

            distribution = {str(k): v / total for k, v in counter.items()}
            return anomaly, distribution
        except Exception as exc:
            logger.warning("评分分布分析失败: %s", exc)
            return False, {}

    # ------------------------------------------------------------------
    # 4. 长度均匀度评分
    # ------------------------------------------------------------------
    def _analyze_length_uniformity(self, texts: List[str]) -> float:
        """计算评论长度的均匀度得分。

        基于长度序列的变异系数 (CV = std / mean)：
        CV 越小，说明评论长度越均匀（疑似模板化），得分越高（越可疑）。
        返回 0-100 的得分，0 表示长度差异大（正常），100 表示完全一致（高度可疑）。

        Args:
            texts: 评论文本列表。

        Returns:
            均匀度可疑得分（0-100，越高越可疑）。
        """
        if not texts:
            return 0.0

        try:
            lengths = [len(t) if isinstance(t, str) else 0 for t in texts]
            if len(lengths) < 2:
                return 0.0

            mean_len = statistics.mean(lengths)
            if mean_len == 0:
                return 0.0

            # 总体标准差（与 numpy 默认的 ddof=0 一致）
            std_len = statistics.pstdev(lengths)
            cv = std_len / mean_len  # 变异系数

            # CV=0 -> 100（完全一致），CV>=1 -> 0（差异大）
            score = max(0.0, min(100.0, (1.0 - cv) * 100.0))
            return round(score, 2)
        except Exception as exc:
            logger.warning("长度均匀度分析失败: %s", exc)
            return 0.0

    # ------------------------------------------------------------------
    # 5. 短语重复检测（n-gram 频率分析）
    # ------------------------------------------------------------------
    def _detect_phrase_repetition(
        self, texts: List[str], n: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """n-gram 频率分析，找出跨多条评论重复出现的短语。

        对每条评论生成 token 级 n-gram（中文按字、英文按词），
        统计每个短语出现在多少条不同评论中，出现 >= 2 条的短语视为模板指标。

        Args:
            texts: 评论文本列表。
            n: n-gram 大小，默认取配置中的 ngram_size。

        Returns:
            重复短语列表，每项含 phrase 与 count（出现的评论条数），按 count 降序。
        """
        if not texts:
            return []

        try:
            if n is None:
                n = self.config["ngram_size"]

            # phrase -> 出现过的评论索引集合
            phrase_reviews: Dict[str, set] = defaultdict(set)

            for idx, text in enumerate(texts):
                if not isinstance(text, str) or not text.strip():
                    continue
                # 使用 set 去重，同一评论内多次出现只计一次
                ngrams = set(self._generate_ngrams(text, n))
                for ng in ngrams:
                    phrase_reviews[ng].add(idx)

            # 仅保留出现在 >=2 条评论中的短语
            repeated: List[Dict[str, Any]] = [
                {"phrase": phrase, "count": len(idxs)}
                for phrase, idxs in phrase_reviews.items()
                if len(idxs) >= 2
            ]
            repeated.sort(key=lambda x: x["count"], reverse=True)

            max_return = self.config["max_repeated_phrases"]
            return repeated[:max_return]
        except Exception as exc:
            logger.warning("短语重复检测失败: %s", exc)
            return []

    @staticmethod
    def _generate_ngrams(text: str, n: int) -> List[str]:
        """生成 token 级 n-gram。

        分词策略：中文字符逐字、英文按单词、数字按串；
        标点与空白被忽略。token 间直接拼接（中文短语可读）。
        """
        tokens = re.findall(r"[\u4e00-\u9fff]|[a-zA-Z]+|[0-9]+", text.lower())
        if len(tokens) < n:
            return []
        return ["".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]

    # ------------------------------------------------------------------
    # 6. 评分-情感矛盾统计
    # ------------------------------------------------------------------
    def _rating_sentiment_mismatch(
        self, analysis_results: List[Dict[str, Any]]
    ) -> int:
        """统计评分与情感矛盾的数量。

        矛盾定义：高分（4-5）但负面情感，或低分（1-2）但正面情感。

        Args:
            analysis_results: 情感分析结果列表，每项含 rating 与 sentiment 字段。

        Returns:
            矛盾评论数量。
        """
        if not analysis_results:
            return 0

        try:
            mismatch_count = 0
            for res in analysis_results:
                if not isinstance(res, dict):
                    continue
                rating = res.get("rating")
                sentiment = res.get("sentiment") or res.get("sentiment_label")
                if rating is None or sentiment is None:
                    continue

                try:
                    rating = int(rating)
                except (TypeError, ValueError):
                    continue
                sentiment_str = str(sentiment).lower().strip()

                # 高分但负面
                if rating >= 4 and sentiment_str in ("negative", "neg", "负面", "消极"):
                    mismatch_count += 1
                # 低分但正面
                elif rating <= 2 and sentiment_str in ("positive", "pos", "正面", "积极"):
                    mismatch_count += 1
            return mismatch_count
        except Exception as exc:
            logger.warning("评分-情感矛盾统计失败: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # 综合评分与风险等级
    # ------------------------------------------------------------------
    def _compute_trust_score(
        self,
        burst_detected: bool,
        duplicate_groups: List[List[int]],
        rating_anomaly: bool,
        uniformity_score: float,
        repeated_phrases: List[Dict[str, Any]],
        mismatch_count: int,
    ) -> int:
        """根据各项检测结果计算综合信任分（0-100，越高越可信）。"""
        score = 100
        cfg = self.config

        # 时间突发
        if burst_detected:
            score -= cfg["penalty_burst"]

        # 重复组：每组扣分，设有上限
        dup_penalty = min(
            len(duplicate_groups) * cfg["penalty_per_dup_group"],
            cfg["penalty_dup_cap"],
        )
        score -= dup_penalty

        # 评分分布异常
        if rating_anomaly:
            score -= cfg["penalty_rating_anomaly"]

        # 长度均匀度：得分越高（越可疑）扣越多
        uniformity_penalty = (uniformity_score / 100.0) * cfg["penalty_uniformity"]
        score -= uniformity_penalty

        # 重复短语：每条扣分，设有上限
        phrase_penalty = min(
            len(repeated_phrases) * cfg["penalty_per_phrase"],
            cfg["penalty_phrase_cap"],
        )
        score -= phrase_penalty

        # 评分-情感矛盾：每条扣分，设有上限
        mismatch_penalty = min(
            mismatch_count * cfg["penalty_per_mismatch"],
            cfg["penalty_mismatch_cap"],
        )
        score -= mismatch_penalty

        return int(max(0, min(100, round(score))))

    def _risk_level(self, trust_score: int) -> str:
        """根据信任分映射风险等级（low / medium / high）。"""
        cfg = self.config
        if trust_score >= cfg["risk_low_threshold"]:
            return "low"
        if trust_score >= cfg["risk_medium_threshold"]:
            return "medium"
        return "high"

    # ------------------------------------------------------------------
    # 报告摘要生成
    # ------------------------------------------------------------------
    def _build_summary(
        self,
        report: Dict[str, Any],
        date_counts: Dict[str, int],
        distribution: Dict[str, float],
        total_reviews: int,
    ) -> str:
        """生成中文文字摘要，概述各项检测结果。"""
        parts: List[str] = [f"共分析 {total_reviews} 条评论。"]

        if report["burst_detected"]:
            # 找出评论最多的一天
            if date_counts:
                peak_day = max(date_counts, key=date_counts.get)
                parts.append(
                    f"检测到时间突发：{peak_day} 当日评论数 {date_counts[peak_day]} 条，"
                    f"显著高于日均水平。"
                )
        else:
            parts.append("未检测到明显的时间突发。")

        if report["duplicate_groups"]:
            total_dup = sum(len(g) for g in report["duplicate_groups"])
            parts.append(
                f"发现 {len(report['duplicate_groups'])} 组重复评论，"
                f"共涉及 {total_dup} 条。"
            )
        else:
            parts.append("未发现高度重复的评论。")

        if report["rating_anomaly"]:
            parts.append("评分分布异常，集中度过高。")
        else:
            parts.append("评分分布正常。")

        if report["length_uniformity_score"] >= 60:
            parts.append(
                f"评论长度均匀度得分 {report['length_uniformity_score']}，"
                f"疑似模板化。"
            )

        if report["repeated_phrases"]:
            top = report["repeated_phrases"][0]
            parts.append(
                f"检测到 {len(report['repeated_phrases'])} 个跨评论重复短语，"
                f"如「{top['phrase']}」（出现于 {top['count']} 条评论）。"
            )

        if report["mismatch_count"] > 0:
            parts.append(f"存在 {report['mismatch_count']} 条评分与情感矛盾的评论。")

        parts.append(
            f"综合信任分 {report['overall_trust_score']}，风险等级：{report['risk_level']}。"
        )
        return "".join(parts)


if __name__ == "__main__":
    # 简单自测示例
    engine = TrustReportEngine()
    sample_reviews = [
        {"text": "这个产品质量很好，物流很快，非常满意！", "rating": 5, "timestamp": "2024-01-01"},
        {"text": "这个产品质量很好，物流很快，非常满意！", "rating": 5, "timestamp": "2024-01-01"},
        {"text": "质量很好物流很快非常满意推荐购买", "rating": 5, "timestamp": "2024-01-02"},
        {"text": "东西一般般吧，不值这个价格。", "rating": 2, "timestamp": "2024-01-10"},
        {"text": "很差", "rating": 1, "timestamp": "2024-01-10"},
    ]
    sample_analysis = [
        {"rating": 5, "sentiment": "positive"},
        {"rating": 5, "sentiment": "positive"},
        {"rating": 5, "sentiment": "positive"},
        {"rating": 2, "sentiment": "positive"},  # 矛盾
        {"rating": 1, "sentiment": "negative"},
    ]
    result = engine.generate_report(sample_reviews, sample_analysis)
    for k, v in result.items():
        print(f"{k}: {v}")
