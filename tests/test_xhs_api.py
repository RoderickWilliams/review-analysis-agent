# -*- coding: utf-8 -*-
"""HTTP API 的小红书端点（离线，monkeypatch 采集与流水线）。"""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from reviewagent import http_api
from reviewagent.scrapers import xhs_reader


CAPTURE = {
    "platform": "小红书",
    "run_dir": "E:/tmp/xhs-run",
    "captured_at": "2026-10-26T22:00:00",
    "notes": [{"note_id": "n1", "title": "粉底液实测", "source_url": "https://example.com/n1", "stats": {"liked": 3}, "comments": [{"comment_id": "c1"}]}],
    "reviews": [{"review_text": "闷痘", "comment_id": "c1", "source_platform": "小红书"}],
    "stats": {"notes": 1, "comments": 1},
    "warnings": [],
}


@pytest.fixture(autouse=True)
def enable_capture_for_adapter_contracts(monkeypatch):
    monkeypatch.setattr(http_api.config, "SCRAPING_ENABLED", True)


def test_disabled_capture_never_calls_adapter(monkeypatch):
    monkeypatch.setattr(http_api.config, "SCRAPING_ENABLED", False)
    def unexpected(**kwargs):
        pytest.fail("Disabled capture must not reach the adapter")
    monkeypatch.setattr(xhs_reader, "capture", unexpected)
    assert TestClient(http_api.app).post("/v1/xhs/capture", json={"keyword": "离线样本"}).status_code == 409


def test_xhs_status(monkeypatch):
    monkeypatch.setattr(xhs_reader, "status", lambda: {"available": True, "logged_in": False})
    client = TestClient(http_api.app)
    body = client.get("/v1/xhs/status").json()
    assert body["available"] is True


def test_xhs_capture_requires_source():
    client = TestClient(http_api.app)
    assert client.post("/v1/xhs/capture", json={}).status_code == 400


def test_xhs_capture_returns_notes(monkeypatch):
    monkeypatch.setattr(xhs_reader, "capture", lambda **kwargs: dict(CAPTURE))
    client = TestClient(http_api.app)
    response = client.post("/v1/xhs/capture", json={"keyword": "粉底液"})
    assert response.status_code == 200
    body = response.json()
    assert body["notes"][0]["comment_count"] == 1
    assert body["reviews"][0]["comment_id"] == "c1"


def test_xhs_capture_maps_login_error(monkeypatch):
    def boom(**kwargs):
        raise xhs_reader.XhsLoginRequired("请先扫码登录")

    monkeypatch.setattr(xhs_reader, "capture", boom)
    client = TestClient(http_api.app)
    response = client.post("/v1/xhs/capture", json={"keyword": "粉底液"})
    assert response.status_code == 409
    assert "扫码" in response.json()["detail"]


def test_xhs_analyze_delegates(monkeypatch):
    import reviewagent.pipeline as pipeline

    monkeypatch.setattr(pipeline, "analyze_xhs", lambda capture, name=None, **kw: {"pain_report": {"verified_count": 1}, "product_name": name})
    client = TestClient(http_api.app)
    response = client.post("/v1/xhs/analyze", json={"capture": CAPTURE, "product_name": "粉底液"})
    assert response.status_code == 200
    assert response.json()["product_name"] == "粉底液"


def test_xhs_analyze_requires_payload():
    client = TestClient(http_api.app)
    assert client.post("/v1/xhs/analyze", json={}).status_code == 400
