# -*- coding: utf-8 -*-
"""
自动登录模块 — 使用 Selenium 自动打开浏览器并捕获Cookie
=========================================================
用户只需点击"一键登录"，浏览器自动打开平台登录页，
用户正常登录后（扫码/账密），系统自动获取Cookie。

依赖: pip install selenium
驱动: Chrome浏览器 + ChromeDriver (或使用webdriver-manager自动管理)
"""

import os
import json
import time
from urllib.parse import urlsplit

from reviewagent.browser_session import open_driver, platform_key, has_saved_session, record_authenticated
from typing import Dict, Optional

# Cookie 保存目录（跟随 REVIEWAGENT_HOME）
from reviewagent.config import HOME_DIR

COOKIE_DIR = str(HOME_DIR / "cookies")

# 各平台登录页URL和登录成功判断条件
LOGIN_CONFIG = {
    "xhs": {
        "login_url": "https://www.xiaohongshu.com/explore",
        "fail_urls": ["login.xiaohongshu.com"],
        "name": "小红书",
    },
    "taobao": {
        "login_url": "https://login.taobao.com/",
        "success_urls": ["i.taobao.com", "my.taobao.com", "taobao.com"],
        "fail_urls": ["login.taobao.com"],
        "name": "淘宝/天猫",
    },
    "jd": {
        "login_url": "https://passport.jd.com/new/login.aspx",
        "success_urls": ["jd.com", "home.jd.com"],
        "fail_urls": ["passport.jd.com"],
        "name": "京东",
    },
}


class AutoLoginManager:
    """自动登录管理器 — 使用Selenium自动捕获Cookie"""

    def __init__(self):
        os.makedirs(COOKIE_DIR, exist_ok=True)

    def _get_driver(self):
        """只启动本次拥有的专用窗口，复用平台独立配置。"""
        return open_driver(self._platform, headless=self._headless)

    def _is_login_success(self, driver, platform: str, *, allow_login_result=False) -> bool:
        """检查是否登录成功"""
        config = LOGIN_CONFIG.get(platform)
        if not config:
            return False
        try:
            parsed = urlsplit(driver.current_url)
            host = (parsed.hostname or "").lower().rstrip(".")
            domains = {"jd": ("jd.com",), "taobao": ("taobao.com", "tmall.com"), "xhs": ("xiaohongshu.com",)}[platform]
            if parsed.scheme != "https" or not any(host == domain or host.endswith("." + domain) for domain in domains):
                return False
            if not allow_login_result and (host in config.get("fail_urls", []) or any(word in parsed.path.lower() for word in ("login", "passport", "captcha", "verify"))):
                return False
            cookies = {item.get("name") for item in driver.get_cookies() if item.get("value")}
            alternatives = {"jd": ({"pt_key", "pt_pin"}, {"thor", "pin"}, {"thor", "unick"}),
                            "taobao": ({"unb", "cookie2"}, {"unb", "sgcookie"}),
                            "xhs": ({"web_session"},)}[platform]
            if not any(required.issubset(cookies) for required in alternatives):
                return False
            selector = {"jd": ".nickname", "taobao": ".site-nav-login-info-nick",
                        "xhs": ".side-bar .user[href*='/user/profile/'], .side-bar .user a[href*='/user/profile/'], .side-bar-component.user[href*='/user/profile/']"}[platform]
            account_visible = any(element.is_displayed() and element.text.strip() and element.text.strip() not in {"登录", "请登录", "免费注册", "登录/注册"}
                                  for element in driver.find_elements("css selector", selector))
            if account_visible:
                return True
            return bool(allow_login_result and driver.execute_script("return /登录成功|验证成功|您已成功登录/.test(document.body?.innerText || '');"))
        except Exception:
            return False

    def auto_login(self, platform: str, timeout: int = 300, headless: bool = False,
                   *, should_cancel=None, on_state=None) -> Dict:
        """扫码由用户完成；回调仅输出状态，不输出 Cookie 或配置路径。"""
        platform = platform_key(platform)
        self._platform, self._headless = platform, headless
        cancelled = should_cancel or (lambda: False)
        def emit(status, message):
            if on_state:
                on_state({"platform": platform, "status": status, "message": message})
        def outcome(status, message, cookies=None):
            emit(status, message)
            return {"success": status == "authenticated", "status": status,
                    "message": message, "cookies": cookies or {}}
        if cancelled():
            return outcome("login_cancelled", "已取消登录，采集进度已保留")
        emit("checking_session" if headless else "opening_browser",
             "正在确认已保存的登录状态" if headless else "正在打开本机专用浏览器，请稍候")
        driver = None
        try:
            driver = self._get_driver()
            driver.get(LOGIN_CONFIG[platform]["login_url"])
            if not headless:
                emit("awaiting_login", "请在已打开的 ReviewAgent 专用窗口中扫码登录，成功后自动继续")
            deadline = time.monotonic() + min(300, max(0, timeout))
            while time.monotonic() < deadline:
                if cancelled():
                    return outcome("login_cancelled", "已取消登录，采集进度已保留")
                if self._is_login_success(driver, platform):
                    cookies = {c["name"]: c["value"] for c in driver.get_cookies()
                               if c.get("name") and c.get("value")}
                    if not cookies:
                        break
                    record_authenticated(driver, platform)
                    return outcome("authenticated", "登录状态已保存在本机专用配置中", cookies)
                # User closing the owned window is cancellation, not success.
                if not driver.window_handles:
                    return outcome("login_cancelled", "登录窗口已关闭，可稍后从断点继续")
                time.sleep(1)
            return outcome("needs_login" if headless else "login_timeout",
                           "保存的会话需要重新登录" if headless else "扫码等待超时，已有采集进度已保留")
        except Exception as exc:
            from reviewagent.browser_session import BrowserUnavailable, BrowserProfileBusy
            if isinstance(exc, (BrowserUnavailable, BrowserProfileBusy, ImportError)):
                message = str(exc) if not isinstance(exc, ImportError) else "登录需要 Selenium 采集依赖，请先完成项目安装"
                return outcome("login_unavailable", message)
            return outcome("login_unavailable", "登录窗口连接未完成，请关闭本任务专用窗口后重试；已有进度已保留")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    def ensure_session(self, platform: str, *, should_cancel=None, on_state=None) -> Dict:
        platform = platform_key(platform)
        if has_saved_session(platform):
            result = self.auto_login(platform, timeout=12, headless=True,
                                     should_cancel=should_cancel, on_state=on_state)
            if result["success"] or result["status"] in {"login_cancelled", "login_unavailable"}:
                return result
        return self.auto_login(platform, should_cancel=should_cancel, on_state=on_state)

    def _save_cookies(self, platform: str, cookies: Dict):
        """保存Cookie到文件"""
        cookie_path = os.path.join(COOKIE_DIR, f"{platform}_cookies.json")
        data = {
            "platform": platform,
            "cookies": cookies,
            "saved_at": time.time(),
            "source": "auto_login_selenium",
        }
        with open(cookie_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_cookies(self, platform: str) -> Optional[Dict]:
        """加载已保存的Cookie"""
        cookie_path = os.path.join(COOKIE_DIR, f"{platform}_cookies.json")
        if not os.path.exists(cookie_path):
            return None
        try:
            with open(cookie_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 保存时间不是平台会话有效期；无明确到期时间时保留为可复用候选。
            # 平台拒绝后仍需重新登录，文件存在不能证明服务端会话有效。
            expires_at = data.get("expires_at")
            if expires_at is not None and float(expires_at) <= time.time():
                return None
            cookies = data.get("cookies")
            return cookies if isinstance(cookies, dict) and cookies else None
        except Exception:
            return None

    def has_valid_cookies(self, platform: str) -> bool:
        """检查本地是否有可复用候选；平台会话有效性需实际请求确认。"""
        return self.load_cookies(platform) is not None


def check_selenium_available() -> dict:
    """
    检查 Selenium 和 Chrome 是否可用。

    :return: {"available": bool, "message": str, "instructions": list}
    """
    instructions = []
    available = True
    message = ""

    # 检查 selenium
    try:
        import selenium
        instructions.append(f"✅ Selenium 已安装 (v{selenium.__version__})")
    except ImportError:
        available = False
        instructions.append("❌ Selenium 未安装，请运行: pip install selenium")
        message = "Selenium 未安装"

    # 检查 webdriver-manager
    try:
        from importlib.util import find_spec
        if find_spec("webdriver_manager") is not None:
            instructions.append("✅ webdriver-manager 已安装（自动管理ChromeDriver）")
        else:
            instructions.append("⚠️ webdriver-manager 未安装，建议运行: pip install webdriver-manager")
    except ImportError:
        instructions.append("⚠️ webdriver-manager 未安装，建议运行: pip install webdriver-manager")

    # 检查 Chrome
    try:
        if os.name == "nt":  # Windows
            chrome_paths = [
                os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ]
            chrome_found = any(os.path.exists(p) for p in chrome_paths)
        else:
            chrome_found = os.system("which google-chrome > /dev/null 2>&1") == 0

        if chrome_found:
            instructions.append("✅ Chrome 浏览器已检测到")
        else:
            available = False
            instructions.append("❌ 未检测到 Chrome 浏览器，请安装 Google Chrome")
            if not message:
                message = "Chrome 浏览器未安装"
    except Exception:
        instructions.append("⚠️ 无法检测 Chrome 浏览器，自动登录可能不可用")

    if available and not message:
        message = "自动登录功能可用"
    elif not message:
        message = "部分功能不可用"

    return {
        "available": available,
        "message": message,
        "instructions": instructions,
    }


def generate_bookmarklet(platform: str) -> str:
    """
    生成书签栏小工具（bookmarklet），用于一键复制Cookie。

    用户将此代码保存为书签，在登录淘宝后点击书签即可复制Cookie。

    :param platform: 平台名称
    :return: bookmarklet JavaScript代码
    """
    bookmarklet = (
        "javascript:(function(){"
        "var cookies=document.cookie;"
        "if(navigator.clipboard){"
        "navigator.clipboard.writeText(cookies).then(function(){"
        "alert('Cookie已复制到剪贴板！共'+cookies.split(';').length+'个');"
        "},function(){"
        "prompt('请手动复制Cookie:',cookies);"
        "});"
        "}else{"
        "prompt('请手动复制Cookie:',cookies);"
        "}"
        "})();"
    )
    return bookmarklet
