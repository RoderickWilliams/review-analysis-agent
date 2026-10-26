# -*- coding: utf-8 -*-
"""Scrapling 抓取后端（可选）。

Scrapling 把 HTTP 请求、隐身浏览器渲染与自适应解析收敛成一套 API，用来替代
项目里 selenium / DrissionPage / Playwright / Patchright 各自维护的请求与解析管道。
平台特有逻辑不迁移：淘宝 mtop 签名（_m_h5_tk）、京东 club.jd.com JSONP、登录态与
验证码处理仍留在各平台爬虫中，Scrapling 只负责取回 HTML/JSON 和按选择器抽评论。

安装::

    pip install "reviewagent[scrapling]"   # 含 curl_cffi / playwright / patchright 等 fetchers
    pip install scrapling                  # 只要解析，不要浏览器

配置::

    REVIEWAGENT_SCRAPER_BACKEND=scrapling
    REVIEWAGENT_SCRAPLING_SELECTORS=config/scrapling_selectors.json
    REVIEWAGENT_SCRAPLING_MODE=auto        # auto | http | stealth
    REVIEWAGENT_SCRAPLING_TIMEOUT=30

选择器写在 JSON 里（见 config/scrapling_selectors.example.json），站点改版时只改配置，
不动 Python。未安装 fetchers 时 fetch() 抛 ScraplingUnavailable，解析仍可用。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

try:  # 解析只依赖 scrapling 核心，抓取依赖 [fetchers] 额外依赖
    from scrapling import Selector

    SCRAPLING_AVAILABLE = True
except Exception:  # pragma: no cover - 未安装时走降级路径
    Selector = None  # type: ignore[assignment]
    SCRAPLING_AVAILABLE = False


# 触发隐身模式的信号：状态码 + 常见反爬挑战页文案
BLOCKED_STATUS = {401, 403, 407, 429, 503}
CHALLENGE_MARKERS = (
    "just a moment",
    "attention required",
    "cf-chl",
    "verify you are human",
    "checking your browser",
    "验证您是真人",
    "滑动验证",
    "安全验证",
)

RATING_RE = re.compile(r"(\d+(?:\.\d+)?)")


class ScraplingUnavailable(RuntimeError):
    """Scrapling 或它的 fetchers 额外依赖未安装。"""


def available() -> bool:
    """解析能力是否可用（只要求 scrapling 核心包）。"""
    return SCRAPLING_AVAILABLE


def fetchers_available() -> bool:
    """抓取能力是否可用（要求 scrapling[fetchers]）。"""
    if not SCRAPLING_AVAILABLE:
        return False
    try:
        from scrapling.fetchers import Fetcher  # noqa: F401
    except Exception:
        return False
    return True


def _require_parse() -> None:
    if not SCRAPLING_AVAILABLE:
        raise ScraplingUnavailable(
            "Scrapling 未安装。安装：pip install scrapling（或 pip install reviewagent[scrapling]）。"
        )


def _require_fetch() -> None:
    if not fetchers_available():
        raise ScraplingUnavailable(
            "Scrapling 抓取依赖未安装。安装：pip install scrapling[fetchers]（或 pip install reviewagent[scrapling]）；"
            "未下载浏览器时 http 模式可用，stealth 模式需先安装 Chromium。"
        )


@dataclass
class FetchedPage:
    """一次抓取的结果。html 已解码为 str，status 缺失时为 0。"""

    url: str
    status: int
    html: str
    mode: str

    def selector(self):
        """按页面 HTML 建一个 Scrapling 选择器。"""
        return parse(self.html, url=self.url)


# ═══════════════════════════════════════════════════════════════
# 抓取
# ═══════════════════════════════════════════════════════════════
def _response_html(response: Any) -> str:
    html = getattr(response, "html_content", None)
    if html is None:
        body = getattr(response, "body", b"")
        if isinstance(body, (bytes, bytearray)):
            encoding = getattr(response, "encoding", "utf-8") or "utf-8"
            try:
                html = body.decode(encoding, errors="replace")
            except LookupError:
                html = body.decode("utf-8", errors="replace")
        else:
            html = str(body or "")
    return str(html)


def _to_page(response: Any, url: str, mode: str) -> FetchedPage:
    status = getattr(response, "status", 0) or 0
    return FetchedPage(
        url=str(getattr(response, "url", "") or url),
        status=int(status) if isinstance(status, int) else 0,
        html=_response_html(response),
        mode=mode,
    )


def _fetch_http(url: str, timeout: float) -> Any:
    from scrapling.fetchers import Fetcher

    return Fetcher.get(url, timeout=max(1, int(round(timeout))), stealthy_headers=True)


def _fetch_stealth(url: str, timeout: float, wait_selector: Optional[str], headless: bool) -> Any:
    from scrapling.fetchers import StealthyFetcher

    kwargs: Dict[str, Any] = {"headless": headless, "network_idle": True}
    if wait_selector:
        kwargs["wait_selector"] = wait_selector
    return StealthyFetcher.fetch(url, **kwargs)


def _is_blocked(page: FetchedPage) -> bool:
    if page.status in BLOCKED_STATUS:
        return True
    sample = (page.html or "")[:20000].lower()
    return any(marker in sample for marker in CHALLENGE_MARKERS)


def fetch(
    url: str,
    *,
    mode: str = "auto",
    timeout: float = 30.0,
    wait_selector: Optional[str] = None,
    headless: bool = True,
) -> FetchedPage:
    """抓取一个页面。

    :param mode: http 只走 HTTP 客户端；stealth 直接开隐身浏览器；
                 auto 先 HTTP，遇到拦截或验证码页再升级到隐身浏览器。
    :param wait_selector: stealth 模式下等待出现的 CSS 选择器。
    :raises ScraplingUnavailable: 未安装 fetchers，或浏览器不可用。
    """
    _require_fetch()
    mode = (mode or "auto").strip().lower()
    if mode not in ("auto", "http", "stealth"):
        raise ValueError(f"未知抓取模式: {mode!r}（可选 auto / http / stealth）")

    if mode == "stealth":
        return _stealth_page(url, timeout, wait_selector, headless)

    page = _to_page(_fetch_http(url, timeout), url, "http")
    if mode == "http" or not _is_blocked(page):
        return page
    return _stealth_page(url, timeout, wait_selector, headless, fallback_from=page)


def _stealth_page(
    url: str,
    timeout: float,
    wait_selector: Optional[str],
    headless: bool,
    fallback_from: Optional[FetchedPage] = None,
) -> FetchedPage:
    try:
        page = _to_page(_fetch_stealth(url, timeout, wait_selector, headless), url, "stealth")
    except ScraplingUnavailable:
        raise
    except Exception as exc:  # 浏览器二进制缺失 / 启动失败
        hint = (
            "隐身抓取失败，通常是 Chromium 未安装或启动失败。安装："
            "set PLAYWRIGHT_BROWSERS_PATH=E:/DeepSeek/local-data/ms-playwright && patchright install chromium"
        )
        raise ScraplingUnavailable(f"{hint}（原始错误：{type(exc).__name__}: {exc}）") from exc
    if fallback_from is not None:
        page.mode = "auto:stealth"
    return page


# ═══════════════════════════════════════════════════════════════
# 解析与抽取
# ═══════════════════════════════════════════════════════════════
def parse(html: Union[str, bytes], url: str = ""):
    """把 HTML 解析成 Scrapling 选择器。"""
    _require_parse()
    if isinstance(html, (bytes, bytearray)):
        html = bytes(html).decode("utf-8", errors="replace")
    return Selector(html, url=url)


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _value(node: Any, selector: str) -> Optional[str]:
    """在节点内取第一个匹配的文本/属性值；选择器写 ::text 或 ::attr(name)。"""
    try:
        result = node.css(selector)
    except Exception as exc:
        raise ValueError(f"选择器无法解析: {selector!r}（{type(exc).__name__}: {exc}）") from exc
    if not result:
        return None
    first = result[0]
    if isinstance(first, str):
        return _clean(first) or None
    if hasattr(first, "get_all_text"):
        try:
            return _clean(first.get_all_text(strip=True)) or None
        except TypeError:
            pass
    if hasattr(first, "text_content"):
        return _clean(first.text_content()) or None
    return None


def _parse_rating(raw: Optional[str], pattern: Optional[str] = None) -> Optional[Union[int, float]]:
    """把评分文本转成 1-5 的数值；无法识别返回 None。"""
    if raw is None:
        return None
    match = re.search(pattern, str(raw)) if pattern else RATING_RE.search(str(raw))
    if not match:
        return None
    try:
        value = float(match.group(1) if match.groups() else match.group(0))
    except (TypeError, ValueError):
        return None
    if value <= 0 or value > 5:
        return None
    return int(value) if value.is_integer() else round(value, 1)


def _parse_date(raw: Optional[str]) -> str:
    """能识别出完整日期就归一到 YYYY-MM-DD，否则原样保留（缺年份不补，避免污染时间分析）。"""
    if not raw:
        return ""
    text = _clean(raw)
    match = re.search(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return text
    return text


def load_selector_map(source: Union[str, Path, Mapping[str, Any]]) -> Dict[str, Any]:
    """读取并校验选择器配置。

    必需 item 与 fields.review_text；其余字段缺失时该列留空。
    """
    if isinstance(source, Mapping):
        data: Dict[str, Any] = dict(source)
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"选择器配置不存在: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))

    if not str(data.get("item") or "").strip():
        raise ValueError("选择器配置缺少 item（每条评论的容器选择器）")
    fields = data.get("fields")
    if not isinstance(fields, Mapping) or not str(fields.get("review_text") or "").strip():
        raise ValueError("选择器配置缺少 fields.review_text")
    data["fields"] = {str(k): str(v) for k, v in fields.items() if str(v or "").strip()}
    return data


def extract_reviews(
    source: Union[str, bytes, Any],
    selector_map: Union[str, Path, Mapping[str, Any]],
    *,
    platform: str = "",
    source_url: str = "",
    product_id: str = "",
    product_name: str = "",
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """按选择器配置抽取评论，返回与现有爬虫一致的可溯源字段。

    :param source: HTML 文本、Scrapling 选择器，或 fetch() 返回的 FetchedPage。
    :param selector_map: 选择器配置（路径或字典）。
    :param platform: 展示用平台名（如「淘宝」）；缺省取配置的 platform_name / platform。
    """
    config_map = load_selector_map(selector_map)
    fields: Dict[str, str] = config_map["fields"]
    platform_code = str(config_map.get("platform") or "web")
    display = platform or str(config_map.get("platform_name") or platform_code)
    rating_pattern = config_map.get("rating_pattern")

    if isinstance(source, FetchedPage):
        page = source.selector()
    elif hasattr(source, "css"):
        page = source
    else:
        page = parse(source if isinstance(source, (str, bytes)) else str(source), url=source_url)

    nodes = page.css(config_map["item"])
    reviews: List[Dict[str, Any]] = []
    seen = set()
    for node in nodes:
        text = _value(node, fields["review_text"])
        if not text:
            continue
        reviewer = _value(node, fields["reviewer_name"]) if fields.get("reviewer_name") else None
        permalink = _value(node, fields["review_permalink"]) if fields.get("review_permalink") else None
        key = (text, reviewer or "")
        if key in seen:
            continue
        seen.add(key)
        reviews.append(
            {
                "review_text": text,
                "rating": _parse_rating(
                    _value(node, fields["rating"]) if fields.get("rating") else None, rating_pattern
                ),
                "platform": display,
                "timestamp": "",
                "user_id": reviewer or "",
                "product_name": product_name,
                "source_platform": platform_code,
                "source_url": source_url,
                "product_id": product_id,
                "review_permalink": permalink or "",
                "reviewer_name": reviewer or "匿名",
                "reviewer_id": "",
                "review_date": _parse_date(
                    _value(node, fields["review_date"]) if fields.get("review_date") else None
                ),
                "sku": _value(node, fields["sku"]) if fields.get("sku") else "",
                "is_demo": False,
                "extraction_method": "scrapling",
            }
        )
        if limit and len(reviews) >= limit:
            break
    return reviews


def fetch_reviews(
    url: str,
    selector_map: Union[str, Path, Mapping[str, Any]],
    *,
    platform: str = "",
    max_reviews: int = 50,
    mode: str = "auto",
    timeout: float = 30.0,
    wait_selector: Optional[str] = None,
    product_id: str = "",
    product_name: str = "",
) -> List[Dict[str, Any]]:
    """抓一页并抽出评论（采集链路的 Scrapling 后端入口）。"""
    selector_config = load_selector_map(selector_map)
    page = fetch(url, mode=mode, timeout=timeout, wait_selector=wait_selector)
    return extract_reviews(
        page.selector(),
        selector_config,
        platform=platform,
        source_url=page.url or url,
        product_id=product_id,
        product_name=product_name,
        limit=max_reviews,
    )
