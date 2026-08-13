# -*- coding: utf-8 -*-
"""
评论分析 LangChain 链
====================
基于 LangChain PromptTemplate 封装 sentiment_agent_core.py 的核心功能，
提供情绪识别、有效性检测、综合分析和报告生成四条分析链。

特性：
- 优先使用 LangChain PromptTemplate 构建结构化提示词
- 当 LangChain 未安装时，自动回退到原生字符串格式化（str.format）
- 支持 OpenAI 兼容 API（通义千问 / DeepSeek / OpenAI 等）
- 支持从 config.py 读取多 Key 轮换，自动跳过失败 Key 并重试
- 所有分析方法返回解析后的 JSON 字典

参考项目：https://github.com/gudireddy-0110/reviewiq
    ReviewIQ 使用 LangChain PromptTemplate + LLM 调用实现评论分析，
    本模块在此基础上适配中文评论分析场景，并集成多 Key 轮换机制。

使用示例::

    from chains.review_chain import ReviewChain

    chain = ReviewChain()
    result = chain.analyze_sentiment("续航确实给力", rating=5, platform="淘宝")
    print(result)
"""

import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────
# 模块日志器
# ─────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 确保 项目根目录 在 sys.path 中（支持从子目录运行）
# ─────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ─────────────────────────────────────────────
# 尝试导入 LangChain
# ─────────────────────────────────────────────
try:
    from langchain.prompts import PromptTemplate
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    PromptTemplate = None  # type: ignore[assignment, misc]
    logger.info("LangChain 未安装，将使用原生字符串格式化。建议安装：pip install langchain")

# ─────────────────────────────────────────────
# 尝试导入 OpenAI SDK
# ─────────────────────────────────────────────
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None  # type: ignore[assignment, misc]
    logger.warning("openai 库未安装，请运行：pip install openai")

# ─────────────────────────────────────────────
# 导入配置（优先 config_v2 多 Key 轮换，回退 config 单 Key）
# ─────────────────────────────────────────────
_USE_KEY_ROTATION: bool = False
_API_KEYS: List[str] = []
_MODEL_DEFAULT: str = "gpt-4o"
_BASE_URL_DEFAULT: Optional[str] = None

try:
    # 优先尝试 config_v2（支持多 Key 轮换）
    from config_v2 import (  # type: ignore[import-not-found]
        API_KEYS as _V2_KEYS,
        MODEL as _V2_MODEL,
        BASE_URL as _V2_BASE_URL,
        get_next_api_key as _v2_get_next_key,
        mark_key_failed as _v2_mark_failed,
    )
    if _V2_KEYS:
        _USE_KEY_ROTATION = True
        _API_KEYS = _V2_KEYS
        _MODEL_DEFAULT = _V2_MODEL
        _BASE_URL_DEFAULT = _V2_BASE_URL
        logger.debug("使用 config_v2 多 Key 轮换配置（%d 个 Key）", len(_V2_KEYS))
except ImportError:
    pass

if not _USE_KEY_ROTATION:
    try:
        from config import (  # type: ignore[import-not-found]
            API_KEY as _V1_KEY,
            MODEL as _V1_MODEL,
            BASE_URL as _V1_BASE_URL,
        )
        if _V1_KEY and _V1_KEY != "your-api-key-here":
            _API_KEYS = [_V1_KEY]
        _MODEL_DEFAULT = _V1_MODEL
        _BASE_URL_DEFAULT = _V1_BASE_URL
        logger.debug("使用 config 单 Key 配置")
    except ImportError:
        logger.debug("未找到 config.py，将使用构造函数传入的参数")


# ═══════════════════════════════════════════════════════════════
# 回退 Prompt 模板
# ═══════════════════════════════════════════════════════════════
# 当 sentiment_agent_core.py 不存在或无法导入时使用这些内置模板。
# 模板使用 {variable} 语法定义变量，{{ }} 表示字面大括号，
# 兼容 str.format() 和 LangChain PromptTemplate。
# ─────────────────────────────────────────────

_FALLBACK_SENTIMENT_ANALYSIS_PROMPT = """你是一位专业的中文NLP分析专家，擅长电商评论情绪识别和反讽检测。

请分析以下电商评论的情绪，特别注意识别反讽、明褒暗贬等隐性情绪。

【评论信息】
- 评分: {rating} 星
- 平台: {platform}
- 评论内容: {review_text}

【情绪分类体系（9类）】
1. authentic_positive（真诚好评）: 真实的正面评价，有具体使用体验
2. direct_negative（直接差评）: 直接表达不满，有具体问题描述
3. objective_neutral（客观中性）: 客观描述，无明显情绪倾向
4. sarcasm（反讽阴阳怪气）: 表面正面实则负面，使用反语
5. backhanded_praise（明褒暗贬）: 表面夸奖实则暗示不足
6. implicit_complaint（隐性抱怨）: 委婉表达不满
7. high_rating_negative（高分低评）: 高评分但评论内容负面
8. low_rating_positive（低分高评）: 低评分但评论内容正面
9. extreme_neutral（评分极端文本中性）: 评分极端但文本无情绪

请严格按以下JSON格式输出（不要输出其他内容）:
{{
  "sentiment_category": "<类别英文名>",
  "sentiment_label": "<类别中文名>",
  "confidence": <0-1之间的置信度>,
  "is_sarcastic": <true/false>,
  "real_sentiment": "<positive/negative/neutral>",
  "key_phrases": ["<关键短语1>", "<关键短语2>"],
  "reasoning": "<判断依据>"
}}"""


_FALLBACK_VALIDITY_CHECK_PROMPT = """你是一位专业的电商评论质量审核专家，擅长识别刷单、模板化好评和虚假评论。

请检测以下评论的有效性，判断是否为真实用户评论。

【评论信息】
- 评论内容: {review_text}
- 产品名称: {product_name}
- 同批次相似评论数: {similar_count}

【有效性分类（8类）】
1. authentic（真实有效）: 真实用户评论，有具体使用体验
2. templated（模板化好评）: 使用通用模板话术，无具体体验
3. generic_praise（套话堆砌）: 堆砌笼统赞美词汇，缺乏细节
4. ai_generated（疑似AI生成）: 文本特征疑似AI自动生成
5. batch_copied（批量复制）: 与其他评论高度相似，疑似批量操作
6. irrelevant（不相关）: 评论内容与产品无关
7. incentivized（诱导好评）: 疑似好评返现/诱导评价
8. spam（垃圾信息）: 广告、无意义内容

请严格按以下JSON格式输出（不要输出其他内容）:
{{
  "is_valid": <true/false>,
  "validity_category": "<类别英文名>",
  "validity_label": "<类别中文名>",
  "specificity_score": <0-1之间的具体性得分>,
  "authenticity_score": <0-1之间的真实性得分>,
  "red_flags": ["<可疑特征1>", "<可疑特征2>"],
  "reasoning": "<判断依据>"
}}"""


_FALLBACK_COMPREHENSIVE_ANALYSIS_PROMPT = """你是一位专业的评论分析专家，请结合情绪分析结果和有效性检测结果进行交叉验证与综合判断。

【情绪分析结果】
{sentiment_result}

【有效性检测结果】
{validity_result}

【原始评论信息】
- 评分: {rating} 星
- 评论内容: {review_text}

【交叉验证规则】
1. 若情绪为反讽但有效性为真实，说明用户真实反讽，需关注产品问题
2. 若情绪为好评但有效性为模板化/可疑，说明疑似刷单好评
3. 若情绪为反讽且有效性为模板化，说明水军用模板刷差评
4. 可信度评分应综合考虑情绪真实性、有效性、评分一致性

请严格按以下JSON格式输出（不要输出其他内容）:
{{
  "final_sentiment": "<positive/negative/neutral/sarcastic>",
  "final_validity": "<authentic/suspicious/fake>",
  "trust_score": <0-100之间的可信度评分>,
  "risk_level": "<low/medium/high>",
  "rating_consistency": <true/false>,
  "summary": "<一句话总结>",
  "cross_validation_notes": "<交叉验证发现>"
}}"""


_FALLBACK_BATCH_REPORT_PROMPT = """你是一位专业的产品口碑分析专家，请基于以下批量评论分析结果生成产品口碑报告。

【产品名称】{product_name}
【评论总数】{total_reviews} 条

【批量分析结果摘要】
{batch_results}

请综合分析所有评论，生成结构化的产品口碑报告。

请严格按以下JSON格式输出（不要输出其他内容）:
{{
  "overall_sentiment": "<positive/negative/neutral/mixed>",
  "authentic_positive_rate": <0-100之间的真实好评率>,
  "suspicious_review_count": <可疑评论数>,
  "fake_review_risk": "<low/medium/high>",
  "key_findings": ["<关键发现1>", "<关键发现2>"],
  "top_complaints": ["<用户痛点1>", "<用户痛点2>"],
  "top_praises": ["<用户好评点1>", "<用户好评点2>"],
  "recommendations": ["<建议1>", "<建议2>"],
  "summary": "<总体评价总结>"
}}"""


# ═══════════════════════════════════════════════════════════════
# Prompt 模板加载
# ═══════════════════════════════════════════════════════════════

def _load_prompt_templates() -> Dict[str, str]:
    """
    从 sentiment_agent_core.py 加载 Prompt 模板。

    若 sentiment_agent_core 不可导入，则使用内置回退模板。

    返回:
        包含四个 Prompt 模板字符串的字典，键为：
        SENTIMENT_ANALYSIS_PROMPT / VALIDITY_CHECK_PROMPT /
        COMPREHENSIVE_ANALYSIS_PROMPT / BATCH_REPORT_PROMPT
    """
    templates: Dict[str, str] = {
        "SENTIMENT_ANALYSIS_PROMPT": _FALLBACK_SENTIMENT_ANALYSIS_PROMPT,
        "VALIDITY_CHECK_PROMPT": _FALLBACK_VALIDITY_CHECK_PROMPT,
        "COMPREHENSIVE_ANALYSIS_PROMPT": _FALLBACK_COMPREHENSIVE_ANALYSIS_PROMPT,
        "BATCH_REPORT_PROMPT": _FALLBACK_BATCH_REPORT_PROMPT,
    }

    try:
        from sentiment_agent_core import (  # type: ignore[import-not-found]
            SENTIMENT_ANALYSIS_PROMPT,
            VALIDITY_CHECK_PROMPT,
            COMPREHENSIVE_ANALYSIS_PROMPT,
            BATCH_REPORT_PROMPT,
        )
        templates["SENTIMENT_ANALYSIS_PROMPT"] = SENTIMENT_ANALYSIS_PROMPT
        templates["VALIDITY_CHECK_PROMPT"] = VALIDITY_CHECK_PROMPT
        templates["COMPREHENSIVE_ANALYSIS_PROMPT"] = COMPREHENSIVE_ANALYSIS_PROMPT
        templates["BATCH_REPORT_PROMPT"] = BATCH_REPORT_PROMPT
        logger.info("已从 sentiment_agent_core 加载 Prompt 模板")
    except ImportError:
        logger.info("sentiment_agent_core 不可导入，使用内置回退 Prompt 模板")
    except Exception as e:
        logger.warning("从 sentiment_agent_core 加载 Prompt 模板失败: %s，使用回退模板", e)

    return templates


# ═══════════════════════════════════════════════════════════════
# ReviewChain 类
# ═══════════════════════════════════════════════════════════════

class ReviewChain:
    """
    评论分析 LangChain 链。

    封装 sentiment_agent_core.py 的四大分析功能：
    1. 情绪识别（analyze_sentiment）—— 含反讽检测
    2. 有效性检测（check_validity）—— 刷单 / 同质化检测
    3. 综合分析（comprehensive_analysis）—— 交叉验证与融合
    4. 报告生成（generate_report）—— 批量结果汇总

    优先使用 LangChain PromptTemplate 构建提示词，
    当 LangChain 不可用时回退到原生字符串格式化。
    支持 OpenAI 兼容 API 和多 Key 轮换。

    参数:
        api_key: API 密钥。为 None 时从 config 自动读取。
        model: 模型名称。为 None 时从 config 读取，默认 ``gpt-4o``。
        base_url: API 基础 URL。为 None 时从 config 读取。
        max_retries: 单次 LLM 调用最大重试次数（Key 轮换重试），默认 3。
        retry_delay: 重试间隔（秒），默认 1.0。

    使用示例::

        # 方式1：使用 config 配置自动初始化
        chain = ReviewChain()

        # 方式2：手动传入参数
        chain = ReviewChain(api_key="sk-xxx", model="deepseek-chat",
                           base_url="https://api.deepseek.com/v1")

        # 情绪分析
        result = chain.analyze_sentiment("续航确实给力", rating=5, platform="淘宝")

        # 有效性检测
        result = chain.check_validity("好评！质量很好！", product_name="手机", similar_count=3)
    """

    # 系统提示词
    SYSTEM_PROMPT: str = (
        "你是一位专业的中文NLP分析专家。"
        "请严格按照要求的JSON格式输出，不要输出其他内容。"
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """
        初始化评论分析链。

        参数:
            api_key: API 密钥，为 None 时从 config 自动读取
            model: 模型名称，为 None 时从 config 读取
            base_url: API 基础 URL，为 None 时从 config 读取
            max_retries: 最大重试次数（Key 轮换重试）
            retry_delay: 重试间隔（秒）
        """
        # ── 模型与 API 配置 ──
        self.model: str = model or _MODEL_DEFAULT
        self.base_url: Optional[str] = base_url if base_url is not None else _BASE_URL_DEFAULT
        self.max_retries: int = max(1, max_retries)
        self.retry_delay: float = max(0.0, retry_delay)

        # ── API Key 管理 ──
        if api_key:
            # 手动传入的 Key 优先
            self._api_keys: List[str] = [api_key]
            self._use_rotation: bool = False
        else:
            # 从 config 读取
            self._api_keys = list(_API_KEYS) if _API_KEYS else []
            self._use_rotation = _USE_KEY_ROTATION

        # 客户端缓存（按 Key 缓存 OpenAI 客户端实例）
        self._clients: Dict[str, Any] = {}
        self._failed_keys: set = set()

        # ── 加载 Prompt 模板 ──
        templates = _load_prompt_templates()
        self._raw_templates: Dict[str, str] = templates

        # 构建 PromptTemplate（若 LangChain 可用）或保留原始字符串
        self._prompt_templates: Dict[str, Any] = {}
        self._build_prompt_templates()

        # ── 状态检查 ──
        if not OPENAI_AVAILABLE:
            logger.error("openai 库未安装，LLM 调用将不可用。请运行：pip install openai")

        if not self._api_keys:
            logger.warning(
                "未配置 API Key。请通过构造函数传入 api_key 参数，"
                "或在 config.py / config_v2.py / .env 中配置。"
            )

        if not LANGCHAIN_AVAILABLE:
            logger.info("LangChain 未安装，使用原生字符串格式化（功能完整，仅缺少 PromptTemplate 抽象层）")

    # ─────────────────────────────────────────
    # 私有方法
    # ─────────────────────────────────────────

    def _build_prompt_templates(self) -> None:
        """
        将原始 Prompt 字符串包装为 LangChain PromptTemplate。

        若 LangChain 不可用，则保留原始字符串，后续通过 str.format() 使用。
        """
        # 各模板对应的输入变量
        input_vars_map: Dict[str, List[str]] = {
            "SENTIMENT_ANALYSIS_PROMPT": ["rating", "review_text", "platform"],
            "VALIDITY_CHECK_PROMPT": ["review_text", "product_name", "similar_count"],
            "COMPREHENSIVE_ANALYSIS_PROMPT": [
                "sentiment_result", "validity_result", "rating", "review_text",
            ],
            "BATCH_REPORT_PROMPT": ["product_name", "total_reviews", "batch_results"],
        }

        for name, template_str in self._raw_templates.items():
            variables = input_vars_map.get(name, [])
            if LANGCHAIN_AVAILABLE:
                try:
                    self._prompt_templates[name] = PromptTemplate(
                        input_variables=variables,
                        template=template_str,
                    )
                except Exception as e:
                    logger.warning("构建 PromptTemplate '%s' 失败: %s，回退到原生格式化", name, e)
                    self._prompt_templates[name] = template_str
            else:
                self._prompt_templates[name] = template_str

    def _get_client(self, api_key: str) -> Any:
        """
        获取指定 API Key 对应的 OpenAI 客户端（带缓存）。

        参数:
            api_key: API 密钥

        返回:
            OpenAI 客户端实例

        Raises:
            RuntimeError: 当 openai 库未安装时
        """
        if not OPENAI_AVAILABLE:
            raise RuntimeError("openai 库未安装，请运行：pip install openai")

        if api_key in self._clients:
            return self._clients[api_key]

        client = OpenAI(api_key=api_key, base_url=self.base_url)
        self._clients[api_key] = client
        return client

    def _get_next_api_key(self) -> Optional[str]:
        """
        获取下一个可用的 API Key（支持轮换和失败跳过）。

        返回:
            可用的 API Key 字符串，若全部不可用则返回 None。
        """
        # 优先使用 config_v2 的轮换函数
        if self._use_rotation:
            try:
                key = _v2_get_next_key()
                if key:
                    return key
            except Exception:
                pass

        # 回退到内部轮换逻辑
        for key in self._api_keys:
            if key not in self._failed_keys:
                return key

        # 所有 Key 都失败了，重置失败列表再试一次
        if self._api_keys:
            self._failed_keys.clear()
            return self._api_keys[0]

        return None

    def _mark_key_failed(self, api_key: str) -> None:
        """
        标记某个 API Key 为失败状态。

        参数:
            api_key: 失败的 API Key
        """
        self._failed_keys.add(api_key)

        if self._use_rotation:
            try:
                _v2_mark_failed(api_key)
            except Exception:
                pass

        remaining = len(self._api_keys) - len(self._failed_keys)
        logger.warning(
            "[Key轮换] 标记失败，剩余可用 Key: %d/%d",
            remaining,
            len(self._api_keys),
        )

    def _call_llm(self, prompt: str, temperature: float = 0.3) -> str:
        """
        调用大语言模型，返回文本响应。

        支持 Key 轮换：当某个 Key 调用失败（认证错误、配额用尽等）时，
        自动标记为失败并使用下一个 Key 重试。

        参数:
            prompt: 格式化后的用户提示词
            temperature: 采样温度，控制输出随机性

        返回:
            LLM 返回的文本内容。

        Raises:
            RuntimeError: 当没有可用的 API Key 或所有重试均失败时。
        """
        if not OPENAI_AVAILABLE:
            raise RuntimeError("openai 库未安装，请运行：pip install openai")

        if not self._api_keys:
            raise RuntimeError(
                "未配置 API Key。请通过构造函数传入 api_key 参数，"
                "或在 config.py / .env 中配置。"
            )

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            api_key = self._get_next_api_key()
            if not api_key:
                raise RuntimeError("没有可用的 API Key")

            try:
                client = self._get_client(api_key)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                )
                content = response.choices[0].message.content
                if content:
                    return content
                else:
                    logger.warning("LLM 返回空内容（尝试 %d/%d）", attempt + 1, self.max_retries)

            except Exception as e:
                last_error = e
                error_msg = str(e).lower()

                # 判断是否为 Key 相关错误（认证失败、配额用尽等）
                is_key_error = any(
                    keyword in error_msg
                    for keyword in [
                        "authentication", "unauthorized", "invalid api key",
                        "quota", "rate limit", "429", "401", "403",
                        "insufficient_quota", "billing",
                    ]
                )

                if is_key_error:
                    self._mark_key_failed(api_key)
                    logger.warning(
                        "API Key 调用失败（认证/配额），尝试切换 Key（尝试 %d/%d）: %s",
                        attempt + 1,
                        self.max_retries,
                        str(e)[:100],
                    )
                else:
                    # 非Key相关错误（网络、服务端等），等待后重试
                    logger.warning(
                        "LLM 调用失败（尝试 %d/%d）: %s",
                        attempt + 1,
                        self.max_retries,
                        str(e)[:100],
                    )

                if attempt < self.max_retries - 1 and self.retry_delay > 0:
                    time.sleep(self.retry_delay)

        error_detail = str(last_error) if last_error else "未知错误"
        raise RuntimeError(f"LLM 调用失败（重试 {self.max_retries} 次后仍失败）: {error_detail}")

    def _format_prompt(self, template_name: str, **kwargs: Any) -> str:
        """
        使用 PromptTemplate 或原生格式化构建提示词。

        当 LangChain 可用时，template 为 PromptTemplate 对象，
        调用其 ``format()`` 方法（会校验输入变量完整性）。
        当 LangChain 不可用时，template 为原始字符串，
        调用 ``str.format()`` 方法。两者接口一致。

        参数:
            template_name: 模板名称（如 SENTIMENT_ANALYSIS_PROMPT）
            **kwargs: 模板变量键值对

        返回:
            格式化后的提示词字符串

        Raises:
            KeyError: 当模板名称不存在时
        """
        if template_name not in self._prompt_templates:
            raise KeyError(f"Prompt 模板 '{template_name}' 不存在")

        template = self._prompt_templates[template_name]
        # PromptTemplate 和 str 都有 format() 方法，接口一致
        return template.format(**kwargs)

    def _call_and_parse(
        self,
        template_name: str,
        temperature: float,
        **prompt_kwargs: Any,
    ) -> Dict[str, Any]:
        """
        构建提示词、调用 LLM、解析 JSON 的通用流程。

        参数:
            template_name: Prompt 模板名称
            temperature: 采样温度
            **prompt_kwargs: 模板变量

        返回:
            解析后的 JSON 字典。失败时返回包含 error 字段的字典。
        """
        # 延迟导入 parse_json_safe，避免循环依赖
        try:
            from utils.helpers import parse_json_safe
        except ImportError:
            # 回退到内联解析
            parse_json_safe = self._parse_json_inline

        try:
            prompt = self._format_prompt(template_name, **prompt_kwargs)
            raw_response = self._call_llm(prompt, temperature=temperature)
            result = parse_json_safe(raw_response)
            return result
        except RuntimeError as e:
            logger.error("LLM 调用失败 [%s]: %s", template_name, e)
            return {"error": str(e)}
        except Exception as e:
            logger.error("分析流程异常 [%s]: %s", template_name, e)
            return {"error": f"分析流程异常: {e}"}

    @staticmethod
    def _parse_json_inline(text: str) -> Dict[str, Any]:
        """
        内联 JSON 解析（当 utils.helpers 不可导入时的回退方案）。

        参数:
            text: LLM 返回的原始文本

        返回:
            解析后的字典
        """
        if not text:
            return {"error": "空响应"}

        import re as _re

        cleaned = text.strip()
        cleaned = _re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=_re.IGNORECASE)
        cleaned = _re.sub(r"\n?```\s*$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                pass

        return {"error": "JSON 解析失败", "raw": cleaned[:500]}

    # ─────────────────────────────────────────
    # 公开方法
    # ─────────────────────────────────────────

    def analyze_sentiment(
        self,
        review_text: str,
        rating: int,
        platform: str = "未知",
    ) -> Dict[str, Any]:
        """
        分析单条评论的情绪（含反讽检测）。

        调用 LLM 对评论进行深度情绪分析，识别 9 种情绪细分类，
        特别关注反讽、明褒暗贬等隐性情绪。

        参数:
            review_text: 评论正文内容
            rating: 用户评分（1-5）
            platform: 来源平台（淘宝 / 京东）

        返回:
            情绪分析结果字典，包含以下字段：
            - sentiment_category: 类别英文名
            - sentiment_label: 类别中文名
            - confidence: 置信度（0-1）
            - is_sarcastic: 是否反讽
            - real_sentiment: 真实情绪（positive/negative/neutral）
            - key_phrases: 关键短语列表
            - reasoning: 判断依据

            失败时返回 ``{"error": "..."}``。
        """
        logger.debug(
            "情绪分析: rating=%d, platform=%s, text=%s",
            rating, platform, review_text[:50] if review_text else "",
        )

        return self._call_and_parse(
            "SENTIMENT_ANALYSIS_PROMPT",
            temperature=0.2,
            rating=rating,
            review_text=review_text,
            platform=platform,
        )

    def check_validity(
        self,
        review_text: str,
        product_name: str = "",
        similar_count: int = 0,
    ) -> Dict[str, Any]:
        """
        检测评论有效性（刷单 / 同质化检测）。

        结合评论内容、产品名称和同批次相似评论数，
        判断评论是否为真实用户评论。

        参数:
            review_text: 评论正文内容
            product_name: 产品名称（用于判断评论相关性）
            similar_count: 同批次中与该评论相似的数量（来自 TF-IDF 相似度计算）

        返回:
            有效性检测结果字典，包含以下字段：
            - is_valid: 是否有效
            - validity_category: 有效性分类英文名
            - validity_label: 有效性分类中文名
            - specificity_score: 具体性得分（0-1）
            - authenticity_score: 真实性得分（0-1）
            - red_flags: 可疑特征列表
            - reasoning: 判断依据

            失败时返回 ``{"error": "..."}``。
        """
        logger.debug(
            "有效性检测: product=%s, similar_count=%d, text=%s",
            product_name, similar_count, review_text[:50] if review_text else "",
        )

        return self._call_and_parse(
            "VALIDITY_CHECK_PROMPT",
            temperature=0.2,
            review_text=review_text,
            product_name=product_name,
            similar_count=similar_count,
        )

    def comprehensive_analysis(
        self,
        sentiment_result: Dict[str, Any],
        validity_result: Dict[str, Any],
        rating: int,
        review_text: str,
    ) -> Dict[str, Any]:
        """
        综合分析：情绪 + 有效性 + 交叉验证。

        接收前两步的分析结果，调用 LLM 进行交叉验证与融合判断，
        输出最终的可信度评分和风险等级。

        参数:
            sentiment_result: analyze_sentiment 的返回结果
            validity_result: check_validity 的返回结果
            rating: 用户评分（1-5）
            review_text: 原始评论文本

        返回:
            综合分析结果字典，包含以下字段：
            - final_sentiment: 最终情绪（positive/negative/neutral/sarcastic）
            - final_validity: 最终有效性（authentic/suspicious/fake）
            - trust_score: 可信度评分（0-100）
            - risk_level: 风险等级（low/medium/high）
            - rating_consistency: 评分是否与评论一致
            - summary: 一句话总结
            - cross_validation_notes: 交叉验证发现

            失败时返回 ``{"error": "..."}``。
        """
        logger.debug(
            "综合分析: rating=%d, text=%s",
            rating, review_text[:50] if review_text else "",
        )

        return self._call_and_parse(
            "COMPREHENSIVE_ANALYSIS_PROMPT",
            temperature=0.3,
            sentiment_result=json.dumps(sentiment_result, ensure_ascii=False),
            validity_result=json.dumps(validity_result, ensure_ascii=False),
            rating=rating,
            review_text=review_text,
        )

    def generate_report(
        self,
        batch_results: List[Dict[str, Any]],
        product_name: str = "",
    ) -> Dict[str, Any]:
        """
        基于批量分析结果生成产品口碑报告。

        汇总所有评论的分析结果，调用 LLM 生成结构化的口碑报告，
        包含情绪分布、可疑评论统计、关键发现、用户痛点和建议。

        参数:
            batch_results: 批量分析结果列表（comprehensive_analysis 的返回结果列表）
            product_name: 产品名称

        返回:
            产品口碑报告字典，包含以下字段：
            - overall_sentiment: 总体情绪
            - authentic_positive_rate: 真实好评率（0-100）
            - suspicious_review_count: 可疑评论数
            - fake_review_risk: 刷单风险（low/medium/high）
            - key_findings: 关键发现列表
            - top_complaints: 用户痛点列表
            - top_praises: 用户好评点列表
            - recommendations: 建议列表
            - summary: 总体评价总结
            - total_reviews: 评论总数（自动补充）
            - sentiment_distribution: 情绪分布统计（自动补充）

            失败时返回包含 error 字段的字典。
        """
        logger.debug("生成报告: product=%s, count=%d", product_name, len(batch_results))

        total = len(batch_results)

        # 统计情绪分布和可疑评论数
        sentiment_dist: Dict[str, int] = {
            "positive": 0, "negative": 0, "neutral": 0, "sarcastic": 0,
        }
        suspicious_count = 0

        for r in batch_results:
            final = r.get("final_analysis", {}) or {}
            sentiment = final.get("final_sentiment", "neutral")
            if sentiment in sentiment_dist:
                sentiment_dist[sentiment] += 1
            validity = final.get("final_validity", "authentic")
            if validity in ("suspicious", "fake"):
                suspicious_count += 1

        # 提取关键结果摘要给 LLM（最多 50 条，控制 Token 消耗）
        batch_summary: List[Dict[str, Any]] = []
        for r in batch_results[:50]:
            final = r.get("final_analysis", {}) or {}
            batch_summary.append({
                "sentiment": final.get("final_sentiment"),
                "validity": final.get("final_validity"),
                "trust_score": final.get("trust_score"),
                "summary": final.get(
                    "summary",
                    r.get("review_text", "")[:50] if r.get("review_text") else "",
                ),
            })

        # 调用 LLM 生成报告
        report = self._call_and_parse(
            "BATCH_REPORT_PROMPT",
            temperature=0.5,
            product_name=product_name,
            total_reviews=total,
            batch_results=json.dumps(batch_summary, ensure_ascii=False, indent=2),
        )

        # 补充统计信息
        if "error" not in report:
            report["total_reviews"] = total
            report["sentiment_distribution"] = sentiment_dist
            report["suspicious_review_count"] = suspicious_count

        return report

    # ─────────────────────────────────────────
    # 便捷方法
    # ─────────────────────────────────────────

    def is_ready(self) -> bool:
        """
        检查分析链是否就绪（有可用 API Key 且 openai 库已安装）。

        返回:
            True 表示可以调用 LLM 分析
        """
        if not OPENAI_AVAILABLE:
            return False
        return len(self._api_keys) > 0 and any(k not in self._failed_keys for k in self._api_keys)

    def get_status(self) -> Dict[str, Any]:
        """
        获取分析链当前状态信息。

        返回:
            状态信息字典，包含：
            - langchain_available: LangChain 是否可用
            - openai_available: openai 库是否可用
            - model: 当前模型名称
            - base_url: API 基础 URL
            - api_keys_count: API Key 总数
            - available_keys: 可用 Key 数量
            - use_key_rotation: 是否启用 Key 轮换
            - prompt_templates: 已加载的 Prompt 模板列表
        """
        available = len(self._api_keys) - len(self._failed_keys)
        return {
            "langchain_available": LANGCHAIN_AVAILABLE,
            "openai_available": OPENAI_AVAILABLE,
            "model": self.model,
            "base_url": self.base_url or "默认（OpenAI官方）",
            "api_keys_count": len(self._api_keys),
            "available_keys": max(0, available),
            "use_key_rotation": self._use_rotation,
            "prompt_templates": list(self._raw_templates.keys()),
            "ready": self.is_ready(),
        }


# ═══════════════════════════════════════════════════════════════
# 模块自测
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  ReviewChain 模块自测")
    print("=" * 60)

    # 初始化（不调用 LLM，仅测试结构）
    chain = ReviewChain(api_key="dummy-key-for-testing")

    # 打印状态
    print("\n[1] 分析链状态:")
    status = chain.get_status()
    for k, v in status.items():
        print(f"  {k}: {v}")

    # 测试 Prompt 构建（不调用 LLM）
    print("\n[2] Prompt 模板构建测试:")
    for name in chain._raw_templates:
        template = chain._prompt_templates.get(name)
        template_type = type(template).__name__
        print(f"  {name}: {template_type}")

    # 测试 _format_prompt
    print("\n[3] Prompt 格式化测试:")
    try:
        formatted = chain._format_prompt(
            "SENTIMENT_ANALYSIS_PROMPT",
            rating=5,
            review_text="续航确实给力",
            platform="淘宝",
        )
        print(f"  格式化成功，长度: {len(formatted)} 字符")
        print(f"  前100字符: {formatted[:100]}...")
    except Exception as e:
        print(f"  格式化失败: {e}")

    # 测试 _parse_json_inline
    print("\n[4] JSON 解析测试:")
    test_jsons = [
        '{"sentiment": "positive", "confidence": 0.95}',
        '```json\n{"sentiment": "negative"}\n```',
        '结果：{"sentiment": "neutral"} 完成',
    ]
    for tj in test_jsons:
        result = ReviewChain._parse_json_inline(tj)
        print(f"  输入: {tj[:40]}...")
        print(f"  输出: {result}")

    print("\n" + "=" * 60)
    print("  自测完成（未调用 LLM，API Key 为占位符）")
    print("=" * 60)
