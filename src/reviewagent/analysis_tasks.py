"""Local persisted workbench tasks. Starting paid analysis is always explicit."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from reviewagent import config, store
from reviewagent.review_data import normalize_reviews, result_succeeded, summarize_results

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reviewagent")
_lock = threading.Lock()
_active = {}
BUSY = {"queued", "running", "cancel_requested"}


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def create_record(payload):
    from reviewagent.object_resolver import resolve_object
    from reviewagent.same_product import build_same_products
    from reviewagent.report_builder import build_analysis_report

    request = dict(payload)
    from reviewagent.collection import normalize_scope
    normalize_scope(request)
    reviews = normalize_reviews(request.get("reviews") or [])
    request["reviews"] = reviews
    primary = resolve_object(request["input"].strip())
    extras = [resolve_object(link) for link in request.get("extra_links", []) if link.strip()]
    matched = build_same_products(primary, extras)
    built = build_analysis_report(primary, matched, ownership=request.get("ownership", "own"),
                                  input_text=request["input"], tier=request.get("tier", "standard"),
                                  window_months=request.get("window_months", 12), reviews=reviews)
    extra_urls = {(item.get("url") or item.get("source_url") or "").strip() for item in extras}
    extra_urls.discard("")
    for candidate in built["candidates"]:
        if (candidate.get("url") or candidate.get("source_url") or "").strip() in extra_urls:
            candidate["user_supplied"] = True
    analysis = {
        "analysis_id": "ra_" + uuid.uuid4().hex[:16], "created_at": now(), "updated_at": now(),
        "status": "draft", "status_label": "待分析" if reviews else "待导入评论",
        "input": request["input"], "request": request, "reviews": reviews, "results": [],
        "object": built["object"], "candidates": built["candidates"], "match_summary": built["match_summary"],
        "report": built["report"], "progress": {"done": 0, "total": len(reviews), "stage": "ready"},
    }
    _rebuild(analysis)
    if request.get("save", True):
        store.save_analysis(analysis)
    return analysis


def _evidence(analysis):
    report = analysis["report"]
    existing = [item for item in report.get("evidence", []) if item.get("type") != "review"]
    for review in analysis.get("reviews", []):
        existing.append({"id": review["review_id"], "type": "review", "title": "评论原文",
                         "quote": review["review_text"], "url": review.get("source_url", ""),
                         "platform": review.get("platform"), "review_date": review.get("review_date", ""),
                         "source_kind": "collected" if review.get("extraction_method") else "imported",
                         "fields": ["review_text", "rating", "review_date"], "fetched_at": review.get("imported_at", "")})
    report["evidence"] = existing


def mutate_record(analysis_id, mutate):
    """Serialize workbench edits with task starts, using a fresh record."""
    with _lock:
        analysis = store.get_analysis(analysis_id)
        if analysis is None:
            raise KeyError(analysis_id)
        if analysis_id in _active or analysis.get("status") in BUSY:
            raise ValueError("请先取消或等待当前任务完成")
        mutate(analysis)
        _rebuild(analysis)
        store.save_analysis(analysis)
        return analysis


def attach_reviews(analysis_id, reviews, *, append=False):
    def apply(analysis):
        raw = list(analysis.get("reviews", [])) + list(reviews) if append else list(reviews)
        if append:
            raw = list({r.get("review_id") or str(i): r for i, r in enumerate(raw)}.values())
        normalized = normalize_reviews(raw)
        if not normalized:
            raise ValueError("至少需要一条有效评论")
        if len(normalized) > 5000:
            raise ValueError("工作台单次最多 5000 条评论")
        request = dict(analysis.get("request") or {})
        request["reviews"] = normalized
        retained = {r.get("review_id"): r for r in analysis.get("results", []) if result_succeeded(r)}
        results = [retained[r["review_id"]] for r in normalized if r["review_id"] in retained and all(retained[r["review_id"]].get(k) == r.get(k) for k in ("review_text", "rating", "review_date", "source_url"))]
        analysis.update(reviews=normalized, request=request, results=results, status="draft", status_label="待分析")
        if analysis.get("enrichment"):
            analysis["enrichment"]["source_changed"] = True
    return mutate_record(analysis_id, apply)


def recover_interrupted():
    """服务启动时把没有本进程活动 worker 的遗留任务标记为中断。

    只改状态，不删除评论、结果或草稿；单 Uvicorn worker 架构下 _active 即真相。
    """
    recovered = []
    with _lock:
        active = set(_active)
    for item in store.list_analyses():
        analysis_id = item.get("analysis_id")
        if item.get("status") in BUSY and analysis_id not in active:
            store.update_analysis(analysis_id, {"status": "interrupted",
                                                "status_label": "任务已中断，可继续", "error": None})
            recovered.append(analysis_id)
    return recovered


def get_record(analysis_id):
    with _lock:
        analysis = store.get_analysis(analysis_id)
        if analysis is None:
            raise KeyError(analysis_id)
        if analysis.get("status") in BUSY and analysis_id not in _active:
            analysis = store.update_analysis(analysis_id, {"status": "interrupted", "status_label": "任务已中断，可继续", "error": None})
        return analysis


def _rebuild(analysis):
    from reviewagent.report_builder import build_analysis_report
    from reviewagent.product_groups import assign_groups

    groups = assign_groups(analysis)
    raw_by_id = {review["review_id"]: review for review in analysis.get("reviews", [])}
    changed_context = False
    for index, result in enumerate(analysis.get("results", [])):
        review = raw_by_id.get(result.get("review_id"))
        if review and result_succeeded(result) and result.get("analysis_context") != review.get("analysis_context"):
            analysis["results"][index] = {**review, "status": "pending", "final_analysis": {}, "previous_analysis": result,
                                          "error": {"code": "context_changed", "message": "商品身份或规格已变化，旧结果已保留，需重新分析"}}
            changed_context = True
    if changed_context:
        if analysis.get("enrichment"):
            analysis["enrichment"]["source_changed"] = True
        groups = assign_groups(analysis)
    request = analysis.get("request") or {}
    built = build_analysis_report(analysis["object"], {"candidates": analysis.get("candidates", []), "summary": analysis.get("match_summary", {})},
                                  ownership=request.get("ownership", "own"), input_text=analysis["input"],
                                  tier=request.get("tier", "standard"), window_months=request.get("window_months", 12), reviews=analysis.get("reviews", []))
    report = built["report"]
    report["actions"] = []
    report["groups"] = groups
    report["comparison_scope"] = "各品牌、型号及关键规格分别统计；未知规格单独待确认"
    report["collection"] = analysis.get("collection", {})
    stats = summarize_results(analysis.get("results", []))
    stats["pending_count"] += max(0, len(analysis.get("reviews", [])) - stats["total"])
    unfinished = stats["failed_count"] + stats["pending_count"] + stats["cancelled_count"]
    from reviewagent.trust_report import TrustReportEngine
    report["trust_report"] = TrustReportEngine().generate_report(analysis.get("reviews", []), analysis.get("results", []))
    report["statistics"] = stats
    report["dashboard"].update(score=stats["avg_trust_score"], score_label="信息可信度", valid_samples=stats["successful_count"])
    if stats["successful_count"]:
        report["diagnosis"].update(status="available", status_label="已分析", sentiment_distribution=stats["sentiment_distribution"],
                                    sarcastic_count=stats["sarcastic_count"], successful_count=stats["successful_count"], failed_count=stats["failed_count"])
        report["overview"]["conclusion"] = f"已导入 {len(analysis.get('reviews', []))} 条评论，分析成功 {stats['successful_count']} 条，未完成 {unfinished} 条。"
        report["method"]["llm_used"] = True
        report["method"]["review_analysis"] = "partial" if unfinished else "complete"
        report["diagnosis"]["summary"] = "情绪与真实性信号分开统计；请结合原句复核疑点。"
    for key in ("pain_points", "improvements", "topics", "content_kit", "ops_plan", "actions", "drafts", "insight_groups"):
        if key in analysis.get("enrichment", {}):
            report[key] = analysis["enrichment"][key]
    score = stats["avg_trust_score"]
    risk = "unknown" if score is None else "low" if score >= 70 else "medium" if score >= 40 else "high"
    report["dashboard"].update(risk=risk, risk_label={"unknown": "未评估", "low": "低疑点", "medium": "需复核", "high": "高疑点"}[risk], score_note="模型内容信号；无法认证评论真实性", pain_count=len(report.get("pain_points", {}).get("items", [])), opportunity_count=len(report.get("improvements", {}).get("items", [])))
    report["diagnosis"].update(score=score, risk=risk, trust=report["trust_report"], signals=report["trust_report"].get("signals", []))
    report["data_status"]["llm_used"] = bool(stats["successful_count"])
    report["data_status"]["analyzed_reviews"] = stats["successful_count"]
    report["data_status"]["insights_stale"] = bool(analysis.get("enrichment", {}).get("source_changed"))
    report["model_cost"] = analysis.get("cost", {})
    report["model_coverage"] = analysis.get("sampling", {"local_count": len(analysis.get("reviews", [])), "modeled_count": stats["successful_count"]})
    if stats["successful_count"]:
        report.update(stage="analysis", stage_label="评论已分析")
        report["diagnosis"]["reasons"] = ["模型逐条判断与统计信号分开呈现；疑点需结合原文核对。"]
    analysis["report"] = report
    _evidence(analysis)
    return analysis


def _insights_single(analysis, agent, cancelled):
    from reviewagent.insights import analyze_pain_points, generate_improvements

    successful_ids = {r.get("review_id") for r in analysis.get("results", []) if result_succeeded(r)}
    reviews = [r for r in analysis.get("reviews", []) if r["review_id"] in successful_ids]
    docs = [{"review_id": r["review_id"], "text": r["review_text"], "source_url": r.get("source_url", ""),
             "platform": r["platform"], "like": r.get("comment_like", 0)} for r in reviews]
    if not docs or cancelled():
        return {}
    def call(prompt):
        if cancelled():
            raise RuntimeError("任务已取消")
        import json
        response = agent._call_llm(prompt)
        from reviewagent.insights.textutil import parse_json_any
        parsed = parse_json_any(response)
        if not isinstance(parsed, (dict, list)):
            raise RuntimeError("洞察模型响应不是有效的 JSON 对象或数组")
        if isinstance(parsed, dict) and parsed.get("error"):
            raise RuntimeError("洞察模型请求未完成")
        return json.dumps(parsed, ensure_ascii=False)
    available = len(docs)
    if len(docs) > 200:
        docs = [docs[round(i * (len(docs) - 1) / 199)] for i in range(200)]
    pain = analyze_pain_points(docs, call)
    verified = [item for item in pain.get("pain_points", []) if item.get("verified")]
    for item in verified:
        item["id"] = analysis.get("group_id", "main") + "-" + item["id"]
        item["group_id"] = analysis.get("group_id", "main")
    improvements = generate_improvements(verified, call) if verified and not cancelled() else {"improvements": []}
    return {
        "pain_points": {"status": "partial" if pain.get("errors") else "available", "items": verified, "unverified": [p for p in pain.get("pain_points", []) if not p.get("verified")], "errors": pain.get("errors", []), "sampling": {"available": available, "selected": len(docs), "method": "evenly_spaced"}},
        "improvements": {"status": "partial" if improvements.get("error") else "available", "items": improvements.get("improvements", []), "error": improvements.get("error", "")},
    }


def _insights(analysis, agent, cancelled):
    from reviewagent.product_groups import assign_groups
    groups = analysis.get("groups") or assign_groups(analysis)
    combined = {"pain_points": {"status": "available", "items": [], "unverified": [], "errors": []},
                "improvements": {"status": "available", "items": []}, "insight_groups": []}
    successful = {r.get("review_id") for r in analysis.get("results", []) if result_succeeded(r)}
    for group in groups:
        if cancelled():
            break
        ids = set(group["review_ids"])
        if not ids & successful:
            combined["pain_points"]["status"] = "partial"
            continue
        title = str(group["title"]) + " · " + group["spec_label"]
        subgroup = {**analysis, "group_id": group["group_id"], "object": {**analysis["object"], "title": title},
                    "reviews": [r for r in analysis["reviews"] if r["review_id"] in ids]}
        data = _insights_single(subgroup, agent, cancelled)
        combined["insight_groups"].append({"group_id": group["group_id"], "title": title, "data": data})
        for key in ("pain_points", "improvements"):
            for item in data.get(key, {}).get("items", []):
                item.update(group_id=group["group_id"], group_title=title)
                combined[key]["items"].append(item)
            if data.get(key, {}).get("status") == "partial":
                combined[key]["status"] = "partial"
        combined["pain_points"]["errors"].extend(data.get("pain_points", {}).get("errors", []))
        combined["pain_points"]["unverified"].extend(data.get("pain_points", {}).get("unverified", []))
    return combined


def _operations(analysis, kind="all"):
    from reviewagent.operations import build_operations
    return build_operations(analysis, kind)


def start(analysis_id, operation="analyze", *, agent=None):
    analysis = get_record(analysis_id)
    if operation not in {"analyze", "collect", "discover", "operations", "generate_actions", "generate_selling_point", "generate_support_script", "generate_content_topic", "login_jd", "login_taobao", "login_xhs"}:
        raise ValueError("未知任务类型")
    if operation == "analyze" and not analysis.get("reviews"):
        raise ValueError("请先导入评论或完成采集")
    if (operation == "analyze" or operation.startswith("generate_") or operation == "operations") and agent is None and not config.is_llm_configured():
        raise ValueError("尚未配置模型，已保留输入；配置后再开始分析")
    if (operation in {"collect", "discover"} or operation.startswith("login_")) and not config.SCRAPING_ENABLED:
        raise ValueError("采集尚未开启，请先配置采集端或导入评论")
    with _lock:
        analysis = store.get_analysis(analysis_id)
        if analysis is None:
            raise KeyError(analysis_id)
        if operation == "analyze" and not analysis.get("reviews"):
            raise ValueError("请先导入评论或完成采集")
        if analysis_id in _active:
            raise ValueError("该分析已有运行中的任务")
        if len(_active) >= 8:
            raise ValueError("任务队列已满，请等待已有任务完成")
        event = threading.Event()
        _active[analysis_id] = event
        try:
            store.update_analysis(analysis_id, {"status": "queued", "status_label": "等待处理", "operation": operation,
                                            "error": None, "progress": {"stage": operation, "done": 0, "total": len(analysis.get("reviews", []))}})
        except Exception:
            _active.pop(analysis_id, None)
            raise
    try:
        _pool.submit(_execute, analysis_id, operation, event, agent)
    except Exception:
        with _lock:
            _active.pop(analysis_id, None)
        store.update_analysis(analysis_id, {"status": "failed", "status_label": "任务未能启动"})
        raise
    return store.get_analysis(analysis_id)


def cancel(analysis_id):
    with _lock:
        current = store.get_analysis(analysis_id)
        if current is None:
            raise KeyError(analysis_id)
        event = _active.get(analysis_id)
        if event is None or current.get("status") not in BUSY:
            return current
        event.set()
        return store.update_analysis(analysis_id, {"status": "cancel_requested", "status_label": "取消中，等待当前请求结束"})


def _execute(analysis_id, operation, event, agent):
    try:
        analysis = store.update_analysis(analysis_id, {"status": "running", "status_label": "处理中"})
        def auth_state(info):
            authentication = analysis.setdefault("authentication", {})
            authentication[info["platform"]] = {**info, "updated_at": now()}
            progress = {**analysis.get("progress", {}), "stage": info["status"],
                        "message": info["message"], "platform": info["platform"]}
            analysis["progress"] = progress
            store.update_analysis(analysis_id, {"authentication": authentication, "progress": progress})

        def checkpoint(current):
            count = len(current.get("reviews", []))
            gaps = current.get("collection", {}).get("gaps", [])
            message = f"已保存 {count} 条真实评论；继续读取或查看来源缺口" if count else "尚未取得评论；正在准备来源或等待平台操作"
            if not count and gaps:
                message = "尚未取得评论；请查看采集失败原因"
            progress = {"stage": "needs_input" if not count and gaps else "collecting", "done": count,
                        "total": current.get("collection", {}).get("total_limit", 5000),
                        "message": message}
            current["progress"] = progress
            store.update_analysis(analysis_id, {"reviews": current["reviews"], "request": current["request"],
                                                "object": current["object"], "candidates": current.get("candidates", []),
                                                "collection": current["collection"], "progress": progress})

        def discovery_checkpoint(current):
            progress = {"stage": "discovering", "done": len(current.get("candidates", [])),
                        "message": "正在核对商品来源，已有候选已保存"}
            current["progress"] = progress
            store.update_analysis(analysis_id, {"candidates": current.get("candidates", []),
                                                "match_summary": current.get("match_summary", {}),
                                                "discovery": current.get("discovery", {}), "progress": progress})

        if operation.startswith("login_"):
            from reviewagent.auto_login import AutoLoginManager
            result = AutoLoginManager().ensure_session(operation[6:], should_cancel=event.is_set, on_state=auth_state)
            if not result["success"] and not event.is_set():
                raise ValueError(result["message"])
        elif operation == "analyze":
            from reviewagent.sentiment_agent_core import ReviewAnalysisAgent
            ledger = None
            if agent is None:
                from reviewagent.model_budget import BudgetLedger, budget_client
                model = "deepseek-flash" if config.MODEL in {"deepseek-chat", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"} else config.MODEL
                def save_cost(cost):
                    analysis["cost"] = cost
                    store.update_analysis(analysis_id, {"cost": cost})
                ledger = BudgetLedger(model, previous=analysis.get("cost"), on_change=save_cost)
                agent = ReviewAnalysisAgent(model=model, base_url=config.BASE_URL, client=budget_client(ledger))
                analysis["cost"] = ledger.snapshot()
            by_id = {r.get("review_id"): r for r in analysis.get("results", [])}
            def progress(index, result, done, total):
                by_id[result["review_id"]] = result
                analysis["results"] = [by_id[r["review_id"]] for r in analysis["reviews"] if r["review_id"] in by_id]
                statistics = summarize_results(analysis["results"])
                analysis["report"]["statistics"] = statistics
                analysis["report"]["dashboard"].update(score=statistics["avg_trust_score"], valid_samples=statistics["successful_count"])
                store.update_analysis(analysis_id, {"results": analysis["results"], "report": analysis["report"],
                                                    "progress": {"stage": "reviews", "done": done, "total": total}})
            if ledger is None:
                analysis["results"] = agent.batch_analyze(analysis["reviews"], product_name=analysis["object"].get("title") or analysis["input"],
                                                           on_result=progress, should_cancel=event.is_set, existing_results=analysis.get("results", []))
            else:
                from reviewagent.model_budget import representative_reviews
                chosen, sampling = representative_reviews(analysis["reviews"])
                full_counts = agent.similar_counts([r["review_text"] for r in analysis["reviews"]])
                counts = {r["review_id"]: full_counts[i] for i, r in enumerate(analysis["reviews"])}
                raw_by_id = {r["review_id"]: r for r in analysis["reviews"]}
                by_id = {rid: value for rid, value in by_id.items() if rid in raw_by_id and result_succeeded(value)
                         and value.get("analysis_model") == agent.model and value.get("prompt_version") == "review-v4"
                         and value.get("similar_count") == counts[rid]
                         and value.get("analysis_product") == (analysis["object"].get("title") or analysis["input"])
                         and value.get("analysis_context") == raw_by_id[rid].get("analysis_context")
                         and all(value.get(key) == raw_by_id[rid].get(key) for key in ("review_text", "rating", "review_date", "source_url"))}
                for offset in range(0, len(chosen), 10):
                    if event.is_set() or ledger.exhausted:
                        break
                    batch = chosen[offset:offset + 10]
                    done = agent.batch_analyze(batch, product_name=analysis["object"].get("title") or analysis["input"],
                                              on_result=progress, should_cancel=event.is_set, existing_results=list(by_id.values()),
                                              similar_counts_override=[counts[r["review_id"]] for r in batch])
                    for result in done:
                        if ledger.exhausted and not result_succeeded(result):
                            result.update(status="pending", budget_deferred=True)
                        by_id[result["review_id"]] = result
                analysis["results"] = [by_id.get(r["review_id"], {**r, "status": "pending", "final_analysis": {},
                                                                "model_coverage": "not_selected_or_budget_limited"}) for r in analysis["reviews"]]
                sampling["modeled_count"] = sum(result_succeeded(r) for r in analysis["results"])
                analysis["sampling"] = sampling
                ledger.set_phase("insights")
            if not event.is_set():
                store.update_analysis(analysis_id, {"progress": {"stage": "insights", "done": len(analysis["reviews"]), "total": len(analysis["reviews"])}})
                analysis.setdefault("enrichment", {}).update(_insights(analysis, agent, event.is_set))
                analysis["enrichment"].pop("source_changed", None)
            if ledger is not None:
                analysis["cost"] = ledger.snapshot()
        elif operation == "operations" or operation.startswith("generate_"):
            from reviewagent.operations import generate_operations
            from reviewagent.model_budget import BudgetLedger, budget_client
            from reviewagent.sentiment_agent_core import ReviewAnalysisAgent
            kind = "actions" if operation == "operations" else operation.removeprefix("generate_")
            ledger = None
            if agent is None:
                model = "deepseek-flash" if config.MODEL in {"deepseek-chat", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"} else config.MODEL
                def save_generation_cost(cost):
                    analysis["cost"] = cost
                    store.update_analysis(analysis_id, {"cost": cost})
                ledger = BudgetLedger(model, previous=analysis.get("cost"), on_change=save_generation_cost)
                ledger.set_phase("operations")
                agent = ReviewAnalysisAgent(model=model, base_url=config.BASE_URL, client=budget_client(ledger))
            analysis.setdefault("enrichment", {}).update(generate_operations(analysis, kind, agent, event.is_set))
            if ledger is not None:
                analysis["cost"] = ledger.snapshot()
        else:
            from reviewagent.collection import collect_into_analysis, discover_into_analysis
            analysis = collect_into_analysis(analysis, event.is_set, on_checkpoint=checkpoint, on_state=auth_state) if operation == "collect" else discover_into_analysis(analysis, event.is_set, on_checkpoint=discovery_checkpoint, on_state=auth_state)
        _rebuild(analysis)
        stats = summarize_results(analysis.get("results", []))
        incomplete = any(item.get("status") == "partial" for item in analysis.get("enrichment", {}).values() if isinstance(item, dict)) or bool(analysis.get("collection", {}).get("gaps")) or bool(analysis.get("discovery", {}).get("gaps"))
        with _lock:
            status = "cancelled" if event.is_set() else "failed" if operation == "analyze" and not stats["successful_count"] else "partial" if incomplete or (stats["failed_count"] or stats["pending_count"] or stats["cancelled_count"]) and stats["successful_count"] else "completed"
            analysis.update(status=status, status_label={"cancelled": "已取消", "partial": "部分完成，可重试", "failed": "分析未完成，可重试", "completed": "已完成"}[status], error=None)
            store.save_analysis(analysis)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else "任务未完成；已有数据和结果已保留，可重试"
        store.update_analysis(analysis_id, {"status": "cancelled" if event.is_set() else "failed", "status_label": "已取消" if event.is_set() else "任务未完成", "error": {"message": message}})
    finally:
        with _lock:
            _active.pop(analysis_id, None)


def clear_saved_records():
    batch_id = "clear_" + uuid.uuid4().hex
    with _lock:
        if _active:
            raise ValueError("请先取消或等待正在运行的任务完成，再清除记录")
        # Mark stale interrupted tasks before clearing, without starting work.
        for item in store.list_analyses():
            if item.get("status") in BUSY:
                store.update_analysis(item["analysis_id"], {"status": "interrupted", "status_label": "任务已中断，可继续"})
        count = store.trash_analyses(batch_id)
    return {"cleared": count, "batch_id": batch_id, "recoverable": True}
