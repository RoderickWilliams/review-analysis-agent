# -*- coding: utf-8 -*-
"""分析流水线：采集 → 预处理 → LLM 深度分析 → Trust Report → HTML 报告。

Streamlit 界面、CLI 与 HTTP API 共用这一层，避免三处各写一遍全链路。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from reviewagent import config
from reviewagent.review_data import normalize_reviews, summarize_results


DEMO_REVIEWS: List[Dict[str, Any]] = [
    {"review_text": "用了两周，续航确实给力，重度使用能撑一天半，充电也快，很满意", "rating": 5, "platform": "淘宝"},
    {"review_text": "这手机真是太好了，卡顿得让我学会了冥想，等待是一种修行", "rating": 5, "platform": "京东"},
    {"review_text": "好评！质量很好，物流很快，卖家态度好，下次还来！", "rating": 5, "platform": "淘宝"},
    {"review_text": "外观确实好看，放在桌上当摆件挺好的", "rating": 4, "platform": "淘宝"},
    {"review_text": "质量太差了，用了一周就坏了，客服也不理人，千万别买", "rating": 1, "platform": "淘宝"},
]
DEMO_PRODUCT = "某款智能手机"


def collect_reviews(product_url: str, max_reviews: int = 50) ->Tuple[List[Dict], str]:
    """从商品链接采集评论，返回 (reviews, product_name)。

    采集是实验功能，默认关闭。未设置 REVIEWAGENT_ENABLE_SCRAPING=1 时抛出
    RuntimeError，避免在用户不知情的情形下启动浏览器、访问第三方站点。
    """
    if not config.SCRAPING_ENABLED:
        raise RuntimeError(
            "链接采集默认关闭（实验功能）。请改用 --csv 导入评论，"
            "或设置 REVIEWAGENT_ENABLE_SCRAPING=1 后重试；采集需自行确认目标站点的使用条款。"
        )

    backend = (getattr(config, "SCRAPER_BACKEND", "legacy") or "legacy").strip().lower()
    if backend == "scrapling":
        from reviewagent.scrapers import scrapling_backend

        if not config.SCRAPLING_SELECTORS:
            raise RuntimeError(
                "Scrapling 后端需要选择器配置：设置 REVIEWAGENT_SCRAPLING_SELECTORS 指向 JSON 文件，"
                "格式见 config/scrapling_selectors.example.json。"
            )
        reviews = scrapling_backend.fetch_reviews(
            product_url,
            config.SCRAPLING_SELECTORS,
            max_reviews=max_reviews,
            mode=config.SCRAPLING_FETCH_MODE,
            timeout=config.SCRAPLING_TIMEOUT,
        )
        product_name = (reviews[0].get("product_name") if reviews else None) or "产品"
        return reviews, product_name
    if backend not in ("legacy", ""):
        raise RuntimeError(f"未知抓取后端: {backend!r}（可选 legacy / scrapling）")

    from reviewagent.scrapers.multi_platform import MultiPlatformScraper

    scraper = MultiPlatformScraper()
    reviews = scraper.scrape_product(product_url, max_reviews=max_reviews)
    product_name = (reviews[0].get("product_name") if reviews else None) or "产品"
    return reviews, product_name


def load_csv_reviews(csv_path: str) -> Tuple[List[Dict], str]:
    """从 CSV 加载评论，返回 (reviews, product_name)。"""
    from reviewagent.utils.helpers import load_reviews_from_csv

    reviews = load_reviews_from_csv(csv_path)
    product_name = (reviews[0].get("product_name") if reviews else None) or "产品"
    return reviews, product_name


def analyze_reviews(
    reviews: List[Dict],
    product_name: str,
    *,
    save_history: bool = True,
    source: str = "cli",
    platform: str = "",
    product_url: str = "",
    agent: Any = None,
    on_result: Any = None,
    should_cancel: Any = None,
    existing_results: Any = None,
) -> Dict[str, Any]:
    """运行完整分析流水线。

    :param agent: 可注入的分析器（测试或自定义模型用）；省略时按配置创建。
    :raises reviewagent.llm.LLMNotConfigured: 未配置 API Key。
    """
    reviews = normalize_reviews(reviews)
    if not reviews:
        raise ValueError("没有可分析的评论")

    from reviewagent.report_generator import HTMLReportGenerator
    from reviewagent.sentiment_agent_core import ReviewAnalysisAgent
    from reviewagent.trust_report import TrustReportEngine

    if agent is None:
        from reviewagent.affordable_analysis import AffordableAgent
        agent = AffordableAgent()
    if on_result is not None or should_cancel is not None or existing_results is not None:
        results = agent.batch_analyze(reviews, product_name=product_name, on_result=on_result,
                                      should_cancel=should_cancel, existing_results=existing_results)
    else:
        results = agent.batch_analyze(reviews, product_name=product_name)
    for index, result in enumerate(results):
        for field, value in reviews[index].items():
            result.setdefault(field, value)
    report = agent.generate_report(results, product_name=product_name)

    try:
        trust_report = TrustReportEngine().generate_report(reviews, results)
    except Exception as exc:  # Trust Report 失败不阻断主链路
        print(f"  Trust Report 生成失败: {exc}")
        trust_report = {}

    config.ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    html_path = HTMLReportGenerator().generate(
        results=results,
        report=report,
        output_path=str(config.OUTPUT_DIR / f"report_{timestamp}.html"),
        product_name=product_name,
    )
    json_path = config.OUTPUT_DIR / f"analysis_{timestamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "product_name": product_name,
                "timestamp": datetime.now().isoformat(),
                "report": report,
                "trust_report": trust_report,
                "detailed_results": results,
                "reviews": reviews,
                "statistics": summarize_results(results),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    record_id = None
    if save_history:
        from reviewagent.history_manager import save_history_record

        record_id = save_history_record(
            source=source,
            platform=platform or (reviews[0].get("source_platform") or ""),
            url=product_url,
            product_name=product_name,
            reviews=reviews,
            results=results,
            report=report,
            trust_report=trust_report,
        )

    return {
        "results": results,
        "report": report,
        "trust_report": trust_report,
        "html_report_path": html_path,
        "json_path": str(json_path),
        "record_id": record_id,
        "review_count": len(results),
        "statistics": summarize_results(results),
        "reviews": reviews,
    }



def _xhs_review_docs(reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把评论映射成洞察引擎要的文档：编号、正文、点赞、来源、所属笔记。"""
    import hashlib

    docs: List[Dict[str, Any]] = []
    for review in reviews:
        text = review.get("review_text") or ""
        review_id = str(review.get("review_id") or review.get("comment_id") or "").strip()
        if not review_id:
            review_id = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
        review["review_id"] = review_id
        docs.append(
            {
                "review_id": review_id,
                "text": text,
                "ocr_text": review.get("note_ocr_text") or "",
                "like": review.get("comment_like") or 0,
                "note_title": review.get("note_title") or "",
                "note_id": review.get("note_id") or "",
                "source_url": review.get("source_url") or "",
                "platform": review.get("source_platform") or "小红书",
            }
        )
    return docs


def analyze_xhs(
    capture: Dict[str, Any],
    product_name: Optional[str] = None,
    *,
    agent: Any = None,
    llm_call: Any = None,
    save_history: bool = True,
    source: str = "cli",
    output_path: Optional[str] = None,
    limit_topics: int = 10,
) -> Dict[str, Any]:
    """小红书链路：采集结果 → 情绪/可信度 → 痛点证据校验 → 改进方向 → 选题 → 内容生产包 → 六章报告。

    :param capture: reviewagent.scrapers.xhs_reader.load_run 或 capture 的返回值。
    :param agent: 可注入的分析器；省略时按配置创建。
    :param llm_call: 洞察引擎调用的大模型函数 (prompt) -> str；省略时复用 agent 的调用通道。
    :raises reviewagent.llm.LLMNotConfigured: 未配置 API Key 且有评论需要分析。
    """
    from reviewagent.insights import (
        analyze_pain_points,
        build_content_kit,
        build_topics,
        generate_improvements,
    )
    from reviewagent.insights.xhs_report import XhsReportGenerator
    from reviewagent.sentiment_agent_core import ReviewAnalysisAgent
    from reviewagent.trust_report import TrustReportEngine

    notes = capture.get("notes") or []
    reviews = normalize_reviews(list(capture.get("reviews") or []), strict=False)
    docs = _xhs_review_docs(reviews)

    if not product_name:
        title = (notes[0].get("title") if notes else "") or ""
        product_name = title.strip()[:40] or "小红书样本"

    results: List[Dict[str, Any]] = []
    report: Dict[str, Any] = {}
    trust_report: Dict[str, Any] = {}
    if reviews:
        if agent is None:
            from reviewagent.affordable_analysis import AffordableAgent
            agent = AffordableAgent()
        results = agent.batch_analyze(reviews, product_name=product_name)
        for index, result in enumerate(results):
            if index < len(reviews):
                result.setdefault("review_text", reviews[index].get("review_text", ""))
                result["review_id"] = reviews[index].get("review_id")
                result.setdefault("platform", reviews[index].get("source_platform") or "小红书")
        results = [{**reviews[i], **result} for i, result in enumerate(results)]
        report = agent.generate_report(results, product_name=product_name)
        try:
            trust_report = TrustReportEngine().generate_report(reviews, results)
        except Exception as exc:  # Trust Report 失败不阻断主链路
            print(f"  Trust Report 生成失败: {exc}")
            trust_report = {}

    if getattr(agent, "ledger", None) is not None:
        from reviewagent.review_data import result_succeeded
        successful_ids = {r.get("review_id") for r in results if result_succeeded(r)}
        docs = [doc for doc in docs if doc.get("review_id") in successful_ids]
    call = llm_call if llm_call is not None else getattr(agent, "_call_llm", None)
    corpus: List[str] = [doc["text"] for doc in docs if doc.get("text")]
    for note in notes:
        corpus.extend([note.get("text") or "", note.get("desc") or ""])
    corpus = [text for text in corpus if text]

    if call is not None and docs:
        pain_report = analyze_pain_points(docs, call)
    else:
        reason = "没有可分析的评论文本" if not docs else "没有配置大模型，无法提取痛点"
        pain_report = {
            "pain_points": [],
            "verified_count": 0,
            "unverified_count": 0,
            "rejected_evidence": 0,
            "errors": [reason],
            "batches": 0,
            "docs": len(docs),
        }

    if call is not None and pain_report.get("verified_count"):
        improvement_report = generate_improvements(pain_report["pain_points"], call)
    else:
        improvement_report = {
            "improvements": [],
            "rejected": [],
            "error": "没有已验证的痛点，无法生成改进方向",
        }
    topic_report = build_topics(pain_report["pain_points"], limit=limit_topics, texts=corpus)
    content_kit = build_content_kit(
        product_name,
        notes=notes,
        pain_points=pain_report["pain_points"],
        improvements=improvement_report.get("improvements") or [],
        topics=topic_report.get("topics") or [],
        audience=topic_report.get("audience") or "",
    )

    if getattr(agent, "ledger", None) is not None:
        report.update(model_cost=agent.ledger.snapshot(), model_coverage=agent.sampling)
    config.ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    html_path = XhsReportGenerator().generate(
        product_name=product_name,
        capture=capture,
        sentiment_results=results,
        sentiment_report=report,
        trust_report=trust_report,
        pain_report=pain_report,
        improvement_report=improvement_report,
        topic_report=topic_report,
        content_kit=content_kit,
        output_path=output_path,
    )
    json_path = config.OUTPUT_DIR / f"xhs_analysis_{timestamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "product_name": product_name,
                "platform": "小红书",
                "timestamp": datetime.now().isoformat(),
                "capture": {
                    "run_dir": capture.get("run_dir", ""),
                    "captured_at": capture.get("captured_at", ""),
                    "stats": capture.get("stats") or {},
                    "warnings": capture.get("warnings") or [],
                    "meta": capture.get("meta") or {},
                },
                "notes": [
                    {
                        "note_id": note.get("note_id"),
                        "title": note.get("title"),
                        "source_url": note.get("source_url"),
                        "stats": note.get("stats"),
                        "image_count": len(note.get("images") or []),
                    }
                    for note in notes
                ],
                "report": report,
                "trust_report": trust_report,
                "pain_report": pain_report,
                "improvement_report": improvement_report,
                "topic_report": topic_report,
                "content_kit": content_kit,
                "detailed_results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    record_id = None
    if save_history:
        from reviewagent.history_manager import save_history_record

        record_id = save_history_record(
            source=source,
            platform="小红书",
            url=(notes[0].get("source_url") if notes else "") or "",
            product_name=product_name,
            reviews=reviews,
            results=results,
            report=report,
            trust_report=trust_report,
        )

    return {
        "results": results,
        "report": report,
        "trust_report": trust_report,
        "pain_report": pain_report,
        "improvement_report": improvement_report,
        "topic_report": topic_report,
        "content_kit": content_kit,
        "html_report_path": html_path,
        "json_path": str(json_path),
        "record_id": record_id,
        "review_count": len(results),
        "note_count": len(notes),
        "capture": capture,
    }


def summarize(result: Dict[str, Any]) -> str:
    """把 analyze_reviews 的结果排成终端摘要（指标 + 输出文件）。"""
    report = result.get("report") or {}
    trust_report = result.get("trust_report") or {}
    lines = [
        "=" * 60,
        "  分析完成！",
        "=" * 60,
        f"  总评论数:     {result.get('review_count', len(result.get('results') or []))}",
        f"  真实好评率:   {report.get('authentic_positive_rate', 'N/A')}",
        f"  可疑评论数:   {report.get('suspicious_review_count', 'N/A')}",
        f"  刷单风险:     {report.get('fake_review_risk', 'N/A')}",
    ]
    if trust_report:
        lines.append(f"  Trust Score:  {trust_report.get('overall_trust_score', 'N/A')}/100")
        lines.append(f"  突发检测:     {'是' if trust_report.get('burst_detected') else '否'}")
        lines.append(f"  重复评论组:   {len(trust_report.get('duplicate_groups') or [])}")
        posterior = trust_report.get("posterior") or {}
        if posterior.get("ci95_score"):
            low, high = posterior["ci95_score"]
            lines.append(f"  启发式区间:   95% 区间（未校准） {low}–{high}（有效样本 {posterior.get('effective_n')}）")
        if trust_report.get("risk_level"):
            lines.append(f"  风险等级:     {trust_report['risk_level']}")
    lines += [
        "",
        "  输出文件:",
        f"    JSON: {result.get('json_path', '')}",
        f"    HTML: {result.get('html_report_path', '')}",
    ]
    if result.get("record_id"):
        lines.append(f"    历史记录: {result['record_id']}")
    return "\n".join(lines)


def summarize_xhs(result: Dict[str, Any]) -> str:
    """把小红书链路结果压成一段可打印摘要。"""
    capture = result.get("capture") or {}
    stats = capture.get("stats") or {}
    pain = result.get("pain_report") or {}
    topic = result.get("topic_report") or {}
    kit = result.get("content_kit") or {}
    kit_brief = kit.get("brief") or {}
    improvements = (result.get("improvement_report") or {}).get("improvements") or []
    priorities: Dict[str, int] = {}
    for item in improvements:
        key = item.get("priority", "P2")
        priorities[key] = priorities.get(key, 0) + 1
    lines = [
        "=" * 60,
        "  小红书分析完成！",
        "=" * 60,
        f"  笔记数:       {result.get('note_count', 0)}（成功 {stats.get('notes_ok', 0)}）",
        f"  评论数:       {result.get('review_count', 0)}",
        f"  带图文字:     {stats.get('with_ocr', 0)} 篇",
        f"  已验证痛点:   {pain.get('verified_count', 0)} 条",
        f"  改进建议:     {len(improvements)} 条（P0 {priorities.get('P0', 0)} / P1 {priorities.get('P1', 0)} / P2 {priorities.get('P2', 0)}）",
        f"  宣传选题:     {len(topic.get('topics') or [])} 个（人群：{topic.get('audience', '目标用户')}）",
        f"  内容生产包:   {len(kit_brief.get('selling_points') or [])} 个卖点 / {len((kit.get('material_index') or {}).get('entries') or [])} 张素材元数据 / {len((kit.get('style_card') or {}).get('observed', {}).get('top_tags') or [])} 个高频标签",
        "",
        "  输出文件:",
        f"    JSON: {result.get('json_path', '')}",
        f"    HTML: {result.get('html_report_path', '')}",
    ]
    errors = pain.get("errors") or []
    if errors:
        lines.append("  提醒: " + "；".join(errors[:3]))
    return "\n".join(lines)
