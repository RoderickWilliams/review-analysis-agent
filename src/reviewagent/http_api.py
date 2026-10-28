# -*- coding: utf-8 -*-
"""HTTP API（FastAPI）：把同一分析内核暴露给其他服务与 DSH 插件。

启动：`reviewagent serve --port 8000`；交互文档位于 /docs。
"""
from __future__ import annotations

import csv
import io
import uuid
import json
import hmac
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, File, Form, UploadFile, Request
from fastapi.responses import RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr, field_validator

from reviewagent import __version__, config
from reviewagent.review_data import normalize_reviews, csv_safe

app = FastAPI(
    title="ReviewAgent API",
    version=__version__,
    description="跨平台用户反馈智能分析：情绪识别、有效性检测、Trust Report。",
)

WEBUI_DIR = Path(__file__).resolve().parent / "webui"


# ── 模型 ──────────────────────────────────────────────────────

class ReviewsPayload(BaseModel):
    @field_validator("reviews", check_fields=False)
    @classmethod
    def validate_reviews(cls, value):
        return normalize_reviews(value)


class AnalyzeRequest(ReviewsPayload):
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


class TrustReportRequest(ReviewsPayload):
    reviews: List[Dict[str, Any]] = Field(..., min_length=1, max_length=5000)
    results: List[Dict[str, Any]] = Field(default_factory=list)


class ObjectResolveRequest(BaseModel):
    input: str = Field(..., min_length=1, max_length=2000)


class AnalysisCreateRequest(ReviewsPayload):
    input: str = Field(..., min_length=1, max_length=2000)
    extra_links: List[str] = Field(default_factory=list, max_length=20)
    ownership: str = Field("own", pattern="^(own|competitor)$")
    tier: str = Field("standard", pattern="^(light|standard|deep|custom)$")
    window_months: int = Field(12, ge=1, le=60)
    reviews: List[Dict[str, Any]] = Field(default_factory=list, max_length=5000)
    save: bool = True
    platforms: List[str] = Field(default_factory=lambda: ["jd", "taobao", "xhs"], max_length=3)
    candidate_limit: int = Field(5, ge=1, le=20)
    per_product_limit: int = Field(300, ge=1, le=500)


# ── 基础 ──────────────────────────────────────────────────────

@app.get("/healthz", summary="健康检查")
def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "model": config.MODEL,
        "llm_configured": config.is_llm_configured(),
        "scraping_enabled": config.SCRAPING_ENABLED,
        "browser_preference": config.BROWSER_PREFERENCE,
        "browser_network": config.BROWSER_NETWORK,
    }


@app.get("/v1/config", summary="只读配置（不含密钥）")
def read_config() -> Dict[str, Any]:
    return {
        "version": __version__,
        "model": config.MODEL,
        "custom_gateway": bool(config.BASE_URL),
        "llm_configured": config.is_llm_configured(),
        "api_key_count": len(config.API_KEYS),
        "scraping_enabled": config.SCRAPING_ENABLED,
        "browser_preference": config.BROWSER_PREFERENCE,
        "browser_network": getattr(config, "BROWSER_NETWORK", "direct"),
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
    if not config.SCRAPING_ENABLED:
        raise HTTPException(status_code=409, detail="采集尚未开启，可先导入评论")
    from reviewagent.scrapers import xhs_reader

    if not (payload.keyword or payload.user or payload.links):
        raise HTTPException(status_code=400, detail="请提供 keyword / user / links 之一")
    if payload.out_dir:
        _output_path(payload.out_dir)
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
        _output_path(payload.run_dir)
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


# ── v2 对象解析与报告骨架 ─────────────────────────────────────

def _analysis_id() -> str:
    return "ra_" + uuid.uuid4().hex[:12]


def _run_analysis(payload: AnalysisCreateRequest) -> Dict[str, Any]:
    from reviewagent.analysis_tasks import create_record
    if not payload.input.strip():
        raise HTTPException(status_code=422, detail="请输入商品链接或商品名")
    return create_record(payload.model_dump())


def _analysis_or_404(analysis_id: str) -> Dict[str, Any]:
    from reviewagent.analysis_tasks import get_record
    try:
        return get_record(analysis_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="分析任务不存在") from None


@app.post("/v1/object/resolve", summary="解析商品链接 / 商品名，返回对象与候选")
def object_resolve(payload: ObjectResolveRequest) -> Dict[str, Any]:
    from reviewagent.object_resolver import resolve_object
    from reviewagent.same_product import build_same_products

    obj = resolve_object(payload.input.strip())
    match_result = build_same_products(obj)
    return {
        "object": obj,
        "candidates": match_result["candidates"],
        "match_summary": match_result["summary"],
    }


@app.post("/v1/analysis", summary="创建对象分析：解析 + 同款匹配 + 报告骨架")
def create_analysis(payload: AnalysisCreateRequest) -> Dict[str, Any]:
    try:
        return _run_analysis(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.get("/v1/analysis", summary="分析任务列表")
def list_analysis(limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    from reviewagent import store

    items = store.list_analyses(limit)
    return {
        "total": len(items),
        "items": [
            {
                "analysis_id": item.get("analysis_id"),
                "created_at": item.get("created_at"),
                "status": item.get("status"),
                "status_label": item.get("status_label"),
                "input": item.get("input"),
                "title": (item.get("object") or {}).get("title"),
                "platform": (item.get("object") or {}).get("platform"),
                "review_count": len(item.get("reviews") or []),
                "statistics": (item.get("report") or {}).get("statistics", {}),
            }
            for item in items
        ],
    }


@app.delete("/v1/analysis", summary="清除分析历史，可撤销；不影响运行中的任务")
def clear_analysis_history():
    from reviewagent.analysis_tasks import clear_saved_records
    try:
        return clear_saved_records()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


class RestoreHistoryRequest(BaseModel):
    batch_id: str = Field(..., pattern="^clear_[0-9a-f]{32}$")


@app.post("/v1/analysis/restore", summary="撤销一次历史清除")
def restore_analysis_history(payload: RestoreHistoryRequest):
    from reviewagent import store
    return {"restored": store.restore_analyses(payload.batch_id)}


@app.get("/v1/analysis/{analysis_id}", summary="分析任务状态与对象")
def get_analysis(analysis_id: str) -> Dict[str, Any]:
    analysis = _analysis_or_404(analysis_id)
    return analysis


@app.get("/v1/analysis/{analysis_id}/report", summary="完整报告 JSON")
def get_analysis_report(analysis_id: str) -> Dict[str, Any]:
    analysis = _analysis_or_404(analysis_id)
    report = dict(analysis.get("report") or {})
    report["analysis_id"] = analysis.get("analysis_id")
    report["object"] = analysis.get("object")
    report["candidates"] = analysis.get("candidates")
    return report


@app.get("/v1/analysis/{analysis_id}/actions.csv", summary="行动清单 CSV")
def get_analysis_actions_csv(analysis_id: str) -> Response:
    analysis = _analysis_or_404(analysis_id)
    report = analysis.get("report") or {}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["优先级", "动作", "依据", "验证指标", "负责人", "截止时间"])
    for action in report.get("actions") or []:
        if not isinstance(action, dict):
            continue
        writer.writerow([csv_safe(value) for value in [
            action.get("priority", ""),
            action.get("label", ""),
            action.get("detail", ""),
            action.get("metric", ""),
            action.get("owner", ""),
            action.get("due", ""),
        ]])
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="actions-{analysis_id}.csv"'},
    )


@app.get("/v1/analysis/{analysis_id}/evidence/{ref}", summary="证据详情")
def get_analysis_evidence(analysis_id: str, ref: str) -> Dict[str, Any]:
    analysis = _analysis_or_404(analysis_id)
    report = analysis.get("report") or {}
    for item in report.get("evidence") or []:
        if str(item.get("id")) == ref:
            return item
    raise HTTPException(status_code=404, detail="证据不存在")


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




@app.middleware("http")
async def access_control(request: Request, call_next):
    token = os.environ.get("REVIEWAGENT_ACCESS_TOKEN", "")
    if token and request.url.path.startswith("/v1"):
        authorization = request.headers.get("authorization", "")
        supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8")):
            return JSONResponse({"detail": "需要服务访问令牌"}, status_code=401)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/app/"):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


def _output_path(value):
    candidate = Path(value).expanduser().resolve()
    if not candidate.is_relative_to(config.OUTPUT_DIR.resolve()):
        raise HTTPException(status_code=400, detail="文件路径必须位于当前服务的 output 目录内")
    return candidate


class AttachReviewsRequest(ReviewsPayload):
    reviews: List[Dict[str, Any]] = Field(..., min_length=1, max_length=5000)
    append: bool = False


class TaskRequest(BaseModel):
    operation: str = Field("analyze", pattern="^(analyze|collect|discover|operations|generate_actions|generate_selling_point|generate_support_script|generate_content_topic|generate_schedule|login_jd|login_taobao|login_xhs)$")


class SettingsRequest(BaseModel):
    discovery_platform: Optional[str] = Field(None, pattern="^(jd|taobao|xhs)$")
    selected_urls: Optional[List[str]] = Field(None, max_length=20)
    ownership: Optional[str] = Field(None, pattern="^(own|competitor)$")
    tier: Optional[str] = Field(None, pattern="^(light|standard|deep|custom)$")
    window_months: Optional[int] = Field(None, ge=1, le=60)
    extra_links: Optional[List[str]] = Field(None, max_length=20)
    platforms: Optional[List[str]] = Field(None, max_length=3)
    candidate_limit: Optional[int] = Field(None, ge=1, le=20)
    per_product_limit: Optional[int] = Field(None, ge=1, le=500)


@app.post("/v1/import/preview", summary="预览文件并映射评论字段")
async def preview_import(file: UploadFile = File(...), mapping: str = Form("{}")):
    from reviewagent.import_reviews import MAX_UPLOAD, parse_upload
    from starlette.concurrency import run_in_threadpool
    try:
        content = await file.read(MAX_UPLOAD + 1)
        fields = json.loads(mapping)
        if not isinstance(fields, dict):
            raise ValueError("字段映射必须是对象")
        return await run_in_threadpool(parse_upload, file.filename or "reviews.csv", content, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    finally:
        await file.close()


@app.post("/v1/analysis/{analysis_id}/reviews", summary="保存评论样本，不自动调用模型")
def attach_analysis_reviews(analysis_id: str, payload: AttachReviewsRequest):
    from reviewagent.analysis_tasks import attach_reviews
    _analysis_or_404(analysis_id)
    try:
        return attach_reviews(analysis_id, payload.reviews, append=payload.append)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@app.post("/v1/analysis/{analysis_id}/run", status_code=202, summary="显式启动分析、采集或运营任务")
def start_analysis_task(analysis_id: str, payload: TaskRequest):
    from reviewagent.analysis_tasks import start
    _analysis_or_404(analysis_id)
    try:
        return start(analysis_id, payload.operation)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@app.post("/v1/analysis/{analysis_id}/cancel", summary="取消后续请求，保留已完成结果")
def cancel_analysis_task(analysis_id: str):
    from reviewagent.analysis_tasks import cancel
    _analysis_or_404(analysis_id)
    return cancel(analysis_id)


@app.patch("/v1/analysis/{analysis_id}", summary="更新归属和采集设置，保留评论与分析")
def update_analysis_settings(analysis_id: str, payload: SettingsRequest):
    from reviewagent.analysis_tasks import mutate_record
    _analysis_or_404(analysis_id)
    changes = payload.model_dump(exclude_none=True)
    extras = None
    if "extra_links" in changes:
        from reviewagent.object_resolver import resolve_object
        extras = [resolve_object(url) for url in changes["extra_links"]]
    def apply(analysis):
        analysis.setdefault("request", {}).update(changes)
        from reviewagent.collection import normalize_scope
        normalize_scope(analysis["request"])
        if extras is not None:
            from reviewagent.same_product import build_same_products
            matched = build_same_products(analysis["object"], extras)
            analysis.update(candidates=matched["candidates"], match_summary=matched["summary"])
    try:
        return mutate_record(analysis_id, apply)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="分析任务不存在") from None


@app.get("/v1/analysis/{analysis_id}/reviews.csv", summary="导出原文、状态、结果与证据链接")
def export_analysis_reviews(analysis_id: str):
    analysis = _analysis_or_404(analysis_id)
    by_id = {item.get("review_id"): item for item in analysis.get("results", [])}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["review_id", "review_text", "rating", "review_date", "platform", "source_url", "status", "sentiment", "is_sarcastic", "validity", "trust_score", "summary"])
    for review in analysis.get("reviews", []):
        result = by_id.get(review["review_id"], {})
        final = result.get("final_analysis") or {}
        writer.writerow([csv_safe(value) for value in [review["review_id"], review["review_text"], review.get("rating"), review.get("review_date"), review.get("platform"), review.get("source_url"), result.get("status", "pending"), final.get("final_sentiment"), (result.get("sentiment_analysis") or {}).get("is_sarcastic"), final.get("final_validity"), final.get("trust_score"), final.get("summary")]])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="reviews-{analysis_id}.csv"'})


@app.get("/v1/analysis/{analysis_id}/report.html", summary="离线完整评论报告")
def export_analysis_html(analysis_id: str):
    from reviewagent.report_generator import HTMLReportGenerator
    analysis = _analysis_or_404(analysis_id)
    gen = HTMLReportGenerator()
    by_id = {r.get("review_id"): r for r in analysis.get("results", [])}
    results = [{**r, **by_id.get(r["review_id"], {"status": "pending"})} for r in analysis.get("reviews", [])]
    report = analysis.get("report") or {}
    html = gen._build_html(analysis["object"].get("title") or analysis["input"], gen._extract_stats(results, report), results, report)
    return Response(html, media_type="text/html; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="report-{analysis_id}.html"', "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


class ActionUpdateRequest(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=500)
    detail: Optional[str] = Field(None, max_length=2000)
    owner: str = Field("", max_length=80)
    due: str = Field("", max_length=10)
    state: str = Field("todo", pattern="^(todo|doing|done)$")
    metric: str = Field("", max_length=1000)

    @field_validator("due")
    @classmethod
    def validate_due(cls, value):
        if value:
            from datetime import date
            date.fromisoformat(value)
        return value


@app.patch("/v1/analysis/{analysis_id}/actions/{action_id}", summary="保存行动负责人、日期、状态与验证指标")
def update_analysis_action(analysis_id: str, action_id: str, payload: ActionUpdateRequest):
    from reviewagent.analysis_tasks import mutate_record
    _analysis_or_404(analysis_id)
    def apply(analysis):
        actions = analysis.get("enrichment", {}).get("actions", [])
        action = next((item for item in actions if item.get("id") == action_id), None)
        if action is None:
            raise HTTPException(status_code=404, detail="行动不存在，请先整理行动计划")
        action.update(payload.model_dump(exclude_none=True))
        action["edited"] = True
        plan = analysis["enrichment"].get("ops_plan", {})
        if plan.get("groups"):
            plan["groups"][0]["items"] = actions
    try:
        return mutate_record(analysis_id, apply)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="分析任务不存在") from None


class SourceIdentityRequest(BaseModel):
    source_url: str = Field("", max_length=2000)
    title: str = Field("", max_length=500)
    brand: str = Field("", max_length=120)
    model: str = Field("", max_length=120)
    key_specs: Dict[str, str] = Field(default_factory=dict, max_length=30)
    specs_confirmed: bool = False
    reviews_scope: str = Field("unknown", pattern="^(unknown|selected_spec)$")

    @field_validator("key_specs")
    @classmethod
    def validate_specs(cls, value):
        if any(not key.strip() or not item.strip() or len(key) > 120 or len(item) > 500 for key, item in value.items()):
            raise ValueError("规格名称与值不能留空，且应为简短、可核对的字段")
        return value


@app.patch("/v1/analysis/{analysis_id}/source-identity", summary="保存来源品牌、型号与关键规格核对结果")
def update_source_identity(analysis_id: str, payload: SourceIdentityRequest):
    from reviewagent.analysis_tasks import mutate_record
    _analysis_or_404(analysis_id)
    if payload.specs_confirmed and not (payload.brand.strip() and payload.model.strip() and payload.key_specs):
        raise HTTPException(status_code=400, detail="确认同款前需填写品牌、型号和关键规格")
    def apply(analysis):
        sources = [analysis["object"]] + list(analysis.get("candidates", []))
        known = any((source.get("url") or source.get("source_url") or "") == payload.source_url for source in sources)
        known = known or any((review.get("source_url") or "") == payload.source_url for review in analysis.get("reviews", []))
        if not known:
            raise HTTPException(status_code=404, detail="此来源不属于当前分析")
        values = payload.model_dump(exclude={"source_url"})
        values["identity_source"] = "user_confirmed" if payload.specs_confirmed else "user_pending"
        analysis.setdefault("source_identities", {})[payload.source_url] = values
        if analysis.get("enrichment"):
            analysis["enrichment"]["source_changed"] = True
    try:
        return mutate_record(analysis_id, apply)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


class DraftUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=10000)
    channel: str = Field("", max_length=120)
    scheduled_date: str = Field("", max_length=10)
    state: str = Field("draft", pattern="^(draft|ready|archived)$")

    @field_validator("scheduled_date")
    @classmethod
    def validate_date(cls, value):
        if value:
            from datetime import date
            date.fromisoformat(value)
        return value


@app.patch("/v1/analysis/{analysis_id}/drafts/{draft_id}", summary="编辑运营草稿，保留证据与商品组")
def update_operation_draft(analysis_id: str, draft_id: str, payload: DraftUpdateRequest):
    from reviewagent.analysis_tasks import mutate_record, now
    _analysis_or_404(analysis_id)
    def apply(analysis):
        draft = next((item for item in analysis.get("enrichment", {}).get("drafts", []) if item.get("id") == draft_id), None)
        if draft is None:
            raise HTTPException(status_code=404, detail="草稿不存在，请先整理运营计划")
        draft.update(payload.model_dump(), edited=True, updated_at=now())
    try:
        return mutate_record(analysis_id, apply)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@app.get("/v1/analysis/{analysis_id}/drafts.csv", summary="导出可编辑运营草稿及证据编号")
def export_operation_drafts(analysis_id: str):
    analysis = _analysis_or_404(analysis_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["类型", "商品组", "标题", "正文", "渠道", "排期日期", "状态", "证据编号", "待确认"])
    for item in analysis.get("enrichment", {}).get("drafts", []):
        writer.writerow([csv_safe(value) for value in [item.get("kind"), item.get("group_title"), item.get("title"),
                         item.get("body"), item.get("channel"), item.get("scheduled_date"), item.get("state"),
                         ";".join(item.get("evidence_ids", [])), item.get("notes")]])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="drafts-{analysis_id}.csv"'})


class DetectModelRequest(BaseModel):
    api_key: SecretStr
    provider: str = "auto"
    base_url: str = Field("", max_length=500)


class CollectionEnabledRequest(BaseModel):
    enabled: Optional[bool] = None
    browser: Optional[str] = Field(None, pattern="^(auto|edge|chrome|firefox)$")
    network: Optional[str] = Field(None, pattern="^(direct|system)$")


@app.post("/v1/collection/configure", summary="用户显式开启或关闭本机平台采集")
def configure_collection(payload: CollectionEnabledRequest):
    from reviewagent.analysis_tasks import _lock, _active
    with _lock:
        if _active:
            raise HTTPException(status_code=409, detail="请先结束运行中的任务")
        if payload.enabled is not None:
            config.SCRAPING_ENABLED = payload.enabled
        if payload.browser is not None:
            config.BROWSER_PREFERENCE = payload.browser
        if payload.network is not None:
            config.BROWSER_NETWORK = payload.network
    return {"enabled": config.SCRAPING_ENABLED, "browser": config.BROWSER_PREFERENCE, "network": config.BROWSER_NETWORK}


class ApplyModelRequest(BaseModel):
    ticket: str = Field(..., max_length=100)
    model: str = Field(..., max_length=200)
    input_price: Optional[float] = Field(None, gt=0, le=100000, allow_inf_nan=False)
    output_price: Optional[float] = Field(None, gt=0, le=100000, allow_inf_nan=False)


@app.post("/v1/model/detect", summary="仅向确定或用户选择的供应商验证 Key 并获取模型")
def detect_model(payload: DetectModelRequest):
    from reviewagent.model_settings import detect
    try:
        return detect(payload.api_key.get_secret_value(), payload.provider, payload.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.post("/v1/model/configure", summary="启用验证后的模型；Key 仅保存于服务内存")
def configure_model(payload: ApplyModelRequest):
    from reviewagent.model_settings import apply
    try:
        return apply(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


# ── 本地 Web UI（静态单页，与 API 同源） ──────────────────────

@app.get("/", include_in_schema=False)
def webui_root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


if WEBUI_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=str(WEBUI_DIR), html=True), name="webui")

WEBUI_REDESIGN_DIR = Path(__file__).resolve().parent / "webui-redesign"
if WEBUI_REDESIGN_DIR.is_dir():
    app.mount("/app-redesign", StaticFiles(directory=str(WEBUI_REDESIGN_DIR), html=True), name="webui-redesign")

WEBUI_CLASSIC_DIR = Path(__file__).resolve().parent / "webui-classic"
if WEBUI_CLASSIC_DIR.is_dir():
    app.mount("/app-classic", StaticFiles(directory=str(WEBUI_CLASSIC_DIR), html=True), name="webui-classic")
