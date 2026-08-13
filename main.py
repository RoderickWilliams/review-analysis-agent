# -*- coding: utf-8 -*-
"""
主入口文件 — 全平台用户反馈智能分析 Agent
==========================================
集成：数据采集 → 预处理 → 深度分析 → Trust Report → HTML报告

使用方式:
    python main.py                          # 运行演示数据
    python main.py --url <产品链接>           # 从产品链接采集+分析
    python main.py --csv <CSV文件路径>        # 从CSV文件分析
    python main.py --demo                    # 5条演示数据
    python main.py --web                     # 启动Streamlit Web界面
"""

import os
import sys
import json
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config import (
    get_next_api_key, mark_key_failed, MODEL, BASE_URL,
    OUTPUT_DIR, DATA_DIR, is_api_key_configured, print_config_status,
    is_web_mode, is_web_configured, get_web_client, is_llm_configured
)


def run_web():
    """启动 Streamlit Web 界面"""
    print("启动 Streamlit Web 界面...")
    os.system(f"streamlit run {os.path.join(PROJECT_ROOT, 'app.py')}")


def run_demo():
    """5条演示数据"""
    return [
        {"review_text": "用了两周，续航确实给力，重度使用能撑一天半，充电也快，很满意", "rating": 5, "platform": "淘宝"},
        {"review_text": "这手机真是太好了，卡顿得让我学会了冥想，等待是一种修行", "rating": 5, "platform": "京东"},
        {"review_text": "好评！质量很好，物流很快，卖家态度好，下次还来！", "rating": 5, "platform": "淘宝"},
        {"review_text": "外观确实好看，放在桌上当摆件挺好的", "rating": 4, "platform": "淘宝"},
        {"review_text": "质量太差了，用了一周就坏了，客服也不理人，千万别买", "rating": 1, "platform": "淘宝"},
    ], "某款智能手机"


def run_url(product_url, max_reviews=50):
    """从产品链接采集评论"""
    print(f"\n[采集] 正在从 {product_url} 采集评论...")
    from scrapers.multi_platform import MultiPlatformScraper
    scraper = MultiPlatformScraper()
    reviews = scraper.scrape_product(product_url, max_reviews=max_reviews)
    product_name = reviews[0].get("product_name", "产品") if reviews else "产品"
    return reviews, product_name


def run_csv(csv_path):
    """从CSV文件加载"""
    from utils.helpers import load_reviews_from_csv
    reviews = load_reviews_from_csv(csv_path)
    product_name = reviews[0].get("product_name", "产品") if reviews else "产品"
    return reviews, product_name


def run_pipeline(reviews, product_name):
    """运行完整分析流水线"""
    if not is_llm_configured():
        if is_web_mode():
            print("\n错误: Web 模式未配置！请在 .env 中设置 OPENAI_ACCESS_TOKEN 或 OPENAI_EMAIL/OPENAI_PASSWORD")
        else:
            print("\n错误: API Key 未配置！请在 .env 文件中设置 LLM_API_KEYS")
            print("提示: 如需使用 Web 模式（无需 API Key），请在 .env 中设置 LLM_MODE=web")
        return None, None, None

    from sentiment_agent_core import ReviewAnalysisAgent
    from report_generator import HTMLReportGenerator

    # 初始化（根据模式选择客户端）
    mode_label = "Web 模式（网页版 access_token）" if is_web_mode() else "API 模式"
    print(f"\n[1/5] 初始化 Agent ({mode_label}, 模型: {MODEL}, 评论数: {len(reviews)})")
    
    if is_web_mode():
        web_client = get_web_client()
        agent = ReviewAnalysisAgent(web_client=web_client, model=MODEL)
    else:
        agent = ReviewAnalysisAgent(api_key=get_next_api_key(), model=MODEL, base_url=BASE_URL)

    # 批量分析
    print(f"\n[2/5] 深度分析（情绪识别 + 有效性检测 + 交叉验证）")
    results = agent.batch_analyze(reviews, product_name=product_name)

    # 生成报告
    print(f"\n[3/5] 生成产品口碑报告")
    report = agent.generate_report(results, product_name=product_name)

    # Trust Report
    print(f"\n[4/5] 生成 Trust Report（统计异常检测）")
    try:
        from trust_report import TrustReportEngine
        trust_engine = TrustReportEngine()
        trust_report = trust_engine.generate_report(reviews, results)
    except Exception as e:
        print(f"  Trust Report 生成失败: {e}")
        trust_report = {}

    # HTML报告
    print(f"\n[5/5] 生成 HTML 可视化报告")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    html_gen = HTMLReportGenerator()
    html_path = html_gen.generate(
        results=results, report=report,
        output_path=os.path.join(OUTPUT_DIR, f"report_{timestamp}.html"),
        product_name=product_name,
    )

    # 保存JSON
    json_path = os.path.join(OUTPUT_DIR, f"analysis_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "product_name": product_name,
            "timestamp": datetime.now().isoformat(),
            "report": report,
            "trust_report": trust_report,
            "detailed_results": results,
        }, f, ensure_ascii=False, indent=2)

    # 输出摘要
    print(f"\n{'='*60}")
    print(f"  分析完成！")
    print(f"{'='*60}")
    print(f"  总评论数:     {len(results)}")
    print(f"  真实好评率:   {report.get('authentic_positive_rate', 'N/A')}")
    print(f"  可疑评论数:   {report.get('suspicious_review_count', 'N/A')}")
    print(f"  刷单风险:     {report.get('fake_review_risk', 'N/A')}")
    if trust_report:
        print(f"  Trust Score:  {trust_report.get('overall_trust_score', 'N/A')}/100")
        print(f"  突发检测:     {'是' if trust_report.get('burst_detected') else '否'}")
        print(f"  重复评论组:   {len(trust_report.get('duplicate_groups', []))}")
    print(f"\n  输出文件:")
    print(f"    JSON: {json_path}")
    print(f"    HTML: {html_path}")

    return results, report, trust_report


def main():
    parser = argparse.ArgumentParser(description="全平台用户反馈智能分析 Agent")
    parser.add_argument("--url", type=str, help="产品链接（自动采集评论）")
    parser.add_argument("--csv", type=str, help="CSV文件路径")
    parser.add_argument("--demo", action="store_true", help="使用演示数据")
    parser.add_argument("--web", action="store_true", help="启动Streamlit Web界面")
    parser.add_argument("--max-reviews", type=int, default=50, help="最大采集量")
    args = parser.parse_args()

    print_config_status()

    if args.web:
        run_web()
        return

    if args.url:
        reviews, product_name = run_url(args.url, args.max_reviews)
    elif args.csv:
        reviews, product_name = run_csv(args.csv)
    else:
        reviews, product_name = run_demo()

    if not reviews:
        print("未获取到评论数据")
        return

    run_pipeline(reviews, product_name)


if __name__ == "__main__":
    main()
