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

# Force light theme before any rendering
st._config.set_option("theme.base", "light")
st._config.set_option("theme.primaryColor", "#667eea")
st._config.set_option("theme.backgroundColor", "#f0f2f5")
st._config.set_option("theme.secondaryBackgroundColor", "#ffffff")
st._config.set_option("theme.textColor", "#1e293b")

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
# 页面样式 — 八爪鱼/影刀风格
# ──────────────────────────────────────────────────────────────

def apply_styles():
    st.markdown("""
    <style>
    /* ===== Force light theme root ===== */
    :root {
        --background: #f0f2f5;
        --secondary-background: #ffffff;
        --text: #1e293b;
        --font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    }
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: var(--font) !important;
        color: #1e293b !important;
    }

    .stApp {
        background: #f0f2f5 !important;
        color: #1e293b !important;
    }

    /* ===== Hide default elements ===== */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {background: transparent !important;}
    .stDeployButton {display: none !important;}

    /* ===== ALL text in main area must be dark ===== */
    .main .stMarkdown, .main .stMarkdown p,
    .main .stMarkdown span, .main .stMarkdown li,
    .main label, .main .stCaption, .main small,
    .main .stText, .main p, .main span, .main li {
        color: #334155 !important;
    }
    .main h1, .main h2, .main h3, .main h4, .main h5, .main h6 {
        color: #0f172a !important;
    }

    /* ===== Brand bar ===== */
    .brand-bar {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
        padding: 20px 36px;
        border-radius: 0 0 20px 20px;
        display: flex; align-items: center; justify-content: space-between;
        margin: -16px -16px 24px -16px;
        box-shadow: 0 6px 24px rgba(49, 46, 129, 0.35);
    }
    .brand-left { display: flex; align-items: center; gap: 16px; }
    .brand-logo {
        width: 48px; height: 48px;
        background: linear-gradient(135deg, #818cf8 0%, #a78bfa 100%);
        border-radius: 14px;
        display: flex; align-items: center; justify-content: center;
        font-size: 24px;
        box-shadow: 0 4px 16px rgba(129, 140, 248, 0.5);
    }
    .brand-title { color: #fff; font-size: 22px; font-weight: 700; letter-spacing: 0.3px; }
    .brand-subtitle { color: rgba(255,255,255,0.65); font-size: 13px; margin-top: 3px; }
    .brand-badge {
        background: rgba(129, 140, 248, 0.2);
        border: 1px solid rgba(129, 140, 248, 0.5);
        color: #c7d2fe;
        padding: 6px 16px; border-radius: 20px;
        font-size: 12px; font-weight: 600; letter-spacing: 0.5px;
    }

    /* ===== Sidebar - dark ===== */
    section[data-testid="stSidebar"],
    nav[data-testid="stSidebarNav"] {
        background: #1e1b4b !important;
        border-right: 1px solid #312e81;
    }
    section[data-testid="stSidebar"] * {
        color: rgba(255,255,255,0.8) !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #fff !important;
    }
    section[data-testid="stSidebar"] .stSelectbox > div > div,
    section[data-testid="stSidebar"] .stTextInput > div > div > input,
    section[data-testid="stSidebar"] .stTextArea > div > div > textarea {
        background: rgba(255,255,255,0.1) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        color: #fff !important;
        border-radius: 8px !important;
    }
    section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.12) !important; }
    section[data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
        border: none !important; color: #fff !important; font-weight: 600 !important;
        border-radius: 8px !important;
    }
    section[data-testid="stSidebar"] .stExpander {
        background: rgba(255,255,255,0.06) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 10px !important;
    }
    section[data-testid="stSidebar"] .stCheckbox label {
        color: rgba(255,255,255,0.8) !important;
    }

    /* ===== Tabs - clean light ===== */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: #fff;
        padding: 6px;
        border-radius: 14px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        margin-bottom: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px !important;
        padding: 12px 24px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        color: #64748b !important;
        background: transparent !important;
        transition: all 0.2s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: #f1f5f9 !important;
        color: #1e293b !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
        color: #fff !important;
        box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
    }

    /* ===== Cards ===== */
    .ui-card {
        background: #fff;
        border-radius: 16px;
        padding: 28px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.05);
        border: 1px solid #e8eaf0;
        margin-bottom: 20px;
    }
    .ui-card-title {
        font-size: 17px; font-weight: 700; color: #0f172a;
        margin-bottom: 18px; display: flex; align-items: center; gap: 8px;
    }

    /* ===== Stat cards ===== */
    .stat-card {
        background: #fff;
        border-radius: 14px;
        padding: 22px 16px;
        text-align: center;
        border: 1px solid #e8eaf0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: all 0.2s ease;
    }
    .stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }
    .stat-card .stat-number { font-size: 34px; font-weight: 700; line-height: 1.2; color: #1e293b; }
    .stat-card .stat-label { font-size: 13px; color: #94a3b8; margin-top: 8px; font-weight: 500; }
    .stat-card .stat-icon { font-size: 22px; margin-bottom: 10px; }
    .stat-purple .stat-number { color: #7c3aed; }
    .stat-blue .stat-number { color: #2563eb; }
    .stat-green .stat-number { color: #059669; }
    .stat-orange .stat-number { color: #d97706; }
    .stat-red .stat-number { color: #dc2626; }

    .trust-high { color: #059669; }
    .trust-medium { color: #d97706; }
    .trust-low { color: #dc2626; }

    /* ===== Ethics banner ===== */
    .ethics-banner {
        background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
        border: 1px solid #f59e0b;
        border-radius: 12px;
        padding: 14px 20px;
        margin-bottom: 20px;
        font-size: 13px;
        color: #92400e;
        display: flex; align-items: center; gap: 10px;
    }

    /* ===== Buttons ===== */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px 32px !important;
        font-weight: 600 !important;
        font-size: 15px !important;
        color: #fff !important;
        box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4) !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5) !important;
    }
    .stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]) {
        border-radius: 8px !important;
        border: 1px solid #e2e8f0 !important;
        background: #fff !important;
        color: #475569 !important;
        font-weight: 500 !important;
    }
    .stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]):hover {
        border-color: #6366f1 !important;
        color: #6366f1 !important;
    }

    /* ===== Inputs - FORCE WHITE BG AND DARK TEXT ===== */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input {
        background: #fff !important;
        color: #1e293b !important;
        border: 1.5px solid #e2e8f0 !important;
        border-radius: 10px !important;
        font-size: 14px !important;
    }
    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder {
        color: #94a3b8 !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stNumberInput > div > div > input:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
    }

    /* ===== Selectbox - force white ===== */
    .stSelectbox > div > div,
    .stSelectbox [data-baseweb="select"] > div {
        background: #fff !important;
        border: 1.5px solid #e2e8f0 !important;
        border-radius: 10px !important;
        color: #1e293b !important;
    }
    .stSelectbox [data-baseweb="select"] > div > div {
        color: #1e293b !important;
    }

    /* ===== Labels - force visible dark ===== */
    .stTextInput label, .stTextArea label, .stSelectbox label,
    .stNumberInput label, .stCheckbox label, .stFileUploader label,
    .stDateInput label, .stTimeInput label {
        color: #334155 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }

    /* ===== DataFrame ===== */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #e8eaf0;
    }

    /* ===== Progress ===== */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #6366f1, #8b5cf6) !important;
        border-radius: 4px;
    }

    /* ===== Alerts ===== */
    .stAlert {
        border-radius: 12px !important;
    }

    /* ===== Divider ===== */
    hr {
        border-color: #e8eaf0 !important;
    }

    /* ===== File uploader ===== */
    .stFileUploader > section {
        background: #fff !important;
        border: 2px dashed #cbd5e1 !important;
        border-radius: 12px !important;
    }
    .stFileUploader > section:hover {
        border-color: #6366f1 !important;
    }
    .stFileUploader p, .stFileUploader span {
        color: #64748b !important;
    }

    /* ===== Checkbox ===== */
    .stCheckbox label {
        color: #334155 !important;
    }

    /* ===== Page title ===== */
    .page-title {
        font-size: 24px; font-weight: 700; color: #0f172a; margin-bottom: 4px;
    }
    .page-subtitle {
        font-size: 14px; color: #94a3b8; margin-bottom: 24px;
    }

    /* ===== Spinner ===== */
    .stSpinner > div {
        border-top-color: #6366f1 !important;
    }

    /* ===== Download button ===== */
    .stDownloadButton > button {
        border-radius: 8px !important;
        border: 1px solid #e2e8f0 !important;
        background: #fff !important;
        color: #475569 !important;
    }
    .stDownloadButton > button:hover {
        border-color: #6366f1 !important;
        color: #6366f1 !important;
    }

    /* ===== JSON display ===== */
    .stJson {
        background: #f8fafc !important;
        border-radius: 10px !important;
        border: 1px solid #e8eaf0 !important;
    }
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


def render_page_header(title, subtitle):
    st.markdown(f'<div class="page-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 功能页面
# ──────────────────────────────────────────────────────────────

def page_single_review():
    """单条评论分析页面"""
    render_page_header("📝 单条评论分析", "粘贴一条用户评论，即时获取情绪识别、有效性检测和综合分析")

    with st.container():
        st.markdown('<div class="ui-card">', unsafe_allow_html=True)
        col1, col2 = st.columns([3, 1])
        with col1:
            review_text = st.text_area(
                "评论内容",
                placeholder="在此粘贴用户评论...",
                height=120,
                label_visibility="collapsed",
            )
        with col2:
            rating = st.selectbox("评分", [5, 4, 3, 2, 1], index=0)
            platform = st.selectbox("平台", ["淘宝", "京东", "其他"])
            product_name = st.text_input("产品名称（可选）", "")
        st.markdown('</div>', unsafe_allow_html=True)

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

        st.markdown('<div class="ui-card">', unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="ui-card-title">🎭 情绪分析</div>', unsafe_allow_html=True)
            st.json(sa)
        with col_b:
            st.markdown('<div class="ui-card-title">🛡️ 有效性检测</div>', unsafe_allow_html=True)
            st.json(va)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="ui-card">', unsafe_allow_html=True)
        st.markdown('<div class="ui-card-title">📊 综合分析</div>', unsafe_allow_html=True)
        st.json(final)
        st.markdown('</div>', unsafe_allow_html=True)

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

    st.markdown('<div class="ui-card">', unsafe_allow_html=True)
    url = st.text_input(
        "产品链接",
        placeholder="https://item.jd.com/100012345.html 或 https://item.taobao.com/item.htm?id=xxx",
        label_visibility="collapsed",
    )
    col1, col2 = st.columns(2)
    with col1:
        max_reviews = st.number_input("最大采集量", 10, 500, 50)
    with col2:
        use_selenium = st.checkbox("使用浏览器抓取（更可靠但较慢）", value=False,
                                    help="勾选后将打开浏览器进行抓取，适合API被反爬拦截时使用")
    st.markdown('</div>', unsafe_allow_html=True)

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
                        pw_scraper = TaobaoPlaywrightScraper(headless=False, max_reviews=max_reviews)
                        reviews = pw_scraper.scrape(url, cookies=ck, max_reviews=max_reviews)
                    except Exception:
                        reviews = []
                    if not reviews:
                        try:
                            from scrapers.taobao_comment_v2 import TaobaoCommentScraperV2
                            reviews = TaobaoCommentScraperV2().scrape(url, cookies=ck, max_reviews=max_reviews)
                        except Exception:
                            reviews = []
                    if not reviews and ck:
                        try:
                            from scrapers.taobao_scraper import TaobaoScraper
                            tb = TaobaoScraper()
                            tb.set_cookies(ck)
                            reviews = tb.scrape_with_cookies(url, ck, max_reviews=max_reviews)
                        except Exception:
                            reviews = []
                elif detected == "jd":
                    ck = scraper._platform_cookies.get("jd", {})
                    try:
                        from scrapers.jd_playwright_scraper import JDPlaywrightScraper
                        reviews = JDPlaywrightScraper(headless=False, max_reviews=max_reviews).scrape(url, cookies=ck, max_reviews=max_reviews)
                    except Exception:
                        reviews = []
                    if not reviews:
                        try:
                            reviews = scraper.scrape_product(url, max_reviews=max_reviews)
                        except Exception:
                            reviews = []
                    if not reviews:
                        try:
                            from scrapers.jd_scraper import JDScraper
                            reviews = JDScraper().scrape_with_selenium(url, cookies=ck, max_reviews=max_reviews)
                        except Exception:
                            reviews = []
                elif use_selenium:
                    from scrapers.jd_scraper import JDScraper
                    reviews = JDScraper().scrape_with_selenium(url, max_reviews=max_reviews)
                else:
                    reviews = scraper.scrape_product(url, max_reviews=max_reviews)

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

    st.markdown('<div class="ui-card">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)

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

    st.markdown('<div class="ui-card">', unsafe_allow_html=True)
    uploaded = st.file_uploader("选择 CSV 文件", type="csv")
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            st.success(f"✅ 加载 {len(df)} 条评论")
            st.dataframe(df.head(5), use_container_width=True)
        except Exception as e:
            st.error(f"读取失败: {e}")
            return
    st.markdown('</div>', unsafe_allow_html=True)

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

    st.markdown('<div class="ui-card">', unsafe_allow_html=True)
    st.markdown('<div class="ui-card-title">📋 产品口碑报告</div>', unsafe_allow_html=True)
    st.json(report)
    st.markdown('</div>', unsafe_allow_html=True)

    if trust_report:
        st.markdown('<div class="ui-card">', unsafe_allow_html=True)
        st.markdown('<div class="ui-card-title">🛡️ Trust Report（统计异常检测）</div>', unsafe_allow_html=True)
        st.json(trust_report)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="ui-card">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="ui-card">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)

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
        <div style="text-align:center; padding: 16px 0 8px;">
            <div style="width:56px;height:56px;background:linear-gradient(135deg,#667eea,#764ba2);border-radius:14px;
                        display:inline-flex;align-items:center;justify-content:center;font-size:28px;
                        box-shadow:0 4px 16px rgba(102,126,234,0.4);">🔍</div>
            <div style="color:#fff;font-size:18px;font-weight:700;margin-top:12px;">ReviewPilot</div>
            <div style="color:rgba(255,255,255,0.5);font-size:12px;">v1.0.0</div>
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
