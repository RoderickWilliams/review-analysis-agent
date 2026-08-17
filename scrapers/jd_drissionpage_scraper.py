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
RATE_LIST_XPATH = 'x://div[@class="jdc-page-overlay _rateListBox_1ygkr_1"]'

# 评论卡片
RATE_CARD_CSS = "css:div[data-index]"
RATE_DESC_CSS = "css:span.jdc-pc-rate-card-main-desc"

# 也尝试更通用的选择器（京东可能改版）
RATE_CARD_CSS_FALLBACKS = [
    "css:div[data-index]",
    "css:.comment-item",
    "css:.comment-con",
    "css:.J-comments-list .comment-item",
]
RATE_DESC_CSS_FALLBACKS = [
    "css:span.jdc-pc-rate-card-main-desc",
    "css:.comment-con",
    "css:p.comment-con",
]

# 虚拟滚动稳定判定
MAX_STALL_ROUNDS = 3
MAX_SCROLL_ROUNDS = 200

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
        if self.headless:
            co.headless()

        self._browser = Chromium(co)
        self._tab = self._browser.new_tab()
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

    def _is_logged_in(self) -> bool:
        """检测当前页面是否已登录京东。"""
        try:
            if self._tab.wait.ele_displayed(LOGIN_USER_XPATH, timeout=2):
                logout = self._tab.ele(LOGOUT_LINK_XPATH, timeout=1)
                if logout:
                    return True
        except Exception:
            pass
        # Cookie 兜底检测
        try:
            cookies = self._tab.cookies(all_domains=True)
            for c in cookies:
                name = c.get("name", "")
                if name in ("pt_key", "pt_pin", "thor"):
                    return True
        except Exception:
            pass
        return False

    def _ensure_logged_in(self) -> bool:
        """确保已登录，未登录则打开登录页等待用户扫码。"""
        if self._is_logged_in():
            print("[jd-dp] 已检测到登录态")
            return True

        print("[jd-dp] 未登录，打开京东登录页...")
        self._tab.get("https://passport.jd.com/new/login.aspx")

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
        """从京东商品 URL 提取商品 ID。"""
        m = re.search(r"item\.jd\.com/(\d+)", url)
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
        return ""

    # ------------------------------------------------------------------
    # 评论弹窗虚拟滚动采集
    # ------------------------------------------------------------------

    @staticmethod
    def _scroll_overlay_js() -> str:
        """增量滚动评论弹窗的 JS：把倒数第二张卡片滚到容器顶部。"""
        return """
        const overlay = document.querySelector('._rateListBox_1ygkr_1');
        if (!overlay) return false;
        const cards = [...overlay.querySelectorAll('div[data-index]')];
        if (cards.length < 2) return false;
        const target = cards[cards.length - 2];
        let scroller = target.parentElement;
        while (scroller && scroller !== overlay) {
            const st = getComputedStyle(scroller);
            if ((st.overflowY === 'auto' || st.overflowY === 'scroll')
                    && scroller.scrollHeight > scroller.clientHeight) {
                break;
            }
            scroller = scroller.parentElement;
        }
        if (scroller) {
            scroller.scrollTop = target.offsetTop - scroller.offsetTop;
            return true;
        }
        return false;
        """

    def _extract_reviews_from_popup(self, product_url: str, product_id: str) -> List[Dict]:
        """
        在评论弹窗中虚拟滚动，逐屏采集评论。

        返回统一格式的评论字典列表。
        """
        reviews: Dict[int, Dict] = {}
        last_max = -1
        stall = 0
        rounds = 0

        while rounds < MAX_SCROLL_ROUNDS:
            rounds += 1

            # 每 5 轮检查滑块
            if rounds % 5 == 0:
                self._handle_verify()

            # 读取当前可见评论卡片
            try:
                overlay = self._tab.ele(RATE_LIST_XPATH, timeout=2)
                if overlay:
                    cards = overlay.eles(RATE_CARD_CSS, timeout=2)
                    for card in cards:
                        try:
                            idx_attr = card.attr("data-index")
                            if not idx_attr or not str(idx_attr).isdigit():
                                continue
                            idx = int(idx_attr)
                            if idx in reviews:
                                continue

                            # 提取评论文本
                            text = ""
                            for desc_sel in RATE_DESC_CSS_FALLBACKS:
                                try:
                                    desc_ele = card.ele(desc_sel, timeout=0.5)
                                    if desc_ele:
                                        text = desc_ele.text.strip()
                                        if text:
                                            break
                                except Exception:
                                    continue

                            if not text or len(text) < 3:
                                continue

                            # 尝试提取评分（星级）
                            rating = 5
                            try:
                                star_ele = card.ele("css:.star", timeout=0.3)
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
                                    timeout=0.3,
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
                                    timeout=0.3,
                                )
                                if user_ele:
                                    user_name = user_ele.text.strip() or "匿名用户"
                            except Exception:
                                pass

                            # 尝试提取 SKU 信息
                            sku = ""
                            try:
                                sku_ele = card.ele(
                                    "css:.sku-info, .sku-name, .J_order_type",
                                    timeout=0.3,
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
            except Exception as e:
                print("[jd-dp] 读取评论弹窗异常: %s" % e)

            # 上限判定
            if len(reviews) >= self.max_reviews:
                print("[jd-dp] 达到采集上限 %d 条" % self.max_reviews)
                break

            # 推进判定
            cur_max = max(reviews) if reviews else -1
            if cur_max > last_max:
                last_max = cur_max
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

            # 等待推进
            wait_until = time.time() + 3
            while time.time() < wait_until:
                time.sleep(0.2)
                # 简单检查：卡片数量是否变化
                try:
                    overlay = self._tab.ele(RATE_LIST_XPATH, timeout=0.5)
                    if overlay:
                        cur_cards = overlay.eles(RATE_CARD_CSS, timeout=0.5)
                        if len(cur_cards) > 0:
                            break
                except Exception:
                    pass

        return list(reviews.values())

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
                time.sleep(1)
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
            time.sleep(random.uniform(1.5, 3.0))

            # 3. 确保已登录
            if not self._ensure_logged_in():
                print("[jd-dp] 登录失败，无法继续")
                return []

            # 4. 访问商品详情页
            print("[jd-dp] 打开商品页: %s" % product_url)
            self._tab.get(product_url)
            time.sleep(random.uniform(2.0, 4.0))

            # 处理可能的滑块
            self._handle_verify()

            # 5. 尝试获取商品名称
            try:
                title_ele = self._tab.ele("css:.sku-name, #name h1, .product-intro .sku-name", timeout=5)
                if title_ele:
                    self._product_name = title_ele.text.strip()
            except Exception:
                pass

            # 6. 滚动页面触发评论区加载
            print("[jd-dp] 滚动页面加载评论区...")
            for _ in range(3):
                try:
                    self._tab.scroll.down(5)
                except Exception:
                    pass
                time.sleep(random.uniform(0.8, 1.5))

            # 7. 等待评论区出现
            comment_root = None
            try:
                comment_root = self._tab.ele(COMMENT_ROOT_XPATH, timeout=10)
            except Exception:
                pass

            if not comment_root:
                print("[jd-dp] 未找到评论区，尝试截图兜底")
                self._capture_screenshots(product_url, product_id)
                return []

            # 8. 点击"全部评论"按钮打开弹窗
            print("[jd-dp] 尝试打开全部评论弹窗...")
            all_btn = None
            try:
                all_btn = self._tab.ele(ALL_BTN_XPATH, timeout=5)
            except Exception:
                pass

            if all_btn:
                try:
                    all_btn.click()
                    print("[jd-dp] 已点击'全部评论'")
                    time.sleep(random.uniform(2.0, 3.0))
                except Exception as e:
                    print("[jd-dp] 点击全部评论失败: %s" % e)

            # 处理滑块
            self._handle_verify()

            # 9. 等待评论弹窗出现
            popup_appeared = False
            try:
                popup_appeared = self._tab.wait.ele_displayed(RATE_LIST_XPATH, timeout=10)
            except Exception:
                pass

            if not popup_appeared:
                print("[jd-dp] 评论弹窗未出现，尝试直接从页面提取评论")

                # 兜底：尝试从页面直接提取评论（非弹窗模式）
                reviews = self._extract_reviews_from_page(product_url, product_id)
                if reviews:
                    print("[jd-dp] 从页面直接提取到 %d 条评论" % len(reviews))
                    return reviews

                # 最终兜底：截图
                print("[jd-dp] DOM 提取失败，截图兜底")
                self._capture_screenshots(product_url, product_id)
                return []

            # 10. 虚拟滚动采集弹窗内评论
            print("[jd-dp] 开始虚拟滚动采集评论...")
            reviews = self._extract_reviews_from_popup(product_url, product_id)
            print("[jd-dp] 弹窗采集完成，共 %d 条评论" % len(reviews))

            # 11. 如果弹窗也没抓到，截图兜底
            if not reviews:
                print("[jd-dp] 弹窗未采集到评论，截图兜底")
                self._capture_screenshots(product_url, product_id)

        except Exception as e:
            print("[jd-dp] 抓取异常: %s" % e)
            import traceback
            traceback.print_exc()
        finally:
            # 不立即关闭浏览器，让用户可以看到页面
            # 浏览器会在 Streamlit session 结束时由 GC 清理
            pass

        return reviews

    def _extract_reviews_from_page(self, product_url: str, product_id: str) -> List[Dict]:
        """兜底：从商品页面直接提取评论（非弹窗模式）。"""
        reviews = []
        seen_texts = set()

        # 尝试多种评论容器选择器
        selectors = [
            "css:.comment-item",
            "css:.J-comments-list .comment-item",
            "css:#comment .comment-item",
            "css:.comments-list .comment-item",
        ]

        for sel in selectors:
            try:
                items = self._tab.eles(sel, timeout=3)
                if not items:
                    continue

                for item in items:
                    try:
                        text = ""
                        for desc_sel in ["css:.comment-con", "css:p.comment-con", RATE_DESC_CSS]:
                            try:
                                ele = item.ele(desc_sel, timeout=0.5)
                                if ele:
                                    text = ele.text.strip()
                                    if text:
                                        break
                            except Exception:
                                continue

                        if not text or len(text) < 3 or text in seen_texts:
                            continue
                        seen_texts.add(text)

                        rating = 5
                        try:
                            star = item.ele("css:.star", timeout=0.3)
                            if star:
                                cls = star.attr("class") or ""
                                m = re.search(r"star(\d)", cls)
                                if m:
                                    rating = int(m.group(1))
                        except Exception:
                            pass

                        user_name = "匿名用户"
                        try:
                            u = item.ele("css:.u-name, .user-info", timeout=0.3)
                            if u:
                                user_name = u.text.strip() or "匿名用户"
                        except Exception:
                            pass

                        review_date = ""
                        try:
                            d = item.ele("css:.comment-date, .date, .order-info", timeout=0.3)
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
