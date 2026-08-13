# -*- coding: utf-8 -*-
"""
京东评论抓取器 — Playwright 浏览器版
====================================
基于 Playwright 的京东商品评论抓取器，无需登录即可抓取基础评论。

核心优势：
  1. Playwright 比 Selenium 更抗检测（无 navigator.webdriver 标记）
  2. 同时拦截网络请求 + DOM 提取，双保险
  3. 支持 headless 模式，可在 Streamlit Cloud 上运行
  4. 自动检测云端环境并切换 headless

伦理准则：
  - 严禁使用AI生成虚假评论进行虚假分析
  - 所有评论来自真实页面 DOM/API 提取
  - 每条评论包含完整溯源字段
"""

import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional


def ensure_playwright_browsers():
    """确保 Playwright 浏览器已安装（云端首次运行时自动安装）"""
    try:
        result = subprocess.run(
            ["python", "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, timeout=30
        )
        if "is already installed" not in (result.stdout or ""):
            print("[jd-pw] 正在安装 Chromium 浏览器...")
            subprocess.run(
                ["python", "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
            print("[jd-pw] Chromium 安装完成")
    except Exception as e:
        print(f"[jd-pw] 浏览器安装检查失败: {e}")
        try:
            subprocess.run(
                ["python", "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
        except Exception:
            pass


class JDPlaywrightScraper:
    """基于 Playwright 的京东评论抓取器。

    用法::

        scraper = JDPlaywrightScraper()
        reviews = scraper.scrape("https://item.jd.com/100012345.html")
    """

    ITEM_URL_TEMPLATE = "https://item.jd.com/{product_id}.html"
    COMMENT_API = "https://club.jd.com/comment/productPageComments.action"

    def __init__(self, headless: bool = False, max_reviews: int = 50):
        self.headless = headless
        self.max_reviews = max_reviews
        self._playwright = None
        self._context = None
        self._page = None

    # ------------------------------------------------------------------
    # 云端环境检测
    # ------------------------------------------------------------------

    @staticmethod
    def _is_cloud_env() -> bool:
        """检测是否运行在云端环境（Streamlit Cloud）"""
        if os.environ.get("STREAMLIT_SHARING_MODE"):
            return True
        if os.environ.get("STREAMLIT_CLOUD"):
            return True
        if os.name != "nt" and os.path.exists("/home/appuser"):
            return True
        return False

    # ------------------------------------------------------------------
    # 浏览器管理
    # ------------------------------------------------------------------

    def _start_browser(self):
        """启动 Playwright 浏览器"""
        ensure_playwright_browsers()

        from playwright.sync_api import sync_playwright

        # 云端环境强制 headless
        if self._is_cloud_env():
            self.headless = True
            print("[jd-pw] 检测到云端环境，使用 headless 模式")

        self._playwright = sync_playwright().start()

        self._context = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        self._page = self._context.new_page()

        # 注入反检测脚本
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});
            window.chrome = {runtime: {}};
        """)

        return self._page

    def _close_browser(self):
        """关闭浏览器"""
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # URL 解析
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_short_link(url: str) -> str:
        """解析京东短链 (u.jd.com)，返回最终URL"""
        if not url:
            return url

        # 从分享文本中提取 URL
        url_match = re.search(r'https?://[^\s一-龥（）「」]+', url)
        if url_match:
            url = url_match.group(0).strip('.,;\'"')

        host = ""
        try:
            from urllib.parse import urlparse
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            pass

        if "u.jd.com" not in host and "jd.tmgrup" not in host:
            return url

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                final_url = r.url
                html = r.read().decode("utf-8", "replace")

            # 从最终URL提取商品ID
            m = re.search(r'/(\d{4,})\.html', final_url)
            if m:
                result = f"https://item.jd.com/{m.group(1)}.html"
                print(f"[jd-pw] 短链解析: {url} -> {result}")
                return result

            # 从HTML提取
            m = re.search(r'productId["\s:=]+(\d+)', html)
            if m:
                result = f"https://item.jd.com/{m.group(1)}.html"
                print(f"[jd-pw] 短链解析: {url} -> {result}")
                return result

            return final_url
        except Exception as e:
            print(f"[jd-pw] 短链解析失败: {e}")
            return url

    @staticmethod
    def _extract_product_id(url: str) -> str:
        """从 URL 中提取京东商品 ID"""
        if not url:
            return ""
        if url.isdigit():
            return url
        m = re.search(r'/(\d{4,})\.html', url)
        if m:
            return m.group(1)
        m = re.search(r'productId=(\d+)', url)
        if m:
            return m.group(1)
        m = re.search(r'/product/(\d+)', url)
        if m:
            return m.group(1)
        m = re.search(r'(\d{6,})', url)
        if m:
            return m.group(1)
        return ""

    # ------------------------------------------------------------------
    # 网络拦截器
    # ------------------------------------------------------------------

    def _inject_network_interceptor(self):
        """注入网络拦截器，捕获京东评论API响应"""
        self._context.add_init_script("""
            window.__capturedReviews = [];
            const origOpen = XMLHttpRequest.prototype.open;
            const origSend = XMLHttpRequest.prototype.send;

            XMLHttpRequest.prototype.open = function(method, url, ...args) {
                this._url = url;
                return origOpen.call(this, method, url, ...args);
            };

            XMLHttpRequest.prototype.send = function(body) {
                this.addEventListener('load', function() {
                    try {
                        const url = this._url || '';
                        if (url.includes('comment') || url.includes('productPageComments')) {
                            let data;
                            try {
                                data = JSON.parse(this.responseText);
                            } catch(e) {
                                const m = this.responseText.match(/^[a-zA-Z0-9_]+\\((.*)\\);?$/);
                                if (m) {
                                    try { data = JSON.parse(m[1]); } catch(e2) { return; }
                                } else { return; }
                            }
                            if (data) {
                                const comments = data.comments || [];
                                if (comments.length > 0) {
                                    window.__capturedReviews.push(...comments);
                                }
                            }
                        }
                    } catch(e) {}
                });
                return origSend.call(this, body);
            };

            const origFetch = window.fetch;
            window.fetch = async function(...args) {
                const resp = await origFetch.apply(this, args);
                const url = args[0]?.url || args[0] || '';
                if (typeof url === 'string' && (url.includes('comment') || url.includes('productPageComments'))) {
                    resp.clone().text().then(text => {
                        try {
                            const data = JSON.parse(text);
                            const comments = data.comments || [];
                            if (comments.length > 0) {
                                window.__capturedReviews.push(...comments);
                            }
                        } catch(e) {}
                    });
                }
                return resp;
            };
        """)

    # ------------------------------------------------------------------
    # 评论提取
    # ------------------------------------------------------------------

    def _open_comments_tab(self) -> bool:
        """点击"评价"标签，展开评论区"""
        self._page.wait_for_timeout(2000)

        candidates = [
            "text=商品评价",
            "text=累计评价",
            "text=评价",
            "text=全部评价",
            "[href*='comment']",
            "[class*='comment']",
            "[class*='Comment']",
            "[data-tab='comments']",
        ]

        for sel in candidates:
            try:
                loc = self._page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=3000)
                    self._page.wait_for_timeout(2000)
                    print(f"[jd-pw] 点击评论标签成功: {sel}")
                    return True
            except Exception:
                continue

        # 尝试滚动到评论区
        try:
            self._page.evaluate("""
                () => {
                    const el = document.querySelector('#comment, .comment-list, [class*="comment"]');
                    if (el) el.scrollIntoView({behavior: 'smooth'});
                }
            """)
            self._page.wait_for_timeout(2000)
        except Exception:
            pass

        print("[jd-pw] 未找到评论标签，尝试直接滚动")
        return False

    def _scroll_once(self):
        """滚动页面触发懒加载"""
        try:
            self._page.mouse.wheel(0, 1800)
        except Exception:
            try:
                self._page.evaluate("window.scrollBy(0, 1800)")
            except Exception:
                pass
        self._page.wait_for_timeout(1500)

    def _extract_comments_from_dom(self) -> List[Dict]:
        """从渲染后的 DOM 中提取评论"""
        js = """
        () => {
          const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
          const out = [];

          const selectors = [
            '[class*=comment-item]', '[class*=CommentItem]',
            '[class*=review-item]', '[class*=ReviewItem]',
            '[class*=comment-content]', '[class*=Comment--]',
            'div.comment-item', 'li.comment-item',
          ];

          let nodes = [];
          for (const sel of selectors) {
            const found = document.querySelectorAll(sel);
            if (found.length > 0) {
              nodes = [...nodes, ...found];
            }
          }

          if (nodes.length === 0) {
            nodes = [...document.querySelectorAll('[class*="comment"], [class*="Comment"]')];
          }

          for (const node of nodes) {
            const rawText = textOf(node);
            if (!rawText || rawText.length < 6) continue;
            if (rawText.length > 3000) continue;

            const user = textOf(node.querySelector('[class*=user], [class*=nick], [class*=Nick], [class*=User], [class*=user-info]'));
            const time = textOf(node.querySelector('[class*=time], time, [class*=Time], [class*=date]'));
            const sku = textOf(node.querySelector('[class*=sku], [class*=spec], [class*=Sku]'));

            let rateScore = 5;
            const starEl = node.querySelector('[class*=star], [class*=Star], [class*=rate], [class*=score]');
            if (starEl) {
              const starText = textOf(starEl);
              const m = starText.match(/(\\d)/);
              if (m) rateScore = parseInt(m[1]);
            }

            let content = rawText;
            if (user && content.includes(user)) content = content.replace(user, '').trim();
            if (time && content.includes(time)) content = content.replace(time, '').trim();
            content = content.replace(/^\\d+\\s*星?\\s*/, '').trim();

            out.push({
              comment_id: node.getAttribute('data-id') || node.getAttribute('id') || '',
              user_name: user || '匿名用户',
              time: time,
              sku: sku,
              content: content.slice(0, 2000),
              rateScore: rateScore,
            });
          }
          return out;
        }
        """
        try:
            return self._page.evaluate(js) or []
        except Exception as e:
            print(f"[jd-pw] DOM提取失败: {e}")
            return []

    def _extract_comments_from_api(self) -> List[Dict]:
        """从拦截的网络请求中提取评论数据"""
        js = """
        () => {
          return window.__capturedReviews || [];
        }
        """
        try:
            return self._page.evaluate(js) or []
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 评论格式化
    # ------------------------------------------------------------------

    def _format_review(
        self,
        raw: Dict,
        product_id: str,
        product_url: str,
        product_name: str,
        source: str = "dom",
    ) -> Optional[Dict]:
        """将原始评论数据格式化为统一格式，包含完整溯源字段"""

        if source == "api":
            review_text = self._clean_text(raw.get("content"))
            user_name = str(raw.get("nickname") or "匿名用户")
            user_id = str(raw.get("uid") or raw.get("id") or "")
            review_date = self._parse_timestamp(raw.get("creationTime"))
            sku = str(raw.get("productColor", "") + " " + raw.get("productSize", "")).strip()
            rating = self._parse_rating(raw.get("score")) or 5
            comment_id = str(raw.get("id") or "")
            product_name_from_api = raw.get("referenceName") or product_name
        else:
            review_text = (raw.get("content") or "").strip()
            user_name = raw.get("user_name", "匿名用户")
            user_id = ""
            review_date = raw.get("time", "")
            sku = raw.get("sku", "")
            rating = raw.get("rateScore", 5)
            comment_id = raw.get("comment_id", "")
            product_name_from_api = product_name

        if not review_text or len(review_text) < 3:
            return None

        return {
            "review_text": review_text,
            "rating": rating,
            "platform": "jd",
            "timestamp": review_date,
            "user_id": user_name,
            "product_name": product_name_from_api,
            # 完整溯源字段（15个）
            "source_platform": "jd",
            "source_url": product_url,
            "product_id": product_id,
            "review_permalink": f"{product_url}#comment-{comment_id}" if comment_id else f"{product_url}#comment",
            "reviewer_name": user_name,
            "reviewer_id": user_id,
            "review_date": review_date,
            "sku": sku,
            "is_demo": False,
            "extraction_method": f"playwright_{source}",
        }

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

    # ------------------------------------------------------------------
    # 主抓取流程
    # ------------------------------------------------------------------

    def scrape(
        self,
        product_url: str,
        cookies: Optional[Dict] = None,
        max_reviews: int = 50,
    ) -> List[Dict]:
        """
        抓取京东商品评论 — Playwright 浏览器方式

        参数:
            product_url: 商品 URL（支持短链 u.jd.com）
            cookies: 可选 Cookie
            max_reviews: 最大评论数

        返回:
            评论列表（含完整溯源字段）
        """
        print(f"[jd-pw] 开始抓取: {product_url}")

        # Step 1: 解析短链
        product_url = self._resolve_short_link(product_url)
        product_id = self._extract_product_id(product_url)

        if not product_id:
            print(f"[jd-pw] 无法提取商品ID: {product_url}")
            return []

        product_url = self.ITEM_URL_TEMPLATE.format(product_id=product_id)
        print(f"[jd-pw] 商品ID: {product_id}")

        # Step 2: 启动浏览器
        try:
            self._start_browser()
        except Exception as e:
            print(f"[jd-pw] 浏览器启动失败: {e}")
            return []

        # 注入网络拦截器
        self._inject_network_interceptor()

        all_reviews: List[Dict] = []

        try:
            # Step 3: 打开商品页面
            print(f"[jd-pw] 打开商品页面: {product_url}")
            self._page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
            self._page.wait_for_timeout(3000)

            # Step 4: 检测登录重定向（京东一般不需要登录就能看评论）
            current_url = (self._page.url or "").lower()
            if "passport.jd.com" in current_url or "login.jd.com" in current_url:
                if self._is_cloud_env():
                    print("[jd-pw] 云端环境遇到登录页，尝试无登录抓取...")
                    self._page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
                    self._page.wait_for_timeout(3000)
                else:
                    print("[jd-pw] 检测到登录页面，请在浏览器中手动登录...")
                    print("[jd-pw] 等待登录完成（最多180秒）...")
                    logged_in = self._wait_for_login(180)
                    if not logged_in:
                        print("[jd-pw] 登录超时，尝试无登录抓取...")
                    self._page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
                    self._page.wait_for_timeout(3000)

            # Step 5: 获取商品名称
            product_name = ""
            try:
                product_name = self._page.evaluate("""
                    () => {
                        const el = document.querySelector('.sku-name, .itemInfo-wrap .sku-name, title, [class*="product-name"], [class*="goodsName"]');
                        return el ? (el.innerText || el.textContent || '').trim().split('\\n')[0] : '';
                    }
                """)
                if not product_name:
                    product_name = self._page.title().split("-")[0].strip()
                print(f"[jd-pw] 商品名: {product_name}")
            except Exception:
                product_name = ""

            # Step 6: 点击评论标签
            self._open_comments_tab()

            # Step 7: 滚动加载评论
            seen_keys = set()
            stagnant_rounds = 0
            max_rounds = 20

            print(f"[jd-pw] 开始滚动加载评论（目标: {max_reviews} 条）...")

            for round_num in range(max_rounds):
                if len(all_reviews) >= max_reviews:
                    break

                # 从 DOM 提取
                dom_comments = self._extract_comments_from_dom()
                before_count = len(all_reviews)

                for comment in dom_comments:
                    if len(all_reviews) >= max_reviews:
                        break
                    review = self._format_review(
                        comment, product_id, product_url, product_name, source="dom"
                    )
                    if review:
                        key = comment.get("comment_id") or f"{review.get('user_id','')}|{review.get('review_date','')}|{review.get('review_text','')[:50]}"
                        if key not in seen_keys:
                            seen_keys.add(key)
                            all_reviews.append(review)

                # 从 API 拦截提取
                api_comments = self._extract_comments_from_api()
                for comment in api_comments:
                    if len(all_reviews) >= max_reviews:
                        break
                    review = self._format_review(
                        comment, product_id, product_url, product_name, source="api"
                    )
                    if review:
                        key = str(comment.get("id") or "")
                        if not key:
                            key = f"{review.get('user_id','')}|{review.get('review_date','')}|{review.get('review_text','')[:50]}"
                        if key not in seen_keys:
                            seen_keys.add(key)
                            all_reviews.append(review)

                new_count = len(all_reviews) - before_count
                if new_count == 0:
                    stagnant_rounds += 1
                    if stagnant_rounds >= 5:
                        print(f"[jd-pw] 连续 {stagnant_rounds} 轮无新评论，停止滚动")
                        break
                else:
                    stagnant_rounds = 0
                    print(f"[jd-pw] 第 {round_num + 1} 轮: 新增 {new_count} 条 (累计 {len(all_reviews)})")

                self._scroll_once()

            # Step 8: 尝试翻页
            if len(all_reviews) < max_reviews:
                for page_num in range(5):
                    if len(all_reviews) >= max_reviews:
                        break
                    try:
                        next_btn = self._page.locator("text=下一页").first
                        if next_btn.count() > 0:
                            next_btn.click(timeout=3000)
                            self._page.wait_for_timeout(3000)
                            self._scroll_once()

                            api_comments = self._extract_comments_from_api()
                            dom_comments = self._extract_comments_from_dom()
                            for comment in api_comments + dom_comments:
                                if len(all_reviews) >= max_reviews:
                                    break
                                src = "api" if comment in api_comments else "dom"
                                review = self._format_review(
                                    comment, product_id, product_url, product_name, source=src
                                )
                                if review:
                                    key = str(comment.get("id") or comment.get("comment_id") or "")
                                    if not key:
                                        key = f"{review.get('user_id','')}|{review.get('review_date','')}|{review.get('review_text','')[:50]}"
                                    if key not in seen_keys:
                                        seen_keys.add(key)
                                        all_reviews.append(review)
                        else:
                            break
                    except Exception:
                        break

            print(f"[jd-pw] 抓取完成: {len(all_reviews)} 条真实评论")

        except Exception as e:
            print(f"[jd-pw] 抓取异常: {e}")
        finally:
            self._close_browser()

        return all_reviews[:max_reviews]

    def _wait_for_login(self, timeout_sec: int = 180) -> bool:
        """等待用户手动登录"""
        for _ in range(int(timeout_sec / 2)):
            url = (self._page.url or "").lower()
            if "passport.jd.com" not in url and "login.jd.com" not in url:
                return True
            self._page.wait_for_timeout(2000)
        return False


# ------------------------------------------------------------------
# 便捷函数
# ------------------------------------------------------------------

def scrape_jd_reviews(
    product_url: str,
    max_reviews: int = 50,
    headless: bool = False,
) -> List[Dict]:
    """
    便捷函数：使用 Playwright 抓取京东评论

    参数:
        product_url: 商品 URL（支持 u.jd.com 短链）
        max_reviews: 最大评论数
        headless: 是否无头模式

    返回:
        评论列表
    """
    scraper = JDPlaywrightScraper(headless=headless, max_reviews=max_reviews)
    return scraper.scrape(product_url, max_reviews=max_reviews)


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else input("请输入京东商品链接: ")
    reviews = scrape_jd_reviews(url, max_reviews=20)
    print(f"\n共抓取 {len(reviews)} 条评论:")
    for i, r in enumerate(reviews[:5], 1):
        print(f"\n--- 评论 {i} ---")
        print(f"用户: {r.get('reviewer_name')}")
        print(f"评分: {r.get('rating')}")
        print(f"内容: {r.get('review_text')[:100]}")
        print(f"溯源: {r.get('source_url')}")
