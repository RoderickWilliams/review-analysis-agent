# -*- coding: utf-8 -*-
"""
淘宝/天猫评论爬虫 — 基于 JSONP 拦截 + 容器滚动
================================================
原始项目: https://github.com/KemenMax/taobao-xhs-crawler (tb.py)
改造内容:
  1. 移除小红书(xhs)相关代码，仅保留淘宝/天猫评论抓取
  2. 支持两种模式：远程调试连接(原项目方式) + 自动启动浏览器(带Cookie注入)
  3. 添加完整溯源字段（source_platform/source_url/product_id 等 15个字段）
  4. 添加反虚假评论验证
  5. 补全 parse_comments 功能（原项目缺失该模块）
  6. 支持短链自动解析
  7. 增加登录等待机制（最多180秒）
  8. JSONP 拦截 + XHR/fetch 拦截双保险
  9. DOM 回退解析（兜底方案）

核心技术:
  - JSONP 拦截: 劫持 document.head.appendChild，包装 mtop.taobao.rate.detaillist.get 回调
  - 容器滚动: 查找评论弹层中真正可滚动的容器（scrollHeight > clientHeight）
  - 持续滚动: 循环滚动容器触发懒加载，收集拦截到的评论数据

伦理准则:
  - 严禁使用AI生成虚假评论进行虚假分析
  - 所有评论必须来自淘宝/天猫真实页面抓取
  - 每条评论包含完整溯源字段
  - 爬取失败时如实告知，不得用虚假数据替代
"""

import os
import re
import json
import time
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TaobaoJsonpScraper:
    """
    淘宝/天猫评论爬虫 — JSONP 拦截 + 容器滚动

    基于 taobao-xhs-crawler 项目的 JSONP 拦截技术，
    劫持 mtop.taobao.rate.detaillist.get 的 JSONP 回调函数，
    在回调执行时捕获评论数据。

    抓取优先级:
    1. JSONP 拦截（最可靠，直接捕获 mtop API 回调）
    2. XHR/fetch 拦截（备用，拦截异步请求）
    3. DOM 解析（兜底，从渲染后的页面提取）
    """

    # JSONP 拦截目标 API
    TARGET_JSONP_API = "mtop.taobao.rate.detaillist.get"

    # 评论容器 CSS 选择器（淘宝类名经常变化，提供多个候选）
    COMMENT_CONTAINER_SELECTORS = [
        ".comments--ChxC7GEN",
        ".beautify-scroll-bar",
        "div[class*='comments--']",
        "div[class*='Comment--']",
        "div[class*='rate-list']",
        "div[class*='ratelist']",
        "div[style*='overflow']",
    ]

    # "查看全部" 按钮选择器
    SHOW_ALL_BUTTON_SELECTORS = [
        "div[class*='ShowButton--fMu7HZNs']",
        "div[class*='ShowButton--']",
        "a[class*='ShowButton--']",
        "div[class*='show-all']",
        "a[class*='show-all']",
    ]

    def __init__(self, delay: float = 2.0, timeout: int = 15, max_retries: int = 3):
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # URL 解析与短链处理
    # ------------------------------------------------------------------
    @staticmethod
    def parse_item_id(url: str) -> Optional[str]:
        """从淘宝/天猫商品 URL 中提取商品 ID"""
        if not url:
            return None
        # ?id=123456 格式
        match = re.search(r"[?&]id=(\d+)", url)
        if match:
            return match.group(1)
        # /i123456.htm 格式
        match = re.search(r"/i(\d+)\.htm", url)
        if match:
            return match.group(1)
        # itemId=123456 格式
        match = re.search(r"itemId=(\d+)", url)
        if match:
            return match.group(1)
        # 从 URL 路径中提取 8 位以上数字
        match = re.search(r"(\d{8,})", url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def clean_url(raw_url: str) -> str:
        """从分享文本中提取纯 URL"""
        if not raw_url:
            return ""
        match = re.search(r'https?://[^\s一-龥（）「」]+', raw_url)
        if match:
            return match.group(0).strip('.,;\'"')
        return raw_url.strip()

    @staticmethod
    def resolve_short_link(url: str) -> Tuple[str, str]:
        """解析淘宝短链，返回 (最终URL, item_id)"""
        import requests
        try:
            resp = requests.get(
                url,
                allow_redirects=True,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                },
            )
            final_url = resp.url
            item_id = TaobaoJsonpScraper.parse_item_id(final_url)
            if not item_id:
                # 从页面内容中提取
                id_match = re.search(r'[?&]id=(\d+)', resp.text)
                if id_match:
                    item_id = id_match.group(1)
            logger.info(f"短链解析: {url} -> {final_url} (item_id={item_id})")
            return final_url, item_id or ""
        except Exception as e:
            logger.error(f"短链解析失败: {e}")
            return url, ""

    # ------------------------------------------------------------------
    # JSONP 拦截脚本注入
    # ------------------------------------------------------------------
    @staticmethod
    def get_jsonp_interceptor_js() -> str:
        """
        生成 JSONP 拦截脚本

        核心原理（来自 taobao-xhs-crawler/tb.py）:
        1. 劫持 document.head.appendChild
        2. 检测插入的 <script> 标签是否为目标 JSONP 请求
        3. 从 script.src 中提取 callback 参数名
        4. 包装原始回调函数，在执行时把数据存入 window.__intercepted_data
        """
        return """
        (function() {
            if (window.__interceptor_injected) return;
            window.__interceptor_injected = true;
            window.__intercepted_data = [];

            var originalAppendChild = document.head.appendChild;
            document.head.appendChild = function(element) {
                if (element.tagName === 'SCRIPT' && element.src &&
                    element.src.includes('mtop.taobao.rate.detaillist.get')) {
                    console.log('[拦截器] 捕获到目标JSONP脚本:', element.src.substring(0, 80));
                    var match = element.src.match(/callback=([^&]+)/);
                    if (match) {
                        var callbackName = match[1];

                        var checkAndWrap = function() {
                            if (window[callbackName] && !window[callbackName].__wrapped) {
                                var originalCallback = window[callbackName];
                                window[callbackName] = function(data) {
                                    console.log('[拦截器] 捕获JSONP数据:', callbackName);
                                    window.__intercepted_data.push(data);
                                    return originalCallback(data);
                                };
                                window[callbackName].__wrapped = true;
                            } else {
                                if (!window[callbackName]) {
                                    window[callbackName] = function(data) {
                                        console.log('[拦截器] 捕获JSONP数据(占位):', callbackName);
                                        window.__intercepted_data.push(data);
                                    };
                                }
                            }
                        };
                        checkAndWrap();
                    }
                }
                return originalAppendChild.call(document.head, element);
            };
            console.log('[拦截器] JSONP拦截器已注入');
        })();
        """

    @staticmethod
    def get_xhr_fetch_interceptor_js() -> str:
        """
        生成 XHR/fetch 拦截脚本（双保险）

        同时拦截 XMLHttpRequest 和 fetch 请求，
        捕获包含 'rate' 或 'comment' 或 'mtop.taobao' 的响应。
        """
        return r"""
        (function() {
            if (window.__xhr_injected) return;
            window.__xhr_injected = true;
            window.__captured_xhr = [];

            // 拦截 XMLHttpRequest
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
                        if (self._url && (self._url.indexOf('rate') !== -1 ||
                            self._url.indexOf('comment') !== -1 ||
                            self._url.indexOf('mtop.taobao') !== -1)) {
                            var text = self.responseText;
                            var m = text.match(/^[a-zA-Z0-9_]+\((.+)\);?$/);
                            var s = m ? m[1] : text;
                            window.__captured_xhr.push({url: self._url, data: JSON.parse(s)});
                        }
                    } catch(e) {}
                });
                return origSend.apply(this, arguments);
            };

            // 拦截 fetch
            var origFetch = window.fetch;
            window.fetch = function() {
                var url = arguments[0];
                if (typeof url === 'object') url = url.url || '';
                return origFetch.apply(this, arguments).then(function(resp) {
                    try {
                        if (url && (url.indexOf('rate') !== -1 ||
                            url.indexOf('comment') !== -1 ||
                            url.indexOf('mtop.taobao') !== -1)) {
                            resp.clone().text().then(function(text) {
                                var m = text.match(/^[a-zA-Z0-9_]+\((.+)\);?$/);
                                var s = m ? m[1] : text;
                                window.__captured_xhr.push({url: url, data: JSON.parse(s)});
                            });
                        }
                    } catch(e) {}
                    return resp;
                });
            };
            console.log('[拦截器] XHR/fetch拦截器已注入');
        })();
        """

    # ------------------------------------------------------------------
    # 可滚动容器查找（来自 taobao-xhs-crawler/tb.py）
    # ------------------------------------------------------------------
    @staticmethod
    def find_scrollable_element(driver):
        """
        寻找评论弹层中真正可以滚动的容器

        原理: scrollHeight > clientHeight 表示内容溢出，可以滚动
        """
        from selenium.webdriver.common.by import By

        logger.info("正在寻找可滚动的评论容器...")
        for css in TaobaoJsonpScraper.COMMENT_CONTAINER_SELECTORS:
            elements = driver.find_elements(By.CSS_SELECTOR, css)
            for elem in elements:
                try:
                    is_scrollable = driver.execute_script(
                        "return arguments[0].scrollHeight > arguments[0].clientHeight "
                        "&& arguments[0].clientHeight > 0;",
                        elem
                    )
                    if is_scrollable:
                        logger.info(f"找到可滚动容器: {css}")
                        return elem
                except Exception:
                    continue

        # 尝试查找所有有 overflow 样式的元素
        try:
            all_elements = driver.find_elements(By.CSS_SELECTOR, "div[style*='overflow']")
            for elem in all_elements:
                try:
                    is_scrollable = driver.execute_script(
                        "return arguments[0].scrollHeight > arguments[0].clientHeight "
                        "&& arguments[0].clientHeight > 50;",
                        elem
                    )
                    if is_scrollable:
                        logger.info("找到可滚动容器(overflow样式)")
                        return elem
                except Exception:
                    continue
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # 评论数据解析（补全原项目缺失的 parse_comments 功能）
    # ------------------------------------------------------------------
    @staticmethod
    def parse_rate_list(rate_list: List[Dict], product_id: str,
                        product_url: str, product_name: str = "") -> List[Dict]:
        """
        解析 mtop API 返回的 rateList 数据，格式化为标准评论（含溯源字段）

        补全原项目缺失的 parse_comments.save_reviews 功能
        """
        reviews = []
        for item in rate_list:
            # 提取评论内容
            content = (item.get("feedback") or
                       item.get("content") or
                       item.get("rateContent") or "").strip()
            if not content or len(content) < 2:
                continue

            # 提取评论者信息
            user_info = item.get("user", {}) if isinstance(item.get("user"), dict) else {}
            nick = (user_info.get("nick") or
                    item.get("displayUserNick") or
                    item.get("userNick") or "匿名")

            # 提取评论时间
            date = (item.get("rateDate") or
                    item.get("date") or
                    item.get("gmtCreate") or "")

            # 提取评分
            rating = 5
            score = item.get("rateScore") or item.get("score")
            if score:
                try:
                    rating = int(float(score))
                except (ValueError, TypeError):
                    pass

            # 提取 SKU
            sku = item.get("auctionSku", "") or item.get("sku", "")
            if not isinstance(sku, str):
                sku = str(sku)

            # 提取追评
            append_list = item.get("appendList", []) or []
            append_comment = ""
            if append_list and isinstance(append_list, list):
                first = append_list[0] if append_list else {}
                if isinstance(first, dict):
                    append_comment = first.get("content", "")

            # 提取商家回复
            reply = item.get("reply")
            reply_content = ""
            if reply and isinstance(reply, dict):
                reply_content = reply.get("content", "")
            elif reply and isinstance(reply, str):
                reply_content = reply

            review = {
                # 核心字段
                "review_text": content[:500],
                "rating": rating,
                "platform": "taobao",
                "product_name": product_name,
                "timestamp": date,

                # 溯源字段（15个，必需）
                "source_platform": "taobao",
                "source_url": product_url,
                "product_id": product_id,
                "review_permalink": f"{product_url}#review",
                "reviewer_name": str(nick),
                "reviewer_id": str(item.get("displayUserNumId") or
                                  user_info.get("userId", "") or ""),
                "review_date": str(date),
                "sku": sku,
                "is_demo": False,
                "extraction_method": "jsonp_intercept",

                # 扩展字段
                "user_id": str(item.get("userNick") or
                              item.get("displayUserNick") or ""),
                "append_comment": append_comment,
                "seller_reply": reply_content,
            }
            reviews.append(review)

        return reviews

    # ------------------------------------------------------------------
    # 主抓取流程 — 自动启动浏览器模式
    # ------------------------------------------------------------------
    def scrape(
        self,
        product_url: str,
        cookies: Optional[Dict] = None,
        max_reviews: int = 50,
        login_wait: int = 180,
    ) -> List[Dict]:
        """
        使用 JSONP 拦截 + 容器滚动 抓取淘宝/天猫评论

        流程:
        1. URL 清洗 + 短链解析
        2. 启动 Chrome 浏览器
        3. 注入 Cookie（如有）
        4. 注入 JSONP + XHR/fetch 拦截脚本
        5. 打开商品页面
        6. 检测登录重定向，等待用户手动登录（最多180秒）
        7. 点击"查看全部评价"
        8. 查找可滚动容器，循环滚动收集评论
        9. 从拦截数据中提取评论
        10. DOM 回退解析（兜底）

        :param product_url: 商品 URL 或分享文本
        :param cookies: 登录 Cookie 字典（可选）
        :param max_reviews: 最大评论数
        :param login_wait: 登录等待时间（秒）
        :return: 评论列表（含完整溯源字段）
        """
        # 1. URL 清洗
        product_url = self.clean_url(product_url)
        if not product_url:
            return []

        # 2. 短链解析
        if 'tb.cn' in product_url or 'tb.com' in product_url:
            final_url, item_id = self.resolve_short_link(product_url)
            if item_id:
                product_url = f"https://item.taobao.com/item.htm?id={item_id}"
            else:
                product_url = final_url
        else:
            item_id = self.parse_item_id(product_url)

        if not item_id:
            logger.error("无法提取商品ID")
            return []

        # 判断是淘宝还是天猫
        if 'tmall.com' in product_url:
            product_page_url = f"https://detail.tmall.com/item.htm?id={item_id}"
        else:
            product_page_url = f"https://item.taobao.com/item.htm?id={item_id}"

        logger.info(f"开始抓取: item_id={item_id}, URL={product_page_url}")

        # 3. 启动 Selenium
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError:
            logger.error("Selenium 未安装")
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
            logger.error(f"Chrome 启动失败: {e}")
            return []

        # 隐藏 webdriver 标记
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
        except Exception:
            pass

        reviews = []
        product_name = ""

        try:
            # 4. 打开淘宝首页（设置 Cookie 的前提）
            driver.get("https://www.taobao.com/")
            time.sleep(2)

            # 5. 注入 Cookie
            if cookies:
                for name, value in cookies.items():
                    try:
                        domain = ".taobao.com"
                        if 'tmall' in product_page_url:
                            domain = ".tmall.com"
                        driver.add_cookie({
                            "name": name,
                            "value": value,
                            "domain": domain,
                        })
                    except Exception:
                        pass
                logger.info(f"已注入 {len(cookies)} 个 Cookie")

            # 6. 注入拦截脚本（在新文档加载前执行）
            jsonp_js = self.get_jsonp_interceptor_js()
            xhr_js = self.get_xhr_fetch_interceptor_js()
            combined_js = jsonp_js + "\n" + xhr_js
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": combined_js},
            )

            # 7. 导航到商品页面
            logger.info(f"正在打开商品页面: {product_page_url}")
            driver.get(product_page_url)
            time.sleep(5)

            # 获取商品名
            try:
                product_name = driver.title.split("-")[0].strip() if driver.title else ""
            except Exception:
                pass
            logger.info(f"商品名: {product_name}")

            # 8. 检测登录重定向
            current_url = driver.current_url
            page_title = driver.title or ""
            is_login_page = ("login" in current_url.lower() or
                            "登录" in page_title or
                            "login.taobao" in current_url.lower())

            if is_login_page:
                logger.info("=" * 50)
                logger.info("检测到需要登录！请在弹出的浏览器窗口中完成淘宝登录")
                logger.info(f"等待登录（最多{login_wait}秒）...")
                logger.info("=" * 50)

                login_success = False
                for i in range(login_wait // 2):
                    time.sleep(2)
                    try:
                        current_url = driver.current_url
                        page_title = driver.title or ""
                        if ("login" not in current_url.lower() and
                            "登录" not in page_title and
                            "login.taobao" not in current_url.lower()):
                            logger.info(f"登录成功！当前页面: {page_title}")
                            login_success = True
                            break
                    except Exception:
                        pass
                    if i % 15 == 0 and i > 0:
                        logger.info(f"仍在等待登录... ({i*2}秒)")

                if not login_success:
                    logger.warning(f"登录超时（{login_wait}秒）")

                # 重新导航到商品页面
                logger.info(f"重新打开商品页面: {product_page_url}")
                driver.get(product_page_url)
                time.sleep(5)
                try:
                    product_name = driver.title.split("-")[0].strip() if driver.title else ""
                except Exception:
                    pass

            # 9. 再次注入 JSONP 拦截器（确保在当前页面生效）
            driver.execute_script(self.get_jsonp_interceptor_js())

            # 10. 滚动主页面确保按钮可见
            driver.execute_script("window.scrollTo(0, 1000);")
            time.sleep(2)

            # 11. 点击"查看全部评价"按钮
            self._click_show_all_button(driver)

            time.sleep(3)

            # 再次注入拦截器（弹层可能重新加载）
            driver.execute_script(self.get_jsonp_interceptor_js())

            # 12. 查找可滚动容器并循环滚动
            container = self.find_scrollable_element(driver)

            if container:
                logger.info("找到可滚动容器，开始循环滚动获取数据...")
                self._scroll_and_collect(driver, container, max_reviews, product_id,
                                        product_page_url, product_name, reviews)
            else:
                logger.warning("未找到可滚动容器，尝试滚动主页面...")
                self._scroll_main_page(driver, max_reviews, product_id,
                                      product_page_url, product_name, reviews)

            # 13. 从拦截的 JSONP 数据中提取评论
            if not reviews:
                reviews = self._extract_from_intercepted(driver, product_id,
                                                         product_page_url, product_name)

            # 14. 从 XHR/fetch 拦截数据中提取
            if not reviews:
                reviews = self._extract_from_xhr(driver, product_id,
                                                product_page_url, product_name)

            # 15. DOM 回退解析
            if not reviews:
                logger.info("拦截器无数据，尝试从DOM提取...")
                from scrapers.taobao_scraper import TaobaoScraper
                ts = TaobaoScraper()
                page_source = driver.page_source
                reviews = ts._extract_reviews_from_dom(
                    page_source, product_page_url, item_id, product_name)
                # 标记提取方式
                for r in reviews:
                    r["extraction_method"] = "dom_fallback"

            # 16. iframe 回退
            if not reviews:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                logger.info(f"尝试从 {len(iframes)} 个 iframe 中提取...")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        iframe_src = driver.page_source
                        from scrapers.taobao_scraper import TaobaoScraper
                        ts = TaobaoScraper()
                        iframe_reviews = ts._extract_reviews_from_dom(
                            iframe_src, product_page_url, item_id, product_name)
                        if iframe_reviews:
                            for r in iframe_reviews:
                                r["extraction_method"] = "iframe_fallback"
                            reviews.extend(iframe_reviews)
                        driver.switch_to.default_content()
                        if len(reviews) >= max_reviews:
                            break
                    except Exception:
                        driver.switch_to.default_content()

            # 17. 保存最新 Cookie
            if cookies:
                self._save_fresh_cookies(driver)

            # 18. 反虚假评论验证 — 过滤空评论和重复
            reviews = self._validate_reviews(reviews)

            logger.info(f"抓取完成: {len(reviews)} 条真实评论")

        except Exception as e:
            import traceback
            logger.error(f"抓取异常: {e}")
            traceback.print_exc()
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        return reviews[:max_reviews]

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _click_show_all_button(self, driver):
        """点击"查看全部评价"按钮"""
        from selenium.webdriver.common.by import By

        # 尝试 CSS 选择器
        for css in self.SHOW_ALL_BUTTON_SELECTORS:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, css)
                for el in elements:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        logger.info(f"点击了'查看全部'按钮: {css}")
                        return True
            except Exception:
                continue

        # 尝试 XPath
        for xpath in [
            '//a[contains(text(),"全部评价")]',
            '//a[contains(text(),"全部评论")]',
            '//span[contains(text(),"全部评价")]',
            '//span[contains(text(),"全部评论")]',
            '//div[contains(text(),"全部评价")]',
            '//a[contains(text(),"评价")]',
            '//span[contains(text(),"评价")]',
            '//a[contains(text(),"累计评论")]',
            '//a[contains(text(),"宝贝评价")]',
        ]:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed():
                        el.click()
                        logger.info(f"点击了评价标签: {el.text}")
                        return True
            except Exception:
                continue

        logger.warning("未找到'查看全部'按钮（可能已展开或选择器变更）")
        return False

    def _scroll_and_collect(self, driver, container, max_reviews: int,
                           product_id: str, product_url: str,
                           product_name: str, reviews: list):
        """
        循环滚动容器并收集拦截到的评论数据

        核心逻辑来自 taobao-xhs-crawler/tb.py:
        - 滚动容器到底部
        - 检查拦截到的 JSONP 数据
        - 清空缓冲区
        - 检测滚动位置是否变化（判断是否加载完毕）
        """
        max_scrolls = 100
        last_scroll_top = -1
        retry_count = 0
        seen_texts = set()  # 去重

        for i in range(max_scrolls):
            # 检查拦截的 JSONP 数据
            data_batch = driver.execute_script("return window.__intercepted_data || [];")
            if data_batch:
                driver.execute_script("window.__intercepted_data = [];")

                for data in data_batch:
                    if not isinstance(data, dict):
                        continue
                    rate_list = data.get('data', {}).get('rateList', [])
                    if rate_list:
                        new_reviews = self.parse_rate_list(
                            rate_list, product_id, product_url, product_name)
                        # 去重
                        for r in new_reviews:
                            text_key = r["review_text"][:100]
                            if text_key not in seen_texts:
                                seen_texts.add(text_key)
                                reviews.append(r)

                logger.info(f"第{i+1}轮: 累计 {len(reviews)} 条评论")

                if len(reviews) >= max_reviews:
                    break

            # 检查 XHR 拦截数据
            xhr_batch = driver.execute_script("return window.__captured_xhr || [];")
            if xhr_batch:
                driver.execute_script("window.__captured_xhr = [];")
                for cap in xhr_batch:
                    if not isinstance(cap, dict):
                        continue
                    cap_data = cap.get("data", cap)
                    if not isinstance(cap_data, dict):
                        continue
                    rate_list = cap_data.get("data", {}).get("rateList", [])
                    if not rate_list:
                        rate_list = cap_data.get("rateList", [])
                    if rate_list:
                        new_reviews = self.parse_rate_list(
                            rate_list, product_id, product_url, product_name)
                        for r in new_reviews:
                            text_key = r["review_text"][:100]
                            if text_key not in seen_texts:
                                seen_texts.add(text_key)
                                reviews.append(r)

                if len(reviews) >= max_reviews:
                    break

            # 执行滚动
            try:
                driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight;", container)
                time.sleep(self.delay)

                # 检查是否真的滚动了
                current_scroll_top = driver.execute_script(
                    "return arguments[0].scrollTop;", container)

                if current_scroll_top == last_scroll_top:
                    retry_count += 1
                    if retry_count > 3:
                        logger.info("没有更多内容加载（滚动位置未变化），停止")
                        break
                else:
                    retry_count = 0

                last_scroll_top = current_scroll_top

            except Exception as e:
                logger.error(f"滚动时发生错误: {e}")
                break

    def _scroll_main_page(self, driver, max_reviews: int,
                         product_id: str, product_url: str,
                         product_name: str, reviews: list):
        """滚动主页面（无法找到容器时的备选方案）"""
        seen_texts = set()
        for i in range(5):
            # 检查拦截数据
            data_batch = driver.execute_script("return window.__intercepted_data || [];")
            if data_batch:
                driver.execute_script("window.__intercepted_data = [];")
                for data in data_batch:
                    if not isinstance(data, dict):
                        continue
                    rate_list = data.get('data', {}).get('rateList', [])
                    if rate_list:
                        new_reviews = self.parse_rate_list(
                            rate_list, product_id, product_url, product_name)
                        for r in new_reviews:
                            text_key = r["review_text"][:100]
                            if text_key not in seen_texts:
                                seen_texts.add(text_key)
                                reviews.append(r)

            if len(reviews) >= max_reviews:
                break

            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(1.5)

    def _extract_from_intercepted(self, driver, product_id: str,
                                  product_url: str, product_name: str) -> list:
        """从 JSONP 拦截数据中提取评论"""
        reviews = []
        data_batch = driver.execute_script("return window.__intercepted_data || [];")
        if data_batch:
            logger.info(f"JSONP 拦截到 {len(data_batch)} 个数据包")
            seen_texts = set()
            for data in data_batch:
                if not isinstance(data, dict):
                    continue
                rate_list = data.get('data', {}).get('rateList', [])
                if rate_list:
                    new_reviews = self.parse_rate_list(
                        rate_list, product_id, product_url, product_name)
                    for r in new_reviews:
                        text_key = r["review_text"][:100]
                        if text_key not in seen_texts:
                            seen_texts.add(text_key)
                            reviews.append(r)
            if reviews:
                logger.info(f"从JSONP拦截获取 {len(reviews)} 条评论")
        return reviews

    def _extract_from_xhr(self, driver, product_id: str,
                         product_url: str, product_name: str) -> list:
        """从 XHR/fetch 拦截数据中提取评论"""
        reviews = []
        xhr_batch = driver.execute_script("return window.__captured_xhr || [];")
        if xhr_batch:
            logger.info(f"XHR/fetch 拦截到 {len(xhr_batch)} 个响应")
            seen_texts = set()
            for cap in xhr_batch:
                if not isinstance(cap, dict):
                    continue
                cap_data = cap.get("data", cap)
                if not isinstance(cap_data, dict):
                    continue
                rate_list = cap_data.get("data", {}).get("rateList", [])
                if not rate_list:
                    rate_list = cap_data.get("rateList", [])
                if rate_list:
                    new_reviews = self.parse_rate_list(
                        rate_list, product_id, product_url, product_name)
                    for r in new_reviews:
                        text_key = r["review_text"][:100]
                        if text_key not in seen_texts:
                            seen_texts.add(text_key)
                            reviews.append(r)
            if reviews:
                logger.info(f"从XHR拦截获取 {len(reviews)} 条评论")
        return reviews

    def _save_fresh_cookies(self, driver):
        """保存最新的浏览器 Cookie"""
        try:
            selenium_cookies = driver.get_cookies()
            fresh_cookies = {}
            for c in selenium_cookies:
                name = c.get("name", "")
                value = c.get("value", "")
                if name and value:
                    fresh_cookies[name] = value
            if fresh_cookies:
                cookie_dir = os.path.join(_PROJECT_ROOT, "cookies")
                os.makedirs(cookie_dir, exist_ok=True)
                cookie_path = os.path.join(cookie_dir, "taobao_cookies.json")
                with open(cookie_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "platform": "taobao",
                        "cookies": fresh_cookies,
                        "saved_at": time.time(),
                        "source": "jsonp_scraper",
                    }, f, ensure_ascii=False, indent=2)
                logger.info(f"已保存最新Cookie ({len(fresh_cookies)} 个)")
        except Exception as e:
            logger.warning(f"保存Cookie失败: {e}")

    @staticmethod
    def _validate_reviews(reviews: list) -> list:
        """反虚假评论验证 — 过滤空评论和重复"""
        valid = []
        seen = set()
        for r in reviews:
            text = r.get("review_text", "").strip()
            if not text or len(text) < 2:
                continue
            # 去重
            text_key = text[:150].lower()
            if text_key in seen:
                continue
            seen.add(text_key)
            # 标记为真实评论
            r["is_demo"] = False
            valid.append(r)
        return valid

    # ------------------------------------------------------------------
    # 远程调试模式（原 taobao-xhs-crawler 方式）
    # ------------------------------------------------------------------
    def scrape_with_remote_debug(
        self,
        product_url: str,
        debug_port: int = 9222,
        max_reviews: int = 50,
    ) -> List[Dict]:
        """
        远程调试模式：连接到已经打开的 Chrome 浏览器

        使用前需要先手动启动 Chrome:
          chrome.exe --remote-debugging-port=9222 --user-data-dir="D:\\selenium_profiles\\taobao_profile"

        然后在浏览器中手动登录淘宝，再调用此方法。

        这是 taobao-xhs-crawler 原始项目的工作方式，
        适合需要完全控制浏览器环境的场景。

        :param product_url: 商品 URL
        :param debug_port: Chrome 远程调试端口
        :param max_reviews: 最大评论数
        :return: 评论列表
        """
        # URL 清洗
        product_url = self.clean_url(product_url)
        if not product_url:
            return []

        # 短链解析
        if 'tb.cn' in product_url or 'tb.com' in product_url:
            _, item_id = self.resolve_short_link(product_url)
            if item_id:
                product_url = f"https://item.taobao.com/item.htm?id={item_id}"
        else:
            item_id = self.parse_item_id(product_url)

        if not item_id:
            logger.error("无法提取商品ID")
            return []

        # 连接到已打开的 Chrome
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError:
            logger.error("Selenium 未安装")
            return []

        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", f"localhost:{debug_port}")

        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.error(f"无法连接到 Chrome (端口 {debug_port}): {e}")
            logger.error("请先启动 Chrome: chrome.exe --remote-debugging-port=9222 "
                        "--user-data-dir=\"D:\\selenium_profiles\\taobao_profile\"")
            return []

        reviews = []
        product_name = ""
        product_page_url = f"https://item.taobao.com/item.htm?id={item_id}"

        try:
            # 打开商品页面
            logger.info(f"打开商品页面: {product_page_url}")
            driver.get(product_page_url)

            # 注入 JSONP 拦截器
            driver.execute_script(self.get_jsonp_interceptor_js())

            # 滚动主页面
            driver.execute_script("window.scrollTo(0, 1000);")
            time.sleep(2)

            # 点击"查看全部"
            try:
                wait = WebDriverWait(driver, 10)
                for css in self.SHOW_ALL_BUTTON_SELECTORS:
                    try:
                        btn = driver.find_element(By.CSS_SELECTOR, css)
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].click();", btn)
                            logger.info("点击'查看全部'成功")
                            break
                    except Exception:
                        continue
            except Exception:
                logger.warning("未找到'查看全部'按钮")

            time.sleep(3)

            # 再次注入拦截器
            driver.execute_script(self.get_jsonp_interceptor_js())

            # 获取商品名
            try:
                product_name = driver.title.split("-")[0].strip()
            except Exception:
                pass

            # 查找可滚动容器
            container = self.find_scrollable_element(driver)

            if container:
                self._scroll_and_collect(driver, container, max_reviews,
                                        item_id, product_page_url, product_name, reviews)
            else:
                logger.warning("未找到可滚动容器")
                self._scroll_main_page(driver, max_reviews, item_id,
                                      product_page_url, product_name, reviews)

            # 从拦截数据提取
            if not reviews:
                reviews = self._extract_from_intercepted(driver, item_id,
                                                         product_page_url, product_name)

            if not reviews:
                reviews = self._extract_from_xhr(driver, item_id,
                                                product_page_url, product_name)

            # DOM 回退
            if not reviews:
                from scrapers.taobao_scraper import TaobaoScraper
                ts = TaobaoScraper()
                page_source = driver.page_source
                reviews = ts._extract_reviews_from_dom(
                    page_source, product_page_url, item_id, product_name)
                for r in reviews:
                    r["extraction_method"] = "dom_fallback"

            reviews = self._validate_reviews(reviews)
            logger.info(f"远程调试模式抓取完成: {len(reviews)} 条评论")

        except Exception as e:
            logger.error(f"远程调试抓取异常: {e}")
        finally:
            # 注意：远程调试模式不关闭浏览器（driver.quit() 会关闭用户的浏览器）
            pass

        return reviews[:max_reviews]
