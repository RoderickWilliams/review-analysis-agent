# -*- coding: utf-8 -*-
"""DSH 插件桥：把插件工具调用转成 ReviewAgent 的 Python 调用，只输出一行 JSON。

用法：python bridge.py <mode> <payload.json>
标准输出只留最终 JSON；库函数打印的进度重定向到 stderr。
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

# Windows 下管道 stdout/stderr 默认走本地代码页（cp936），插件按 UTF-8 解码就会乱码。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - 非常规流
        pass


class BridgeError(RuntimeError):
    def __init__(self, message: str, hint: str = "", kind: str = "BridgeError"):
        super().__init__(message)
        self.hint = hint
        self.kind = kind


def _require_config() -> None:
    from reviewagent import config

    if not config.is_llm_configured():
        raise BridgeError(
            "未配置大模型 API Key，分析类工具不可用。",
            "在 E:\\DeepSeek\\review-agent\\.env 或环境变量 REVIEWAGENT_API_KEYS 中配置 Key 后重试。",
            kind="LLMNotConfigured",
        )


def cmd_analyze(payload: dict) -> dict:
    from reviewagent.pipeline import (
        DEMO_PRODUCT,
        DEMO_REVIEWS,
        analyze_reviews,
        collect_reviews,
        load_csv_reviews,
        summarize,
    )

    if payload.get("demo"):
        reviews, product_name, source = DEMO_REVIEWS, DEMO_PRODUCT, "demo"
    elif payload.get("csv"):
        reviews, product_name = load_csv_reviews(str(payload["csv"]))
        source = "csv"
    elif payload.get("url"):
        reviews, product_name = collect_reviews(
            str(payload["url"]), max_reviews=int(payload.get("max_reviews") or 50)
        )
        source = "url"
    else:
        raise BridgeError("请提供 url、csv 或 demo 之一。", "例如 demo=true 先跑演示数据。")

    if not reviews:
        raise BridgeError("没有采到评论数据。", "确认链接可访问、或改用 CSV / demo。")

    _require_config()
    result = analyze_reviews(
        reviews,
        product_name,
        source=source,
        save_history=bool(payload.get("save_history", True)),
    )
    trust = result.get("trust_report") or {}
    return {
        "ok": True,
        "summary": summarize(result),
        "product_name": product_name,
        "review_count": result.get("review_count"),
        "trust_score": trust.get("overall_trust_score"),
        "risk_level": trust.get("risk_level"),
        "html_report_path": result.get("html_report_path"),
        "json_path": result.get("json_path"),
        "record_id": result.get("record_id"),
    }


def cmd_xhs(payload: dict) -> dict:
    from reviewagent.pipeline import analyze_xhs, summarize_xhs
    from reviewagent.scrapers import xhs_reader

    links = payload.get("links") or None
    if isinstance(links, str):
        links = [links]

    if payload.get("run_dir"):
        capture = xhs_reader.load_run(str(payload["run_dir"]))
    else:
        if not (payload.get("keyword") or payload.get("user") or links):
            raise BridgeError(
                "请提供 keyword、user、links 或 run_dir 之一。",
                "搜索与主页需要先扫码登录（reviewagent xhs 会提示）。",
            )
        capture = xhs_reader.capture(
            links=links,
            keyword=payload.get("keyword") or "",
            user=payload.get("user") or "",
            limit=int(payload.get("limit") or 20),
            with_comments=payload.get("with_comments", True),
            out_dir=payload.get("out_dir") or None,
            sort=payload.get("sort") or "",
            sweep=bool(payload.get("sweep", False)),
            note_type=payload.get("note_type") or "",
            with_ocr=payload.get("with_ocr"),
            max_images=payload.get("max_images"),
        )

    capture_summary = xhs_reader.summarize(capture)
    meta = {
        "ok": True,
        "capture_summary": capture_summary,
        "run_dir": capture.get("run_dir"),
        "stats": capture.get("stats") or {},
        "warnings": capture.get("warnings") or [],
    }

    if payload.get("capture_only"):
        meta["capture_only"] = True
        meta["summary"] = capture_summary
        return meta

    _require_config()
    result = analyze_xhs(
        capture,
        payload.get("product_name") or None,
        save_history=bool(payload.get("save_history", True)),
        source="plugin",
    )
    pains = result.get("pain_report") or {}
    topics = result.get("topic_report") or {}
    meta.update(
        {
            "summary": summarize_xhs(result),
            "note_count": result.get("note_count"),
            "review_count": result.get("review_count"),
            "verified_pains": pains.get("verified_count"),
            "topic_count": len(topics.get("topics") or []),
            "html_report_path": result.get("html_report_path"),
            "json_path": result.get("json_path"),
            "record_id": result.get("record_id"),
        }
    )
    return meta


def cmd_susu(payload: dict) -> dict:
    from reviewagent import config
    from reviewagent.insights import susu
    from reviewagent.scrapers import xhs_reader

    if payload.get("analysis"):
        path = Path(str(payload["analysis"]))
        if not path.is_file():
            raise BridgeError(f"找不到 analysis JSON: {path}", "先跑一次 review_xhs 或 review_susu 生成 analysis。")
        try:
            analysis = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise BridgeError(f"analysis JSON 解析失败: {exc}") from exc
        try:
            rendered = susu.render_analysis(analysis, out_dir=payload.get("out_dir") or None)
        except ValueError as exc:
            raise BridgeError(
                f"analysis 没通过技能校验: {exc}",
                "按 susu-insight 的 references/report-data.md 修正字段后重试。",
            ) from exc
        return {
            "ok": True,
            "summary": f"susu-insight 报告已渲染：{rendered['html_path']}",
            "html_report_path": rendered["html_path"],
            "json_path": rendered["json_path"],
            "statistics": rendered["statistics"],
        }

    run_dir = payload.get("run_dir")
    if not run_dir:
        raise BridgeError(
            "review_susu 需要 run_dir 或 analysis。",
            "先用 review_xhs 的 capture_only=true 采集，或传已有采集目录。",
        )
    capture = xhs_reader.load_run(str(run_dir))
    use_llm = bool(payload.get("use_llm", True))
    warnings = []
    if use_llm and not config.is_llm_configured():
        use_llm = False
        warnings.append("未配置 API Key，本次只做确定性归类。")
    result = susu.analyze_capture(
        capture,
        account_name=payload.get("account") or "",
        out_dir=payload.get("out_dir") or None,
        use_llm=use_llm,
    )
    stats = result.get("statistics") or {}
    return {
        "ok": True,
        "summary": susu.summarize(result),
        "account": (result.get("analysis") or {}).get("account", {}).get("name", ""),
        "note_count": len((result.get("analysis") or {}).get("contents") or []),
        "professional_comments": stats.get("professional"),
        "topic_count": len((result.get("analysis") or {}).get("topics") or []),
        "opportunity_count": len((result.get("analysis") or {}).get("opportunities") or []),
        "used_llm": result.get("used_llm"),
        "warnings": warnings,
        "html_report_path": result.get("html_path"),
        "json_path": result.get("json_path"),
    }


def cmd_xhs_status(_payload: dict) -> dict:
    from reviewagent.scrapers import xhs_reader

    status = xhs_reader.status()
    status["ok"] = True
    status["summary"] = (
        f"小红书采集{'可用' if status.get('available') else '不可用'}；"
        f"{'已登录' if status.get('logged_in') else '未登录（搜索与主页需要扫码）'}"
    )
    return status


def cmd_trust(payload: dict) -> dict:
    from reviewagent.pipeline import load_csv_reviews
    from reviewagent.trust_report import TrustReportEngine

    csv = payload.get("csv")
    if not csv:
        raise BridgeError("review_trust_report 需要 csv 参数。", "CSV 至少包含 review_text 列。")
    reviews, product_name = load_csv_reviews(str(csv))
    if not reviews:
        raise BridgeError("CSV 里没有可用的评论。", "检查 review_text 列与编码（UTF-8）。")
    report = TrustReportEngine().generate_report(reviews, reviews)
    score = report.get("overall_trust_score")
    return {
        "ok": True,
        "summary": f"Trust Report：{product_name}，{len(reviews)} 条评论，综合信任分 {score}/100，风险等级 {report.get('risk_level')}。",
        "product_name": product_name,
        "review_count": len(reviews),
        "report": report,
    }


def cmd_history(payload: dict) -> dict:
    from reviewagent import store

    if payload.get("clear"):
        if not payload.get("yes"):
            raise BridgeError("清空历史需要同时传 yes=true。", "这是不可撤销操作。")
        removed = store.clear_history()
        return {"ok": True, "summary": f"已清空 {removed} 条历史记录。", "removed": removed}

    limit = int(payload.get("limit") or 20)
    records = store.list_history(limit=limit)
    lines = [f"最近 {len(records)} 条记录："]
    for rec in records:
        lines.append(
            f"- {rec.get('created_at', '')}  {rec.get('product_name', '')}"
            f"  评论 {rec.get('review_count', 0)}  信任分 {rec.get('avg_trust_score', 'N/A')}"
        )
    return {"ok": True, "summary": "\n".join(lines), "records": records}


def cmd_doctor(_payload: dict) -> dict:
    from reviewagent.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["doctor"])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = args.func(args)
    text = buf.getvalue()
    return {"ok": True, "healthy": code == 0, "summary": text.strip()[-4000:]}


HANDLERS = {
    "analyze": cmd_analyze,
    "xhs": cmd_xhs,
    "xhs_status": cmd_xhs_status,
    "susu": cmd_susu,
    "trust": cmd_trust,
    "history": cmd_history,
    "doctor": cmd_doctor,
}


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "缺少 mode 参数", "error_type": "UsageError"}, ensure_ascii=False))
        return 0
    mode = sys.argv[1]
    payload = {}
    if len(sys.argv) >= 3:
        payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))

    handler = HANDLERS.get(mode)
    if handler is None:
        print(json.dumps({"ok": False, "error": f"未知 mode: {mode}", "error_type": "UsageError"}, ensure_ascii=False))
        return 0

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            result = handler(payload)
    except BridgeError as exc:
        result = {"ok": False, "error": str(exc), "hint": exc.hint, "error_type": exc.kind}
    except Exception as exc:  # noqa: BLE001 - 插件边界统一成结构化错误
        result = {"ok": False, "error": str(exc) or exc.__class__.__name__, "error_type": type(exc).__name__}
    finally:
        sys.stderr.write(buf.getvalue())

    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
