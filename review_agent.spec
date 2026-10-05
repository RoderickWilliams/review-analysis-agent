# -*- mode: python ; coding: utf-8 -*-
"""
ReviewAgent PyInstaller Spec
=============================
将 Streamlit 应用 + 所有依赖打包为独立可执行程序。
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

PROJECT_ROOT = r'E:\review-analysis-agent'

# ---- 收集关键包的全部数据文件和子模块 ----
datas = []
binaries = []
hiddenimports = []

# Streamlit 及其依赖
for pkg in [
    'streamlit', 'altair', 'pydeck', 'watchdog', 'tornado',
    'sklearn', 'scipy', 'pandas', 'numpy', 'pyarrow',
    'DrissionPage', 'patchright', 'playwright',
    'openai', 'requests', 'bs4', 'selenium',
    'jieba', 'PIL', 'pytesseract',
    'docx', 'fitz', 'openpyxl',
    'dotenv', 'tenacity', 'psutil', 'mss',
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# ---- 项目源文件 ----
project_files = [
    'app.py', 'launcher.py', 'config.py', 'data_collector.py',
    'data_preprocessor.py', 'deepseek_web_client.py', 'desktop_app.py',
    'fallback_client.py', 'history_manager.py', 'login_subprocess.py',
    'main.py', 'ocr_engine.py', 'red_flags.py', 'report_generator.py',
    'screenshot_analyzer.py', 'sentiment_agent_core.py', 'setup.py',
    'trust_report.py', 'web_llm_client.py', 'web_proxy_server.py',
    'auto_login.py', '_ui_styles.py',
    '.env', '.env.example', 'trust_score_guide.html',
    'ETHICS.md', 'LICENSE', 'README.md', 'requirements.txt',
]
for f in project_files:
    src = os.path.join(PROJECT_ROOT, f)
    if os.path.isfile(src):
        datas.append((src, '.'))

# ---- 项目子目录 ----
subdirs = ['scrapers', 'utils', 'chains', 'data', 'dsk', '.streamlit', 'cookies']
for sd in subdirs:
    src = os.path.join(PROJECT_ROOT, sd)
    if os.path.isdir(src):
        datas.append((src, sd))

# ---- Tesseract-OCR ----
tesseract_dir = os.path.join(PROJECT_ROOT, 'tools', 'Tesseract-OCR')
if os.path.isdir(tesseract_dir):
    datas.append((tesseract_dir, os.path.join('tools', 'Tesseract-OCR')))

# ---- Playwright 浏览器数据 ----
pw_data = os.path.join(PROJECT_ROOT, 'playwright-data')
if os.path.isdir(pw_data):
    datas.append((pw_data, 'playwright-data'))

# ---- 额外 hidden imports ----
hiddenimports += [
    'streamlit.web.cli',
    'streamlit.runtime.scriptrunner',
    'streamlit.runtime.state',
    'sklearn.utils._typedefs',
    'sklearn.tree._utils',
    'pyarrow.lib',
    'PIL._tkinter_finder',
    'altair.vegalite.v5',
    'watchdog.observers',
    'watchdog.observers.polling',
    'jinja2.ext',
    'csv',
    'xml',
    'xml.etree',
    'xml.etree.ElementTree',
    'http.cookiejar',
    'urllib.parse',
]

# ---- 排除不需要的包 ----
excludes = [
    'matplotlib', 'notebook', 'IPython', 'jupyter',
    'pytest', 'unittest', 'sphinx',
    'paddlepaddle', 'paddleocr',
    'flask',
]

a = Analysis(
    ['launcher.py'],
    pathex=[PROJECT_ROOT, os.path.join(PROJECT_ROOT, 'venv', 'Lib', 'site-packages')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ReviewAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='ReviewAgent',
)
