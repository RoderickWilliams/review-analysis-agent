"""OpenAI-compatible client with bounded, per-request key failover."""
from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Optional


class LLMNotConfigured(RuntimeError):
    pass


class AnthropicClient:
    def __init__(self, key, base_url, timeout):
        self.key, self.base_url, self.timeout = key, base_url.rstrip("/"), timeout
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        import httpx
        messages = kwargs["messages"]
        response = httpx.post(self.base_url + "/messages", headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                              json={"model": kwargs["model"], "max_tokens": kwargs.get("max_tokens", 2048),
                                    "system": "\n".join(m["content"] for m in messages if m["role"] == "system"),
                                    "messages": [m for m in messages if m["role"] != "system"]}, timeout=self.timeout, follow_redirects=False)
        if response.status_code != 200:
            error = RuntimeError("模型供应商请求未完成")
            error.status_code = response.status_code
            raise error
        data = response.json()
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        usage = data.get("usage", {})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
                               usage=SimpleNamespace(prompt_tokens=usage.get("input_tokens"), completion_tokens=usage.get("output_tokens")))


class RotatingClient:
    def __init__(self, keys, base_url, timeout, max_retries, ledger=None):
        from openai import OpenAI

        self._clients = [OpenAI(api_key=k, base_url=base_url, timeout=timeout, max_retries=max_retries) for k in keys]
        if base_url and base_url.rstrip("/") == "https://api.anthropic.com/v1":
            self._clients = [AnthropicClient(key, base_url, timeout) for key in keys]
        if ledger is not None:
            from reviewagent.model_budget import BudgetClient
            self._clients = [BudgetClient(client, ledger) for client in self._clients]
        self._index = 0
        self._lock = threading.Lock()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        with self._lock:
            start = self._index
        last_error = None
        for offset in range(len(self._clients)):
            index = (start + offset) % len(self._clients)
            try:
                response = self._clients[index].chat.completions.create(**kwargs)
                with self._lock:
                    self._index = index
                return response
            except Exception as exc:
                last_error = exc
                if getattr(exc, "status_code", None) not in {401, 402, 403, 429}:
                    raise
        raise RuntimeError("所有已配置模型通道均暂不可用，请检查配额或稍后重试") from last_error


def create_llm_client(api_key: Optional[str] = None, base_url: Optional[str] = None,
                      timeout: Optional[float] = None, max_retries: Optional[int] = None):
    from reviewagent import config

    keys = [api_key] if api_key else list(config.API_KEYS)
    if not keys:
        raise LLMNotConfigured("未配置模型。请设置 REVIEWAGENT_API_KEYS 或 DEEPSEEK_API_KEY。")
    return RotatingClient(keys, base_url or config.BASE_URL,
                          config.LLM_TIMEOUT if timeout is None else timeout,
                          config.LLM_MAX_RETRIES if max_retries is None else max_retries)
