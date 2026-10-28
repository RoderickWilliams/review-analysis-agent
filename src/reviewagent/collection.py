"""Bounded, opt-in acquisition using existing adapters and public search pages."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from urllib.parse import urljoin

from reviewagent.review_data import normalize_reviews

TIERS = {"light": (2, 30, 5), "standard": (5, 300, 20), "deep": (10, 500, 50)}

FAILURE_GUIDANCE = {
    "identity_verification": ("淘宝身份校验尚未完成", "在专用窗口核对平台提示；当前没有二维码，不要反复重新登录"),
    "identity_verification_timeout": ("淘宝账号状态检测超时", "暂停该平台，先确认正常浏览器能否完成官方身份校验，不连续重试"),
    "login_redirect_loop": ("登录操作后商品仍被重定向至登录页", "暂停当前平台，在专用窗口核对身份验证与商品访问权限，避免重复扫码"),
    "account_restricted": ("平台提示账号异常或限制", "暂停该平台，在平台官方页面核对账号状态，不连续重试"),
    "platform_busy": ("该平台已有采集任务", "等待现有任务结束后再手动采集"),
    "platform_paused": ("本轮该平台已暂停", "查看前一条来源的失败原因，人工确认后再决定是否重试"),
    "browser_closed": ("专用浏览器连接已关闭", "需要继续时手动重新启动，已保存原文和断点"),
    "source_unavailable": ("平台提示商品或笔记不可访问", "核对链接是否失效、下架、删除或仅特定账号可见"),
    "response_too_large": ("评论接口响应超过安全读取上限", "减少单次数据规模或检查平台响应"),
    "needs_login": ("平台要求重新登录", "在专用窗口重新扫码后重试"),
    "login_timeout": ("等待扫码登录超时", "重新打开登录窗口并在提示时间内完成扫码"),
    "login_cancelled": ("登录已取消或窗口已关闭", "需要时重新连接该平台"),
    "verification_required": ("平台要求人工验证", "在专用窗口手动完成验证码后重试"),
    "rate_limited": ("平台提示访问频繁或访问受限", "暂停该平台，稍后重试，保留其他平台结果"),
    "invalid_source": ("链接不属于所选平台的受支持地址", "核对平台并粘贴正确商品链接"),
    "unsupported_redirect": ("链接跳转到不支持的页面", "打开分享链接，复制商品详情页链接后重试"),
    "blank_page": ("浏览器仍停留在空白新标签页", "重新打开该商品；若仍失败，查看导航失败原因，不进入评论采集"),
    "comment_section_not_loaded": ("等待后评价区域仍未加载完成", "检查商品页资源加载、登录或平台提示；本次未能判断实际评论数量"),
    "degraded_page": ("平台只返回了精简商品页，评价模块未下发", "多为平台对高频访问的限流；暂停该平台一段时间后重试，或改用正常浏览器核对页面"),
    "navigation_failed": ("浏览器没有进入商品页", "重新打开该商品，并根据专用窗口或失败原因检查网络与链接"),
    "navigation_dns_failed": ("浏览器无法解析商品页域名", "检查本机 DNS 与网络后再重试"),
    "navigation_proxy_failed": ("浏览器连接被代理设置阻断", "检查系统或安全软件的代理设置；专用窗口本身使用直连"),
    "navigation_connection_failed": ("浏览器与商品页的连接未能建立", "确认网络可访问该平台后再重试"),
    "navigation_aborted": ("浏览器中止了商品页导航", "重新打开该商品；若平台弹出身份校验，先完成校验"),
    "navigation_timeout": ("浏览器等待商品页响应超时", "检查网络或平台页面状态后再重试"),
    "disabled": ("平台采集未开启", "开启平台采集后重试"),
    "cancelled": ("任务已取消", "已取得的数据保留，可稍后继续"),
    "BrowserUnavailable": ("默认浏览器无法连接或暂不受支持", "配置受支持的 Chrome、Edge 或 Firefox 默认浏览器"),
    "BrowserProfileBusy": ("该平台专用浏览器配置正在使用", "等待该平台任务结束后重试"),
    "TimeoutException": ("浏览器等待页面响应超时", "检查网络，稍后重新打开该商品"),
    "TimeoutError": ("页面请求超时", "检查网络后重试"),
    "no_review_text": ("未读取到评论正文，具体原因尚未确定", "核对商品页是否显示评论，或重试、换链接、导入补充"),
    "unknown": ("采集过程未完成，具体原因尚未确定", "检查专用浏览器提示，重试或更换链接"),
}


def failure_detail(code, message=None):
    reason, action = FAILURE_GUIDANCE.get(code, FAILURE_GUIDANCE["unknown"])
    return {"code": code, "reason": reason, "message": message or reason, "suggested_action": action,
            "reason_confirmed": code in FAILURE_GUIDANCE and code not in {"unknown", "no_review_text"}}


def normalize_scope(request):
    """A source is a platform, independent of how many product links it has."""
    tier = request.get("tier", "standard")
    maximum = 2 if tier == "light" else 3
    platforms = request.get("platforms", ["jd", "taobao"] if tier == "light" else ["jd", "taobao", "xhs"])
    if not isinstance(platforms, list) or any(p not in {"jd", "taobao", "xhs"} for p in platforms):
        raise ValueError("来源平台仅支持京东、淘宝/天猫和小红书")
    if len(set(platforms)) != len(platforms) or len(platforms) > maximum:
        raise ValueError(f"此档位最多 {maximum} 个平台来源；选择小红书前请先取消一个已选平台")
    request["platforms"] = platforms
    return request


def limits(request):
    if request.get("tier") == "custom":
        return min(20, request.get("candidate_limit", 5)), min(500, request.get("per_product_limit", 300)), 20
    return TIERS.get(request.get("tier"), TIERS["standard"])


def select_window(reviews, months, limit):
    today = date.today()
    month_index = today.year * 12 + today.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    cutoff = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
    recent, older, unknown = [], [], []
    for review in reviews:
        value = review.get("review_date")
        if not value:
            unknown.append(review)
            continue
        try:
            published = datetime.fromisoformat(str(value).replace("Z", "+00:00").replace("/", "-")).date()
        except ValueError:
            unknown.append(review)
            continue
        (recent if published >= cutoff else older).append(review)
    key = lambda r: str(r.get("review_date") or "")
    recent.sort(key=key, reverse=True)
    older.sort(key=key, reverse=True)
    selected = recent[:limit]
    supplement = older[:max(0, limit - len(selected))]
    selected.extend(supplement)
    selected.extend(unknown[:max(0, limit - len(selected))])
    return selected, {"window_start": cutoff.isoformat(), "supplemented_older": len(supplement),
                      "unknown_dates": sum(not r.get("review_date") for r in selected),
                      "oldest_known_date": min((r["review_date"] for r in selected if r.get("review_date")), default=None)}


def _sources(analysis):
    request = analysis.get("request") or {}
    maximum, _, _ = limits(request)
    selected_urls = request.get("selected_urls")
    if selected_urls is not None:
        maximum = len(selected_urls)
    sources = [analysis["object"]] + list(analysis.get("candidates", []))
    platforms = request.get("platforms", ["jd", "taobao", "xhs"])
    buckets = {platform: [] for platform in platforms}
    seen = set()
    for source in sources:
        if source.get("platform") in {None, "", "unknown"}:
            from reviewagent.object_resolver import detect_platform, PLATFORM_LABELS
            detected = detect_platform(source.get("url") or source.get("source_url") or "")
            if detected != "unknown":
                source.update(platform=detected, platform_label=PLATFORM_LABELS[detected], status="needs_capture", status_label="已识别链接，等待采集")
                source["gaps"] = [gap for gap in source.get("gaps", []) if gap.get("code") != "unsupported_host"]
        platform = "taobao" if source.get("platform") == "tmall" and "taobao" in platforms else source.get("platform")
        url = source.get("url") or source.get("source_url")
        if selected_urls is not None and url not in selected_urls and source.get("input_url") not in selected_urls:
            continue
        if platform in buckets and url and (platform, url) not in seen:
            buckets[platform].append(source)
            seen.add((platform, url))
    selected = []
    while len(selected) < maximum and any(buckets.values()):
        for bucket in buckets.values():
            if bucket and len(selected) < maximum:
                selected.append(bucket.pop(0))
    return selected


def collect_into_analysis(analysis, cancelled, *, on_checkpoint=None, on_state=None):
    from reviewagent.browser_collection import collect_source, CollectionPaused

    request = analysis.get("request") or {}
    _, per_product, _ = limits(request)
    sources = _sources(analysis)
    if not sources:
        raise ValueError("没有可采集的商品链接，请先确认对象或补充来源链接")
    combined = list(analysis.get("reviews", []))
    previous_count = len(combined)
    known = {(r.get("platform"), r.get("source_url"), r.get("comment_id") or r.get("review_id")) for r in combined}
    old_collection = analysis.get("collection") or {}
    settings_key = [request.get("window_months", 12), per_product]
    previous = {item.get("url"): item for item in old_collection.get("sources", [])} if old_collection.get("settings_key") == settings_key else {}
    sampling, gaps = [], []
    paused_platforms = {}

    def checkpoint():
        analysis["reviews"] = combined
        analysis.setdefault("request", {})["reviews"] = combined
        analysis["collection"] = {"sources": sampling, "gaps": gaps, "new_reviews": len(combined) - previous_count,
                                  "total_limit": 5000, "settings_key": settings_key,
                                  "resume_method": "completed_sources_skipped_current_source_reloaded_and_deduplicated"}
        platform_summary = []
        for platform in request.get("platforms", ["jd", "taobao", "xhs"]):
            family = lambda value: "taobao" if value == "tmall" else value
            selected_sources = [s for s in sources if family(s.get("platform")) == platform]
            if not selected_sources:
                continue
            actual = sum(family(r.get("platform")) == platform and r.get("source_url") in {s.get("url") or s.get("source_url") for s in selected_sources} for r in combined)
            target = len(selected_sources) * per_product
            platform_summary.append({"platform": platform, "product_count": len(selected_sources), "actual_count": actual,
                                     "target_count": target, "shortfall": max(0, target - actual),
                                     "failures": [dict(g) for g in gaps if family(g.get("platform")) == platform]})
        analysis["collection"]["platform_summary"] = platform_summary
        analysis["collection"]["failure_policy"] = "analyze_available_reviews_with_explicit_gaps"
        if on_checkpoint:
            on_checkpoint(analysis)

    for source in sources:
        if cancelled() or len(combined) >= 5000:
            break
        url = source.get("url") or source.get("source_url") or ""
        if not url:
            continue
        family = "taobao" if source.get("platform") == "tmall" else source.get("platform")
        if family in paused_platforms:
            detail = failure_detail("platform_paused")
            detail["message"] = "此前来源触发 " + paused_platforms[family] + "，为保护账号，本条未请求"
            sampling.append({"url": url, "platform": source.get("platform"), "status": "platform_paused", "received": 0, "selected": 0, "target": per_product, **detail})
            gaps.append({"platform": source.get("platform"), "url": url, **detail})
            checkpoint()
            continue
        saved = previous.get(url)
        if saved and saved.get("status") == "completed":
            sampling.append(dict(saved))
            continue
        item = {"url": url, "platform": source.get("platform"), "status": "collecting", "received": 0, "selected": 0, "target": per_product}
        sampling.append(item)

        def accept_batch(raw):
            prepared = []
            for review in raw:
                review = dict(review)
                review.setdefault("source_url", url)
                review.setdefault("source_platform", source.get("platform", ""))
                prepared.append(review)
            normalized = normalize_reviews(prepared, strict=False)
            chosen, window = select_window(normalized, request.get("window_months", 12), per_product)
            for review in chosen:
                key = (review.get("platform"), review.get("source_url"), review.get("comment_id") or review.get("review_id"))
                if key not in known and len(combined) < 5000:
                    combined.append(review)
                    known.add(key)
            item.update(received=len(raw), invalid=len(raw) - len(normalized), selected=len(chosen), **window)
            checkpoint()

        checkpoint()
        try:
            def accept_metadata(metadata):
                source.update(metadata)
                displayed = metadata.get('displayed_review_count')
                if isinstance(displayed, int) and not isinstance(displayed, bool) and displayed > 0:
                    item['displayed_total'] = displayed
                    item['target'] = min(per_product, displayed)
                    item['requested_limit'] = per_product
                checkpoint()
            raw = collect_source(source, per_product, cancelled, on_state=on_state, on_batch=accept_batch, on_metadata=accept_metadata)
            facts = getattr(raw, 'facts', None) or {}
            accept_batch(raw)
            item["status"] = "cancelled" if cancelled() else "completed" if item["selected"] >= item['target'] else "partial" if item["selected"] else "needs_input"
            if not raw:
                detail = failure_detail("no_review_text")
                item.update(detail)
                gaps.append({"platform": source.get("platform"), "url": url, **detail})
            elif item["selected"] < item['target'] and not cancelled():
                invalid = item.get("invalid", 0)
                message = f"采集上限 {per_product} 条，当前核对目标 {item['target']} 条，本次读取 {len(raw)} 条，其中有效选入 {item['selected']} 条。"
                if invalid:
                    message += f"有 {invalid} 条未通过字段校验。"
                if facts.get('rating_only'):
                    message += ("另有 %s 条评价只有星级、没有买家正文，未作为文本证据计入；"
                                "已通过页面评论接口补取折叠评价。" % facts['rating_only'])
                    reason, confirmed = "部分评价只有星级，没有可分析正文", True
                elif facts.get('rate_api') == 'ok':
                    message += "已通过页面评论接口补取被折叠的评价，仍未采满的部分缺少可分析正文。"
                    reason, confirmed = "接口列表已取回，部分条目没有正文", True
                elif facts.get('folded'):
                    message += ("平台把 %s 条评价折叠为“对你帮助不大”，页面只展示其余评价；"
                                "本次已按实际可见内容采集。" % facts['folded'])
                    reason, confirmed = "平台折叠了部分低帮助度评价，当前页面不再展开", True
                elif facts.get('displayed'):
                    message += "页面标注 %s 条评价，未采满部分可能仍未展开。" % facts['displayed']
                    reason, confirmed = "本次未采满目标数量，未采满的具体原因尚未确定", False
                else:
                    message += "未能确认是否还有未加载评论。"
                    reason, confirmed = "本次未采满目标数量，未采满的具体原因尚未确定", False
                suggested = ("直接分析已取得的正文评论即可；其余只有星级，重试也取不到买家正文"
                              if facts.get('rating_only') else "先分析已有真实评论，可稍后重试或补充链接")
                detail = {"code": "insufficient_reviews", "reason": reason, "reason_confirmed": confirmed,
                          "message": message, "suggested_action": suggested}
                item.update(detail)
                gaps.append({"platform": source.get("platform"), "url": url, **detail})
        except CollectionPaused as exc:
            if exc.code in {"account_restricted", "rate_limited", "verification_required", "identity_verification", "identity_verification_timeout", "needs_login", "login_timeout", "login_cancelled", "login_redirect_loop", "browser_closed", "platform_busy", "cancelled"}:
                paused_platforms[family] = exc.code
            item["status"] = exc.code
            detail = failure_detail(exc.code, str(exc))
            item.update(detail)
            gaps.append({"platform": source.get("platform"), "url": url, **detail})
        except Exception as exc:
            item["status"] = "needs_input"
            detail = failure_detail(type(exc).__name__ if type(exc).__name__ in FAILURE_GUIDANCE else "unknown", "采集连接未完成（" + type(exc).__name__ + "）；具体原因尚未确认")
            item.update(detail)
            gaps.append({"platform": source.get("platform"), "url": url, **detail})
        checkpoint()
    if len(combined) > previous_count and analysis.get("enrichment"):
        # Keep edited plans while marking older insights as requiring refresh.
        analysis["enrichment"]["source_changed"] = True
    checkpoint()
    if gaps:
        analysis["collection"]["status"] = "needs_input"
    return analysis


def discover_into_analysis(analysis, cancelled, *, on_checkpoint=None, on_state=None):
    from reviewagent.browser_collection import discover_sources
    from reviewagent.same_product import build_same_products

    request = analysis.get("request") or {}
    platforms = request.get("platforms", ["jd", "taobao", "xhs"])
    if request.get("discovery_platform"):
        platforms = [request["discovery_platform"]]
    if not platforms:
        raise ValueError("请至少选择一个检索平台")
    maximum = request.get("candidate_limit", 5)
    import unicodedata
    query = unicodedata.normalize("NFKC", analysis["object"].get("title") or analysis["input"]).strip().casefold()
    previous = list(analysis.get("candidates", []))
    def accept(candidates, gaps):
        matched = build_same_products(analysis["object"], previous + candidates)
        matched["summary"].update(auto_discovery="owned_browser", auto_discovery_reason="默认浏览器专用会话读取的真实搜索结果；缺失身份字段需确认")
        analysis.update(candidates=matched["candidates"], match_summary=matched["summary"])
        analysis["discovery"] = {"query": query, "resolved": len(candidates), "gaps": list(gaps),
                                  "ranking": "平台轮流保留候选，按身份匹配度排序；未取得销量与价格时不按其排序"}
        if on_checkpoint:
            on_checkpoint(analysis)
    candidates, gaps = discover_sources(query, platforms, maximum, cancelled, on_state=on_state, on_batch=accept)
    accept(candidates, gaps)
    return analysis
