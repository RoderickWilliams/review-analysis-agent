# -*- coding: utf-8 -*-
"""测试基座：在导入 reviewagent 之前把数据目录指向临时目录。

关键点：config 在导入时读取环境变量并计算 HOME/DATA/OUTPUT，
所以环境变量必须在任何 reviewagent 模块被导入之前设置。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TEST_HOME = Path(tempfile.mkdtemp(prefix="reviewagent-test-"))

os.environ["REVIEWAGENT_HOME"] = str(_TEST_HOME)
os.environ["REVIEWAGENT_LLM_CACHE"] = "0"
os.environ.pop("REVIEWAGENT_ACCESS_TOKEN", None)
os.environ["REVIEWAGENT_ENABLE_SCRAPING"] = "0"
os.environ["REVIEWAGENT_MIGRATE_LEGACY_HISTORY"] = "0"
os.environ["REVIEWAGENT_MODEL"] = "test-model"
os.environ["REVIEWAGENT_API_KEYS"] = "sk-test-0123456789abcdef0123456789abcdef"

from reviewagent import config, store  # noqa: E402
from reviewagent.trust_report import TrustReportEngine  # noqa: E402

config.ensure_dirs()


def pytest_sessionfinish(session, exitstatus):  # pragma: no cover - 清理临时目录
    shutil.rmtree(_TEST_HOME, ignore_errors=True)


@pytest.fixture()
def fake_client():
    from tests.fakes import FakeLLMClient

    return FakeLLMClient()


@pytest.fixture()
def agent(fake_client):
    from reviewagent.sentiment_agent_core import ReviewAnalysisAgent

    return ReviewAnalysisAgent(model="test-model", client=fake_client)


@pytest.fixture()
def fake_agent():
    from tests.fakes import FakeAgent

    return FakeAgent()


@pytest.fixture()
def sample_reviews():
    return [
        {"review_text": "用了两周，续航确实给力，重度使用能撑一天半，充电也快，很满意", "rating": 5, "platform": "淘宝", "review_date": "2026-10-01"},
        {"review_text": "这手机真是太好了，卡顿得让我学会了冥想，等待是一种修行", "rating": 5, "platform": "京东", "review_date": "2026-10-01"},
        {"review_text": "外观确实好看，放在桌上当摆件挺好的", "rating": 4, "platform": "淘宝", "review_date": "2026-10-02"},
        {"review_text": "质量太差了，用了一周就坏了，客服也不理人，千万别买", "rating": 1, "platform": "淘宝", "review_date": "2026-10-02"},
        {"review_text": "信号一般，地铁里经常断流，其他还行", "rating": 3, "platform": "京东", "review_date": "2026-10-03"},
    ]


@pytest.fixture()
def duplicate_reviews():
    text = "好评！质量很好，物流很快，卖家态度好，下次还来！"
    return [
        {"review_text": text, "rating": 5, "review_date": "2026-10-01"},
        {"review_text": text, "rating": 5, "review_date": "2026-10-01"},
        {"review_text": "包装有点破损，机器本身没问题，用着还行", "rating": 4, "review_date": "2026-10-02"},
        {"review_text": "续航一般，一天两充，不太适合出差", "rating": 2, "review_date": "2026-10-03"},
    ]


@pytest.fixture(autouse=True)
def _clean_state():
    """每个测试前后清空历史，避免相互干扰。"""
    store.init_db()
    store.clear_history()
    yield
    store.clear_history()


@pytest.fixture()
def trust_engine():
    return TrustReportEngine()

@pytest.fixture(autouse=True)
def _deny_external_network(monkeypatch):
    import socket
    def denied(*args, **kwargs):
        raise AssertionError("离线测试禁止外部网络连接；请注入测试替身")
    monkeypatch.setattr(socket, "create_connection", denied)
