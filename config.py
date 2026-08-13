# -*- coding: utf-8 -*-
"""
全局配置文件（支持 .env 多 Key 轮换 + Web 模式）
==================================================

两种 LLM 调用模式:
  1. api 模式: 使用 OpenAI API Key 调用（传统方式）
  2. web 模式: 通过网页版 access_token 调用（无需 API Key）

在 .env 文件中设置 LLM_MODE=web 即可切换到 web 模式
"""

# ═══════════════════════════════════════════════════════════════
# 伦理准则 — 严禁使用AI生成虚假评论进行虚假分析
# ═══════════════════════════════════════════════════════════════
ETHICS_POLICY = """
严禁使用AI生成虚假评论进行虚假分析！
- 所有评论必须来自真实平台抓取
- 每条评论必须可溯源到原始平台和链接
- 爬取失败时明确告知用户，不得用虚假数据替代
- 演示数据必须标注为DEMO，不得冒充真实评论
"""

# 反虚假评论模式（强制开启，不可关闭）
ANTI_FAKE_REVIEW = True

# 评论溯源必填字段
REVIEW_TRACEABILITY_FIELDS = [
    "source_platform",    # 来源平台
    "source_url",         # 商品页面URL
    "product_id",         # 平台商品ID
    "reviewer_name",      # 评论者昵称
    "review_date",        # 评论日期
    "sku",                # 购买的SKU
]


def validate_review_traceability(review: dict) -> tuple:
    """
    验证评论是否包含溯源信息。

    :param review: 评论字典
    :return: (是否通过, 缺失字段列表)
    """
    missing = []
    for field in REVIEW_TRACEABILITY_FIELDS:
        if not review.get(field):
            missing.append(field)
    return len(missing) == 0, missing


def check_ethics_compliance(reviews: list) -> dict:
    """
    检查评论列表是否符合伦理准则。

    :param reviews: 评论列表
    :return: 检查结果字典
    """
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



import os
import re
import itertools
from typing import Optional, List

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_env_path):
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip()
                    if key not in os.environ:
                        os.environ[key] = value

# ═══════════════════════════════════════════════════════════════
# LLM 模式配置
# ═══════════════════════════════════════════════════════════════

# LLM 调用模式: "api"（使用 API Key）或 "web"（使用网页版 access_token）
LLM_MODE = os.environ.get("LLM_MODE", "api").lower().strip()

# ═══════════════════════════════════════════════════════════════
# API Key 轮换管理（api 模式使用）
# ═══════════════════════════════════════════════════════════════

_raw_keys = os.environ.get("LLM_API_KEYS", os.environ.get("LLM_API_KEY", ""))

def _is_valid_api_key_format(key: str) -> bool:
    """检查 API Key 格式是否可能是真实的（非占位符）

    支持多种 LLM 提供商的 Key 格式:
    - OpenAI: sk- 开头，48+ 字符
    - DeepSeek: sk- 开头，32-40 字符（十六进制）
    - 其他: sk- 开头，30+ 字符
    """
    key = key.strip()
    if not key or key == "your-api-key-here":
        return False
    # 检查是否是中文占位符文本
    if any('\u4e00' <= c <= '\u9fff' for c in key):
        return False
    if not key.startswith("sk-"):
        return False
    if len(key) < 30:  # 降低最小长度要求以支持 DeepSeek
        return False

    test_part = key[3:]  # 去掉 sk- 前缀

    # 检查1: 是否包含明显的占位符子串
    placeholder_patterns = [
        "abcdef", "1234567890", "abcd1234",
        "ijklmnop", "qrstuvwx",
        "testtest", "example", "placeholder", "fake", "dummy",
        "your_api_key", "your-api-key",
    ]
    lower_part = test_part.lower()
    for pattern in placeholder_patterns:
        if pattern in lower_part:
            return False

    # 检查2: 是否有4字符段重复3次以上（排除纯十六进制Key的合法重复）
    # DeepSeek Key 是纯十六进制，某些4字符段可能重复，所以放宽检查
    is_hex = bool(re.match(r'^[0-9a-f]+$', lower_part))
    if not is_hex:
        for i in range(len(test_part) - 3):
            segment = test_part[i:i+4]
            if test_part.count(segment) >= 3:
                return False

    # 检查3: 字符多样性（降低要求以支持 DeepSeek 纯十六进制 Key）
    unique_chars = len(set(test_part.lower()))
    if is_hex:
        if unique_chars < 5:  # 十六进制 Key 至少有5种不同字符
            return False
    else:
        if unique_chars < 10:
            return False

    return True

API_KEYS: List[str] = [k.strip() for k in _raw_keys.split(",") if _is_valid_api_key_format(k.strip())]

_key_cycle = itertools.cycle(API_KEYS) if API_KEYS else None
_failed_keys: set = set()

# 模型配置
MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
_base_url = os.environ.get("LLM_BASE_URL", "")
BASE_URL = _base_url if _base_url else None

# ═══════════════════════════════════════════════════════════════
# Web 模式配置（web 模式使用）
# ═══════════════════════════════════════════════════════════════

# OpenAI 网页版账号（用于自动获取 access_token）
OPENAI_EMAIL = os.environ.get("OPENAI_EMAIL", "")
OPENAI_PASSWORD = os.environ.get("OPENAI_PASSWORD", "")

# 手动获取的 access_token（优先使用）
OPENAI_ACCESS_TOKEN = os.environ.get("OPENAI_ACCESS_TOKEN", "")

# 反向代理 URL（用于绕过 Cloudflare 验证）
REVERSE_PROXY_URL = os.environ.get(
    "REVERSE_PROXY_URL",
    "https://ai.fakeopen.com/api/conversation"
)

# 独立代理服务 URL（可选，指向 web_proxy_server.py）
WEB_PROXY_SERVER_URL = os.environ.get("WEB_PROXY_SERVER_URL", "")

# 认证服务 URL（用于获取 access_token）
AUTH_SERVICE_URL = os.environ.get(
    "AUTH_SERVICE_URL",
    "https://chatgpt-auth.vercel.app/api"
)

# ═══════════════════════════════════════════════════════════════
# 路径配置
# ═══════════════════════════════════════════════════════════════

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 采集配置
CRAWL_DELAY = float(os.environ.get("CRAWL_DELAY", "2.0"))
USER_AGENT = os.environ.get("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "15"))

# 相似度阈值
SIMILARITY_HIGH = 0.85
SIMILARITY_MEDIUM = 0.70

# LLM 温度
TEMPERATURE_CLASSIFY = 0.2
TEMPERATURE_REASONING = 0.3
TEMPERATURE_REPORT = 0.5
MAX_REVIEWS_FOR_REPORT = 50


# ═══════════════════════════════════════════════════════════════
# API Key 轮换函数
# ═══════════════════════════════════════════════════════════════

def get_next_api_key() -> Optional[str]:
    """获取下一个可用的 API Key（轮换 + 跳过失败 Key）"""
    global _key_cycle
    if not _key_cycle or not API_KEYS:
        return None
    for _ in range(len(API_KEYS)):
        key = next(_key_cycle)
        if key not in _failed_keys:
            return key
    _failed_keys.clear()
    return next(_key_cycle)


def mark_key_failed(key: str):
    """标记某个 Key 为失败（配额用尽或无效）"""
    _failed_keys.add(key)
    remaining = len(API_KEYS) - len(_failed_keys)
    print(f"  [Key轮换] 标记失败，剩余可用 Key: {remaining}/{len(API_KEYS)}")


def is_api_key_configured() -> bool:
    """检查是否有可用的 API Key"""
    return len(API_KEYS) > 0 and any(k not in _failed_keys for k in API_KEYS)


# ═══════════════════════════════════════════════════════════════
# Web 模式函数
# ═══════════════════════════════════════════════════════════════

def is_web_mode() -> bool:
    """是否使用 web 模式（通过网页版 access_token 调用）"""
    return LLM_MODE == "web"


def is_web_configured() -> bool:
    """检查 web 模式是否已配置（有 access_token 或 email/password 或代理服务）"""
    return bool(
        OPENAI_ACCESS_TOKEN
        or (OPENAI_EMAIL and OPENAI_PASSWORD)
        or WEB_PROXY_SERVER_URL
    )


def get_web_client():
    """
    创建 WebLLMClient 实例（web 模式使用）

    返回:
        WebLLMClient 实例
    """
    from web_llm_client import WebLLMClient

    return WebLLMClient(
        access_token=OPENAI_ACCESS_TOKEN or None,
        email=OPENAI_EMAIL or None,
        password=OPENAI_PASSWORD or None,
        reverse_proxy=REVERSE_PROXY_URL,
        proxy_server_url=WEB_PROXY_SERVER_URL or None,
    )


# ═══════════════════════════════════════════════════════════════
# 统一 LLM 客户端获取
# ═══════════════════════════════════════════════════════════════

def is_llm_configured() -> bool:
    """检查 LLM 是否已配置（api 或 web 模式任一可用即可）"""
    if is_web_mode():
        return is_web_configured()
    return is_api_key_configured()


# DeepSeek 网页端备用 Token
DEEPSEEK_USER_TOKEN = os.environ.get("DEEPSEEK_USER_TOKEN", "")


def has_deepseek_web_fallback() -> bool:
    """检查是否有 DeepSeek 网页端备用调用可用"""
    return bool(DEEPSEEK_USER_TOKEN)


def get_deepseek_web_client():
    """
    创建 DeepSeekWebClient 实例（网页端备用模式）

    返回:
        DeepSeekWebClient 实例
    """
    from deepseek_web_client import DeepSeekWebClient
    return DeepSeekWebClient(user_token=DEEPSEEK_USER_TOKEN)


def should_fallback_to_web(api_error: str = "") -> bool:
    """
    判断是否应该降级到网页端调用

    触发条件:
    1. API Key 额度用尽（错误信息包含 quota/billing/402）
    2. API Key 认证失败且没有其他可用 Key
    3. 有 DEEPSEEK_USER_TOKEN 可用
    """
    if not has_deepseek_web_fallback():
        return False

    error_lower = api_error.lower()
    quota_keywords = ["quota", "billing", "402", "insufficient", "余额不足", "额度"]
    if any(kw in error_lower for kw in quota_keywords):
        return True

    # 所有 API Key 都已失败
    if _failed_keys and len(_failed_keys) >= len(API_KEYS):
        return True

    return False


def get_llm_client():
    """
    根据配置自动创建 LLM 客户端

    返回:
        api 模式: OpenAI 客户端实例
        web 模式: WebLLMClient 实例
    """
    if is_web_mode():
        return get_web_client()
    else:
        from openai import OpenAI
        return OpenAI(api_key=get_next_api_key(), base_url=BASE_URL)


# ═══════════════════════════════════════════════════════════════
# 配置状态打印
# ═══════════════════════════════════════════════════════════════

def print_config_status():
    """打印配置状态"""
    print("配置状态:")
    print(f"  LLM 模式:   {LLM_MODE}" + (" (网页版 access_token)" if is_web_mode() else " (API Key)"))
    print(f"  模型:       {MODEL}")

    if is_web_mode():
        if OPENAI_ACCESS_TOKEN:
            print(f"  Token:      已配置 (OPENAI_ACCESS_TOKEN)")
        elif OPENAI_EMAIL:
            print(f"  账号:       {OPENAI_EMAIL}")
        elif WEB_PROXY_SERVER_URL:
            print(f"  代理服务:   {WEB_PROXY_SERVER_URL}")
        else:
            print(f"  Token:      未配置")

        print(f"  反向代理:   {REVERSE_PROXY_URL}")

        if not is_web_configured():
            print("\n  提示: Web 模式未配置！请设置以下之一:")
            print("    OPENAI_ACCESS_TOKEN  (手动获取的 token)")
            print("    OPENAI_EMAIL + OPENAI_PASSWORD  (自动获取 token)")
            print("    WEB_PROXY_SERVER_URL  (代理服务地址)")
    else:
        valid_count = len(API_KEYS)
        print(f"  API Keys:   {valid_count} 个有效 (可用: {valid_count - len(_failed_keys)})")
        if _raw_keys and valid_count == 0:
            raw_count = len([k for k in _raw_keys.split(",") if k.strip()])
            print(f"  警告: .env 中有 {raw_count} 个 Key，但全部格式无效（疑似占位符）")
        print(f"  Base URL:   {BASE_URL or '默认（OpenAI官方）'}")

        if not is_api_key_configured():
            print("\n  提示: 请在 .env 文件中填入真实的 API Key")
            print("  DeepSeek 注册: https://platform.deepseek.com/")
            print("  OpenAI 注册: https://platform.openai.com/api-keys")
            print("  格式: sk- 开头，长度约 50+ 字符的随机字符串")

    print(f"  数据目录:   {DATA_DIR}")
    print(f"  输出目录:   {OUTPUT_DIR}")


if __name__ == "__main__":
    print_config_status()
