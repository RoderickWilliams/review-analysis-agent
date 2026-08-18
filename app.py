"""
Streamlit Web UI — ReviewPilot 智能评论分析 Agent
=====================================================
浅色 SaaS 设计系统：侧边栏导航 + Hero 仪表盘 + 卡片化布局
"""

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
    clear_all_history, get_cache_size, clear_cache,
)
from trust_report import TrustReportEngine

st.set_page_config(
    page_title="ReviewPilot - 智能评论分析 Agent",
    page_icon="🔍",
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
    from _ui_styles import get_styles
    st.markdown(get_styles("light"), unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# UI 辅助组件
# ──────────────────────────────────────────────────────────────

def metric_card_html(value, label, icon="", bg_color="#EDE9FE", icon_color="#6366F1"):
    return f"""
    <div class="rp-metric">
        <div class="rp-metric-icon" style="background:{bg_color};color:{icon_color}">{icon}</div>
        <div class="rp-metric-value">{value}</div>
        <div class="rp-metric-label">{label}</div>
    </div>
    """


def render_page_header(title, subtitle):
    st.markdown(f'<div class="rp-page-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="rp-page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def render_ethics_banner():
    st.markdown("""
    <div class="rp-ethics">
        <strong>🛡️ 伦理准则：</strong>AI无法自主生成虚假评论并进行虚假分析；每条用于分析的评论都有可追溯的来源。
    </div>
    """, unsafe_allow_html=True)


def trust_color(score):
    if score >= 70:
        return "#10B981"
    elif score >= 40:
        return "#F59E0B"
    return "#EF4444"


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

# ──────────────────────────────────────────────────────────────
# 仪表盘
# ──────────────────────────────────────────────────────────────

def render_dashboard():
    """首页仪表盘：Hero 横幅 + 指标卡片 + 环形图 + 最近分析"""
    st.markdown("""
    <div class="rp-hero">
        <div>
            <h1>欢迎使用 ReviewPilot 👋</h1>
            <p>AI 驱动的跨平台评论分析 Agent，支持淘宝/京东评论采集、OCR 截图识别与 CSV 批量分析，
            自动完成情绪识别、反讽检测、可信度评估与口碑报告生成。</p>
        </div>
        <div class="rp-hero-logo">🔍</div>
    </div>
    """, unsafe_allow_html=True)

    try:
        records = load_history()
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
        st.markdown(metric_card_html(total_analyses, "分析任务数", "📊", "#EDE9FE", "#6366F1"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card_html(total_reviews, "累计评论数", "💬", "#DBEAFE", "#3B82F6"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card_html(f"{avg_trust:.1f}", "平均可信度", "🛡️", "#D1FAE5", "#10B981"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card_html(total_sarcastic, "反讽评论", "😏", "#FEF3C7", "#F59E0B"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card_html(total_suspicious, "可疑评论", "🚨", "#FEE2E2", "#EF4444"), unsafe_allow_html=True)

    # 用 components.html 渲染整个仪表板区域，确保 JavaScript 在同一 iframe 内可执行
    import streamlit.components.v1 as components

    # 构建左侧饼图 HTML
    if sentiment_total > 0:
        pos_pct = pos_total / sentiment_total * 100
        neu_pct = neu_total / sentiment_total * 100
        neg_pct = neg_total / sentiment_total * 100
        default_chart = f"""
        <div class="rp-donut-wrap" id="chart-default">
            <div class="rp-donut" style="background: conic-gradient(#10B981 0% {pos_pct}%, #F59E0B {pos_pct}% {pos_pct + neu_pct}%, #EF4444 {pos_pct + neu_pct}% 100%);">
                <div class="rp-donut-hole"><div class="rp-donut-value">{sentiment_total}</div><div class="rp-donut-label">总评论</div></div>
            </div>
            <div class="rp-legend">
                <div class="rp-legend-item"><span class="rp-legend-dot" style="background:#10B981"></span><span>正面</span><span class="rp-legend-pct">{pos_pct:.1f}% ({pos_total})</span></div>
                <div class="rp-legend-item"><span class="rp-legend-dot" style="background:#F59E0B"></span><span>中性</span><span class="rp-legend-pct">{neu_pct:.1f}% ({neu_total})</span></div>
                <div class="rp-legend-item"><span class="rp-legend-dot" style="background:#EF4444"></span><span>负面</span><span class="rp-legend-pct">{neg_pct:.1f}% ({neg_total})</span></div>
            </div>
        </div>"""
    else:
        default_chart = '<div style="text-align:center;padding:40px 0;color:#9CA3AF;" id="chart-default">暂无分析数据</div>'

    # 情绪标签映射
    POSITIVE_KEYS = {"positive", "正面", "真诚好评", "好评", "满意"}
    NEUTRAL_KEYS = {"neutral", "中性", "一般", "普通"}
    NEGATIVE_KEYS = {"negative", "负面", "差评", "不满", "抱怨"}
    SARCASTIC_KEYS = {"sarcasm", "反讽", "反讽/阴阳怪气", "阴阳怪气"}

    hover_charts_html = ""
    recent_items_html = ""
    report_data_html = ""
    source_meta = {
        "single": ("💬", "#EDE9FE", "#6366F1"),
        "product_url": ("🔗", "#DBEAFE", "#3B82F6"),
        "screenshot": ("🖼️", "#FEF3C7", "#F59E0B"),
        "csv": ("📁", "#D1FAE5", "#10B981"),
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
            stops = [f"#10B981 0% {pos_p:.1f}%"]
            cumulative = pos_p
            if neu_p > 0:
                stops.append(f"#F59E0B {cumulative:.1f}% {cumulative + neu_p:.1f}%")
                cumulative += neu_p
            if sar_p > 0:
                stops.append(f"#8B5CF6 {cumulative:.1f}% {cumulative + sar_p:.1f}%")
                cumulative += sar_p
            if neg_p > 0:
                stops.append(f"#EF4444 {cumulative:.1f}% {cumulative + neg_p:.1f}%")
                cumulative += neg_p
            if other_count > 0:
                stops.append(f"#6B7280 {cumulative:.1f}% 100%")
            else:
                stops.append(f"#EF4444 {cumulative:.1f}% 100%")
            grad_stops = ", ".join(stops)
            chart_name = display_name[:18]

            legend_items = ""
            if pos_r > 0:
                legend_items += f'<div class="rp-legend-item"><span class="rp-legend-dot" style="background:#10B981"></span><span>正面</span><span class="rp-legend-pct">{pos_p:.0f}% ({pos_r})</span></div>'
            if neu_r > 0:
                legend_items += f'<div class="rp-legend-item"><span class="rp-legend-dot" style="background:#F59E0B"></span><span>中性</span><span class="rp-legend-pct">{neu_p:.0f}% ({neu_r})</span></div>'
            if sar_r > 0:
                legend_items += f'<div class="rp-legend-item"><span class="rp-legend-dot" style="background:#8B5CF6"></span><span>反讽</span><span class="rp-legend-pct">{sar_p:.0f}% ({sar_r})</span></div>'
            if neg_r > 0:
                legend_items += f'<div class="rp-legend-item"><span class="rp-legend-dot" style="background:#EF4444"></span><span>负面</span><span class="rp-legend-pct">{neg_p:.0f}% ({neg_r})</span></div>'

            hover_charts_html += f'<div class="rp-donut-wrap rp-hover-chart" id="chart-{rec_id}" style="display:none;"><div class="rp-donut" style="background: conic-gradient({grad_stops});"><div class="rp-donut-hole"><div class="rp-donut-value">{rec_total}</div><div class="rp-donut-label">{chart_name}</div></div></div><div class="rp-legend">{legend_items}</div></div>'

        # 右侧历史记录条目
        src = rec.get("source", "")
        icon, bg, fg = source_meta.get(src, ("📊", "#E5E7EB", "#6B7280"))
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
            name_html = f'<a href="{safe_url}" target="_blank" class="rp-rec-name" onclick="event.stopPropagation()" title="点击打开原网页">{display_name}</a>'
        else:
            name_html = f'<span class="rp-rec-name rp-rec-name-nolink">{display_name}</span>'

        # 分数区域（绿框）：左键查看报告，右键固定饼图
        if report_b64:
            score_onclick = f"rpOpenReport('{rec_id}', event)"
            score_title = "左键：查看HTML报告 | 右键：固定饼图"
        else:
            score_onclick = "event.stopPropagation()"
            score_title = "右键：固定饼图"

        item_display = "" if page_num == 1 else "none"
        recent_items_html += f"""<div class="rp-recent-item" data-rec-id="{rec_id}" data-page="{page_num}" style="display:{item_display};" onmouseover="rpHoverChart('{rec_id}')" onmouseout="rpHoverDefault()"><div class="rp-rec-icon" style="background:{bg};color:{fg};">{icon}</div><div class="rp-rec-info">{name_html}<div class="rp-rec-meta">{review_count} 条 · {ts_disp}</div></div><div class="rp-rec-score" onclick="{score_onclick}" oncontextmenu="rpPinChart('{rec_id}', event)" title="{score_title}"><div class="rp-rec-score-val" style="color:{tcolor};">{tscore}</div><div class="rp-rec-score-label">可信度</div></div></div>"""

    pager_html = f'<div class="rp-pager" id="rp-pager" data-total-pages="{total_pages}"><button class="rp-pager-btn" id="rp-prev" onclick="rpChangePage(-1)">‹ 上一页</button><span class="rp-pager-info" id="rp-page-info">1 / {total_pages}</span><button class="rp-pager-btn" id="rp-next" onclick="rpChangePage(1)">下一页 ›</button></div>' if total_recs > PER_PAGE else ''

    tips_html = '<div class="rp-tips"><span class="rp-tips-title">💡 操作提示</span><div class="rp-tips-item">· 点击 <b style="color:#3B82F6;">名称</b> → 打开原网页</div><div class="rp-tips-item">· 左键 <b style="color:#10B981;">分数</b> → 查看 HTML 报告</div><div class="rp-tips-item">· 右键 <b style="color:#10B981;">分数</b> → 固定饼图</div><div class="rp-tips-item">· 点击空白处 → 恢复默认</div></div>'

    dashboard_html = f"""
    <style>
    .rp-db-container {{ display:flex;gap:16px;width:100%;align-items:stretch; }}
    .rp-db-left {{ flex:0 0 65%;display:flex;align-items:stretch; }}
    .rp-db-right {{ flex:0 0 calc(35% - 16px);display:flex;align-items:stretch;min-width:0; }}
    .rp-db-card {{ background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.08);width:100%;height:100%;display:flex;flex-direction:column; }}
    .rp-db-title {{ font-size:14px;font-weight:700;color:#1F2937;margin-bottom:12px;display:flex;align-items:center;gap:6px; }}
    .rp-donut-wrap {{ display:flex;align-items:center;gap:24px;flex:1;justify-content:center; }}
    .rp-donut {{ width:200px;height:200px;border-radius:50%;flex-shrink:0; }}
    .rp-donut-hole {{ width:140px;height:140px;background:#FFFFFF;border-radius:50%;margin:30px auto;display:flex;flex-direction:column;align-items:center;justify-content:center; }}
    .rp-donut-value {{ font-size:32px;font-weight:800;color:#1F2937; }}
    .rp-donut-label {{ font-size:11px;color:#6B7280;max-width:110px;text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px; }}
    .rp-legend {{ display:flex;flex-direction:column;gap:8px; }}
    .rp-legend-item {{ display:flex;align-items:center;gap:8px;font-size:13px;color:#374151; }}
    .rp-legend-dot {{ width:12px;height:12px;border-radius:50%;flex-shrink:0; }}
    .rp-legend-pct {{ margin-left:auto;color:#6B7280;font-size:12px; }}
    .rp-recent-list {{ flex:1;overflow-y:auto; }}
    .rp-recent-item {{ padding:8px 6px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #f0f0f0;border-radius:8px;transition:background .15s; }}
    .rp-recent-item:hover {{ background:#F3F4F6; }}
    .rp-recent-item:last-child {{ border-bottom:none; }}
    .rp-recent-item.rp-pinned {{ background:#EDE9FE!important; border-color:#C4B5FD; }}
    .rp-rec-icon {{ width:28px;height:28px;font-size:12px;display:flex;align-items:center;justify-content:center;border-radius:6px;flex-shrink:0; }}
    .rp-rec-info {{ flex:1;min-width:0; }}
    .rp-rec-name {{ display:block;font-size:13px;font-weight:500;color:#3B82F6;text-decoration:none;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }}
    .rp-rec-name:hover {{ text-decoration:underline; }}
    .rp-rec-name-nolink {{ color:#1F2937;cursor:default; }}
    .rp-rec-name-nolink:hover {{ text-decoration:none; }}
    .rp-rec-meta {{ font-size:11px;color:#6B7280; }}
    .rp-rec-score {{ text-align:right;flex-shrink:0;cursor:pointer;padding:4px 8px;border-radius:6px;transition:background .15s; }}
    .rp-rec-score:hover {{ background:#F3F4F6; }}
    .rp-rec-score-val {{ font-size:15px;font-weight:700; }}
    .rp-rec-score-label {{ font-size:10px;color:#9CA3AF; }}
    .rp-tips {{ margin-top:8px;padding:8px 10px;background:#F8F9FC;border-radius:6px;font-size:11px;color:#6B7280;line-height:1.8;border:1px solid #E5E7EB; }}
    .rp-tips-title {{ font-weight:600;color:#374151;display:block;margin-bottom:2px; }}
    .rp-tips-item {{ padding-left:2px; }}
    .rp-pager {{ display:flex;align-items:center;justify-content:center;gap:8px;margin-top:8px; }}
    .rp-pager-btn {{ border:1px solid #E5E7EB;background:#FFFFFF;color:#374151;padding:4px 12px;border-radius:6px;font-size:12px;cursor:pointer;transition:all .15s; }}
    .rp-pager-btn:hover {{ background:#F3F4F6;border-color:#6366F1; }}
    .rp-pager-btn:disabled {{ opacity:0.4;cursor:not-allowed; }}
    .rp-pager-info {{ font-size:12px;color:#6B7280;min-width:60px;text-align:center; }}
    </style>
    <div class="rp-db-container">
        <div class="rp-db-left">
            <div class="rp-db-card">
                <div class="rp-db-title">📈 评论情绪分布</div>
                {default_chart}
                {hover_charts_html}
            </div>
        </div>
        <div class="rp-db-right">
            <div class="rp-db-card">
                <div class="rp-db-title">🕐 最近分析</div>
                <div class="rp-recent-list">
                {recent_items_html if recent_items_html else '<div style="text-align:center;padding:40px 0;color:#9CA3AF;">暂无历史记录</div>'}
                </div>
                {pager_html}
                {tips_html if recent_items_html else ''}
            </div>
        </div>
    </div>
    {report_data_html}
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
            alert('报告打开失败: ' + e.message);
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
    </script>
    """

    components.html(dashboard_html, height=460, scrolling=False)


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
            with st.spinner("正在启动浏览器采集淘宝评论..."):
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
        with st.spinner("正在重新提取淘宝评论..."):
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
        st.warning("🤖 浏览器未能自动提取到淘宝评论。请查看已打开的浏览器窗口：")
        st.info("👉 如果页面上**能看到评论**，请先滚动评论区/完成登录，然后点击「我已看到评论，重新提取」。\n\n"
                "👉 如果页面上**确实没有评论**（需要登录/被反爬/商品无评论），点击「继续降级」。")
        col_a, col_b = st.columns(2)
        if col_a.button("✅ 我已看到评论，重新提取", type="primary", key="btn_tb_pw_retry"):
            st.session_state[stage_key] = "pw_retry"
            st.rerun()
        if col_b.button("⏭️ 继续降级", key="btn_tb_pw_continue"):
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
            with st.spinner("正在启动真实 Chrome 采集京东评论..."):
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
                st.info(f"Chrome 采集到 {len(dp_reviews)} 条，不足预期 {max_reviews} 条，尝试 API 补充...")
                st.session_state[confirm_key] = "dp_supplement"
                st.rerun()
            else:
                st.session_state[confirm_key] = "dp_confirm"
                st.rerun()

        elif stage == "dp_reextract":
            with st.spinner("正在从浏览器重新提取评论..."):
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

            with st.spinner("正在通过 API 补充采集评论..."):
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
            st.warning("🤖 Chrome 浏览器未能自动提取到评论。请查看已打开的浏览器窗口：")
            st.info("👉 如果页面上**能看到评论**，请先滚动评论区确保内容加载完毕，然后点击「我已看到评论，重新提取」。\n\n"
                    "👉 如果页面上**确实没有评论**（需要登录/被反爬/商品无评论），点击「继续降级」尝试下一种方式。")
            col_a, col_b = st.columns(2)
            if col_a.button("✅ 我已看到评论，重新提取", type="primary", key="btn_dp_reextract"):
                st.session_state[confirm_key] = "dp_reextract"
                st.rerun()
            if col_b.button("⏭️ 继续降级到反检测浏览器", key="btn_dp_continue"):
                st.session_state[confirm_key] = "pw"
                st.rerun()
            for method, result in jd_scraper._method_results.items():
                icon = "✅" if "成功" in result else "⚠️"
                st.caption(f"{icon} {method}: {result}")
            st.stop()

        elif stage == "pw":
            with st.spinner("正在启动反检测浏览器采集..."):
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
            with st.spinner("正在从反检测浏览器重新提取..."):
                reviews = jd_scraper.reextract_last(url)
            if reviews:
                jd_scraper._method_results["playwright"] = "重新提取成功 %d 条" % len(reviews)
                jd_scraper._last_method = "playwright"
                st.session_state[confirm_key] = "done"
            else:
                st.session_state[confirm_key] = "api"
                st.rerun()

        elif stage == "pw_confirm":
            st.warning("🤖 反检测浏览器也未能自动提取到评论。请查看已打开的浏览器窗口：")
            st.info("👉 如果页面上**能看到评论**，请先滚动评论区确保内容加载完毕，然后点击「我已看到评论，重新提取」。\n\n"
                    "👉 如果页面上**确实没有评论**，点击「继续降级」尝试 API 直连。")
            col_a, col_b = st.columns(2)
            if col_a.button("✅ 我已看到评论，重新提取", type="primary", key="btn_pw_reextract"):
                st.session_state[confirm_key] = "pw_reextract"
                st.rerun()
            if col_b.button("⏭️ 继续降级到 API 直连", key="btn_pw_continue"):
                st.session_state[confirm_key] = "api"
                st.rerun()
            for method, result in jd_scraper._method_results.items():
                icon = "✅" if "成功" in result else "⚠️"
                st.caption(f"{icon} {method}: {result}")
            st.stop()

        elif stage == "api":
            with st.spinner("正在通过 API 直连采集..."):
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
                icon = "✅" if "成功" in result else "⚠️"
                st.caption(f"{icon} {method}: {result}")
            del st.session_state[confirm_key]

    except Exception as e:
        st.warning(f"统一抓取器异常: {e}")
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
                st.warning(f"第 {idx+1} 条分析失败: {err}")
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
    render_page_header("🔗 链接采集分析", "粘贴淘宝/京东产品链接，自动采集评论并进行深度分析")

    if st.session_state.get("product_reviews"):
        reviews = st.session_state["product_reviews"]
        results = st.session_state.get("product_results", [])
        report = st.session_state.get("product_report", {})
        trust_report = st.session_state.get("product_trust_report", {})

        st.success(f"✅ 已完成 {len(reviews)} 条评论的分析")

        if st.button("🔄 再次分析"):
            for key in ["product_reviews", "product_results", "product_report", "product_trust_report"]:
                st.session_state.pop(key, None)
            st.rerun()

        display_results(reviews, results, report, trust_report)
        return

    url = st.text_input(
        "产品链接",
        placeholder="https://item.jd.com/100012345.html 或 https://item.taobao.com/item.htm?id=xxx",
        label_visibility="collapsed",
    )
    col1, _ = st.columns(2)
    with col1:
        max_reviews = st.number_input("最大采集量（0=无上限）", 0, 100000, 100, help="设为0则持续采集直到没有更多评论")
        _max_reviews = max_reviews if max_reviews > 0 else 1000000

    if st.button("🚀 开始采集 + 分析", type="primary"):
        if not url.strip():
            st.warning("请输入产品链接")
            return

        reviews = []

        with st.spinner("正在采集评论..."):
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
                            st.info(f"📸 自动抓取未成功，已截取 {len(screenshots)} 张评论区截图，正在通过 OCR 识别...")
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
                                    st.success(f"✅ OCR 从截图中识别出 {len(reviews)} 条评论")
                            except Exception as e:
                                st.warning(f"OCR 识别失败: {e}")
                    if not reviews:
                        try:
                            reviews = scraper.scrape_product(url, max_reviews=_max_reviews)
                        except Exception:
                            reviews = []

                else:
                    reviews = scraper.scrape_product(url, max_reviews=_max_reviews)

            except Exception as e:
                st.error(f"采集失败: {e}")
                return

        if not reviews:
            st.warning("自动采集未获取到评论数据")
            st.info("💡 请尝试：1. 在侧边栏登录平台获取 Cookie  2. 切换到「截图分析」模式")
            return

        has_trace = all(r.get("source_platform") for r in reviews)
        if has_trace:
            st.success(f"✅ 采集到 {len(reviews)} 条评论（全部含溯源信息）")
        else:
            st.warning(f"⚠️ 采集到 {len(reviews)} 条评论，部分缺少溯源信息")

        df_preview = pd.DataFrame(reviews)
        display_cols = ["review_text", "rating", "platform"]
        for extra in ["source_platform", "extraction_method"]:
            if extra in df_preview.columns:
                display_cols.append(extra)
        st.table(df_preview[[c for c in display_cols if c in df_preview.columns]].head(10).style.hide(axis="index"))

        agent, err = get_agent()
        if err:
            st.error(f"Agent初始化失败: {err}")
            return

        with st.spinner(f"正在分析 {len(reviews)} 条评论（并发处理）..."):
            progress = st.progress(0)
            results, auth_failed = _run_concurrent_analysis(agent, reviews, progress)
            if auth_failed:
                st.error("API Key 认证失败！请检查 .env 配置。")
                st.stop()

        with st.spinner("正在生成口碑报告..."):
            report = agent.generate_report(results, product_name=reviews[0].get("product_name", "产品"))

        with st.spinner("正在生成 Trust Report..."):
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
    render_page_header("🖼️ 截图识别分析", "上传商品评论页面截图，OCR + LLM 自动识别评论并生成深度分析报告")

    uploaded_files = st.file_uploader(
        "上传网页截图（支持多张）",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.success(f"✅ 已上传 {len(uploaded_files)} 张截图")
        for f in uploaded_files:
            st.text(f"  📎 {f.name} ({f.size/1024:.0f} KB)")

    col1, col2 = st.columns(2)
    with col1:
        platform = st.selectbox(
            "评论来源平台",
            ["taobao", "jd"],
            format_func=lambda x: {"taobao": "淘宝/天猫", "jd": "京东"}.get(x, x),
        )
    with col2:
        product_url = st.text_input("商品链接（可选，用于溯源）", placeholder="https://item.taobao.com/item.htm?id=xxx")

    if st.button("🔍 识别截图评论", type="primary", disabled=not uploaded_files):
        from screenshot_analyzer import create_screenshot_analyzer
        with st.spinner("正在初始化视觉识别引擎（OCR + LLM）..."):
            analyzer = create_screenshot_analyzer()

        if analyzer is None:
            st.error("视觉分析引擎初始化失败，请检查 API Key 配置")
            return

        image_list = [f.getvalue() for f in uploaded_files]
        progress = st.progress(0, text="准备分析...")
        all_reviews, all_errors = [], []

        for i, img_bytes in enumerate(image_list):
            progress.progress(i / len(image_list), text=f"正在分析第 {i+1}/{len(image_list)} 张截图...")
            reviews, err = analyzer.analyze_screenshot(img_bytes, platform=platform, product_url=product_url, product_name="")
            if err:
                all_errors.append(f"截图 {i+1}: {err}")
            all_reviews.extend(reviews)

        progress.progress(1.0, text="分析完成!")

        seen, unique_reviews = set(), []
        for r in all_reviews:
            text = r.get("review_text", "")[:150].strip().lower()
            if text and text not in seen:
                seen.add(text)
                unique_reviews.append(r)

        if all_errors:
            st.warning("部分截图分析失败：" + "; ".join(all_errors))

        if unique_reviews:
            methods = {}
            for r in unique_reviews:
                m = r.get("extraction_method", "unknown")
                methods[m] = methods.get(m, 0) + 1
            st.success(f"✅ 提取到 {len(unique_reviews)} 条评论（{' | '.join(f'{k}:{v}' for k,v in methods.items())}）")
            st.table(pd.DataFrame(unique_reviews)[["review_text", "rating"]].head(10).style.hide(axis="index"))
            st.session_state["screenshot_reviews"] = unique_reviews
        else:
            st.error("未能从截图中提取到评论，请检查截图内容")
            return

    if st.session_state.get("screenshot_reviews"):
        st.divider()
        if st.button("🚀 生成深度分析报告", type="primary"):
            reviews = st.session_state["screenshot_reviews"]
            agent, err = get_agent()
            if err:
                st.error(f"Agent 初始化失败: {err}")
                return

            with st.spinner(f"正在分析 {len(reviews)} 条评论（并发处理）..."):
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
    render_page_header("📁 批量 CSV 分析", "上传 CSV 文件进行批量评论分析，支持 review_text/rating/platform 字段")

    uploaded = st.file_uploader("选择 CSV 文件", type="csv")
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            st.success(f"✅ 加载 {len(df)} 条评论")
            st.table(df.head(5).style.hide(axis="index"))
        except Exception as e:
            st.error(f"读取失败: {e}")
            return

    if uploaded is not None and st.button("🔍 开始批量分析", type="primary"):
        agent, err = get_agent()
        if err:
            st.error(f"Agent初始化失败: {err}")
            return

        reviews = df.to_dict("records")
        with st.spinner(f"正在分析 {len(reviews)} 条评论..."):
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
                    st.warning(f"第 {i+1} 条失败: {str(e)[:100]}")
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
    render_page_header("📊 分析结果", f"共分析 {len(results)} 条评论")

    total = len(results)
    sarcastic = sum(1 for r in results if r.get("sentiment_analysis", {}).get("is_sarcastic"))
    suspicious = sum(1 for r in results if r.get("final_analysis", {}).get("final_validity") in ("suspicious", "fake"))
    avg_trust = sum(r.get("final_analysis", {}).get("trust_score", 50) for r in results) / total if total else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card_html(total, "总评论数", "📝", "#EDE9FE", "#6366F1"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card_html(sarcastic, "反讽评论", "😏", "#FEF3C7", "#F59E0B"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card_html(suspicious, "可疑评论", "🚨", "#FEE2E2", "#EF4444"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card_html(f"{avg_trust:.1f}", "平均可信度", "🛡️", "#D1FAE5", "#10B981"), unsafe_allow_html=True)

    st.markdown('<div class="rp-card-title">📋 产品口碑报告</div>', unsafe_allow_html=True)
    st.code(json.dumps(report, ensure_ascii=False, indent=2), language="json")

    if trust_report:
        st.markdown('<div class="rp-card-title">🛡️ Trust Report（统计异常检测）</div>', unsafe_allow_html=True)
        st.code(json.dumps(trust_report, ensure_ascii=False, indent=2), language="json")

    st.markdown('<div class="rp-card-title">🔗 评论溯源信息</div>', unsafe_allow_html=True)
    trace_data = []
    for i, r in enumerate(reviews):
        trace_data.append({
            "#": i + 1,
            "平台": r.get("source_platform", r.get("platform", "未知")),
            "商品ID": r.get("product_id", ""),
            "评论者": r.get("reviewer_name", ""),
            "日期": r.get("review_date", ""),
            "提取方式": r.get("extraction_method", ""),
        })
    if trace_data:
        st.table(pd.DataFrame(trace_data).style.hide(axis="index"))
        st.caption("✅ 每条评论均可溯源到原始平台")

    st.markdown('<div class="rp-card-title">📝 逐条评论分析</div>', unsafe_allow_html=True)
    table_data = []
    for i, r in enumerate(results):
        final = r.get("final_analysis", {})
        sa = r.get("sentiment_analysis", {})
        va = r.get("validity_analysis", {})
        table_data.append({
            "#": i + 1,
            "评论摘要": r.get("review_text", "")[:50] + "...",
            "评分": r.get("rating", "-"),
            "情绪": sa.get("sentiment_label", "N/A"),
            "反讽": "是" if sa.get("is_sarcastic") else "否",
            "有效性": va.get("validity_label", "N/A"),
            "可信度": final.get("trust_score", "N/A"),
            "风险": final.get("risk_level", "N/A"),
        })
    st.table(pd.DataFrame(table_data).style.hide(axis="index"))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "💾 下载 JSON",
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
                st.download_button("📊 下载 CSV", data=f.read(), file_name=os.path.basename(csv_path), mime="text/csv", use_container_width=True)
        except Exception:
            pass
    with col3:
        if st.button("📄 生成 HTML 报告", use_container_width=True):
            try:
                from report_generator import HTMLReportGenerator
                gen = HTMLReportGenerator()
                html_path = gen.generate(results=results, report=report,
                    product_name=reviews[0].get("product_name", "产品") if reviews else "产品")
                st.success(f"报告已生成: {html_path}")
                webbrowser.open(f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}")
                with open(html_path, "r", encoding="utf-8") as f:
                    st.download_button("⬇️ 下载 HTML 报告", data=f.read(), file_name=os.path.basename(html_path), mime="text/html")
            except Exception as e:
                st.error(f"生成失败: {e}")


# ──────────────────────────────────────────────────────────────
# 页面：历史记录
# ──────────────────────────────────────────────────────────────

def page_history():
    """历史记录页面"""
    render_page_header("📜 历史记录", "查看所有历史分析记录，支持重新查看和导出报告")

    records = load_history()

    # Top action bar
    col_info, col_clear = st.columns([3, 1])
    with col_info:
        if records:
            st.caption(f"共 {len(records)} 条历史记录")
        else:
            st.caption("暂无历史记录")
    with col_clear:
        if records and st.button("🗑️ 清除历史记录", type="secondary", use_container_width=True):
            st.session_state["_history_confirm_clear"] = True

    if st.session_state.get("_history_confirm_clear"):
        st.markdown("""<div style="background:#FEF3C7;border:1px solid #F59E0B;border-radius:10px;padding:14px 18px;margin-bottom:16px;display:flex;align-items:center;gap:10px;">
        <span style="font-size:18px;">⚠️</span>
        <span style="color:#92400E;font-size:14px;font-weight:600;">确定要清除所有历史记录吗？此操作不可恢复！</span>
        </div>""", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ 确认清除", type="primary", use_container_width=True):
                n = clear_all_history()
                st.session_state["_history_confirm_clear"] = False
                st.success(f"已清除 {n} 条历史记录")
                st.rerun()
        with c2:
            if st.button("取消", use_container_width=True):
                st.session_state["_history_confirm_clear"] = False
                st.rerun()

    if not records:
        st.info("📭 还没有分析记录。去「产品链接」或「截图分析」开始一次分析吧。")
        return

    platform_icons = {"jd": "🛒 京东", "taobao": "🛍️ 淘宝", "tmall": "🛍️ 天猫", "unknown": "❓ 未知"}
    source_labels = {
        "product_url": "🔗 产品链接",
        "screenshot": "🖼️ 截图分析", "csv": "📁 CSV批量",
    }

    for rec in records:
        plat = rec.get("platform", "unknown")
        plat_label = platform_icons.get(plat, f"🌐 {plat}")
        src_label = source_labels.get(rec.get("source", ""), "📊 分析")
        trust = rec.get("avg_trust_score", 0)
        pname = rec.get("product_name", "未命名产品")[:60]

        with st.expander(
            f"{plat_label}  |  {src_label}  |  {pname}  |  "
            f"📊 {rec.get('review_count', 0)} 条  |  🛡️ {trust}  |  "
            f"🕐 {rec.get('timestamp_display', '')}",
            expanded=False,
        ):
            # Stats row
            mc1, mc2, mc3, mc4, mc5 = st.columns(5)
            with mc1:
                st.metric("评论数", rec.get("review_count", 0))
            with mc2:
                st.metric("平均可信度", f"{trust}")
            with mc3:
                st.metric("反讽评论", rec.get("sarcastic_count", 0))
            with mc4:
                st.metric("可疑评论", rec.get("suspicious_count", 0))
            dist = rec.get("sentiment_distribution", {})
            with mc5:
                pos = dist.get("positive", dist.get("正面", 0))
                neg = dist.get("negative", dist.get("负面", 0))
                st.metric("正/负面", f"{pos}/{neg}")

            if rec.get("url"):
                st.caption(f"🔗 {rec['url']}")

            # Report data
            if rec.get("report"):
                st.markdown('<div class="rp-card-title">📋 口碑报告</div>', unsafe_allow_html=True)
                st.code(json.dumps(rec["report"], ensure_ascii=False, indent=2), language="json")

            if rec.get("trust_report"):
                st.markdown('<div class="rp-card-title">🛡️ Trust Report</div>', unsafe_allow_html=True)
                st.code(json.dumps(rec["trust_report"], ensure_ascii=False, indent=2), language="json")

            if rec.get("results"):
                st.markdown('<div class="rp-card-title">📝 逐条分析</div>', unsafe_allow_html=True)
                table_data = []
                for i, r in enumerate(rec["results"]):
                    final = r.get("final_analysis", {})
                    sa = r.get("sentiment_analysis", {})
                    va = r.get("validity_analysis", {})
                    table_data.append({
                        "#": i + 1,
                        "评论摘要": r.get("review_text", "")[:60] + "..." if len(r.get("review_text", "")) > 60 else r.get("review_text", ""),
                        "评分": r.get("rating", "-"),
                        "情绪": sa.get("sentiment_label", "N/A"),
                        "反讽": "是" if sa.get("is_sarcastic") else "否",
                        "有效性": va.get("validity_label", "N/A"),
                        "可信度": final.get("trust_score", "N/A"),
                        "风险": final.get("risk_level", "N/A"),
                    })
                st.table(pd.DataFrame(table_data).style.hide(axis="index"))

            # Action buttons
            ac1, ac2, ac3 = st.columns(3)
            with ac1:
                st.download_button(
                    "💾 下载 JSON",
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
            with ac2:
                html_path = rec.get("html_report_path")
                if html_path and os.path.exists(html_path):
                    with open(html_path, "r", encoding="utf-8") as f:
                        st.download_button(
                            "📄 下载 HTML 报告",
                            data=f.read(),
                            file_name=f"report_{rec['id']}.html",
                            mime="text/html",
                            use_container_width=True,
                            key=f"dl_html_{rec['id']}",
                        )
                else:
                    st.button("📄 HTML 不可用", disabled=True, use_container_width=True, key=f"no_html_{rec['id']}")
            with ac3:
                if st.button("🗑️ 删除此记录", use_container_width=True, key=f"del_{rec['id']}"):
                    delete_record(rec["id"])
                    st.rerun()


# ──────────────────────────────────────────────────────────────
# 侧边栏导航
# ──────────────────────────────────────────────────────────────

NAV_ITEMS = [
    ("🏠", "首页", "dashboard"),
    ("🔗", "链接采集分析", "product_url"),
    ("🖼️", "截图识别分析", "screenshot"),
    ("📁", "批量 CSV 分析", "csv"),
    ("📜", "历史记录", "history"),
]


def render_sidebar():
    """侧边栏：品牌标识 + 导航按钮 + 缓存管理 + 版本信息"""
    with st.sidebar:
        st.markdown("""
        <div class="rp-sidebar-brand">
            <div class="rp-sidebar-logo">🔍</div>
            <div>
                <div class="rp-sidebar-name">ReviewPilot</div>
                <div class="rp-sidebar-version">智能评论分析 Agent</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 导航按钮
        current = st.session_state.get("current_page", "dashboard")
        for icon, label, key in NAV_ITEMS:
            btn_type = "primary" if current == key else "secondary"
            if st.button(f"{icon}  {label}", key=f"nav_{key}",
                         use_container_width=True, type=btn_type):
                st.session_state["current_page"] = key
                st.rerun()

        st.divider()

        # 缓存管理
        st.markdown("### 🧹 缓存管理")
        try:
            _cache_bytes = get_cache_size()
            _cache_mb = _cache_bytes / 1024 / 1024
            if _cache_mb > 0.1:
                st.caption(f"可清理缓存: {_cache_mb:.1f} MB")
            else:
                st.caption("缓存已是干净状态")
        except Exception:
            pass
        if st.button("🧹 一键清理缓存", use_container_width=True):
            try:
                freed = clear_cache()
                st.session_state["_cache_cleaned_msg"] = f"✅ 已清理 {freed/1024/1024:.1f} MB 缓存（不影响历史记录和登录状态）"
                st.rerun()
            except Exception as e:
                st.warning(f"清理部分失败: {e}")

        if st.session_state.get("_cache_cleaned_msg"):
            st.success(st.session_state["_cache_cleaned_msg"])

        st.divider()

        # 可信度评分细则
        if st.button("📊 可信度评分细则", use_container_width=True):
            trust_guide_path = os.path.join(PROJECT_ROOT, "trust_score_guide.html")
            if os.path.exists(trust_guide_path):
                import webbrowser
                webbrowser.open(f"file:///{trust_guide_path.replace(os.sep, '/')}")
                st.toast("已在新窗口打开可信度评分细则", icon="📊")
            else:
                st.warning("评分细则文件未找到")

        st.divider()

        # 版本信息 — 固定在侧边栏底部
        st.markdown("""
        <div style="position:fixed;bottom:20px;left:0;width:inherit;padding:0 20px;color:#9CA3AF;font-size:11px;line-height:1.8;">
            <div style="font-weight:600;color:#6B7280;font-size:12px;">📖 ReviewPilot v4.1.6</div>
            <div>支持淘宝/天猫/京东 · OCR 截图识别</div>
            <div>情绪识别 · 可信度评估</div>
        </div>
        """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────

def main():
    apply_styles()
    render_ethics_banner()
    render_sidebar()

    page = st.session_state.get("current_page", "dashboard")

    # 缓存清理成功提示：点击主页任意位置后自动消失
    if st.session_state.get("_cache_cleaned_msg"):
        st.markdown("""
        <script>
        document.addEventListener('click', function(e) {
            var sidebar = window.parent.document.querySelector('section[data-testid="stSidebar"]');
            if (sidebar && sidebar.contains(e.target)) return;
            var params = new URLSearchParams(window.parent.location.search);
            if (!params.get('clear_cache_msg')) {
                params.set('clear_cache_msg', '1');
                window.parent.location.search = params.toString();
            }
        });
        </script>
        """, unsafe_allow_html=True)

    qs = st.query_params
    if qs.get("clear_cache_msg") == "1":
        st.session_state["_cache_cleaned_msg"] = None
        del qs["clear_cache_msg"]
        st.query_params = qs
        st.rerun()

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


if __name__ == "__main__":
    main()
