# -*- coding: utf-8 -*-
"""llm：无 Key 必须报错，显式 Key 才能构造客户端。"""
from __future__ import annotations

import pytest

from reviewagent import config
from reviewagent.llm import LLMNotConfigured, create_llm_client


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(config, "API_KEYS", [])
    monkeypatch.setattr(config, "API_KEY", None)
    monkeypatch.setattr(config, "_key_cycle", None)
    with pytest.raises(LLMNotConfigured):
        create_llm_client()


def test_explicit_key_returns_client():
    pytest.importorskip("openai")
    client = create_llm_client(api_key="sk-test-0123456789abcdef")
    assert hasattr(client, "chat")


def test_llm_not_configured_is_runtime_error():
    assert issubclass(LLMNotConfigured, RuntimeError)
