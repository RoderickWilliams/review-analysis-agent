# -*- coding: utf-8 -*-
"""
Streamlit Web UI — 跨平台用户反馈智能分析（淘宝+京东专版）
=========================================================
提供四种分析模式：
1. 单条评论分析 — 粘贴评论，即时获取深度分析
2. 产品链接分析 — 粘贴产品URL，自动爬取+分析评论
3. 截图评论分析 — 上传网页截图，OCR+LLM识别评论并分析
4. CSV批量分析 — 上传CSV文件，批量分析并生成报告

集成能力：
  爬虫工具（6个）：JSONP拦截抓取(taobao-xhs-crawler)、API分页抓取、Selenium浏览器抓取、
                   Cookie注入抓取、短链自动解析、XHR/fetch API拦截
  图片识别（3个）：PaddleOCR、Tesseract、LLM Vision

伦理准则：
  - 严禁使用AI生成虚假评论进行虚假分析
  - 每条用于分析的评论都有可追溯的来源
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
    page_title="用户反馈智能分析 Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
            get_next_api_key, MODEL, BASE_URL,
            is_api_key_configured, is_web_mode, is_web_configured,
            get_web_client, is_llm_configured, has_deepseek_web_fallback,
        )
        if not is_llm_configured() and not has_deepseek_web_fallback():
            return None, ("LLM 未配置！请在 .env 中至少配置以下之一：\n"
                          "1. LLM_API_KEYS — DeepSeek API Key (https://platform.deepseek.com/)\n"
                          "2. DEEPSEEK_USER_TOKEN — DeepSeek 网页端 Token (免费备用)")

        from fallback_client import create_llm_client
        llm_client = create_llm_client()
        from sentiment_agent_core import ReviewAnalysisAgent
        agent = ReviewAnalysisAgent(client=llm_client, model=MODEL)
        return agent, None
    except Exception as e:
        return None, str(e)


# ──────────────────────────────────────────────────────────────
# 页面样式
# ──────────────────────────────────────────────────────────────

def apply_styles():
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(135deg, #4B3FE3 0%, #6C5CE7 100%);
        padding: 20px 30px;
        border-radius: 12px;
        color: white;
        margin-bottom: 20px;
    }
    .main-header h1 { margin: 0; font-size: 24px; }
    .main-header p { margin: 5px 0 0; font-size: 13px; opacity: 0.85; }
    .stat-card {
        background: #f8f9fc;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        border: 1px solid #e8e8f0;
    }
    .stat-card .number { font-size: 28px; font-weight: 700; color: #4B3FE3; }
    .stat-card .label { font-size: 12px; color: #6b6b80; }
    .trust-high { color: #1DC981; font-weight: 700; }
    .trust-medium { color: #EFAA17; font-weight: 700; }
    .trust-low { color: #E8463A; font-weight: 700; }
    .ethics-banner {
        background: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 8px;
        padding: 10px 15px;
        margin: 10px 0;
        font-size: 13px;
        color: #856404;
    }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    st.markdown("""
    <div class="main-header">
        <h1>🔍 跨平台用户反馈智能分析</h1>
        <p>深度情绪识别 · 反讽检测 · 评价有效性分析 · 淘宝+京东评论采集</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="ethics-banner">
        ⚠️ <strong>伦理准则</strong>：严禁使用AI生成虚假评论进行虚假分析。每条用于分析的评论都有可追溯的来源（source_platform/source_url/product_id等）。
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 功能页面
# ──────────────────────────────────────────────────────────────

def page_single_review():
    """单条评论分析页面"""
    st.header("📝 单条评论分析")

    col1, col2 = st.columns([3, 1])
    with col1:
        review_text = st.text_area(
            "输入评论内容",
            placeholder="在此粘贴用户评论...",
            height=100,
        )
    with col2:
        rating = st.selectbox("评分", [5, 4, 3, 2, 1], index=0)
        platform = st.selectbox("平台", ["淘宝", "京东", "其他"])
        product_name = st.text_input("产品名称（可选）", "")

    if st.button("🔍 开始分析", type="primary"):
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

        c1, c2, c3, c4 = st.columns(4)
        trust = final.get("trust_score", 50)
        trust_class = "trust-high" if trust >= 71 else "trust-medium" if trust >= 31 else "trust-low"

        with c1:
            st.markdown(f'<div class="stat-card"><div class="number {trust_class}">{trust}</div><div class="label">可信度评分</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="stat-card"><div class="number">{sa.get("confidence", "N/A")}</div><div class="label">情绪置信度</div></div>', unsafe_allow_html=True)
        with c3:
            sarc = "是 🔴" if sa.get("is_sarcastic") else "否 ✅"
            st.markdown(f'<div class="stat-card"><div class="number">{sarc}</div><div class="label">是否反讽</div></div>', unsafe_allow_html=True)
        with c4:
            risk = final.get("risk_level", "unknown")
            risk_color = {"low": "✅ 低", "medium": "⚠️ 中", "high": "🔴 高"}.get(risk, risk)
            st.markdown(f'<div class="stat-card"><div class="number">{risk_color}</div><div class="label">风险等级</div></div>', unsafe_allow_html=True)

        st.divider()

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("🎭 情绪分析")
            st.json(sa)
        with col_b:
            st.subheader("🛡️ 有效性检测")
            st.json(va)

        st.subheader("📊 综合分析")
        st.json(final)

        st.download_button(
            "💾 下载分析结果 (JSON)",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )


def page_product_url():
    """产品链接分析页面"""
    st.header("🔗 产品链接分析")
    st.caption("粘贴淘宝/京东产品链接，自动采集评论并进行深度分析")

    # 如果已有分析结果，直接显示（避免点击按钮后页面重置）
    if st.session_state.get("product_reviews"):
        reviews = st.session_state["product_reviews"]
        results = st.session_state.get("product_results", [])
        report = st.session_state.get("product_report", {})
        trust_report = st.session_state.get("product_trust_report", {})

        st.success(f"✅ 已完成 {len(reviews)} 条评论的分析")
        display_results(reviews, results, report, trust_report)

        if st.button("🔄 重新分析其他产品"):
            st.session_state.pop("product_reviews", None)
            st.session_state.pop("product_results", None)
            st.session_state.pop("product_report", None)
            st.session_state.pop("product_trust_report", None)
            st.rerun()
        return

    url = st.text_input(
        "产品链接",
        placeholder="https://item.jd.com/100012345.html 或 https://item.taobao.com/item.htm?id=xxx",
    )

    col1, col2 = st.columns(2)
    with col1:
        max_reviews = st.number_input("最大采集量", 10, 500, 50)
    with col2:
        use_selenium = st.checkbox("使用浏览器抓取（更可靠但较慢）", value=False,
                                    help="勾选后将打开Chrome浏览器进行抓取，适合API被反爬拦截时使用")

    if st.button("🚀 开始采集+分析", type="primary"):
        if not url.strip():
            st.warning("请输入产品链接")
            return

        reviews = []
        product_name = ""

        with st.spinner("正在采集评论..."):
            try:
                from scrapers.multi_platform import MultiPlatformScraper
                scraper = MultiPlatformScraper()

                # 加载已保存的 Cookie
                cookie_dir = os.path.join(PROJECT_ROOT, "cookies")
                for plat in ["taobao", "jd"]:
                    ck_path = os.path.join(cookie_dir, f"{plat}_cookies.json")
                    if os.path.exists(ck_path):
                        import json as _json
                        try:
                            with open(ck_path, "r", encoding="utf-8") as f:
                                ck_data = _json.load(f)
                            ck = ck_data.get("cookies", {})
                            if ck:
                                scraper.set_platform_cookies(plat, ck)
                                print(f"[app] 已加载 {plat} Cookie ({len(ck)} 个)")
                        except Exception:
                            pass

                # 自动检测平台
                from scrapers.multi_platform import MultiPlatformScraper as MPS
                detected = MPS.detect_platform(url)
                print(f"[app] 检测到平台: {detected}")

                # 淘宝: Playwright(优先,最抗检测) → API分页 → mtop签名 → Selenium(兜底)
                # 京东: 优先 API，失败后自动降级到 Selenium
                if detected == "taobao":
                    ck = scraper._platform_cookies.get("taobao", {})

                    # 方法1: Playwright 持久化登录抓取（最抗检测，不依赖API签名）
                    print("[app] 淘宝链接: 方法1 - Playwright 浏览器抓取（持久化登录）")
                    st.info("正在启动 Playwright 浏览器抓取（首次需登录，后续自动复用）...")
                    try:
                        from scrapers.taobao_playwright_scraper import TaobaoPlaywrightScraper
                        pw_scraper = TaobaoPlaywrightScraper(headless=False, max_reviews=max_reviews)
                        reviews = pw_scraper.scrape(url, cookies=ck, max_reviews=max_reviews)
                        if reviews:
                            print(f"[app] 方法1成功: {len(reviews)} 条评论")
                    except Exception as e:
                        print(f"[app] 方法1失败: {e}")
                        reviews = []

                    # 方法2: rate.taobao.com API（无需mtop签名，只需卖家ID+Cookie）
                    if not reviews:
                        print("[app] 淘宝链接: 方法2 - rate.taobao.com API 抓取")
                        try:
                            from scrapers.taobao_comment_v2 import TaobaoCommentScraperV2
                            tb_v2 = TaobaoCommentScraperV2()
                            reviews = tb_v2.scrape(url, cookies=ck, max_reviews=max_reviews)
                            if reviews:
                                print(f"[app] 方法2成功: {len(reviews)} 条评论")
                        except Exception as e:
                            print(f"[app] 方法2失败: {e}")
                            reviews = []

                    # 方法3: mtop API签名抓取（需要_m_h5_tk Cookie）
                    if not reviews:
                        print("[app] 淘宝链接: 方法3 - mtop API 签名抓取")
                        try:
                            from scrapers.taobao_scraper import TaobaoScraper
                            tb_scraper = TaobaoScraper()
                            if ck:
                                tb_scraper.set_cookies(ck)
                                reviews = tb_scraper.scrape_with_cookies(url, ck, max_reviews=max_reviews)
                                if reviews:
                                    print(f"[app] 方法3成功: {len(reviews)} 条评论")
                            else:
                                print("[app] 方法3跳过: 无Cookie")
                        except Exception as e:
                            print(f"[app] 方法3失败: {e}")
                            reviews = []
                elif detected == "jd" or use_selenium:
                    if use_selenium:
                        print("[app] 京东链接: 使用 Selenium 浏览器抓取")
                        from scrapers.jd_scraper import JDScraper
                        jd = JDScraper()
                        ck = scraper._platform_cookies.get("jd", {})
                        reviews = jd.scrape_with_selenium(url, cookies=ck, max_reviews=max_reviews)
                    else:
                        print(f"[app] 京东链接: 使用 API 抓取")
                        reviews = scraper.scrape_product(url, max_reviews=max_reviews)
                        # API 抓取失败时自动降级到 Selenium
                        if not reviews:
                            print("[app] API 抓取无结果，自动降级到 Selenium 浏览器抓取...")
                            st.info("API 抓取未获取到评论，正在尝试浏览器抓取（更可靠）...")
                            try:
                                from scrapers.jd_scraper import JDScraper
                                jd = JDScraper()
                                ck = scraper._platform_cookies.get("jd", {})
                                reviews = jd.scrape_with_selenium(url, cookies=ck, max_reviews=max_reviews)
                            except Exception as e2:
                                print(f"[app] Selenium 降级也失败: {e2}")
                else:
                    reviews = scraper.scrape_product(url, max_reviews=max_reviews)

            except Exception as e:
                st.error(f"采集失败: {e}")
                import traceback
                traceback.print_exc()
                return

        if not reviews:
            st.warning("自动采集未获取到评论数据")
            st.info(
                "💡 **可能原因**：\n\n"
                "1. **淘宝反爬保护** — 请先在侧边栏登录淘宝获取Cookie\n"
                "2. **京东需要登录** — 请先在侧边栏登录京东\n"
                "3. **尝试浏览器抓取** — 勾选「使用浏览器抓取」选项\n\n"
                "或者切换到 **📷 截图分析** 标签，上传评论页面截图进行分析。"
            )
            return

        # 验证溯源字段
        has_traceability = all(r.get("source_platform") for r in reviews)
        if has_traceability:
            st.success(f"✅ 采集到 {len(reviews)} 条评论（全部含溯源信息）")
        else:
            st.warning(f"⚠️ 采集到 {len(reviews)} 条评论，部分缺少溯源信息")

        # 显示采集预览
        df_preview = pd.DataFrame(reviews)
        display_cols = ["review_text", "rating", "platform"]
        if "source_platform" in df_preview.columns:
            display_cols.append("source_platform")
        if "extraction_method" in df_preview.columns:
            display_cols.append("extraction_method")
        st.dataframe(df_preview[[c for c in display_cols if c in df_preview.columns]].head(10),
                     use_container_width=True)

        # 分析
        agent, err = get_agent()
        if err:
            st.error(f"Agent初始化失败: {err}")
            return

        with st.spinner(f"正在分析 {len(reviews)} 条评论（情绪识别+有效性检测+交叉验证）..."):
            progress = st.progress(0)
            results = []
            analysis_failed = False
            for i, review in enumerate(reviews):
                try:
                    result = agent.comprehensive_analysis(
                        review_text=review.get("review_text", ""),
                        rating=review.get("rating", 3),
                        platform=review.get("platform", "未知"),
                        product_name=review.get("product_name", ""),
                    )
                    # 检查是否返回了错误
                    sa = result.get("sentiment_analysis", {})
                    if sa.get("error"):
                        error_type = sa.get("error_type", "unknown")
                        if error_type == "auth":
                            st.error("API Key 认证失败！")
                            st.info("请在 .env 文件中填入真实的 API Key。\n"
                                    "DeepSeek（推荐，免费额度）: https://platform.deepseek.com/\n"
                                    "OpenAI: https://platform.openai.com/api-keys")
                            analysis_failed = True
                            break
                        elif error_type == "rate_limit":
                            st.warning("API 调用频率超限，稍后重试...")
                            time.sleep(5)
                            continue
                    results.append(result)
                except Exception as e:
                    st.warning(f"第 {i+1} 条评论分析失败: {str(e)[:100]}")
                    continue
                progress.progress((i + 1) / len(reviews))

            if analysis_failed:
                st.stop()
            if not results:
                st.error("分析失败，未能生成任何结果。请检查 API Key 配置。")
                st.stop()

        with st.spinner("正在生成口碑报告..."):
            report = agent.generate_report(results, product_name=reviews[0].get("product_name", "产品"))

        with st.spinner("正在生成 Trust Report..."):
            try:
                from trust_report import TrustReportEngine
                trust_engine = TrustReportEngine()
                trust_report = trust_engine.generate_report(reviews, results)
            except Exception:
                trust_report = {}

        # 保存分析结果到 session_state（避免点击按钮后页面重置）
        st.session_state["product_reviews"] = reviews
        st.session_state["product_results"] = results
        st.session_state["product_report"] = report
        st.session_state["product_trust_report"] = trust_report

        display_results(reviews, results, report, trust_report)


def page_screenshot():
    """截图分析页面 — OCR + LLM 双管道"""
    st.header("📷 截图评论分析")
    st.caption("上传商品评论页面截图，OCR+LLM自动识别评论内容并生成深度分析报告")

    uploaded_files = st.file_uploader(
        "上传网页截图（支持多张）",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="screenshot_page_upload",
    )

    if uploaded_files:
        st.success(f"✅ 已上传 {len(uploaded_files)} 张截图")
        for f in uploaded_files:
            size_kb = f.size / 1024
            st.text(f"  📎 {f.name} ({size_kb:.0f} KB)")
    else:
        st.info("👆 请上传网页评论页面的截图\n\n"
                "操作步骤：\n"
                "1. 在浏览器中打开商品评论页面\n"
                "2. 按 Win+Shift+S 或 Cmd+Shift+4 截图\n"
                "3. 可以上传多张截图（每页评论一张）\n"
                "4. 点击下方按钮开始分析\n\n"
                "支持的图片识别引擎：\n"
                "- PaddleOCR（首选，精度高）\n"
                "- Tesseract（备用，轻量级）\n"
                "- LLM Vision（兜底，GPT-4o视觉）")

    col1, col2 = st.columns(2)
    with col1:
        platform = st.selectbox(
            "评论来源平台",
            ["taobao", "jd"],
            format_func=lambda x: {"taobao": "淘宝/天猫", "jd": "京东"}.get(x, x),
        )
    with col2:
        product_url = st.text_input(
            "商品链接（可选，用于溯源）",
            placeholder="https://item.taobao.com/item.htm?id=xxx",
        )

    if st.button("🔍 分析截图评论", type="primary", disabled=not uploaded_files):
        with st.spinner("正在初始化视觉识别引擎（OCR + LLM）..."):
            from screenshot_analyzer import create_screenshot_analyzer
            analyzer = create_screenshot_analyzer()

        if analyzer is None:
            st.error("❌ 视觉分析引擎初始化失败")
            st.info("请检查：\n"
                    "1. .env 文件中 LLM_MODE=api\n"
                    "2. LLM_API_KEYS 已配置有效的 OpenAI API Key\n"
                    "3. LLM_MODEL 设置为支持视觉的模型（如 gpt-4o）")
            return

        image_list = [f.getvalue() for f in uploaded_files]
        progress = st.progress(0, text="准备分析...")

        all_reviews = []
        all_errors = []

        for i, img_bytes in enumerate(image_list):
            progress.progress(
                (i) / len(image_list),
                text=f"正在分析第 {i+1}/{len(image_list)} 张截图...",
            )
            reviews, err = analyzer.analyze_screenshot(
                img_bytes,
                platform=platform,
                product_url=product_url,
                product_name="",
            )
            if err:
                all_errors.append(f"截图 {i+1}: {err}")
            all_reviews.extend(reviews)

        progress.progress(1.0, text="分析完成!")

        # 去重
        seen = set()
        unique_reviews = []
        for r in all_reviews:
            text = r.get("review_text", "")[:150].strip().lower()
            if text and text not in seen:
                seen.add(text)
                unique_reviews.append(r)

        if all_errors:
            st.warning(f"⚠️ 部分截图分析失败：")
            for err in all_errors:
                st.text(f"  • {err}")

        if unique_reviews:
            # 显示提取方法统计
            methods = {}
            for r in unique_reviews:
                m = r.get("extraction_method", "unknown")
                methods[m] = methods.get(m, 0) + 1
            method_str = " | ".join(f"{k}: {v}" for k, v in methods.items())
            st.success(f"✅ 从 {len(uploaded_files)} 张截图中提取到 {len(unique_reviews)} 条评论（{method_str}）")

            df_preview = pd.DataFrame(unique_reviews)
            st.subheader("📋 评论预览")
            display_cols = ["review_text", "rating", "reviewer_name"]
            if "extraction_method" in df_preview.columns:
                display_cols.append("extraction_method")
            st.dataframe(df_preview[[c for c in display_cols if c in df_preview.columns]].head(10),
                         use_container_width=True)

            st.session_state["screenshot_reviews"] = unique_reviews
        else:
            st.error("❌ 未能从截图中提取到任何评论")
            st.info("可能原因：\n"
                    "1. OCR引擎未安装 — 请安装 paddleocr 或 pytesseract\n"
                    "2. API超时 — 图片太大或网络较慢\n"
                    "3. 截图内容 — 确保截图中包含可见的评论文字\n"
                    "4. API Key — 确保配置了有效的 OpenAI API Key\n")
            return

    # 生成分析报告
    if st.session_state.get("screenshot_reviews"):
        st.divider()
        st.subheader("📊 生成深度分析报告")

        if st.button("🚀 生成报告（情绪识别+有效性检测+交叉验证）", type="primary"):
            reviews = st.session_state["screenshot_reviews"]

            agent, err = get_agent()
            if err:
                st.error(f"Agent 初始化失败: {err}")
                return

            with st.spinner(f"正在分析 {len(reviews)} 条评论..."):
                progress = st.progress(0)
                results = []
                analysis_failed = False
                for i, review in enumerate(reviews):
                    try:
                        result = agent.comprehensive_analysis(
                            review_text=review.get("review_text", ""),
                            rating=review.get("rating", 3),
                            platform=review.get("platform", "未知"),
                            product_name=review.get("product_name", ""),
                        )
                        sa = result.get("sentiment_analysis", {})
                        if sa.get("error"):
                            error_type = sa.get("error_type", "unknown")
                            if error_type == "auth":
                                st.error("API Key 认证失败！")
                                st.info("请在 .env 文件中填入真实的 API Key。\nDeepSeek（推荐）: https://platform.deepseek.com/")
                                analysis_failed = True
                                break
                        results.append(result)
                    except Exception as e:
                        st.warning(f"第 {i+1} 条评论分析失败: {str(e)[:100]}")
                        continue
                    progress.progress((i + 1) / len(reviews))

                if analysis_failed:
                    st.stop()

            with st.spinner("正在生成口碑报告..."):
                report = agent.generate_report(
                    results,
                    product_name=reviews[0].get("product_name", "截图评论分析"),
                )

            with st.spinner("正在生成 Trust Report..."):
                try:
                    from trust_report import TrustReportEngine
                    trust_engine = TrustReportEngine()
                    trust_report = trust_engine.generate_report(reviews, results)
                except Exception:
                    trust_report = {}

            display_results(reviews, results, report, trust_report)


def page_csv_upload():
    """CSV上传分析页面"""
    st.header("📁 CSV 批量分析")
    st.caption("上传CSV文件进行批量分析")

    uploaded = st.file_uploader("选择CSV文件", type=["csv"])

    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
        except Exception as e:
            st.error(f"读取失败: {e}")
            return

        st.success(f"✅ 加载 {len(df)} 条评论")
        st.dataframe(df.head(5), use_container_width=True)

        if st.button("🔍 开始批量分析", type="primary"):
            agent, err = get_agent()
            if err:
                st.error(f"Agent初始化失败: {err}")
                return

            reviews = df.to_dict("records")
            with st.spinner(f"正在分析 {len(reviews)} 条评论..."):
                progress = st.progress(0)
                results = []
                analysis_failed = False
                for i, review in enumerate(reviews):
                    try:
                        result = agent.comprehensive_analysis(
                            review_text=str(review.get("review_text", "")),
                            rating=int(review.get("rating", 3)),
                            platform=str(review.get("platform", "未知")),
                        )
                        sa = result.get("sentiment_analysis", {})
                        if sa.get("error"):
                            error_type = sa.get("error_type", "unknown")
                            if error_type == "auth":
                                st.error("API Key 认证失败！")
                                st.info("请在 .env 文件中填入真实的 API Key。\nDeepSeek（推荐）: https://platform.deepseek.com/")
                                analysis_failed = True
                                break
                        results.append(result)
                    except Exception as e:
                        st.warning(f"第 {i+1} 条评论分析失败: {str(e)[:100]}")
                        continue
                    progress.progress((i + 1) / len(reviews))

                if analysis_failed:
                    st.stop()

            report = agent.generate_report(results)

            try:
                from trust_report import TrustReportEngine
                trust_engine = TrustReportEngine()
                trust_report = trust_engine.generate_report(reviews, results)
            except Exception:
                trust_report = {}

            display_results(reviews, results, report, trust_report)


def display_results(reviews, results, report, trust_report):
    """显示分析结果"""
    st.divider()
    st.header("📊 分析结果")

    total = len(results)
    sarcastic = sum(1 for r in results if r.get("sentiment_analysis", {}).get("is_sarcastic"))
    suspicious = sum(1 for r in results if r.get("final_analysis", {}).get("final_validity") in ("suspicious", "fake"))
    avg_trust = sum(r.get("final_analysis", {}).get("trust_score", 50) for r in results) / total if total else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("总评论数", total)
    with c2:
        st.metric("反讽评论", sarcastic)
    with c3:
        st.metric("可疑评论", suspicious)
    with c4:
        st.metric("平均可信度", f"{avg_trust:.1f}")

    st.subheader("📋 产品口碑报告")
    st.json(report)

    if trust_report:
        st.subheader("🛡️ Trust Report（统计异常检测）")
        st.json(trust_report)

    # 溯源信息展示
    st.subheader("🔗 评论溯源信息")
    trace_data = []
    for i, r in enumerate(reviews):
        trace_data.append({
            "#": i + 1,
            "平台": r.get("source_platform", r.get("platform", "未知")),
            "商品ID": r.get("product_id", ""),
            "评论者": r.get("reviewer_name", ""),
            "日期": r.get("review_date", ""),
            "提取方式": r.get("extraction_method", ""),
            "来源URL": r.get("source_url", "")[:50] + "..." if r.get("source_url") else "",
        })
    if trace_data:
        st.dataframe(pd.DataFrame(trace_data), use_container_width=True)
        st.caption("✅ 每条评论均可溯源到原始平台和链接")

    st.subheader("📝 逐条评论分析")
    table_data = []
    for i, r in enumerate(results):
        final = r.get("final_analysis", {})
        sa = r.get("sentiment_analysis", {})
        va = r.get("validity_analysis", {})
        table_data.append({
            "#": i + 1,
            "评论": r.get("review_text", "")[:50] + "...",
            "评分": r.get("rating", "-"),
            "情绪": sa.get("sentiment_label", "N/A"),
            "反讽": "是" if sa.get("is_sarcastic") else "否",
            "有效性": va.get("validity_label", "N/A"),
            "可信度": final.get("trust_score", "N/A"),
            "风险": final.get("risk_level", "N/A"),
            "总结": final.get("summary", "N/A"),
        })
    st.dataframe(pd.DataFrame(table_data), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "💾 下载 JSON 结果",
            data=json.dumps({"report": report, "results": results, "trust_report": trust_report}, ensure_ascii=False, indent=2),
            file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )
    with col2:
        try:
            from utils.helpers import export_to_csv
            csv_path = os.path.join(tempfile.gettempdir(), f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            export_to_csv(results, csv_path)
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                st.download_button("📊 下载 CSV 结果", data=f.read(), file_name=os.path.basename(csv_path), mime="text/csv")
        except Exception:
            pass

    if st.button("📄 生成HTML可视化报告"):
        try:
            from report_generator import HTMLReportGenerator
            from config import OUTPUT_DIR
            gen = HTMLReportGenerator()
            html_path = gen.generate(
                results=results,
                report=report,
                product_name=reviews[0].get("product_name", "产品") if reviews else "产品",
            )
            st.success(f"HTML报告已生成: {html_path}")
            with open(html_path, "r", encoding="utf-8") as f:
                st.download_button("⬇️ 下载HTML报告", data=f.read(), file_name=os.path.basename(html_path), mime="text/html")
        except Exception as e:
            st.error(f"生成失败: {e}")


# ──────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────

def main():
    apply_styles()
    render_header()

    with st.sidebar:
        st.header("⚙️ 配置状态")
        cfg = get_config()
        if cfg:
            try:
                cfg.print_config_status()
            except Exception:
                st.warning("配置加载异常")
        else:
            st.warning("config.py 未找到")

        st.divider()
        st.header("🔑 平台登录（淘宝/京东）")
        st.markdown("*抓取评论需要登录对应平台*")

        login_platform = st.selectbox(
            "选择平台",
            ["", "taobao", "jd"],
            format_func=lambda x: {"": "请选择...", "taobao": "淘宝/天猫", "jd": "京东"}.get(x, x)
        )

        if login_platform:
            cookie_dir = os.path.join(PROJECT_ROOT, "cookies")
            os.makedirs(cookie_dir, exist_ok=True)
            cookie_path = os.path.join(cookie_dir, f"{login_platform}_cookies.json")
            has_cookie = os.path.exists(cookie_path)

            if has_cookie:
                import json
                try:
                    with open(cookie_path, "r", encoding="utf-8") as f:
                        cookie_data = json.load(f)
                    cookie_count = len(cookie_data.get("cookies", {}))
                    saved_time = cookie_data.get("saved_at", 0)
                    age_hours = (time.time() - saved_time) / 3600
                    if age_hours < 24:
                        st.success(f"✅ 已登录 {login_platform}（{cookie_count} 个Cookie，{age_hours:.1f}小时前）")
                    else:
                        st.warning(f"⚠️ Cookie已过期（{age_hours:.0f}小时前），请重新登录")
                        has_cookie = False
                except Exception:
                    has_cookie = False

            if not has_cookie:
                st.warning(f"尚未登录 {login_platform}")

            st.markdown("---")

            login_urls = {
                "taobao": "https://login.taobao.com/",
                "jd": "https://passport.jd.com/new/login.aspx",
            }
            login_url = login_urls.get(login_platform, "")
            platform_names = {"taobao": "淘宝", "jd": "京东"}
            platform_name = platform_names.get(login_platform, login_platform)

            st.markdown(f"#### 🔑 登录{platform_name}")

            st.markdown("**第1步：打开登录页**")
            if st.button(f"📂 打开{platform_name}登录页", type="primary", key=f"open_login_{login_platform}", use_container_width=True):
                import webbrowser
                try:
                    webbrowser.open(login_url)
                    st.session_state[f"login_opened_{login_platform}"] = True
                except Exception:
                    st.markdown(f"👉 [点此打开]({login_url})")
                    st.session_state[f"login_opened_{login_platform}"] = True

            st.markdown("**第2步：登录账号**")
            st.markdown(f"在打开的页面中正常登录{platform_name}（扫码或账密）")

            if st.session_state.get(f"login_opened_{login_platform}"):
                st.info(f"✅ 已打开{platform_name}登录页，请完成登录后继续第3步")

            st.markdown("**第3步：获取Cookie（二选一）**")

            with st.expander("方式A：书签工具（推荐）", expanded=True):
                st.markdown("① 把下方链接拖到浏览器书签栏：")
                bookmarklet_html = (
                    '<a href="javascript:void((function(){'
                    'var c=document.cookie;'
                    'if(navigator.clipboard){'
                    "navigator.clipboard.writeText(c).then(function(){"
                    "alert('Cookie已复制!共'+c.split(';').length+'个')"
                    '})}'
                    '})())" '
                    'style="display:inline-block;padding:8px 20px;background:#ff5000;color:white;border-radius:8px;text-decoration:none;font-weight:bold;">'
                    '📑 获取Cookie</a>'
                )
                st.markdown(bookmarklet_html, unsafe_allow_html=True)
                st.markdown("② 登录后，点击书签栏中的「获取Cookie」")
                st.markdown("③ 弹出「Cookie已复制」后，继续第4步")
                st.caption("💡 书签栏没显示？按 Ctrl+Shift+B")

            with st.expander("方式B：控制台复制"):
                st.markdown("① 在页面按 **F12** 键")
                st.markdown("② 点击顶部的 **「控制台」** 标签")
                st.markdown("③ 粘贴这行代码：")
                st.code("copy(document.cookie)", language="javascript")
                st.markdown("④ 按 **回车键**，Cookie已复制")
                st.caption("💡 中文浏览器显示「控制台」，不是 Console")

            st.markdown("**第4步：粘贴Cookie并保存**")
            cookie_str = st.text_area(
                "粘贴Cookie（Ctrl+V）",
                placeholder="在此粘贴 Cookie 内容...",
                height=70,
                key=f"cookie_input_{login_platform}"
            )
            if st.button("💾 保存Cookie并完成登录", type="primary", key=f"save_cookie_{login_platform}", use_container_width=True):
                if cookie_str and cookie_str.strip():
                    cookies = {}
                    for item in cookie_str.split(";"):
                        item = item.strip()
                        if "=" in item:
                            k, v = item.split("=", 1)
                            cookies[k.strip()] = v.strip()
                    if cookies:
                        import json
                        with open(cookie_path, "w", encoding="utf-8") as f:
                            json.dump({"platform": login_platform, "cookies": cookies, "saved_at": time.time()}, f, ensure_ascii=False)
                        st.success(f"✅ 登录成功！已保存 {len(cookies)} 个Cookie")
                        st.rerun()
                    else:
                        st.error("Cookie格式无效")
                else:
                    st.warning("请先粘贴Cookie")

        st.divider()
        st.header("📖 使用说明")
        st.markdown("""
        **支持平台**：淘宝/天猫、京东

        **分析模式**：
        1. **单条评论** — 粘贴评论，即时分析
        2. **产品链接** — 粘贴URL，自动爬取+分析
        3. **截图分析** — 上传截图，OCR+LLM识别
        4. **CSV批量** — 上传CSV文件批量处理

        **集成工具**：
        - 6个爬虫工具（JSONP拦截/API/Selenium/Cookie/短链/XHR拦截）
        - 3个图片识别工具（PaddleOCR/Tesseract/LLM Vision）

        **伦理准则**：
        - 严禁AI生成虚假评论
        - 每条评论可溯源到原始平台
        """)

    tab1, tab2, tab3, tab4 = st.tabs(["📝 单条评论", "🔗 产品链接", "📷 截图分析", "📁 CSV批量"])

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
