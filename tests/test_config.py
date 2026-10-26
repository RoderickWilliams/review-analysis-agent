# -*- coding: utf-8 -*-
"""config：路径、Key 解析、网页通道已移除的兼容符号。"""
from __future__ import annotations

import pytest

from reviewagent import config


def test_home_points_to_test_dir():
    assert config.HOME_DIR.name.startswith("reviewagent-test-")
    assert config.DATA_DIR.parent == config.HOME_DIR
    assert config.DB_PATH.name == "reviewagent.db"


def test_api_keys_parsed():
    assert len(config.API_KEYS) >= 1
    assert config.API_KEY == config.API_KEYS[0]
    assert len(config.API_KEY) >= 16


def test_llm_configured():
    assert config.is_llm_configured() is True


def test_parse_api_keys_rejects_short_and_duplicates(monkeypatch):
    monkeypatch.setenv(
        "REVIEWAGENT_API_KEYS",
        "sk-good-0123456789abcdef,short,sk-good-0123456789abcdef",
    )
    for name in ("LLM_API_KEYS", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    keys = config._parse_api_keys()
    assert keys == ["sk-good-0123456789abcdef"]


def test_web_mode_is_gone():
    assert config.is_web_mode() is False
    assert config.is_web_configured() is False
    with pytest.raises(RuntimeError):
        config.get_web_client()
    with pytest.raises(RuntimeError):
        config.get_deepseek_web_client()


def test_print_config_status_never_prints_key(capsys):
    config.print_config_status()
    out = capsys.readouterr().out
    assert "API Key" in out
    assert config.API_KEYS[0] not in out


def test_ensure_dirs_creates_data_output():
    config.ensure_dirs()
    assert config.DATA_DIR.is_dir()
    assert config.OUTPUT_DIR.is_dir()
    assert config.REPORTS_DIR.is_dir()
