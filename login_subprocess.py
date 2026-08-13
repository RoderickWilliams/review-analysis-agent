# -*- coding: utf-8 -*-
"""
登录子进程脚本 — 独立运行 Selenium 登录，不阻塞 Streamlit
=================================================================
由 app.py 通过 subprocess 启动，独立打开浏览器完成登录后保存Cookie。
"""
import sys
import os

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from auto_login import AutoLoginManager


def main():
    if len(sys.argv) < 2:
        print("用法: python login_subprocess.py <platform>")
        sys.exit(1)

    platform = sys.argv[1]
    print(f"[login_subprocess] 开始自动登录 {platform}...")

    manager = AutoLoginManager()
    result = manager.auto_login(platform, timeout=300)

    if result["success"]:
        print(f"[login_subprocess] 登录成功: {result['message']}")
        sys.exit(0)
    else:
        print(f"[login_subprocess] 登录失败: {result['message']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
