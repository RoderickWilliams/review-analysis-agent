"""Owned browser profiles. Never attach to or copy the user's daily profile."""
from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime

from reviewagent import config

_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


class BrowserUnavailable(ValueError):
    pass


class BrowserProfileBusy(ValueError):
    pass


class BrowserNavigationError(RuntimeError):
    """A safe, user-facing navigation failure without leaking full URLs."""

    def __init__(self, message: str, *, code: str = "navigation_failed"):
        super().__init__(message)
        self.code = code


def _navigation_error(exc: Exception) -> BrowserNavigationError:
    detail = str(exc).upper()
    cases = (
        (("ERR_NAME_NOT_RESOLVED", "DNS"), "navigation_dns_failed", "浏览器无法解析商品页域名"),
        (("ERR_PROXY_CONNECTION_FAILED", "ERR_TUNNEL_CONNECTION_FAILED"), "navigation_proxy_failed", "浏览器连接被代理设置阻断"),
        (("ERR_CONNECTION_CLOSED", "ERR_CONNECTION_RESET", "ERR_CONNECTION_REFUSED"), "navigation_connection_failed", "浏览器与商品页的连接未能建立"),
        (("ERR_ABORTED",), "navigation_aborted", "浏览器中止了商品页导航"),
        (("TIMEOUT", "TIMED OUT", "ERR_TIMED_OUT"), "navigation_timeout", "浏览器等待商品页响应超时"),
    )
    for markers, code, message in cases:
        if any(marker in detail for marker in markers):
            return BrowserNavigationError(message, code=code)
    return BrowserNavigationError("浏览器未能打开商品页", code="navigation_failed")


def platform_key(platform: str) -> str:
    key = "taobao" if platform == "tmall" else platform
    if key not in {"jd", "taobao", "xhs"}:
        raise ValueError("不支持此平台的浏览器登录")
    return key


def _browser_from_command(command: str) -> tuple[str, str]:
    # Only use the executable, never launch a registry command through a shell.
    match = re.match(r'^\s*(?:"([^"\r\n]+)"|([^\s]+))', command)
    executable = os.path.expandvars((match.group(1) or match.group(2)) if match else "")
    name = Path(executable.replace("\\", "/")).name.lower()
    engines = {"chrome.exe": "chrome", "msedge.exe": "edge", "firefox.exe": "firefox",
               "google-chrome": "chrome", "chromium": "chrome", "firefox": "firefox"}
    engine = engines.get(name)
    if not engine or not Path(executable).is_file():
        raise BrowserUnavailable("当前默认浏览器暂不受支持，请使用 Chrome、Edge 或 Firefox 作为默认浏览器")
    return engine, executable


def _system_browser() -> tuple[str, str]:
    """Resolve the OS association; no browser processes or credentials are touched."""
    if os.name == "nt":
        import winreg
        try:
            association = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, association) as key:
                prog_id = winreg.QueryValueEx(key, "ProgId")[0]
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id + r"\shell\open\command") as key:
                command = winreg.QueryValueEx(key, None)[0]
            return _browser_from_command(command)
        except OSError:
            raise BrowserUnavailable("无法读取默认浏览器设置，请在系统中设置默认浏览器后重试") from None
    if shutil.which("xdg-settings"):
        result = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True, timeout=5)
        desktop = result.stdout.strip().lower()
        names = ("firefox",) if "firefox" in desktop else ("google-chrome", "chromium") if "chrome" in desktop or "chromium" in desktop else ()
        for name in names:
            executable = shutil.which(name)
            if executable:
                return _browser_from_command(executable)
    raise BrowserUnavailable("当前系统的默认浏览器连接暂不受支持")


def default_browser() -> tuple[str, str]:
    preference = getattr(config, "BROWSER_PREFERENCE", os.environ.get("REVIEWAGENT_BROWSER", "auto"))
    if preference == "auto":
        return _system_browser()
    if preference not in {"edge", "chrome", "firefox"}:
        raise BrowserUnavailable("请选择系统默认、Edge、Chrome 或 Firefox")
    names = {"edge": ["Microsoft/Edge/Application/msedge.exe"],
             "chrome": ["Google/Chrome/Application/chrome.exe"],
             "firefox": ["Mozilla Firefox/firefox.exe"]}[preference]
    for base in (os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("LOCALAPPDATA", "")):
        for name in names:
            candidate = Path(base) / name
            if base and candidate.is_file():
                return preference, str(candidate)
    executable = shutil.which({"edge": "microsoft-edge", "chrome": "google-chrome", "firefox": "firefox"}[preference])
    if executable:
        return preference, executable
    raise BrowserUnavailable("未找到所选浏览器，请安装或改用本机已有浏览器")


def profile_directory(platform: str, engine: str) -> Path:
    if engine not in {"chrome", "edge", "firefox"}:
        raise BrowserUnavailable("不支持的浏览器类型")
    return config.HOME_DIR / "browser-profiles" / platform_key(platform) / engine


def has_saved_session(platform: str) -> bool:
    engine, _ = default_browser()
    return (profile_directory(platform, engine) / ".reviewagent-session.json").is_file()


def record_authenticated(driver, platform: str):
    # Cookies stay in the browser's own profile, not an extra plaintext JSON export.
    profile = driver._profile_directory
    marker = profile / ".reviewagent-session.json"
    temporary = profile / ".reviewagent-session.tmp"
    temporary.write_text(json.dumps({"platform": platform_key(platform),
                                    "last_confirmed_at": datetime.now().astimezone().isoformat(),
                                    "state": "previously_authenticated"}), encoding="utf-8")
    os.replace(temporary, marker)


class OwnedDriver:
    """Release only this driver and its profile lease, even on cancellation."""

    def __init__(self, driver, lease):
        self._driver = driver
        self._lease = lease
        self._closed = False

    def __getattr__(self, name):
        return getattr(self._driver, name)

    def quit(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._driver.quit()
        finally:
            self._lease.close()


class _ProfileLease:
    def __init__(self, profile: Path):
        with _locks_guard:
            self.lock = _locks.setdefault(str(profile), threading.Lock())
        if not self.lock.acquire(blocking=False):
            raise BrowserProfileBusy("此平台的专用浏览器正在使用，请等待该任务完成")
        self.handle = None
        try:
            profile.mkdir(parents=True, exist_ok=True)
            self.handle = (profile / ".reviewagent.lock").open("a+b")
            self.handle.seek(0, 2)
            if self.handle.tell() == 0:
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            if self.handle:
                self.handle.close()
            self.lock.release()
            raise BrowserProfileBusy("此平台的浏览器配置被占用，稍后可从断点继续") from None

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
            self.lock.release()


def open_driver(platform: str, *, headless: bool = False):
    """Use the installed default browser with a dedicated persistent profile."""
    from selenium import webdriver

    engine, executable = default_browser()
    profile = profile_directory(platform, engine)
    lease = _ProfileLease(profile)
    try:
        if engine in {"chrome", "edge"}:
            try:
                from DrissionPage import Chromium, ChromiumOptions
            except ImportError:
                pass
            else:
                import socket
                with socket.socket() as reserved:
                    reserved.bind(("127.0.0.1", 0))
                    port = reserved.getsockname()[1]
                options = ChromiumOptions(read_file=False)
                options.set_browser_path(executable).set_local_port(port).set_user_data_path(str(profile))
                options.set_load_mode("eager")
                options.set_argument("--window-size", "1280,900")
                if getattr(config, "BROWSER_NETWORK", "direct") == "direct":
                    options.set_argument("--no-proxy-server")
                options.headless(headless)
                browser = Chromium(options)
                driver = _CdpDriver(browser, browser.latest_tab)
                owned = OwnedDriver(driver, lease)
                owned._profile_directory = profile
                return owned
        if engine == "firefox":
            options = webdriver.FirefoxOptions()
            options.binary_location = executable
            options.add_argument("-profile")
            options.add_argument(str(profile))
            if headless:
                options.add_argument("-headless")
            driver = webdriver.Firefox(options=options)
        else:
            options = webdriver.EdgeOptions() if engine == "edge" else webdriver.ChromeOptions()
            options.binary_location = executable
            options.page_load_strategy = "eager"
            if getattr(config, "BROWSER_NETWORK", "direct") == "direct":
                options.add_argument("--no-proxy-server")
            options.add_argument("--user-data-dir=" + str(profile))
            options.add_argument("--window-size=1280,900")
            if headless:
                options.add_argument("--headless=new")
            driver = webdriver.Edge(options=options) if engine == "edge" else webdriver.Chrome(options=options)
        owned = OwnedDriver(driver, lease)
        owned._profile_directory = profile
        try:
            owned.set_page_load_timeout(30)
            owned.set_script_timeout(15)
        except Exception:
            owned.quit()
            raise
        return owned
    except Exception:
        lease.close()
        raise


class _CdpElement:
    def __init__(self, element):
        self.element = element

    @property
    def text(self):
        return self.element.text

    def is_displayed(self):
        return self.element.states.is_displayed

    def click(self):
        return self.element.click()


class _CdpDriver:
    """Same owned browser contract without a separately downloaded WebDriver."""
    def __init__(self, browser, tab):
        self.browser, self.tab = browser, tab
        self._listening = False

    @property
    def current_url(self):
        return self.tab.url

    @property
    def window_handles(self):
        return self.browser.tab_ids

    def get(self, url):
        try:
            loaded = self.tab.get(url, timeout=25, retry=0, show_errmsg=True)
        except Exception as exc:
            failure = _navigation_error(exc)
            if failure.code != "navigation_aborted":
                raise failure from None
            # Redirects can abort Page.navigate while a document is still loading.
            # Observe that navigation first; never refresh a live login/verification page.
            if self._wait_for_document(2):
                return
            # Target.url may already contain the requested URL while the actual
            # document is still the new-tab or browser error document.
            try:
                actual = self.tab.run_js("return {url: location.href, text: (document.body?.innerText || '').trim().length};", timeout=2)
            except Exception:
                raise BrowserNavigationError("导航被中止，且无法确认当前文档；已停止，未执行备用导航", code="navigation_aborted") from None
            if not isinstance(actual, dict) or not isinstance(actual.get("url"), str):
                raise BrowserNavigationError("导航被中止，当前文档状态未知；已停止，未执行备用导航", code="navigation_aborted") from None
            current = actual["url"].strip().lower()
            blank = not current or current in {"about:blank", "chrome://newtab/", "chrome://new-tab-page/", "edge://newtab/"} or current.startswith("chrome-error://")
            if not blank:
                raise BrowserNavigationError("导航被中止，当前文档不是空白页；为保留平台登录或验证页面，未再次导航", code="navigation_aborted") from None
            # One fallback on the same owned tab, only while it is still blank.
            # Schedule navigation so context destruction does not swallow its result.
            try:
                self.tab.run_js("const target = arguments[0]; setTimeout(() => location.assign(target), 0); return true;", url, timeout=5)
                if self._wait_for_document(15):
                    return
            except Exception as fallback_exc:
                fallback_failure = _navigation_error(fallback_exc)
                raise BrowserNavigationError("备用导航执行失败：" + str(fallback_failure), code=fallback_failure.code) from None
            raise BrowserNavigationError("备用导航后仍未进入可读取的页面，已停止本次采集", code="navigation_aborted") from None
        if loaded is not True:
            raise BrowserNavigationError("浏览器未能打开商品页，页面仍停留在新标签页", code="navigation_failed")
        current = (self.current_url or "").strip().lower()
        if not current or current in {"about:blank", "chrome://newtab/", "chrome://new-tab-page/", "edge://newtab/"}:
            raise BrowserNavigationError("浏览器未能打开商品页，页面仍停留在新标签页", code="navigation_failed")

    def _wait_for_document(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                ready = self.tab.run_js("return location.protocol === 'https:' && ['interactive', 'complete'].includes(document.readyState) && !!document.body && document.body.innerText.trim().length > 0;", timeout=1)
                if ready is True:
                    return True
            except Exception as exc:
                if type(exc).__name__ in {"PageDisconnectedError", "TargetClosedError"}:
                    raise
                # Context can briefly disappear during a normal redirect.
            time.sleep(.2)
        return False

    def execute_script(self, script, *args):
        return self.tab.run_js(script, *args, timeout=15)

    def find_elements(self, by, selector):
        prefix = "x:" if by == "xpath" else "css:"
        return [_CdpElement(element) for element in self.tab.eles(prefix + selector, timeout=.5)]

    def get_cookies(self):
        return self.tab.cookies(all_domains=False, all_info=True)

    def start_review_listener(self):
        self.tab.listen.start(r"productPageComments|rate\.taobao\.com|rate\.tmall\.com|mtop\.taobao\.rate|mtop\.tmall\.rate|/api/sns/web/v2/comment", is_regex=True)
        self._listening = True

    def follow_login_tab(self, platform):
        from urllib.parse import urlsplit
        domains = {"jd": ("jd.com",), "taobao": ("taobao.com", "tmall.com"), "xhs": ("xiaohongshu.com",)}[platform_key(platform)]
        candidates = []
        for tab in self.browser.get_tabs():
            if tab.tab_id == self.tab.tab_id:
                continue
            parsed = urlsplit(tab.url)
            host = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or not any(host == domain or host.endswith("." + domain) for domain in domains):
                continue
            if host.startswith(("login.", "passport.")) or any(part in parsed.path.lower() for part in ("login", "captcha", "verify")):
                continue
            score = 2 if parsed.path.endswith(("item.htm", ".html")) or "/explore/" in parsed.path else 1
            candidates.append((score, tab))
        if candidates:
            if self._listening:
                try:
                    self.tab.listen.stop()
                except Exception:
                    pass
            self.tab = max(candidates, key=lambda item: item[0])[1]
            if self._listening:
                self.start_review_listener()
            return True
        return False

    def review_payloads(self):
        payloads = []
        for _ in range(50):
            packet = self.tab.listen.wait(timeout=.05, raise_err=False)
            if not packet:
                break
            if packet.response.status == 200:
                body = packet.response.body
                if isinstance(body, (dict, list)) or isinstance(body, str) and len(body) <= 3_000_000:
                    payloads.append(body)
        return payloads

    def quit(self):
        self.browser.quit(timeout=5)
