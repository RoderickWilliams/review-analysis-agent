# -*- coding: utf-8 -*-
"""兼容旧启动方式：streamlit run app.py（实际界面在 reviewagent.app）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import reviewagent.app  # noqa: F401,E402  (导入即执行 Streamlit 页面)
