# -*- coding: utf-8 -*-
"""
平台登录管理器
==============
当平台需要登录才能抓取评论时，引导用户完成登录并获取Cookie。

支持平台: 淘宝/天猫、京东
"""

import os
import json
import time
import webbrowser
from typing import Dict, Optional

# 各平台登录页面URL
LOGIN_URLS = {
    "taobao": "https://login.taobao.com/",
    "tmall": "https://login.tmall.com/",
    "jd": "https://passport.jd.com/new/login.aspx",
}

# Cookie 保存路径
COOKIE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies")


class LoginManager:
    """平台登录管理器"""

    def __init__(self):
        os.makedirs(COOKIE_DIR, exist_ok=True)

    def get_cookie_path(self, platform: str) -> str:
        """获取平台Cookie文件路径"""
        return os.path.join(COOKIE_DIR, f"{platform}_cookies.json")

    def has_valid_cookies(self, platform: str) -> bool:
        """检查是否已有有效Cookie"""
        cookie_path = self.get_cookie_path(platform)
        if not os.path.exists(cookie_path):
            return False
        try:
            with open(cookie_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 检查Cookie是否过期（24小时）
            saved_time = data.get("saved_at", 0)
            if time.time() - saved_time > 86400:
                return False
            return bool(data.get("cookies"))
        except Exception:
            return False

    def load_cookies(self, platform: str) -> Optional[Dict]:
        """加载已保存的Cookie"""
        if not self.has_valid_cookies(platform):
            return None
        cookie_path = self.get_cookie_path(platform)
        try:
            with open(cookie_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("cookies")
        except Exception:
            return None

    def save_cookies(self, platform: str, cookies: Dict):
        """保存Cookie"""
        cookie_path = self.get_cookie_path(platform)
        data = {
            "platform": platform,
            "cookies": cookies,
            "saved_at": time.time(),
        }
        with open(cookie_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def require_login(self, platform: str) -> Dict:
        """
        提示用户需要登录指定平台。

        在 CLI 模式下：
        1. 打开浏览器到登录页面
        2. 等待用户完成登录
        3. 用户输入Cookie字符串

        在 Web 模式下：
        1. 返回登录页面URL
        2. 用户提供Cookie

        :param platform: 平台名称
        :return: Cookie字典
        """
        login_url = LOGIN_URLS.get(platform, "")

        print(f"\n{'='*60}")
        print(f"  需要登录 {platform} 才能抓取评论")
        print(f"{'='*60}")
        print(f"\n请在浏览器中完成 {platform} 登录：")
        print(f"  登录地址: {login_url}")
        print(f"\n登录成功后，请按 F12 → Application → Cookies")
        print(f"复制 {platform} 域名下的所有Cookie，粘贴到下方：")
        print(f"\n格式: cookie_name=cookie_value; cookie_name2=cookie_value2")
        print(f"{'='*60}\n")

        # 打开浏览器
        if login_url:
            try:
                webbrowser.open(login_url)
                print(f"[已自动打开浏览器，请在浏览器中完成登录]")
            except Exception:
                pass

        # 等待用户输入Cookie
        cookie_str = input("请粘贴Cookie字符串（输入 q 取消）: ").strip()
        if cookie_str.lower() == "q":
            return {}

        # 解析Cookie字符串
        cookies = {}
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                cookies[k.strip()] = v.strip()

        if cookies:
            self.save_cookies(platform, cookies)
            print(f"\n[OK] 已保存 {platform} Cookie（{len(cookies)} 个）")
        else:
            print(f"\n[WARNING] 未解析到有效Cookie")

        return cookies

    def get_cookies_or_login(self, platform: str) -> Dict:
        """
        获取Cookie：先检查已有Cookie，没有则提示登录。

        :param platform: 平台名称
        :return: Cookie字典
        """
        # 先检查已有Cookie
        cookies = self.load_cookies(platform)
        if cookies:
            print(f"[{platform}] 使用已保存的Cookie")
            return cookies

        # 需要登录
        return self.require_login(platform)


def get_login_info_for_web(platform: str) -> Dict:
    """
    Web界面专用：返回登录信息（不直接打开浏览器）。

    :param platform: 平台名称
    :return: 包含登录URL和说明的字典
    """
    login_url = LOGIN_URLS.get(platform, "")
    return {
        "platform": platform,
        "login_url": login_url,
        "requires_login": True,
        "message": f"抓取{platform}评论需要登录，请先完成登录并提供Cookie",
        "instructions": [
            f"1. 在新窗口打开: {login_url}",
            "2. 完成{platform}账号登录",
            "3. 登录成功后，按 F12 打开开发者工具",
            "4. 切换到 Application → Cookies",
            f"5. 复制 {login_url.split('//')[1].split('/')[0]} 域名下的Cookie",
            "6. 将Cookie粘贴到下方的输入框中",
        ],
    }
