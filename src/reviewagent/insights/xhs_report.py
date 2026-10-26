# -*- coding: utf-8 -*-
"""小红书六章 HTML 报告：概览 / 情绪与可信度 / 痛点榜 / 改进方向 / 选题模板 / 内容生产包。

报告不引外部 CDN，单文件可离线打开；所有用户内容都做 HTML 转义，
外部链接只放行 http(s)，避免笔记正文里的脚本或伪协议被执行。
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from reviewagent import config

_SENTIMENT_LABEL = {
    "positive": "正面", "negative": "负面", "neutral": "中性", "sarcastic": "反讽",
    "正面": "正面", "负面": "负面", "中性": "中性", "反讽": "反讽",
}
_RISK_LABEL = {"low": "低", "medium": "中", "high": "高"}
_SEVERITY_CLASS = {1: "sev-1", 2: "sev-2", 3: "sev-3"}


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _safe_url(url: Any) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        return ""
    return _esc(text)


def _link(url: Any, label: str = "查看原帖") -> str:
    safe = _safe_url(url)
    return f'<a href="{safe}" target="_blank" rel="noopener noreferrer">{_esc(label)}</a>' if safe else ""


class XhsReportGenerator:
    """把采集、情绪、信任、痛点、改进、选题与内容生产包拼成一份六章报告。"""

    def generate(
        self,
        *,
        product_name: str,
        capture: Dict[str, Any],
        sentiment_results: List[Dict[str, Any]],
        sentiment_report: Dict[str, Any],
        trust_report: Dict[str, Any],
        pain_report: Dict[str, Any],
        improvement_report: Dict[str, Any],
        topic_report: Dict[str, Any],
        content_kit: Optional[Dict[str, Any]] = None,
        output_path: Optional[str] = None,
    ) -> str:
        if output_path is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(config.OUTPUT_DIR / f"xhs_report_{stamp}.html")
        html_text = self._build(
            product_name=product_name,
            capture=capture,
            sentiment_results=sentiment_results,
            sentiment_report=sentiment_report,
            trust_report=trust_report,
            pain_report=pain_report,
            improvement_report=improvement_report,
            topic_report=topic_report,
            content_kit=content_kit or {},
        )
        import os

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(html_text)
        return output_path

    # ── 各章 ────────────────────────────────────────────────────

    def _build(self, **data: Any) -> str:
        capture = data["capture"]
        pain_report = data["pain_report"]
        topic_report = data["topic_report"]
        stats = capture.get("stats") or {}
        pains = pain_report.get("pain_points") or []
        verified = [point for point in pains if point.get("verified")]
        improvements = data["improvement_report"].get("improvements") or []
        topics = topic_report.get("topics") or []
        content_kit = data.get("content_kit") or {}
        kit_brief = content_kit.get("brief") or {}
        kit_selling = kit_brief.get("selling_points") or []

        cards = [
            ("笔记", stats.get("notes", 0)),
            ("评论", stats.get("comments", 0)),
            ("带图文字", stats.get("with_ocr", 0)),
            ("已验证痛点", len(verified)),
            ("选题", len(topics)),
            ("内容卖点", len(kit_selling)),
        ]
        cards_html = "".join(
            f'<div class="card"><div class="num">{_esc(value)}</div><div class="label">{_esc(label)}</div></div>'
            for label, value in cards
        )

        warnings = capture.get("warnings") or []
        warnings_html = "".join(f"<li>{_esc(item)}</li>" for item in warnings)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(data['product_name'])} · 小红书用户反馈洞察</title>
<style>
:root {{ --ink:#1c1c24; --muted:#6b6b80; --line:#e8e8f0; --bg:#f6f6fa; --surface:#fff;
  --accent:#ff2442; --accent2:#4b3fe3; --ok:#13a06b; --warn:#c98a00; --danger:#d92d20; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family:'PingFang SC','Microsoft YaHei',-apple-system,sans-serif; line-height:1.7; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:28px 20px 60px; }}
header.hero {{ background:linear-gradient(135deg,#ff2442 0%,#ff6b81 58%,#4b3fe3 130%); color:#fff; border-radius:18px; padding:34px 30px; }}
header.hero h1 {{ margin:0 0 8px; font-size:27px; }}
header.hero p {{ margin:0; opacity:.9; font-size:13px; }}
nav {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 22px; }}
nav a {{ color:var(--accent2); background:#fff; border:1px solid var(--line); border-radius:999px; padding:5px 13px; font-size:13px; text-decoration:none; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin-bottom:26px; }}
.card {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:15px 16px; }}
.card .num {{ font-size:26px; font-weight:700; letter-spacing:-.5px; }}
.card .label {{ color:var(--muted); font-size:12px; margin-top:2px; }}
section {{ background:var(--surface); border:1px solid var(--line); border-radius:16px; padding:24px 26px; margin-bottom:20px; }}
section h2 {{ margin:0 0 4px; font-size:20px; }}
section .lede {{ color:var(--muted); font-size:13px; margin:0 0 18px; }}
.sub {{ font-size:13px; color:var(--muted); }}
.bars {{ display:grid; gap:8px; margin:12px 0 4px; }}
.bar {{ display:grid; grid-template-columns:72px 1fr 42px; gap:10px; align-items:center; font-size:13px; }}
.bar .track {{ background:#f0f0f6; border-radius:999px; height:10px; overflow:hidden; }}
.bar .fill {{ height:100%; background:var(--accent2); border-radius:999px; }}
.bar .val {{ text-align:right; color:var(--muted); }}
.trust {{ display:flex; gap:20px; align-items:center; flex-wrap:wrap; margin:10px 0 6px; }}
.trust .score {{ font-size:38px; font-weight:800; }}
.tag {{ display:inline-block; font-size:12px; padding:1px 9px; border-radius:999px; background:#f1f1f7; color:var(--muted); margin-right:6px; }}
.tag.sev-3 {{ background:#fde8e6; color:var(--danger); }}
.tag.sev-2 {{ background:#fff3d6; color:var(--warn); }}
.tag.sev-1 {{ background:#e8f5ef; color:var(--ok); }}
.pain {{ border:1px solid var(--line); border-radius:12px; padding:15px 17px; margin:12px 0; }}
.pain h3 {{ margin:0 0 6px; font-size:16px; }}
.pain .meta {{ font-size:12px; color:var(--muted); margin-bottom:8px; }}
.quote {{ border-left:3px solid var(--accent); padding:6px 12px; margin:8px 0; background:#fff8f8; font-size:13px; }}
.quote .src {{ display:block; color:var(--muted); font-size:12px; margin-top:4px; }}
.grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
.improve {{ border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.improve h3 {{ margin:0 0 6px; font-size:15px; }}
.p0 {{ border-color:#f3b3ae; background:#fff9f8; }}
.p1 {{ border-color:#f0d49a; background:#fffcf4; }}
.topic {{ border:1px solid var(--line); border-radius:12px; padding:15px 17px; margin:12px 0; }}
.topic .titles {{ margin:6px 0 8px; padding-left:18px; }}
.topic .cover {{ font-family:ui-monospace,Consolas,monospace; background:#1c1c24; color:#fff; border-radius:8px; padding:8px 12px; font-size:13px; display:inline-block; margin:4px 0 8px; }}
.topic .secs {{ margin:6px 0; padding-left:18px; font-size:13px; color:var(--muted); }}
.risk-高 {{ color:var(--danger); font-weight:600; }}
.risk-中 {{ color:var(--warn); font-weight:600; }}
.risk-低 {{ color:var(--ok); }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:8px 9px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-weight:600; font-size:12px; }}
.note {{ background:#fafafd; border:1px dashed var(--line); border-radius:10px; padding:12px 14px; font-size:12px; color:var(--muted); }}
pre {{ white-space:pre-wrap; word-break:break-word; background:#fafafd; border:1px solid var(--line); border-radius:10px; padding:12px; font-size:12px; line-height:1.55; }}
details summary {{ cursor:pointer; color:var(--accent2); font-size:13px; margin:6px 0; }}
footer {{ color:var(--muted); font-size:12px; text-align:center; margin-top:26px; }}
@media (max-width:760px) {{ .cards {{ grid-template-columns:repeat(2,1fr); }} .grid-2 {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
<header class="hero">
  <h1>{_esc(data['product_name'])} · 小红书用户反馈洞察</h1>
  <p>只读采集 {_esc(stats.get('notes', 0))} 篇笔记 / {_esc(stats.get('comments', 0))} 条评论 · 情绪与可信度 · 痛点 · 改进 · 选题 · 内容生产包</p>
  <p>生成时间 {_esc(datetime.now().strftime('%Y-%m-%d %H:%M'))} · 采集目录 {_esc(capture.get('run_dir', ''))}</p>
</header>
<nav>
  <a href="#overview">一、概览</a><a href="#sentiment">二、情绪与可信度</a>
  <a href="#pains">三、痛点榜</a><a href="#improve">四、改进方向</a><a href="#topics">五、选题模板</a><a href="#content">六、内容生产包</a>
</nav>
<div class="cards">{cards_html}</div>

<section id="overview">
  <h2>一、概览与采集边界</h2>
  <p class="lede">先看这批数据能回答什么，再看榜单。样本只代表这次采到的公开笔记与评论，不外推到整个平台。</p>
  <div class="grid-2">
    <div>
      <h3>采集概况</h3>
      <table>
        <tr><th>笔记</th><td>{_esc(stats.get('notes', 0))} 篇（成功 {_esc(stats.get('notes_ok', 0))}）</td></tr>
        <tr><th>评论</th><td>{_esc(stats.get('comments', 0))} 条</td></tr>
        <tr><th>带图文字</th><td>{_esc(stats.get('with_ocr', 0))} 篇</td></tr>
        <tr><th>识别到的人群</th><td>{_esc(topic_report.get('audience', '目标用户'))}</td></tr>
        <tr><th>已验证痛点</th><td>{_esc(pain_report.get('verified_count', 0))} 条（未验证 {_esc(pain_report.get('unverified_count', 0))} 条）</td></tr>
        <tr><th>被拒引语</th><td>{_esc(pain_report.get('rejected_evidence', 0))} 条</td></tr>
      </table>
    </div>
    <div>
      <h3>这次采集的提醒</h3>
      <ul class="sub">{warnings_html or '<li>无</li>'}</ul>
      <p class="note">评论区没有展开二级回复；笔记发布时间与 IP 属地按采集结果原样保留，不推算。情绪与可信度只对评论文本做判断，笔记正文只用来补充痛点证据。</p>
    </div>
  </div>
</section>

<section id="sentiment">
  <h2>二、情绪与可信度</h2>
  <p class="lede">先判断评论本身是否可信，再读情绪分布；低可信评论不进入痛点榜的证据池。</p>
  {self._sentiment_bars(data['sentiment_results'])}
  {self._trust_block(data['trust_report'])}
  {self._dubious_table(data['sentiment_results'])}
</section>

<section id="pains">
  <h2>三、痛点榜</h2>
  <p class="lede">按“提及人数 × 互动量 × 严重度”排序。每条都带原文引语与原帖链接，引语在正文里找不到的直接剔除。</p>
  {self._pains_html(pains)}
</section>

<section id="improve">
  <h2>四、产品改进方向</h2>
  <p class="lede">优先级由影响面与改造成本计算：高影响低成本先做。每条都对应一个已验证痛点。</p>
  {self._improvements_html(improvements, data['improvement_report'].get('error', ''))}
</section>

<section id="topics">
  <h2>五、宣传选题与模板</h2>
  <p class="lede">选题只从已验证痛点出发，给标题、封面两行、正文骨架和标签；发布前仍需人工改写与合规确认。</p>
  {self._topics_html(topics, topic_report.get('risk_hits') or [])}
</section>

<section id="content">
  <h2>六、内容生产包</h2>
  <p class="lede">把已验证痛点转成主图、详情页、15 秒短视频、英文清单和素材索引；只给可执行骨架，产品参数、认证与售后必须由产品方补。</p>
  {self._content_kit_html(content_kit)}
</section>

<footer>ReviewAgent · 小红书只读采集 + 情绪/可信度 + 洞察引擎 · 报告中的链接指向原帖，观点归原作者</footer>
</div>
</body>
</html>"""

    # ── 片段 ────────────────────────────────────────────────────

    def _sentiment_bars(self, results: List[Dict[str, Any]]) -> str:
        counts: Dict[str, int] = {}
        for item in results:
            label = (
                (item.get("sentiment_analysis") or {}).get("real_sentiment")
                or (item.get("final_analysis") or {}).get("final_sentiment")
                or (item.get("sentiment_analysis") or {}).get("sentiment_label")
                or "未判定"
            )
            label = _SENTIMENT_LABEL.get(str(label), str(label))
            counts[label] = counts.get(label, 0) + 1
        if not counts:
            return '<p class="sub">没有可用的情绪分析结果。</p>'
        total = max(1, sum(counts.values()))
        rows = []
        for label, count in sorted(counts.items(), key=lambda pair: pair[1], reverse=True):
            width = round(count / total * 100, 1)
            rows.append(
                f'<div class="bar"><span>{_esc(label)}</span><span class="track">'
                f'<span class="fill" style="width:{width}%"></span></span>'
                f'<span class="val">{count}</span></div>'
            )
        return '<div class="bars">' + "".join(rows) + "</div>"

    def _trust_block(self, trust: Dict[str, Any]) -> str:
        score = trust.get("overall_trust_score", 0)
        risk = trust.get("risk_level", "low")
        posterior = trust.get("posterior") or {}
        interval = ""
        if posterior.get("low") is not None and posterior.get("high") is not None:
            interval = f"（区间 {posterior.get('low')}–{posterior.get('high')}）"
        signals = []
        for signal in trust.get("signals") or []:
            name = signal.get("name") or signal.get("label") or signal.get("id") or "信号"
            penalty = signal.get("penalty", signal.get("value", ""))
            signals.append(f"<li>{_esc(name)}：{_esc(penalty)}</li>")
        return f"""
<div class="trust">
  <div><div class="sub">综合可信度</div><div class="score">{_esc(score)}<span class="sub">/100</span></div></div>
  <div><span class="tag">风险 {_esc(_RISK_LABEL.get(risk, risk))}</span>{_esc(interval)}</div>
</div>
<p class="sub">{_esc(trust.get('summary', ''))}</p>
<ul class="sub">{''.join(signals) or '<li>无异常信号</li>'}</ul>"""

    def _dubious_table(self, results: List[Dict[str, Any]]) -> str:
        rows = []
        for index, item in enumerate(results, start=1):
            validity = (item.get("validity_analysis") or {}).get("validity_label", "")
            final = item.get("final_analysis") or {}
            trust = final.get("trust_score", "")
            if validity in ("", "真实有效"):
                continue
            text = _esc((item.get("review_text") or "")[:80])
            rows.append(f"<tr><td>{index}</td><td>{text}</td><td>{_esc(validity)}</td><td>{_esc(trust)}</td></tr>")
        if not rows:
            return '<p class="sub">没有检测到模板化、AI 生成或异常模式的评论。</p>'
        return (
            '<h3>需要谨慎看的评论</h3><table><thead><tr><th>#</th><th>评论</th>'
            '<th>有效性</th><th>可信度</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"
        )

    def _pains_html(self, pains: List[Dict[str, Any]]) -> str:
        if not pains:
            return '<p class="sub">没有提取到可验证的痛点。</p>'
        blocks = []
        unverified = []
        for point in pains:
            if not point.get("verified"):
                unverified.append(point)
                continue
            quotes = []
            for evidence in point.get("evidence") or []:
                link = _link(evidence.get("source_url"), "原帖")
                quotes.append(
                    f'<div class="quote">「{_esc(evidence.get("quote"))}」'
                    f'<span class="src">{_esc(evidence.get("review_text", ""))} {link}</span></div>'
                )
            severity = point.get("severity", 2)
            blocks.append(f"""
<div class="pain">
  <h3>#{_esc(point.get('rank'))} {_esc(point.get('statement'))}</h3>
  <div class="meta"><span class="tag {_SEVERITY_CLASS.get(severity, 'sev-2')}">{_esc(point.get('severity_label', '明显'))}</span>
  <span class="tag">{_esc(point.get('category'))}</span>
  <span class="tag">{_esc(point.get('frequency', 0))} 人提及</span>
  <span class="tag">热度 {_esc(point.get('score', 0))}</span></div>
  {''.join(quotes[:3])}
</div>""")
        if unverified:
            items = "".join(
                f"<li>{_esc(point.get('statement'))}（{_esc(point.get('category'))}，证据未通过校验）</li>"
                for point in unverified
            )
            blocks.append(f'<div class="note"><strong>未进入榜单的痛点</strong><ul>{items}</ul>引语在原文里找不到或编号不存在，已剔除。</div>')
        return "".join(blocks)

    def _improvements_html(self, improvements: List[Dict[str, Any]], error: str) -> str:
        if not improvements:
            return f'<p class="sub">{_esc(error or "没有生成改进建议。")}</p>'
        blocks = []
        for item in improvements:
            priority = item.get("priority", "P2")
            css = {"P0": "p0", "P1": "p1"}.get(priority, "")
            evidence = (item.get("evidence") or [{}])[0]
            link = _link(evidence.get("source_url"), "证据原帖")
            blocks.append(f"""
<div class="improve {css}">
  <h3>[{_esc(priority)}] {_esc(item.get('action'))}</h3>
  <div class="sub">对应痛点：{_esc(item.get('pain_statement'))}（{_esc(item.get('category'))}，严重度 {_esc(item.get('severity'))}）</div>
  <p>{_esc(item.get('rationale'))}</p>
  <table><tr><th>改造成本</th><td>{_esc(item.get('effort'))}/3</td><th>影响面</th><td>{_esc(item.get('impact'))}/3</td></tr>
  <tr><th>怎么验证</th><td colspan="3">{_esc(item.get('verification'))}</td></tr></table>
  <div class="quote">「{_esc(evidence.get('quote'))}」 {link}</div>
</div>""")
        return '<div class="grid-2">' + "".join(blocks) + "</div>"

    def _content_kit_html(self, kit: Dict[str, Any]) -> str:
        if not kit:
            return '<p class="sub">本次没有生成内容生产包。</p>'
        brief = kit.get("brief") or {}
        selling = brief.get("selling_points") or []
        hero = brief.get("hero_image") or {}
        detail = brief.get("detail_page") or {}
        video = brief.get("short_video") or {}
        multi = brief.get("multilingual") or {}
        material = kit.get("material_index") or {}
        style = kit.get("style_card") or {}
        layered = kit.get("layered_cards") or {}
        guard = kit.get("claim_guard") or {}
        warnings = kit.get("warnings") or []

        status = kit.get("status", "")
        status_label = "可执行骨架" if status == "ready" else "证据不足，只给骨架"
        status_html = f'<p class="sub">状态：{_esc(status_label)} · {_esc(kit.get("summary", ""))}</p>'
        warnings_html = "".join(f"<li>{_esc(item)}</li>" for item in warnings)

        selling_html = []
        for point in selling:
            quotes = "".join(
                f'<div class="quote">「{_esc(item.get("quote"))}」 {_link(item.get("source_url"), "原帖")}</div>'
                for item in point.get("evidence") or []
            )
            selling_html.append(f"""
<div class="improve p1">
  <h3>{_esc(point.get('id'))}｜{_esc(point.get('pain_statement'))}</h3>
  <div class="sub">{_esc(point.get('category'))} · 严重度 {_esc(point.get('severity'))}</div>
  <p>{_esc(point.get('angle'))}</p>
  <div class="sub">标题方向：{_esc(point.get('headline_direction'))}</div>
  {quotes}
</div>""")
        selling_block = "".join(selling_html) or '<p class="sub">没有已验证痛点，卖点方向留空，等补证据。</p>'

        ratios = "".join(
            f'<li>{_esc(item.get("ratio"))} · {_esc(item.get("size"))} · {_esc(item.get("use"))}</li>'
            for item in hero.get("ratios") or []
        )
        headlines = "".join(f"<li>{_esc(item)}</li>" for item in hero.get("headline_directions") or [])
        detail_rows = "".join(
            f'<tr><td>{_esc(item.get("no"))}</td><td>{_esc(item.get("title"))}</td>'
            f'<td>{_esc(item.get("copy_hint"))}</td></tr>'
            for item in detail.get("sections") or []
        )
        beats_rows = "".join(
            f'<tr><td>{_esc(item.get("start"))}–{_esc(item.get("end"))}s</td>'
            f'<td>{_esc(item.get("shot"))}</td><td>{_esc(item.get("voiceover"))}</td>'
            f'<td>{_esc(item.get("on_screen"))}</td></tr>'
            for item in video.get("beats") or []
        )
        lang_rows = "".join(
            f'<tr><td>{_esc(item.get("name"))}</td><td>{_esc(item.get("status"))}</td>'
            f'<td>{_esc("、".join(item.get("fields") or []))}</td></tr>'
            for item in multi.get("languages") or []
        )
        glossary = "".join(
            f'<li>{_esc(item.get("term"))}：{_esc(item.get("note"))}</li>'
            for item in multi.get("glossary") or []
        )
        checklist = "".join(f"<li>{_esc(item)}</li>" for item in multi.get("checklist") or [])

        image_rows = "".join(
            f'<tr><td>{_esc(item.get("note_title"))}</td><td>{_esc(item.get("orientation"))}</td>'
            f'<td>{_esc(item.get("ratio"))}</td><td>{_esc(item.get("width"))}×{_esc(item.get("height"))}</td>'
            f'<td>{_esc(item.get("note_engagement"))}</td><td>{_link(item.get("src"), "原图")} {_link(item.get("source_url"), "笔记")}</td></tr>'
            for item in material.get("entries") or []
        )
        tags = "".join(
            f'<span class="tag">#{_esc(item.get("tag"))} ×{_esc(item.get("count"))}</span>'
            for item in (style.get("observed") or {}).get("top_tags") or []
        )
        layers_json = json.dumps(layered.get("cards") or [], ensure_ascii=False, indent=2)
        allowed = "".join(
            f'<li>{_esc(item.get("claim"))}<span class="sub">（{_esc(item.get("scope"))}）</span></li>'
            for item in guard.get("allowed_evidence_claims") or []
        )
        confirm = "".join(f"<li>{_esc(item)}</li>" for item in guard.get("needs_product_confirmation") or [])
        forbidden = "、".join(_esc(item) for item in (guard.get("forbidden_terms") or [])[:16])
        scene_hint = _esc(hero.get('scene_hint'))
        style_layout = _esc((style.get('recommendations') or {}).get('layout'))
        style_limits = ''.join(f"<li>{_esc(item)}</li>" for item in style.get('limitations') or [])
        material_total = _esc(material.get('total_images', 0))
        material_notes = _esc(material.get('notes_with_images', 0))
        material_confidence = _esc(material.get('confidence'))
        material_hint = _esc(material.get('note'))
        material_rows = image_rows or '<tr><td colspan="6">没有图片元数据。</td></tr>'
        style_status = _esc(style.get('status'))
        layered_note = _esc(layered.get('note'))
        risk_hits_text = _esc('、'.join(guard.get('risk_hits') or []) or '无')
        risk_level = _esc(guard.get('risk_level'))

        return f"""
{status_html}
<div class="note"><strong>先看边界</strong><ul>{warnings_html}</ul></div>

<h3>6.1 主图与卖点方向</h3>
<div class="grid-2">{selling_block}</div>
<p class="sub">场景提示：{scene_hint}</p>
<ul>{ratios}{headlines}</ul>

<h3>6.2 详情页 8 段</h3>
<table><thead><tr><th>#</th><th>段落</th><th>怎么写</th></tr></thead><tbody>{detail_rows}</tbody></table>

<h3>6.3 15 秒短视频分镜</h3>
<table><thead><tr><th>时间</th><th>镜头</th><th>口播</th><th>字幕</th></tr></thead><tbody>{beats_rows}</tbody></table>

<h3>6.4 英文本地化清单</h3>
<table><thead><tr><th>语言</th><th>状态</th><th>要翻的字段</th></tr></thead><tbody>{lang_rows}</tbody></table>
<ul>{glossary}</ul>
<ul>{checklist}</ul>

<h3>6.5 素材索引</h3>
<p class="sub">共 {material_total} 张，来自 {material_notes} 篇笔记；置信度 {material_confidence}。{material_hint}</p>
<table><thead><tr><th>笔记</th><th>方向</th><th>比例</th><th>尺寸</th><th>互动量</th><th>链接</th></tr></thead><tbody>{material_rows}</tbody></table>

<h3>6.6 风格卡</h3>
<p class="sub">状态：{style_status}；{style_layout}</p>
<p>{tags or '<span class="sub">样本没有标签。</span>'}</p>
<ul>{style_limits}</ul>

<h3>6.7 分层卡片结构（不生成图片）</h3>
<p class="sub">{layered_note}</p>
<details><summary>展开 JSON</summary><pre>{_esc(layers_json)}</pre></details>

<h3>6.8 宣称边界</h3>
<p class="sub">可引用的用户原话只证明问题存在，不证明产品功效；风险词命中：{risk_hits_text}（{risk_level}）</p>
<ul>{allowed or '<li>没有可引用的用户原话。</li>'}</ul>
<strong>必须由产品方确认</strong><ul>{confirm}</ul>
<p class="sub">禁用词（节选）：{forbidden}</p>
"""

    def _topics_html(self, topics: List[Dict[str, Any]], risk_hits: List[str]) -> str:
        if not topics:
            return '<p class="sub">没有足够证据生成选题。</p>'
        blocks = []
        for topic in topics:
            titles = "".join(f"<li>{_esc(title)}</li>" for title in topic.get("titles") or [])
            sections = "".join(f"<li>{_esc(section.lstrip('# '))}</li>" for section in topic.get("sections") or [])
            tags = " ".join(f"#{_esc(tag)}" for tag in topic.get("tags") or [])
            risk = topic.get("risk") or {}
            risk_words = "、".join(risk.get("words") or []) or "无"
            blocks.append(f"""
<div class="topic">
  <h3>{_esc(topic.get('template_name'))} · 面向{_esc(topic.get('audience'))}</h3>
  <div class="sub">痛点：{_esc(topic.get('pain_statement'))} · 角度：{_esc(topic.get('angle'))}</div>
  <ol class="titles">{titles}</ol>
  <div class="cover">{' / '.join(_esc(line) for line in topic.get('cover') or [])}</div>
  <ul class="secs">{sections}</ul>
  <div class="sub">{tags}</div>
  <div class="sub">风险词：<span class="risk-{_esc(risk.get('level', '低'))}">{_esc(risk_words)}</span> · 依据：{_link(topic.get('source_url'), '原帖')}</div>
</div>""")
        summary = f'<p class="note">共 {len(topics)} 个选题，整体风险词：{_esc("、".join(risk_hits) or "未命中")}。命中不等于违规，发布前按上下文人工确认。</p>'
        return "".join(blocks) + summary
