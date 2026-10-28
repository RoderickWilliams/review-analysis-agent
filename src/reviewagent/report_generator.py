"""Offline HTML reports. Every imported or model-generated value is escaped."""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from reviewagent import config
from reviewagent.review_data import result_succeeded, summarize_results


def _text(value):
    return escape(str(value if value is not None else "未评估"), quote=True)


def _link(value):
    value = str(value or "")
    try:
        scheme = urlsplit(value).scheme.lower()
    except ValueError:
        return "—"
    if scheme not in {"http", "https"}:
        return "—"
    return '<a href="' + _text(value) + '" rel="noreferrer">原文</a>'


class HTMLReportGenerator:
    def generate(self, results, report, output_path=None, product_name="产品"):
        output = Path(output_path) if output_path else config.OUTPUT_DIR / ("report_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".html")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self._build_html(product_name, self._extract_stats(results, report), results, report), encoding="utf-8")
        return str(output)

    def _extract_stats(self, results, report):
        stats = summarize_results(results)
        stats.update(
            sentiment_dist=stats["sentiment_distribution"], validity_dist=stats["validity_distribution"],
            trust_scores=[r["final_analysis"]["trust_score"] for r in results if result_succeeded(r) and r["final_analysis"].get("trust_score") is not None],
            avg_trust=stats["avg_trust_score"],
            key_findings=(report or {}).get("key_findings") or [],
            top_complaints=(report or {}).get("top_complaints") or [],
            recommendations=(report or {}).get("recommendations") or [],
            fake_risk=(report or {}).get("fake_review_risk", "unknown"),
        )
        return stats

    def _build_html(self, product_name, stats, results, report):
        labels = {"positive": "正面", "negative": "负面", "neutral": "中性"}
        colors = {"positive": "#27785d", "negative": "#b64545", "neutral": "#697870"}
        total = stats["successful_count"]
        bars = "".join('<div class="bar"><span>' + labels[key] + '</span><div class="track"><i style="width:' + str(round(100 * count / total, 1) if total else 0) + '%;background:' + colors[key] + '"></i></div><b>' + str(count) + '</b></div>' for key, count in stats["sentiment_dist"].items())
        rows = []
        for result in results:
            final = result.get("final_analysis") or {}
            sa = result.get("sentiment_analysis") or {}
            success = result_succeeded(result)
            status = "已分析" if success else {"pending": "待分析 / 未选入模型样本", "cancelled": "已取消", "failed": "未完成"}.get(result.get("status"), "未完成")
            error = result.get("error") or {}
            message = final.get("summary") if success else (error.get("message") if isinstance(error, dict) else str(error)) or "分析未完成，可重试"
            rows.append('<tr><td>' + _text(status) + '</td><td>' + _text(result.get("review_text", "")) + '</td><td>' + _text(result.get("rating")) + '</td><td>' + _text(result.get("review_date") or "未知") + '</td><td>' + _text(labels.get(final.get("final_sentiment"), "未分析") if success else "未分析") + (' · 反讽' if success and sa.get("is_sarcastic") else '') + '</td><td>' + _text(final.get("trust_score") if success else None) + '</td><td>' + _text(message) + '</td><td>' + _link(result.get("source_url")) + '</td></tr>')
        sections = []
        collection = report.get("collection") or {}
        if collection.get("platform_summary") or collection.get("gaps"):
            body = []
            for platform in collection.get("platform_summary", []):
                body.append('<p>' + _text(platform.get("platform")) + '：实际 ' + _text(platform.get("actual_count")) + ' / 目标 ' + _text(platform.get("target_count")) + ' 条，缺口 ' + _text(platform.get("shortfall")) + ' 条。</p>')
            for gap in collection.get("gaps", []):
                body.append('<article><h3>' + _text(gap.get("platform")) + '</h3><p>' + _text(gap.get("message")) + '</p><p>原因：' + _text(gap.get("reason") or "具体原因尚未确定") + '</p><p>建议：' + _text(gap.get("suggested_action") or "查看平台提示后重试") + '</p>' + _link(gap.get("url")) + '</article>')
            sections.append('<section><h2>采集数量、失败原因与缺口</h2>' + ''.join(body) + '</section>')
        groups = report.get("groups") or []
        if groups:
            group_rows = []
            for group in groups:
                group_stats = group.get("statistics") or {}
                group_rows.append('<tr><td>' + _text(group.get("title")) + '</td><td>' + _text(group.get("brand")) + ' / ' + _text(group.get("model")) + '</td><td>' + _text(group.get("spec_label")) + '</td><td>' + _text(group.get("review_count")) + '</td><td>' + _text(group_stats.get("successful_count", 0)) + '</td><td>' + _text("已核对" if group.get("status") == "confirmed" else "单独待确认") + '</td></tr>')
            sections.append('<section><h2>独立商品组比较</h2><p>品牌、型号及关键规格分别核对；未知规格不自动归并。</p><div class="table-wrap"><table><thead><tr><th>商品</th><th>品牌 / 型号</th><th>规格</th><th>原文</th><th>模型已分析</th><th>身份状态</th></tr></thead><tbody>' + ''.join(group_rows) + '</tbody></table></div></section>')
        cost = report.get("model_cost") or {}
        if cost:
            coverage = report.get("model_coverage") or {}
            sections.append('<section><h2>模型费用与覆盖范围</h2><p>保守估算 ¥' + _text(cost.get("accounted_cny")) + ' / 上限 ¥1.50；原文 ' + _text(coverage.get("local_count", len(results))) + ' 条，模型已覆盖 ' + _text(total) + ' 条。</p><p>按高峰、未命中缓存价格估算，包含不确定请求预留，最终以供应商账单为准。其余原文未调用模型，不代表已逐条分析。</p></section>')
        for key, title in (("key_findings", "主要发现"), ("top_complaints", "用户反馈"), ("recommendations", "建议")):
            values = stats.get(key) or []
            if isinstance(values, list) and values:
                sections.append('<section><h2>' + title + '</h2><ul>' + ''.join('<li>' + _text(value) + '</li>' for value in values) + '</ul></section>')
        for key, title in (("pain_points", "用户痛点与原句"), ("improvements", "改进建议"), ("topics", "选题草稿")):
            items = (report.get(key) or {}).get("items", [])
            if not items:
                continue
            body = []
            for item in items:
                heading = item.get("statement") or item.get("action") or item.get("title") or item.get("topic") or "研究条目"
                quotes = ''.join('<blockquote>' + _text(e.get("quote", "")) + ' ' + _link(e.get("source_url")) + '</blockquote>' for e in item.get("evidence", []))
                body.append('<article><h3>' + _text(heading) + '</h3><p>' + _text(item.get("rationale") or item.get("verification") or item.get("hook") or "") + '</p>' + quotes + '</article>')
            sections.append('<section><h2>' + title + '</h2>' + ''.join(body) + '</section>')
        actions = report.get("actions") or []
        if actions:
            sections.append('<section><h2>行动计划</h2><ul>' + ''.join('<li>' + _text(a.get("label")) + ' · ' + _text(a.get("owner") or "未分配") + ' · ' + _text(a.get("due") or "未设日期") + ' · ' + _text(a.get("metric")) + '</li>' for a in actions) + '</ul></section>')
        drafts = report.get("drafts") or []
        if drafts:
            draft_body = []
            kinds = {"selling_point": "商品卖点", "support_script": "客服话术", "content_topic": "内容选题", "schedule": "排期"}
            for item in drafts:
                draft_body.append('<article><h3>' + _text(kinds.get(item.get("kind"), "运营草稿")) + ' · ' + _text(item.get("title")) + '</h3><p>' + _text(item.get("group_title")) + '</p><p style="white-space:pre-wrap">' + _text(item.get("body")) + '</p><p>渠道：' + _text(item.get("channel")) + '；日期：' + _text(item.get("scheduled_date") or "待定") + '</p><p>证据编号：' + _text(', '.join(item.get("evidence_ids", []))) + '</p></article>')
            sections.append('<section><h2>运营草稿</h2>' + ''.join(draft_body) + '</section>')
        if (report.get("content_kit") or {}).get("data"):
            import json
            sections.append('<section><h2>内容生产包 · 草稿</h2><pre style="white-space:pre-wrap;overflow-wrap:anywhere">' + _text(json.dumps(report["content_kit"]["data"], ensure_ascii=False, indent=2)) + '</pre></section>')
        return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>''' + _text(product_name) + ''' · 评论研究</title><style>
        *{box-sizing:border-box}body{margin:0;background:#f4f6f5;color:#202b26;font:14px/1.65 system-ui,"Microsoft YaHei",sans-serif}.page{max-width:1200px;margin:auto;padding:40px 24px}header{border-bottom:1px solid #d5ded8;padding-bottom:22px}h1{font-size:28px;line-height:1.3;margin:12px 0}h2{font-size:18px;margin:0 0 18px}small,.muted{color:#596b61}.metrics{display:grid;grid-template-columns:repeat(4,1fr);margin:24px 0;border:1px solid #d5ded8;background:white;border-radius:8px}.metric{padding:20px;border-right:1px solid #d5ded8}.metric:last-child{border:0}.metric strong{display:block;font-size:28px;font-variant-numeric:tabular-nums}section{background:white;border:1px solid #d5ded8;border-radius:8px;padding:24px;margin:20px 0}.bar{display:grid;grid-template-columns:50px 1fr 40px;gap:16px;align-items:center;margin:14px 0}.track{height:8px;background:#edf2ef;border-radius:4px;overflow:hidden}.track i{display:block;height:100%}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:12px;text-align:left;border-bottom:1px solid #e2e7e4;vertical-align:top}th{background:#f4f6f5;white-space:nowrap}td:nth-child(2){min-width:220px;white-space:pre-wrap}td:nth-child(7){min-width:180px}a{color:#216449}.note{padding:14px 18px;border-left:3px solid #27785d;background:#edf4ef}@media(max-width:680px){.page{padding:24px 14px}.metrics{grid-template-columns:repeat(2,1fr)}h1{font-size:24px}}@media print{body{background:white}.page{max-width:none;padding:0}section,tr{break-inside:avoid}table{font-size:10px}.table-wrap{overflow:visible}}
        </style></head><body><main class="page"><header><small>ReviewAgent · 评论研究</small><h1>''' + _text(product_name) + '''</h1><span class="muted">''' + _text(datetime.now().astimezone().isoformat(timespec="seconds")) + '''</span></header><div class="metrics">''' + ''.join('<div class="metric"><small>' + title + '</small><strong>' + _text(value) + '</strong></div>' for title, value in (("导入评论", stats["total"]), ("分析成功", total), ("分析未完成", stats["failed_count"] + stats["pending_count"] + stats["cancelled_count"]), ("平均可信度", stats["avg_trust"]))) + '''</div><p class="note">情绪分布以分析成功的评论为分母。反讽是独立表达标志，不重复计入情绪总数；未知评分与日期保留为空。可信度为模型判断，不代表已确认评论来源或作者身份。</p><section><h2>情绪分布</h2>''' + (bars if total else '<p>没有分析成功的样本，暂不计算分布。</p>') + '''<p class="muted">反讽 ''' + str(stats["sarcastic_count"]) + ''' 条；需复核 ''' + str(stats["suspicious_count"]) + ''' 条。</p></section>''' + ''.join(sections) + '''<section><h2>逐条结果与证据</h2><div class="table-wrap"><table><thead><tr><th>状态</th><th>评论原文</th><th>评分</th><th>发布时间</th><th>情绪</th><th>可信度</th><th>判断与下一步</th><th>来源</th></tr></thead><tbody>''' + ''.join(rows) + '''</tbody></table></div></section></main></body></html>'''

    def _trust_color(self, score):
        return "#697870" if score is None else "#27785d" if score >= 70 else "#92612a" if score >= 40 else "#b64545"
