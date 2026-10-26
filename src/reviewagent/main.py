# -*- coding: utf-8 -*-
"""兼容入口：保留 `python main.py --url/--csv/--demo/--web` 的旧用法。

新入口见 `reviewagent --help`（安装后）或 `python -m reviewagent --help`。
"""
from reviewagent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
