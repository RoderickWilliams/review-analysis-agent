# -*- coding: utf-8 -*-
"""HTTP API（FastAPI）：把同一分析内核暴露给其他服务与 DSH 插件。

启动：`reviewagent serve --port 8000`；交互文档位于 /docs。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from reviewagent import __version__, config

app = FastAPI(
    title="ReviewAgent API",
    version=__version__,
    description="跨平台用户反馈智能分析：情绪识别、有效性检测、Trust Report。",
)

WEBUI_DIR = Path(__file__).resolve().parent / "webui"


# ── 模型 ──────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    reviews: List[Dict[str, Any]] = Field(..., min_length=1, max_length=200)
    product_name: str = "产品"
    save_history: bool = False


class XhsCaptureRequest(BaseModel):
    keyword: str = ""
    user: str = ""
    links: List[str] = Field(default_factory=list)
    limit: int = Field(20, ge=1, le=50)
    with_comments: bool = True
    sort: str = ""
    sweep: bool = False
    note_type: str = ""
    with_ocr: Optional[bool] = None
    max_images: Optional[int] = Field(None, ge=1, le=50)
    out_dir: str = ""


class XhsAnalyzeRequest(BaseModel):
    capture: Optional[Dict[str, Any]] = None
    run_dir: str = ""
    product_name: str = ""
    save_history: bool = False
    limit_topics: int = Field(10, ge=1, le=20)


class TrustReportRequest(BaseModel):
    reviews: List[Dict[str, Any]] = Field(..., min_length=1, max_length=500)
    results: List[Dict[str, Any]] = Field(default_factory=list)


# ── 基础 ──────────────────────────────────────────────────────

@app.get("/healthz", summary="健康检查")
def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "model": config.MODEL,
        "llm_configured": config.is_llm_configured(),
        "data_dir": str(config.DATA_DIR),
    }


@app.get("/v1/config", summary="只读配置（不含密钥）")
def read_config() -> Dict[str, Any]:
    return {
        "version": __version__,
        "model": config.MODEL,
        "base_url": config.BASE_URL,
        "llm_configured": config.is_llm_configured(),
        "api_key_count": len(config.API_KEYS),
        "similarity_high": config.SIMILARITY_HIGH,
        "similarity_medium": config.SIMILARITY_MEDIUM,
    }


# ── 分析 ──────────────────────────────────────────────────────

@app.post("/v1/analyze", summary="批量分析评论")
def analyze(payload: AnalyzeRequest) -> Dict[str, Any]:
    from reviewagent.llm import LLMNotConfigured
    from reviewagent.pipeline import analyze_reviews

    try:
        result = analyze_reviews(
            payload.reviews,
            payload.product_name,
            save_history=payload.save_history,
            source="api",
        )
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.post("/v1/trust-report", summary="仅生成 Trust Report")
def trust_report(payload: TrustReportRequest) -> Dict[str, Any]:
    from reviewagent.trust_report import TrustReportEngine

    return TrustReportEngine().generate_report(payload.reviews, payload.results)



# ── 小红书 ────────────────────────────────────────────────────

def _xhs_http_error(exc: Exception) -> HTTPException:
    from reviewagent.scrapers import xhs_reader

    if isinstance(exc, xhs_reader.XhsLoginRequired):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, xhs_reader.XhsUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, xhs_reader.XhsError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


@app.get("/v1/xhs/status", summary="小红书采集端与登录状态")
def xhs_status() -> Dict[str, Any]:
    from reviewagent.scrapers import xhs_reader

    return xhs_reader.status()


@app.post("/v1/xhs/capture", summary="小红书只读采集（笔记 + 评论 + OCR）")
def xhs_capture(payload: XhsCaptureRequest) -> Dict[str, Any]:
    from reviewagent.scrapers import xhs_reader

    if not (payload.keyword or payload.user or payload.links):
        raise HTTPException(status_code=400, detail="请提供 keyword / user / links 之一")
    try:
        capture = xhs_reader.capture(
            links=payload.links or None,
            keyword=payload.keyword,
            user=payload.user,
            limit=payload.limit,
            with_comments=payload.with_comments,
            out_dir=payload.out_dir or None,
            sort=payload.sort,
            sweep=payload.sweep,
            note_type=payload.note_type,
            with_ocr=payload.with_ocr,
            max_images=payload.max_images,
        )
    except Exception as exc:
        raise _xhs_http_error(exc) from exc

    notes = capture.get("notes") or []
    return {
        "run_dir": capture.get("run_dir", ""),
        "platform": capture.get("platform", "小红书"),
        "captured_at": capture.get("captured_at", ""),
        "stats": capture.get("stats") or {},
        "warnings": capture.get("warnings") or [],
        "notes": [
            {
                "note_id": note.get("note_id"),
                "title": note.get("title"),
                "type": note.get("type"),
                "source_url": note.get("source_url"),
                "author": (note.get("author") or {}).get("nickname", ""),
                "published_at": note.get("published_at", ""),
                "stats": note.get("stats") or {},
                "comment_count": len(note.get("comments") or []),
            }
            for note in notes
        ],
        "reviews": capture.get("reviews") or [],
    }


@app.post("/v1/xhs/analyze", summary="小红书六章分析：情绪/可信度/痛点/改进/选题/内容生产包")
def xhs_analyze(payload: XhsAnalyzeRequest) -> Dict[str, Any]:
    from reviewagent.llm import LLMNotConfigured
    from reviewagent.pipeline import analyze_xhs
    from reviewagent.scrapers import xhs_reader

    capture = payload.capture
    if payload.run_dir:
        try:
            capture = xhs_reader.load_run(payload.run_dir)
        except Exception as exc:
            raise _xhs_http_error(exc) from exc
    if not capture:
        raise HTTPException(status_code=400, detail="请提供 capture 对象或 run_dir")

    try:
        return analyze_xhs(
            capture,
            payload.product_name or None,
            save_history=payload.save_history,
            source="api",
            limit_topics=payload.limit_topics,
        )
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── 历史 ──────────────────────────────────────────────────────

def _history_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "id", "timestamp", "timestamp_display", "source", "platform", "url",
        "product_name", "review_count", "sarcastic_count", "suspicious_count",
        "avg_trust_score", "html_report_path",
    )
    return {k: record.get(k) for k in keys}


@app.get("/v1/history", summary="历史记录列表")
def list_history(
    limit: int = Query(20, ge=1, le=500),
    include_payload: bool = False,
) -> Dict[str, Any]:
    from reviewagent.history_manager import load_history

    records = load_history()[:limit]
    return {
        "total": len(records),
        "items": records if include_payload else [_history_summary(r) for r in records],
    }


@app.get("/v1/history/{record_id}", summary="单条历史记录")
def get_history(record_id: str) -> Dict[str, Any]:
    from reviewagent import store

    record = store.get_history(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


@app.delete("/v1/history/{record_id}", summary="删除历史记录")
def delete_history(record_id: str) -> Dict[str, Any]:
    from reviewagent.history_manager import delete_record

    if not delete_record(record_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"deleted": record_id}


# ── 本地 Web UI（静态单页，与 API 同源） ──────────────────────

@app.get("/", include_in_schema=False)
def webui_root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


if WEBUI_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=str(WEBUI_DIR), html=True), name="webui")
