# -*- coding: utf-8 -*-
"""
多平台评论聚合爬虫 (MultiPlatformScraper) — 淘宝+京东专版
========================================================

统一调度淘宝/京东爬虫，自动识别平台并聚合评论为统一格式。
集成 JSONP 拦截抓取、Selenium 浏览器抓取、API 签名抓取、HTML 回退解析等多种方式。

淘宝评论抓取优先级：
  1. JSONP 拦截（taobao_jsonp_scraper.py，基于 taobao-xhs-crawler）
  2. API 签名抓取（taobao_scraper.py）
  3. HTML 回退解析（兜底）

支持平台（仅这两个）：
  - 淘宝/天猫 (taobao): item.taobao.com, detail.tmall.com, e.tb.cn
  - 京东 (jd): item.jd.com, item.m.jd.com, u.jd.com

伦理准则：
  - 严禁使用AI生成虚假评论进行虚假分析
  - 所有评论必须来自真实平台抓取
  - 每条评论包含完整溯源字段
  - 爬取失败时如实告知，不得用虚假数据替代
"""

import csv
import hashlib
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional

from urllib.parse import urlparse

from .base_scraper import BaseScraper
from .jd_scraper import JDScraper
from .taobao_scraper import TaobaoScraper
from .taobao_playwright_scraper import TaobaoPlaywrightScraper
from .jd_playwright_scraper import JDPlaywrightScraper


# 平台与域名的映射表（仅淘宝+京东）
PLATFORM_DOMAIN_MAP = {
    # 淘宝 / 天猫
    "taobao.com": "taobao",
    "tmall.com": "taobao",
    "m.taobao.com": "taobao",
    "a.m.taobao.com": "taobao",
    # 淘宝短链域名
    "s.tb.cn": "taobao",
    "e.tb.cn": "taobao",
    "m.tb.cn": "taobao",
    "tb.cn": "taobao",
    "t.tb.cn": "taobao",
    # 京东
    "jd.com": "jd",
    "item.jd.com": "jd",
    "item.m.jd.com": "jd",
    "m.jd.com": "jd",
    # 京东短链
    "u.jd.com": "jd",
}

# 已知的短链域名
SHORT_LINK_DOMAINS = {
    "s.tb.cn", "e.tb.cn", "m.tb.cn", "tb.cn", "t.tb.cn",
    "u.jd.com"
}

# 统一输出字段顺序（CSV 列顺序）
UNIFIED_FIELDS = [
    "review_text",
    "rating",
    "platform",
    "timestamp",
    "user_id",
    "product_name",
    "source_platform",
    "source_url",
    "product_id",
    "review_permalink",
    "reviewer_name",
    "reviewer_id",
    "review_date",
    "sku",
    "is_demo",
    "extraction_method",
]


class MultiPlatformScraper:
    """多平台评论聚合爬虫 — 仅支持淘宝和京东。

    用法示例::

        scraper = MultiPlatformScraper(delay=2.0)
        reviews = scraper.scrape_product("https://item.jd.com/123456.html")
    """

    def __init__(self, delay: float = 2.0, timeout: int = 15, max_retries: int = 3,
                 output_dir: str = "output"):
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.output_dir = output_dir
        self._lock = threading.Lock()
        self._platform_cookies: Dict[str, Dict[str, str]] = {}
        self._scraper_factories = {
            "taobao": lambda: TaobaoScraper(delay, timeout, max_retries),
            "jd": lambda: JDScraper(delay, timeout, max_retries),
        }

    # ------------------------------------------------------------------
    # 平台检测
    # ------------------------------------------------------------------
    @staticmethod
    def detect_platform(url: str) -> Optional[str]:
        """根据 URL 自动识别电商平台（仅淘宝/京东）。"""
        if not url or url.isdigit():
            return None
        try:
            netloc = urlparse(url).netloc.lower()
        except Exception:
            return None
        if not netloc:
            return None
        if netloc in PLATFORM_DOMAIN_MAP:
            return PLATFORM_DOMAIN_MAP[netloc]
        for domain, platform in PLATFORM_DOMAIN_MAP.items():
            if netloc.endswith(domain) or domain in netloc:
                return platform
        return None

    @staticmethod
    def is_short_link(url: str) -> bool:
        """判断 URL 是否为短链。"""
        try:
            netloc = urlparse(url).netloc.lower()
            return netloc in SHORT_LINK_DOMAINS
        except Exception:
            return False

    @staticmethod
    def resolve_short_url(url: str, timeout: int = 10) -> str:
        """跟随短链重定向，获取最终的真实 URL。"""
        try:
            import requests as _req
            resp = _req.get(
                url, allow_redirects=True, timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"},
            )
            final_url = resp.url
            if final_url and final_url != url:
                print(f"[multi] 短链解析: {url} -> {final_url}")
                return final_url
        except Exception as e:
            print(f"[multi] 短链解析失败: {e}，使用原始 URL")
        return url

    # ------------------------------------------------------------------
    # Cookie 配置
    # ------------------------------------------------------------------
    def set_platform_cookies(self, platform: str, cookies: Dict[str, str]) -> None:
        """为指定平台设置登录 Cookie。"""
        if platform not in self._scraper_factories:
            print(f"[multi] 不支持的平台: {platform}（仅支持 taobao/jd）")
            return
        self._platform_cookies[platform] = cookies
        print(f"[multi] 已为平台 {platform} 设置 {len(cookies)} 个 Cookie")

    def _create_scraper(self, platform: str) -> Optional[BaseScraper]:
        """创建指定平台的爬虫实例。"""
        factory = self._scraper_factories.get(platform)
        if not factory:
            print(f"[multi] 不支持的平台: {platform}")
            return None
        scraper = factory()
        cookies = self._platform_cookies.get(platform)
        if cookies:
            scraper.set_cookies(cookies)
        return scraper

    # ------------------------------------------------------------------
    # 单平台抓取
    # ------------------------------------------------------------------
    def _scrape_single(self, platform: str, target: str,
                       max_reviews: int) -> List[Dict]:
        """抓取单个平台评论。"""
        scraper = self._create_scraper(platform)
        if scraper is None:
            return []

        cookies = self._platform_cookies.get(platform)
        if cookies:
            scraper.set_cookies(cookies)
            print(f"[multi] 已注入 {platform} Cookie ({len(cookies)} 个)")

        try:
            print(f"[multi] 开始抓取平台 {platform}，目标: {target}")
            reviews = []

            # 淘宝平台：优先 Playwright → rate.taobao.com API → mtop签名API → 基础
            if platform == "taobao":
                # 方法1: Playwright 持久化登录抓取（最抗检测）
                try:
                    print(f"[multi] 淘宝: 方法1 - Playwright 浏览器抓取")
                    pw_scraper = TaobaoPlaywrightScraper(headless=False, max_reviews=max_reviews)
                    reviews = pw_scraper.scrape(target, cookies=cookies, max_reviews=max_reviews)
                except Exception as e:
                    print(f"[multi] 淘宝: 方法1失败: {e}")
                    reviews = []
                # 方法2: rate.taobao.com API（无需mtop签名）
                if not reviews:
                    try:
                        print(f"[multi] 淘宝: 方法2 - rate.taobao.com API")
                        from scrapers.taobao_comment_v2 import TaobaoCommentScraperV2
                        tb_v2 = TaobaoCommentScraperV2()
                        reviews = tb_v2.scrape(target, cookies=cookies, max_reviews=max_reviews)
                    except Exception as e:
                        print(f"[multi] 淘宝: 方法2失败: {e}")
                        reviews = []
                # 方法3: mtop API签名抓取
                if not reviews and cookies and hasattr(scraper, 'scrape_with_cookies'):
                    try:
                        print(f"[multi] 淘宝: 方法3 - mtop API 签名抓取")
                        reviews = scraper.scrape_with_cookies(
                            target, cookies, max_reviews=max_reviews)
                    except Exception as e:
                        print(f"[multi] 淘宝: 方法3失败: {e}")
                        reviews = []
                # 方法4: 基础抓取
                if not reviews:
                    reviews = scraper.scrape(target, max_reviews=max_reviews)

            # 京东平台：优先 Playwright → API → Selenium → 基础
            elif platform == "jd":
                # 方法1: Playwright 浏览器抓取（最抗检测，支持云端 headless）
                try:
                    print(f"[multi] 京东: 方法1 - Playwright 浏览器抓取")
                    jd_pw = JDPlaywrightScraper(headless=False, max_reviews=max_reviews)
                    reviews = jd_pw.scrape(target, cookies=cookies, max_reviews=max_reviews)
                except Exception as e:
                    print(f"[multi] 京东: 方法1失败: {e}")
                    reviews = []
                # 方法2: API 抓取
                if not reviews:
                    print(f"[multi] 京东: 方法2 - API 抓取")
                    reviews = scraper.scrape(target, max_reviews=max_reviews)
                # 方法3: Selenium 浏览器抓取
                if not reviews and hasattr(scraper, 'scrape_with_selenium'):
                    print(f"[multi] 京东: 方法3 - Selenium 抓取")
                    try:
                        reviews = scraper.scrape_with_selenium(
                            target, cookies=cookies, max_reviews=max_reviews)
                    except Exception as e:
                        print(f"[multi] 京东: 方法3失败: {e}")

            # 统一字段格式 + 溯源验证
            unified = [self._normalize(r, platform) for r in reviews]
            # 过滤掉缺少溯源字段的评论（反虚假评论机制）
            validated = self._validate_traceability(unified, platform)
            print(f"[multi] 平台 {platform} 抓取完成，共 {len(validated)} 条有效评论")
            return validated
        except Exception as e:
            print(f"[multi] 平台 {platform} 抓取异常: {e}")
            return []
        finally:
            scraper.close()

    @staticmethod
    def _normalize(review: Dict, platform: str) -> Dict:
        """将单条评论归一化为统一字段格式（保留所有溯源字段）。"""
        result = {
            "review_text": review.get("review_text", ""),
            "rating": review.get("rating"),
            "platform": review.get("platform", platform),
            "timestamp": review.get("timestamp", ""),
            "user_id": review.get("user_id", ""),
            "product_name": review.get("product_name", ""),
        }
        traceability_fields = [
            "source_platform", "source_url", "product_id",
            "review_permalink", "reviewer_name", "reviewer_id",
            "review_date", "sku", "is_demo", "extraction_method",
        ]
        for field in traceability_fields:
            if field in review:
                result[field] = review[field]
        result.setdefault("source_platform", platform)
        result.setdefault("source_url", "")
        result.setdefault("product_id", "")
        result.setdefault("review_permalink", "")
        result.setdefault("reviewer_name", review.get("user_id", "匿名"))
        result.setdefault("reviewer_id", "")
        result.setdefault("review_date", review.get("timestamp", ""))
        result.setdefault("sku", "")
        result.setdefault("is_demo", False)
        result.setdefault("extraction_method", "unknown")
        return result

    @staticmethod
    def _validate_traceability(reviews: List[Dict], platform: str) -> List[Dict]:
        """验证评论溯源字段，过滤掉无效评论。

        反虚假评论机制：每条评论必须有 source_platform 和 review_text。
        """
        valid = []
        for r in reviews:
            # 必须有评论文字
            if not r.get("review_text", "").strip():
                continue
            # 必须有来源平台
            if not r.get("source_platform"):
                r["source_platform"] = platform
            # 标记为演示数据的评论不进入分析
            if r.get("is_demo"):
                print(f"[multi] 警告: 发现演示数据，已过滤")
                continue
            valid.append(r)
        return valid

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def scrape_product(self, product_url_or_keyword: str,
                       platforms: Optional[List[str]] = None,
                       max_reviews: int = 100) -> List[Dict]:
        """抓取商品评论（仅淘宝/京东）。

        :param product_url_or_keyword: 商品 URL
        :param platforms: 指定平台列表，None 表示自动检测
        :param max_reviews: 每个平台最大评论数
        :return: 统一格式的评论列表
        """
        if not product_url_or_keyword:
            print("[multi] 输入为空")
            return []

        # URL清洗
        url_match = re.search(r'https?://[^\s\u4e00-\u9fff\uff08\uff09\u300c\u300d]+', product_url_or_keyword)
        if url_match:
            clean_url = url_match.group(0).rstrip(',.;\'")')
            if clean_url != product_url_or_keyword:
                print(f"[multi] URL清洗: {product_url_or_keyword[:50]}... -> {clean_url[:80]}")
                product_url_or_keyword = clean_url

        # 短链解析
        if self.is_short_link(product_url_or_keyword):
            print(f"[multi] 检测到短链，正在解析...")
            product_url_or_keyword = self.resolve_short_url(product_url_or_keyword)

        # 自动识别平台
        if platforms is None:
            detected = self.detect_platform(product_url_or_keyword)
            if detected:
                platforms = [detected]
                print(f"[multi] 自动识别平台: {detected}")
            else:
                print(f"[multi] 无法识别平台（仅支持淘宝/京东）")
                return []
        else:
            platforms = [p for p in platforms if p in self._scraper_factories]
            if not platforms:
                print("[multi] 指定的平台均不支持（仅支持 taobao/jd）")
                return []

        # 单平台直接抓取
        if len(platforms) == 1:
            all_reviews = self._scrape_single(platforms[0], product_url_or_keyword, max_reviews)
        else:
            all_reviews = self._scrape_concurrent(platforms, product_url_or_keyword, max_reviews)

        # 全局去重
        all_reviews = self._global_dedupe(all_reviews)
        print(f"[multi] 聚合完成，去重后共 {len(all_reviews)} 条评论")

        # 自动保存 CSV
        if all_reviews:
            csv_path = self.save_to_csv(all_reviews)
            print(f"[multi] 结果已保存至: {csv_path}")

        return all_reviews

    def _scrape_concurrent(self, platforms: List[str], target: str,
                           max_reviews: int) -> List[Dict]:
        """并发抓取多个平台。"""
        all_reviews: List[Dict] = []
        max_workers = min(len(platforms), 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self._scrape_single, p, target, max_reviews): p
                for p in platforms
            }
            for future in as_completed(future_map):
                platform = future_map[future]
                try:
                    result = future.result()
                    with self._lock:
                        all_reviews.extend(result)
                except Exception as e:
                    print(f"[multi] 平台 {platform} 并发抓取失败: {e}")
        return all_reviews

    @staticmethod
    def _global_dedupe(reviews: List[Dict]) -> List[Dict]:
        """跨平台全局去重。"""
        seen: set = set()
        unique: List[Dict] = []
        for r in reviews:
            text = re.sub(r"\s+", "", r.get("review_text", ""))[:150].lower()
            key = hashlib.md5(
                f"{r.get('platform')}|{text}|{r.get('rating')}".encode("utf-8")
            ).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            unique.append(r)
        return unique

    # ------------------------------------------------------------------
    # CSV 保存
    # ------------------------------------------------------------------
    def save_to_csv(self, reviews: List[Dict],
                    filename: Optional[str] = None) -> str:
        """将评论列表保存为 CSV 文件。"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"reviews_{timestamp}.csv"
        os.makedirs(self.output_dir, exist_ok=True)
        filepath = os.path.abspath(os.path.join(self.output_dir, filename))
        platform_counts: Dict[str, int] = {}
        for r in reviews:
            p = r.get("platform", "unknown")
            platform_counts[p] = platform_counts.get(p, 0) + 1
        with self._lock:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=UNIFIED_FIELDS, extrasaction="ignore")
                writer.writeheader()
                for review in reviews:
                    row = {k: ("" if review.get(k) is None else review.get(k, ""))
                           for k in UNIFIED_FIELDS}
                    writer.writerow(row)
        print(f"[multi] CSV 保存完成: {filepath}")
        print(f"[multi] 各平台评论数: {platform_counts}")
        return filepath

    def scrape_products(self, targets: List[str],
                        platforms: Optional[List[str]] = None,
                        max_reviews: int = 100) -> Dict[str, List[Dict]]:
        """批量抓取多个商品的评论。"""
        results: Dict[str, List[Dict]] = {}
        for target in targets:
            print(f"\n[multi] ===== 开始处理: {target} =====")
            try:
                reviews = self.scrape_product(target, platforms, max_reviews)
                results[target] = reviews
            except Exception as e:
                print(f"[multi] 处理 {target} 失败: {e}")
                results[target] = []
        return results


if __name__ == "__main__":
    scraper = MultiPlatformScraper(delay=2.0)
    test_urls = [
        "https://item.jd.com/100012043978.html",
        "https://item.taobao.com/item.htm?id=655448745434",
        "https://detail.tmall.com/item.htm?id=123456",
    ]
    print("=== 平台检测演示 ===")
    for u in test_urls:
        print(f"{u} -> {scraper.detect_platform(u)}")
