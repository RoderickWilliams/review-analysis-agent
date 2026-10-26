# -*- coding: utf-8 -*-
"""
登录子进程脚本 — 独立运行 Selenium 登录，不阻塞 Streamlit
=================================================================
用法: python -m reviewagent.login_subprocess <platform>
平台: taobao / jd
"""
import sys

from reviewagent.auto_login import AutoLoginManager


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("用法: python -m reviewagent.login_subprocess <platform>")
        return 1

    platform = argv[0]
    print(f"[login_subprocess] 开始自动登录 {platform}...")

    manager = AutoLoginManager()
    result = manager.auto_login(platform, timeout=300)

    if result["success"]:
        print(f"[login_subprocess] 登录成功: {result['message']}")
        return 0
    print(f"[login_subprocess] 登录失败: {result['message']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
