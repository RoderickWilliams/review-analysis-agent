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
from typing import Dict, Optional, List

# Cookie 保存目录
COOKIE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cookies"
)

# 各平台登录页URL和登录成功判断条件
LOGIN_CONFIG = {
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
        """创建Selenium WebDriver实例"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
        except ImportError:
            raise ImportError(
                "请先安装 Selenium: pip install selenium\n"
                "并确保已安装 Chrome 浏览器"
            )

        options = Options()

        # Selenium 4 内置驱动管理器，自动匹配 Chrome 版本
        try:
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            raise RuntimeError(
                f"无法启动 Chrome 浏览器: {e}\n"
                "请确保已安装 Chrome 浏览器"
            )

        return driver

    def _is_login_success(self, driver, platform: str) -> bool:
        """检查是否登录成功"""
        config = LOGIN_CONFIG.get(platform, {})
        current_url = driver.current_url.lower()

        # 如果URL中还有login字样，说明还在登录页
        if "login" in current_url:
            return False

        # 检查是否到达成功页面
        for success_url in config.get("success_urls", []):
            if success_url in current_url:
                return True

        return False

    def auto_login(
        self,
        platform: str,
        timeout: int = 300,
        headless: bool = False,
    ) -> Dict:
        """
        自动登录平台并获取Cookie。

        流程:
        1. 打开Chrome浏览器到平台登录页
        2. 用户正常登录（扫码/账密）
        3. 系统自动检测登录成功
        4. 自动提取Cookie并保存

        :param platform: 平台名称 (taobao/jd)
        :param timeout: 登录超时时间（秒），默认5分钟
        :param headless: 是否无头模式（不推荐，登录需要用户交互）
        :return: {"success": bool, "cookies": dict, "message": str}
        """
        config = LOGIN_CONFIG.get(platform)
        if not config:
            return {
                "success": False,
                "cookies": {},
                "message": f"不支持的平台: {platform}",
            }

        print(f"\n{'='*60}")
        print(f"  自动登录 {config['name']}")
        print(f"{'='*60}")
        print(f"  即将打开浏览器，请在浏览器中完成登录")
        print(f"  超时时间: {timeout}秒 ({timeout//60}分钟)")
        print(f"{'='*60}\n")

        try:
            driver = self._get_driver()
        except Exception as e:
            return {
                "success": False,
                "cookies": {},
                "message": str(e),
            }

        try:
            # 打开登录页
            driver.get(config["login_url"])
            print(f"[auto_login] 已打开 {config['name']} 登录页")
            print(f"[auto_login] 请在浏览器中完成登录...")

            # 等待登录成功
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._is_login_success(driver, platform):
                    print(f"[auto_login] 检测到登录成功!")
                    break

                # 检查浏览器是否被用户关闭
                try:
                    _ = driver.current_url
                except Exception:
                    return {
                        "success": False,
                        "cookies": {},
                        "message": "浏览器已关闭，登录取消",
                    }

                time.sleep(2)  # 每2秒检查一次
            else:
                return {
                    "success": False,
                    "cookies": {},
                    "message": f"登录超时（{timeout}秒），请重试",
                }

            # 等待页面完全加载
            time.sleep(3)

            # 获取Cookie
            selenium_cookies = driver.get_cookies()

            # 转换为字典格式
            cookies = {}
            for cookie in selenium_cookies:
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                if name and value:
                    cookies[name] = value

            # 保存Cookie
            if cookies:
                self._save_cookies(platform, cookies)
                print(f"[auto_login] 已保存 {len(cookies)} 个Cookie")
            else:
                print(f"[auto_login] 警告: 未获取到Cookie")

            # 关闭浏览器
            driver.quit()

            return {
                "success": True,
                "cookies": cookies,
                "message": f"登录成功，已获取 {len(cookies)} 个Cookie",
            }

        except Exception as e:
            try:
                driver.quit()
            except Exception:
                pass
            return {
                "success": False,
                "cookies": {},
                "message": f"登录过程出错: {e}",
            }

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
            # 检查Cookie是否过期（24小时）
            saved_time = data.get("saved_at", 0)
            if time.time() - saved_time > 86400:
                return None
            return data.get("cookies")
        except Exception:
            return None

    def has_valid_cookies(self, platform: str) -> bool:
        """检查是否已有有效Cookie"""
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
        import webdriver_manager
        instructions.append("✅ webdriver-manager 已安装（自动管理ChromeDriver）")
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
