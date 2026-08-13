# -*- coding: utf-8 -*-
"""
京东 (JD.com) 商品评论爬虫 (JDScraper) — 增强版
==============================================

集成 5 大爬虫能力：
  1. productPageComments API 分页抓取（基础，无需登录）
  2. Selenium 浏览器渲染抓取（反爬绕过，拦截 XHR/fetch）
  3. Cookie 注入 + 持久化登录（断点续采）
  4. 京东短链 (u.jd.com) 自动解析
  5. HTML 回退解析（兜底方案）

伦理准则：
  - 严禁使用AI生成虚假评论
  - 所有评论必须来自京东真实页面
  - 每条评论包含完整溯源字段（source_platform/source_url/product_id 等）
"""

import hashlib
import json
import os
import re
import time
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


class JDScraper(BaseScraper):
    """京东商品评论爬虫 — 支持 API/Selenium/Cookie 多模式抓取。"""

    platform_name = "jd"

    COMMENT_API = "https://club.jd.com/comment/productPageComments.action"
    ITEM_URL_TEMPLATE = "https://item.jd.com/{product_id}.html"
    M_ITEM_URL_TEMPLATE = "https://item.m.jd.com/product/{product_id}.html"

    def __init__(self, delay: float = 2.0, timeout: int = 15, max_retries: int = 3):
        super().__init__(delay=delay, timeout=timeout, max_retries=max_retries)
        self.product_id: Optional[str] = None
        self.product_name: Optional[str] = None

    @staticmethod
    def parse_product_id(url: str) -> Optional[str]:
        """从京东商品 URL 中提取商品 ID (productId)。"""
        if not url:
            return None
        if url.isdigit():
            return url
        match = re.search(r"/(?:product/)?(\d{4,})\.html", url)
        if match:
            return match.group(1)
        match = re.search(r"[?&]productId=(\d+)", url)
        if match:
            return match.group(1)
        if "u.jd.com" in url or "jd.tmgrup" in url:
            try:
                import requests as _req
                resp = _req.get(url, allow_redirects=True, timeout=10,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"})
                final_url = resp.url
                match = re.search(r"/(?:product/)?(\d{4,})", final_url)
                if match:
                    return match.group(1)
                id_match = re.search(r'productId["\s:=]+(\d+)', resp.text)
                if id_match:
                    return id_match.group(1)
            except Exception:
                pass
        return None

    @staticmethod
    def clean_url(raw: str) -> str:
        """从分享文本中提取纯 URL。"""
        if not raw:
            return ""
        match = re.search(r'https?://[^\s\u4e00-\u9fff\uff08\uff09\u300c\u300d]+', raw)
        if match:
            return match.group(0).rstrip(',.;\'")')
        return raw

    def _fetch_product_name(self) -> str:
        """从京东商品详情页提取商品名称。"""
        if not self.product_id:
            return ""
        url = self.ITEM_URL_TEMPLATE.format(product_id=self.product_id)
        text = self.fetch_page(url)
        if not text:
            return ""
        soup = BeautifulSoup(text, "html.parser")
        for selector in [".sku-name", "title", "meta[property='og:title']"]:
            tag = soup.select_one(selector)
            if tag:
                content = tag.get("content") or tag.get_text(strip=True)
                if content:
                    return content.split("-京东")[0].strip()
        return ""

    def parse_reviews(self, html: str, **kwargs) -> List[Dict]:
        """解析京东评论接口返回的 JSON（含溯源字段）。"""
        reviews: List[Dict] = []
        if not html:
            return reviews
        data = self._extract_json(html)
        if not data:
            return reviews
        comments = data.get("comments", []) if isinstance(data, dict) else []
        product_url = (self.ITEM_URL_TEMPLATE.format(product_id=self.product_id)
                       if self.product_id else "")
        for item in comments:
            review_text = self._clean_text(item.get("content"))
            if not review_text:
                continue
            after_content = item.get("afterUserComment", {}) or {}
            if isinstance(after_content, dict):
                after_text = self._clean_text(after_content.get("content"))
                if after_text:
                    review_text = review_text + " 【追加】" + after_text
            review = {
                "review_text": review_text,
                "rating": self._parse_rating(item.get("score")),
                "timestamp": self._parse_timestamp(item.get("creationTime")),
                "user_id": str(item.get("nickname") or item.get("uid") or ""),
                "product_name": item.get("referenceName") or self.product_name or "",
                "platform": self.platform_name,
                "source_platform": "jd",
                "source_url": product_url,
                "product_id": self.product_id or "",
                "review_permalink": f"{product_url}#comment-{item.get('id', '')}" if product_url else "",
                "reviewer_name": str(item.get("nickname") or "匿名用户"),
                "reviewer_id": str(item.get("uid") or item.get("id") or ""),
                "review_date": self._parse_timestamp(item.get("creationTime")),
                "sku": str(item.get("productColor", "") + " " + item.get("productSize", "")).strip(),
                "is_demo": False,
                "extraction_method": "jd_api",
            }
            reviews.append(review)
        return reviews

    def _extract_json(self, text: str) -> Optional[Dict]:
        text = text.strip()
        jsonp_match = re.match(r"^[a-zA-Z_]+\w*\((.*)\);?$", text, re.DOTALL)
        if jsonp_match:
            text = jsonp_match.group(1)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _clean_text(text) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", str(text))
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _parse_rating(score) -> Optional[float]:
        try:
            return float(score)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_timestamp(raw) -> str:
        if not raw:
            return ""
        if isinstance(raw, str):
            try:
                dt = time.strptime(raw, "%Y-%m-%d %H:%M:%S")
                return time.strftime("%Y-%m-%d %H:%M:%S", dt)
            except (ValueError, TypeError):
                return raw
        return str(raw)

    def scrape(self, url: str, max_reviews: int = 100, **kwargs) -> List[Dict]:
        """抓取京东商品评论，自动分页。"""
        url = self.clean_url(url)
        if url.isdigit():
            self.product_id = url
        else:
            self.product_id = self.parse_product_id(url)
        if not self.product_id:
            print(f"[jd] 无法从 URL 解析 productId: {url}")
            return []
        try:
            self.product_name = self._fetch_product_name()
        except Exception as e:
            print(f"[jd] 商品名提取失败: {e}")
        all_reviews: List[Dict] = []
        page = 0
        page_size = 10
        max_pages = (max_reviews // page_size) + 2
        empty_pages = 0
        while len(all_reviews) < max_reviews and page <= max_pages:
            params = {
                "productId": self.product_id,
                "score": 0,
                "sortType": 5,
                "page": page,
                "pageSize": page_size,
                "isShadowSku": 0,
                "fold": 1,
            }
            text = self.fetch_page(
                self.COMMENT_API, params=params,
                extra_headers={
                    "Referer": self.ITEM_URL_TEMPLATE.format(product_id=self.product_id),
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            if not text:
                break
            page_reviews = self.parse_reviews(text)
            page_reviews = self._dedupe(page_reviews)
            if not page_reviews:
                empty_pages += 1
                if empty_pages >= 2:
                    print(f"[jd] 连续 {empty_pages} 页无评论数据，结束抓取")
                    break
            else:
                empty_pages = 0
                all_reviews.extend(page_reviews)
                print(f"[jd] 已抓取 {len(all_reviews)} 条评论（第 {page + 1} 页）")
            page += 1
        return all_reviews[:max_reviews]

    def scrape_with_selenium(self, product_url: str, cookies: dict = None,
                              max_reviews: int = 50) -> list:
        """使用 Selenium 浏览器抓取京东评论（反爬绕过，最可靠）。"""
        import re
        import time
        import json as _json
        product_url = self.clean_url(product_url)
        if not product_url:
            return []
        if "u.jd.com" in product_url:
            import requests
            try:
                resp = requests.get(product_url, allow_redirects=True, timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"})
                final_url = resp.url
                self.product_id = self.parse_product_id(final_url)
                if not self.product_id:
                    id_match = re.search(r'productId["\s:=]+(\d+)', resp.text)
                    if id_match:
                        self.product_id = id_match.group(1)
                print(f"[jd] 短链解析: {product_url} -> {final_url}")
            except Exception as e:
                print(f"[jd] 短链解析失败: {e}")
                return []
        else:
            self.product_id = self.parse_product_id(product_url)
        if not self.product_id:
            print("[jd] Selenium: 无法提取商品ID")
            return []
        print(f"[jd] Selenium模式启动: 商品ID={self.product_id}")
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
        except ImportError:
            print("[jd] Selenium 未安装")
            return []
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--window-size=1280,900")
        try:
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            print(f"[jd] Chrome 启动失败: {e}")
            return []
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
        except Exception:
            pass
        reviews = []
        product_name = ""
        product_page_url = self.ITEM_URL_TEMPLATE.format(product_id=self.product_id)
        try:
            driver.get("https://www.jd.com/")
            time.sleep(2)
            if cookies:
                for name, value in cookies.items():
                    try:
                        driver.add_cookie({"name": name, "value": value, "domain": ".jd.com"})
                    except Exception:
                        pass
                print(f"[jd] 已注入 {len(cookies)} 个 Cookie")
            interceptor_js = r"""
            window.__capturedReviews = [];
            var origOpen = XMLHttpRequest.prototype.open;
            var origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(m, u) {
                this._url = u;
                return origOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function() {
                var self = this;
                this.addEventListener('load', function() {
                    try {
                        if (self._url && (self._url.indexOf('comment') !== -1 ||
                            self._url.indexOf('productPageComments') !== -1)) {
                            var text = self.responseText;
                            window.__capturedReviews.push({url: self._url, data: JSON.parse(text)});
                        }
                    } catch(e) {}
                });
                return origSend.apply(this, arguments);
            };
            var origFetch = window.fetch;
            window.fetch = function() {
                var url = arguments[0];
                if (typeof url === 'object') url = url.url || '';
                return origFetch.apply(this, arguments).then(function(resp) {
                    try {
                        if (url && (url.indexOf('comment') !== -1 ||
                            url.indexOf('productPageComments') !== -1)) {
                            resp.clone().text().then(function(text) {
                                window.__capturedReviews.push({url: url, data: JSON.parse(text)});
                            });
                        }
                    } catch(e) {}
                    return resp;
                });
            };
            """
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": interceptor_js})
            print(f"[jd] 正在打开商品页面: {product_page_url}")
            driver.get(product_page_url)
            time.sleep(5)
            try:
                product_name = driver.title.split("-")[0].strip() if driver.title else ""
            except Exception:
                pass
            print(f"[jd] 商品名: {product_name}")
            self.product_name = product_name
            current_url = driver.current_url
            if "login" in current_url.lower() or "passport" in current_url.lower():
                print("[jd] 检测到需要登录！请在浏览器中完成京东登录...")
                login_success = False
                for i in range(90):
                    time.sleep(2)
                    try:
                        current_url = driver.current_url
                        if "login" not in current_url.lower() and "passport" not in current_url.lower():
                            print(f"[jd] 登录成功！")
                            login_success = True
                            break
                    except Exception:
                        pass
                    if i % 15 == 0 and i > 0:
                        print(f"[jd] 仍在等待登录... ({i*2}秒)")
                if not login_success:
                    print("[jd] 登录超时（180秒）")
                driver.get(product_page_url)
                time.sleep(5)
            print("[jd] 尝试点击评价标签...")
            clicked = False
            for xpath in ['//a[contains(text(),"商品评价")]', '//a[contains(text(),"评价")]',
                          '//li[contains(text(),"评价")]', '//span[contains(text(),"评价")]',
                          '//a[contains(text(),"累计评价")]']:
                try:
                    els = driver.find_elements(By.XPATH, xpath)
                    for el in els:
                        if el.is_displayed():
                            el.click()
                            print(f"[jd] 点击了: {el.text}")
                            clicked = True
                            time.sleep(3)
                            break
                except Exception:
                    pass
                if clicked:
                    break
            print("[jd] 滚动页面加载更多评论...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1.5)
            time.sleep(3)
            captured = driver.execute_script("return window.__capturedReviews || [];")
            if captured:
                print(f"[jd] 拦截到 {len(captured)} 个 API 响应")
                for cap in captured:
                    if not isinstance(cap, dict):
                        continue
                    cap_data = cap.get("data", cap)
                    if not isinstance(cap_data, dict):
                        continue
                    comments = cap_data.get("comments", [])
                    for item in comments:
                        review_text = self._clean_text(item.get("content"))
                        if not review_text:
                            continue
                        reviews.append({
                            "review_text": review_text,
                            "rating": self._parse_rating(item.get("score")) or 5,
                            "platform": "jd",
                            "product_name": product_name,
                            "timestamp": self._parse_timestamp(item.get("creationTime")),
                            "user_id": str(item.get("nickname") or ""),
                            "source_platform": "jd",
                            "source_url": product_page_url,
                            "product_id": self.product_id,
                            "review_permalink": f"{product_page_url}#comment-{item.get('id', '')}",
                            "reviewer_name": str(item.get("nickname") or "匿名用户"),
                            "reviewer_id": str(item.get("uid") or item.get("id") or ""),
                            "review_date": self._parse_timestamp(item.get("creationTime")),
                            "sku": str(item.get("productColor", "") + " " + item.get("productSize", "")).strip(),
                            "is_demo": False,
                            "extraction_method": "jd_selenium",
                        })
                if reviews:
                    print(f"[jd] 从API拦截获取 {len(reviews)} 条评论")
            if not reviews:
                print("[jd] API拦截无数据，尝试从DOM提取...")
                page_source = driver.page_source
                reviews = self._extract_reviews_from_dom(page_source, product_page_url, self.product_id, product_name)
                if reviews:
                    print(f"[jd] 从DOM提取 {len(reviews)} 条评论")
            if cookies:
                try:
                    selenium_cookies = driver.get_cookies()
                    fresh_cookies = {}
                    for c in selenium_cookies:
                        name = c.get("name", "")
                        value = c.get("value", "")
                        if name and value:
                            fresh_cookies[name] = value
                    if fresh_cookies:
                        cookie_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies")
                        os.makedirs(cookie_dir, exist_ok=True)
                        cookie_path = os.path.join(cookie_dir, "jd_cookies.json")
                        with open(cookie_path, "w", encoding="utf-8") as f:
                            _json.dump({"platform": "jd", "cookies": fresh_cookies, "saved_at": time.time(), "source": "selenium_interactive"}, f, ensure_ascii=False, indent=2)
                        print(f"[jd] 已保存最新Cookie ({len(fresh_cookies)} 个)")
                except Exception as e:
                    print(f"[jd] 保存Cookie失败: {e}")
            print(f"[jd] Selenium 共抓取 {len(reviews)} 条真实评论")
        except Exception as e:
            import traceback
            print(f"[jd] Selenium 抓取异常: {e}")
            traceback.print_exc()
        finally:
            try:
                driver.quit()
            except Exception:
                pass
        return reviews[:max_reviews]

    def _extract_reviews_from_dom(self, page_source: str, product_url: str,
                                   product_id: str, product_name: str) -> list:
        """从 Selenium 渲染后的 DOM 中提取京东评论。"""
        from bs4 import BeautifulSoup
        import re
        reviews = []
        soup = BeautifulSoup(page_source, "html.parser")
        selectors = ['[class*="comment-item"]', '[class*="Comment--"]', '[class*="review-item"]',
                     '[class*="comment-content"]', '[class*="CommentItem"]', 'div.comment-item']
        for selector in selectors:
            items = soup.select(selector)
            if not items:
                continue
            for item in items:
                text = item.get_text(strip=True, separator=" ")
                if len(text) < 5:
                    continue
                reviewer = "匿名用户"
                for sel in ['[class*="user"]', '[class*="User"]', '[class*="nick"]', '[class*="Nick"]', '[class*="user-info"]']:
                    el = item.select_one(sel)
                    if el:
                        reviewer = el.get_text(strip=True)
                        break
                date = ""
                date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', text)
                if date_match:
                    date = date_match.group(1)
                rating = 5
                rating_match = re.search(r'(\d)\s*星|评分[::](\d)', text)
                if rating_match:
                    rating = int(rating_match.group(1) or rating_match.group(2))
                sku = ""
                sku_match = re.search(r'(?:已购|颜色|版本)[::]\s*(.+?)(?:\s|$)', text, re.IGNORECASE)
                if sku_match:
                    sku = sku_match.group(1)
                content = text
                if reviewer != "匿名用户":
                    content = content.replace(reviewer, "")
                if date:
                    content = content.replace(date, "")
                content = re.sub(r'^\d+\s*星?\s*', '', content).strip()
                if content and len(content) > 3:
                    reviews.append({
                        "review_text": content[:500],
                        "rating": rating,
                        "platform": "jd",
                        "product_name": product_name,
                        "timestamp": date,
                        "user_id": reviewer,
                        "source_platform": "jd",
                        "source_url": product_url,
                        "product_id": product_id,
                        "review_permalink": f"{product_url}#review",
                        "reviewer_name": reviewer,
                        "reviewer_id": "",
                        "review_date": date,
                        "sku": sku,
                        "is_demo": False,
                        "extraction_method": "jd_dom",
                    })
            if reviews:
                break
        return reviews
