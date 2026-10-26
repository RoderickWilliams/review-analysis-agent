# -*- coding: utf-8 -*-
"""LLM 客户端工厂（仅官方 API）

所有调用统一走 OpenAI 兼容的 `chat.completions` 接口。ReviewAgent 不再包含
网页版登录、access_token、PoW 或 Cloudflare 绕过逻辑。
"""
from __future__ import annotations

from typing import Optional


class LLMNotConfigured(RuntimeError):
    """没有可用的 API Key 时抛出。"""


def create_llm_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
):
    """创建 OpenAI 兼容客户端。

    :param api_key: 显式指定 Key；缺省时从配置的 Key 池轮换取用。
    :param base_url: 兼容网关地址；缺省用配置值。
    :raises LLMNotConfigured: 未配置任何 Key。
    """
    from reviewagent import config

    key = api_key or config.get_next_api_key()
    if not key:
        raise LLMNotConfigured(
            "未配置 API Key。请设置环境变量 REVIEWAGENT_API_KEYS（或 OPENAI_API_KEY / DEEPSEEK_API_KEY）后重试。"
        )
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - 依赖缺失路径
        raise LLMNotConfigured("缺少 openai 依赖，请先执行 pip install -e .[llm]") from exc

    return OpenAI(
        api_key=key,
        base_url=base_url or config.BASE_URL,
        timeout=timeout if timeout is not None else config.LLM_TIMEOUT,
        max_retries=max_retries if max_retries is not None else config.LLM_MAX_RETRIES,
    )
