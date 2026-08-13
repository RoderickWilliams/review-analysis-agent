# -*- coding: utf-8 -*-
"""
HTML 可视化报告生成模块
====================
将分析结果生成美观的 HTML 可视化报告，包含图表和表格。

使用方式:
    from report_generator import HTMLReportGenerator
    generator = HTMLReportGenerator()

    # 从JSON结果生成报告
    generator.generate(
        results=analysis_results,
        report=product_report,
        output_path="output/report.html",
        product_name="某款智能手机"
    )
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Optional

try:
    from config import OUTPUT_DIR
except ImportError:
    OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


class HTMLReportGenerator:
    """HTML可视化报告生成器"""

    def __init__(self):
        pass

    def generate(
        self,
        results: List[Dict],
        report: Dict,
        output_path: str = None,
        product_name: str = "产品",
    ) -> str:
        """
        生成HTML可视化报告

        参数:
            results:     逐条评论的分析结果列表
            report:      批量报告汇总字典
            output_path: 输出文件路径
            product_name: 产品名称

        返回:
            生成的HTML文件路径
        """
        if output_path is None:
            output_path = os.path.join(OUTPUT_DIR, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 提取统计数据
        stats = self._extract_stats(results, report)

        # 生成HTML
        html = self._build_html(product_name, stats, results, report)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"HTML报告已生成: {output_path}")
        return output_path

    def _extract_stats(self, results: List[Dict], report: Dict) -> Dict:
        """从分析结果中提取统计信息"""
        stats = {
            "total": len(results),
            "sentiment_dist": {"positive": 0, "negative": 0, "neutral": 0, "sarcastic": 0},
            "validity_dist": {"authentic": 0, "suspicious": 0, "fake": 0},
            "trust_scores": [],
            "suspicious_count": 0,
            "sarcastic_count": 0,
        }

        for r in results:
            final = r.get("final_analysis", {})
            sentiment = final.get("final_sentiment", "neutral")
            validity = final.get("final_validity", "authentic")
            trust = final.get("trust_score", 50)

            if sentiment in stats["sentiment_dist"]:
                stats["sentiment_dist"][sentiment] += 1
            if validity in stats["validity_dist"]:
                stats["validity_dist"][validity] += 1

            stats["trust_scores"].append(trust)

            if validity in ("suspicious", "fake"):
                stats["suspicious_count"] += 1

            sa = r.get("sentiment_analysis", {})
            if sa.get("is_sarcastic"):
                stats["sarcastic_count"] += 1

        # 平均价信任分
        if stats["trust_scores"]:
            stats["avg_trust"] = round(sum(stats["trust_scores"]) / len(stats["trust_scores"]), 1)
        else:
            stats["avg_trust"] = 0

        # 从report补充
        if report:
            stats["key_findings"] = report.get("key_findings", [])
            stats["top_complaints"] = report.get("top_complaints", [])
            stats["recommendations"] = report.get("recommendations", [])
            stats["fake_risk"] = report.get("fake_review_risk", "unknown")

        return stats

    def _build_html(self, product_name: str, stats: Dict, results: List[Dict], report: Dict) -> str:
        """构建完整HTML"""

        # 情绪分布数据
        sent_data = stats["sentiment_dist"]
        sent_labels = []
        sent_values = []
        sent_colors = []
        color_map = {"positive": "#1DC981", "negative": "#E8463A", "neutral": "#6B6B80", "sarcastic": "#EFAA17"}
        label_map = {"positive": "正面", "negative": "负面", "neutral": "中性", "sarcastic": "反讽"}
        for k, v in sent_data.items():
            if v > 0:
                sent_labels.append(label_map.get(k, k))
                sent_values.append(v)
                sent_colors.append(color_map.get(k, "#999"))

        # 信任分分布
        trust_ranges = {"0-30": 0, "31-50": 0, "51-70": 0, "71-100": 0}
        for score in stats["trust_scores"]:
            if score <= 30:
                trust_ranges["0-30"] += 1
            elif score <= 50:
                trust_ranges["31-50"] += 1
            elif score <= 70:
                trust_ranges["51-70"] += 1
            else:
                trust_ranges["71-100"] += 1

        # 逐条评论表格行
        table_rows = ""
        for i, r in enumerate(results):
            final = r.get("final_analysis", {})
            sa = r.get("sentiment_analysis", {})
            va = r.get("validity_analysis", {})
            trust = final.get("trust_score", 50)
            risk = final.get("risk_level", "unknown")

            risk_color = {"low": "#1DC981", "medium": "#EFAA17", "high": "#E8463A"}.get(risk, "#999")
            risk_label = {"low": "低", "medium": "中", "high": "高"}.get(risk, "未知")

            sentiment_label = sa.get("sentiment_label", "N/A")
            is_sarc = sa.get("is_sarcastic", False)
            validity_label = va.get("validity_label", "N/A")

            review_text = r.get("review_text", "")[:50]
            if len(r.get("review_text", "")) > 50:
                review_text += "..."

            sarc_badge = '<span class="badge badge-sarcasm">反讽</span>' if is_sarc else ""

            table_rows += f"""
            <tr>
                <td>{i + 1}</td>
                <td class="review-text">{review_text}</td>
                <td>{r.get('rating', '-')}</td>
                <td>{sentiment_label} {sarc_badge}</td>
                <td>{validity_label}</td>
                <td><span class="trust-score" style="color: {self._trust_color(trust)}">{trust}</span></td>
                <td><span class="badge" style="background: {risk_color}">{risk_label}</span></td>
                <td class="summary-cell">{final.get('summary', '-')}</td>
            </tr>"""

        # 关键发现
        findings_html = ""
        for f in stats.get("key_findings", []):
            findings_html += f'<li>{f}</li>'

        # 痛点
        complaints_html = ""
        for c in stats.get("top_complaints", []):
            complaints_html += f'<li>{c}</li>'

        # 建议
        recs_html = ""
        for r in stats.get("recommendations", []):
            recs_html += f'<li>{r}</li>'

        # 风险等级
        fake_risk = stats.get("fake_risk", "unknown")
        risk_color = {"low": "#1DC981", "medium": "#EFAA17", "high": "#E8463A"}.get(fake_risk, "#999")
        risk_label = {"low": "低风险", "medium": "中风险", "high": "高风险", "unknown": "未知"}.get(fake_risk, "未知")

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{product_name} - 用户反馈分析报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --accent: #4B3FE3;
            --accent2: #27D2BF;
            --dark: #1A1A2E;
            --muted: #6B6B80;
            --bg: #F5F5FA;
            --surface: #FFFFFF;
            --border: #E8E8F0;
            --danger: #E8463A;
            --success: #1DC981;
            --warning: #EFAA17;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Microsoft YaHei', 'PingFang SC', -apple-system, sans-serif;
            background: var(--bg);
            color: var(--dark);
            line-height: 1.6;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}

        /* Header */
        .report-header {{
            background: linear-gradient(135deg, var(--accent) 0%, #6C5CE7 100%);
            color: white;
            padding: 40px 32px;
            border-radius: 16px;
            margin-bottom: 24px;
        }}
        .report-header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .report-header .subtitle {{ font-size: 14px; opacity: 0.85; }}
        .report-header .date {{ font-size: 12px; opacity: 0.7; margin-top: 12px; }}

        /* Stats Cards */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: var(--surface);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            border: 1px solid var(--border);
        }}
        .stat-card .number {{
            font-size: 32px;
            font-weight: 700;
            color: var(--accent);
        }}
        .stat-card .label {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}
        .stat-card.danger .number {{ color: var(--danger); }}
        .stat-card.warning .number {{ color: var(--warning); }}
        .stat-card.success .number {{ color: var(--success); }}

        /* Section */
        .section {{
            background: var(--surface);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid var(--border);
        }}
        .section h2 {{
            font-size: 18px;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--accent);
        }}

        /* Charts */
        .chart-container {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
        }}
        .chart-box {{ position: relative; height: 260px; }}

        /* Table */
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        thead th {{
            background: var(--accent);
            color: white;
            padding: 10px 8px;
            text-align: left;
            font-weight: 600;
        }}
        tbody td {{
            padding: 8px;
            border-bottom: 1px solid var(--border);
        }}
        tbody tr:nth-child(even) {{ background: #F8F8FC; }}
        tbody tr:hover {{ background: #EEEDFC; }}
        .review-text {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .summary-cell {{ max-width: 180px; font-size: 12px; color: var(--muted); }}
        .trust-score {{ font-weight: 700; font-size: 15px; }}

        /* Badges */
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            color: white;
            font-weight: 600;
        }}
        .badge-sarcasm {{ background: var(--warning); }}

        /* Findings */
        .findings-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 16px;
        }}
        .finding-box h3 {{
            font-size: 14px;
            color: var(--accent);
            margin-bottom: 10px;
        }}
        .finding-box ul {{ list-style: none; }}
        .finding-box li {{
            padding: 6px 0 6px 16px;
            position: relative;
            font-size: 13px;
            color: var(--dark);
            border-bottom: 1px solid var(--border);
        }}
        .finding-box li:before {{
            content: "▸";
            position: absolute;
            left: 0;
            color: var(--accent2);
        }}

        /* Risk Banner */
        .risk-banner {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 16px 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            font-size: 15px;
        }}
        .risk-banner .icon {{ font-size: 24px; }}

        @media (max-width: 768px) {{
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .chart-container {{ grid-template-columns: 1fr; }}
            .findings-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="report-header">
            <h1>{product_name} - 用户反馈分析报告</h1>
            <div class="subtitle">全平台用户反馈智能分析 Agent | 深度情绪识别 · 反讽检测 · 评价有效性分析</div>
            <div class="date">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>

        <!-- Stats Cards -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="number">{stats['total']}</div>
                <div class="label">总评论数</div>
            </div>
            <div class="stat-card warning">
                <div class="number">{stats['sarcastic_count']}</div>
                <div class="label">反讽评论</div>
            </div>
            <div class="stat-card danger">
                <div class="number">{stats['suspicious_count']}</div>
                <div class="label">可疑评论</div>
            </div>
            <div class="stat-card success">
                <div class="number">{stats['avg_trust']}</div>
                <div class="label">平均可信度</div>
            </div>
        </div>

        <!-- Risk Banner -->
        <div class="risk-banner" style="background: {risk_color}22; border: 1px solid {risk_color};">
            <span class="icon">{'✅' if fake_risk == 'low' else '⚠️' if fake_risk == 'medium' else '🚨'}</span>
            <span>刷单风险评估: <strong style="color: {risk_color}">{risk_label}</strong></span>
        </div>

        <!-- Charts -->
        <div class="section">
            <h2>数据分布可视化</h2>
            <div class="chart-container">
                <div class="chart-box">
                    <canvas id="sentimentChart"></canvas>
                </div>
                <div class="chart-box">
                    <canvas id="trustChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Findings -->
        <div class="section">
            <h2>关键发现与建议</h2>
            <div class="findings-grid">
                <div class="finding-box">
                    <h3>关键发现</h3>
                    <ul>{findings_html if findings_html else '<li>暂无</li>'}</ul>
                </div>
                <div class="finding-box">
                    <h3>用户痛点</h3>
                    <ul>{complaints_html if complaints_html else '<li>暂无</li>'}</ul>
                </div>
                <div class="finding-box">
                    <h3>改进建议</h3>
                    <ul>{recs_html if recs_html else '<li>暂无</li>'}</ul>
                </div>
            </div>
        </div>

        <!-- Detailed Results -->
        <div class="section">
            <h2>逐条评论分析</h2>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>评论内容</th>
                        <th>评分</th>
                        <th>情绪分析</th>
                        <th>有效性</th>
                        <th>可信度</th>
                        <th>风险</th>
                        <th>总结</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // 情绪分布饼图
        new Chart(document.getElementById('sentimentChart'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(sent_labels, ensure_ascii=False)},
                datasets: [{{
                    data: {json.dumps(sent_values)},
                    backgroundColor: {json.dumps(sent_colors)},
                    borderWidth: 2,
                    borderColor: '#fff'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    title: {{ display: true, text: '情绪分布', font: {{ size: 14 }} }},
                    legend: {{ position: 'bottom', labels: {{ font: {{ size: 12 }} }} }}
                }}
            }}
        }});

        // 信任分分布柱状图
        new Chart(document.getElementById('trustChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(list(trust_ranges.keys()))},
                datasets: [{{
                    label: '评论数量',
                    data: {json.dumps(list(trust_ranges.values()))},
                    backgroundColor: ['#E8463A', '#EFAA17', '#6B6B80', '#1DC981'],
                    borderRadius: 6
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    title: {{ display: true, text: '可信度分布', font: {{ size: 14 }} }},
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }}
                }}
            }}
        }});
    </script>
</body>
</html>"""
        return html

    def _trust_color(self, score: int) -> str:
        """根据可信度返回颜色"""
        if score >= 71:
            return "#1DC981"
        elif score >= 51:
            return "#6B6B80"
        elif score >= 31:
            return "#EFAA17"
        else:
            return "#E8463A"


if __name__ == "__main__":
    # 测试报告生成（使用模拟数据）
    mock_results = [
        {
            "review_text": "用了两周，续航确实给力，重度使用能撑一天半",
            "rating": 5,
            "sentiment_analysis": {"sentiment_label": "真诚好评", "is_sarcastic": False, "confidence": 0.95},
            "validity_analysis": {"validity_label": "真实有效"},
            "final_analysis": {"final_sentiment": "positive", "final_validity": "authentic", "trust_score": 92, "risk_level": "low", "summary": "真实好评，续航满意度高"},
        },
        {
            "review_text": "这手机太好了，卡顿得让我学会了冥想",
            "rating": 5,
            "sentiment_analysis": {"sentiment_label": "反讽阴阳怪气", "is_sarcastic": True, "confidence": 0.88},
            "validity_analysis": {"validity_label": "真实有效"},
            "final_analysis": {"final_sentiment": "negative", "final_validity": "authentic", "trust_score": 45, "risk_level": "medium", "summary": "反讽评论，暗示卡顿严重"},
        },
    ]
    mock_report = {
        "key_findings": ["续航表现获得正面评价", "存在反讽评论暗示性能问题"],
        "top_complaints": ["卡顿问题", "性能不足"],
        "recommendations": ["优化系统流畅度", "关注性能反馈"],
        "fake_review_risk": "low",
    }

    generator = HTMLReportGenerator()
    path = generator.generate(mock_results, mock_report, product_name="测试产品")
    print(f"测试报告已生成: {path}")
