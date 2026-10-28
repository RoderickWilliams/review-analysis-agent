# -*- coding: utf-8 -*-
"""全局配置（ReviewAgent，仅官方 API 模式）
=================================================

LLM 统一走 OpenAI 兼容的 Chat Completions API（官方 SDK）。
本包不包含任何网页版登录、access_token 抓取、PoW 求解或 Cloudflare 绕过代码。

环境变量（可写在 `<HOME>/.env` 或仓库根 `.env`）::

    REVIEWAGENT_API_KEYS  逗号分隔的 API Key 列表（兼容 LLM_API_KEYS / OPENAI_API_KEY / DEEPSEEK_API_KEY）
    REVIEWAGENT_MODEL     模型名，默认 gpt-4o
    REVIEWAGENT_BASE_URL  OpenAI 兼容网关地址，默认官方
    REVIEWAGENT_HOME      数据根目录，默认仓库根
    REVIEWAGENT_DB_PATH   SQLite 路径，默认 <DATA_DIR>/reviewagent.db
    REVIEWAGENT_ENABLE_SCRAPING  设为 1 才启用实验性浏览器采集（默认关闭）
"""
from __future__ import annotations

import itertools
import json
import threading
import os
from pathlib import Path
from typing import List, Optional

# ── 路径 ────────────────────────────────────────────────────────
PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
PROJECT_ROOT = str(REPO_ROOT)


def _load_dotenv(path: Path) -> None:
    """零依赖 .env 解析：只在环境变量缺省时填充。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


for _candidate in (REPO_ROOT / ".env", Path.cwd() / ".env"):
    if _candidate.is_file():
        _load_dotenv(_candidate)

HOME_DIR = Path(os.environ.get("REVIEWAGENT_HOME", str(REPO_ROOT))).expanduser()
DATA_DIR = Path(os.environ.get("REVIEWAGENT_DATA_DIR", str(HOME_DIR / "data"))).expanduser()
OUTPUT_DIR = Path(os.environ.get("REVIEWAGENT_OUTPUT_DIR", str(HOME_DIR / "output"))).expanduser()
CACHE_DIR = Path(os.environ.get("REVIEWAGENT_CACHE_DIR", str(HOME_DIR / ".cache"))).expanduser()
REPORTS_DIR = DATA_DIR / "reports"
DB_PATH = Path(os.environ.get("REVIEWAGENT_DB_PATH", str(DATA_DIR / "reviewagent.db"))).expanduser()


def ensure_dirs() -> None:
    for d in (DATA_DIR, OUTPUT_DIR, CACHE_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# 伦理准则 — 严禁使用 AI 生成虚假评论进行虚假分析
# ═══════════════════════════════════════════════════════════════
ETHICS_POLICY = """
严禁使用AI生成虚假评论进行虚假分析！
- 所有评论必须来自真实平台抓取
- 每条评论必须可溯源到原始平台和链接
- 爬取失败时明确告知用户，不得用虚假数据替代
- 演示数据必须标注为DEMO，不得冒充真实评论
"""

ANTI_FAKE_REVIEW = True

REVIEW_TRACEABILITY_FIELDS = [
    "source_platform",    # 来源平台
    "source_url",         # 商品页面URL
    "product_id",         # 平台商品ID
    "reviewer_name",      # 评论者昵称
    "review_date",        # 评论日期
    "sku",                # 购买的SKU
]


def validate_review_traceability(review: dict) -> tuple:
    """验证评论是否包含溯源信息，返回 (是否通过, 缺失字段列表)。"""
    missing = [f for f in REVIEW_TRACEABILITY_FIELDS if not review.get(f)]
    return len(missing) == 0, missing


def check_ethics_compliance(reviews: list) -> dict:
    """检查评论列表是否符合伦理准则。"""
    issues = []
    for i, r in enumerate(reviews):
        valid, missing = validate_review_traceability(r)
        if not valid:
            issues.append(f"评论 #{i+1} 缺少溯源字段: {', '.join(missing)}")
        if r.get("is_demo"):
            issues.append(f"评论 #{i+1} 标记为演示数据，不得作为真实分析结果")
    return {
        "compliant": len(issues) == 0,
        "issues": issues,
        "total_reviews": len(reviews),
        "reviewed_count": len(reviews) - len([r for r in reviews if r.get("is_demo")]),
    }


# ═══════════════════════════════════════════════════════════════
# 模型与 Key 配置（单一 API 模式）
# ═══════════════════════════════════════════════════════════════

LLM_MODE = "api"

_deepseek_default = bool(os.environ.get("DEEPSEEK_API_KEY")) and not any(os.environ.get(name) for name in ("REVIEWAGENT_API_KEYS", "LLM_API_KEYS", "OPENAI_API_KEY"))
MODEL = (os.environ.get("REVIEWAGENT_MODEL") or os.environ.get("LLM_MODEL")
         or os.environ.get("OPENAI_MODEL") or os.environ.get("DEEPSEEK_MODEL")
         or ("deepseek-flash" if _deepseek_default else "gpt-4o")).strip()
_base_url = (os.environ.get("REVIEWAGENT_BASE_URL") or os.environ.get("LLM_BASE_URL")
              or os.environ.get("OPENAI_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL")
              or ("https://api.deepseek.com" if os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("OPENAI_API_KEY") else "")).strip()
BASE_URL = _base_url or None

LLM_TIMEOUT = float(os.environ.get("REVIEWAGENT_LLM_TIMEOUT", "120"))
LLM_MAX_RETRIES = int(os.environ.get("REVIEWAGENT_LLM_MAX_RETRIES", "3"))


def _parse_api_keys() -> List[str]:
    raw = next((os.environ[name] for name in ("REVIEWAGENT_API_KEYS", "LLM_API_KEYS", "OPENAI_API_KEY", "DEEPSEEK_API_KEY") if os.environ.get(name)), "")
    try:
        values = json.loads(raw) if raw.lstrip().startswith("[") else raw.split(",")
    except ValueError:
        return []
    if not isinstance(values, list):
        return []
    keys: List[str] = []
    for key in values:
        if not isinstance(key, str):
            continue
        key = key.strip().strip('"').strip("'")
        if len(key) >= 16 and not any(ch.isspace() for ch in key) and key not in keys:
            keys.append(key)
    return keys


API_KEYS: List[str] = _parse_api_keys()
API_KEY: Optional[str] = API_KEYS[0] if API_KEYS else None
_key_cycle = itertools.cycle(API_KEYS) if API_KEYS else None
_failed_keys: set = set()
_key_lock = threading.Lock()


def get_next_api_key() -> Optional[str]:
    """获取下一个可用 API Key（轮换 + 跳过失败 Key）。"""
    with _key_lock:
        if not _key_cycle or not API_KEYS:
            return None
        for _ in range(len(API_KEYS)):
            key = next(_key_cycle)
            if key not in _failed_keys:
                return key
        return None


def mark_key_failed(key: str) -> None:
    """标记某个 Key 为失败（配额用尽或无效）。"""
    with _key_lock:
        _failed_keys.add(key)


def is_api_key_configured() -> bool:
    return bool(API_KEYS)


def is_llm_configured() -> bool:
    """是否具备调用真实 LLM 的条件。"""
    return is_api_key_configured()


# ── 已移除的网页版通道：保留只读兼容符号，避免旧代码 import 直接崩溃 ──
OPENAI_EMAIL = ""
OPENAI_PASSWORD = ""
OPENAI_ACCESS_TOKEN = ""
DEEPSEEK_USER_TOKEN = ""
REVERSE_PROXY_URL = ""
WEB_PROXY_SERVER_URL = ""
AUTH_SERVICE_URL = ""


def is_web_mode() -> bool:
    """网页版调用通道已移除，恒为 False。"""
    return False


def is_web_configured() -> bool:
    return False


def get_web_client():
    raise RuntimeError(
        "网页版调用通道已移除：ReviewAgent 仅支持官方 API。"
        "请设置 REVIEWAGENT_API_KEYS（或 OPENAI_API_KEY）后重试。"
    )


def has_deepseek_web_fallback() -> bool:
    return False


def get_deepseek_web_client():
    raise RuntimeError("网页版调用通道已移除，ReviewAgent 仅支持官方 API。")


def should_fallback_to_web(api_error: str = "") -> bool:
    return False


def get_llm_client(**kwargs):
    """创建 OpenAI 兼容客户端（延迟导入，避免循环依赖）。"""
    from reviewagent.llm import create_llm_client

    return create_llm_client(**kwargs)


# ═══════════════════════════════════════════════════════════════
# 采集 / 分析参数
# ═══════════════════════════════════════════════════════════════

# 采集是实验功能：涉及第三方站点与浏览器自动化，默认关闭。
# 打开方式：REVIEWAGENT_ENABLE_SCRAPING=1；关闭时 --url 会明确报错而不是静默回退。
SCRAPING_ENABLED = os.environ.get("REVIEWAGENT_ENABLE_SCRAPING", "").strip().lower() in ("1", "true", "yes", "on")
BROWSER_PREFERENCE = os.environ.get("REVIEWAGENT_BROWSER", "auto").strip().lower()
BROWSER_NETWORK = os.environ.get("REVIEWAGENT_BROWSER_NETWORK", "direct").strip().lower()

# 抓取后端：legacy 用现有平台爬虫；scrapling 用可选后端（见 scrapers/scrapling_backend.py）。
# 选择器配置是 JSON 文件，站点改版时改配置不改代码。
SCRAPER_BACKEND = (os.environ.get("REVIEWAGENT_SCRAPER_BACKEND") or "legacy").strip().lower()
SCRAPLING_SELECTORS = (os.environ.get("REVIEWAGENT_SCRAPLING_SELECTORS") or "").strip()
SCRAPLING_FETCH_MODE = (os.environ.get("REVIEWAGENT_SCRAPLING_MODE") or "auto").strip().lower()
SCRAPLING_TIMEOUT = float(os.environ.get("REVIEWAGENT_SCRAPLING_TIMEOUT", "30"))

# ── 小红书采集（复用 xhs-batch-reader 技能的只读 CLI）──────────
# 搜索与博主主页需要扫码登录一次；单篇笔记链接需要 xsec_token。
XHS_PYTHON = (os.environ.get("REVIEWAGENT_XHS_PYTHON") or "").strip()
XHS_SCRIPT = (os.environ.get("REVIEWAGENT_XHS_SCRIPT") or "").strip()
XHS_RUN_DIR = (os.environ.get("REVIEWAGENT_XHS_RUN_DIR") or "").strip()
XHS_TIMEOUT = float(os.environ.get("REVIEWAGENT_XHS_TIMEOUT", "900"))
XHS_LIMIT = int(os.environ.get("REVIEWAGENT_XHS_LIMIT", "20"))
XHS_WITH_OCR = os.environ.get("REVIEWAGENT_XHS_OCR", "1").strip().lower() not in ("0", "false", "no", "off")
XHS_MAX_IMAGES = int(os.environ.get("REVIEWAGENT_XHS_MAX_IMAGES", "12"))

CRAWL_DELAY = float(os.environ.get("CRAWL_DELAY", "2.0"))
USER_AGENT = os.environ.get(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "15"))

SIMILARITY_HIGH = 0.85
SIMILARITY_MEDIUM = 0.70

TEMPERATURE_CLASSIFY = 0.2
TEMPERATURE_REASONING = 0.3
TEMPERATURE_REPORT = 0.5
MAX_REVIEWS_FOR_REPORT = 50


def print_config_status() -> None:
    """打印配置状态（不输出 Key 明文）。"""
    print("=" * 60)
    print("  ReviewAgent 配置状态")
    print("=" * 60)
    print(f"  模式:        API（官方 OpenAI 兼容接口）")
    print(f"  模型:        {MODEL}")
    print(f"  接口地址:    {BASE_URL or 'https://api.openai.com/v1（默认）'}")
    print(f"  API Key:     {'已配置 ' + str(len(API_KEYS)) + ' 个' if API_KEYS else '未配置'}")
    print(f"  数据目录:    {DATA_DIR}")
    print(f"  输出目录:    {OUTPUT_DIR}")
    print(f"  数据库:      {DB_PATH}")
    print(f"  采集:        {'开启' if SCRAPING_ENABLED else '关闭（实验功能，默认关闭）'} / 后端 {SCRAPER_BACKEND}")
    print("=" * 60)
