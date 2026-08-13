# -*- coding: utf-8 -*-
"""
数据预处理模块
====================
对采集的原始评论数据进行清洗、去重、分词等预处理。

使用方式:
    from data_preprocessor import DataPreprocessor
    processor = DataPreprocessor()

    # 清洗单条评论
    cleaned = processor.clean_text("  好评！！！质量很好！！！  ")

    # 批量预处理
    df_clean = processor.preprocess_csv("data/raw_reviews.csv",
                                        "data/cleaned_reviews.csv")
"""

import os
import re
from typing import List, Dict, Optional

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import jieba
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False

try:
    from config import DATA_DIR, SIMILARITY_HIGH
except ImportError:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    SIMILARITY_HIGH = 0.85


class DataPreprocessor:
    """数据预处理器：清洗、去重、分词"""

    def __init__(self):
        # 加载自定义词典（如有）
        self._init_jieba()

    def _init_jieba(self):
        """初始化jieba分词"""
        if not HAS_JIEBA:
            print("警告: 未安装 jieba，请运行 pip install jieba")
            return

        # 添加电商领域常用词
        domain_words = [
            "续航", "快充", "闪充", "拍照", "夜景", "刷新率",
            "性价比", "物流", "卖家", "客服", "好评", "差评",
            "阴阳怪气", "刷单", "种草", "拔草", "开箱",
        ]
        for word in domain_words:
            jieba.add_word(word)

    # ═══════════════════════════════════════════════════════════════
    # 文本清洗
    # ═══════════════════════════════════════════════════════════════

    def clean_text(self, text: str) -> str:
        """
        清洗单条评论文本

        处理:
        - 去除首尾空白
        - 去除HTML标签
        - 去除多余空白字符
        - 统一标点符号（全角转半角）
        - 去除控制字符
        - 保留表情符号（蕴含情绪信息）
        """
        if not text or not isinstance(text, str):
            return ""

        # 去除HTML标签
        text = re.sub(r'<[^>]+>', '', text)

        # 去除控制字符（保留换行和空格）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

        # 全角转半角（标点）
        fullwidth = '！＂＃＄％＆＇（）＊＋，－．／：；＜＝＞？＠［＼］＾＿｀｛｜｝～'
        halfwidth = '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
        trans = str.maketrans(fullwidth, halfwidth)
        text = text.translate(trans)

        # 合并连续空白
        text = re.sub(r'[ \t]+', ' ', text)

        # 合并连续换行
        text = re.sub(r'\n+', '\n', text)

        # 去除首尾空白
        text = text.strip()

        return text

    # ═══════════════════════════════════════════════════════════════
    # 分词
    # ═══════════════════════════════════════════════════════════════

    def tokenize(self, text: str) -> List[str]:
        """
        中文分词

        返回:
            分词后的词语列表
        """
        if not HAS_JIEBA:
            print("警告: 未安装 jieba，返回字符级切分")
            return list(text)

        words = jieba.lcut(text)
        # 过滤空字符串和纯空白
        return [w for w in words if w.strip()]

    def tokenize_for_tfidf(self, text: str) -> str:
        """
        分词并返回空格连接的字符串（供TF-IDF使用）

        scikit-learn的TfidfVectorizer需要空格分隔的文本
        """
        words = self.tokenize(text)
        return " ".join(words)

    # ═══════════════════════════════════════════════════════════════
    # 批量预处理
    # ═══════════════════════════════════════════════════════════════

    def preprocess_csv(
        self,
        input_path: str,
        output_path: str = None,
        min_length: int = 3,
        deduplicate: bool = True,
    ) -> "pd.DataFrame":
        """
        批量预处理CSV格式的评论数据

        步骤:
        1. 读取CSV
        2. 清洗文本
        3. 去除空评论和过短评论
        4. 去除完全重复
        5. 评分标准化（1-5）
        6. 时间格式统一
        7. 中文分词（添加tokens列）
        8. 保存清洗后数据

        参数:
            input_path:   输入CSV路径
            output_path:  输出CSV路径（None则自动生成）
            min_length:   最短评论长度（字符数）
            deduplicate:  是否去重

        返回:
            清洗后的DataFrame
        """
        if not HAS_PANDAS:
            print("错误: 请先安装依赖 pip install pandas")
            return None

        print(f"开始预处理: {input_path}")

        # 1. 读取
        df = pd.read_csv(input_path, encoding="utf-8-sig")
        original_count = len(df)
        print(f"  原始数据: {original_count} 条")

        # 2. 清洗文本
        df["review_text"] = df["review_text"].astype(str).apply(self.clean_text)

        # 3. 去除空评论和过短评论
        df = df[df["review_text"].str.len() >= min_length]
        print(f"  去除空/过短评论后: {len(df)} 条")

        # 4. 去重
        if deduplicate:
            before = len(df)
            df = df.drop_duplicates(subset=["review_text"], keep="first")
            print(f"  去重后: {len(df)} 条 (移除 {before - len(df)} 条重复)")

        # 5. 评分标准化
        if "rating" in df.columns:
            df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
            df["rating"] = df["rating"].clip(1, 5).fillna(3).astype(int)

        # 6. 时间格式统一
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(
                df["timestamp"], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M:%S")

        # 7. 分词
        if HAS_JIEBA:
            df["tokens"] = df["review_text"].apply(self.tokenize_for_tfidf)
            print(f"  分词完成")

        # 8. 保存
        if output_path is None:
            basename = os.path.basename(input_path)
            output_path = os.path.join(
                os.path.dirname(input_path),
                f"cleaned_{basename}"
            )

        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"  已保存至: {output_path}")
        print(f"  最终数据: {len(df)} 条 (清洗率: {(1 - len(df) / original_count) * 100:.1f}%)")

        return df

    # ═══════════════════════════════════════════════════════════════
    # 数据统计
    # ═══════════════════════════════════════════════════════════════

    def get_statistics(self, df: "pd.DataFrame") -> Dict:
        """获取数据集统计信息"""
        if not HAS_PANDAS:
            return {}

        stats = {
            "total_reviews": len(df),
            "avg_length": round(df["review_text"].str.len().mean(), 1),
            "max_length": int(df["review_text"].str.len().max()),
            "min_length": int(df["review_text"].str.len().min()),
        }

        if "rating" in df.columns:
            stats["rating_distribution"] = df["rating"].value_counts().sort_index().to_dict()

        if "platform" in df.columns:
            stats["platform_distribution"] = df["platform"].value_counts().to_dict()

        return stats

    def print_statistics(self, df: "pd.DataFrame"):
        """打印数据集统计信息"""
        stats = self.get_statistics(df)
        print("\n数据集统计:")
        print(f"  总评论数:   {stats.get('total_reviews', 0)}")
        print(f"  平均长度:   {stats.get('avg_length', 0)} 字符")
        print(f"  最长评论:   {stats.get('max_length', 0)} 字符")
        print(f"  最短评论:   {stats.get('min_length', 0)} 字符")

        if "rating_distribution" in stats:
            print(f"  评分分布:   {stats['rating_distribution']}")

        if "platform_distribution" in stats:
            print(f"  平台分布:   {stats['platform_distribution']}")


if __name__ == "__main__":
    processor = DataPreprocessor()

    # 测试文本清洗
    test_text = "  好评！！！质量很好！！！<br>  "
    cleaned = processor.clean_text(test_text)
    print(f"清洗前: '{test_text}'")
    print(f"清洗后: '{cleaned}'")

    # 测试分词
    tokens = processor.tokenize("这手机续航确实给力")
    print(f"分词结果: {tokens}")

    # 测试批量预处理
    sample_path = os.path.join(DATA_DIR, "test_reviews.csv")
    if os.path.exists(sample_path):
        df = processor.preprocess_csv(sample_path)
        processor.print_statistics(df)
