"""ReviewPilot Streamlit UI."""
# force reload trigger

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import json
import base64
import time
import tempfile
import webbrowser
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
import pandas as pd
from history_manager import (
    save_history_record, load_history, delete_record,
    clear_all_history,
)
from trust_report import TrustReportEngine

st.set_page_config(
    page_title="ReviewPilot",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_config():
    try:
        import config
        return config
    except Exception:
        return None

@st.cache_resource
def get_agent():
    try:
        from config import MODEL
        from fallback_client import create_llm_client
        llm_client = create_llm_client()
        from sentiment_agent_core import ReviewAnalysisAgent
        agent = ReviewAnalysisAgent(client=llm_client, model=MODEL)
        return agent, None
    except Exception as e:
        return None, str(e)


def apply_styles():
    import importlib
    import _ui_styles
    importlib.reload(_ui_styles)
    from _ui_styles import get_styles
    st.markdown(get_styles("light"), unsafe_allow_html=True)


def t(zh: str, en: str) -> str:
    """Return UI copy in the selected language."""
    return en if st.session_state.get("language", "zh") == "en" else zh


# ──────────────────────────────────────────────────────────────
# UI 辅助组件
# ──────────────────────────────────────────────────────────────

def metric_card_html(value, label, meta="LIVE", tone="orange"):
    return f"""
    <div class="rp-metric rp-metric-{tone}">
        <div class="rp-metric-top"><span>{label}</span><span class="rp-metric-dot"></span></div>
        <div class="rp-metric-value">{value}</div>
        <div class="rp-metric-footer"><span>{meta}</span><span class="rp-metric-line"></span></div>
    </div>
    """


def render_page_header(title, subtitle):
    st.markdown(f'<div class="rp-page-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="rp-page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def render_ethics_banner():
    st.markdown(f"""
    <div class="rp-ethics">
        <strong>{t("数据原则", "Data principles")}</strong>&nbsp;&nbsp;
        {t("分析只基于真实评论，每条评论都保留可追溯来源。", "Analysis is based on authentic reviews, with traceable sources preserved for every item.")}
    </div>
    """, unsafe_allow_html=True)


def trust_color(score):
    if score >= 70:
        return "#12b76a"
    elif score >= 40:
        return "#f79009"
    return "#d92d20"


def _resolve_display_name(product_name: str, platform: str = "") -> str:
    """Resolve a display-friendly product name, replacing invalid names like 'item.htm'."""
    pname = (product_name or "").strip()
    plat = (platform or "").lower()
    invalid_names = {"按图片搜索", "item.htm", "item.html", "未命名产品", ""}
    # SKU 选项标签特征：包含"计算器"/"单价"等与商品无关的词
    sku_like_keywords = ("计算器", "单价", "最小单价")
    if (pname in invalid_names
            or (pname.endswith(".htm") and len(pname) < 15)
            or any(kw in pname for kw in sku_like_keywords)):
        if "jd" in plat:
            return "京东链接商品采集分析"
        elif "taobao" in plat or "tmall" in plat:
            return "淘宝链接商品采集分析"
        else:
            return "商品链接采集分析"
    return pname


def _demo_record():
    """Return a realistic, read-only sample analysis for the current session."""
    demo_rows = [
        ("屏幕清晰，运动记录和睡眠监测都很直观，续航用了六天还有电。", 5, "positive", False, "真实有效", 94),
        ("表带比较柔软，全天佩戴不会勒手，消息提醒偶尔会延迟。", 4, "positive", False, "真实有效", 88),
        ("定位速度比旧款快很多，户外跑步轨迹基本准确。", 5, "positive", False, "真实有效", 91),
        ("功能够用，应用里的图表还可以再简单一些。", 4, "neutral", False, "真实有效", 82),
        ("客服响应很快，换货流程两天就处理完了。", 5, "positive", False, "真实有效", 90),
        ("充电底座吸力一般，轻碰一下会移位。", 3, "negative", False, "真实有效", 78),
        ("真是太智能了，抬腕三次终于亮屏。", 2, "negative", True, "真实有效", 61),
        ("很好很好很好，质量非常好，值得购买。", 5, "positive", False, "模板化好评", 27),
    ]
    results = []
    reviews = []
    for text_value, rating, sentiment, sarcastic, validity, trust in demo_rows:
        reviews.append({"review_text": text_value, "rating": rating, "platform": "jd", "extraction_method": "demo"})
        results.append({
            "review_text": text_value,
            "rating": rating,
            "sentiment_analysis": {"sentiment_label": sentiment, "is_sarcastic": sarcastic},
            "validity_analysis": {"validity_label": validity},
            "final_analysis": {
                "trust_score": trust,
                "final_validity": "suspicious" if trust < 40 else "valid",
                "risk_level": "高" if trust < 40 else ("中" if trust < 70 else "低"),
            },
        })
    return {
        "id": "reviewpilot_demo_analysis",
        "timestamp": "2026-09-28T09:30:00",
        "timestamp_display": "2026-09-28 09:30:00",
        "source": "product_url",
        "platform": "jd",
        "url": "",
        "product_name": "AuroraFit X1 智能运动手表",
        "review_count": len(results),
        "sarcastic_count": 1,
        "suspicious_count": 1,
        "avg_trust_score": 76.4,
        "sentiment_distribution": {"positive": 5, "neutral": 1, "negative": 2},
        "extraction_methods": {"demo": len(results)},
        "report": {
            "summary": "整体口碑积极，用户认可屏幕、佩戴体验和运动记录；抬腕唤醒和充电底座是主要改进点。",
            "strengths": ["屏幕清晰", "续航稳定", "运动轨迹准确", "售后响应快"],
            "risks": ["抬腕唤醒灵敏度", "充电底座吸附力", "少量模板化评论"],
        },
        "trust_report": {"overall_score": 76.4, "risk_level": "low", "sample": True},
        "results": results,
        "reviews": reviews,
        "html_report_path": os.path.join(PROJECT_ROOT, "static", "demo_analysis_report.html"),
        "is_demo": True,
    }


def _display_history():
    """Combine persistent records with the session-removable product demo."""
    records = load_history()
    if not st.session_state.get("_demo_hidden", False):
        return [_demo_record(), *[r for r in records if r.get("id") != "reviewpilot_demo_analysis"]]
    return records

# ──────────────────────────────────────────────────────────────
# 仪表盘
# ──────────────────────────────────────────────────────────────

def render_dashboard():
    """Dashboard with aggregate metrics and recent analyses."""
    st.markdown(f"""
    <div class="rp-hero">
        <div>
            <h1>{t("读懂每一条评论", "Understand every review")}</h1>
            <p>{t("跨平台采集淘宝和京东评论，结合 OCR 与批量数据处理，生成情绪、反讽、可信度和产品口碑分析。", "Collect reviews across Taobao and JD, process screenshots and batch data, and turn feedback into sentiment, sarcasm, trust and product reputation insights.")}</p>
        </div>
        <div class="rp-hero-mark">Review intelligence</div>
    </div>
    """, unsafe_allow_html=True)

    try:
        records = _display_history()
    except Exception:
        records = []

    total_analyses = len(records)
    total_reviews = sum(int(r.get("review_count", 0) or 0) for r in records)
    trust_scores = [r.get("avg_trust_score") for r in records if r.get("avg_trust_score") is not None]
    avg_trust = sum(trust_scores) / len(trust_scores) if trust_scores else 0
    total_sarcastic = sum(int(r.get("sarcastic_count", 0) or 0) for r in records)
    total_suspicious = sum(int(r.get("suspicious_count", 0) or 0) for r in records)

    # 情绪分布统计
    pos_total = neu_total = neg_total = 0
    for r in records:
        dist = r.get("sentiment_distribution", {}) or {}
        pos_total += int(dist.get("positive", dist.get("正面", 0)) or 0)
        neu_total += int(dist.get("neutral", dist.get("中性", 0)) or 0)
        neg_total += int(dist.get("negative", dist.get("负面", 0)) or 0)
    sentiment_total = pos_total + neu_total + neg_total

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(metric_card_html(total_analyses, t("分析任务", "Analyses"), t("示例 + 实时", "DEMO + LIVE"), "orange"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card_html(total_reviews, t("累计评论", "Reviews"), t("跨来源汇总", "ALL SOURCES"), "blue"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card_html(f"{avg_trust:.1f}", t("平均可信度", "Average trust"), t("满分 100", "OUT OF 100"), "green"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card_html(total_sarcastic, t("反讽评论", "Sarcastic"), t("语义识别", "SEMANTIC"), "purple"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card_html(total_suspicious, t("可疑评论", "Suspicious"), t("需要复核", "REVIEW"), "red"), unsafe_allow_html=True)

    st.markdown('<div class="rp-dashboard-gap"></div>', unsafe_allow_html=True)

    # 用 components.html 渲染整个仪表板区域，确保 JavaScript 在同一 iframe 内可执行
    import streamlit.components.v1 as components

    # 构建左侧饼图 HTML
    if sentiment_total > 0:
        pos_pct = pos_total / sentiment_total * 100
        neu_pct = neu_total / sentiment_total * 100
        neg_pct = neg_total / sentiment_total * 100
        default_chart = f"""
        <div class="rp-donut-wrap" id="chart-default">
            <div class="rp-donut" style="background: conic-gradient(#12b76a 0% {pos_pct}%, #f79009 {pos_pct}% {pos_pct + neu_pct}%, #d92d20 {pos_pct + neu_pct}% 100%);">
                <div class="rp-donut-hole"><div class="rp-donut-value">{sentiment_total}</div><div class="rp-donut-label">{t("总评论", "Reviews")}</div></div>
            </div>
            <div class="rp-legend">
                <div class="rp-legend-item"><span class="rp-legend-dot" style="background:#12b76a"></span><span>{t("正面", "Positive")}</span><span class="rp-legend-pct">{pos_pct:.1f}% ({pos_total})</span></div>
                <div class="rp-legend-item"><span class="rp-legend-dot" style="background:#f79009"></span><span>{t("中性", "Neutral")}</span><span class="rp-legend-pct">{neu_pct:.1f}% ({neu_total})</span></div>
                <div class="rp-legend-item"><span class="rp-legend-dot" style="background:#d92d20"></span><span>{t("负面", "Negative")}</span><span class="rp-legend-pct">{neg_pct:.1f}% ({neg_total})</span></div>
            </div>
        </div>"""
    else:
        default_chart = f'<div style="text-align:center;padding:40px 0;color:#8a8782;" id="chart-default">{t("暂无分析数据", "No analysis data yet")}</div>'

    # 情绪标签映射
    POSITIVE_KEYS = {"positive", "正面", "真诚好评", "好评", "满意"}
    NEUTRAL_KEYS = {"neutral", "中性", "一般", "普通"}
    NEGATIVE_KEYS = {"negative", "负面", "差评", "不满", "抱怨"}
    SARCASTIC_KEYS = {"sarcasm", "反讽", "反讽/阴阳怪气", "阴阳怪气"}

    hover_charts_html = ""
    recent_items_html = ""
    report_data_html = ""
    source_meta = {
        "single": ("S", "#ebe7e1", "#111111"),
        "product_url": ("U", "#e6f3ff", "#0007cb"),
        "screenshot": ("O", "#fff0e8", "#b93800"),
        "csv": ("C", "#e8f8ee", "#087443"),
    }

    PER_PAGE = 4
    total_recs = len(records)
    total_pages = max(1, (total_recs + PER_PAGE - 1) // PER_PAGE)

    for idx, rec in enumerate(records):
        page_num = idx // PER_PAGE + 1
        rec_id = rec.get("id", "")
        rec_plat = rec.get("platform", "")
        display_name = _resolve_display_name(rec.get("product_name", ""), rec_plat)
        dist = rec.get("sentiment_distribution", {}) or {}
        pos_r = neu_r = neg_r = sar_r = other_count = 0
        for k, v in dist.items():
            kl = k.lower()
            count = int(v or 0)
            if kl in POSITIVE_KEYS or "好评" in k or "满意" in k:
                pos_r += count
            elif kl in NEUTRAL_KEYS or "中性" in k or "一般" in k:
                neu_r += count
            elif kl in SARCASTIC_KEYS or "反讽" in k or "阴阳" in k:
                sar_r += count
            elif kl in NEGATIVE_KEYS or "差评" in k or "不满" in k or "抱怨" in k:
                neg_r += count
            else:
                other_count += count
        rec_total = pos_r + neu_r + neg_r + sar_r + other_count

        if rec_total > 0:
            pos_p = pos_r / rec_total * 100
            neu_p = neu_r / rec_total * 100
            neg_p = neg_r / rec_total * 100
            sar_p = sar_r / rec_total * 100
            stops = [f"#12b76a 0% {pos_p:.1f}%"]
            cumulative = pos_p
            if neu_p > 0:
                stops.append(f"#f79009 {cumulative:.1f}% {cumulative + neu_p:.1f}%")
                cumulative += neu_p
            if sar_p > 0:
                stops.append(f"#7a5af8 {cumulative:.1f}% {cumulative + sar_p:.1f}%")
                cumulative += sar_p
            if neg_p > 0:
                stops.append(f"#d92d20 {cumulative:.1f}% {cumulative + neg_p:.1f}%")
                cumulative += neg_p
            if other_count > 0:
                stops.append(f"#8a8782 {cumulative:.1f}% 100%")
            else:
                stops.append(f"#d92d20 {cumulative:.1f}% 100%")
            grad_stops = ", ".join(stops)
            chart_name = display_name[:18]

            legend_items = ""
            if pos_r > 0:
                legend_items += f'<div class="rp-legend-item"><span class="rp-legend-dot" style="background:#12b76a"></span><span>{t("正面", "Positive")}</span><span class="rp-legend-pct">{pos_p:.0f}% ({pos_r})</span></div>'
            if neu_r > 0:
                legend_items += f'<div class="rp-legend-item"><span class="rp-legend-dot" style="background:#f79009"></span><span>{t("中性", "Neutral")}</span><span class="rp-legend-pct">{neu_p:.0f}% ({neu_r})</span></div>'
            if sar_r > 0:
                legend_items += f'<div class="rp-legend-item"><span class="rp-legend-dot" style="background:#7a5af8"></span><span>{t("反讽", "Sarcastic")}</span><span class="rp-legend-pct">{sar_p:.0f}% ({sar_r})</span></div>'
            if neg_r > 0:
                legend_items += f'<div class="rp-legend-item"><span class="rp-legend-dot" style="background:#d92d20"></span><span>{t("负面", "Negative")}</span><span class="rp-legend-pct">{neg_p:.0f}% ({neg_r})</span></div>'

            hover_charts_html += f'<div class="rp-donut-wrap rp-hover-chart" id="chart-{rec_id}" style="display:none;"><div class="rp-donut" style="background: conic-gradient({grad_stops});"><div class="rp-donut-hole"><div class="rp-donut-value">{rec_total}</div><div class="rp-donut-label">{chart_name}</div></div></div><div class="rp-legend">{legend_items}</div></div>'

        # 右侧历史记录条目
        src = rec.get("source", "")
        icon, bg, fg = source_meta.get(src, ("A", "#ebe7e1", "#626260"))
        tscore = rec.get("avg_trust_score", 0)
        tcolor = trust_color(tscore)
        ts_disp = rec.get("timestamp_display", "")[5:16] if rec.get("timestamp_display", "") else ""
        review_count = rec.get("review_count", 0)
        rec_url = rec.get("url", "")

        # 读取 HTML 报告并 base64 编码
        html_report_path = rec.get("html_report_path", "")
        report_b64 = ""
        if html_report_path and os.path.exists(html_report_path):
            try:
                if os.path.getsize(html_report_path) < 500000:
                    with open(html_report_path, "r", encoding="utf-8") as f:
                        report_b64 = base64.b64encode(f.read().encode("utf-8")).decode("ascii")
            except Exception:
                pass
        report_data_html += f'<div id="report-b64-{rec_id}" style="display:none;">{report_b64}</div>'

        # 名称区域（红框）：点击跳转原网页
        if rec_url:
            safe_url = rec_url.replace("&", "&amp;").replace('"', "&quot;").replace("'", "&#39;")
            name_html = f'<a href="{safe_url}" target="_blank" class="rp-rec-name" onclick="event.stopPropagation()" title="{t("打开原网页", "Open source page")}">{display_name}</a>'
        else:
            name_html = f'<span class="rp-rec-name rp-rec-name-nolink">{display_name}</span>'

        # 分数区域（绿框）：左键查看报告，右键固定饼图
        if report_b64:
            score_onclick = f"rpOpenReport('{rec_id}', event)"
            score_title = t("左键查看报告，右键固定图表", "Left click for report, right click to pin chart")
        else:
            score_onclick = "event.stopPropagation()"
            score_title = t("右键固定图表", "Right click to pin chart")

        item_display = "" if page_num == 1 else "none"
        recent_items_html += f"""<div class="rp-recent-item" data-rec-id="{rec_id}" data-page="{page_num}" style="display:{item_display};" onmouseover="rpHoverChart('{rec_id}')" onmouseout="rpHoverDefault()"><div class="rp-rec-icon" style="background:{bg};color:{fg};">{icon}</div><div class="rp-rec-info">{name_html}<div class="rp-rec-meta">{review_count} {t("条", "reviews")} · {ts_disp}</div></div><div class="rp-rec-score" onclick="{score_onclick}" oncontextmenu="rpPinChart('{rec_id}', event)" title="{score_title}"><div class="rp-rec-score-val" style="color:{tcolor};">{tscore}</div><div class="rp-rec-score-label">{t("可信度", "Trust")}</div></div></div>"""

    pager_html = f'<div class="rp-pager" id="rp-pager" data-total-pages="{total_pages}"><button class="rp-pager-btn" id="rp-prev" onclick="rpChangePage(-1)">{t("上一页", "Previous")}</button><span class="rp-pager-info" id="rp-page-info">1 / {total_pages}</span><button class="rp-pager-btn" id="rp-next" onclick="rpChangePage(1)">{t("下一页", "Next")}</button></div>' if total_recs > PER_PAGE else ''

    tips_html = f'<div class="rp-tips"><span class="rp-tips-title">{t("操作提示", "Tips")}</span><div class="rp-tips-item">{t("点击名称打开来源页面", "Select a name to open its source")}</div><div class="rp-tips-item">{t("点击分数查看报告，右键固定图表", "Select a score for its report, or right click to pin the chart")}</div></div>'

    dashboard_html = f"""
    <link rel="stylesheet" href="/app/static/vendor/lenis.css">
    <style>
    * {{ box-sizing:border-box; }}
    body {{ margin:0;background:#f5f1ec;font-family:Inter,system-ui,sans-serif;overflow:hidden; }}
    .rp-db-container {{ display:grid;grid-template-columns:minmax(0,1.58fr) minmax(300px,1fr);gap:24px;width:100%;align-items:stretch;padding:2px; }}
    .rp-db-left,.rp-db-right {{ display:flex;min-width:0; }}
    .rp-db-card {{ position:relative;isolation:isolate;overflow:hidden;background:rgba(255,255,255,.96);border:1px solid #d3cec6;border-radius:16px;padding:26px;box-shadow:0 12px 34px rgba(17,17,17,.055);width:100%;min-height:400px;display:flex;flex-direction:column;transition:transform .28s ease,border-color .28s ease,box-shadow .28s ease; }}
    .rp-db-card:hover {{ transform:translateY(-3px);border-color:#bdb7ae;box-shadow:0 18px 44px rgba(17,17,17,.075); }}
    .rp-db-card::after {{ content:"";position:absolute;inset:auto -80px -110px auto;width:230px;height:230px;border-radius:50%;background:radial-gradient(circle,rgba(255,86,0,.09),rgba(255,86,0,0) 70%);z-index:-1;pointer-events:none; }}
    .rp-db-card > * {{ position:relative;z-index:2; }}
    .rp-db-title {{ display:flex;align-items:center;justify-content:space-between;font-size:14px;font-weight:600;color:#111;margin-bottom:22px;letter-spacing:-.1px; }}
    .rp-db-kicker {{ font-size:9px;letter-spacing:.14em;color:#b93800;text-transform:uppercase;background:#fff0e8;border:1px solid #ffd7c2;border-radius:999px;padding:5px 8px; }}
    .rp-donut-wrap {{ display:flex;align-items:center;gap:34px;flex:1;justify-content:center; }}
    .rp-donut {{ width:190px;height:190px;border-radius:50%;flex-shrink:0; }}
    .rp-donut-hole {{ width:134px;height:134px;background:rgba(255,255,255,.96);border-radius:50%;margin:28px auto;display:flex;flex-direction:column;align-items:center;justify-content:center;box-shadow:inset 0 0 0 1px #eee9e3; }}
    .rp-donut-value {{ font-size:30px;font-weight:500;color:#111;letter-spacing:-1px; }}
    .rp-donut-label {{ font-size:11px;color:#626260;max-width:110px;text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:3px; }}
    .rp-legend {{ display:flex;flex-direction:column;gap:8px; }}
    .rp-legend-item {{ display:flex;align-items:center;gap:8px;font-size:12px;color:#626260; }}
    .rp-legend-dot {{ width:8px;height:8px;border-radius:50%;flex-shrink:0; }}
    .rp-legend-pct {{ margin-left:auto;color:#8a8782;font-size:11px; }}
    .rp-recent-list {{ flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:9px; }}
    .rp-recent-item {{ padding:13px 12px;display:flex;align-items:center;gap:11px;border:1px solid #e7e2dc;border-radius:10px;background:rgba(255,255,255,.82);transition:transform .2s ease,border-color .2s ease,background .2s ease; }}
    .rp-recent-item:hover {{ background:#fffaf6;border-color:#ffc3a3; }}
    .rp-recent-item:last-child {{ border-bottom:none; }}
    .rp-recent-item.rp-pinned {{ background:#fff0e8!important; }}
    .rp-rec-icon {{ width:28px;height:28px;font-size:12px;display:flex;align-items:center;justify-content:center;border-radius:6px;flex-shrink:0; }}
    .rp-rec-info {{ flex:1;min-width:0; }}
    .rp-rec-name {{ display:block;font-size:12px;font-weight:500;color:#0007cb;text-decoration:none;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }}
    .rp-rec-name:hover {{ text-decoration:underline; }}
    .rp-rec-name-nolink {{ color:#111;cursor:default; }}
    .rp-rec-name-nolink:hover {{ text-decoration:none; }}
    .rp-rec-meta {{ font-size:10px;color:#8a8782;margin-top:2px; }}
    .rp-rec-score {{ text-align:right;flex-shrink:0;cursor:pointer;padding:4px 6px;border-radius:6px;transition:background .15s; }}
    .rp-rec-score:hover {{ background:#f5f1ec; }}
    .rp-rec-score-val {{ font-size:15px;font-weight:600; }}
    .rp-rec-score-label {{ font-size:9px;color:#8a8782; }}
    .rp-tips {{ margin-top:10px;padding:10px 0 0;border-top:1px solid #e7e2dc;font-size:10px;color:#8a8782;line-height:1.7; }}
    .rp-tips-title {{ font-weight:600;color:#626260;display:block;margin-bottom:2px; }}
    .rp-tips-item {{ padding-left:2px; }}
    .rp-pager {{ display:flex;align-items:center;justify-content:center;gap:8px;margin-top:8px; }}
    .rp-pager-btn {{ border:1px solid #d3cec6;background:#fff;color:#111;padding:5px 10px;border-radius:6px;font-size:11px;cursor:pointer;transition:all .15s; }}
    .rp-pager-btn:hover {{ border-color:#111; }}
    .rp-pager-btn:disabled {{ opacity:0.4;cursor:not-allowed; }}
    .rp-pager-info {{ font-size:11px;color:#626260;min-width:60px;text-align:center; }}
    @media (max-width:760px) {{ .rp-db-container{{grid-template-columns:1fr;}} .rp-db-card{{min-height:360px;}} }}
    @media (prefers-reduced-motion:reduce) {{ *,*::before,*::after{{animation:none!important;transition:none!important;scroll-behavior:auto!important;}} }}
    </style>
    <div class="rp-db-container">
        <div class="rp-db-left">
            <div class="rp-db-card">
                <div class="rp-db-title"><span>{t("评论情绪分布", "Sentiment distribution")}</span><span class="rp-db-kicker">INSIGHT</span></div>
                {default_chart}
                {hover_charts_html}
            </div>
        </div>
        <div class="rp-db-right">
            <div class="rp-db-card">
                <div class="rp-db-title"><span>{t("最近分析", "Recent analyses")}</span><span class="rp-db-kicker">RECENT</span></div>
                <div class="rp-recent-list">
                {recent_items_html if recent_items_html else f'<div style="text-align:center;padding:40px 0;color:#8a8782;">{t("暂无历史记录", "No history yet")}</div>'}
                </div>
                {pager_html}
                {tips_html if recent_items_html else ''}
            </div>
        </div>
    </div>
    {report_data_html}
    <script src="/app/static/vendor/lenis.min.js"></script>
    <script src="/app/static/vendor/gsap.min.js"></script>
    <script>
    var rpPinnedChart = null;
    function rpShowChart(recId) {{
        document.querySelectorAll('.rp-hover-chart').forEach(el => el.style.display = 'none');
        var def = document.getElementById('chart-default');
        if (def) def.style.display = 'none';
        var target = document.getElementById('chart-' + recId);
        if (target) target.style.display = 'flex';
    }}
    function rpShowDefault() {{
        document.querySelectorAll('.rp-hover-chart').forEach(el => el.style.display = 'none');
        var def = document.getElementById('chart-default');
        if (def) def.style.display = 'flex';
    }}
    function rpHoverChart(recId) {{
        if (rpPinnedChart) return;
        rpShowChart(recId);
    }}
    function rpHoverDefault() {{
        if (rpPinnedChart) return;
        rpShowDefault();
    }}
    function rpPinChart(recId, event) {{
        event.preventDefault();
        event.stopPropagation();
        rpPinnedChart = recId;
        document.querySelectorAll('.rp-recent-item').forEach(el => el.classList.remove('rp-pinned'));
        var item = document.querySelector('[data-rec-id="' + recId + '"]');
        if (item) item.classList.add('rp-pinned');
        rpShowChart(recId);
    }}
    function rpUnpin() {{
        if (!rpPinnedChart) return;
        rpPinnedChart = null;
        document.querySelectorAll('.rp-recent-item').forEach(el => el.classList.remove('rp-pinned'));
        rpShowDefault();
    }}
    function rpOpenReport(recId, event) {{
        event.stopPropagation();
        var b64El = document.getElementById('report-b64-' + recId);
        if (!b64El || !b64El.textContent.trim()) return;
        try {{
            var b64 = b64El.textContent.trim();
            var binary = atob(b64);
            var bytes = new Uint8Array(binary.length);
            for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            var html = new TextDecoder('utf-8').decode(bytes);
            var blob = new Blob([html], {{type: 'text/html;charset=utf-8'}});
            var url = URL.createObjectURL(blob);
            window.open(url, '_blank');
            setTimeout(function() {{ URL.revokeObjectURL(url); }}, 3000);
        }} catch(e) {{
            alert('{t("报告打开失败", "Could not open report")}: ' + e.message);
        }}
    }}
    var rpCurrentPage = 1;
    function rpChangePage(delta) {{
        var pager = document.getElementById('rp-pager');
        if (!pager) return;
        var totalPages = parseInt(pager.dataset.totalPages);
        var newPage = rpCurrentPage + delta;
        if (newPage < 1 || newPage > totalPages) return;
        rpCurrentPage = newPage;
        document.querySelectorAll('.rp-recent-item').forEach(function(el) {{
            el.style.display = (parseInt(el.dataset.page) === rpCurrentPage) ? '' : 'none';
        }});
        document.getElementById('rp-page-info').textContent = rpCurrentPage + ' / ' + totalPages;
        document.getElementById('rp-prev').disabled = (rpCurrentPage <= 1);
        document.getElementById('rp-next').disabled = (rpCurrentPage >= totalPages);
    }}
    document.addEventListener('click', function(e) {{
        if (!rpPinnedChart) return;
        if (!e.target.closest('.rp-recent-item') && !e.target.closest('a') && !e.target.closest('.rp-tips') && !e.target.closest('.rp-pager')) {{
            rpUnpin();
        }}
    }});
    try {{
        var pdoc = window.parent.document;
        if (!pdoc._rpUnpinBound) {{
            pdoc._rpUnpinBound = true;
            pdoc.addEventListener('click', function() {{
                if (rpPinnedChart) rpUnpin();
            }});
        }}
    }} catch(e) {{}}
    (function() {{
        var prev = document.getElementById('rp-prev');
        if (prev) prev.disabled = true;
    }})();
    window.addEventListener('load', function() {{
        var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (!reduceMotion && window.gsap) {{
            gsap.from('.rp-db-card', {{y:20,autoAlpha:0,duration:.68,ease:'power2.out',stagger:.1,clearProps:'transform,opacity,visibility'}});
            gsap.from('.rp-recent-item', {{x:12,autoAlpha:0,duration:.4,ease:'power1.out',stagger:.06,delay:.2,clearProps:'transform,opacity,visibility'}});
        }}
        try {{
            var pwin = window.parent;
            if (!reduceMotion && window.Lenis && pwin === pwin.top) {{
                if (pwin._rpLenis) pwin._rpLenis.destroy();
                pwin._rpLenis = new Lenis({{wrapper:pwin,content:pwin.document.documentElement,autoRaf:true,anchors:true,allowNestedScroll:true,respectReducedMotion:true,lerp:.12}});
            }}
        }} catch(e) {{}}
    }});
    </script>
    """

    components.html(dashboard_html, height=440, scrolling=False)


# ──────────────────────────────────────────────────────────────
# 爬虫降级逻辑（独立函数）
# ──────────────────────────────────────────────────────────────

def _scrape_taobao(scraper, url, cookies, max_reviews):
    """淘宝评论采集 — 4 级降级状态机。

    阶段流转：pw → (pw_confirm → pw_retry) → v2 → tb_api → done
    返回 (reviews, done)；done=False 表示需 st.rerun() 等待用户交互。
    """
    reviews = []
    stage_key = "_tb_confirm_stage"
    stage = st.session_state.get(stage_key, "pw")
    pw_scraper = st.session_state.get("_tb_pw_scraper")

    if stage == "pw":
        try:
            from scrapers.taobao_playwright_scraper import TaobaoPlaywrightScraper
            pw_scraper = TaobaoPlaywrightScraper(headless=False, max_reviews=max_reviews)
            st.session_state["_tb_pw_scraper"] = pw_scraper
            with st.spinner(t("正在启动浏览器采集淘宝评论...", "Starting browser collection for Taobao reviews...")):
                reviews = pw_scraper.scrape(url, cookies=cookies, max_reviews=max_reviews)
        except Exception:
            reviews = []
        if reviews:
            st.session_state[stage_key] = "done"
        else:
            st.session_state[stage_key] = "pw_confirm"
            st.rerun()

    elif stage == "pw_retry":
        # 用户在浏览器中手动滚动/登录后，重新运行同一 scraper
        with st.spinner(t("正在重新提取淘宝评论...", "Extracting Taobao reviews again...")):
            try:
                reviews = pw_scraper.scrape(url, cookies=cookies, max_reviews=max_reviews)
            except Exception:
                reviews = []
        if reviews:
            st.session_state[stage_key] = "done"
        else:
            st.session_state[stage_key] = "v2"
            st.rerun()

    elif stage == "pw_confirm":
        st.warning(t("浏览器未能自动提取淘宝评论，请查看已打开的浏览器窗口。", "The browser could not extract Taobao reviews automatically. Check the open browser window."))
        st.info(t("如果页面上能看到评论，请滚动评论区或完成登录，再重新提取。如果没有评论，请继续使用备用方式。", "If reviews are visible, scroll the review area or sign in, then extract again. Otherwise continue with the fallback method."))
        col_a, col_b = st.columns(2)
        if col_a.button(t("重新提取", "Extract again"), type="primary", key="btn_tb_pw_retry"):
            st.session_state[stage_key] = "pw_retry"
            st.rerun()
        if col_b.button(t("使用备用方式", "Use fallback"), key="btn_tb_pw_continue"):
            st.session_state[stage_key] = "v2"
            st.rerun()
        st.stop()

    elif stage == "v2":
        try:
            from scrapers.taobao_comment_v2 import TaobaoCommentScraperV2
            reviews = TaobaoCommentScraperV2().scrape(url, cookies=cookies, max_reviews=max_reviews)
        except Exception:
            reviews = []
        if reviews:
            st.session_state[stage_key] = "done"
        elif cookies:
            st.session_state[stage_key] = "tb_api"
            st.rerun()

    elif stage == "tb_api":
        try:
            from scrapers.taobao_scraper import TaobaoScraper
            tb = TaobaoScraper()
            tb.set_cookies(cookies)
            reviews = tb.scrape_with_cookies(url, cookies, max_reviews=max_reviews)
        except Exception:
            reviews = []
        st.session_state[stage_key] = "done"

    if st.session_state.get(stage_key) == "done":
        st.session_state.pop("_tb_confirm_stage", None)
        st.session_state.pop("_tb_pw_scraper", None)

    return reviews


def _scrape_jd(scraper, url, cookies, max_reviews):
    """京东评论采集 — 5 级降级状态机（统一抓取器内部完成）。

    阶段流转：dp → (dp_confirm → dp_reextract) → pw → (pw_confirm → pw_reextract)
              → api → done
    返回 (reviews, jd_scraper, done)；done=False 表示需 st.rerun() 等待用户交互。
    """
    reviews = []
    jd_scraper = None

    try:
        from scrapers.jd_unified_scraper import JDUnifiedScraper
        jd_scraper = JDUnifiedScraper(headless=False, max_reviews=max_reviews)
        st.session_state["_jd_scraper_ref"] = jd_scraper
        st.session_state["_jd_url"] = url

        confirm_key = "_jd_confirm_stage"
        stage = st.session_state.get(confirm_key, "dp")

        if stage == "dp":
            with st.spinner(t("正在启动 Chrome 采集京东评论...", "Starting Chrome to collect JD reviews...")):
                dp_reviews = jd_scraper._scrape_drissionpage(url, cookies)
            jd_scraper._method_results["drissionpage"] = (
                "成功 %d 条" % len(dp_reviews) if dp_reviews else "返回 0 条"
            )
            # 采集量不足预期的一半时，降级到 API（更可靠）
            min_expected = max_reviews * 0.5 if max_reviews > 0 else 0
            if dp_reviews and len(dp_reviews) >= min_expected:
                reviews = dp_reviews
                jd_scraper._last_method = "drissionpage"
                st.session_state[confirm_key] = "done"
            elif dp_reviews and len(dp_reviews) > 0:
                # DrissionPage 拿到一些但不够，存下来降级 API 补充
                jd_scraper._method_results["drissionpage_reviews"] = dp_reviews
                st.info(t(f"Chrome 采集到 {len(dp_reviews)} 条，正在通过 API 补充。", f"Chrome collected {len(dp_reviews)} reviews. Using the API to supplement them."))
                st.session_state[confirm_key] = "dp_supplement"
                st.rerun()
            else:
                st.session_state[confirm_key] = "dp_confirm"
                st.rerun()

        elif stage == "dp_reextract":
            with st.spinner(t("正在从浏览器重新提取评论...", "Extracting reviews from the browser again...")):
                reviews = jd_scraper.reextract_last(url)
            if reviews:
                jd_scraper._method_results["drissionpage"] = "重新提取成功 %d 条" % len(reviews)
                jd_scraper._last_method = "drissionpage"
                st.session_state[confirm_key] = "done"
            else:
                st.session_state[confirm_key] = "pw"
                st.rerun()

        elif stage == "dp_supplement":
            # DrissionPage 拿到一些但不够，用 API 补充（携带浏览器 cookies）
            dp_reviews = jd_scraper._method_results.get("drissionpage_reviews", [])
            browser_cookies = {}
            try:
                dp_scraper_inst = jd_scraper._scraper_instances.get("drissionpage")
                if dp_scraper_inst and hasattr(dp_scraper_inst, "get_browser_cookies"):
                    browser_cookies = dp_scraper_inst.get_browser_cookies()
                    print(f"[jd-supplement] 提取到 {len(browser_cookies)} 条浏览器 cookies")
            except Exception as e:
                print(f"[jd-supplement] 提取 cookies 失败: {e}")

            with st.spinner(t("正在通过 API 补充评论...", "Supplementing reviews through the API...")):
                api_reviews = jd_scraper._scrape_api(url, browser_cookies if browser_cookies else cookies)
            if api_reviews:
                # 合并去重
                seen_texts = set(r.get("review_text", "")[:80] for r in dp_reviews)
                merged = list(dp_reviews)
                for r in api_reviews:
                    txt = r.get("review_text", "")[:80]
                    if txt not in seen_texts:
                        merged.append(r)
                        seen_texts.add(txt)
                reviews = merged
                jd_scraper._method_results["drissionpage"] = f"Chrome + API 合并: {len(reviews)} 条"
                jd_scraper._method_results["api"] = f"补充 {len(api_reviews)} 条"
                jd_scraper._last_method = "drissionpage+api"
            else:
                reviews = dp_reviews
                jd_scraper._method_results["api"] = "API 返回 0 条（无有效 cookies）"
                jd_scraper._last_method = "drissionpage"
            st.session_state[confirm_key] = "done"

        elif stage == "dp_confirm":
            st.warning(t("Chrome 未能自动提取评论，请查看已打开的浏览器窗口。", "Chrome could not extract reviews automatically. Check the open browser window."))
            st.info(t("如果页面上能看到评论，请滚动评论区确保内容加载完成，再重新提取。如果没有评论，请继续使用备用方式。", "If reviews are visible, scroll until they finish loading, then extract again. Otherwise continue with the fallback method."))
            col_a, col_b = st.columns(2)
            if col_a.button(t("重新提取", "Extract again"), type="primary", key="btn_dp_reextract"):
                st.session_state[confirm_key] = "dp_reextract"
                st.rerun()
            if col_b.button(t("使用备用浏览器", "Use fallback browser"), key="btn_dp_continue"):
                st.session_state[confirm_key] = "pw"
                st.rerun()
            for method, result in jd_scraper._method_results.items():
                st.caption(f"{method}: {result}")
            st.stop()

        elif stage == "pw":
            with st.spinner(t("正在启动备用浏览器采集...", "Starting fallback browser collection...")):
                pw_reviews = jd_scraper._scrape_playwright(url, cookies)
            jd_scraper._method_results["playwright"] = (
                "成功 %d 条" % len(pw_reviews) if pw_reviews else "返回 0 条"
            )
            if pw_reviews:
                reviews = pw_reviews
                jd_scraper._last_method = "playwright"
                st.session_state[confirm_key] = "done"
            else:
                st.session_state[confirm_key] = "pw_confirm"
                st.rerun()

        elif stage == "pw_reextract":
            with st.spinner(t("正在从备用浏览器重新提取...", "Extracting from the fallback browser again...")):
                reviews = jd_scraper.reextract_last(url)
            if reviews:
                jd_scraper._method_results["playwright"] = "重新提取成功 %d 条" % len(reviews)
                jd_scraper._last_method = "playwright"
                st.session_state[confirm_key] = "done"
            else:
                st.session_state[confirm_key] = "api"
                st.rerun()

        elif stage == "pw_confirm":
            st.warning(t("备用浏览器仍未提取到评论，请查看已打开的浏览器窗口。", "The fallback browser could not extract reviews. Check the open browser window."))
            st.info(t("如果页面上能看到评论，请滚动评论区后重新提取。如果没有评论，请继续尝试 API。", "If reviews are visible, scroll the review area and extract again. Otherwise continue with the API."))
            col_a, col_b = st.columns(2)
            if col_a.button(t("重新提取", "Extract again"), type="primary", key="btn_pw_reextract"):
                st.session_state[confirm_key] = "pw_reextract"
                st.rerun()
            if col_b.button(t("继续使用 API", "Continue with API"), key="btn_pw_continue"):
                st.session_state[confirm_key] = "api"
                st.rerun()
            for method, result in jd_scraper._method_results.items():
                st.caption(f"{method}: {result}")
            st.stop()

        elif stage == "api":
            with st.spinner(t("正在通过 API 采集...", "Collecting through the API...")):
                reviews = jd_scraper._scrape_api(url, cookies)
            jd_scraper._method_results["api"] = (
                "成功 %d 条" % len(reviews) if reviews else "返回 0 条"
            )
            if reviews:
                jd_scraper._last_method = "api"
            st.session_state[confirm_key] = "done"

        elif stage == "done":
            pass  # reviews already set

        # 显示每级结果（完成后）
        if st.session_state.get(confirm_key) == "done":
            for method, result in jd_scraper._method_results.items():
                st.caption(f"{method}: {result}")
            del st.session_state[confirm_key]

    except Exception as e:
        st.warning(t(f"统一抓取器异常: {e}", f"Collector error: {e}"))
        reviews = []

    return reviews, jd_scraper


def _run_concurrent_analysis(agent, reviews, progress_bar=None):
    """使用 ThreadPoolExecutor 并发分析评论（max_workers=8）。

    返回 (results, auth_failed)。遇到 auth 错误会在 UI 上提示并返回 auth_failed=True。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = [None] * len(reviews)
    done_count = 0
    auth_failed = False

    # 预计算 TF-IDF 相似度，得到每条评论的 similar_count
    review_texts = [r.get("review_text", "") for r in reviews]
    try:
        similarity_matrix = agent._calculate_similarity(review_texts)
        similar_counts = [
            sum(1 for j in range(len(reviews))
                if i != j and similarity_matrix[i][j] > 0.7)
            for i in range(len(reviews))
        ]
    except Exception:
        similar_counts = [0] * len(reviews)

    def _analyze_one(idx_review):
        idx, review = idx_review
        try:
            result = agent.comprehensive_analysis(
                review_text=review.get("review_text", ""),
                rating=review.get("rating", 3),
                platform=review.get("platform", "未知"),
                product_name=review.get("product_name", ""),
                similar_count=similar_counts[idx],
            )
            result["similar_count"] = similar_counts[idx]
            sa = result.get("sentiment_analysis", {})
            if sa.get("error") and sa.get("error_type") == "auth":
                return idx, None, "auth"
            return idx, result, None
        except Exception as e:
            return idx, None, str(e)[:100]

    max_workers = min(8, max(2, len(reviews)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_analyze_one, (i, r)): i for i, r in enumerate(reviews)}
        for future in as_completed(futures):
            idx, result, err = future.result()
            done_count += 1
            if err == "auth":
                auth_failed = True
            elif err:
                st.warning(t(f"第 {idx+1} 条分析失败: {err}", f"Review {idx+1} failed: {err}"))
            else:
                results[idx] = result
            if progress_bar is not None:
                progress_bar.progress(done_count / len(reviews))

    results = [r for r in results if r is not None]
    return results, auth_failed


# ──────────────────────────────────────────────────────────────
# 页面：产品链接采集分析
# ──────────────────────────────────────────────────────────────

def page_product_url():
    """产品链接分析页面"""
    render_page_header(t("链接采集分析", "Link analysis"), t("粘贴淘宝或京东商品链接，自动采集评论并生成深度分析。", "Paste a Taobao or JD product link to collect reviews and generate an in-depth analysis."))

    if st.session_state.get("product_reviews"):
        reviews = st.session_state["product_reviews"]
        results = st.session_state.get("product_results", [])
        report = st.session_state.get("product_report", {})
        trust_report = st.session_state.get("product_trust_report", {})

        st.success(t(f"已完成 {len(reviews)} 条评论的分析", f"Completed analysis of {len(reviews)} reviews"))

        if st.button(t("再次分析", "Start another analysis")):
            for key in ["product_reviews", "product_results", "product_report", "product_trust_report"]:
                st.session_state.pop(key, None)
            st.rerun()

        display_results(reviews, results, report, trust_report)
        return

    url = st.text_input(
        t("产品链接", "Product link"),
        placeholder="https://item.jd.com/100012345.html 或 https://item.taobao.com/item.htm?id=xxx",
        label_visibility="collapsed",
    )
    col1, _ = st.columns(2)
    with col1:
        max_reviews = st.number_input(t("最大采集量（0 表示无上限）", "Maximum reviews (0 for unlimited)"), 0, 100000, 100)
        _max_reviews = max_reviews if max_reviews > 0 else 1000000

    if st.button(t("开始采集并分析", "Collect and analyze"), type="primary"):
        if not url.strip():
            st.warning(t("请输入产品链接", "Enter a product link"))
            return

        reviews = []

        with st.spinner(t("正在采集评论...", "Collecting reviews...")):
            try:
                from scrapers.multi_platform import MultiPlatformScraper
                scraper = MultiPlatformScraper()

                cookie_dir = os.path.join(PROJECT_ROOT, "cookies")
                for plat in ["taobao", "jd"]:
                    ck_path = os.path.join(cookie_dir, f"{plat}_cookies.json")
                    if os.path.exists(ck_path):
                        try:
                            with open(ck_path, "r", encoding="utf-8") as f:
                                ck_data = json.load(f)
                            ck = ck_data.get("cookies", {})
                            if ck:
                                scraper.set_platform_cookies(plat, ck)
                        except Exception:
                            pass

                detected = MultiPlatformScraper.detect_platform(url)

                if detected == "taobao":
                    ck = scraper._platform_cookies.get("taobao", {})
                    reviews = _scrape_taobao(scraper, url, ck, _max_reviews)

                elif detected == "jd":
                    ck = scraper._platform_cookies.get("jd", {})
                    reviews, jd_scraper = _scrape_jd(scraper, url, ck, _max_reviews)

                    # 截图兜底：所有方式均未抓到评论时，收集浏览器截图 + OCR
                    if not reviews and jd_scraper:
                        screenshots = jd_scraper.get_screenshots()
                        if screenshots:
                            st.info(t(f"自动采集未成功，正在识别 {len(screenshots)} 张评论区截图。", f"Automatic collection did not succeed. Reading {len(screenshots)} review screenshots with OCR."))
                            try:
                                from screenshot_analyzer import create_screenshot_analyzer
                                analyzer = create_screenshot_analyzer()
                                ocr_reviews = []
                                for sp in screenshots:
                                    try:
                                        with open(sp, "rb") as img_f:
                                            img_bytes = img_f.read()
                                        parsed, err = analyzer.analyze_screenshot(
                                            img_bytes, platform="jd", product_url=url
                                        )
                                        if parsed and not err:
                                            ocr_reviews.extend(parsed)
                                    except Exception:
                                        continue
                                if ocr_reviews:
                                    for r in ocr_reviews:
                                        r.setdefault("source_platform", "jd")
                                        r.setdefault("source_url", url)
                                        r.setdefault("platform", "jd")
                                        r["extraction_method"] = "screenshot_ocr"
                                    reviews = ocr_reviews
                                    st.success(t(f"OCR 从截图中识别出 {len(reviews)} 条评论", f"OCR extracted {len(reviews)} reviews from screenshots"))
                            except Exception as e:
                                st.warning(t(f"OCR 识别失败: {e}", f"OCR failed: {e}"))
                    if not reviews:
                        try:
                            reviews = scraper.scrape_product(url, max_reviews=_max_reviews)
                        except Exception:
                            reviews = []

                else:
                    reviews = scraper.scrape_product(url, max_reviews=_max_reviews)

            except Exception as e:
                st.error(t(f"采集失败: {e}", f"Collection failed: {e}"))
                return

        if not reviews:
            st.warning(t("自动采集未获取到评论数据", "No reviews were collected automatically"))
            st.info(t("请登录对应平台后重试，或使用截图识别分析。", "Sign in to the platform and try again, or use screenshot analysis."))
            return

        has_trace = all(r.get("source_platform") for r in reviews)
        if has_trace:
            st.success(t(f"采集到 {len(reviews)} 条评论，全部含溯源信息", f"Collected {len(reviews)} reviews with complete source data"))
        else:
            st.warning(t(f"采集到 {len(reviews)} 条评论，部分缺少溯源信息", f"Collected {len(reviews)} reviews; some source data is missing"))

        df_preview = pd.DataFrame(reviews)
        display_cols = ["review_text", "rating", "platform"]
        for extra in ["source_platform", "extraction_method"]:
            if extra in df_preview.columns:
                display_cols.append(extra)
        st.table(df_preview[[c for c in display_cols if c in df_preview.columns]].head(10).style.hide(axis="index"))

        agent, err = get_agent()
        if err:
            st.error(t(f"分析服务初始化失败: {err}", f"Analysis service failed to initialize: {err}"))
            return

        with st.spinner(t(f"正在分析 {len(reviews)} 条评论...", f"Analyzing {len(reviews)} reviews...")):
            progress = st.progress(0)
            results, auth_failed = _run_concurrent_analysis(agent, reviews, progress)
            if auth_failed:
                st.error(t("API Key 认证失败，请检查 .env 配置。", "API key authentication failed. Check your .env configuration."))
                st.stop()

        with st.spinner(t("正在生成口碑报告...", "Generating reputation report...")):
            report = agent.generate_report(results, product_name=reviews[0].get("product_name", "产品"))

        with st.spinner(t("正在生成可信度报告...", "Generating trust report...")):
            try:
                trust_report = TrustReportEngine().generate_report(reviews, results)
            except Exception:
                trust_report = {}

        # Save to history
        try:
            _detected = "jd" if "jd." in url or "jd.com" in url else ("taobao" if "taobao" in url or "tmall" in url else "unknown")
            _plat = reviews[0].get("source_platform", reviews[0].get("platform", _detected)) if reviews else _detected
            _pname = _resolve_display_name(
                reviews[0].get("product_name", "") if reviews else "", _plat
            )
            save_history_record(
                source="product_url", platform=_plat, url=url,
                product_name=_pname,
                reviews=reviews, results=results, report=report, trust_report=trust_report,
            )
        except Exception:
            pass

        st.session_state["product_reviews"] = reviews
        st.session_state["product_results"] = results
        st.session_state["product_report"] = report
        st.session_state["product_trust_report"] = trust_report
        st.rerun()


# ──────────────────────────────────────────────────────────────
# 页面：截图识别分析
# ──────────────────────────────────────────────────────────────

def page_screenshot():
    """截图分析页面"""
    render_page_header(t("截图识别分析", "Screenshot analysis"), t("上传评论页面截图，通过 OCR 与模型识别评论并生成分析报告。", "Upload review screenshots to extract feedback with OCR and generate an analysis report."))

    uploaded_files = st.file_uploader(
        t("上传网页截图（支持多张）", "Upload screenshots (multiple files supported)"),
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.success(t(f"已上传 {len(uploaded_files)} 张截图", f"Uploaded {len(uploaded_files)} screenshots"))
        for f in uploaded_files:
            st.text(f"{f.name} ({f.size/1024:.0f} KB)")

    col1, col2 = st.columns(2)
    with col1:
        platform = st.selectbox(
            t("评论来源平台", "Review platform"),
            ["taobao", "jd"],
            format_func=lambda x: {"taobao": t("淘宝/天猫", "Taobao / Tmall"), "jd": t("京东", "JD")}.get(x, x),
        )
    with col2:
        product_url = st.text_input(t("商品链接（可选，用于溯源）", "Product link (optional, for traceability)"), placeholder="https://item.taobao.com/item.htm?id=xxx")

    if st.button(t("识别截图评论", "Extract reviews"), type="primary", disabled=not uploaded_files):
        from screenshot_analyzer import create_screenshot_analyzer
        with st.spinner(t("正在初始化视觉识别引擎...", "Initializing visual analysis...")):
            analyzer = create_screenshot_analyzer()

        if analyzer is None:
            st.error(t("视觉分析引擎初始化失败，请检查 API Key 配置", "Visual analysis failed to initialize. Check the API key configuration."))
            return

        image_list = [f.getvalue() for f in uploaded_files]
        progress = st.progress(0, text=t("准备分析...", "Preparing analysis..."))
        all_reviews, all_errors = [], []

        for i, img_bytes in enumerate(image_list):
            progress.progress(i / len(image_list), text=t(f"正在分析第 {i+1}/{len(image_list)} 张截图...", f"Analyzing screenshot {i+1} of {len(image_list)}..."))
            reviews, err = analyzer.analyze_screenshot(img_bytes, platform=platform, product_url=product_url, product_name="")
            if err:
                all_errors.append(f"截图 {i+1}: {err}")
            all_reviews.extend(reviews)

        progress.progress(1.0, text=t("分析完成", "Analysis complete"))

        seen, unique_reviews = set(), []
        for r in all_reviews:
            text = r.get("review_text", "")[:150].strip().lower()
            if text and text not in seen:
                seen.add(text)
                unique_reviews.append(r)

        if all_errors:
            st.warning(t("部分截图分析失败：", "Some screenshots failed: ") + "; ".join(all_errors))

        if unique_reviews:
            methods = {}
            for r in unique_reviews:
                m = r.get("extraction_method", "unknown")
                methods[m] = methods.get(m, 0) + 1
            st.success(t(f"提取到 {len(unique_reviews)} 条评论", f"Extracted {len(unique_reviews)} reviews"))
            st.table(pd.DataFrame(unique_reviews)[["review_text", "rating"]].head(10).style.hide(axis="index"))
            st.session_state["screenshot_reviews"] = unique_reviews
        else:
            st.error(t("未能从截图中提取评论，请检查截图内容", "No reviews were extracted. Check the screenshot content."))
            return

    if st.session_state.get("screenshot_reviews"):
        st.divider()
        if st.button(t("生成深度分析报告", "Generate analysis report"), type="primary"):
            reviews = st.session_state["screenshot_reviews"]
            agent, err = get_agent()
            if err:
                st.error(t(f"分析服务初始化失败: {err}", f"Analysis service failed to initialize: {err}"))
                return

            with st.spinner(t(f"正在分析 {len(reviews)} 条评论...", f"Analyzing {len(reviews)} reviews...")):
                progress = st.progress(0)
                results, _auth_failed = _run_concurrent_analysis(agent, reviews, progress)

            report = agent.generate_report(results, product_name=reviews[0].get("product_name", "截图分析"))
            try:
                trust_report = TrustReportEngine().generate_report(reviews, results)
            except Exception:
                trust_report = {}
            # Save to history
            try:
                save_history_record(
                    source="screenshot", platform=platform, url=product_url or "",
                    product_name=reviews[0].get("product_name", "截图分析") if reviews else "截图分析",
                    reviews=reviews, results=results, report=report, trust_report=trust_report,
                )
            except Exception:
                pass
            display_results(reviews, results, report, trust_report)


# ──────────────────────────────────────────────────────────────
# 页面：CSV 批量分析
# ──────────────────────────────────────────────────────────────

def page_csv_upload():
    """CSV上传分析页面"""
    render_page_header(t("批量 CSV 分析", "Batch CSV analysis"), t("上传 CSV 文件进行批量分析，支持 review_text、rating 和 platform 字段。", "Upload a CSV for batch analysis using review_text, rating and platform fields."))

    uploaded = st.file_uploader(t("选择 CSV 文件", "Choose a CSV file"), type="csv")
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            st.success(t(f"已加载 {len(df)} 条评论", f"Loaded {len(df)} reviews"))
            st.table(df.head(5).style.hide(axis="index"))
        except Exception as e:
            st.error(t(f"读取失败: {e}", f"Could not read file: {e}"))
            return

    if uploaded is not None and st.button(t("开始批量分析", "Start batch analysis"), type="primary"):
        agent, err = get_agent()
        if err:
            st.error(t(f"分析服务初始化失败: {err}", f"Analysis service failed to initialize: {err}"))
            return

        reviews = df.to_dict("records")
        with st.spinner(t(f"正在分析 {len(reviews)} 条评论...", f"Analyzing {len(reviews)} reviews...")):
            progress = st.progress(0)
            results = []
            for i, review in enumerate(reviews):
                try:
                    result = agent.comprehensive_analysis(
                        review_text=str(review.get("review_text", "")),
                        rating=int(review.get("rating", 3)),
                        platform=str(review.get("platform", "未知")),
                    )
                    results.append(result)
                except Exception as e:
                    st.warning(t(f"第 {i+1} 条失败: {str(e)[:100]}", f"Review {i+1} failed: {str(e)[:100]}"))
                progress.progress((i + 1) / len(reviews))

        report = agent.generate_report(results)
        try:
            trust_report = TrustReportEngine().generate_report(reviews, results)
        except Exception:
            trust_report = {}
        # Save to history
        try:
            _csv_plat = str(reviews[0].get("platform", "unknown")) if reviews else "unknown"
            save_history_record(
                source="csv", platform=_csv_plat, url="",
                product_name="CSV批量分析",
                reviews=reviews, results=results, report=report, trust_report=trust_report,
            )
        except Exception:
            pass
        display_results(reviews, results, report, trust_report)


# ──────────────────────────────────────────────────────────────
# 结果展示
# ──────────────────────────────────────────────────────────────

def display_results(reviews, results, report, trust_report):
    """显示分析结果"""
    st.divider()
    render_page_header(t("分析结果", "Analysis results"), t(f"共分析 {len(results)} 条评论", f"{len(results)} reviews analyzed"))

    total = len(results)
    sarcastic = sum(1 for r in results if r.get("sentiment_analysis", {}).get("is_sarcastic"))
    suspicious = sum(1 for r in results if r.get("final_analysis", {}).get("final_validity") in ("suspicious", "fake"))
    avg_trust = sum(r.get("final_analysis", {}).get("trust_score", 50) for r in results) / total if total else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card_html(total, t("总评论数", "Reviews")), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card_html(sarcastic, t("反讽评论", "Sarcastic")), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card_html(suspicious, t("可疑评论", "Suspicious")), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card_html(f"{avg_trust:.1f}", t("平均可信度", "Average trust")), unsafe_allow_html=True)

    st.markdown(f'<div class="rp-section-title">{t("产品口碑报告", "Product reputation report")}</div>', unsafe_allow_html=True)
    st.code(json.dumps(report, ensure_ascii=False, indent=2), language="json")

    if trust_report:
        st.markdown(f'<div class="rp-section-title">{t("可信度报告与统计异常", "Trust report and statistical anomalies")}</div>', unsafe_allow_html=True)
        st.code(json.dumps(trust_report, ensure_ascii=False, indent=2), language="json")

    st.markdown(f'<div class="rp-section-title">{t("评论溯源信息", "Review sources")}</div>', unsafe_allow_html=True)
    trace_data = []
    for i, r in enumerate(reviews):
        trace_data.append({
            "#": i + 1,
            t("平台", "Platform"): r.get("source_platform", r.get("platform", t("未知", "Unknown"))),
            t("商品ID", "Product ID"): r.get("product_id", ""),
            t("评论者", "Reviewer"): r.get("reviewer_name", ""),
            t("日期", "Date"): r.get("review_date", ""),
            t("提取方式", "Method"): r.get("extraction_method", ""),
        })
    if trace_data:
        st.table(pd.DataFrame(trace_data).style.hide(axis="index"))
        st.caption(t("每条评论均可溯源到原始平台", "Every review is traceable to its source platform"))

    st.markdown(f'<div class="rp-section-title">{t("逐条评论分析", "Review-level analysis")}</div>', unsafe_allow_html=True)
    table_data = []
    for i, r in enumerate(results):
        final = r.get("final_analysis", {})
        sa = r.get("sentiment_analysis", {})
        va = r.get("validity_analysis", {})
        table_data.append({
            "#": i + 1,
            t("评论摘要", "Review"): r.get("review_text", "")[:50] + "...",
            t("评分", "Rating"): r.get("rating", "-"),
            t("情绪", "Sentiment"): sa.get("sentiment_label", "N/A"),
            t("反讽", "Sarcasm"): t("是", "Yes") if sa.get("is_sarcastic") else t("否", "No"),
            t("有效性", "Validity"): va.get("validity_label", "N/A"),
            t("可信度", "Trust"): final.get("trust_score", "N/A"),
            t("风险", "Risk"): final.get("risk_level", "N/A"),
        })
    st.table(pd.DataFrame(table_data).style.hide(axis="index"))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            t("下载 JSON", "Download JSON"),
            data=json.dumps({"report": report, "results": results, "trust_report": trust_report}, ensure_ascii=False, indent=2),
            file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )
    with col2:
        try:
            from utils.helpers import export_to_csv
            csv_path = os.path.join(tempfile.gettempdir(), f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            export_to_csv(results, csv_path)
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                st.download_button(t("下载 CSV", "Download CSV"), data=f.read(), file_name=os.path.basename(csv_path), mime="text/csv", use_container_width=True)
        except Exception:
            pass
    with col3:
        if st.button(t("生成 HTML 报告", "Generate HTML report"), use_container_width=True):
            try:
                from report_generator import HTMLReportGenerator
                gen = HTMLReportGenerator()
                html_path = gen.generate(results=results, report=report,
                    product_name=reviews[0].get("product_name", "产品") if reviews else "产品")
                st.success(t(f"报告已生成: {html_path}", f"Report generated: {html_path}"))
                webbrowser.open(f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}")
                with open(html_path, "r", encoding="utf-8") as f:
                    st.download_button(t("下载 HTML 报告", "Download HTML report"), data=f.read(), file_name=os.path.basename(html_path), mime="text/html")
            except Exception as e:
                st.error(t(f"生成失败: {e}", f"Report generation failed: {e}"))


# ──────────────────────────────────────────────────────────────
# 页面：可信度评分细则
# ──────────────────────────────────────────────────────────────

def page_trust_guide():
    """Render the trust methodology inside the current app window."""
    render_page_header(
        t("可信度评分细则", "Trust score guide"),
        t("了解单条评论与整体商品口碑如何形成可信度评分。", "See how review-level and product-level trust scores are calculated."),
    )
    if st.button(t("返回首页", "Back to overview"), key="trust_back"):
        st.session_state["current_page"] = "dashboard"
        st.rerun()

    st.markdown(f"""
    <div class="rp-guide-overview">
        <div><span>01</span><strong>{t("语义分析", "Semantic analysis")}</strong><small>{t("情绪、反讽和评分一致性", "Sentiment, sarcasm and rating alignment")}</small></div>
        <div><span>02</span><strong>{t("有效性检测", "Validity checks")}</strong><small>{t("模板、复制、偏题和异常行为", "Templates, duplication, drift and anomalies")}</small></div>
        <div><span>03</span><strong>{t("交叉验证", "Cross validation")}</strong><small>{t("生成单条评论可信度", "Produces review-level trust")}</small></div>
        <div><span>04</span><strong>{t("统计聚合", "Statistical aggregation")}</strong><small>{t("形成整体商品可信度", "Produces product-level trust")}</small></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f'<div class="rp-section-title">{t("评分区间", "Score bands")}</div>', unsafe_allow_html=True)
    score_rows = [
        {t("分数", "Score"): "80–100", t("等级", "Level"): t("低风险", "Low risk"), t("判断", "Meaning"): t("内容具体，情绪与评分一致，可信度较高", "Specific content with aligned sentiment and rating")},
        {t("分数", "Score"): "60–79", t("等级", "Level"): t("中低风险", "Moderate-low"), t("判断", "Meaning"): t("大体可信，但存在少量矛盾或信息不足", "Mostly credible with minor conflicts or limited detail")},
        {t("分数", "Score"): "30–59", t("等级", "Level"): t("中风险", "Moderate risk"), t("判断", "Meaning"): t("包含反讽、明显矛盾或模板特征", "Sarcasm, clear conflicts or template patterns")},
        {t("分数", "Score"): "0–29", t("等级", "Level"): t("高风险", "High risk"), t("判断", "Meaning"): t("高度模板化、批量复制或疑似生成内容", "Strong templating, duplication or generated content")},
    ]
    st.table(pd.DataFrame(score_rows).style.hide(axis="index"))

    left, right = st.columns(2)
    with left:
        st.markdown(f"""
        <div class="rp-guide-panel rp-guide-orange"><span class="rp-guide-kicker">REVIEW LEVEL</span>
        <h3>{t("单条评论评分", "Review-level score")}</h3>
        <p>{t("模型先分析情绪与反讽，再判断评论是否真实有效，最后交叉验证评分、文本和产品语境。", "The model evaluates sentiment and sarcasm, checks validity, then cross-validates rating, text and product context.")}</p>
        <div class="rp-guide-formula">{t("情绪识别 + 有效性检测 + 交叉验证 = 单条可信度", "Sentiment + validity + cross validation = review trust")}</div></div>
        """, unsafe_allow_html=True)
    with right:
        st.markdown(f"""
        <div class="rp-guide-panel rp-guide-blue"><span class="rp-guide-kicker">PRODUCT LEVEL</span>
        <h3>{t("整体商品评分", "Product-level score")}</h3>
        <p>{t("系统从 100 分开始，根据时间突发、重复评论、极端评分、长度均匀、短语重复和评分矛盾进行扣分。", "The system starts at 100 and applies deductions for bursts, duplicates, extreme ratings, uniform length, repeated phrases and rating conflicts.")}</p>
        <div class="rp-guide-formula">100 − {t("六类统计异常扣分", "six statistical anomaly deductions")}</div></div>
        """, unsafe_allow_html=True)

    st.markdown(f'<div class="rp-section-title">{t("六个统计检测维度", "Six statistical checks")}</div>', unsafe_allow_html=True)
    dimensions = [
        (t("时间突发", "Time bursts"), t("单日评论量显著高于平均值", "Daily volume materially exceeds the average"), "−15"),
        (t("重复评论", "Duplicate groups"), t("TF-IDF 与余弦相似度识别批量复制", "TF-IDF and cosine similarity detect copying"), "−25"),
        (t("评分异常", "Rating anomaly"), t("单一极端评分占比过高", "One extreme rating dominates the distribution"), "−15"),
        (t("长度均匀", "Uniform length"), t("评论长度过度一致，呈现模板特征", "Review lengths are unusually consistent"), "−15"),
        (t("短语重复", "Phrase repetition"), t("四词短语在多条评论中重复", "Four-word phrases repeat across reviews"), "−20"),
        (t("评分矛盾", "Rating conflict"), t("星级与文本情绪明显不一致", "Star ratings conflict with written sentiment"), "−20"),
    ]
    guide_tones = ["orange", "blue", "green", "purple", "red", "amber"]
    for start in range(0, len(dimensions), 3):
        cols = st.columns(3)
        for offset, (col, (name, desc, penalty)) in enumerate(zip(cols, dimensions[start:start + 3])):
            with col:
                tone = guide_tones[start + offset]
                st.markdown(f'<div class="rp-guide-check rp-guide-{tone}"><strong>{name}</strong><p>{desc}</p><span>{penalty}</span></div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 页面：历史记录
# ──────────────────────────────────────────────────────────────

def page_history():
    """历史记录页面"""
    render_page_header(t("历史记录", "History"), t("查看历史分析记录，并重新打开或导出报告。", "Review past analyses and reopen or export reports."))

    records = _display_history()

    # Top action bar
    col_info, col_clear = st.columns([3, 1])
    with col_info:
        if records:
            st.caption(t(f"共 {len(records)} 条历史记录", f"{len(records)} records"))
        else:
            st.caption(t("暂无历史记录", "No history yet"))
    with col_clear:
        if records and st.button(t("清除历史记录", "Clear history"), type="secondary", use_container_width=True):
            st.session_state["_history_confirm_clear"] = True

    if st.session_state.get("_history_confirm_clear"):
        st.warning(t("确定要清除所有历史记录吗？此操作不可恢复。", "Clear all history? This action cannot be undone."))
        c1, c2 = st.columns(2)
        with c1:
            if st.button(t("确认清除", "Clear all"), type="primary", use_container_width=True):
                n = clear_all_history()
                st.session_state["_demo_hidden"] = True
                st.session_state["_history_confirm_clear"] = False
                st.success(t(f"已清除 {n} 条历史记录和示例", f"Cleared {n} records and the demo"))
                st.rerun()
        with c2:
            if st.button(t("取消", "Cancel"), use_container_width=True):
                st.session_state["_history_confirm_clear"] = False
                st.rerun()

    if not records:
        st.info(t("还没有分析记录，请先完成一次链接分析或截图分析。", "No analyses yet. Start with a product link or screenshot."))
        return

    platform_icons = {"jd": t("京东", "JD"), "taobao": t("淘宝", "Taobao"), "tmall": t("天猫", "Tmall"), "unknown": t("未知", "Unknown")}
    source_labels = {
        "product_url": t("产品链接", "Product link"),
        "screenshot": t("截图分析", "Screenshot"), "csv": t("CSV 批量", "CSV batch"),
    }

    for rec in records:
        plat = rec.get("platform", "unknown")
        plat_label = platform_icons.get(plat, plat)
        src_label = source_labels.get(rec.get("source", ""), t("分析", "Analysis"))
        trust = rec.get("avg_trust_score", 0)
        pname = rec.get("product_name", "未命名产品")[:60]
        if rec.get("is_demo"):
            pname = f"{t('示例', 'Demo')} · {pname}"

        with st.expander(
            f"{plat_label}  |  {src_label}  |  {pname}  |  "
            f"{rec.get('review_count', 0)} {t('条', 'reviews')}  |  {t('可信度', 'Trust')} {trust}  |  "
            f"{rec.get('timestamp_display', '')}",
            expanded=False,
        ):
            # Stats row
            mc1, mc2, mc3, mc4, mc5 = st.columns(5)
            with mc1:
                st.metric(t("评论数", "Reviews"), rec.get("review_count", 0))
            with mc2:
                st.metric(t("平均可信度", "Average trust"), f"{trust}")
            with mc3:
                st.metric(t("反讽评论", "Sarcastic"), rec.get("sarcastic_count", 0))
            with mc4:
                st.metric(t("可疑评论", "Suspicious"), rec.get("suspicious_count", 0))
            dist = rec.get("sentiment_distribution", {})
            with mc5:
                pos = dist.get("positive", dist.get("正面", 0))
                neg = dist.get("negative", dist.get("负面", 0))
                st.metric(t("正面 / 负面", "Positive / negative"), f"{pos}/{neg}")

            if rec.get("url"):
                st.caption(rec["url"])

            # Report data
            if rec.get("report"):
                st.markdown(f'<div class="rp-section-title">{t("口碑报告", "Reputation report")}</div>', unsafe_allow_html=True)
                st.code(json.dumps(rec["report"], ensure_ascii=False, indent=2), language="json")

            if rec.get("trust_report"):
                st.markdown(f'<div class="rp-section-title">{t("可信度报告", "Trust report")}</div>', unsafe_allow_html=True)
                st.code(json.dumps(rec["trust_report"], ensure_ascii=False, indent=2), language="json")

            if rec.get("results"):
                st.markdown(f'<div class="rp-section-title">{t("逐条分析", "Review-level analysis")}</div>', unsafe_allow_html=True)
                table_data = []
                for i, r in enumerate(rec["results"]):
                    final = r.get("final_analysis", {})
                    sa = r.get("sentiment_analysis", {})
                    va = r.get("validity_analysis", {})
                    table_data.append({
                        "#": i + 1,
                        t("评论摘要", "Review"): r.get("review_text", "")[:60] + "..." if len(r.get("review_text", "")) > 60 else r.get("review_text", ""),
                        t("评分", "Rating"): r.get("rating", "-"),
                        t("情绪", "Sentiment"): sa.get("sentiment_label", "N/A"),
                        t("反讽", "Sarcasm"): t("是", "Yes") if sa.get("is_sarcastic") else t("否", "No"),
                        t("有效性", "Validity"): va.get("validity_label", "N/A"),
                        t("可信度", "Trust"): final.get("trust_score", "N/A"),
                        t("风险", "Risk"): final.get("risk_level", "N/A"),
                    })
                st.table(pd.DataFrame(table_data).style.hide(axis="index"))

            # Action buttons
            ac1, ac2, ac3, ac4 = st.columns(4)
            with ac1:
                st.download_button(
                    t("下载 JSON", "Download JSON"),
                    data=json.dumps(
                        {"report": rec.get("report", {}), "results": rec.get("results", []),
                         "trust_report": rec.get("trust_report", {})},
                        ensure_ascii=False, indent=2,
                    ),
                    file_name=f"history_{rec['id']}.json",
                    mime="application/json",
                    use_container_width=True,
                    key=f"dl_json_{rec['id']}",
                )
            html_path = rec.get("html_report_path")
            with ac2:
                if html_path and os.path.exists(html_path):
                    if st.button(t("查看 HTML 报告", "View HTML report"), use_container_width=True, key=f"view_html_{rec['id']}"):
                        st.session_state["_history_report_id"] = rec["id"]
                        st.rerun()
                else:
                    st.button(t("查看报告", "View report"), disabled=True, use_container_width=True, key=f"no_view_{rec['id']}")
            with ac3:
                if html_path and os.path.exists(html_path):
                    with open(html_path, "r", encoding="utf-8") as f:
                        st.download_button(
                            t("下载 HTML 报告", "Download HTML report"),
                            data=f.read(),
                            file_name=f"report_{rec['id']}.html",
                            mime="text/html",
                            use_container_width=True,
                            key=f"dl_html_{rec['id']}",
                        )
                else:
                    st.button(t("HTML 报告不可用", "HTML report unavailable"), disabled=True, use_container_width=True, key=f"no_html_{rec['id']}")
            with ac4:
                if st.button(t("删除此记录", "Delete record"), use_container_width=True, key=f"del_{rec['id']}"):
                    if rec.get("is_demo"):
                        st.session_state["_demo_hidden"] = True
                    else:
                        delete_record(rec["id"])
                    st.rerun()

            if st.session_state.get("_history_report_id") == rec["id"] and html_path and os.path.exists(html_path):
                close_col, _ = st.columns([1, 3])
                with close_col:
                    if st.button(t("关闭报告", "Close report"), key=f"close_html_{rec['id']}", use_container_width=True):
                        st.session_state["_history_report_id"] = None
                        st.rerun()
                with open(html_path, "r", encoding="utf-8") as f:
                    report_html = f.read()
                import streamlit.components.v1 as components
                components.html(report_html, height=880, scrolling=True)


# ──────────────────────────────────────────────────────────────
# 侧边栏导航
# ──────────────────────────────────────────────────────────────

NAV_ITEMS = [
    ("首页", "Overview", "dashboard"),
    ("链接采集分析", "Link analysis", "product_url"),
    ("截图识别分析", "Screenshot analysis", "screenshot"),
    ("批量 CSV 分析", "Batch CSV", "csv"),
    ("历史记录", "History", "history"),
    ("可信度评分细则", "Trust score guide", "trust_guide"),
]

NAV_ICONS = {
    "dashboard": ":material/home:",
    "product_url": ":material/link:",
    "screenshot": ":material/image_search:",
    "csv": ":material/table_view:",
    "history": ":material/history:",
    "trust_guide": ":material/verified_user:",
}


def render_sidebar():
    """Render navigation, language control and utilities."""
    with st.sidebar:
        st.markdown("""
        <div class="rp-sidebar-brand">
            <div class="rp-sidebar-logo">RP</div>
            <div>
                <div class="rp-sidebar-name">ReviewPilot</div>
                <div class="rp-sidebar-version">Review intelligence</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        current = st.session_state.get("current_page", "dashboard")
        st.markdown('<div class="rp-nav-label">WORKSPACE</div>', unsafe_allow_html=True)
        for zh, en, key in NAV_ITEMS[:4]:
            btn_type = "primary" if current == key else "secondary"
            if st.button(t(zh, en), key=f"nav_{key}",
                         use_container_width=True, type=btn_type, icon=NAV_ICONS[key]):
                st.session_state["current_page"] = key
                st.rerun()

        st.markdown('<div class="rp-nav-label rp-nav-label-data">DATA</div>', unsafe_allow_html=True)
        for zh, en, key in NAV_ITEMS[4:]:
            btn_type = "primary" if current == key else "secondary"
            if st.button(t(zh, en), key=f"nav_{key}",
                         use_container_width=True, type=btn_type, icon=NAV_ICONS[key]):
                st.session_state["current_page"] = key
                st.rerun()

        with st.container(key="sidebar_footer"):
            st.markdown('<div class="rp-sidebar-divider"></div>', unsafe_allow_html=True)
            st.markdown("""
            <div class="rp-sidebar-version-row">
                <span>ReviewPilot v5.0.0</span>
            </div>
            """, unsafe_allow_html=True)


def render_language_switcher():
    """Render the existing language control in the top-right utility area."""
    picker_state = st.session_state.get("_language_picker", "中文")
    if picker_state == "English":
        picker_state = "EN"
        st.session_state["_language_picker"] = "EN"
    with st.container(key="language_switcher"):
        selected_language = st.segmented_control(
            "Language / 语言", ["中文", "EN"],
            default="EN" if picker_state == "EN" else "中文",
            key="_language_picker",
            label_visibility="collapsed",
        )
    st.session_state["language"] = "en" if selected_language == "EN" else "zh"


# ──────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────

def main():
    apply_styles()
    render_language_switcher()
    render_sidebar()
    render_ethics_banner()

    page = st.session_state.get("current_page", "dashboard")

    if page == "dashboard":
        render_dashboard()
    elif page == "product_url":
        page_product_url()
    elif page == "screenshot":
        page_screenshot()
    elif page == "csv":
        page_csv_upload()
    elif page == "history":
        page_history()
    elif page == "trust_guide":
        page_trust_guide()


if __name__ == "__main__":
    main()
