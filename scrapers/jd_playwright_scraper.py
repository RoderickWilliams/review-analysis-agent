"""
京东评论抓取器 — Patchright 反检测版
======================================
基于 Patchright（Playwright 反检测 fork）的京东商品评论抓取器。

核心升级（相比普通 Playwright 版）：
  1. Patchright 在二进制/CDP/JS 多层修补自动化指纹
  2. channel="chrome" 使用系统真实 Chrome，获得真实 TLS/JA3 指纹
  3. 全面 stealth init script（webdriver / plugins / chrome.runtime / permissions）
  4. 人类行为模拟（随机延迟、随机滚动距离、随机鼠标轨迹）
  5. page.route 拦截 club.jd.com 评论 API，自动解析 JSONP
  6. DOM 提取 + API 拦截双保险
  7. 403 / 滑块验证码检测 + 手动验证等待
  8. 持久化上下文保留 Cookie/登录态

伦理准则：
  - 严禁使用 AI 生成虚假评论进行虚假分析
  - 所有评论来自真实页面 DOM/API 提取
  - 每条评论包含完整溯源字段
"""

import json
import os
import random
import re
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional


def _import_patchright():
    """优先导入 Patchright，失败时回退到 Playwright。

    Patchright 是 Playwright 的 drop-in 反检测 fork，
    API 100% 兼容，只需修改 import 路径。
    """
    try:
        from patchright.sync_api import sync_playwright
        return sync_playwright, "patchright"
    except ImportError:
        try:
            from playwright.sync_api import sync_playwright
            print("[jd-pw] patchright 未安装，回退到 playwright（反检测能力较弱）")
            return sync_playwright, "playwright"
        except ImportError:
            raise ImportError(
                "需要安装 patchright 或 playwright：\n"
                "  pip install patchright\n"
                "  patchright install chromium"
            )


def ensure_playwright_browsers():
    """确保 Patchright/Playwright 浏览器已安装（云端首次运行时自动安装）"""
    try:
        # 优先检查 patchright
        result = subprocess.run(
            ["python", "-m", "patchright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, timeout=30
        )
        if "is already installed" not in (result.stdout or ""):
            print("[jd-pw] 正在安装 Patchright Chromium 浏览器...")
            subprocess.run(
                ["python", "-m", "patchright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
            print("[jd-pw] Chromium 安装完成")
    except Exception:
        try:
            subprocess.run(
                ["python", "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
        except Exception as e:
            print(f"[jd-pw] 浏览器安装检查失败: {e}")


# ── Stealth 脚本 ──────────────────────────────────────────────
# 比基础版更全面的反检测注入脚本
_STEALTH_JS = """
// 1. 移除 navigator.webdriver 标记
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// 2. 伪装 plugins（真实 Chrome 有 5 个内置插件）
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            {name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            {name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            {name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            {name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            {name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
        ];
        plugins.length = 5;
        return plugins;
    }
});

// 3. 伪装 languages
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});

// 4. 伪装 chrome.runtime
if (!window.chrome) window.chrome = {};
window.chrome.runtime = window.chrome.runtime || {};
window.chrome.app = window.chrome.app || {isInstalled: false};
window.chrome.csi = window.chrome.csi || function(){};
window.chrome.loadTimes = window.chrome.loadTimes || function(){};

// 5. 伪装 permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : originalQuery(parameters);

// 6. 伪装 WebGL vendor/renderer
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';           // UNMASKED_VENDOR_WEBGL
    if (parameter === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
    return getParameter.call(this, parameter);
};

// 7. 伪装 screen.colorDepth 和 pixelDepth
Object.defineProperty(screen, 'colorDepth', {get: () => 24});
Object.defineProperty(screen, 'pixelDepth', {get: () => 24});

// 8. 伪装 hardwareConcurrency
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});

// 9. 伪装 deviceMemory
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

// 10. 伪装 connection
if (navigator.connection) {
    Object.defineProperty(navigator.connection, 'rtt', {get: () => 50});
    Object.defineProperty(navigator.connection, 'downlink', {get: () => 10});
    Object.defineProperty(navigator.connection, 'effectiveType', {get: () => '4g'});
}

// 11. 移除 Playwright/Patchright 特有的全局变量
delete window.__playwright__;
delete window.__pw_manual;

// 12. 伪装 platform
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});

// 13. 伪装 vendor
Object.defineProperty(navigator, 'vendor', {get: () => 'Google Inc.'});
"""


class JDPlaywrightScraper:
    """基于 Patchright 的京东评论抓取器。

    用法::

        scraper = JDPlaywrightScraper()
        reviews = scraper.scrape("https://item.jd.com/100012345.html")
    """

    ITEM_URL_TEMPLATE = "https://item.jd.com/{product_id}.html"
    COMMENT_API_PATTERN = "**/club.jd.com/comment/productPageComments*"
    COMMENT_API_FALLBACK = "**/*productPageComments*"
    USER_DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "playwright-data", "jd-profile"
    )

    def __init__(self, headless: bool = False, max_reviews: int = 50, screenshot_dir: Optional[str] = None):
        self.headless = headless
        self.max_reviews = max_reviews
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._persistent = False
        self._driver_name = "patchright"
        self._api_comments: List[Dict] = []  # 存储拦截到的 API 评论
        self._screenshot_dir = screenshot_dir or os.path.join(
            tempfile.gettempdir(), "jd_screenshots"
        )
        self._screenshots: List[str] = []  # 截图文件路径列表

    # ------------------------------------------------------------------
    # 云端环境检测
    # ------------------------------------------------------------------

    @staticmethod
    def _is_cloud_env() -> bool:
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
        """启动 Patchright 浏览器（优先使用系统真实 Chrome）"""
        ensure_playwright_browsers()

        sync_pw, driver_name = _import_patchright()
        self._driver_name = driver_name

        if self._is_cloud_env():
            self.headless = True
            print("[jd-pw] 检测到云端环境，使用 headless 模式")

        self._playwright = sync_pw().start()

        # 检测系统是否安装了 Chrome（用于 channel="chrome" 获得真实 TLS 指纹）
        use_chrome_channel = self._detect_system_chrome() and not self._is_cloud_env()
        channel = "chrome" if use_chrome_channel else None

        use_persistent = not self._is_cloud_env()
        try:
            launch_kwargs = dict(
                headless=self.headless,
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-infobars",
                    "--window-size=1440,900",
                ],
                ignore_default_args=["--enable-automation"],
            )
            if channel:
                launch_kwargs["channel"] = channel
                print(f"[jd-pw] 使用系统真实 Chrome (channel=chrome)，驱动: {driver_name}")
            else:
                print(f"[jd-pw] 使用内置 Chromium，驱动: {driver_name}")

            if use_persistent:
                Path(self.USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
                launch_kwargs["user_data_dir"] = self.USER_DATA_DIR
                self._context = self._playwright.chromium.launch_persistent_context(
                    **launch_kwargs
                )
                self._persistent = True
            else:
                self._browser = self._playwright.chromium.launch(**launch_kwargs)
                ctx_kwargs = {k: v for k, v in launch_kwargs.items()
                              if k not in ("headless", "args", "ignore_default_args", "channel", "user_data_dir")}
                self._context = self._browser.new_context(**ctx_kwargs)
                self._persistent = False

        except Exception as e:
            print(f"[jd-pw] 浏览器启动失败 ({e})，尝试回退模式...")
            self._cleanup_browser()
            # 回退：不用 channel，用基本参数
            try:
                if use_persistent:
                    Path(self.USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
                    self._context = self._playwright.chromium.launch_persistent_context(
                        user_data_dir=self.USER_DATA_DIR,
                        headless=self.headless,
                        viewport={"width": 1440, "height": 900},
                        locale="zh-CN",
                        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                        ignore_default_args=["--enable-automation"],
                    )
                    self._persistent = True
                else:
                    self._browser = self._playwright.chromium.launch(
                        headless=self.headless,
                        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                    )
                    self._context = self._browser.new_context(
                        viewport={"width": 1440, "height": 900},
                        locale="zh-CN",
                    )
                    self._persistent = False
            except Exception as e2:
                print(f"[jd-pw] 回退启动也失败: {e2}")
                raise

        # 注入 stealth 脚本
        self._context.add_init_script(_STEALTH_JS)

        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()

        # 设置默认超时
        self._page.set_default_timeout(30000)

        return self._page

    @staticmethod
    def _detect_system_chrome() -> bool:
        """检测系统是否安装了 Chrome 浏览器"""
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
        ]
        for p in chrome_paths:
            if os.path.exists(p):
                return True
        # Linux: which google-chrome
        if os.name != "nt":
            try:
                subprocess.run(["which", "google-chrome"], capture_output=True, timeout=5)
                return True
            except Exception:
                pass
        return False

    def _cleanup_browser(self):
        """清理已启动的浏览器资源（用于启动失败回退）"""
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None

    def _close_browser(self):
        """关闭浏览器"""
        self._cleanup_browser()
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    # ------------------------------------------------------------------
    # 人类行为模拟
    # ------------------------------------------------------------------

    def _human_delay(self, min_ms: int = 800, max_ms: int = 2500):
        """随机延迟，模拟人类操作间隔"""
        delay = random.randint(min_ms, max_ms)
        self._page.wait_for_timeout(delay)

    def _human_scroll(self, distance: Optional[int] = None):
        """人类滚动：随机距离 + 随机缓动"""
        if distance is None:
            distance = random.randint(600, 2000)
        # 分几步滚动，模拟人类
        steps = random.randint(3, 8)
        step_dist = distance // steps
        for _ in range(steps):
            delta = step_dist + random.randint(-50, 100)
            try:
                self._page.mouse.wheel(0, delta)
            except Exception:
                try:
                    self._page.evaluate(f"window.scrollBy(0, {delta})")
                except Exception:
                    pass
            self._page.wait_for_timeout(random.randint(50, 200))
        self._page.wait_for_timeout(random.randint(500, 1500))

    def _human_mouse_move(self):
        """随机鼠标移动，模拟人类浏览行为"""
        try:
            vp = self._page.viewport_size or {"width": 1440, "height": 900}
            x = random.randint(100, vp["width"] - 100)
            y = random.randint(100, vp["height"] - 100)
            self._page.mouse.move(x, y, steps=random.randint(5, 15))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # URL 解析
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_short_link(url: str) -> str:
        if not url:
            return url
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
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/124.0.0.0 Safari/537.36",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                final_url = r.url
                html = r.read().decode("utf-8", "replace")

            m = re.search(r'/(\d{4,})\.html', final_url)
            if m:
                result = f"https://item.jd.com/{m.group(1)}.html"
                print(f"[jd-pw] 短链解析: {url} -> {result}")
                return result

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
    # 网络拦截器（用 page.route 拦截评论 API）
    # ------------------------------------------------------------------

    def _setup_route_interception(self):
        """使用 page.route 拦截 club.jd.com 评论 API 响应"""
        def handle_route(route):
            try:
                response = route.fetch()
                body = response.text()

                # 解析 JSONP 或 JSON
                data = None
                # 尝试 JSONP: fetchJSON_xxx({...})
                m = re.match(r'^[a-zA-Z0-9_]+\((.*)\);?\s*$', body, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(1))
                    except json.JSONDecodeError:
                        pass
                if data is None:
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError:
                        pass

                if data and "comments" in data:
                    comments = data.get("comments", [])
                    if comments:
                        self._api_comments.extend(comments)
                        print(f"[jd-pw] 拦截到 {len(comments)} 条 API 评论 (累计 {len(self._api_comments)})")

                route.fulfill(response=response)
            except Exception as e:
                print(f"[jd-pw] 路由拦截异常: {e}")
                try:
                    route.continue_()
                except Exception:
                    pass

        try:
            self._page.route(self.COMMENT_API_PATTERN, handle_route)
            self._page.route(self.COMMENT_API_FALLBACK, handle_route)
        except Exception as e:
            print(f"[jd-pw] 设置路由拦截失败: {e}")

        # 同时注入 XHR/fetch 拦截作为备份
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
                            try { data = JSON.parse(this.responseText); }
                            catch(e) {
                                const m = this.responseText.match(/^[a-zA-Z0-9_]+\\((.*)\\);?$/);
                                if (m) { try { data = JSON.parse(m[1]); } catch(e2) { return; } }
                                else return;
                            }
                            if (data && data.comments && data.comments.length > 0) {
                                window.__capturedReviews.push(...data.comments);
                            }
                        }
                    } catch(e) {}
                });
                return origSend.call(this, body);
            };
        """)

    # ------------------------------------------------------------------
    # 风控检测
    # ------------------------------------------------------------------

    def _check_blocked(self) -> bool:
        """检测是否被京东风控拦截（403/滑块/验证码）"""
        try:
            title = (self._page.title() or "").lower()
            body_text = (self._page.inner_text("body") or "")[:1000].lower()
            current_url = (self._page.url or "").lower()

            block_keywords = [
                "403", "forbidden", "拒绝", "请求来源",
                "验证", "滑块", "captcha", "verify",
                "访问被拒绝", "access denied", "blocked",
                "安全验证", "人机验证",
            ]

            if any(kw in title for kw in ["403", "forbidden", "验证", "captcha"]):
                return True
            if any(kw in body_text for kw in ["403", "forbidden", "拒绝", "请求来源", "滑块", "安全验证", "人机验证"]):
                return True
            if "403" in current_url or "forbidden" in current_url:
                return True

            # 检测滑块 iframe
            try:
                captcha = self._page.locator("#captcha, .J_MIDDLEWARE_FRAME_WARP, #nc_1_wrapper, [id*='captcha']")
                if captcha.count() > 0:
                    return True
            except Exception:
                pass

        except Exception:
            pass
        return False

    def _wait_for_manual_verification(self, timeout_sec: int = 120) -> bool:
        """等待用户手动完成验证（非 headless 模式下）"""
        if self.headless:
            return False
        print(f"[jd-pw] 请在浏览器中手动处理验证（刷新/登录/滑块），最多等待 {timeout_sec} 秒...")
        for i in range(timeout_sec // 3):
            self._page.wait_for_timeout(3000)
            if not self._check_blocked():
                print("[jd-pw] 检测到已通过验证，继续...")
                self._page.wait_for_timeout(3000)
                return True
        print("[jd-pw] 验证等待超时")
        return False

    # ------------------------------------------------------------------
    # 登录态检测与引导
    # ------------------------------------------------------------------

    def _is_logged_in(self) -> bool:
        """通过 Cookie / DOM 检测是否已登录京东"""
        try:
            cookies = self._context.cookies()
            cookie_names = {c.get("name", "") for c in cookies}
            # 京东登录后会有这些关键 Cookie
            login_cookies = {"pt_key", "pt_pin", "thor", "unick"}
            if cookie_names & login_cookies:
                # 进一步确认 pt_key 非空
                for c in cookies:
                    if c.get("name") == "pt_key" and c.get("value"):
                        return True
            # DOM 检测：页面有用户昵称元素
            try:
                logged_in_dom = self._page.evaluate("""
                    () => {
                        const el = document.querySelector(
                            '.nickname, .user-name, [class*="userinfo"], #ttbar-login .link-login'
                        );
                        if (!el) return false;
                        const text = (el.innerText || '').trim();
                        // 未登录时显示"你好，请登录"
                        if (text.includes('请登录') || text.includes('登录注册')) return false;
                        return text.length > 0;
                    }
                """)
                if logged_in_dom:
                    return True
            except Exception:
                pass
        except Exception:
            pass
        return False

    def _ensure_logged_in(self, timeout_sec: int = 180) -> bool:
        """
        确保用户已登录京东。
        未登录时打开登录页，等待用户手动扫码/输入账号登录。
        返回 True 表示已登录。
        """
        if self._is_logged_in():
            print("[jd-pw] 检测到已登录京东")
            return True

        if self.headless:
            print("[jd-pw] headless 模式无法手动登录，跳过登录引导")
            return False

        print("[jd-pw] 未检测到登录态，打开京东登录页...")
        try:
            self._page.goto("https://passport.jd.com/new/login.aspx", wait_until="domcontentloaded", timeout=30000)
            self._human_delay(2000, 3000)
        except Exception as e:
            print(f"[jd-pw] 打开登录页失败: {e}")
            return False

        print(f"[jd-pw] 请在浏览器中扫码或输入账号登录京东（最多等待 {timeout_sec} 秒）...")
        for i in range(timeout_sec // 3):
            self._page.wait_for_timeout(3000)
            current_url = (self._page.url or "").lower()
            # 登录成功后会跳转到 jd.com 首页
            if "passport.jd.com" not in current_url and "login.jd.com" not in current_url:
                self._human_delay(2000, 3000)
                if self._is_logged_in():
                    print("[jd-pw] 登录成功！")
                    return True
        print("[jd-pw] 登录等待超时")
        return False

    # ------------------------------------------------------------------
    # 评论提取
    # ------------------------------------------------------------------

    def _open_comments_tab(self) -> bool:
        """点击评价标签，展开评论区"""
        self._human_delay(1500, 3000)
        self._human_mouse_move()

        candidates = [
            "text=商品评价",
            "text=累计评价",
            "text=评价",
            "text=全部评价",
            "#detail .tab-main li:has-text('评价')",
            "[href*='comment']",
            "[class*='comment']",
            "[class*='Comment']",
            "[data-tab='comments']",
        ]

        for sel in candidates:
            try:
                loc = self._page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=3000)
                    self._human_delay(2000, 4000)
                    print(f"[jd-pw] 点击评论标签成功: {sel}")
                    return True
            except Exception:
                continue

        # 滚动到评论区
        try:
            self._page.evaluate("""
                () => {
                    const el = document.querySelector('#comment, .comment-list, [class*="comment"]');
                    if (el) el.scrollIntoView({behavior: 'smooth'});
                }
            """)
            self._human_delay(2000, 4000)
        except Exception:
            pass

        print("[jd-pw] 未找到评论标签，尝试直接滚动")
        return False

    def _extract_comments_from_dom(self) -> List[Dict]:
        """从渲染后的 DOM 中提取评论"""
        js = r"""
        () => {
            const textOf = (el) => (el?.innerText || el?.textContent || '').trim();
            const out = [];

            const selectors = [
                '.comment-item', '[class*=comment-item]', '[class*=CommentItem]',
                '.comment-con', '[class*=comment-con]',
                'div.comment-item', 'li.comment-item',
                '[class*=review-item]', '[class*=ReviewItem]',
                '[class*=Comment--]',
            ];

            let nodes = [];
            const seen = new Set();
            for (const sel of selectors) {
                const found = document.querySelectorAll(sel);
                for (const n of found) {
                    if (!seen.has(n)) { seen.add(n); nodes.push(n); }
                }
            }

            if (nodes.length === 0) {
                nodes = [...document.querySelectorAll('[class*="comment"], [class*="Comment"]')];
            }

            for (const node of nodes) {
                const rawText = textOf(node);
                if (!rawText || rawText.length < 6) continue;
                if (rawText.length > 3000) continue;
                // 过滤非评论节点（导航/标签等）
                if (rawText.length < 10 && !node.querySelector('[class*=star],[class*=Star]')) continue;

                const user = textOf(node.querySelector(
                    '[class*=user], [class*=nick], [class*=Nick], [class*=User], [class*=user-info], .user-name'
                ));
                const time = textOf(node.querySelector(
                    '[class*=time], time, [class*=Time], [class*=date], .order-info'
                ));
                const sku = textOf(node.querySelector(
                    '[class*=sku], [class*=spec], [class*=Sku], .sku-item, .sku-name'
                ));

                let rateScore = 5;
                const starEl = node.querySelector(
                    '[class*=star], [class*=Star], [class*=rate], [class*=score], .star'
                );
                if (starEl) {
                    const cls = starEl.className || '';
                    const style = starEl.getAttribute('style') || '';
                    const starText = textOf(starEl);
                    // 京东: class="star star5" 或 style="width:100%"
                    const m1 = cls.match(/star(\d)/);
                    const m2 = style.match(/width:\s*(\d+)%/);
                    const m3 = starText.match(/(\d)/);
                    if (m1) rateScore = parseInt(m1[1]);
                    else if (m2) rateScore = Math.round(parseInt(m2[1]) / 20);
                    else if (m3) rateScore = parseInt(m3[1]);
                }

                // 提取评论正文（优先使用 .comment-con）
                let content = '';
                const conEl = node.querySelector('.comment-con, [class*=comment-con], [class*=commentCon]');
                if (conEl) {
                    content = textOf(conEl);
                }
                if (!content) {
                    content = rawText;
                    if (user && content.includes(user)) content = content.replace(user, '').trim();
                    if (time && content.includes(time)) content = content.replace(time, '').trim();
                    content = content.replace(/^\d+\s*星?\s*/, '').trim();
                }

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

    def _get_xhr_comments(self) -> List[Dict]:
        """从 init script 注入的 XHR 拦截器获取评论"""
        js = "() => window.__capturedReviews || []"
        try:
            return self._page.evaluate(js) or []
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 截图兜底（当 DOM/API 均无法提取评论时）
    # ------------------------------------------------------------------

    def _capture_comment_screenshots(self, product_url: str, product_id: str, max_shots: int = 5) -> List[str]:
        """
        滚动评论区并逐屏截图，保存到临时目录。
        返回截图文件路径列表。
        """
        Path(self._screenshot_dir).mkdir(parents=True, exist_ok=True)
        screenshots = []
        try:
            # 确保已滚动到评论区
            self._open_comments_tab()
            self._human_delay(1500, 2500)

            for i in range(max_shots):
                ts = time.strftime("%Y%m%d_%H%M%S")
                fname = f"jd_{product_id}_{ts}_{i+1}.png"
                fpath = os.path.join(self._screenshot_dir, fname)
                try:
                    self._page.screenshot(path=fpath, full_page=False)
                    screenshots.append(fpath)
                    print(f"[jd-pw] 截图 {i+1}/{max_shots}: {fname}")
                except Exception as e:
                    print(f"[jd-pw] 截图失败 ({i+1}): {e}")
                if i < max_shots - 1:
                    self._human_scroll(random.randint(500, 900))
                    self._human_delay(1000, 2000)
        except Exception as e:
            print(f"[jd-pw] 截图流程异常: {e}")
        return screenshots

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
            "source_platform": "jd",
            "source_url": product_url,
            "product_id": product_id,
            "review_permalink": f"{product_url}#comment-{comment_id}" if comment_id else f"{product_url}#comment",
            "reviewer_name": user_name,
            "reviewer_id": user_id,
            "review_date": review_date,
            "sku": sku,
            "is_demo": False,
            "extraction_method": f"{self._driver_name}_{source}",
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
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
                try:
                    dt = time.strptime(raw, fmt)
                    return time.strftime("%Y-%m-%d %H:%M:%S", dt)
                except (ValueError, TypeError):
                    continue
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
        抓取京东商品评论 — Patchright 反检测浏览器方式

        参数:
            product_url: 商品 URL（支持短链 u.jd.com）
            cookies: 可选 Cookie
            max_reviews: 最大评论数

        返回:
            评论列表（含完整溯源字段）
        """
        print(f"[jd-pw] 开始抓取: {product_url}")
        self._api_comments = []

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

        # 设置 API 路由拦截
        self._setup_route_interception()

        all_reviews: List[Dict] = []
        seen_keys = set()

        try:
            # Step 3: 先访问首页建立会话（降低风控）
            print("[jd-pw] 访问京东首页建立会话...")
            try:
                self._page.goto("https://www.jd.com/", wait_until="domcontentloaded", timeout=30000)
                self._human_delay(2000, 4000)
                self._human_mouse_move()
            except Exception as e:
                print(f"[jd-pw] 首页访问异常（可忽略）: {e}")

            # Step 4: 检查登录态，未登录则引导用户扫码登录
            if not self._is_logged_in():
                print("[jd-pw] 未检测到京东登录态，引导用户登录...")
                logged_in = self._ensure_logged_in(timeout_sec=180)
                if not logged_in:
                    print("[jd-pw] 用户未完成登录，继续尝试抓取（可能受限）")
            else:
                print("[jd-pw] 已登录京东")

            # Step 5: 打开商品页面
            print(f"[jd-pw] 打开商品页面: {product_url}")
            self._page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
            self._human_delay(3000, 5000)
            self._human_mouse_move()

            # Step 6: 风控检测
            if self._check_blocked():
                print("[jd-pw] 检测到京东风控页面")
                if not self.headless:
                    passed = self._wait_for_manual_verification(120)
                    if not passed:
                        print("[jd-pw] 未通过验证，尝试继续...")
                else:
                    print("[jd-pw] headless 模式下无法手动验证，尝试继续...")

            # Step 7: 获取商品名称
            product_name = ""
            try:
                product_name = self._page.evaluate("""
                    () => {
                        const el = document.querySelector(
                            '.sku-name, .itemInfo-wrap .sku-name, [class*="product-name"], [class*="goodsName"]'
                        );
                        if (el) return (el.innerText || el.textContent || '').trim().split('\\n')[0];
                        return document.title.split('-')[0].trim();
                    }
                """)
                print(f"[jd-pw] 商品名: {product_name}")
            except Exception:
                pass

            # Step 8: 缓慢滚动到评论区（模拟人类浏览）
            print("[jd-pw] 滚动到评论区...")
            for _ in range(random.randint(2, 4)):
                self._human_scroll(random.randint(400, 800))

            # Step 9: 点击评论标签
            self._open_comments_tab()

            # Step 10: 滚动加载并提取评论
            stagnant_rounds = 0
            max_rounds = 25
            target = min(max_reviews, self.max_reviews) if max_reviews else self.max_reviews

            print(f"[jd-pw] 开始滚动加载评论（目标: {target} 条）...")

            for round_num in range(max_rounds):
                if len(all_reviews) >= target:
                    break

                before_count = len(all_reviews)

                # 从 route 拦截的 API 评论提取
                for comment in self._api_comments:
                    if len(all_reviews) >= target:
                        break
                    review = self._format_review(comment, product_id, product_url, product_name, source="api")
                    if review:
                        key = str(comment.get("id") or "")
                        if not key:
                            key = f"{review.get('reviewer_name','')}|{review.get('review_date','')}|{review.get('review_text','')[:50]}"
                        if key not in seen_keys:
                            seen_keys.add(key)
                            all_reviews.append(review)

                # 从 XHR 拦截器提取（备份）
                xhr_comments = self._get_xhr_comments()
                for comment in xhr_comments:
                    if len(all_reviews) >= target:
                        break
                    review = self._format_review(comment, product_id, product_url, product_name, source="api")
                    if review:
                        key = str(comment.get("id") or "")
                        if not key:
                            key = f"{review.get('reviewer_name','')}|{review.get('review_date','')}|{review.get('review_text','')[:50]}"
                        if key not in seen_keys:
                            seen_keys.add(key)
                            all_reviews.append(review)

                # 从 DOM 提取
                dom_comments = self._extract_comments_from_dom()
                for comment in dom_comments:
                    if len(all_reviews) >= target:
                        break
                    review = self._format_review(comment, product_id, product_url, product_name, source="dom")
                    if review:
                        key = comment.get("comment_id") or f"{review.get('reviewer_name','')}|{review.get('review_date','')}|{review.get('review_text','')[:50]}"
                        if key not in seen_keys:
                            seen_keys.add(key)
                            all_reviews.append(review)

                new_count = len(all_reviews) - before_count
                if new_count == 0:
                    stagnant_rounds += 1
                    if stagnant_rounds >= 6:
                        print(f"[jd-pw] 连续 {stagnant_rounds} 轮无新评论，停止滚动")
                        break
                else:
                    stagnant_rounds = 0
                    print(f"[jd-pw] 第 {round_num + 1} 轮: 新增 {new_count} 条 (累计 {len(all_reviews)})")

                # 人类滚动
                self._human_scroll()

                # 偶尔移动鼠标
                if random.random() < 0.4:
                    self._human_mouse_move()

            # Step 11: 尝试翻页
            if len(all_reviews) < target:
                for page_num in range(5):
                    if len(all_reviews) >= target:
                        break
                    try:
                        next_btn = self._page.locator("text=下一页, a:has-text('下一页'), .ui-pager-next").first
                        if next_btn.count() > 0 and next_btn.is_visible():
                            next_btn.click(timeout=3000)
                            self._human_delay(2000, 4000)
                            self._human_scroll(random.randint(300, 600))

                            # 提取新页评论
                            for comment in self._api_comments + self._get_xhr_comments() + self._extract_comments_from_dom():
                                if len(all_reviews) >= target:
                                    break
                                src = "api" if comment in self._api_comments or "nickname" in comment else "dom"
                                review = self._format_review(comment, product_id, product_url, product_name, source=src)
                                if review:
                                    key = str(comment.get("id") or comment.get("comment_id") or "")
                                    if not key:
                                        key = f"{review.get('reviewer_name','')}|{review.get('review_date','')}|{review.get('review_text','')[:50]}"
                                    if key not in seen_keys:
                                        seen_keys.add(key)
                                        all_reviews.append(review)
                        else:
                            break
                    except Exception:
                        break

            print(f"[jd-pw] 抓取完成: {len(all_reviews)} 条真实评论")

            # Step 12: 如果没有抓到评论，用截图兜底
            if not all_reviews and not self.headless:
                print("[jd-pw] DOM/API 均未提取到评论，启用截图兜底模式...")
                self._screenshots = self._capture_comment_screenshots(
                    product_url, product_id, max_shots=5
                )
                if self._screenshots:
                    print(f"[jd-pw] 已截取 {len(self._screenshots)} 张评论区截图，交由 OCR 分析")

        except Exception as e:
            print(f"[jd-pw] 抓取异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._close_browser()

        return all_reviews[:target]

    def get_screenshots(self) -> List[str]:
        """返回截图兜底模式生成的截图路径列表"""
        return self._screenshots

    def _wait_for_login(self, timeout_sec: int = 180) -> bool:
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
    便捷函数：使用 Patchright 抓取京东评论

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
