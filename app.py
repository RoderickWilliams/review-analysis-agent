# -*- coding: utf-8 -*-
"""
Streamlit Web UI — 跨平台用户反馈智能分析（淘宝+京东专版）
=========================================================
八爪鱼/影刀风格设计：深色侧边栏 + 品牌渐变 + 卡片化布局

提供四种分析模式：
1. 单条评论分析 — 粘贴评论，即时获取深度分析
2. 产品链接分析 — 粘贴产品URL，自动爬取+分析评论
3. 截图评论分析 — 上传网页截图，OCR+LLM识别评论并分析
4. CSV批量分析 — 上传CSV文件，批量分析并生成报告
"""

import os
import sys

# Ensure stdout/stderr use UTF-8 on Windows to prevent
# UnicodeEncodeError when emoji/symbols are printed to console.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import json
import time
import tempfile
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="ReviewPilot - 用户反馈智能分析",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Spotify dark theme
st._config.set_option("theme.base", "dark")
st._config.set_option("theme.primaryColor", "#6366f1")
st._config.set_option("theme.backgroundColor", "#121212")
st._config.set_option("theme.secondaryBackgroundColor", "#181818")
st._config.set_option("theme.textColor", "#ffffff")

# ──────────────────────────────────────────────────────────────
# 模块导入
# ──────────────────────────────────────────────────────────────

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
        from config import (
            MODEL,
        )
        from fallback_client import create_llm_client
        llm_client = create_llm_client()
        from sentiment_agent_core import ReviewAnalysisAgent
        agent = ReviewAnalysisAgent(client=llm_client, model=MODEL)
        return agent, None
    except Exception as e:
        return None, str(e)


# ──────────────────────────────────────────────────────────────
# 页面样式 — Shadcn/Tailwind 现代 SaaS 风格
# ──────────────────────────────────────────────────────────────

def apply_styles():
    st.markdown("""
    <style>
    /* ===== Spotify-Inspired Dark Design System ===== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    :root {
        --bg: #121212;
        --surface: #181818;
        --surface-elevated: #1f1f1f;
        --surface-highlight: #282828;
        --surface-hover: #2a2a2a;
        --border: #282828;
        --border-strong: #4d4d4d;
        --text: #ffffff;
        --text-secondary: #b3b3b3;
        --text-muted: #7c7c7c;
        --primary: #6366f1;
        --primary-hover: #4f46e5;
        --primary-dark: #4338ca;
        --gradient: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        --gradient-hover: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        --error: #f3727f;
        --warning: #ffa42b;
        --info: #539df5;
        --radius-sm: 4px;
        --radius: 8px;
        --radius-lg: 10px;
        --radius-pill: 9999px;
        --shadow-card: rgba(0,0,0,0.3) 0px 8px 8px;
        --shadow-elevated: rgba(0,0,0,0.5) 0px 8px 24px;
        --inset-border: rgb(18,18,18) 0px 1px 0px, rgb(124,124,124) 0px 0px 0px 1px inset;
    }

    * { box-sizing: border-box; }

    html, body, [class*="css"] {
        font-family: 'Inter', 'Helvetica Neue', Helvetica, Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
    .stApp { background: var(--bg) !important; }
    #MainMenu, footer, .stDeployButton { display: none !important; }
    header[data-testid="stHeader"] {
        background: var(--bg) !important;
        border-bottom: none !important;
    }

    /* Block spacing — Spotify packs content densely */
    .block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; max-width: 1280px !important; }
    .main .block-container { gap: 0.75rem !important; }
    .element-container, .stMarkdown { margin-bottom: 0.5rem; }
    div[data-testid="stVerticalBlock"] > div { margin-bottom: 0.25rem; }
    .main .stMarkdown p { line-height: 1.5 !important; }

    /* Typography — bold/regular binary, compact */
    .main h1 {
        font-size: 28px !important; font-weight: 700 !important; color: var(--text) !important;
        letter-spacing: -0.02em !important; line-height: 1.2 !important; margin-bottom: 4px !important;
    }
    .main h2 {
        font-size: 22px !important; font-weight: 700 !important; color: var(--text) !important;
        letter-spacing: -0.02em !important; margin-top: 1rem !important; margin-bottom: 8px !important;
    }
    .main h3 {
        font-size: 16px !important; font-weight: 700 !important; color: var(--text) !important;
        letter-spacing: normal !important; margin-bottom: 6px !important;
    }
    .main, .main .stMarkdown, .main .stMarkdown p,
    .main label, .main .stCaption, .main small,
    .main p, .main span, .main li { color: var(--text-secondary) !important; font-size: 14px !important; line-height: 1.5 !important; }
    .main .stMarkdown strong { color: var(--text) !important; font-weight: 700 !important; }

    /* Tabs — minimal text only, no fill color */
    .stTabs [data-baseweb="tab-list"] {
        gap: 28px; background: transparent; padding: 0;
        border: none; border-radius: 0; border-bottom: 1px solid var(--border) !important;
        box-shadow: none; margin-bottom: 32px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 2px !important; font-weight: 600 !important;
        font-size: 14px !important; color: var(--text-secondary) !important;
        background: transparent !important; border-radius: 0 !important;
        border: none !important; border-bottom: 2px solid transparent !important;
        margin-bottom: -1px !important;
        transition: color 0.2s ease !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: transparent !important; color: var(--text) !important;
    }
    .stTabs [aria-selected="true"] {
        background: transparent !important; color: var(--text) !important;
        border: none !important; border-bottom: 2px solid var(--text) !important;
        font-weight: 700 !important; box-shadow: none !important;
    }

    /* Cards — dark surfaces, no visible borders, heavy shadows */
    .ui-card {
        background: var(--surface); border-radius: var(--radius); padding: 24px; margin-bottom: 16px;
        box-shadow: var(--shadow-card); transition: background 0.3s ease;
    }
    .ui-card:hover { background: var(--surface-elevated); }
    .ui-card-title {
        font-size: 16px; font-weight: 700; color: var(--text);
        margin-bottom: 16px;
        display: flex; align-items: center; gap: 8px;
    }

    /* Stat cards */
    .stat-card {
        background: var(--surface); border-radius: var(--radius); padding: 20px; text-align: center;
        box-shadow: var(--shadow-card); transition: all 0.3s ease;
    }
    .stat-card:hover { background: var(--surface-elevated); transform: translateY(-2px); }
    .stat-card .stat-number {
        font-size: 28px; font-weight: 700; color: var(--text); line-height: 1.2;
    }
    .stat-card .stat-label {
        font-size: 12px; color: var(--text-secondary); margin-top: 6px; font-weight: 400;
        text-transform: uppercase; letter-spacing: 0.02em;
    }
    .stat-card .stat-icon { font-size: 16px; margin-bottom: 8px; }
    .stat-purple .stat-number { color: #c4b5fd; }
    .stat-blue .stat-number { color: #93c5fd; }
    .stat-green .stat-number { color: #a78bfa; }
    .stat-orange .stat-number { color: var(--warning); }
    .stat-red .stat-number { color: var(--error); }
    .trust-high { color: #a78bfa !important; font-weight: 700; }
    .trust-medium { color: var(--warning) !important; font-weight: 700; }
    .trust-low { color: var(--error) !important; font-weight: 700; }

    /* Ethics banner */
    .ethics-banner {
        background: var(--surface); border-radius: var(--radius);
        padding: 14px 18px; margin-bottom: 20px;
        font-size: 13px; color: var(--text-secondary); line-height: 1.5;
        box-shadow: var(--shadow-card);
        border-left: 3px solid #8b5cf6;
    }

    /* Buttons — pill shape, uppercase labels */
    .stButton > button[kind="primary"] {
        background: var(--gradient) !important; border: none !important;
        border-radius: var(--radius-pill) !important; padding: 10px 32px !important;
        font-weight: 700 !important; font-size: 14px !important; color: #fff !important;
        text-transform: none !important; letter-spacing: normal !important;
        box-shadow: 0 8px 24px rgba(99,102,241,0.35) !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: var(--gradient-hover) !important;
        box-shadow: 0 10px 28px rgba(99,102,241,0.45) !important;
        transform: scale(1.02) !important;
    }
    .stButton > button[kind="primary"]:active { transform: scale(0.98) !important; }
    .stButton > button:not([kind="primary"]) {
        border-radius: var(--radius-pill) !important; border: 1px solid var(--border-strong) !important;
        background: var(--surface-elevated) !important; color: var(--text) !important;
        font-weight: 700 !important; font-size: 14px !important; padding: 8px 24px !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button:not([kind="primary"]):hover {
        border-color: var(--text) !important; color: var(--text) !important;
        background: var(--surface-highlight) !important;
    }

    /* Inputs — pill search, inset border on focus */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input {
        background: var(--surface-elevated) !important; color: var(--text) !important;
        border: none !important; border-radius: var(--radius) !important;
        padding: 12px 14px !important; font-size: 14px !important; line-height: 1.5 !important;
        transition: all 0.2s ease !important;
        box-shadow: var(--inset-border) !important;
    }
    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder { color: var(--text-muted) !important; }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        box-shadow: rgb(255,255,255) 0px 0px 0px 1px inset !important;
        outline: none !important;
    }
    .stTextInput > div > div > input:hover,
    .stTextArea > div > div > textarea:hover {
        box-shadow: rgb(255,255,255) 0px 0px 0px 1px inset !important;
    }

    /* Selectbox */
    .stSelectbox > div > div,
    .stSelectbox [data-baseweb="select"] > div {
        background: var(--surface-elevated) !important; border: none !important;
        border-radius: var(--radius) !important; color: var(--text) !important;
        min-height: 42px !important;
        box-shadow: var(--inset-border) !important;
        transition: all 0.2s ease !important;
    }
    .stSelectbox > div > div:hover {
        box-shadow: rgb(255,255,255) 0px 0px 0px 1px inset !important;
    }
    .stSelectbox [data-baseweb="popover"],
    .stSelectbox ul {
        background: var(--surface-elevated) !important; border: none !important;
        border-radius: var(--radius) !important; box-shadow: var(--shadow-elevated) !important;
        padding: 4px !important;
    }
    .stSelectbox li {
        color: var(--text-secondary) !important; border-radius: var(--radius-sm) !important;
        padding: 10px 14px !important; font-size: 14px !important;
        transition: all 0.15s !important;
    }
    .stSelectbox li:hover { background: var(--surface-highlight) !important; color: var(--text) !important; }

    /* Labels */
    .stTextInput label, .stTextArea label, .stSelectbox label,
    .stNumberInput label, .stCheckbox label, .stFileUploader label {
        color: var(--text) !important; font-size: 14px !important;
        font-weight: 700 !important; margin-bottom: 4px !important;
    }

    /* File uploader */
    .stFileUploader > section {
        background: var(--surface) !important;
        border: 2px dashed var(--border-strong) !important; border-radius: var(--radius) !important;
        padding: 20px !important; transition: all 0.2s !important;
    }
    .stFileUploader > section:hover { border-color: #8b5cf6 !important; background: var(--surface-elevated) !important; }
    .stFileUploader p, .stFileUploader span { color: var(--text-secondary) !important; font-size: 13px !important; }

    /* Data display */
    .stDataFrame {
        background: var(--surface); border-radius: var(--radius);
        box-shadow: var(--shadow-card); overflow: hidden;
    }
    .stProgress > div > div > div > div {
        background: var(--gradient) !important; border-radius: var(--radius-pill);
    }
    .stAlert {
        border-radius: var(--radius) !important; border: none !important;
        box-shadow: var(--shadow-card) !important; padding: 14px 18px !important;
    }
    hr { border-color: var(--border) !important; margin: 1rem 0 !important; }
    .stJson {
        background: var(--surface-elevated) !important; border-radius: var(--radius) !important;
        padding: 14px !important; color: var(--text-secondary) !important;
    }
    .stCheckbox label { color: var(--text-secondary) !important; }

    /* Page header */
    .page-title {
        font-size: 28px; font-weight: 700; color: var(--text);
        margin-bottom: 4px; letter-spacing: -0.02em; line-height: 1.2;
    }
    .page-subtitle {
        font-size: 14px; color: var(--text-secondary); margin-bottom: 24px; line-height: 1.5;
    }

    /* Brand bar */
    .brand-bar {
        background: transparent; padding: 12px 0 20px 0; border-radius: 0;
        border-bottom: none;
        display: flex; align-items: center; justify-content: space-between;
        margin: 0 0 20px 0;
        box-shadow: none;
    }
    .brand-left { display: flex; align-items: center; gap: 12px; }
    .brand-logo {
        width: 40px; height: 40px; background: var(--gradient); border-radius: 12px;
        display: flex; align-items: center; justify-content: center; font-size: 18px;
        box-shadow: 0 4px 14px rgba(99,102,241,0.35);
    }
    .brand-title { color: var(--text); font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
    .brand-subtitle { color: var(--text-secondary); font-size: 12px; margin-top: 1px; font-weight: 400; }
    .brand-badge {
        background: var(--gradient); color: #fff;
        padding: 6px 16px; border-radius: var(--radius-pill);
        font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
    }

    /* Sidebar — same dark family, deeper shade */
    section[data-testid="stSidebar"] {
        background: #0a0a0a !important; border-right: none;
    }
    section[data-testid="stSidebar"] * { color: var(--text-secondary) !important; }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 { color: var(--text) !important; font-weight: 700 !important; }
    section[data-testid="stSidebar"] .stSelectbox > div > div,
    section[data-testid="stSidebar"] .stTextInput > div > div > input,
    section[data-testid="stSidebar"] .stTextArea > div > div > textarea {
        background: var(--surface) !important; border: none !important;
        color: var(--text) !important; border-radius: var(--radius) !important;
        box-shadow: var(--inset-border) !important;
    }
    section[data-testid="stSidebar"] .stButton > button {
        background: var(--surface-elevated) !important; border: 1px solid var(--border-strong) !important;
        color: var(--text) !important; border-radius: var(--radius-pill) !important;
        font-weight: 700 !important; padding: 8px 20px !important;
        transition: all 0.2s ease !important;
        box-shadow: none !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: var(--surface-highlight) !important; border-color: var(--text) !important;
        transform: none !important; box-shadow: none !important;
    }
    section[data-testid="stSidebar"] hr { border-color: var(--border) !important; }
    section[data-testid="stSidebar"] .stExpander {
        background: var(--surface) !important; border: none !important;
        border-radius: var(--radius) !important;
    }

    /* Spinner & download */
    .stSpinner > div { border-top-color: #8b5cf6 !important; }
    .stDownloadButton > button {
        border-radius: var(--radius-pill) !important; border: 1px solid var(--border-strong) !important;
        background: var(--surface-elevated) !important; color: var(--text) !important;
        font-weight: 700 !important; padding: 8px 24px !important;
        transition: all 0.2s ease !important;
    }
    .stDownloadButton > button:hover {
        border-color: var(--text) !important; color: var(--text) !important;
        background: var(--surface-highlight) !important;
    }

    /* Code — stays dark on dark */
    .stCodeBlock, pre {
        background: #0a0a0a !important; border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important; color: var(--text-secondary) !important;
        padding: 14px 18px !important; font-size: 13px !important; line-height: 1.5 !important;
    }
    code {
        color: #a78bfa !important; background: var(--surface-elevated) !important;
        padding: 2px 6px !important; border-radius: var(--radius-sm) !important;
        font-size: 13px !important; font-weight: 500 !important;
    }
    pre code { color: var(--text-secondary) !important; background: transparent !important; padding: 0 !important; }

    /* Expander */
    .stExpander {
        background: var(--surface) !important; border: none !important;
        border-radius: var(--radius) !important; box-shadow: var(--shadow-card) !important;
        overflow: hidden;
    }
    .stExpander summary {
        padding: 14px 18px !important; font-weight: 700 !important; color: var(--text) !important;
    }
    .stExpander [data-testid="stExpanderDetails"] { padding: 0 18px 18px 18px !important; }

    /* Metric */
    [data-testid="stMetric"] {
        background: var(--surface); border-radius: var(--radius); padding: 18px 22px;
        box-shadow: var(--shadow-card);
    }
    [data-testid="stMetricValue"] {
        font-size: 26px !important; font-weight: 700 !important;
        color: var(--text) !important; letter-spacing: -0.02em !important;
    }
    [data-testid="stMetricLabel"] { color: var(--text-secondary) !important; font-weight: 400 !important; font-size: 12px !important; text-transform: uppercase; letter-spacing: 0.02em; }
    [data-testid="stMetricDelta"] { font-weight: 700 !important; }

    /* Info boxes */
    [data-baseweb="notification"] {
        border-radius: var(--radius) !important; border: none !important;
        box-shadow: var(--shadow-card) !important;
    }

    /* Scrollbar — Spotify style thin dark */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--surface-highlight); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }

    /* Selection */
    ::selection { background: rgba(139,92,246,0.3); color: #fff; }
    </style>
    """, unsafe_allow_html=True)


def render_brand_bar():
    """顶部品牌栏"""
    st.markdown("""
    <div class="brand-bar">
        <div class="brand-left">
            <div class="brand-logo">🔍</div>
            <div>
                <div class="brand-title">ReviewPilot</div>
                <div class="brand-subtitle">跨平台用户反馈智能分析 Agent</div>
            </div>
        </div>
        <div class="brand-badge">AI Powered</div>
    </div>
    """, unsafe_allow_html=True)


def render_ethics_banner():
    st.markdown("""
    <div class="ethics-banner">
        <span>⚠️</span>
        <span><strong>伦理准则：</strong>严禁使用 AI 生成虚假评论进行虚假分析。每条用于分析的评论都有可追溯的来源（source_platform / source_url / product_id 等）。</span>
    </div>
    """, unsafe_allow_html=True)


def render_stat_card(number, label, color_class="stat-purple", icon=""):
    st.markdown(f"""
    <div class="stat-card {color_class}">
        <div class="stat-icon">{icon}</div>
        <div class="stat-number">{number}</div>
        <div class="stat-label">{label}</div>
    </div>
    """, unsafe_allow_html=True)


def render_page_header(title, subtitle, right_content=None):
    if right_content is not None:
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;">'
            f'<div><div class="page-title">{title}</div>'
            f'<div class="page-subtitle">{subtitle}</div></div>'
            f'<div id="header-right-slot"></div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 功能页面
# ──────────────────────────────────────────────────────────────

def page_single_review():
    """单条评论分析页面"""
    render_page_header("📝 单条评论分析", "粘贴一条用户评论，即时获取情绪识别、有效性检测和综合分析")

    _rcol, _rspacer = st.columns([1, 4])
    with _rcol:
        rating = st.selectbox("评分", [5, 4, 3, 2, 1], index=0)

    review_text = st.text_area(
        "评论内容",
        placeholder="在此粘贴用户评论...",
        height=120,
        label_visibility="collapsed",
    )
    _p_col1, _p_col2 = st.columns([1, 1])
    with _p_col1:
        platform = st.selectbox("平台", ["淘宝", "京东", "其他"])
    with _p_col2:
        product_name = st.text_input("产品名称（可选）", "")

    if st.button("🚀 开始深度分析", type="primary"):
        if not review_text.strip():
            st.warning("请输入评论内容")
            return

        agent, err = get_agent()
        if err:
            st.error(f"初始化失败: {err}")
            return

        with st.spinner("正在深度分析（情绪识别 + 有效性检测 + 交叉验证）..."):
            result = agent.comprehensive_analysis(
                review_text=review_text,
                rating=rating,
                platform=platform,
                product_name=product_name,
            )

        final = result.get("final_analysis", {})
        sa = result.get("sentiment_analysis", {})
        va = result.get("validity_analysis", {})

        trust = final.get("trust_score", 50)
        trust_class = "trust-high" if trust >= 71 else "trust-medium" if trust >= 31 else "trust-low"

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_stat_card(f'<span class="{trust_class}">{trust}</span>', "可信度评分", "stat-purple", "🛡️")
        with c2:
            render_stat_card(sa.get("confidence", "N/A"), "情绪置信度", "stat-blue", "🎭")
        with c3:
            sarc = "是" if sa.get("is_sarcastic") else "否"
            sarc_cls = "stat-red" if sa.get("is_sarcastic") else "stat-green"
            render_stat_card(sarc, "是否反讽", sarc_cls, "😏")
        with c4:
            risk = final.get("risk_level", "unknown")
            risk_map = {"low": ("低", "stat-green"), "medium": ("中", "stat-orange"), "high": ("高", "stat-red")}
            risk_label, risk_cls = risk_map.get(risk, (risk, "stat-purple"))
            render_stat_card(risk_label, "风险等级", risk_cls, "⚡")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="ui-card-title">🎭 情绪分析</div>', unsafe_allow_html=True)
            st.json(sa)
        with col_b:
            st.markdown('<div class="ui-card-title">🛡️ 有效性检测</div>', unsafe_allow_html=True)
            st.json(va)

        st.markdown('<div class="ui-card-title">📊 综合分析</div>', unsafe_allow_html=True)
        st.json(final)

        st.download_button(
            "💾 下载分析结果 (JSON)",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )


def page_product_url():
    """产品链接分析页面"""
    render_page_header("🔗 产品链接分析", "粘贴淘宝/京东产品链接，自动采集评论并进行深度分析")

    if st.session_state.get("product_reviews"):
        reviews = st.session_state["product_reviews"]
        results = st.session_state.get("product_results", [])
        report = st.session_state.get("product_report", {})
        trust_report = st.session_state.get("product_trust_report", {})

        st.success(f"✅ 已完成 {len(reviews)} 条评论的分析")
        display_results(reviews, results, report, trust_report)

        if st.button("🔄 重新分析其他产品"):
            for key in ["product_reviews", "product_results", "product_report", "product_trust_report"]:
                st.session_state.pop(key, None)
            st.rerun()
        return

    url = st.text_input(
        "产品链接",
        placeholder="https://item.jd.com/100012345.html 或 https://item.taobao.com/item.htm?id=xxx",
        label_visibility="collapsed",
    )
    col1, col2 = st.columns(2)
    with col1:
        max_reviews = st.number_input("最大采集量（0=无上限）", 0, 100000, 100, help="设为0则持续采集直到没有更多评论")
        _max_reviews = max_reviews if max_reviews > 0 else 1000000
    with col2:
        use_selenium = st.checkbox("使用浏览器抓取（更可靠但较慢）", value=False,
                                    help="勾选后将打开浏览器进行抓取，适合API被反爬拦截时使用")

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
                    try:
                        from scrapers.taobao_playwright_scraper import TaobaoPlaywrightScraper
                        pw_scraper = TaobaoPlaywrightScraper(headless=False, max_reviews=_max_reviews)
                        reviews = pw_scraper.scrape(url, cookies=ck, max_reviews=_max_reviews)
                    except Exception:
                        reviews = []
                    if not reviews:
                        try:
                            from scrapers.taobao_comment_v2 import TaobaoCommentScraperV2
                            reviews = TaobaoCommentScraperV2().scrape(url, cookies=ck, max_reviews=_max_reviews)
                        except Exception:
                            reviews = []
                    if not reviews and ck:
                        try:
                            from scrapers.taobao_scraper import TaobaoScraper
                            tb = TaobaoScraper()
                            tb.set_cookies(ck)
                            reviews = tb.scrape_with_cookies(url, ck, max_reviews=_max_reviews)
                        except Exception:
                            reviews = []
                elif detected == "jd":
                    ck = scraper._platform_cookies.get("jd", {})
                    jd_scraper = None
                    try:
                        # 统一降级调度：DrissionPage（真实 Chrome）→ Patchright → API 直连
                        from scrapers.jd_unified_scraper import JDUnifiedScraper
                        jd_scraper = JDUnifiedScraper(headless=False, max_reviews=_max_reviews)
                        with st.spinner("正在采集京东评论（真实 Chrome → 反检测浏览器 → API 三级降级）..."):
                            reviews = jd_scraper.scrape(url, cookies=ck, max_reviews=_max_reviews)
                        # 显示每级结果
                        for method, result in jd_scraper.method_results.items():
                            icon = "✅" if "成功" in result else "⚠️"
                            st.caption(f"{icon} {method}: {result}")
                    except Exception as e:
                        st.warning(f"统一抓取器异常: {e}")
                        reviews = []
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
                elif use_selenium:
                    from scrapers.jd_scraper import JDScraper
                    reviews = JDScraper().scrape_with_selenium(url, max_reviews=_max_reviews)
                else:
                    reviews = scraper.scrape_product(url, max_reviews=_max_reviews)

            except Exception as e:
                st.error(f"采集失败: {e}")
                return

        if not reviews:
            st.warning("自动采集未获取到评论数据")
            st.info("💡 请尝试：1. 在侧边栏登录平台获取 Cookie  2. 勾选「使用浏览器抓取」  3. 切换到「截图分析」模式")
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
        st.dataframe(df_preview[[c for c in display_cols if c in df_preview.columns]].head(10),
                     use_container_width=True)

        agent, err = get_agent()
        if err:
            st.error(f"Agent初始化失败: {err}")
            return

        with st.spinner(f"正在分析 {len(reviews)} 条评论..."):
            progress = st.progress(0)
            results = []
            for i, review in enumerate(reviews):
                try:
                    result = agent.comprehensive_analysis(
                        review_text=review.get("review_text", ""),
                        rating=review.get("rating", 3),
                        platform=review.get("platform", "未知"),
                        product_name=review.get("product_name", ""),
                    )
                    sa = result.get("sentiment_analysis", {})
                    if sa.get("error") and sa.get("error_type") == "auth":
                        st.error("API Key 认证失败！请检查 .env 配置。")
                        st.stop()
                    results.append(result)
                except Exception as e:
                    st.warning(f"第 {i+1} 条分析失败: {str(e)[:100]}")
                progress.progress((i + 1) / len(reviews))

        with st.spinner("正在生成口碑报告..."):
            report = agent.generate_report(results, product_name=reviews[0].get("product_name", "产品"))

        with st.spinner("正在生成 Trust Report..."):
            try:
                trust_report = TrustReportEngine().generate_report(reviews, results)
            except Exception:
                trust_report = {}

        st.session_state["product_reviews"] = reviews
        st.session_state["product_results"] = results
        st.session_state["product_report"] = report
        st.session_state["product_trust_report"] = trust_report
        st.rerun()


def page_screenshot():
    """截图分析页面"""
    render_page_header("📷 截图评论分析", "上传商品评论页面截图，OCR + LLM 自动识别评论并生成深度分析报告")

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
            st.dataframe(pd.DataFrame(unique_reviews)[["review_text", "rating"]].head(10), use_container_width=True)
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

            with st.spinner(f"正在分析 {len(reviews)} 条评论..."):
                progress = st.progress(0)
                results = []
                for i, review in enumerate(reviews):
                    try:
                        result = agent.comprehensive_analysis(
                            review_text=review.get("review_text", ""),
                            rating=review.get("rating", 3),
                            platform=review.get("platform", "未知"),
                            product_name=review.get("product_name", ""),
                        )
                        results.append(result)
                    except Exception as e:
                        st.warning(f"第 {i+1} 条失败: {str(e)[:100]}")
                    progress.progress((i + 1) / len(reviews))

            report = agent.generate_report(results, product_name=reviews[0].get("product_name", "截图分析"))
            try:
                trust_report = TrustReportEngine().generate_report(reviews, results)
            except Exception:
                trust_report = {}
            display_results(reviews, results, report, trust_report)


def page_csv_upload():
    """CSV上传分析页面"""
    render_page_header("📁 CSV 批量分析", "上传 CSV 文件进行批量评论分析，支持 review_text/rating/platform 字段")

    uploaded = st.file_uploader("选择 CSV 文件", type="csv")
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            st.success(f"✅ 加载 {len(df)} 条评论")
            st.dataframe(df.head(5), use_container_width=True)
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
        display_results(reviews, results, report, trust_report)


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
        render_stat_card(total, "总评论数", "stat-purple", "📝")
    with c2:
        render_stat_card(sarcastic, "反讽评论", "stat-orange", "😏")
    with c3:
        render_stat_card(suspicious, "可疑评论", "stat-red", "🚨")
    with c4:
        render_stat_card(f"{avg_trust:.1f}", "平均可信度", "stat-green", "🛡️")

    st.markdown('<div class="ui-card-title">📋 产品口碑报告</div>', unsafe_allow_html=True)
    st.json(report)

    if trust_report:
        st.markdown('<div class="ui-card-title">🛡️ Trust Report（统计异常检测）</div>', unsafe_allow_html=True)
        st.json(trust_report)

    st.markdown('<div class="ui-card-title">🔗 评论溯源信息</div>', unsafe_allow_html=True)
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
        st.dataframe(pd.DataFrame(trace_data), use_container_width=True)
        st.caption("✅ 每条评论均可溯源到原始平台")

    st.markdown('<div class="ui-card-title">📝 逐条评论分析</div>', unsafe_allow_html=True)
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
    st.dataframe(pd.DataFrame(table_data), use_container_width=True)

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
                with open(html_path, "r", encoding="utf-8") as f:
                    st.download_button("⬇️ 下载 HTML 报告", data=f.read(), file_name=os.path.basename(html_path), mime="text/html")
            except Exception as e:
                st.error(f"生成失败: {e}")


# ──────────────────────────────────────────────────────────────
# 侧边栏
# ──────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding: 20px 0 12px;">
            <div style="width:56px;height:56px;background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:14px;
                        display:inline-flex;align-items:center;justify-content:center;font-size:26px;
                        box-shadow:0 4px 14px rgba(99,102,241,0.35);">🔍</div>
            <div style="color:#fff;font-size:20px;font-weight:700;margin-top:14px;letter-spacing:-0.02em;">ReviewPilot</div>
            <div style="color:#b3b3b3;font-size:12px;font-weight:400;margin-top:2px;">v1.0.0</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # 配置状态
        st.markdown("### ⚙️ 配置状态")
        cfg = get_config()
        if cfg:
            try:
                cfg.print_config_status()
            except Exception:
                st.warning("配置加载异常")
        else:
            st.warning("config.py 未找到")

        st.divider()

        # 平台登录
        st.markdown("### 🔑 平台登录")
        st.caption("抓取评论需要登录对应平台")

        login_platform = st.selectbox(
            "选择平台",
            ["", "taobao", "jd"],
            format_func=lambda x: {"": "请选择...", "taobao": "淘宝/天猫", "jd": "京东"}.get(x, x),
            label_visibility="collapsed",
        )

        if login_platform:
            cookie_dir = os.path.join(PROJECT_ROOT, "cookies")
            os.makedirs(cookie_dir, exist_ok=True)
            cookie_path = os.path.join(cookie_dir, f"{login_platform}_cookies.json")
            has_cookie = os.path.exists(cookie_path)

            if has_cookie:
                try:
                    with open(cookie_path, "r", encoding="utf-8") as f:
                        cookie_data = json.load(f)
                    cookie_count = len(cookie_data.get("cookies", {}))
                    saved_time = cookie_data.get("saved_at", 0)
                    age_hours = (time.time() - saved_time) / 3600
                    if age_hours < 24:
                        st.success(f"✅ 已登录（{cookie_count} 个 Cookie，{age_hours:.1f}h 前）")
                    else:
                        st.warning(f"⚠️ Cookie 已过期（{age_hours:.0f}h），请重新登录")
                        has_cookie = False
                except Exception:
                    has_cookie = False

            if not has_cookie:
                st.warning(f"尚未登录，请完成下方步骤")

            login_urls = {"taobao": "https://login.taobao.com/", "jd": "https://passport.jd.com/new/login.aspx"}
            platform_names = {"taobao": "淘宝", "jd": "京东"}
            login_url = login_urls.get(login_platform, "")
            platform_name = platform_names.get(login_platform, login_platform)

            if st.button(f"📂 打开 {platform_name} 登录页", use_container_width=True, key=f"open_{login_platform}"):
                import webbrowser
                try:
                    webbrowser.open(login_url)
                except Exception:
                    st.markdown(f"[点此打开]({login_url})")
                st.session_state[f"login_opened_{login_platform}"] = True

            if st.session_state.get(f"login_opened_{login_platform}"):
                st.info(f"✅ 已打开登录页，请在浏览器中完成登录")

            with st.expander("📋 获取 Cookie 步骤", expanded=False):
                st.markdown("1. 登录后按 **F12** 打开开发者工具")
                st.markdown("2. 切换到 **「控制台」** 标签")
                st.markdown("3. 输入 `copy(document.cookie)` 回车")
                st.markdown("4. Cookie 已复制，粘贴到下方")

            cookie_str = st.text_area(
                "粘贴 Cookie",
                placeholder="在此粘贴 Cookie 内容...",
                height=70,
                label_visibility="collapsed",
                key=f"cookie_{login_platform}",
            )
            if st.button("💾 保存 Cookie", type="primary", use_container_width=True, key=f"save_{login_platform}"):
                if cookie_str and cookie_str.strip():
                    cookies = {}
                    for item in cookie_str.split(";"):
                        item = item.strip()
                        if "=" in item:
                            k, v = item.split("=", 1)
                            cookies[k.strip()] = v.strip()
                    if cookies:
                        with open(cookie_path, "w", encoding="utf-8") as f:
                            json.dump({"platform": login_platform, "cookies": cookies, "saved_at": time.time()}, f, ensure_ascii=False)
                        st.success(f"✅ 登录成功！{len(cookies)} 个 Cookie 已保存")
                        st.rerun()
                    else:
                        st.error("Cookie 格式无效")
                else:
                    st.warning("请先粘贴 Cookie")

        st.divider()
        st.markdown("### 📖 关于")
        st.caption("AI 驱动的跨平台评论分析工具")
        st.caption("支持淘宝/天猫/京东 · OCR截图识别")
        st.caption("情绪识别 · 反讽检测 · 可信度评估")


# ──────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────

def main():
    apply_styles()
    render_brand_bar()
    render_ethics_banner()
    render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📝  单条评论",
        "🔗  产品链接",
        "📷  截图分析",
        "📁  CSV批量",
    ])

    with tab1:
        page_single_review()
    with tab2:
        page_product_url()
    with tab3:
        page_screenshot()
    with tab4:
        page_csv_upload()


if __name__ == "__main__":
    main()
