# -*- coding: utf-8 -*-
"""
LLM 降级客户端 — API Key 优先，自动降级到 DeepSeek 网页端
=====================================================
当 API Key 额度用尽或认证失败时，自动切换到 DeepSeek 网页端调用。

使用方式:
    from fallback_client import create_llm_client
    client = create_llm_client()
    # 和 OpenAI SDK 完全兼容
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "你好"}]
    )
"""

import os
import sys
import logging
import time
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class FallbackLLMClient:
    """
    LLM 降级客户端 — API Key 优先，自动降级到网页端

    优先级:
    1. OpenAI/DeepSeek API Key（官方接口，稳定可靠）
    2. DeepSeek 网页端逆向调用（免费，但可能不稳定）
    """

    def __init__(self, api_key: str = None, model: str = "deepseek-chat",
                 base_url: str = None, web_client=None):
        self.model = model
        self._api_key = api_key
        self._base_url = base_url
        self._primary_client = None
        self._web_client = web_client
        self._fallback_mode = False
        self._error_count = 0
        self._max_errors = 3  # 连续失败3次后切换到降级模式

        # 初始化主客户端（API Key 模式）
        if api_key:
            try:
                from openai import OpenAI
                self._primary_client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=120.0,
                )
                logger.info(f"主客户端已初始化 (API Key 模式, model={model})")
            except Exception as e:
                logger.warning(f"主客户端初始化失败: {e}")

        # 如果没有主客户端且有网页端客户端，直接使用网页端
        if self._primary_client is None and self._web_client is not None:
            self._fallback_mode = True
            logger.info("无 API Key，直接使用 DeepSeek 网页端模式")

        # 构建兼容接口
        self.chat = self._Chat(self)

    @property
    def current_mode(self) -> str:
        """当前调用模式"""
        if self._fallback_mode:
            return "DeepSeek 网页端（免费备用）"
        elif self._primary_client:
            return "API Key（主力）"
        else:
            return "未初始化"

    def _should_fallback(self, error: Exception) -> bool:
        """判断是否应该降级"""
        if self._web_client is None:
            return False

        error_str = str(error).lower()
        # 额度用尽、认证失败、计费错误
        fallback_keywords = [
            "quota", "billing", "402", "insufficient",
            "余额不足", "额度", "rate_limit", "429",
            "authentication", "401", "invalid_api_key",
        ]
        return any(kw in error_str for kw in fallback_keywords)

    def _call_primary(self, messages: List[Dict], temperature: float) -> Any:
        """调用主客户端"""
        if self._primary_client is None:
            raise RuntimeError("主客户端未初始化")

        response = self._primary_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response

    def _call_fallback(self, messages: List[Dict], temperature: float) -> Any:
        """调用降级客户端（DeepSeek 网页端）"""
        if self._web_client is None:
            raise RuntimeError("降级客户端未配置")

        response = self._web_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response

    def _call(self, messages: List[Dict], temperature: float) -> Any:
        """统一调用入口 — 自动降级"""
        # 如果已经在降级模式，直接调用降级客户端
        if self._fallback_mode:
            return self._call_fallback(messages, temperature)

        # 尝试主客户端
        try:
            response = self._call_primary(messages, temperature)
            self._error_count = 0  # 重置错误计数
            return response
        except Exception as e:
            self._error_count += 1
            logger.warning(f"主客户端调用失败 ({self._error_count}/{self._max_errors}): {str(e)[:100]}")

            # 检查是否应该降级
            if self._should_fallback(e) or self._error_count >= self._max_errors:
                if self._web_client is not None:
                    logger.info("切换到 DeepSeek 网页端降级模式")
                    self._fallback_mode = True
                    return self._call_fallback(messages, temperature)
                else:
                    raise
            else:
                raise

    class _Chat:
        """模拟 openai.Chat 接口"""
        def __init__(self, client):
            self.completions = FallbackLLMClient._Completions(client)

    class _Completions:
        """模拟 openai.Chat.Completions 接口"""
        def __init__(self, client: "FallbackLLMClient"):
            self._client = client

        def create(
            self,
            model: str = "deepseek-chat",
            messages: List[Dict] = None,
            temperature: float = 0.3,
            max_tokens: Optional[int] = None,
            stream: bool = False,
            **kwargs
        ):
            """创建聊天补全 — 与 openai SDK 完全兼容"""
            return self._client._call(messages or [], temperature)


def create_llm_client() -> FallbackLLMClient:
    """
    根据配置自动创建 LLM 客户端

    优先级:
    1. API Key 模式（如果配置了有效的 API Key）
    2. DeepSeek 网页端模式（如果配置了 DEEPSEEK_USER_TOKEN）
    3. 抛出异常（如果都没有配置）

    返回:
        FallbackLLMClient 实例
    """
    from config import (
        get_next_api_key, MODEL, BASE_URL,
        is_api_key_configured, has_deepseek_web_fallback,
        get_deepseek_web_client,
    )

    api_key = None
    if is_api_key_configured():
        api_key = get_next_api_key()

    web_client = None
    if has_deepseek_web_fallback():
        try:
            web_client = get_deepseek_web_client()
            logger.info("DeepSeek 网页端备用客户端已就绪")
        except Exception as e:
            logger.warning(f"DeepSeek 网页端客户端初始化失败: {e}")

    if not api_key and not web_client:
        raise ValueError(
            "LLM 未配置！请至少配置以下之一：\n"
            "  1. 在 .env 中设置 LLM_API_KEYS（DeepSeek API Key）\n"
            "  2. 在 .env 中设置 DEEPSEEK_USER_TOKEN（网页端备用）"
        )

    return FallbackLLMClient(
        api_key=api_key,
        model=MODEL,
        base_url=BASE_URL,
        web_client=web_client,
    )
