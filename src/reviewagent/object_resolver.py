# -*- coding: utf-8 -*-
"""对象识别：把用户粘贴的链接 / 商品名变成一个可核对的商品对象。

设计约束
--------
1. 只使用公开页面，不登录、不求解风控、不伪造 Cookie。
2. 能解析多少写多少；解析不到就返回明确缺口，不用相似商品或模型记忆补全。
3. 京东移动商品页的 window._itemOnly 是本阶段唯一稳定的结构化来源。
4. 淘宝 / 天猫 / 小红书只识别链接和平台，不假装拿到了商品详情。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import requests

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
HTTP_TIMEOUT = 12
MAX_HTML_BYTES = 3_000_000

JD_HOSTS = {"item.jd.com", "item.m.jd.com", "u.jd.com", "3.cn", "jd.com", "www.jd.com"}
TMALL_HOSTS = {"detail.tmall.com", "detail.m.tmall.com", "tmall.com", "www.tmall.com", "m.tmall.com"}
TAOBAO_HOSTS = {"item.taobao.com", "item.m.taobao.com", "taobao.com", "www.taobao.com", "m.taobao.com", "m.tb.cn", "e.tb.cn"}
XHS_HOSTS = {"www.xiaohongshu.com", "xiaohongshu.com", "xhslink.com", "www.xhslink.com", "xhslink.cn", "www.xhslink.cn"}

PLATFORM_LABELS = {
    "jd": "京东",
    "tmall": "天猫",
    "taobao": "淘宝",
    "xhs": "小红书",
    "unknown": "未识别平台",
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def extract_url(text: str) -> str:
    """从一段分享文案里取出第一个 http(s) 链接。"""
    match = re.search(r"https?://[^\s<>\"']+", text or "")
    if not match:
        return ""
    return match.group(0).rstrip("，。；、）】》>”’.,;)")


def detect_platform(url: str) -> str:
    host = _host(url)
    if not host:
        return "unknown"
    if host in JD_HOSTS or host.endswith(".jd.com"):
        return "jd"
    if host in TMALL_HOSTS or host.endswith(".tmall.com"):
        return "tmall"
    if host in TAOBAO_HOSTS or host.endswith(".taobao.com"):
        return "taobao"
    if host in XHS_HOSTS or host.endswith(".xiaohongshu.com"):
        return "xhs"
    return "unknown"


def _platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)


def _request(url: str, *, allow_redirects: bool = True) -> requests.Response:
    from urllib.parse import urljoin
    for redirect in range(5):
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        allowed = host in {"3.cn", "m.tb.cn", "e.tb.cn", "xhslink.com", "www.xhslink.com", "xhslink.cn", "www.xhslink.cn"} or any(host == domain or host.endswith("." + domain) for domain in ("jd.com", "tmall.com", "taobao.com", "xiaohongshu.com"))
        if parsed.scheme not in {"http", "https"} or not allowed or parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            raise requests.RequestException("商品来源地址不受支持")
        response = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=HTTP_TIMEOUT, allow_redirects=False, stream=True)
        if allow_redirects and response.is_redirect:
            target = response.headers.get("Location", "")
            response.close()
            if redirect == 4 or not target:
                raise requests.RequestException("商品链接重定向次数过多")
            url = urljoin(url, target)
            continue
        try:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_HTML_BYTES:
                    raise requests.RequestException("商品页面超过读取上限")
                chunks.append(chunk)
            response._content = b"".join(chunks)
            response._content_consumed = True
            response.encoding = "utf-8"
            return response
        finally:
            response.close()
    raise requests.RequestException("商品链接无法展开")


def _taobao_item_id_from_html(html: str) -> Tuple[str, str]:
    """只从可信字段取淘宝/天猫商品 ID：规范链接、item.htm?id= 链接、itemId/auctionId 字段。

    返回 (item_id, host)；host 为空表示 HTML 没有给出明确的主机。
    """
    text = html or ""
    # 可信度从高到低：canonical → 内嵌 itemId/auctionId → itemId 参数 → item.htm 链接。
    # 页面正文里的推荐商品链接排在最后，避免把别人的商品 ID 当成本商品。
    match = re.search(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\'][^"\']*?[?&]id=(\d{6,})', text, re.I)
    if match:
        return match.group(1), ""
    match = re.search(r'"(?:itemId|auctionId)"\s*:\s*"?(\d{6,})"?', text)
    if match:
        return match.group(1), ""
    match = re.search(r'(?:itemId|auctionNumId)=(\d{6,})', text)
    if match:
        return match.group(1), ""
    match = re.search(r'//(detail\.tmall\.com|item\.taobao\.com)/item\.htm\?[^"\'\s<>]*?[?&]id=(\d{6,})', text)
    if match:
        return match.group(2), match.group(1)
    return "", ""


def _canonical_taobao_url(item_id: str, host: str, platform: str, final_url: str) -> str:
    final_host = _host(final_url)
    host = host or ("detail.tmall.com" if platform == "tmall" or final_host.startswith("detail.tmall") or "tmall" in final_url else "item.taobao.com")
    return f"https://{host}/item.htm?id={item_id}"


def _unwrap_short_url(url: str, platform: str) -> Tuple[str, List[str]]:
    """展开京东 / 淘宝短链；失败时保留原链接并记录 warning。"""
    warnings: List[str] = []
    host = _host(url)
    if host not in {"u.jd.com", "3.cn", "m.tb.cn", "e.tb.cn", "xhslink.com", "www.xhslink.com", "xhslink.cn", "www.xhslink.cn"}:
        return url, warnings
    try:
        response = _request(url)
        final = response.url or url
        html = ""
        if platform in {"taobao", "tmall"}:
            html = getattr(response, "text", None)
            if html is None:
                content = getattr(response, "content", b"") or b""
                html = content.decode("utf-8", "replace") if isinstance(content, bytes) else str(content or "")
        stable_id, item_host = _taobao_item_id_from_html(html) if html else ("", "")
        reachable = (final != url and detect_platform(final) in {"jd", "taobao", "tmall", "xhs"}
                     and not _host(final).startswith(("login.", "passport."))
                     and not any(word in urlparse(final).path.lower() for word in ("login", "passport", "captcha", "verify")))
        if reachable:
            if platform in {"taobao", "tmall"} and not _tmall_or_taobao_id(final):
                if stable_id:
                    warnings.append("短链最终地址不带商品 ID，已按页面可信字段重建规范采集入口。")
                    return _canonical_taobao_url(stable_id, item_host, platform, final), warnings
                # 最终地址只剩移动端一次性参数时，保留原始短链，避免把分享参数当采集入口。
                warnings.append("短链最终地址不含商品 ID；保留原始短链，采集时再解析。")
                return url, warnings
            return final, warnings
        if platform in {"taobao", "tmall"} and stable_id and final == url:
            warnings.append("短链最终地址不带商品 ID，已按页面可信字段重建规范采集入口。")
            return _canonical_taobao_url(stable_id, item_host, platform, final), warnings
        warnings.append("短链接没有跳转到商品页，可能已失效。")
    except requests.RequestException as exc:
        warnings.append(f"短链接展开失败：{exc.__class__.__name__}。")
    return url, warnings


def _jd_sku(url: str) -> str:
    patterns = (
        r"item\.m\.jd\.com/product/(\d+)",
        r"item\.jd\.com/(\d+)\.html",
        r"item\.jd\.com/product/(\d+)",
        r"[?&]sku(?:Id)?=(\d+)",
        r"jd\.com/(\d+)\.html",
    )
    for pattern in patterns:
        match = re.search(pattern, url, re.I)
        if match:
            return match.group(1)
    return ""


def _tmall_or_taobao_id(url: str) -> str:
    for pattern in (r"[?&](?:id|itemId)=(\d+)", r"/(\d{6,})\.html?"):
        match = re.search(pattern, url, re.I)
        if match:
            return match.group(1)
    return ""


def _xhs_note_id(url: str) -> str:
    for pattern in (r"/explore/([0-9a-fA-F]{16,32})", r"/discovery/item/([0-9a-fA-F]{16,32})", r"/item/([0-9a-fA-F]{16,32})"):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def _extract_json_assignment(html: str, variable: str) -> Optional[Dict[str, Any]]:
    """读取 window.xxx = ({...}); 形式的 JSON 赋值。"""
    pattern = rf"window\.{re.escape(variable)}\s*=\s*\((.*?)\);\s*window\._isLogin"
    match = re.search(pattern, html, re.S)
    if not match:
        pattern = rf"window\.{re.escape(variable)}\s*=\s*\((.*?)\);\s*</script>"
        match = re.search(pattern, html, re.S)
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _json_string_field(html: str, field: str) -> str:
    """从页面内嵌 JSON 片段里取一个字符串字段，避免整体解析被污染的 JSON。"""
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"', html)
    if not match:
        return ""
    raw = match.group(1)
    try:
        return _clean_text(json.loads(f'"{raw}"'))
    except (ValueError, TypeError):
        return _clean_text(raw)


def _image_url(path: str) -> str:
    path = _clean_text(path)
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return "https://img14.360buyimg.com/n1/" + path.lstrip("/")


def _variant_title(primary_title: str, color: str, size: str) -> str:
    parts = [part for part in (color, size) if part and part.strip()]
    if not parts:
        return primary_title
    return f"{primary_title} · " + " / ".join(parts)


def _jd_variants(item: Dict[str, Any], primary_sku: str, primary_title: str) -> List[Dict[str, Any]]:
    variants: List[Dict[str, Any]] = []
    seen: set = set()
    for entry in item.get("newColorSize") or []:
        if not isinstance(entry, dict):
            continue
        sku = _clean_text(entry.get("skuId"))
        if not sku or sku in seen:
            continue
        seen.add(sku)
        color = _clean_text(entry.get("color") or entry.get("1"))
        size = _clean_text(entry.get("size") or entry.get("2"))
        variants.append(
            {
                "sku_id": sku,
                "color": color,
                "size": size,
                "title": _variant_title(primary_title, color, size),
                "url": f"https://item.jd.com/{sku}.html",
                "image_url": _image_url(entry.get("imagePath") or ""),
                "is_primary": sku == primary_sku,
            }
        )
    return variants


def _metadata_score(object_data: Dict[str, Any]) -> int:
    checks = [
        (bool(object_data.get("title")), 30),
        (bool(object_data.get("brand")), 15),
        (bool(object_data.get("platform_id")), 15),
        (bool(object_data.get("shop")), 10),
        (bool(object_data.get("image_url")), 10),
        (bool(object_data.get("variants")), 10),
        (bool(object_data.get("category")), 10),
    ]
    return sum(weight for ok, weight in checks if ok)


def _confidence(object_data: Dict[str, Any], status: str) -> Tuple[float, str]:
    if status == "resolved":
        score = 0.78
        if object_data.get("brand"):
            score += 0.08
        if object_data.get("shop"):
            score += 0.04
        if object_data.get("variants"):
            score += 0.05
        score = min(score, 0.97)
    elif status == "partial":
        score = 0.45 if object_data.get("title") else 0.35
    else:
        score = 0.15
    label = "高" if score >= 0.8 else "中" if score >= 0.55 else "低"
    return round(score, 2), label


def _base_object(input_text: str, input_type: str, platform: str) -> Dict[str, Any]:
    return {
        "input": input_text,
        "input_type": input_type,
        "platform": platform,
        "platform_label": _platform_label(platform),
        "status": "needs_link",
        "status_label": "需要补充链接",
        "platform_id": "",
        "url": extract_url(input_text),
        "title": "",
        "brand": "",
        "shop": "",
        "category": [],
        "image_url": "",
        "variants": [],
        "metadata_score": 0,
        "confidence": 0.15,
        "confidence_label": "低",
        "parser": "none",
        "fetched_at": _now(),
        "evidence": [],
        "gaps": [],
        "warnings": [],
        "next_actions": [],
    }


def _gap(code: str, label: str, detail: str, severity: str = "medium") -> Dict[str, str]:
    return {"code": code, "label": label, "detail": detail, "severity": severity}


def _finalize(object_data: Dict[str, Any]) -> Dict[str, Any]:
    object_data["metadata_score"] = _metadata_score(object_data)
    object_data["confidence"], object_data["confidence_label"] = _confidence(object_data, object_data["status"])
    if object_data.get("title"):
        object_data["evidence"].insert(
            0,
            {
                "id": "ev-object",
                "type": "product_page",
                "title": "商品页标题与结构化字段",
                "url": object_data.get("url", ""),
                "quote": object_data["title"],
                "fields": ["title", "brand", "shop", "variants", "category"],
                "fetched_at": object_data.get("fetched_at", ""),
            },
        )
    return object_data


def _search_urls(keyword: str) -> List[Dict[str, str]]:
    q = quote(keyword)
    return [
        {"platform": "京东", "url": f"https://search.jd.com/Search?keyword={q}"},
        {"platform": "淘宝 / 天猫", "url": f"https://list.tmall.com/search_product.htm?q={q}"},
        {"platform": "小红书", "url": f"https://www.xiaohongshu.com/search_result?keyword={q}"},
    ]


def _resolve_keyword(text: str) -> Dict[str, Any]:
    data = _base_object(text, "keyword", "unknown")
    data["status"] = "needs_link"
    data["status_label"] = "未解析：需要商品链接"
    data["gaps"].append(
        _gap(
            "keyword_no_search",
            "没有可用的商品搜索通道",
            "当前版本不把搜索引擎结果当成商品；纯商品名无法确认具体 SKU、店铺和规格。",
            "high",
        )
    )
    data["next_actions"].append(
        {
            "label": "粘贴京东 / 淘宝 / 天猫 / 小红书商品链接",
            "detail": "链接里的商品 ID 能唯一确定对象；纯名称会先进入待确认状态。",
        }
    )
    data["search_urls"] = _search_urls(text)
    data["message"] = "已记录商品名，但没有可核对的商品链接。请补一个商品链接，或直接粘贴真实评论样本。"
    return _finalize(data)


def _resolve_jd(url: str) -> Dict[str, Any]:
    data = _base_object(url, "url", "jd")
    sku = _jd_sku(url)
    if not sku:
        data["status"] = "needs_link"
        data["status_label"] = "未解析：链接里没有商品 ID"
        data["gaps"].append(_gap("jd_no_sku", "无法从链接取商品 ID", "请使用 item.jd.com/<数字>.html 或 item.m.jd.com/product/<数字>.html。", "high"))
        data["message"] = "这个京东链接里没有可识别的商品 ID。"
        return _finalize(data)

    data["platform_id"] = sku
    data["url"] = f"https://item.jd.com/{sku}.html"
    mobile_url = f"https://item.m.jd.com/product/{sku}.html"
    data["parser"] = "jd_item_only"
    try:
        response = _request(mobile_url)
    except requests.RequestException as exc:
        data["status"] = "needs_capture"
        data["status_label"] = "解析失败：无法访问商品页"
        data["gaps"].append(_gap("jd_network", "京东商品页不可达", f"{exc.__class__.__name__}: {exc}", "high"))
        data["message"] = "暂时无法访问京东商品页，请稍后重试或直接粘贴评论样本。"
        return _finalize(data)

    if response.status_code != 200:
        data["status"] = "needs_capture"
        data["status_label"] = f"解析失败：HTTP {response.status_code}"
        data["gaps"].append(_gap("jd_http", "京东商品页返回异常", f"HTTP {response.status_code}，页面没有返回商品信息。", "high"))
        data["message"] = "京东商品页没有正常返回，可能触发了访问限制。"
        return _finalize(data)

    html = response.text[:MAX_HTML_BYTES]
    if "window._itemOnly" not in html:
        data["status"] = "needs_capture"
        data["status_label"] = "解析失败：页面结构变化"
        data["gaps"].append(_gap("jd_layout", "没有找到 _itemOnly 数据", "页面可能改版或返回了验证页，当前解析器读不到商品字段。", "high"))
        data["message"] = "页面已打开，但没有找到可解析的商品数据。"
        return _finalize(data)

    payload = _extract_json_assignment(html, "_itemOnly")
    item = (payload or {}).get("item") if isinstance(payload, dict) else None
    if not isinstance(item, dict):
        data["status"] = "needs_capture"
        data["status_label"] = "解析失败：商品数据不完整"
        data["gaps"].append(_gap("jd_json", "_itemOnly 不是有效 JSON", "页面内嵌数据可能被截断，当前解析器无法恢复。", "high"))
        data["message"] = "商品页已返回，但内嵌数据无法解析。"
        return _finalize(data)

    title = _clean_text(item.get("skuName"))
    brand = _clean_text(item.get("brandName"))
    shop = _json_string_field(html, "shopName")
    category = [_clean_text(part) for part in (item.get("category") or []) if _clean_text(part)]
    image_list = item.get("image") or []
    image_url = _image_url(image_list[0]) if isinstance(image_list, list) and image_list else ""
    variants = _jd_variants(item, sku, title or f"京东商品 {sku}")

    data.update(
        {
            "title": title or f"京东商品 {sku}",
            "brand": brand,
            "shop": shop,
            "category": category,
            "image_url": image_url,
            "variants": variants,
            "status": "resolved" if title else "partial",
            "status_label": "已解析商品对象" if title else "只解析到商品 ID",
        }
    )
    data["raw_fields"] = {
        "sku_id": sku,
        "brand_id": _clean_text(item.get("brandId")),
        "vender_id": _clean_text(item.get("venderID")),
        "ware_status": _clean_text(item.get("warestatus")),
        "category_ids": category,
        "variant_count": len(variants),
    }
    if not title:
        data["gaps"].append(_gap("jd_title", "没有商品标题", "只能确认商品 ID，无法核对标题与规格。", "high"))
    if not brand:
        data["gaps"].append(_gap("jd_brand", "没有品牌字段", "商品页没有返回品牌，后续同款匹配只能依赖标题和规格。", "medium"))
    if not shop:
        data["gaps"].append(_gap("jd_shop", "没有店铺字段", "页面内嵌 shopName 缺失，无法核对售卖店铺。", "medium"))
    if not variants:
        data["gaps"].append(_gap("jd_variants", "没有规格数据", "无法列出同 SPU 的其他规格。", "medium"))
    data["gaps"].append(
        _gap(
            "jd_reviews_unavailable",
            "没有评论正文",
            "商品页只返回商品与规格；当前版本没有登录态，评论接口需要平台风控签名，未抓取评论。",
            "high",
        )
    )
    data["message"] = (
        f"已从京东商品页解析到标题、品牌、店铺和 {len(variants)} 个规格；"
        "评论正文尚未采集，报告会先给出对象与同款匹配骨架。"
    )
    return _finalize(data)


def _resolve_unsupported_url(url: str, platform: str) -> Dict[str, Any]:
    data = _base_object(url, "url", platform)
    platform_id = _tmall_or_taobao_id(url) if platform in {"tmall", "taobao"} else _xhs_note_id(url)
    data["platform_id"] = platform_id
    data["status"] = "needs_capture"
    data["status_label"] = "已识别链接，详情需采集"
    data["gaps"].append(
        _gap(
            f"{platform}_auth",
            f"{_platform_label(platform)}页面需要登录或风控校验",
            "当前阶段只做无登录对象解析；该平台的商品/笔记正文没有稳定公开接口，不在本阶段猜测。",
            "high",
        )
    )
    if platform_id:
        data["warnings"].append(f"已从链接中提取 ID：{platform_id}，但没有拿到标题和规格，不能据此推断商品。")
    else:
        data["warnings"].append("链接中没有提取到稳定 ID，可能是短链或分享页。")
    data["next_actions"].append({"label": "粘贴评论样本", "detail": "有真实评论后仍可生成口碑诊断与痛点报告。"})
    data["message"] = f"已识别为{_platform_label(platform)}链接；本阶段不登录，商品详情与评论留待采集。"
    return _finalize(data)


def resolve_object(text: str) -> Dict[str, Any]:
    """解析一段输入（链接、分享文案或商品名），返回可序列化的对象描述。

    永不抛网络异常：所有失败都变成 status / gaps / message。
    """
    raw = _clean_text(text)
    if not raw:
        data = _base_object("", "empty", "unknown")
        data["status"] = "needs_link"
        data["status_label"] = "没有输入"
        data["message"] = "请粘贴商品链接或输入商品名。"
        return _finalize(data)

    url = extract_url(raw)
    if not url:
        return _resolve_keyword(raw)

    input_url = url
    platform = detect_platform(url)
    url, short_warnings = _unwrap_short_url(url, platform)
    platform = detect_platform(url) if detect_platform(url) != "unknown" else platform
    if platform == "jd":
        data = _resolve_jd(url)
    elif platform in {"tmall", "taobao"}:
        data = _resolve_unsupported_url(url, platform)
    elif platform == "xhs":
        data = _resolve_unsupported_url(url, platform)
    else:
        data = _base_object(raw, "url", "unknown")
        data["url"] = url
        data["status"] = "needs_link"
        data["status_label"] = "未支持的链接"
        data["gaps"].append(_gap("unsupported_host", "不支持的平台", "当前只识别京东、淘宝/天猫、小红书链接。", "high"))
        data["message"] = "这个链接不属于当前支持的平台。"
    data["input_url"] = input_url
    data["warnings"] = short_warnings + list(data.get("warnings") or [])
    return data
