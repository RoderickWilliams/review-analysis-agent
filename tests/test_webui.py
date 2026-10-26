# -*- coding: utf-8 -*-
"""本地 Web UI：与 API 同源挂载，页面不依赖外部 CDN。"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from reviewagent.http_api import WEBUI_DIR, app  # noqa: E402

client = TestClient(app)


def test_webui_assets_exist():
    assert (WEBUI_DIR / "index.html").is_file()
    assert (WEBUI_DIR / "styles.css").is_file()
    assert (WEBUI_DIR / "app.js").is_file()


def test_root_redirects_to_app():
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/app/"


def test_webui_index_served():
    resp = client.get("/app/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "ReviewAgent" in resp.text
    assert "跨平台口碑工作台" in resp.text
    assert "analyze-form" in resp.text


def test_webui_css_and_js_served():
    css = client.get("/app/styles.css")
    assert css.status_code == 200
    assert "--surface" in css.text
    js = client.get("/app/app.js")
    assert js.status_code == 200
    assert "activateTab" in js.text


def test_webui_has_no_external_cdn_assets():
    html = (WEBUI_DIR / "index.html").read_text(encoding="utf-8")
    assert '<script src="http' not in html
    assert '<link rel="stylesheet" href="http' not in html
    assert "@import url(http" not in html
