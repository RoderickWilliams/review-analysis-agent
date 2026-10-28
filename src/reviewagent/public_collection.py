"""Bounded public comment reads; no login requirement, token guessing or TLS bypass."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

import requests


def parse_payload(body):
    if isinstance(body, (dict, list)):
        return body
    from reviewagent.scrapers.jd_api_scraper import JDAPIScraper
    return JDAPIScraper._parse_jsonp(str(body or "")) or {}


def comment_rows(body, platform):
    """Accept only explicit comment collections, never product descriptions."""
    data = parse_payload(body)
    rows = []
    def visit(node, depth=0):
        if depth > 8 or not isinstance(node, dict):
            return
        for key, value in node.items():
            if key in {"comments", "rateList", "rates", "rateListVO"} and isinstance(value, list):
                rows.extend(item for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                visit(value, depth + 1)
    visit(data)
    return rows[:1000]


def normalize_comment(raw, source, method):
    content = str(raw.get("content") or raw.get("rateContent") or raw.get("feedback") or "").strip()
    if not content:
        return None
    from reviewagent.browser_collection import _review_date
    date = (raw.get("feedbackDate") or raw.get("creationTime") or raw.get("rateDate") or raw.get("date")
            or raw.get("time") or "")
    user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    rating = raw.get("score") if "score" in raw else raw.get("rateScore")
    if isinstance(rating, bool) or str(rating) not in {"1", "2", "3", "4", "5"}:
        rating = None
    else:
        rating = int(rating)
    identity = str(raw.get("id") or raw.get("rateId") or raw.get("comment_id") or "")
    if not identity:
        identity = hashlib.sha256((content + "|" + str(date) + "|" + str(user.get("nick") or raw.get("nickname") or "")).encode()).hexdigest()
    sku = raw.get("auctionSku") or raw.get("skuValueStr") or raw.get("sku") or raw.get("referenceName") or ""
    return {"review_text": content, "raw_card_text": str(raw.get("raw_card_text") or ""), "rating": rating, "source_url": source.get("url") or source.get("source_url"),
            "platform": source.get("platform"), "source_platform": source.get("platform"), "comment_id": identity,
            "review_date": _review_date(date), "review_date_raw": str(date), "sku": sku if isinstance(sku, str) else "",
            "reviewer_name": str(raw.get("userNick") or raw.get("reduceUserNick") or raw.get("nickname")
                               or raw.get("displayUserNick") or raw.get("user_name") or user.get("nick") or ""),
            "product_name": source.get("title", ""), "is_demo": False, "extraction_method": method,
            "content_kind": "social_comment" if source.get("platform") == "xhs" else "product_review"}


def product_id(url, platform):
    parsed = urlsplit(url)
    if platform == "jd":
        match = re.fullmatch(r"/(?:product/)?(\d+)\.html", parsed.path)
        return match.group(1) if match else ""
    value = parse_qs(parsed.query).get("id", [""])[0]
    return value if value.isdigit() else ""


def public_reviews(source, limit, cancelled, *, on_state=None, on_batch=None):
    """Try one documented legacy endpoint; explicit denial stops this route."""
    from reviewagent.browser_collection import CollectionPaused, _wait
    platform = source.get("platform")
    if platform not in {"jd", "taobao", "tmall"}:
        return []
    url = source.get("url") or source.get("source_url") or ""
    item_id = product_id(url, platform)
    if not item_id:
        return []
    endpoint = {"jd": "https://club.jd.com/comment/productPageComments.action",
                "taobao": "https://rate.taobao.com/feedRateList.htm",
                "tmall": "https://rate.tmall.com/list_detail_rate.htm"}[platform]
    reviews, seen = [], set()
    with requests.Session() as session:
        session.trust_env = False
        session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": url, "Accept": "application/json, text/javascript, */*"})
        for page in range(min(30, (limit + 9) // 10)):
            if cancelled():
                break
            params = {"productId": item_id, "score": 0, "sortType": 6, "page": page, "pageSize": 10, "isShadowSku": 0, "fold": 1} if platform == "jd" else (
                {"auctionNumId": item_id, "showContent": "1", "currentPageNum": page + 1} if platform == "taobao" else
                {"itemId": item_id, "currentPage": page + 1, "pageSize": 20})
            if on_state:
                on_state({"platform": "taobao" if platform == "tmall" else platform, "status": "public_collection",
                          "message": "先尝试公开评论接口，无需先登录；第 " + str(page + 1) + " 页"})
            try:
                response = session.get(endpoint, params=params, timeout=(5, 12), allow_redirects=False, stream=True)
                with response:
                    if response.status_code in {403, 429}:
                        raise CollectionPaused("公开评论接口拒绝或限制访问（HTTP " + str(response.status_code) + "），已停止请求", code="rate_limited")
                    if response.status_code != 200:
                        break
                    chunks, total = [], 0
                    for chunk in response.iter_content(65536):
                        total += len(chunk)
                        if total > 3_000_000:
                            raise CollectionPaused("评论接口响应超过读取上限", code="response_too_large")
                        chunks.append(chunk)
                    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            except requests.RequestException:
                break
            if len(body) < 300 and re.search(r"活动太火爆|请稍微再试|访问频繁", body):
                raise CollectionPaused("公开评论接口返回平台限流提示，已停止该平台请求", code="rate_limited")
            rows = comment_rows(body, platform)
            if not rows:
                break
            previous = len(reviews)
            for row in rows:
                review = normalize_comment(row, source, "public_comment_api")
                if review and review["comment_id"] not in seen:
                    reviews.append(review)
                    seen.add(review["comment_id"])
                if len(reviews) >= limit:
                    break
            if on_batch and len(reviews) > previous:
                on_batch(reviews)
            if len(reviews) >= limit or len(reviews) == previous:
                break
            _wait(2, cancelled)
    return reviews
