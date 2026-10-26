# -*- coding: utf-8 -*-
"""HTTP API：分析、Trust Report、健康检查与历史 CRUD。"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from reviewagent.http_api import app  # noqa: E402
from reviewagent.llm import LLMNotConfigured  # noqa: E402

client = TestClient(app)


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["llm_configured"] is True


def test_config_endpoint_does_not_leak_key():
    resp = client.get("/v1/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key_count"] >= 1
    assert "sk-test" not in resp.text


def test_analyze_success(monkeypatch):
    monkeypatch.setattr(
        "reviewagent.pipeline.analyze_reviews",
        lambda reviews, name, **kw: {"review_count": len(reviews), "report": {}, "trust_report": {}},
    )
    resp = client.post("/v1/analyze", json={"reviews": [{"review_text": "很好"}], "product_name": "X"})
    assert resp.status_code == 200
    assert resp.json()["review_count"] == 1


def test_analyze_without_llm_returns_503(monkeypatch):
    def _boom(*args, **kwargs):
        raise LLMNotConfigured("no key")

    monkeypatch.setattr("reviewagent.pipeline.analyze_reviews", _boom)
    resp = client.post("/v1/analyze", json={"reviews": [{"review_text": "很好"}]})
    assert resp.status_code == 503


def test_analyze_empty_reviews_returns_422():
    resp = client.post("/v1/analyze", json={"reviews": []})
    assert resp.status_code == 422


def test_trust_report_endpoint():
    resp = client.post(
        "/v1/trust-report",
        json={"reviews": [{"review_text": "好评！质量很好，物流很快"}, {"review_text": "好评！质量很好，物流很快"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "overall_trust_score" in body
    assert body["duplicate_groups"]


def test_history_crud_via_api():
    from reviewagent import store

    store.save_history_record({"id": "h1", "product_name": "历史品", "review_count": 2})
    listed = client.get("/v1/history").json()
    assert listed["total"] >= 1
    assert any(item["id"] == "h1" for item in listed["items"])

    one = client.get("/v1/history/h1")
    assert one.status_code == 200
    assert one.json()["product_name"] == "历史品"

    assert client.get("/v1/history/missing").status_code == 404
    assert client.delete("/v1/history/h1").status_code == 200
    assert client.get("/v1/history/h1").status_code == 404
