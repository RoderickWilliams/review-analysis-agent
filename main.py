# -*- coding: utf-8 -*-
"""兼容旧启动方式：python main.py [--web|--url ...]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from reviewagent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
