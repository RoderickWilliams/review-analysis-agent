# -*- coding: utf-8 -*-
"""
淘宝评论抓取器 — Playwright 持久化登录版
==========================================
基于 https://github.com/ezam988/taobao-comment-grabber 的方法封装。

核心优势：
  1. Playwright 比 Selenium 更抗检测（无 navigator.webdriver 标记）
  2. 持久化用户目录 — 首次手动登录后，后续自动复用登录态
  3. 启发式 DOM 提取 — 不依赖固定 API，适应页面结构变化
  4. 同时拦截网络请求 + DOM 提取，双保险

伦理准则：
  - 严禁使用AI生成虚假评论进行虚假分析
  - 所有评论来自真实页面 DOM 提取
  - 每条评论包含完整溯源字段
"""

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs, urlencode


class TaobaoPlaywrightScraper:
    """基于 Playwright 的淘宝评论抓取器。

    使用持久化用户目录（playwright-data/）保存登录态：
    - 首次运行：弹出浏览器，用户手动登录淘宝
    - 后续运行：自动复用已保存的登录态

    用法::

        scraper = TaobaoPlaywrightScraper()
        reviews = scraper.scrape("https://item.taobao.com/item.htm?id=XXX")
    """

    # 持久化登录目录
    USER_DATA_DIR = str(Path("playwright-data").resolve())

    def __init__(self, headless: bool = False, max_reviews: int = 50):
        self.headless = headless
        self.max_reviews = max_reviews
        self._playwright = None
        self._context = None
        self._page = None

    @staticmethod
    def _is_cloud_env() -> bool:
        """检测是否运行在云端环境（Streamlit Cloud）"""
        if os.environ.get("STREAMLIT_SHARING_MODE"):
            return True
        if os.environ.get("STREAMLIT_CLOUD"):
            return True
        # Streamlit Cloud runs on Linux with /home/appuser
        if os.name != "nt" and os.path.exists("/home/appuser"):
            return True
        return False

    # ------------------------------------------------------------------
    # 浏览器管理
    # ------------------------------------------------------------------

    def _start_browser(self):
        """启动 Playwright 持久化浏览器上下文"""
        # 确保浏览器已安装
        ensure_playwright_browsers()

        from playwright.sync_api import sync_playwright

        # 云端环境强制 headless
        if self._is_cloud_env():
            self.headless = True
            print("[playwright] 检测到云端环境，使用 headless 模式")

        self._playwright = sync_playwright().start()
        data_dir = self.USER_DATA_DIR

        # 确保目录存在
        Path(data_dir).mkdir(parents=True, exist_ok=True)

        self._context = self._playwright.chromium.launch_persistent_context(
            data_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()

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
            self._context.close()
        if self._playwright:
            self._playwright.stop()

    # ------------------------------------------------------------------
    # 短链解析
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_short_link(url: str) -> str:
        """解析淘宝短链，返回最终URL"""
        if not url:
            return url

        # 从分享文本中提取 URL
        url_match = re.search(r'https?://[^\s一-龥（）「」]+', url)
        if url_match:
            url = url_match.group(0).strip('.,;\'"')

        # 如果不是短链，直接返回
        host = (urlparse(url).hostname or "").lower()
        if not any(h in host for h in ["e.tb.cn", "m.tb.cn", "t.tb.cn", "tb.cn", "t.cn"]):
            return url

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                final_url = r.url
                html = r.read().decode("utf-8", "replace")

            # 从最终URL提取item_id
            item_id = ""
            m = re.search(r'[?&]id=(\d+)', final_url)
            if m:
                item_id = m.group(1)
            if not item_id:
                # 从HTML内容提取
                m = re.search(r'[?&]id=(\d+)', html)
                if m:
                    item_id = m.group(1)
            if not item_id:
                # 尝试 var url = '...' 模式
                m = re.search(r"var url\s*=\s*'([^']+)'", html)
                if m:
                    m2 = re.search(r'[?&]id=(\d+)', m.group(1))
                    if m2:
                        item_id = m2.group(1)

            if item_id:
                result = f"https://item.taobao.com/item.htm?id={item_id}"
                print(f"[playwright] 短链解析: {url} -> {result}")
                return result

            return final_url
        except Exception as e:
            print(f"[playwright] 短链解析失败: {e}")
            return url

    @staticmethod
    def _extract_item_id(url: str) -> str:
        """从 URL 中提取商品 ID"""
        m = re.search(r'[?&]id=(\d+)', url)
        if m:
            return m.group(1)
        m = re.search(r'/i(\d+)\.htm', url)
        if m:
            return m.group(1)
        m = re.search(r'(\d{8,})', url)
        if m:
            return m.group(1)
        return ""

    # ------------------------------------------------------------------
    # 登录检测
    # ------------------------------------------------------------------

    def _wait_for_login(self, timeout_sec: int = 180) -> bool:
        """检测登录页面，等待用户手动登录"""
        for _ in range(int(timeout_sec / 2)):
            url = (self._page.url or "").lower()
            if "login.taobao.com" not in url and "login.m.taobao.com" not in url:
                return True
            self._page.wait_for_timeout(2000)
        return False

    def _check_login_status(self) -> bool:
        """检查是否已登录"""
        try:
            url = (self._page.url or "").lower()
            if "login.taobao.com" in url or "login.m.taobao.com" in url:
                return False
            # 检查页面是否有登录后的元素
            has_login = self._page.evaluate("""
                () => {
                    const cookies = document.cookie;
                    return cookies.includes('_tb_token_') || cookies.includes('sgcookie');
                }
            """)
            return has_login
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 评论提取 — 启发式 DOM 提取
    # ------------------------------------------------------------------

    def _open_comments_tab(self) -> bool:
        """点击"评价"/"评论"标签，展开评论区"""
        self._page.wait_for_timeout(2000)

        candidates = [
            "text=评价",
            "text=评论",
            "text=累计评价",
            "text=宝贝评价",
            "text=全部评价",
            "[href*='rate']",
            "[data-tab='comments']",
            "[class*='review']",
            "[class*='comment']",
            "[class*='Comment']",
            "[class*='Review']",
        ]

        for sel in candidates:
            try:
                loc = self._page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=3000)
                    self._page.wait_for_timeout(2000)
                    print(f"[playwright] 点击评论标签成功: {sel}")
                    return True
            except Exception:
                continue

        print("[playwright] 未找到评论标签，尝试直接滚动")
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
        self._page.wait_for_timeout(1200)

    def _extract_comments_from_dom(self) -> List[Dict]:
        """从渲染后的 DOM 中提取评论（精准定位评论卡片，避免 UI 文本污染）"""
        js = r"""
        () => {
          const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
          const uniq = (arr) => [...new Set(arr.filter(Boolean))];

          // ---------- 1. 黑名单关键词：命中则整段丢弃 ----------
          const BLACKLIST_KEYWORDS = [
            '账号管理', '退出', '我的淘宝', '购物车', '收藏夹', '卖家中心',
            '联系客服', '手机逛', '请登录', '免费注册',
            '为你展示真实评价', '默认排序', '款式筛选', '查看全部评价',
            '近半年', '默认好评', '最近一条发布于', '累计评价',
            '全部评价', '写追评', '大家都在问', '宝贝评价',
            '此用户没有填写评价', '评价方未及时',
            '图/视频', '追评', '好评', '中评', '差评', '有图',
            ' Sort', '排序', '筛选',
          ];

          // ---------- 2. 定位真正的"评论卡片"节点 ----------
          // 淘宝常见结构：
          //   .rate-grid > table/tr/td  (旧版)
          //   [class*="Comment--"] [class*="Content--"]
          //   [class*="rate-"] .tm-rate-content / .tb-rev-item
          //   div[data-id] / li[data-id] 且内部含评论文本
          //   [class*="commentItem"], [class*="reviewItem"], [class*="rate-item"]
          const CARD_SELECTORS = [
            '[class*="Comment--"]:not([class*="CommentList"]):not([class*="CommentWrap"])',
            '[class*="commentItem"]',
            '[class*="reviewItem"]',
            '[class*="rate-item"]',
            '[class*="rate-grid"] tr',
            '.tb-rev-item',
            '.tm-rate-item',
            '[class*="Feedback--"]:not([class*="FeedbackList"])',
            'li[data-id]', 'div[data-id]',
          ];

          let cardEls = [];
          for (const sel of CARD_SELECTORS) {
            try {
              const found = document.querySelectorAll(sel);
              if (found && found.length) cardEls = cardEls.concat([...found]);
            } catch (e) {}
          }
          // 去重相同 DOM 节点
          cardEls = uniq(cardEls);

          // 过滤掉"容器型"节点（只保留最内层的真实卡片）：
          // 如果一个节点内部还包含另一个候选卡片，就跳过外层容器
          const leafCards = cardEls.filter(node => {
            for (const sel of CARD_SELECTORS) {
              try {
                if (node.querySelector(sel)) return false;
              } catch (e) {}
            }
            return true;
          });
          const cards = leafCards.length ? leafCards : cardEls;

          // ---------- 3. 精准提取每条评论的字段 ----------
          const out = [];
          for (const card of cards) {
            // 评论正文：优先找专门的内容元素；找不到才退化到卡片文本
            let content = '';
            const contentSelectors = [
              '[class*="Content--"]:not([class*="ContentWrap"]):not([class*="Contents"])',
              '[class*="comment-content"]',
              '[class*="review-content"]',
              '.tm-rate-content', '.tb-r-ev-content',
              '.rate-content', '[class*="rate-content"]',
              '[class*="feedback"]', '[class*="Feedback"]',
              'p[data-content]', 'p.content',
            ];
            for (const cs of contentSelectors) {
              const el = card.querySelector(cs);
              if (el) {
                const t = textOf(el);
                if (t && t.length >= 4 && t.length < 2000) { content = t; break; }
              }
            }
            if (!content) {
              // 退化：直接取卡片文本，但必须通过后续黑名单/长度过滤
              content = textOf(card);
            }
            content = content.replace(/\s+/g, ' ').trim();
            if (!content || content.length < 6 || content.length > 2000) continue;

            // 黑名单过滤
            let blacklisted = false;
            for (const kw of BLACKLIST_KEYWORDS) {
              if (content.includes(kw)) { blacklisted = true; break; }
            }
            if (blacklisted) continue;

            // 必须包含中文（过滤掉纯数字/纯符号/纯英文 UI 碎片）
            if (!/[\u4e00-\u9fa5]/.test(content)) continue;

            // 用户名 / 时间 / sku（各字段独立取，不污染 content）
            const user = textOf(card.querySelector(
              '[class*="User--"], [class*="userName"], [class*="user-name"], ' +
              '[class*="nick"], [class*="Nick"], [class*="author"], .tb-user-info, .rate-user-info'
            ));
            const time = textOf(card.querySelector(
              '[class*="time"], [class*="Time"], [class*="date"], [class*="Date"], time, .tb-rev-date, .col-date'
            ));
            const sku = textOf(card.querySelector(
              '[class*="sku"], [class*="Sku"], [class*="spec"], [class*="auctionSku"], ' +
              '[class*="SkuInfo"], [class*="skuInfo"], .tm-rate-sku, .tb-sku'
            ));

            // 图片
            const imgs = uniq([...card.querySelectorAll('img')]
              .map(img => img.getAttribute('src') || img.getAttribute('data-src') ||
                          img.getAttribute('data-lazyload') || '')
              .filter(s => s && !s.includes('loading.gif') && !s.includes('placeholder') &&
                           !s.includes('avatar') && !s.includes('icon')));

            // 星级
            let rateScore = 5;
            const starEl = card.querySelector('[class*="star"], [class*="Star"], [class*="rateLevel"]');
            if (starEl) {
              const starText = textOf(starEl);
              const m = starText.match(/([1-5])/);
              if (m) rateScore = parseInt(m[1]);
            }

            out.push({
              comment_id: card.getAttribute('data-id') || card.getAttribute('id') || '',
              user_name: user,
              time: time,
              sku: sku,
              content: content.slice(0, 2000),
              images: imgs,
              rateScore: rateScore,
            });
          }
          return out;
        }
        """
        try:
            return self._page.evaluate(js) or []
        except Exception as e:
            print(f"[playwright] DOM提取失败: {e}")
            return []

    def _extract_comments_from_api(self) -> List[Dict]:
        """从拦截的网络请求中提取评论数据"""
        js = """
        () => {
          const data = window.__capturedReviews || [];
          return data;
        }
        """
        try:
            return self._page.evaluate(js) or []
        except Exception:
            return []

    def _inject_network_interceptor(self):
        """注入网络拦截器，捕获评论API响应"""
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
                        if (url.includes('rate') || url.includes('comment') || url.includes('mtop.taobao.rate')) {
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
                                const rateList = data.data?.rateList || data.rateList || [];
                                if (rateList.length > 0) {
                                    window.__capturedReviews.push(...rateList);
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
                if (typeof url === 'string' && (url.includes('rate') || url.includes('comment'))) {
                    resp.clone().text().then(text => {
                        try {
                            const data = JSON.parse(text);
                            const rateList = data.data?.rateList || data.rateList || [];
                            if (rateList.length > 0) {
                                window.__capturedReviews.push(...rateList);
                            }
                        } catch(e) {}
                    });
                }
                return resp;
            };
        """)

    # ------------------------------------------------------------------
    # 评论格式化 — 添加完整溯源字段
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

        # 从 API 拦截的评论有不同字段名
        if source == "api":
            review_text = (raw.get("feedback") or raw.get("content") or "").strip()
            user_name = str(raw.get("displayUserNick") or raw.get("userNick") or "匿名")
            user_id = str(raw.get("displayUserNumId") or "")
            review_date = raw.get("rateDate", "")
            sku = raw.get("auctionSku", "")
            rating = int(raw.get("rateScore", 5)) if raw.get("rateScore") else 5
            comment_id = str(raw.get("id") or raw.get("rateId") or "")
        else:
            # DOM 提取的评论
            review_text = (raw.get("content") or "").strip()
            user_name = raw.get("user_name", "匿名")
            user_id = ""
            review_date = raw.get("time", "")
            sku = raw.get("sku", "")
            rating = raw.get("rateScore", 5)
            comment_id = raw.get("comment_id", "")

        if not review_text:
            return None

        return {
            "review_text": review_text,
            "rating": rating,
            "platform": "taobao",
            "timestamp": review_date,
            "user_id": user_name,
            "product_name": product_name,
            # 完整溯源字段（15个）
            "source_platform": "taobao",
            "source_url": product_url,
            "product_id": product_id,
            "review_permalink": f"https://item.taobao.com/item.htm?id={product_id}#review",
            "reviewer_name": user_name,
            "reviewer_id": user_id,
            "review_date": review_date,
            "sku": sku,
            "is_demo": False,
            "extraction_method": f"playwright_{source}",
        }

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
        抓取淘宝商品评论 — Playwright 持久化登录方式

        参数:
            product_url: 商品 URL（支持短链）
            cookies: 可选 Cookie（Playwright 持久化目录已保存登录态时可省略）
            max_reviews: 最大评论数

        返回:
            评论列表（含完整溯源字段）
        """
        print(f"[playwright] 开始抓取: {product_url}")

        # Step 1: 解析短链
        product_url = self._resolve_short_link(product_url)
        product_id = self._extract_item_id(product_url)

        if not product_id:
            print(f"[playwright] 无法提取商品ID: {product_url}")
            return []

        print(f"[playwright] 商品ID: {product_id}")

        # Step 2: 启动浏览器
        try:
            self._start_browser()
        except Exception as e:
            print(f"[playwright] 浏览器启动失败: {e}")
            return []

        # 注入网络拦截器（在导航之前）
        self._inject_network_interceptor()

        all_reviews: List[Dict] = []

        try:
            # Step 3: 打开商品页面
            print(f"[playwright] 打开商品页面: {product_url}")
            self._page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
            self._page.wait_for_timeout(3000)

            # Step 4: 检测登录重定向
            current_url = (self._page.url or "").lower()
            if "login.taobao.com" in current_url or "login.m.taobao.com" in current_url:
                if self._is_cloud_env():
                    print("[playwright] 云端环境无法手动登录，尝试无登录抓取...")
                    # 直接导航回商品页，尝试无登录抓取
                    self._page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
                    self._page.wait_for_timeout(3000)
                else:
                    # 原有的登录等待逻辑
                    print("[playwright] 检测到登录页面，请在弹出的浏览器中手动登录...")
                    print("[playwright] 等待登录完成（最多180秒）...")
                    logged_in = self._wait_for_login(180)
                    if not logged_in:
                        print("[playwright] 登录超时")
                        return []
                    # 登录后重新导航到商品页
                    self._page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
                    self._page.wait_for_timeout(3000)

            # Step 5: 获取商品名称
            product_name = ""
            try:
                product_name = self._page.evaluate("""
                    () => {
                        const el = document.querySelector('h1, [data-title], .tb-main-title, [class*="mainTitle"], [class*="title"]');
                        return el ? (el.innerText || el.textContent || '').trim().split('\\n')[0] : '';
                    }
                """)
                if not product_name:
                    product_name = self._page.title()
                print(f"[playwright] 商品名: {product_name}")
            except Exception:
                product_name = ""

            # Step 6: 点击评论标签
            self._open_comments_tab()

            # Step 7: 滚动加载评论
            seen_keys = set()
            seen_texts = set()  # 按规范化评论文本去重（兜底，防同评论不同 key）
            stagnant_rounds = 0
            max_rounds = 20  # 最多滚动20轮

            def _norm_text(t: str) -> str:
                """规范化评论文本，用于跨来源/跨轮次去重。"""
                if not t:
                    return ""
                t = re.sub(r"\s+", "", str(t))
                # 去掉常见前后缀噪声
                t = t.strip()
                return t[:120]  # 取前 120 字符作为指纹，足够区分不同评论

            def _dedup_key(comment: Dict, review: Dict, source: str) -> str:
                """生成去重 key：优先 comment_id，其次规范化文本指纹。"""
                cid = ""
                if source == "api":
                    cid = str(comment.get("id") or comment.get("rateId") or "")
                else:
                    cid = str(comment.get("comment_id") or "")
                if cid:
                    return f"id:{cid}"
                # 没有 id 时，用文本指纹兜底
                text_fp = _norm_text(review.get("review_text", ""))
                if text_fp:
                    return f"txt:{text_fp}"
                return ""

            print(f"[playwright] 开始滚动加载评论（目标: {max_reviews} 条）...")

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
                    if not review:
                        continue
                    text_fp = _norm_text(review.get("review_text", ""))
                    if text_fp and text_fp in seen_texts:
                        continue  # 同一条评论已抓过（无论外层容器/字段顺序如何）
                    key = _dedup_key(comment, review, "dom")
                    if key and key in seen_keys:
                        continue
                    if key:
                        seen_keys.add(key)
                    if text_fp:
                        seen_texts.add(text_fp)
                    all_reviews.append(review)

                # 从 API 拦截提取
                api_comments = self._extract_comments_from_api()
                for comment in api_comments:
                    if len(all_reviews) >= max_reviews:
                        break

                    review = self._format_review(
                        comment, product_id, product_url, product_name, source="api"
                    )
                    if not review:
                        continue
                    text_fp = _norm_text(review.get("review_text", ""))
                    if text_fp and text_fp in seen_texts:
                        continue
                    key = _dedup_key(comment, review, "api")
                    if key and key in seen_keys:
                        continue
                    if key:
                        seen_keys.add(key)
                    if text_fp:
                        seen_texts.add(text_fp)
                    all_reviews.append(review)

                new_count = len(all_reviews) - before_count
                if new_count == 0:
                    stagnant_rounds += 1
                    if stagnant_rounds >= 5:
                        print(f"[playwright] 连续 {stagnant_rounds} 轮无新评论，停止滚动")
                        break
                else:
                    stagnant_rounds = 0
                    print(f"[playwright] 第 {round_num + 1} 轮: 新增 {new_count} 条 (累计 {len(all_reviews)})")

                # 滚动
                self._scroll_once()

            # Step 8: 尝试点击"全部评价"
            if len(all_reviews) < max_reviews:
                try:
                    loc = self._page.locator("text=全部评价").first
                    if loc.count() > 0:
                        loc.click(timeout=2000)
                        self._page.wait_for_timeout(2000)
                        # 再滚动几轮
                        for _ in range(5):
                            if len(all_reviews) >= max_reviews:
                                break
                            self._scroll_once()
                            dom_comments = self._extract_comments_from_dom()
                            for comment in dom_comments:
                                if len(all_reviews) >= max_reviews:
                                    break
                                review = self._format_review(
                                    comment, product_id, product_url, product_name, source="dom"
                                )
                                if not review:
                                    continue
                                text_fp = _norm_text(review.get("review_text", ""))
                                if text_fp and text_fp in seen_texts:
                                    continue
                                key = _dedup_key(comment, review, "dom")
                                if key and key in seen_keys:
                                    continue
                                if key:
                                    seen_keys.add(key)
                                if text_fp:
                                    seen_texts.add(text_fp)
                                all_reviews.append(review)
                except Exception:
                    pass

            print(f"[playwright] 抓取完成: {len(all_reviews)} 条真实评论")

        except Exception as e:
            print(f"[playwright] 抓取异常: {e}")
        finally:
            self._close_browser()

        return all_reviews[:max_reviews]


def ensure_playwright_browsers():
    """确保 Playwright 浏览器已安装（云端首次运行时自动安装）"""
    import subprocess
    import shutil
    try:
        # 检查 chromium 是否已安装
        result = subprocess.run(
            ["python", "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, timeout=30
        )
        if "is already installed" not in result.stdout:
            print("[playwright] 正在安装 Chromium 浏览器...")
            subprocess.run(
                ["python", "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
            print("[playwright] Chromium 安装完成")
    except Exception as e:
        print(f"[playwright] 浏览器安装检查失败: {e}")
        # 尝试直接安装
        try:
            subprocess.run(
                ["python", "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
        except Exception:
            pass


# ------------------------------------------------------------------
# 便捷函数
# ------------------------------------------------------------------

def scrape_taobao_reviews(
    product_url: str,
    max_reviews: int = 50,
    headless: bool = False,
) -> List[Dict]:
    """
    便捷函数：使用 Playwright 抓取淘宝评论

    参数:
        product_url: 商品 URL（支持短链）
        max_reviews: 最大评论数
        headless: 是否无头模式（首次登录建议 False）

    返回:
        评论列表
    """
    scraper = TaobaoPlaywrightScraper(headless=headless, max_reviews=max_reviews)
    return scraper.scrape(product_url, max_reviews=max_reviews)


if __name__ == "__main__":
    # 测试
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else input("请输入淘宝商品链接: ")
    reviews = scrape_taobao_reviews(url, max_reviews=20)
    print(f"\n共抓取 {len(reviews)} 条评论:")
    for i, r in enumerate(reviews[:5], 1):
        print(f"\n--- 评论 {i} ---")
        print(f"用户: {r.get('reviewer_name')}")
        print(f"评分: {r.get('rating')}")
        print(f"内容: {r.get('review_text')[:100]}")
        print(f"溯源: {r.get('source_url')}")
