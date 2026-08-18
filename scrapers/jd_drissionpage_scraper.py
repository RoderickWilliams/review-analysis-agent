"""
京东评论抓取器 — DrissionPage 版
================================
基于 DrissionPage 驱动真实 Chrome 浏览器，绕过京东反爬机制。

核心原理：
  1. DrissionPage 控制的是用户系统中安装的真实 Chrome（非自动化浏览器）
  2. 持久化 chrome_profile 保留登录 Cookie，跨 session 复用
  3. 手动扫码登录，不保存密码
  4. 评论通过"全部评论"弹窗虚拟滚动逐屏采集（DOM 提取，不走 API）
  5. 滑块验证码检测 + 蜂鸣提示等待人工通过
  6. DOM 提取失败时自动截图兜底（配合 screenshot_analyzer OCR）

与 JD_Spider (https://github.com/LacYCle/JD_Spider) 的关系：
  - 借鉴其 DrissionPage + 真实 Chrome + 持久化 profile + 虚拟滚动方案
  - 适配本项目的评论格式（15 个溯源字段）
  - 增加截图兜底、评级/日期/SKU 等字段提取
  - 集成到 Streamlit 应用而非独立 CLI
"""

import json
import os
import random
import re
import tempfile
import time

# 文件日志（用于调试卡死问题）
import os as _os
_LOG_FILE = "jd_dp_debug.log"
def _dlog(msg):
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as _f:
            _f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass
    print("[jd-dp] %s" % msg)
import winsound
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / "playwright-data" / "jd-dp-profile"
COOKIE_FILE = PROJECT_ROOT / "playwright-data" / "jd_cookies.json"
SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "jd_screenshots"


def _import_drissionpage():
    """延迟导入 DrissionPage，给出友好的安装提示。"""
    try:
        from DrissionPage import Chromium, ChromiumOptions
        return Chromium, ChromiumOptions
    except ImportError:
        raise ImportError(
            "需要安装 DrissionPage：\n"
            "  pip install DrissionPage\n"
            "并确保系统已安装 Google Chrome 浏览器。"
        )


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

JD_HOMEPAGE = "https://www.jd.com/"

# 登录检测
LOGIN_USER_XPATH = "x://div[@id='J_user']"
LOGOUT_LINK_XPATH = "x://div[@id='J_user']//a[contains(@class,'user_logout')][1]"

# 商品详情页评论区
COMMENT_ROOT_XPATH = "x://div[@id='comment-root']"
ALL_BTN_XPATH = 'x://div[@id="comment-root"]//div[@class="all-btn"]'
# 弹窗选择器：匹配 rateListBox（CSS hash 可能变动），不含过宽的 comment-list
RATE_LIST_XPATH = 'x://div[contains(@class,"_rateListBox_") or contains(@class,"rateListBox")]'
# 兜底弹窗选择器（多个备选）
RATE_LIST_XPATH_FALLBACKS = [
    'x://div[contains(@class,"_rateListBox_")]',
    'x://div[contains(@class,"rateListBox")]',
    'x://div[contains(@class,"jdc-page-overlay")]',
    'x://div[contains(@class,"comment-list") and contains(@class,"overlay")]',
]

# 评论卡片 — 优先带 data-index 的，但也接受其他评论卡片
RATE_CARD_CSS = "css:div[data-index]"
RATE_DESC_CSS = "css:span.jdc-pc-rate-card-main-desc"

# 也尝试更通用的选择器（京东可能改版）
RATE_CARD_CSS_FALLBACKS = [
    "css:div[data-index]",
    "css:div[class*='rate-card']",
    "css:.comment-item",
    "css:div[class*='comment-item']",
    "css:.J-comments-list .comment-item",
    "css:div[class*='CommentItem']",
]
RATE_DESC_CSS_FALLBACKS = [
    "css:span.jdc-pc-rate-card-main-desc",
    "css:span[class*='rate-card-main-desc']",
    "css:.comment-con",
    "css:p.comment-con",
    "css:.comment-item p",
    "css:.J_commentsList .comment-con",
    "css:[class*='comment-con']",
    "css:[class*='CommentContent']",
    "css:[class*='review-content']",
    "css:.rate-content",
    "css:.evaluation-content",
]

# 虚拟滚动稳定判定
MAX_STALL_ROUNDS = 8
MAX_SCROLL_ROUNDS = 2000

# 快速验证滑块检测
VERIFY_TEXT_KEYWORDS = (
    "拖动滑块", "请拖动滑块", "向右滑动", "滑动完成验证",
    "请完成验证", "快速验证", "滑动解锁",
)
VERIFY_CLASS_PATTERN = re.compile(r"(captcha|geetest)", re.I)
VERIFY_IFRAME_PATTERN = re.compile(r"(verify|captcha|geetest|slider)", re.I)

VERIFY_DETECT_JS = r"""
(() => {
  for (const f of document.querySelectorAll('iframe')) {
    const s = (f.src || '') + ' ' + (f.className || '') + ' ' + (f.id || '');
    if (/%s/i.test(s)) return true;
  }
  for (const n of document.querySelectorAll('div,section,iframe')) {
    const c = (n.className && String(n.className)) || '';
    if (/%s/i.test(c + ' ' + (n.id || ''))) return true;
  }
  const body = document.body && document.body.innerText;
  if (body && body.length <= 50000) {
    const kws = %s;
    for (const kw of kws) if (body.includes(kw)) return true;
  }
  return false;
})()
""" % (
    VERIFY_IFRAME_PATTERN.pattern,
    VERIFY_CLASS_PATTERN.pattern,
    json.dumps(list(VERIFY_TEXT_KEYWORDS), ensure_ascii=False),
)


class JDDrissionPageScraper:
    """基于 DrissionPage 的京东评论抓取器。"""

    def __init__(
        self,
        max_reviews: int = 50,
        headless: bool = False,
        screenshot_dir: Optional[str] = None,
        login_timeout: int = 180,
    ):
        """
        :param max_reviews: 最多采集评论条数
        :param headless: 是否无头模式（默认 False，需要用户扫码登录）
        :param screenshot_dir: 截图保存目录（默认系统临时目录）
        :param login_timeout: 等待登录超时秒数
        """
        self.max_reviews = max_reviews
        self.headless = headless
        self.login_timeout = login_timeout
        self._screenshot_dir = Path(screenshot_dir) if screenshot_dir else SCREENSHOT_DIR
        self._screenshots: List[str] = []
        self._browser = None
        self._tab = None
        self._product_name = ""

    # ------------------------------------------------------------------
    # 浏览器生命周期
    # ------------------------------------------------------------------

    def _start_browser(self):
        """启动 Chrome 浏览器（持久化 profile）。"""
        Chromium, ChromiumOptions = _import_drissionpage()
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        co = ChromiumOptions()
        co.set_argument(f"--user-data-dir={str(PROFILE_DIR)}")
        co.set_argument("--disable-blink-features=AutomationControlled")
        co.set_argument("--disable-features=PrivacySandboxSettings4")
        co.set_argument("--no-first-run")
        co.set_argument("--disable-infobars")
        # 强制中文语言环境，防止 AJAX 动态内容出现 GBK 乱码
        co.set_argument("--lang=zh-CN")
        co.set_argument("--accept-lang=zh-CN,zh;q=0.9,en;q=0.8")
        # 京东域名直连绕过系统代理（逗号分隔，Chrome 规范）：
        #   1) 代理不碰京东流量 → 不会篡改 HTTPS 响应 charset → 解决"锟斤拷"乱码
        #   2) 浏览器出口 IP 即用户真实 IP → 内地自动进大陆版、港澳自动进港澳版
        #   3) 其他网站流量仍走系统代理，不受影响
        co.set_argument("--proxy-bypass-list=jd.com,*.jd.com,jd.hk,*.jd.hk,360buyimg.com,*.360buyimg.com,jdcdn.com,*.jdcdn.com,jcloudcs.com,*.jcloudcs.com,jcloud.com,*.jcloud.com,<local>")
        if self.headless:
            co.headless()

        self._browser = Chromium(co)
        self._tab = self._browser.new_tab()
        # 设置页面加载策略为 eager：等 DOMContentLoaded 但不等 load 事件，
        # 避免京东第三方资源加载不完导致卡死，同时保证 JS 上下文可用
        try:
            self._tab.set.load_mode.eager()
        except Exception:
            try:
                self._tab.load_mode.eager()
            except Exception:
                pass
        # 缩短全局超时
        try:
            self._tab.set.timeouts(base=10, page_load=20, script=15)
        except Exception:
            pass
        print("[jd-dp] 浏览器已启动（profile: %s）" % PROFILE_DIR)

    def _close_browser(self):
        """关闭浏览器。"""
        try:
            if self._browser:
                self._browser.quit()
        except Exception:
            pass
        self._browser = None
        self._tab = None

    # ------------------------------------------------------------------
    # 登录检测
    # ------------------------------------------------------------------

    def _detect_region(self) -> str:
        """检测当前是大陆版还是港澳版。返回 'mainland' 或 'hk'。"""
        try:
            url = self._tab.url or ""
            if "jd.hk" in url or "hk.jd.com" in url:
                return "hk"
        except Exception:
            pass
        return "mainland"

    def _is_logged_in(self) -> bool:
        """检测当前页面是否已登录京东（支持大陆版和港澳版）。"""
        # 1. Cookie 检测（两版本通用，最可靠）
        try:
            cookies = self._tab.cookies(all_domains=True)
            for c in cookies:
                name = c.get("name", "")
                value = c.get("value", "")
                if name in ("pt_key", "pt_pin", "thor") and value:
                    return True
        except Exception:
            pass

        # 2. 大陆版 DOM 检测
        if self._detect_region() == "mainland":
            try:
                if self._tab.wait.ele_displayed(LOGIN_USER_XPATH, timeout=2):
                    logout = self._tab.ele(LOGOUT_LINK_XPATH, timeout=1)
                    if logout:
                        return True
            except Exception:
                pass
        else:
            # 3. 港澳版 DOM 检测：检查是否有用户昵称/我的账户等元素
            try:
                for xpath in (
                    "x://a[contains(@class,'nickname')]",
                    "x://span[contains(@class,'user-name')]",
                    "x://a[contains(text(),'我的订单')]",
                    "x://a[contains(text(),'我的京东')]",
                    "x://div[contains(@class,'userinfo')]//a",
                ):
                    ele = self._tab.ele(xpath, timeout=1)
                    if ele and ele.text.strip():
                        txt = ele.text.strip()
                        if "登录" not in txt and "注册" not in txt and len(txt) > 0:
                            return True
            except Exception:
                pass
        return False

    def _ensure_logged_in(self) -> bool:
        """确保已登录，未登录则打开登录页等待用户扫码（支持大陆/港澳版）。"""
        if self._is_logged_in():
            print("[jd-dp] 已检测到登录态")
            return True

        region = self._detect_region()
        print("[jd-dp] 未登录，当前版本: %s，打开登录页..." % ("港澳版" if region == "hk" else "大陆版"))

        # 两版本都用统一的 passport.jd.com 登录
        login_urls = [
            "https://passport.jd.com/new/login.aspx",
            "https://passport.jd.com/uc/login",
        ]
        if region == "hk":
            # 港澳版可能有自己的登录入口
            login_urls.insert(0, "https://passport.jd.com/new/login.aspx?ReturnURL=https%3A%2F%2Fwww.jd.hk%2F")

        for login_url in login_urls:
            try:
                self._tab.get(login_url)
                time.sleep(3)
                # 检查页面是否正常加载（非空白/非乱码）
                title = self._tab.title or ""
                if "京东" in title or "登录" in title or "login" in title.lower():
                    break
                print("[jd-dp] 登录页加载异常，尝试下一个地址...")
            except Exception as e:
                print("[jd-dp] 打开登录页失败: %s" % e)
                continue

        start = time.time()
        while time.time() - start < self.login_timeout:
            if self._is_logged_in():
                print("[jd-dp] 登录成功！")
                self._save_cookies()
                return True
            time.sleep(2)

        print("[jd-dp] 等待登录超时（%d 秒）" % self.login_timeout)
        return False

    def _save_cookies(self):
        """保存当前 cookies 到文件。"""
        try:
            cookies = self._tab.cookies(all_domains=True, all_info=True)
            cookie_list = [dict(c) for c in cookies]
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIE_FILE.write_text(
                json.dumps(cookie_list, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("[jd-dp] Cookies 已保存（%d 条）" % len(cookie_list))
        except Exception as e:
            print("[jd-dp] 保存 cookies 失败: %s" % e)

    # ------------------------------------------------------------------
    # 滑块验证检测
    # ------------------------------------------------------------------

    def _verify_detected(self) -> bool:
        """检测页面是否出现滑块验证。"""
        try:
            return bool(self._tab.run_js(VERIFY_DETECT_JS))
        except Exception:
            return False

    def _wait_manual_verify(self, max_wait: int = 120) -> bool:
        """检测到滑块后蜂鸣提示，等待人工通过。"""
        print("[jd-dp] ⚠ 检测到滑块验证，请手动拖动！")
        for _ in range(3):
            try:
                winsound.MessageBeep()
            except Exception:
                pass
            time.sleep(0.3)

        start = time.time()
        while self._verify_detected():
            time.sleep(2)
            if time.time() - start > max_wait:
                print("[jd-dp] 等待滑块验证超时")
                return False
        print("[jd-dp] 滑块验证已通过")
        return True

    def _handle_verify(self) -> bool:
        """检查并处理滑块验证。"""
        if self._verify_detected():
            return self._wait_manual_verify()
        return True

    # ------------------------------------------------------------------
    # 商品 ID 提取
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_product_id(url: str) -> str:
        """从京东商品 URL 提取商品 ID（支持大陆版 jd.com 和港澳版 jd.hk）。"""
        # 港澳版: hk.jd.com/Product-100012345678.html 或 www.jd.hk/product/...
        m = re.search(r"jd\.hk/[^\d]*(\d{5,})", url)
        if m:
            return m.group(1)
        m = re.search(r"item\.jd\.com/(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"hk\.jd\.com/(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"/(\d{5,})\.html", url)
        if m:
            return m.group(1)
        m = re.search(r"sku=(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"product/(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"(\d{6,})", url)
        if m:
            return m.group(1)
        return ""

    # ------------------------------------------------------------------
    # 评论弹窗虚拟滚动采集
    # ------------------------------------------------------------------

    @staticmethod
    def _scroll_overlay_js() -> str:
        """增量滚动评论弹窗：遍历所有可滚动容器，把内容向下滚一屏。
        不依赖特定 class 名，兼容京东新版弹窗 DOM 结构。"""
        return """
        return (function(){
            // 1. 先找评论卡片（任意容器内）
            var cards = document.querySelectorAll('div[data-index], [class*="rate-card"], [class*="comment-item"], [class*="CommentItem"]');
            if (cards.length < 1) return false;

            // 2. 从最后一张卡片向上找可滚动的祖先容器
            var lastCard = cards[cards.length - 1];
            var scroller = null;
            var node = lastCard.parentElement;
            while (node && node !== document.body) {
                var st = getComputedStyle(node);
                if ((st.overflowY === 'auto' || st.overflowY === 'scroll')
                        && node.scrollHeight > node.clientHeight + 50) {
                    scroller = node;
                    break;
                }
                node = node.parentElement;
            }

            // 3. 如果找到了可滚动容器，把最后一张卡片滚到视口
            if (scroller) {
                lastCard.scrollIntoView({block: 'center', behavior: 'instant'});
                return true;
            }

            // 4. 兜底：找页面上任意可滚动容器（通常是弹窗主体），滚到底
            var all = document.querySelectorAll('*');
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                var s2 = getComputedStyle(el);
                if ((s2.overflowY === 'auto' || s2.overflowY === 'scroll')
                        && el.scrollHeight > el.clientHeight + 100) {
                    el.scrollTop = el.scrollHeight;
                    return true;
                }
            }

            // 5. 最终兜底：window 滚动
            window.scrollBy(0, 800);
            return true;
        })();
        """

    def _find_overlay(self, timeout: float = 2.0):
        """尝试多个选择器找到评论弹窗 overlay，返回元素或 None。"""
        # 先试主选择器
        try:
            overlay = self._tab.ele(RATE_LIST_XPATH, timeout=timeout)
            if overlay:
                return overlay
        except Exception:
            pass
        # 试兜底选择器
        for fb_xpath in RATE_LIST_XPATH_FALLBACKS:
            if fb_xpath == RATE_LIST_XPATH:
                continue
            try:
                overlay = self._tab.ele(fb_xpath, timeout=1.0)
                if overlay:
                    return overlay
            except Exception:
                continue
        return None

    def _find_cards(self, overlay, timeout: float = 1.0):
        """从 overlay 中尝试多个选择器提取评论卡片，返回列表。"""
        for card_css in RATE_CARD_CSS_FALLBACKS:
            try:
                cards = overlay.eles(card_css, timeout=timeout)
                if cards:
                    return cards
            except Exception:
                continue
        return []

    def _extract_reviews_from_popup(self, product_url: str, product_id: str) -> List[Dict]:
        """
        在评论弹窗中虚拟滚动，逐屏采集评论。

        返回统一格式的评论字典列表。
        """
        reviews: Dict[int, Dict] = {}
        last_count = 0
        stall = 0
        rounds = 0

        while rounds < MAX_SCROLL_ROUNDS:
            rounds += 1

            # 每 5 轮检查滑块
            if rounds % 5 == 0:
                self._handle_verify()

            # 读取当前可见评论卡片（使用 _find_overlay + _find_cards 避免长超时）
            overlay = self._find_overlay(timeout=1.5)
            if overlay:
                cards = self._find_cards(overlay, timeout=1.0)
                for card in cards:
                    try:
                        idx_attr = card.attr("data-index")
                        if idx_attr and str(idx_attr).isdigit():
                            idx = int(idx_attr)
                        else:
                            # 无 data-index 时用内容哈希作为 key
                            raw_text = card.text[:80] if card.text else ""
                            idx = abs(hash(raw_text)) % (10**8)
                        if idx in reviews:
                            continue

                        # 提取评论文本
                        text = ""
                        for desc_sel in RATE_DESC_CSS_FALLBACKS:
                            try:
                                desc_ele = card.ele(desc_sel, timeout=0.3)
                                if desc_ele:
                                    text = desc_ele.text.strip()
                                    if text:
                                        break
                            except Exception:
                                continue

                        if not text or len(text) < 5:
                            continue

                        # 尝试提取评分（星级）
                        rating = 5
                        try:
                            star_ele = card.ele("css:.star", timeout=0.2)
                            if star_ele:
                                cls = star_ele.attr("class") or ""
                                m = re.search(r"star(\d)", cls)
                                if m:
                                    rating = int(m.group(1))
                        except Exception:
                            pass

                        # 尝试提取日期
                        review_date = ""
                        try:
                            date_ele = card.ele(
                                "css:.order-info span, .comment-date, .date",
                                timeout=0.2,
                            )
                            if date_ele:
                                review_date = date_ele.text.strip()
                        except Exception:
                            pass

                        # 尝试提取用户名
                        user_name = "匿名用户"
                        try:
                            user_ele = card.ele(
                                "css:.user-info, .u-name, .nickname",
                                timeout=0.2,
                            )
                            if user_ele:
                                user_name = user_ele.text.strip() or "匿名用户"
                        except Exception:
                            pass

                        # 尝试提取 SKU 信息
                        sku = ""
                        try:
                            sku_ele = card.ele(
                                "css:.sku-info, .J_order_type",
                                timeout=0.2,
                            )
                            if sku_ele:
                                sku = sku_ele.text.strip()
                        except Exception:
                            pass

                        reviews[idx] = self._format_review(
                            text=text,
                            rating=rating,
                            user_name=user_name,
                            review_date=review_date,
                            sku=sku,
                            product_id=product_id,
                            product_url=product_url,
                            index=idx,
                        )
                    except Exception as e:
                        print("[jd-dp] 解析评论卡片异常: %s" % e)
                        continue

            # 上限判定
            if len(reviews) >= self.max_reviews:
                print("[jd-dp] 达到采集上限 %d 条" % self.max_reviews)
                break

            # 推进判定：跟踪评论数量变化
            cur_count = len(reviews)
            if cur_count > last_count:
                last_count = cur_count
                stall = 0
            else:
                stall += 1

            if stall >= MAX_STALL_ROUNDS:
                print("[jd-dp] 评论已到底，共采集 %d 条" % len(reviews))
                break

            # 增量滚动
            try:
                self._tab.run_js(self._scroll_overlay_js())
            except Exception:
                pass

            # 等待新评论加载（短轮询，最多等 2 秒）
            pre_count = len(reviews)
            wait_until = time.time() + 2.0
            while time.time() < wait_until:
                time.sleep(0.2)
                try:
                    ov = self._find_overlay(timeout=0.3)
                    if ov:
                        cur_cards = self._find_cards(ov, timeout=0.3)
                        if len(cur_cards) > pre_count:
                            break
                except Exception:
                    pass

        return list(reviews.values())[:self.max_reviews]

    # ------------------------------------------------------------------
    # 截图兜底
    # ------------------------------------------------------------------

    def _capture_screenshots(self, product_url: str, product_id: str, max_shots: int = 5) -> List[str]:
        """DOM 提取失败时，滚动评论区逐屏截图保存。"""
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshots = []

        try:
            # 尝试滚动评论弹窗
            for i in range(max_shots):
                shot_path = str(
                    self._screenshot_dir / f"jd_dp_{product_id}_{int(time.time())}_{i}.png"
                )
                try:
                    self._tab.get_screenshot(path=shot_path, full_page=False)
                    screenshots.append(shot_path)
                    print("[jd-dp] 截图 %d: %s" % (i + 1, shot_path))
                except Exception as e:
                    print("[jd-dp] 截图失败: %s" % e)

                # 滚动
                try:
                    self._tab.run_js(self._scroll_overlay_js())
                except Exception:
                    try:
                        self._tab.scroll.down(3)
                    except Exception:
                        pass
                time.sleep(0.4)
        except Exception as e:
            print("[jd-dp] 截图兜底异常: %s" % e)

        self._screenshots = screenshots
        return screenshots

    # ------------------------------------------------------------------
    # 评论格式化
    # ------------------------------------------------------------------

    def _format_review(
        self,
        text: str,
        rating: int,
        user_name: str,
        review_date: str,
        sku: str,
        product_id: str,
        product_url: str,
        index: int = 0,
    ) -> Dict:
        """统一评论格式，与项目其他 scraper 输出兼容。"""
        return {
            "review_text": self._clean_text(text),
            "rating": rating,
            "platform": "jd",
            "timestamp": review_date,
            "user_id": user_name,
            "product_name": self._product_name,
            "source_platform": "jd",
            "source_url": product_url,
            "product_id": product_id,
            "review_permalink": f"{product_url}#comment-{index}",
            "reviewer_name": user_name,
            "reviewer_id": "",
            "review_date": review_date,
            "sku": sku,
            "is_demo": False,
            "extraction_method": "drissionpage_dom",
        }

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", str(text))
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ------------------------------------------------------------------
    # 主抓取流程
    # ------------------------------------------------------------------

    def scrape(self, product_url: str, cookies: Optional[Dict] = None,
               max_reviews: Optional[int] = None) -> List[Dict]:
        """
        抓取京东商品评论。

        :param product_url: 京东商品详情页 URL
        :param cookies: 可选 cookies（目前通过持久化 profile 管理，此参数保留兼容）
        :param max_reviews: 覆盖实例的 max_reviews
        :return: 评论字典列表
        """
        if max_reviews is not None:
            self.max_reviews = max_reviews

        product_id = self._extract_product_id(product_url)
        if not product_id:
            print("[jd-dp] 无法从 URL 提取商品 ID: %s" % product_url)
            return []

        reviews: List[Dict] = []

        try:
            # 1. 启动浏览器
            self._start_browser()

            # 2. 先访问京东首页
            print("[jd-dp] 打开京东首页...")
            self._tab.get(JD_HOMEPAGE)
            try:
                self._tab.wait.doc_loaded(timeout=10)
            except Exception:
                pass
            time.sleep(random.uniform(0.5, 1.0))

            # 3. 确保已登录
            if not self._ensure_logged_in():
                print("[jd-dp] 登录失败，无法继续")
                return []

            # 4. 访问商品详情页
            print("[jd-dp] 打开商品页: %s" % product_url)
            self._tab.get(product_url)
            # load_mode=none 后，get() 可能在 DOM 还没解析完就返回，
            # 显式等待 document.readyState 至少为 interactive
            try:
                self._tab.wait.doc_loaded(timeout=15)
            except Exception:
                pass
            # 等待 body 出现
            try:
                self._tab.wait.ele_displayed("css:body", timeout=10)
            except Exception:
                pass
            time.sleep(random.uniform(1.5, 2.5))

            # 检测是否被重定向到港澳版
            region = self._detect_region()
            if region == "hk":
                print("[jd-dp] 当前为港澳版京东，适配港澳版页面结构")

            # 处理可能的滑块
            self._handle_verify()

            # 5. 获取商品名称 — 优先用页面 title（最可靠），再尝试 DOM 选择器
            try:
                # 方式1：从页面 title 提取（京东 title 格式：商品名【...】-京东）
                page_title = ""
                try:
                    page_title = self._tab.title or ""
                except Exception:
                    pass
                if page_title:
                    # 去掉 "-京东" 后缀和【...】中的价格/品牌信息
                    name = page_title.split("-京东")[0].split("-")[0].split("·")[0].strip()
                    # 去掉 【...】 后缀
                    name = re.sub(r'【.*?】.*$', '', name).strip()
                    if name and len(name) >= 2:
                        self._product_name = name
                        print(f"[jd-dp] 商品名(title): {self._product_name}")

                # 方式2：DOM 选择器（仅当 title 提取失败时）
                if not self._product_name or len(self._product_name) < 2:
                    title_selectors = (
                        "css:#name h1",
                        "css:.itemInfo-wrap .sku-name",
                        "css:.product-intro .sku-name",
                        "css:[class*='goodsName']",
                        "css:[class*='product-name']",
                        "css:h1",
                    )
                    for ts in title_selectors:
                        title_ele = self._tab.ele(ts, timeout=2)
                        if title_ele:
                            txt = title_ele.text.strip()
                            if txt and len(txt) > 2:
                                candidate = txt.split("\n")[0].strip()
                                if len(candidate) >= 4:
                                    self._product_name = candidate
                                    break
            except Exception:
                pass

            # 6. 滚动页面触发评论区加载（多滚几次确保评论区进入视口）
            print("[jd-dp] 滚动页面加载评论区...")
            for _ in range(4):
                try:
                    self._tab.scroll.down(8)
                except Exception:
                    pass
                time.sleep(random.uniform(0.5, 1.0))

            # 7. 等待评论区出现（大陆版 + 港澳版多种选择器）
            comment_root = None
            for cr_xpath in (
                COMMENT_ROOT_XPATH,
                "x://div[@id='comment']",
                "x://div[contains(@class,'comment')]",
                "x://div[contains(@class,'Comment')]",
                "x://div[contains(@id,'comment')]",
                "x://div[contains(@class,'review')]",
                "x://div[contains(@class,'evaluation')]",
            ):
                try:
                    comment_root = self._tab.ele(cr_xpath, timeout=1.5)
                    if comment_root:
                        break
                except Exception:
                    continue

            if not comment_root:
                print("[jd-dp] 未找到评论区，保存页面HTML用于诊断...")
                self._dump_page_html(product_id)
                print("[jd-dp] 尝试从页面全局提取评论...")
                reviews = self._extract_reviews_global(product_url, product_id)
                if reviews:
                    print("[jd-dp] 全局提取到 %d 条评论" % len(reviews))
                    return reviews
                print("[jd-dp] 全局提取失败，截图兜底")
                self._capture_screenshots(product_url, product_id)
                return []

            # 8. 先用 JS 直接从页面 DOM 提取评论（最可靠，不依赖 CSS 选择器）
            _dlog("尝试 JS 直接提取评论...")
            reviews = self._extract_reviews_via_js(product_url, product_id)
            _dlog("JS 直接提取返回 %d 条" % len(reviews) if reviews else "JS 直接提取返回 0 条")
            if reviews and len(reviews) >= 3:
                _dlog("JS 提取到 %d 条评论，直接返回" % len(reviews))
                return reviews

            # 9. 页面直接提取不足，尝试点击"全部评价"打开弹窗
            _dlog("页面评论不足，尝试点击'全部评价'打开弹窗...")
            all_btn = None
            for btn_xpath in (
                ALL_BTN_XPATH,
                "x://a[contains(text(),'全部评价')]",
                "x://a[contains(text(),'全部评论')]",
                "x://a[contains(text(),'查看全部')]",
                "x://a[contains(text(),'更多评价')]",
                "x://span[contains(text(),'全部评价')]",
                "x://div[contains(text(),'全部评价')]",
                "x://a[contains(@class,'all-btn')]",
                "x://div[contains(@class,'all-btn')]",
            ):
                try:
                    all_btn = self._tab.ele(btn_xpath, timeout=1.5)
                    if all_btn:
                        break
                except Exception:
                    continue

            if all_btn:
                try:
                    _dlog("准备点击'全部评价'...")
                    # 滚动到按钮位置确保可见
                    try:
                        all_btn.scroll.to_see()
                    except Exception:
                        pass
                    time.sleep(0.5)
                    old_url = self._tab.url or ""
                    all_btn.click()
                    _dlog("已点击'全部评价'，等待弹窗/页面加载...")
                    # 等待：可能弹窗打开，也可能页面导航
                    time.sleep(3)
                    new_url = self._tab.url or ""
                    if new_url != old_url:
                        _dlog("页面导航到: %s" % new_url)
                        # 页面发生了导航，等待 DOM 就绪
                        try:
                            self._tab.wait.doc_loaded(timeout=15)
                        except Exception:
                            pass
                        time.sleep(2)
                    else:
                        _dlog("URL未变化，等待弹窗渲染...")
                        time.sleep(2)
                except Exception as e:
                    _dlog("点击全部评价失败: %s" % e)
                    import traceback; traceback.print_exc()
            else:
                _dlog("未找到'全部评价'按钮")

            # 处理滑块
            _dlog("检查滑块验证...")
            self._handle_verify()
            _dlog("滑块检查完成")

            # 9.5 诊断：dump 弹窗 DOM 结构
            _dlog("弹窗诊断：分析 DOM 结构...")
            try:
                # 用 return 关键字（DrissionPage 要求）
                diag = self._tab.run_js("""
                var report = {scrollables: [], overlays: [], commentEls: [], allClasses: []};
                try {
                  document.querySelectorAll('*').forEach(function(el){
                    var st = getComputedStyle(el);
                    if ((st.overflowY === 'auto' || st.overflowY === 'scroll')
                        && el.scrollHeight > el.clientHeight + 50) {
                      report.scrollables.push({
                        tag: el.tagName,
                        cls: String(el.className||'').substring(0,120),
                        id: el.id||'',
                        sh: el.scrollHeight, ch: el.clientHeight
                      });
                    }
                  });
                } catch(e) { report.err1 = e.message; }
                try {
                  document.querySelectorAll('[class*="overlay"],[class*="Overlay"],[class*="modal"],[class*="Modal"],[class*="popup"],[class*="Popup"],[class*="dialog"],[class*="Dialog"],[role="dialog"]').forEach(function(el){
                    report.overlays.push({
                      tag: el.tagName,
                      cls: String(el.className||'').substring(0,150),
                      id: el.id||'',
                      childCount: el.children.length,
                      textLen: (el.innerText||'').length
                    });
                  });
                } catch(e) { report.err2 = e.message; }
                try {
                  document.querySelectorAll('[class*="comment"],[class*="Comment"],[class*="rate"],[class*="Rate"],[class*="review"],[class*="Review"]').forEach(function(el, i){
                    if (i < 30) {
                      report.commentEls.push({
                        tag: el.tagName,
                        cls: String(el.className||'').substring(0,120),
                        id: el.id||'',
                        textLen: (el.innerText||'').length
                      });
                    }
                  });
                } catch(e) { report.err3 = e.message; }
                return JSON.stringify(report);
                """)
                if diag is None:
                    _dlog("run_js 返回 None! 尝试简单JS测试...")
                    simple = self._tab.run_js("return document.title;")
                    _dlog("document.title = %s" % simple)
                    body_len = self._tab.run_js("return document.body ? document.body.innerHTML.length : 0;")
                    _dlog("body.innerHTML.length = %s" % body_len)
                else:
                    import json as _json
                    diag_data = _json.loads(diag) if isinstance(diag, str) else diag
                    _dlog("可滚动容器数量: %d" % len(diag_data.get("scrollables", [])))
                    for s in diag_data.get("scrollables", [])[:5]:
                        _dlog("  scroll: <%s> cls=%s sh=%d ch=%d" % (s["tag"], s["cls"][:80], s["sh"], s["ch"]))
                    _dlog("overlay数量: %d" % len(diag_data.get("overlays", [])))
                    for o in diag_data.get("overlays", [])[:5]:
                        _dlog("  overlay: <%s> cls=%s children=%d textLen=%d" % (o["tag"], o["cls"][:80], o["childCount"], o["textLen"]))
                    _dlog("评论相关元素数量: %d" % len(diag_data.get("commentEls", [])))
                    for c in diag_data.get("commentEls", [])[:15]:
                        _dlog("  commentEl: <%s> cls=%s textLen=%d" % (c["tag"], c["cls"][:80], c["textLen"]))
                    for ek in ["err1","err2","err3"]:
                        if ek in diag_data:
                            _dlog("JS错误 %s: %s" % (ek, diag_data[ek]))
            except Exception as e:
                _dlog("DOM 诊断失败: %s" % e)
                import traceback; traceback.print_exc()

            # 9.6 保存弹窗区域HTML到文件用于分析
            try:
                html_dump = self._tab.run_js("return document.body ? document.body.innerHTML.substring(0, 80000) : '';")
                if html_dump:
                    dump_path = "jd_popup_dump.html"
                    with io.open(dump_path, "w", encoding="utf-8") as df:
                        df.write(html_dump)
                    _dlog("弹窗HTML已保存到 %s (%d字符)" % (dump_path, len(html_dump)))
            except Exception as e:
                _dlog("保存HTML失败: %s" % e)

            # 10. 弹窗出现后，用 JS 直接提取 + 虚拟滚动
            _dlog("弹窗已打开，用 JS 提取评论...")
            _dlog("当前URL: %s" % (self._tab.url or "unknown"))
            # 检测 iframe
            try:
                iframe_count = self._tab.run_js("return document.querySelectorAll('iframe').length;")
                _dlog("页面iframe数量: %s" % iframe_count)
            except Exception as e:
                _dlog("检测iframe失败: %s" % e)
            # 先直接提取当前可见的
            try:
                reviews = self._extract_reviews_via_js(product_url, product_id)
            except Exception as e:
                _dlog("JS提取异常: %s" % e)
                import traceback; traceback.print_exc()
                reviews = []
            _dlog("JS提取返回 %d 条评论" % len(reviews))
            if reviews and len(reviews) >= 3:
                print("[jd-dp] 弹窗 JS 提取到 %d 条评论" % len(reviews))
                # 如果还不够，继续滚动提取
                if len(reviews) < self.max_reviews:
                    _dlog("开始滚动加载更多评论 (已有%d, 目标%d)..." % (len(reviews), self.max_reviews))
                    try:
                        more = self._scroll_and_extract_js(product_url, product_id, reviews)
                        if more:
                            reviews = more
                    except Exception as e:
                        _dlog("滚动提取异常: %s" % e)
                        import traceback; traceback.print_exc()
                    _dlog("滚动提取结束，共 %d 条" % len(reviews))
                return reviews

            # 11. JS 提取失败，尝试 DrissionPage 选择器提取
            print("[jd-dp] JS 提取不足，尝试选择器提取...")
            reviews = self._extract_reviews_from_page(product_url, product_id)
            if reviews:
                print("[jd-dp] 选择器提取到 %d 条评论" % len(reviews))
                return reviews

            # 12. 最终兜底：全局提取 + 截图
            print("[jd-dp] 所有提取方式均失败，尝试全局提取...")
            reviews = self._extract_reviews_global(product_url, product_id)
            if reviews:
                print("[jd-dp] 全局提取到 %d 条评论" % len(reviews))
                return reviews

            print("[jd-dp] 截图兜底")
            self._capture_screenshots(product_url, product_id)

        except Exception as e:
            print("[jd-dp] 抓取异常: %s" % e)
            import traceback
            traceback.print_exc()
        finally:
            # 不立即关闭浏览器，让用户可以看到页面
            # 浏览器会在 Streamlit session 结束时由 GC 清理
            pass

        # 最终去重 + 截断（不凑数，有多少返回多少）
        final = []
        _seen_text = set()
        for r in reviews:
            t = (r.get("review_text") or "").strip()
            if not t or len(t) < 5 or t in _seen_text:
                continue
            _seen_text.add(t)
            final.append(r)
        return final[:self.max_reviews]


    def reextract_current(self, product_url: str = "", product_id: str = "") -> List[Dict]:
        """从当前已打开的浏览器页面重新提取评论（用于用户手动确认后重试）。
        不重新打开浏览器，不重新导航，直接从当前 DOM 提取。
        """
        if not self._tab:
            return []
        if not product_id:
            product_id = self._extract_product_id(product_url or self._tab.url or "")
        if not product_url:
            product_url = self._tab.url or ""

        # 检测弹窗是否存在
        reviews = []
        try:
            popup = self._tab.ele(RATE_LIST_XPATH, timeout=1)
            if popup:
                print("[jd-dp-reextract] 弹窗存在，从弹窗提取...")
                reviews = self._extract_reviews_from_popup(product_url, product_id)
        except Exception:
            pass

        if not reviews:
            print("[jd-dp-reextract] 从页面全局提取...")
            reviews = self._extract_reviews_global(product_url, product_id)

        if not reviews:
            print("[jd-dp-reextract] 从页面直接提取...")
            reviews = self._extract_reviews_from_page(product_url, product_id)

        # 去重截断
        final = []
        seen = set()
        for r in reviews:
            t = (r.get("review_text") or "").strip()
            if t and len(t) >= 5 and t not in seen:
                seen.add(t)
                final.append(r)
        return final[:self.max_reviews]

    def _dump_page_html(self, product_id: str):
        """保存当前页面 HTML 到 debug/ 目录，用于诊断页面结构。"""
        try:
            debug_dir = PROJECT_ROOT / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            import datetime
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            html_file = debug_dir / f"jd_dp_{product_id}_{ts}.html"
            html = self._tab.html or ""
            html_file.write_text(html, encoding="utf-8")
            print("[jd-dp] 页面HTML已保存: %s (%d 字符)" % (html_file, len(html)))
            # 同时保存当前URL
            url_file = debug_dir / f"jd_dp_{product_id}_{ts}_url.txt"
            url_file.write_text(self._tab.url or "", encoding="utf-8")
        except Exception as e:
            print("[jd-dp] 保存HTML失败: %s" % e)

    def _extract_reviews_global(self, product_url: str, product_id: str) -> List[Dict]:
        """全局兜底：用JS扫描页面中所有可能是评论的元素。
        严格过滤：必须有星级图标 + 中文文本 >= 15字 + 非黑名单内容。"""
        try:
            js = r"""
            return (function() {
                var results = [];
                var seen = {};
                var blacklist = [
                    'header', 'nav', 'footer', '.header', '.footer', '.nav',
                    '.crumb', '.breadcrumb', '.filter', '.sort', '.tab',
                    '.sku-name', '#name', '.product-intro', '.itemInfo-wrap',
                    '.shop-name', '.price', '.btn-special1',
                    '.comment-filter', '.comment-sort', '.comment-tab',
                    '.comment-header', '.comment-score', '.comment-percent',
                    '.comments-info', '.comment-column', '#comment-form',
                    '.mc', '.mt', '.tb', '.tc', '.tm'
                ];
                function isBlacklisted(el) {
                    for (var b = 0; b < blacklist.length; b++) {
                        try { if (el.closest(blacklist[b])) return true; } catch(e) {}
                    }
                    return false;
                }
                var selectors = [
                    '.comment-item',
                    '.J-comments-list .comment-item',
                    '#comment .comment-item',
                    '.comments-list .comment-item',
                    '.J_commentsList .comment-item',
                    '.comment-list .comment-item',
                    'li.comment-item',
                    'div[class*="commentItem"]',
                    'div[class*="comment-item"]',
                    'div[class*="CommentItem"]',
                    'div[class*="review-item"]',
                    'div[class*="ReviewItem"]',
                    'div[class*="evaluation-item"]',
                    '[class*="commentList"] li',
                    '[class*="CommentList"] li',
                    '[class*="reviewList"] li',
                    '.rate-list li',
                    'ul[class*="comment"] li',
                    'ul[class*="Comment"] li'
                ];
                var nodes = [];
                var nodeSet = new Set();
                for (var s = 0; s < selectors.length; s++) {
                    try {
                        var found = document.querySelectorAll(selectors[s]);
                        for (var i = 0; i < found.length; i++) {
                            if (!nodeSet.has(found[i])) {
                                nodeSet.add(found[i]);
                                nodes.push(found[i]);
                            }
                        }
                    } catch(e) {}
                }
                var skipWords = ['登录', '注册', '购物车', '配送至', '优惠券', '满减',
                                 '秒杀', '加入购物车', '商品评价', '好评率', '晒图',
                                 '视频购买', '降价通知', '促销', '增值服务', '京豆',
                                 '白条', '免邮', '搜本店', '搜全站'];
                for (var n = 0; n < nodes.length; n++) {
                    var el = nodes[n];
                    if (isBlacklisted(el)) continue;
                    var text = (el.innerText || el.textContent || '').trim();
                    if (!text || text.length < 15 || text.length > 2000) continue;
                    if (seen[text]) continue;
                    if (!/[\u4e00-\u9fa5]/.test(text)) continue;
                    var rating = 0;
                    var cls = el.className || '';
                    var starMatch = cls.match(/star(\d)/) || cls.match(/star-(\d)/);
                    if (starMatch) {
                        rating = parseInt(starMatch[1]);
                    } else {
                        var starEl = el.querySelector('[class*="star"]');
                        if (starEl) {
                            var sc = starEl.className || '';
                            var m = sc.match(/star(\d)/) || sc.match(/star-(\d)/);
                            if (m) rating = parseInt(m[1]);
                        }
                    }
                    if (rating === 0) continue;
                    var content = text;
                    var contentEl = el.querySelector('[class*="comment-con"],[class*="commentCon"],[class*="commentContent"],[class*="comment_content"],[class*="review-content"],[class*="reviewContent"],[class*="rate-content"],[class*="evaluation-content"]');
                    if (contentEl) {
                        content = (contentEl.innerText || '').trim();
                    } else {
                        var pEl = el.querySelector('p');
                        if (pEl) content = (pEl.innerText || '').trim();
                    }
                    if (!content || content.length < 10) continue;
                    var head = content.substring(0, 20);
                    var skip = false;
                    for (var k = 0; k < skipWords.length; k++) {
                        if (head.indexOf(skipWords[k]) !== -1) { skip = true; break; }
                    }
                    if (skip) continue;
                    var userEl = el.querySelector('[class*="user-info"],[class*="u-name"],[class*="nickname"],[class*="userName"]');
                    var userName = userEl ? (userEl.innerText || '').trim().substring(0, 50) : '匿名用户';
                    if (!userName) userName = '匿名用户';
                    var dateEl = el.querySelector('[class*="date"],[class*="time"],time,.order-info span');
                    var dateStr = dateEl ? (dateEl.innerText || '').trim() : '';
                    seen[text] = true;
                    results.push({content: content.substring(0, 500), rating: rating, user: userName, date: dateStr});
                }
                return JSON.stringify(results.slice(0, 100));
            })();
            """
            raw = self._tab.run_js(js)
            if not raw:
                return []
            import json as _json
            items = _json.loads(raw) if isinstance(raw, str) else raw
            reviews = []
            seen = set()
            for item in items:
                text = item.get("content", "").strip()
                if not text or text in seen or len(text) < 10:
                    continue
                seen.add(text)
                reviews.append(self._format_review(
                    text=text,
                    rating=item.get("rating", 5),
                    user_name=item.get("user", "匿名用户"),
                    review_date=item.get("date", ""),
                    sku="",
                    product_id=product_id,
                    product_url=product_url,
                ))
            print("[jd-dp] 全局提取: JS扫描到 %d 条，有效 %d 条" % (len(items), len(reviews)))
            return reviews[:self.max_reviews]
        except Exception as e:
            print("[jd-dp] 全局提取异常: %s" % e)
            return []

    def _extract_reviews_via_js(self, product_url: str, product_id: str) -> List[Dict]:
        """用 JavaScript 直接从 DOM 提取评论，不依赖 DrissionPage CSS 选择器。"""
        js_code = """
        return (function() {
            var results = [];
            var seen = new Set();

            // 查找评论卡片：优先弹窗内，再找页面全局
            var containers = [];
            // 1. 弹窗 overlay（class 含 rateListBox 或 jdc-page-overlay）
            document.querySelectorAll('[class*="rateListBox"], [class*="jdc-page-overlay"], [class*="_rateListBox_"]').forEach(function(el) {
                containers.push(el);
            });
            // 2. comment-root
            var cr = document.getElementById('comment-root');
            if (cr) containers.push(cr);
            // 3. 全局兜底
            if (containers.length === 0) {
                containers.push(document);
            }

            // 评论卡片选择器（多种变体）
            var cardSelectors = [
                '[class*="rate-card"]',
                '[class*="RateCard"]',
                '[class*="comment-item"]',
                '[class*="CommentItem"]',
                '[class*="review-item"]',
                '[class*="ReviewItem"]',
                '.comment-item',
                '[data-index]'
            ];

            // 评论文本选择器
            var descSelectors = [
                '[class*="rate-card-main-desc"]',
                '[class*="rate-card-desc"]',
                '[class*="comment-content"]',
                '[class*="commentContent"]',
                '.comment-con',
                '[class*="comment-con"]',
                '[class*="review-content"]',
                '[class*="reviewContent"]',
                '[class*="rate-content"]',
                '[class*="evaluation-content"]',
                'p'
            ];

            // 用户名选择器
            var userSelectors = [
                '[class*="user-info"]', '[class*="userInfo"]',
                '.u-name', '.user-info', '.nickname',
                '[class*="rate-card-user"]', '[class*="rate-card-name"]'
            ];

            // 日期选择器
            var dateSelectors = [
                '[class*="comment-date"]', '[class*="date"]',
                '.comment-date', '.date', '.order-info'
            ];

            containers.forEach(function(container) {
                cardSelectors.forEach(function(cs) {
                    var cards = container.querySelectorAll(cs);
                    cards.forEach(function(card) {
                        if (results.length >= 200) return;

                        // 提取评论文本
                        var text = '';
                        for (var i = 0; i < descSelectors.length; i++) {
                            var el = card.querySelector(descSelectors[i]);
                            if (el) {
                                text = (el.innerText || el.textContent || '').trim();
                                if (text && text.length >= 5) break;
                            }
                        }
                        if (!text || text.length < 5) return;
                        // 去重
                        if (seen.has(text)) return;
                        // 必须含中文
                        if (!/[\\u4e00-\\u9fa5]/.test(text)) return;
                        // 黑名单
                        var skipKw = ['登录','注册','购物车','配送至','优惠券','满减','秒杀','加入购物车','商品评价','好评率','视频购买','降价通知','促销','增值服务','白条','免邮'];
                        for (var k = 0; k < skipKw.length; k++) {
                            if (text.indexOf(skipKw[k]) === 0) return;
                        }
                        seen.add(text);

                        // 提取评分
                        var rating = 5;
                        var starEl = card.querySelector('.star, [class*="star"]');
                        if (starEl) {
                            var cls = starEl.className || '';
                            var m = cls.match(/star(\\d)/);
                            if (m) rating = parseInt(m[1]);
                        }

                        // 提取用户名
                        var userName = '匿名用户';
                        for (var i = 0; i < userSelectors.length; i++) {
                            var ue = card.querySelector(userSelectors[i]);
                            if (ue) {
                                var un = (ue.innerText || ue.textContent || '').trim();
                                if (un && un.length > 0 && un.length < 30) {
                                    userName = un;
                                    break;
                                }
                            }
                        }

                        // 提取日期
                        var reviewDate = '';
                        for (var i = 0; i < dateSelectors.length; i++) {
                            var de = card.querySelector(dateSelectors[i]);
                            if (de) {
                                reviewDate = (de.innerText || de.textContent || '').trim();
                                if (reviewDate) break;
                            }
                        }

                        results.push({
                            text: text,
                            rating: rating,
                            user: userName,
                            date: reviewDate
                        });
                    });
                });
            });

            return JSON.stringify(results);
        })();
        """
        try:
            raw = self._tab.run_js(js_code)
            if not raw:
                return []
            import json as _json
            data = _json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, list):
                return []
            reviews = []
            for item in data:
                text = self._clean_text(item.get("text", ""))
                if not text or len(text) < 5:
                    continue
                reviews.append(self._format_review(
                    text=text,
                    rating=item.get("rating", 5),
                    user_name=item.get("user", "匿名用户"),
                    review_date=item.get("date", ""),
                    sku="",
                    product_id=product_id,
                    product_url=product_url,
                ))
            print(f"[jd-dp] JS 提取到 {len(reviews)} 条评论")
            return reviews[:self.max_reviews]
        except Exception as e:
            print(f"[jd-dp] JS 提取异常: {e}")
            return []

    def _scroll_and_extract_js(self, product_url: str, product_id: str,
                                existing_reviews: List[Dict]) -> List[Dict]:
        """在弹窗中虚拟滚动并用 JS 反复提取，直到达到上限或无新评论。"""
        all_reviews = list(existing_reviews)
        seen_texts = set(r.get("review_text", "")[:80] for r in all_reviews)
        stall = 0

        for round_num in range(50):
            if len(all_reviews) >= self.max_reviews:
                break

            # 滚动
            try:
                self._tab.run_js(self._scroll_overlay_js())
            except Exception:
                pass
            time.sleep(1.0)

            # 提取
            new_reviews = self._extract_reviews_via_js(product_url, product_id)
            new_count = 0
            for r in new_reviews:
                txt = r.get("review_text", "")[:80]
                if txt and txt not in seen_texts:
                    all_reviews.append(r)
                    seen_texts.add(txt)
                    new_count += 1
                    if len(all_reviews) >= self.max_reviews:
                        break

            if new_count == 0:
                stall += 1
                if stall >= 5:
                    print(f"[jd-dp] 滚动提取连续 {stall} 轮无新评论，停止")
                    break
            else:
                stall = 0
                print(f"[jd-dp] 滚动第 {round_num + 1} 轮: +{new_count} 条 (累计 {len(all_reviews)})")

        return all_reviews[:self.max_reviews]

    def _extract_reviews_from_page(self, product_url: str, product_id: str) -> List[Dict]:

        """兜底：从商品页面直接提取评论（非弹窗模式）。"""
        reviews = []
        seen_texts = set()

        # 评论容器选择器 — 优先新版 CSS module 选择器，再试旧版
        selectors = [
            # 新版京东 CSS module（rate-card）
            "css:div[class*='rate-card']",
            "css:div[class*='RateCard']",
            "css:div[class*='comment-item']",
            "css:div[class*='CommentItem']",
            # 旧版
            "css:.comment-item",
            "css:.J-comments-list .comment-item",
            "css:.J_commentsList .comment-item",
            "css:div[class*='review-item']",
            "css:div[class*='ReviewItem']",
            "css:div[class*='evaluation-item']",
            "css:[class*='commentList'] li",
            "css:[class*='CommentList'] li",
        ]

        # 评论文本选择器 — 同样优先新版
        desc_selectors = [
            "css:span[class*='rate-card-main-desc']",
            "css:span[class*='rate-card-desc']",
            "css:div[class*='rate-card-content']",
            "css:div[class*='comment-content']",
            "css:.comment-con", "css:p.comment-con",
            "css:[class*='comment-con']", "css:[class*='commentCon']",
            "css:[class*='commentContent']", "css:[class*='comment_content']",
            "css:[class*='review-content']", "css:[class*='reviewContent']",
            "css:[class*='rate-content']", "css:[class*='evaluation-content']",
            "css:p", RATE_DESC_CSS,
        ]

        for sel in selectors:
            try:
                items = self._tab.eles(sel, timeout=1.0)
                if not items:
                    continue

                for item in items:
                    try:
                        text = ""
                        for desc_sel in desc_selectors:
                            try:
                                ele = item.ele(desc_sel, timeout=0.2)
                                if ele:
                                    text = ele.text.strip()
                                    if text:
                                        break
                            except Exception:
                                continue

                        if not text or len(text) < 5 or text in seen_texts:
                            continue
                        # 必须包含中文字符
                        if not re.search(r"[\u4e00-\u9fa5]", text):
                            continue
                        # 黑名单关键词
                        _skip_kw = ("登录", "注册", "购物车", "配送至", "优惠券", "满减",
                                    "秒杀", "加入购物车", "商品评价", "好评率",
                                    "视频购买", "降价通知", "促销", "增值服务",
                                    "白条", "免邮", "搜本店", "搜全站")
                        if text.startswith(_skip_kw):
                            continue
                        seen_texts.add(text)

                        rating = 5
                        try:
                            star = item.ele("css:.star", timeout=0.2)
                            if star:
                                cls = star.attr("class") or ""
                                m = re.search(r"star(\d)", cls)
                                if m:
                                    rating = int(m.group(1))
                        except Exception:
                            pass

                        user_name = "匿名用户"
                        try:
                            u = item.ele("css:.u-name, .user-info, [class*='user-info']", timeout=0.2)
                            if u:
                                user_name = u.text.strip() or "匿名用户"
                        except Exception:
                            pass

                        review_date = ""
                        try:
                            d = item.ele("css:.comment-date, .date, .order-info, [class*='date']", timeout=0.2)
                            if d:
                                review_date = d.text.strip()
                        except Exception:
                            pass

                        reviews.append(self._format_review(
                            text=text, rating=rating, user_name=user_name,
                            review_date=review_date, sku="",
                            product_id=product_id, product_url=product_url,
                        ))
                    except Exception:
                        continue

                if reviews:
                    break
            except Exception:
                continue

        return reviews[:self.max_reviews]

    def get_screenshots(self) -> List[str]:
        """返回截图文件路径列表。"""
        return [s for s in self._screenshots if os.path.exists(s)]

    def get_browser_cookies(self) -> Dict:
        """提取浏览器中的京东 cookie，供 API 直连使用。"""
        try:
            cookies = self._tab.cookies(all_domains=True)
            return {c.get("name", ""): c.get("value", "") for c in cookies if c.get("name")}
        except Exception as e:
            print("[jd-dp] 提取 cookies 失败: %s" % e)
            return {}

    def close(self):
        """显式关闭浏览器。"""
        self._close_browser()

    def __del__(self):
        self._close_browser()


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def scrape_jd_reviews(
    url: str,
    max_reviews: int = 50,
    **kwargs,
) -> List[Dict]:
    """
    便捷函数：抓取京东商品评论。

    :param url: 京东商品 URL
    :param max_reviews: 最多评论数
    :return: 评论字典列表
    """
    scraper = JDDrissionPageScraper(max_reviews=max_reviews, **kwargs)
    return scraper.scrape(url, max_reviews=max_reviews)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python jd_drissionpage_scraper.py <京东商品URL> [最大评论数]")
        sys.exit(1)
    test_url = sys.argv[1]
    test_max = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    result = scrape_jd_reviews(test_url, max_reviews=test_max)
    print("\n===== 采集结果（%d 条）=====" % len(result))
    for i, r in enumerate(result, 1):
        print("[%d] %s | %s | %s" % (
            i, r.get("rating", ""), r.get("reviewer_name", ""),
            r.get("review_text", "")[:80]
        ))
