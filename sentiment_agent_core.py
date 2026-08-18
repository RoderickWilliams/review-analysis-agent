#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全平台用户反馈智能分析Agent - 核心模块
========================================
基于LLM的深度情绪识别 + 评价有效性检测 + 交叉验证

核心能力:
- 9类情绪识别（含中文反讽/阴阳怪气检测）
- 8类有效性检测（1真实+7无效：模板化/刷单/AI生成等）
- 多维度交叉验证 & 可信度评分

技术栈: Python / OpenAI API / TF-IDF / jieba / Pandas
"""

import json
import re
import os
import hashlib
import threading
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime

# LLM 结果缓存（确保 temperature=0 时相同 prompt 产生相同结果）
_LLM_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".llm_cache")
_LLM_CACHE_LOCK = threading.Lock()


# =============================================================================
# 第一部分：分类体系定义（9类情绪 + 8类有效性(1真实+7无效) = 17类）
# =============================================================================

class SentimentType(Enum):
    """情绪大类 —— 区分显性 / 隐性 / 矛盾"""
    EXPLICIT = "显性情绪"        # 用户直接表达的情绪
    IMPLICIT = "隐性情绪"        # 反讽、明褒暗贬、隐性抱怨
    MISMATCH = "评分评论矛盾"    # 评分与评论内容不一致


class SentimentCategory(Enum):
    """情绪细分类（9类）"""
    # 显性情绪
    AUTHENTIC_POSITIVE = "真诚好评"
    DIRECT_NEGATIVE = "直接差评"
    OBJECTIVE_NEUTRAL = "客观中性"
    # 隐性情绪（核心技术壁垒）
    SARCASM = "反讽阴阳怪气"
    BACKHANDED_PRAISE = "明褒暗贬"
    IMPLICIT_COMPLAINT = "隐性抱怨"
    # 评分-评论矛盾
    HIGH_RATING_NEGATIVE = "高分低评"
    LOW_RATING_POSITIVE = "低分高评"
    EXTREME_NEUTRAL = "评分极端文本中性"


class ValidityCategory(Enum):
    """评价有效性分类（7类）"""
    # 同质化检测（3类）
    AUTHENTIC = "真实有效"
    TEMPLATED = "模板化好评"
    CLICHE_STACKING = "套话堆砌"
    BATCH_COPY = "批量复制"
    # 异常模式检测（3类）
    TEMPORAL_BURST = "时间集中异常"
    CONTENT_DRIFT = "内容偏移"
    USER_ANOMALY = "用户行为异常"
    # AI生成检测（1类）
    AI_GENERATED = "AI生成"


# 分类映射表：细分类 → 大类
SENTIMENT_TYPE_MAP = {
    SentimentCategory.AUTHENTIC_POSITIVE: SentimentType.EXPLICIT,
    SentimentCategory.DIRECT_NEGATIVE: SentimentType.EXPLICIT,
    SentimentCategory.OBJECTIVE_NEUTRAL: SentimentType.EXPLICIT,
    SentimentCategory.SARCASM: SentimentType.IMPLICIT,
    SentimentCategory.BACKHANDED_PRAISE: SentimentType.IMPLICIT,
    SentimentCategory.IMPLICIT_COMPLAINT: SentimentType.IMPLICIT,
    SentimentCategory.HIGH_RATING_NEGATIVE: SentimentType.MISMATCH,
    SentimentCategory.LOW_RATING_POSITIVE: SentimentType.MISMATCH,
    SentimentCategory.EXTREME_NEUTRAL: SentimentType.MISMATCH,
}


# =============================================================================
# 第二部分：Prompt 模板定义（4个核心Prompt）
# =============================================================================

# ---------- Prompt 1：情绪识别（最关键，决定反讽识别准确率）----------
SENTIMENT_ANALYSIS_PROMPT = """你是一位专业的中文用户评论情绪分析专家，擅长识别显性情绪和隐性情绪，特别是中文语境下的反讽和阴阳怪气。

## 你的任务
分析以下用户评论的真实情绪，判断它属于哪个类别。

## 情绪分类体系

### 显性情绪（用户直接表达的情绪）
1. 真诚好评 (authentic_positive)：评分高，评论正面且包含具体使用体验
   示例："用了两周，续航确实给力，重度使用能撑一天半"

2. 直接差评 (direct_negative)：评分低，评论直接表达不满
   示例："质量太差了，用了一周就坏了，客服也不理人"

3. 客观中性 (objective_neutral)：评分中等，评论客观描述优缺点
   示例："音质还行，低音不错但高音有点闷"

### 隐性情绪（需要深度语义理解）
4. 反讽/阴阳怪气 (sarcasm)：文字表面积极正面，实际表达不满或嘲讽
   判断要点：字面意思与上下文矛盾、使用反语、夸张正面表述搭配负面暗示
   示例：
   - "这手机太好了，卡顿得让我学会了冥想，等待是一种修行"
   - "质量棒极了，买回来三天就坏了，省得我用太久，真环保"
   - "客服太热情了，热情到我想退货他们都拦着"

5. 明褒暗贬 (backhanded_praise)：表面夸某方面，实则暗示其他方面差
   判断要点：夸奖点与产品核心功能无关、暗含转折意味
   示例：
   - "外观确实好看，放在桌上当摆件挺好的"（暗示功能不行）
   - "包装很精美，送人很有面子"（暗示产品本身不行）

6. 隐性抱怨 (implicit_complaint)：不直接说不好，通过细节描述暗示不满
   判断要点：语气词犹豫、勉强的肯定、回避直接评价
   示例：
   - "嗯……收到了，就这样吧"（暗示失望）
   - "用了三天，目前还在用"（暗示勉强）

### 评分-评论矛盾
7. 高分低评 (high_rating_negative)：评分4-5星，但评论内容负面
8. 低分高评 (low_rating_positive)：评分1-2星，但评论内容正面
9. 评分极端文本中性 (extreme_neutral)：评分1星或5星，但评论平淡无情绪

## 输入信息
- 用户评分：{rating} 星（满分5星）
- 评论内容：{review_text}
- 来源平台：{platform}

## 输出要求
请以JSON格式输出，不要输出其他内容：
{{
  "sentiment_category": "类别英文名（如sarcasm、authentic_positive等）",
  "sentiment_label": "类别中文名",
  "sentiment_type": "显性情绪/隐性情绪/评分评论矛盾",
  "confidence": 0.0到1.0的置信度,
  "real_sentiment": "positive/negative/neutral",
  "is_sarcastic": true或false,
  "rating_consistent": true或false,
  "key_phrases": ["触发判断的关键词或短语"],
  "reasoning": "简要说明判断依据（1-2句话）"
}}"""


# ---------- Prompt 2：有效性检测（刷单/同质化/AI生成检测）----------
VALIDITY_CHECK_PROMPT = """你是一位专业的用户评论真实性检测专家，擅长识别刷单评论、模板化评价和AI生成的虚假评论。

## 你的任务
判断以下用户评论是否来自真实用户，是否反映真实的使用体验。

## 有效性分类体系

### 真实有效
- authentic（真实有效）：评论包含具体使用体验、产品细节，语言自然口语化

### 同质化评论（疑似刷单）
- templated（模板化好评）：万能好评模板，笼统赞美无具体场景
  示例："好评！质量很好，物流很快，卖家态度好，下次还来！"
- cliche_stacking（套话堆砌）：无实质内容的套话组合，重复词汇
  示例："很好很好很好很好很好"
- batch_copy（批量复制）：多条评论高度相似，疑似复制粘贴

### 异常模式
- temporal_burst（时间集中异常）：疑似短时间内批量发布
- content_drift（内容偏移）：评论与产品核心功能无关的通用话术
  示例：对耳机评价"发货快，包装好"但完全没提到音质、佩戴体验
- user_anomaly（用户行为异常）：新注册账号、高频评价等（需结合用户信息）

### AI生成
- ai_generated（AI生成）：语言过于流畅规范，缺乏口语化表达；结构模式化；内容过于"完美"但缺乏个人体验细节

## 输入信息
- 评论内容：{review_text}
- 产品名称：{product_name}
- 同批次相似评论数：{similar_count}（由TF-IDF算法计算得出，0表示无相似评论）

## 输出要求
请以JSON格式输出，不要输出其他内容：
{{
  "is_valid": true或false,
  "validity_category": "authentic/templated/cliche_stacking/batch_copy/temporal_burst/content_drift/ai_generated",
  "validity_label": "类别中文名",
  "confidence": 0.0到1.0的置信度,
  "specificity_score": 0.0到1.0的具体性得分（越高越有具体使用体验）,
  "authenticity_score": 0.0到1.0的真实性得分（越高越像真实用户）,
  "red_flags": ["可疑特征列表，如无则空数组"],
  "reasoning": "简要说明判断依据（1-2句话）"
}}"""


# ---------- Prompt 3：综合分析（交叉验证 + 可信度评分）----------
COMPREHENSIVE_ANALYSIS_PROMPT = """你是一位资深的产品口碑分析专家。请根据以下两个维度的分析结果，进行交叉验证，给出综合评估。

## 输入数据
- 用户评分：{rating} 星
- 评论内容：{review_text}

### 情绪识别结果
{sentiment_result}

### 有效性检测结果
{validity_result}

## 交叉验证规则
请根据以下规则进行交叉验证：
1. 反讽 + 模板化 → 高度疑似水军用模板刷差评（高风险）
2. 真诚好评 + AI生成 → AI生成的虚假好评（高风险）
3. 高分低评 + 具体性低 → 刷好评但内容随意（中风险）
4. 正面情绪 + 真实有效 → 正常好评（低风险）
5. 直接差评 + 真实有效 → 真实用户不满，需关注产品问题（中风险）

## 可信度评分标准
- 80-100分：真实有效的好评
- 60-80分：真实有效的差评（虽然负面但信息有价值）
- 30-50分：反讽/隐性情绪（情绪真实但需关注产品问题）
- 0-30分：模板化/AI生成/高度可疑（无效评论）

## 输出要求
请以JSON格式输出，不要输出其他内容：
{{
  "final_sentiment": "positive/negative/neutral",
  "final_validity": "authentic/suspicious/fake",
  "trust_score": 0到100的整数（综合可信度，100最可信）,
  "risk_level": "low/medium/high",
  "cross_validation": {{
    "consistent": true或false,
    "notes": "交叉验证说明"
  }},
  "summary": "一句话总结这条评论",
  "recommendation": "给品牌方的建议（无需处理/需关注/需调查）"
}}"""


# ---------- Prompt 4：批量报告（产品口碑分析报告）----------
BATCH_REPORT_PROMPT = """你是一位资深的产品口碑分析师。请根据以下批量分析结果，生成一份产品口碑分析报告。

## 输入信息
- 产品名称：{product_name}
- 总评论数：{total_reviews}
- 分析结果摘要（最多50条）：
{batch_results}

## 输出要求
请以JSON格式输出完整的产品口碑分析报告，不要输出其他内容：
{{
  "product_name": "产品名称",
  "total_reviews": 总评论数,
  "authentic_positive_rate": 真实好评率百分比（整数）,
  "sentiment_distribution": {{
    "positive": 正面情绪数量,
    "negative": 负面情绪数量,
    "neutral": 中性情绪数量,
    "sarcastic": 反讽数量
  }},
  "suspicious_review_count": 疑似无效评论数,
  "key_findings": ["关键发现1", "关键发现2", "关键发现3"],
  "top_complaints": ["用户痛点1", "用户痛点2", "用户痛点3"],
  "fake_review_risk": "low/medium/high（刷单风险等级）",
  "recommendations": ["改进建议1", "改进建议2", "改进建议3"]
}}"""


# =============================================================================
# 第三部分：Agent 核心逻辑
# =============================================================================

class ReviewAnalysisAgent:
    """
    全平台用户反馈智能分析Agent
    
    核心方法:
    - analyze_sentiment(): 情绪识别（含反讽检测）
    - check_validity(): 有效性检测（刷单/同质化/AI生成）
    - comprehensive_analysis(): 综合分析（交叉验证）
    - batch_analyze(): 批量分析
    - generate_report(): 口碑报告生成
    """

    def __init__(self, api_key: str = None, model: str = "gpt-4o",
                 base_url: str = None, web_client=None, client=None):
        """
        初始化Agent，支持三种 LLM 调用方式：

        1. API 模式（传统）: 提供 api_key，使用 OpenAI SDK
        2. Web 模式（无需 API Key）: 提供 web_client（WebLLMClient 实例）
        3. 降级模式: 提供 client（FallbackLLMClient 实例，自动降级）

        参数:
            api_key:     API密钥（api 模式）
            model:       模型名称（默认gpt-4o）
            base_url:    API基础URL（兼容第三方平台）
            web_client:  WebLLMClient 实例（web 模式，无需 API Key）
            client:      预构建的 LLM 客户端（降级模式，优先使用）
        """
        self.model = model

        if client is not None:
            # 降级模式：使用预构建的客户端（FallbackLLMClient）
            self.client = client
            self._web_mode = False
        elif web_client is not None:
            # Web 模式：使用 WebLLMClient（无需 API Key）
            self.client = web_client
            self._web_mode = True
        else:
            # API 模式：使用 OpenAI SDK
            self._web_mode = False
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key, base_url=base_url)
            except ImportError:
                print("错误：请先安装 openai 库：pip install openai")
                self.client = None

    _LLM_SYSTEM_MSG = "你是一位专业的中文NLP分析专家。请严格按照要求的JSON格式输出，不要输出其他内容。"

    def _cache_key(self, prompt: str, temperature: float) -> str:
        """生成缓存键（model + system + prompt + temperature 的哈希）"""
        raw = f"{self.model}|{self._LLM_SYSTEM_MSG}|{prompt}|{temperature}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _call_llm(self, prompt: str, temperature: float = 0.0) -> str:
        """
        调用大模型，返回文本响应

        参数:
            prompt:      用户提示词
            temperature: 温度参数（分析任务设为0确保结果一致性）

        temperature=0 时启用文件缓存，确保相同 prompt 永远返回相同结果，
        消除 LLM API 在 temperature=0 下仍可能存在的微小非确定性。
        """
        if not self.client:
            return '{"error": "LLM client not initialized"}'

        # temperature=0 时检查缓存
        if temperature == 0.0:
            cache_key = self._cache_key(prompt, temperature)
            cache_path = os.path.join(_LLM_CACHE_DIR, f"{cache_key}.txt")
            with _LLM_CACHE_LOCK:
                if os.path.exists(cache_path):
                    try:
                        with open(cache_path, "r", encoding="utf-8") as f:
                            return f.read()
                    except Exception:
                        pass  # 缓存读取失败，继续调用 LLM

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._LLM_SYSTEM_MSG},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
            )
            result = response.choices[0].message.content

            # temperature=0 时写入缓存
            if temperature == 0.0:
                with _LLM_CACHE_LOCK:
                    os.makedirs(_LLM_CACHE_DIR, exist_ok=True)
                    try:
                        with open(cache_path, "w", encoding="utf-8") as f:
                            f.write(result)
                    except Exception:
                        pass  # 缓存写入失败不影响正常流程

            return result
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            # 区分错误类型，返回结构化错误信息
            if "AuthenticationError" in error_type or "401" in error_msg:
                print(f"[LLM] API Key 认证失败: {error_msg[:100]}")
                return '{"error": "API Key 认证失败，请检查 .env 中的 LLM_API_KEYS 是否为真实的 OpenAI API Key", "error_type": "auth"}'
            elif "RateLimitError" in error_type or "429" in error_msg:
                print(f"[LLM] API 速率限制: {error_msg[:100]}")
                return '{"error": "API 调用频率超限，请稍后重试", "error_type": "rate_limit"}'
            elif "connect" in error_msg.lower() or "timeout" in error_msg.lower():
                print(f"[LLM] 网络连接失败: {error_msg[:100]}")
                return '{"error": "网络连接失败，请检查网络或 BASE_URL 设置", "error_type": "network"}'
            else:
                print(f"[LLM] 调用失败 ({error_type}): {error_msg[:200]}")
                return '{"error": "LLM 调用失败", "error_type": "unknown", "detail": "' + str(e)[:100].replace('"', "'") + '"}'

    def _parse_json(self, text: str) -> Dict:
        """
        从LLM响应中提取JSON（兼容markdown代码块）
        
        处理策略:
        1. 去除 ```json ``` 标记
        2. 尝试直接解析
        3. 失败则提取 { } 之间的内容重试
        """
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
            return {"error": "JSON解析失败", "raw": text[:200]}

    # -------------------------------------------------------------------------
    # 核心方法1：情绪识别（含反讽检测）
    # -------------------------------------------------------------------------
    def analyze_sentiment(self, review_text: str, rating: int,
                          platform: str = "未知") -> Dict:
        """
        分析单条评论的情绪（含反讽检测）
        
        参数:
            review_text: 评论内容
            rating:      用户评分（1-5）
            platform:    来源平台（淘宝/京东等）
        
        返回: 情绪分析结果字典，包含:
            - sentiment_category: 类别英文名
            - sentiment_label: 类别中文名
            - confidence: 置信度(0-1)
            - is_sarcastic: 是否反讽
            - real_sentiment: 真实情绪
            - key_phrases: 关键短语
            - reasoning: 判断依据
        """
        prompt = SENTIMENT_ANALYSIS_PROMPT.format(
            rating=rating,
            review_text=review_text,
            platform=platform
        )
        raw = self._call_llm(prompt, temperature=0.0)
        return self._parse_json(raw)

    # -------------------------------------------------------------------------
    # 核心方法2：有效性检测（刷单/同质化/AI生成）
    # -------------------------------------------------------------------------
    def check_validity(self, review_text: str, product_name: str = "",
                       similar_count: int = 0) -> Dict:
        """
        检测评论有效性（刷单/同质化检测）
        
        参数:
            review_text:   评论内容
            product_name:  产品名称（用于判断相关性）
            similar_count: 同批次中相似评论数量（来自TF-IDF计算）
        
        返回: 有效性检测结果字典，包含:
            - is_valid: 是否有效
            - validity_category: 有效性分类
            - specificity_score: 具体性得分(0-1)
            - authenticity_score: 真实性得分(0-1)
            - red_flags: 可疑特征列表
        """
        prompt = VALIDITY_CHECK_PROMPT.format(
            review_text=review_text,
            product_name=product_name,
            similar_count=similar_count
        )
        raw = self._call_llm(prompt, temperature=0.0)
        return self._parse_json(raw)

    # -------------------------------------------------------------------------
    # 核心方法3：综合分析（交叉验证 + 可信度评分）
    # -------------------------------------------------------------------------
    def comprehensive_analysis(self, review_text: str, rating: int,
                               platform: str = "未知",
                               product_name: str = "",
                               similar_count: int = 0) -> Dict:
        """
        综合分析：情绪 + 有效性 + 交叉验证
        这是Agent的核心方法，串联所有分析模块。
        
        流程:
        1. 情绪识别（LLM）
        2. 有效性检测（LLM + TF-IDF数据）
        3. 交叉验证与融合（LLM）
        """
        # 步骤1：情绪识别
        sentiment_result = self.analyze_sentiment(
            review_text, rating, platform
        )
        print(f"    [1/3] 情绪识别完成: {sentiment_result.get('sentiment_label', 'N/A')}")

        # 步骤2：有效性检测
        validity_result = self.check_validity(
            review_text, product_name, similar_count
        )
        print(f"    [2/3] 有效性检测完成: {validity_result.get('validity_label', 'N/A')}")

        # 步骤3：交叉验证与融合
        prompt = COMPREHENSIVE_ANALYSIS_PROMPT.format(
            sentiment_result=json.dumps(sentiment_result,
                                        ensure_ascii=False),
            validity_result=json.dumps(validity_result,
                                       ensure_ascii=False),
            rating=rating,
            review_text=review_text
        )
        raw = self._call_llm(prompt, temperature=0.0)
        final_result = self._parse_json(raw)
        print(f"    [3/3] 交叉验证完成: 可信度={final_result.get('trust_score', 'N/A')}")

        # 合并所有结果
        return {
            "review_text": review_text,
            "rating": rating,
            "platform": platform,
            "sentiment_analysis": sentiment_result,
            "validity_analysis": validity_result,
            "final_analysis": final_result,
            "timestamp": datetime.now().isoformat()
        }

    # -------------------------------------------------------------------------
    # 核心方法4：批量分析
    # -------------------------------------------------------------------------
    def batch_analyze(self, reviews: List[Dict],
                      product_name: str = "") -> List[Dict]:
        """
        批量分析多条评论
        
        参数:
            reviews: 评论列表，每条包含
                {review_text, rating, platform, timestamp}
            product_name: 产品名称
        
        返回: 每条评论的综合分析结果列表
        """
        results = []
        total = len(reviews)
        print(f"\n{'='*60}")
        print(f"开始批量分析：共 {total} 条评论 | 产品：{product_name}")
        print(f"{'='*60}")

        # 步骤1：计算文本相似度，找出同质化评论
        print("\n[预处理] 计算TF-IDF文本相似度...")
        similarity_matrix = self._calculate_similarity(
            [r["review_text"] for r in reviews]
        )

        # 步骤2：逐条分析
        print("\n[分析中] 逐条调用LLM进行综合分析...\n")
        for i, review in enumerate(reviews):
            # 统计该评论与其他评论的相似度
            similar_count = sum(
                1 for j in range(len(reviews))
                if i != j and similarity_matrix[i][j] > 0.7
            )

            print(f"--- 评论 {i + 1}/{total} "
                  f"(相似度邻居: {similar_count}) ---")
            print(f"    内容: {review['review_text'][:50]}...")

            result = self.comprehensive_analysis(
                review_text=review["review_text"],
                rating=review.get("rating", 0),
                platform=review.get("platform", "未知"),
                product_name=product_name,
                similar_count=similar_count
            )
            result["similar_count"] = similar_count
            results.append(result)
            print()

        print(f"{'='*60}")
        print(f"批量分析完成：共分析 {total} 条评论")
        print(f"{'='*60}\n")
        return results

    # -------------------------------------------------------------------------
    # 核心方法5：口碑报告生成
    # -------------------------------------------------------------------------
    def generate_report(self, batch_results: List[Dict],
                        product_name: str = "") -> Dict:
        """
        基于批量分析结果生成产品口碑分析报告
        
        参数:
            batch_results: batch_analyze() 的返回结果
            product_name: 产品名称
        
        返回: 口碑报告字典
        """
        total = len(batch_results)
        sentiment_dist = {"positive": 0, "negative": 0,
                          "neutral": 0, "sarcastic": 0}
        suspicious_count = 0

        # 统计情绪分布和可疑评论数
        for r in batch_results:
            final = r.get("final_analysis", {})
            sentiment = final.get("final_sentiment", "neutral")
            if sentiment in sentiment_dist:
                sentiment_dist[sentiment] += 1

            # 检测反讽
            sa = r.get("sentiment_analysis", {})
            if sa.get("is_sarcastic"):
                sentiment_dist["sarcastic"] += 1

            validity = final.get("final_validity", "authentic")
            if validity in ("suspicious", "fake"):
                suspicious_count += 1

        # 提取关键结果摘要给LLM（最多50条）
        batch_summary = []
        for r in batch_results[:50]:
            final = r.get("final_analysis", {})
            batch_summary.append({
                "sentiment": final.get("final_sentiment"),
                "validity": final.get("final_validity"),
                "trust_score": final.get("trust_score"),
                "risk_level": final.get("risk_level"),
                "summary": final.get("summary",
                                     r.get("review_text", "")[:50])
            })

        prompt = BATCH_REPORT_PROMPT.format(
            product_name=product_name,
            total_reviews=total,
            batch_results=json.dumps(batch_summary,
                                     ensure_ascii=False, indent=2)
        )
        raw = self._call_llm(prompt, temperature=0.0)
        report = self._parse_json(raw)

        # 补充统计信息
        report["total_reviews"] = total
        report["sentiment_distribution"] = sentiment_dist
        report["suspicious_review_count"] = suspicious_count

        return report

    # -------------------------------------------------------------------------
    # 内部方法：TF-IDF 文本相似度计算
    # -------------------------------------------------------------------------
    def _calculate_similarity(self, texts: List[str]) -> List[List[float]]:
        """
        使用 TF-IDF + 余弦相似度计算文本间相似度
        参考 ReviewIQ 的 Trust Report Engine 中的近重复检测（阈值0.85）
        
        返回: NxN 相似度矩阵
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            import jieba

            # 中文分词（关键步骤：jieba将句子切分为词语）
            tokenized = [" ".join(jieba.cut(t)) for t in texts]

            # TF-IDF 向量化
            vectorizer = TfidfVectorizer(max_features=5000)
            tfidf_matrix = vectorizer.fit_transform(tokenized)

            # 计算余弦相似度矩阵
            sim_matrix = cosine_similarity(tfidf_matrix)

            return sim_matrix.tolist()

        except ImportError:
            print("警告：sklearn 或 jieba 未安装，跳过相似度计算")
            # 降级：返回零矩阵
            n = len(texts)
            return [[0.0] * n for _ in range(n)]


# =============================================================================
# 第四部分：示例 & 测试
# =============================================================================

def demo():
    """
    演示函数：使用5条测试评论验证Agent核心能力
    
    覆盖场景:
    1. 真诚好评（基础能力）
    2. 反讽/阴阳怪气（核心壁垒）
    3. 模板化好评（刷单检测）
    4. 明褒暗贬（隐性情绪）
    5. 直接差评（基础能力）
    """
    # ====== API配置从 config.py 读取 ======
    try:
        from config import API_KEY, MODEL, BASE_URL, is_api_key_configured
        if not is_api_key_configured():
            print("错误: API Key 未配置！请在 config.py 中填入真实 API Key")
            print("或设置环境变量 LLM_API_KEY")
            return
    except ImportError:
        print("错误: 未找到 config.py，请确保项目结构完整")
        return
    # ======================================

    agent = ReviewAnalysisAgent(
        api_key=API_KEY,
        model=MODEL,
        base_url=BASE_URL
    )

    # 测试数据（覆盖各类情绪和有效性场景）
    test_reviews = [
        # 用例1：真诚好评
        {"review_text": "用了两周，续航确实给力，重度使用能撑一天半，充电也快，很满意",
         "rating": 5, "platform": "淘宝"},

        # 用例2：反讽/阴阳怪气（核心测试）
        {"review_text": "这手机真是太好了，卡顿得让我学会了冥想，等待是一种修行",
         "rating": 5, "platform": "京东"},

        # 用例3：模板化好评（刷单检测）
        {"review_text": "好评！质量很好，物流很快，卖家态度好，下次还来！",
         "rating": 5, "platform": "京东"},

        # 用例4：明褒暗贬
        {"review_text": "外观确实好看，放在桌上当摆件挺好的",
         "rating": 4, "platform": "淘宝"},

        # 用例5：直接差评
        {"review_text": "质量太差了，用了一周就坏了，客服也不理人，千万别买",
         "rating": 1, "platform": "淘宝"},
    ]

    print("\n" + "━" * 60)
    print("  全平台用户反馈智能分析Agent - 演示")
    print("  深度情绪识别 · 反讽检测 · 评价有效性分析")
    print("━" * 60)

    # 批量分析
    results = agent.batch_analyze(
        test_reviews,
        product_name="某款智能手机"
    )

    # 生成报告
    print("\n[生成报告] 正在汇总分析结果...")
    report = agent.generate_report(
        results,
        product_name="某款智能手机"
    )

    # 输出报告
    print("\n" + "━" * 60)
    print("  产品口碑分析报告")
    print("━" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # 输出每条评论的关键结论
    print("\n\n" + "━" * 60)
    print("  逐条评论分析结论")
    print("━" * 60)
    for i, r in enumerate(results):
        final = r.get("final_analysis", {})
        sa = r.get("sentiment_analysis", {})
        va = r.get("validity_analysis", {})
        print(f"\n[评论{i+1}] {r['review_text'][:40]}...")
        print(f"  情绪: {sa.get('sentiment_label', 'N/A')} "
              f"(置信度: {sa.get('confidence', 'N/A')})")
        print(f"  反讽: {'是' if sa.get('is_sarcastic') else '否'}")
        print(f"  有效性: {va.get('validity_label', 'N/A')}")
        print(f"  可信度: {final.get('trust_score', 'N/A')}/100")
        print(f"  风险: {final.get('risk_level', 'N/A')}")
        print(f"  总结: {final.get('summary', 'N/A')}")
        print(f"  建议: {final.get('recommendation', 'N/A')}")

    # 保存结果
    output = {
        "report": report,
        "detailed_results": results
    }
    with open("output/analysis_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存至 output/analysis_results.json")


if __name__ == "__main__":
    demo()
