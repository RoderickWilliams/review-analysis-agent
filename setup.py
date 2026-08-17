# -*- coding: utf-8 -*-
"""
全平台用户反馈智能分析 Agent - 一键环境安装脚本
=================================================
自动完成:
  1. 检查 Python 版本
  2. 安装 pip 依赖 (requirements.txt)
  3. 安装 Playwright Chromium 浏览器
  4. 安装/定位 Tesseract OCR 引擎（含中文语言包）
  5. 验证所有模块

用法:
  python setup.py          # 完整安装
  python setup.py --check  # 仅检查环境，不安装
"""
import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
VENV_PYTHON = sys.executable
VENV_PIP = [sys.executable, "-m", "pip"]

# Tesseract 封装目录
TOOLS_DIR = PROJECT_ROOT / "tools" / "Tesseract-OCR"

# Tesseract 下载信息
TESSERACT_VERSION = "5.5.3.20260724"
TESSERACT_DOWNLOAD = (
    "https://github.com/tesseract-ocr/tesseract/releases/download/"
    f"5.5.3/tesseract-ocr-w64-setup-{TESSERACT_VERSION}.exe"
)
TESSDATA_BASE = "https://github.com/tesseract-ocr/tessdata_fast/raw/main"
TESSERACT_LANGS = ["chi_sim", "chi_tra"]


def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def run(cmd, check=True, **kwargs):
    """运行命令并实时输出。"""
    print(f">>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, check=False, text=True,
                            capture_output=False, **kwargs)
    if check and result.returncode != 0:
        print(f"WARNING: Command exited with code {result.returncode}")
    return result.returncode == 0


def check_python():
    """检查 Python 版本。"""
    banner("Step 1/5: Checking Python version")
    ver = sys.version_info
    print(f"Python {ver.major}.{ver.minor}.{ver.micro} at {sys.executable}")

    if ver.major < 3 or (ver.major == 3 and ver.minor < 10):
        print("ERROR: Python 3.10 or higher is required.")
        return False

    if ver.major == 3 and ver.minor >= 14:
        print("NOTE: Python 3.14+ detected. PaddleOCR is not supported on 3.14,")
        print("      but Tesseract OCR will be used as the local OCR engine.")
    elif ver.major == 3 and ver.minor <= 13:
        print("TIP: PaddleOCR is available. To install:")
        print("     pip install paddlepaddle==3.2.0 paddleocr \\")
        print("       -i https://www.paddlepaddle.org.cn/packages/stable/cpu/")

    return True


def install_requirements():
    """安装 pip 依赖。"""
    banner("Step 2/5: Installing Python dependencies")
    req_file = PROJECT_ROOT / "requirements.txt"
    if not req_file.exists():
        print("ERROR: requirements.txt not found!")
        return False

    # Upgrade pip first
    run(VENV_PIP + ["install", "--upgrade", "pip"], check=False)
    # Install requirements
    return run(VENV_PIP + ["install", "-r", str(req_file)])


def install_playwright():
    """安装 Playwright Chromium。"""
    banner("Step 3/5: Installing Playwright Chromium browser")
    return run([sys.executable, "-m", "playwright", "install", "chromium"])


def find_system_tesseract():
    """在系统中查找 Tesseract。"""
    # 1. 项目封装目录
    if TOOLS_DIR.exists():
        exe = TOOLS_DIR / "tesseract.exe" if sys.platform == "win32" else TOOLS_DIR / "tesseract"
        if exe.exists():
            return str(exe)

    # 2. PATH
    found = shutil.which("tesseract")
    if found:
        return found

    # 3. Windows 标准路径
    if sys.platform == "win32":
        for p in [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]:
            if Path(p).exists():
                return p

    return None


def download_tesseract_windows():
    """在 Windows 上下载并安装 Tesseract 到 tools/ 目录。"""
    import requests

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    installer = TOOLS_DIR.parent / "tesseract-setup.exe"

    print(f"Downloading Tesseract {TESSERACT_VERSION}...")
    try:
        r = requests.get(TESSERACT_DOWNLOAD, stream=True, timeout=120,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(installer, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  Progress: {pct}% ({downloaded//1024//1024}MB/{total//1024//1024}MB)", end="")
        print()
    except Exception as e:
        print(f"Download failed: {e}")
        print("Please install Tesseract manually:")
        print(f"  1. Download: {TESSERACT_DOWNLOAD}")
        print(f"  2. Install to: {TOOLS_DIR}")
        return False

    # Run installer silently
    print("Installing Tesseract (may require admin permission)...")
    try:
        subprocess.run(
            [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
             f"/DIR={TOOLS_DIR}", "/COMPONENTS=main"],
            check=True, timeout=300
        )
    except subprocess.CalledProcessError:
        # Try with elevation
        print("Elevation required, requesting admin permission...")
        import ctypes
        params = (f'/VERYSILENT /SUPPRESSMSGBOXES /NORESTART '
                  f'/DIR="{TOOLS_DIR}" /COMPONENTS=main')
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", str(installer), params, None, 0
        )
        print("Waiting for elevated installation...")
        import time
        for _ in range(60):
            time.sleep(2)
            if (TOOLS_DIR / "tesseract.exe").exists():
                break

    # Clean up installer
    try:
        installer.unlink()
    except Exception:
        pass

    return (TOOLS_DIR / "tesseract.exe").exists()


def download_language_data(tesseract_cmd):
    """下载中文语言包。"""
    import requests

    tessdata = Path(tesseract_cmd).parent / "tessdata"
    tessdata.mkdir(parents=True, exist_ok=True)

    for lang in TESSERACT_LANGS:
        target = tessdata / f"{lang}.traineddata"
        if target.exists():
            print(f"  {lang}: already installed")
            continue

        url = f"{TESSDATA_BASE}/{lang}.traineddata"
        print(f"  Downloading {lang}...")
        try:
            r = requests.get(url, timeout=120, stream=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            with open(target, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
            print(f"  {lang}: installed ({target.stat().st_size // 1024} KB)")
        except Exception as e:
            print(f"  {lang}: download failed - {e}")
            print(f"    Manual download: {url}")


def setup_tesseract():
    """安装/定位 Tesseract OCR。"""
    banner("Step 4/5: Setting up Tesseract OCR engine")

    # Check if already available
    tess_cmd = find_system_tesseract()
    if tess_cmd:
        print(f"Tesseract found: {tess_cmd}")
        result = subprocess.run([tess_cmd, "--version"],
                                capture_output=True, text=True)
        if result.stdout:
            print(result.stdout.strip().split("\n")[0])
        download_language_data(tess_cmd)
        return True

    # Not found - install based on OS
    system = platform.system()
    print(f"Tesseract not found on this {system} system.")

    if system == "Windows":
        success = download_tesseract_windows()
        if success:
            tess_cmd = str(TOOLS_DIR / "tesseract.exe")
            download_language_data(tess_cmd)
            return True
        return False

    elif system == "Darwin":  # macOS
        print("Installing via Homebrew...")
        if run(["brew", "install", "tesseract", "tesseract-lang"]):
            tess_cmd = shutil.which("tesseract")
            return tess_cmd is not None
        return False

    elif system == "Linux":
        print("Installing via apt...")
        if run(["sudo", "apt-get", "update"]):
            if run(["sudo", "apt-get", "install", "-y",
                    "tesseract-ocr", "tesseract-ocr-chi-sim",
                    "tesseract-ocr-chi-tra"]):
                tess_cmd = shutil.which("tesseract")
                return tess_cmd is not None
        return False

    else:
        print(f"Unsupported OS: {system}")
        print("Please install Tesseract manually:")
        print("  https://github.com/tesseract-ocr/tesseract")
        return False


def verify():
    """验证所有模块。"""
    banner("Step 5/5: Verifying installation")

    modules = [
        ("openai", "openai"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("sklearn", "scikit-learn"),
        ("jieba", "jieba"),
        ("requests", "requests"),
        ("bs4", "beautifulsoup4"),
        ("dotenv", "python-dotenv"),
        ("streamlit", "streamlit"),
        ("selenium", "selenium"),
        ("playwright", "playwright"),
        ("PIL", "Pillow"),
        ("pytesseract", "pytesseract"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
    ]

    all_ok = True
    for import_name, display_name in modules:
        try:
            __import__(import_name)
            print(f"  [OK] {display_name}")
        except ImportError:
            print(f"  [FAIL] {display_name}")
            all_ok = False

    # Verify Tesseract
    tess_cmd = find_system_tesseract()
    if tess_cmd:
        try:
            result = subprocess.run([tess_cmd, "--version"],
                                    capture_output=True, text=True)
            ver = result.stdout.strip().split("\n")[0] if result.stdout else "unknown"
            print(f"  [OK] Tesseract: {ver}")

            # Check languages
            result = subprocess.run([tess_cmd, "--list-langs"],
                                    capture_output=True, text=True)
            langs = [l.strip() for l in result.stdout.strip().split("\n")[1:]]
            has_chinese = "chi_sim" in langs
            print(f"  [{'OK' if has_chinese else 'WARN'}] Languages: {', '.join(langs)}")
            if not has_chinese:
                print("        Chinese (chi_sim) not found. Run setup again to download.")
        except Exception as e:
            print(f"  [FAIL] Tesseract: {e}")
            all_ok = False
    else:
        print("  [FAIL] Tesseract not found")
        all_ok = False

    # Verify project modules
    print("\n  Project modules:")
    project_mods = [
        "config", "sentiment_agent_core", "fallback_client",
        "ocr_engine", "screenshot_analyzer", "trust_report",
        "red_flags", "report_generator",
    ]
    sys.path.insert(0, str(PROJECT_ROOT))
    for mod in project_mods:
        try:
            __import__(mod)
            print(f"    [OK] {mod}")
        except Exception as e:
            print(f"    [FAIL] {mod}: {e}")
            all_ok = False

    try:
        __import__("scrapers.multi_platform")
        print(f"    [OK] scrapers.multi_platform")
    except Exception as e:
        print(f"    [FAIL] scrapers.multi_platform: {e}")
        all_ok = False

    banner("RESULT")
    if all_ok:
        print("  All checks passed! Environment is ready.")
        print(f"\n  To start the app:")
        print(f"    {sys.executable} -m streamlit run app.py")
        print(f"\n  Or run CLI demo:")
        print(f"    {sys.executable} main.py --demo")
    else:
        print("  Some checks failed. Please review the errors above.")
        print("  Try running: python setup.py")

    return all_ok


def main():
    print("=" * 60)
    print("  全平台用户反馈智能分析 Agent - 环境安装")
    print("=" * 60)

    check_only = "--check" in sys.argv

    if not check_python():
        sys.exit(1)

    if check_only:
        verify()
        return

    if not install_requirements():
        print("WARNING: Some pip packages failed to install.")

    if not install_playwright():
        print("WARNING: Playwright Chromium installation failed.")
        print("  Manual fix: python -m playwright install chromium")

    if not setup_tesseract():
        print("WARNING: Tesseract setup failed. OCR features may not work.")
        print("  Manual install: https://github.com/tesseract-ocr/tesseract")

    verify()


if __name__ == "__main__":
    main()
