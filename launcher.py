#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ReviewAgent 启动器
==================
启动 Streamlit 服务器并自动打开浏览器。
"""

import os
import sys
import time
import threading
import webbrowser
import subprocess


def get_base_dir():
    """获取程序根目录（兼容 PyInstaller 打包和源码运行）。"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def open_browser_delayed(url: str, delay: float = 3.0):
    """延迟打开浏览器，等 Streamlit 启动完成。"""
    time.sleep(delay)
    webbrowser.open(url)


def main():
    base_dir = get_base_dir()
    os.chdir(base_dir)

    if getattr(sys, 'frozen', False):
        sys.path.insert(0, base_dir)

    app_path = os.path.join(base_dir, 'app.py')

    port = 8501
    url = f"http://localhost:{port}"

    print("=" * 50)
    print("  ReviewAgent 正在启动...")
    print(f"  访问地址: {url}")
    print("  按 Ctrl+C 退出")
    print("=" * 50)

    threading.Thread(target=open_browser_delayed, args=(url,), daemon=True).start()

    if getattr(sys, 'frozen', False):
        from streamlit.web import cli as stcli
        sys.argv = [
            'streamlit', 'run', app_path,
            '--server.port', str(port),
            '--server.headless', 'true',
            '--browser.gatherUsageStats', 'false',
        ]
        stcli.main()
    else:
        # 源码模式：用 subprocess 启动
        python_exe = sys.executable
        proc = subprocess.Popen(
            [
                python_exe, '-m', 'streamlit', 'run', 'app.py',
                '--server.port', str(port),
                '--server.headless', 'true',
                '--browser.gatherUsageStats', 'false',
            ],
            cwd=base_dir,
        )
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()


if __name__ == '__main__':
    main()
