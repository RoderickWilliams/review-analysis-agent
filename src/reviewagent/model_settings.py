"""Explicit provider discovery: never send an ambiguous key to guessed hosts."""
import itertools
import secrets
import threading
import time
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from reviewagent import config

PROVIDERS = {
    "deepseek": ("DeepSeek", "https://api.deepseek.com"),
    "openai": ("OpenAI", "https://api.openai.com/v1"),
    "gemini": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
    "anthropic": ("Anthropic Claude", "https://api.anthropic.com/v1"),
}
_tickets = {}
_lock = threading.Lock()
_selected_base = None


def guess_provider(key):
    if key.startswith(("sk-proj-", "sk-svcacct-")):
        return "openai"
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("AIza"):
        return "gemini"
    return None


def detect(key, provider="auto", base_url=""):
    if not isinstance(key, str) or not 16 <= len(key.strip()) <= 1024 or any(c.isspace() for c in key.strip()):
        raise ValueError("请填写有效的 API Key")
    key = key.strip()
    provider = guess_provider(key) if provider == "auto" else provider
    if not provider:
        return {"needs_provider": True, "message": "此 Key 前缀被多个供应商共用，请选择供应商后验证；尚未发送 Key。"}
    if provider == "custom":
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("自定义接口必须为不含账号、查询参数的 HTTPS API 地址")
        base = base_url.rstrip("/")
        name = "自定义兼容接口"
    elif provider in PROVIDERS:
        name, base = PROVIDERS[provider]
    else:
        raise ValueError("请选择支持的供应商或自定义兼容接口")
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"} if provider == "anthropic" else {"Authorization": "Bearer " + key}
    try:
        response = httpx.get(base + "/models", headers=headers, timeout=15, follow_redirects=False)
        if response.status_code != 200:
            raise ValueError("供应商验证未通过，请核对 Key、供应商或接口权限")
        payload = response.json()
        models = sorted({item["id"] for item in payload.get("data", []) if isinstance(item, dict) and isinstance(item.get("id"), str)
                         and not any(part in item["id"].lower() for part in ("embedding", "audio", "realtime", "whisper", "dall-e", "moderation", "tts"))})
    except (httpx.HTTPError, TypeError, KeyError):
        raise ValueError("无法连接所选供应商，请检查网络及 API 地址") from None
    if not models:
        raise ValueError("供应商没有返回可选文本模型，请确认模型访问权限")
    ticket = secrets.token_urlsafe(24)
    with _lock:
        for old in list(_tickets):
            if _tickets[old]["expires"] < time.monotonic():
                del _tickets[old]
        if len(_tickets) >= 8:
            del _tickets[next(iter(_tickets))]
        _tickets[ticket] = {"key": key, "provider": provider, "base": base, "models": models, "expires": time.monotonic() + 300}
    return {"ticket": ticket, "provider": provider, "provider_name": name, "base_url": base, "models": models,
            "model": "deepseek-flash" if "deepseek-flash" in models else models[0], "needs_prices": provider != "deepseek"}


def apply(ticket, model, input_price=None, output_price=None):
    global _selected_base
    from reviewagent.analysis_tasks import _active, _lock as task_lock
    from reviewagent.model_budget import PRICES, OFFICIAL_DEEPSEEK_PRICES
    with task_lock, _lock:
        if _active:
            raise ValueError("请等待或取消运行中的任务，再切换模型")
        selected = _tickets.get(ticket)
        if not selected or selected["expires"] < time.monotonic() or model not in selected["models"]:
            raise ValueError("模型验证已过期或模型不可用，请重新验证")
        if selected["provider"] == "deepseek" and model in OFFICIAL_DEEPSEEK_PRICES:
            PRICES[model] = OFFICIAL_DEEPSEEK_PRICES[model]
        else:
            if input_price is None or output_price is None or input_price <= 0 or output_price <= 0:
                raise ValueError("此模型没有已确认人民币价格，请填写每百万 token 输入、输出单价后启用费用保护")
            PRICES[model] = (Decimal(str(input_price)), Decimal(str(output_price)))
        config.MODEL, config.BASE_URL = model, selected["base"]
        with config._key_lock:
            config.API_KEYS = [selected["key"]]
            config.API_KEY = selected["key"]
            config._key_cycle = itertools.cycle(config.API_KEYS)
            config._failed_keys.clear()
        _selected_base = selected["base"]
        del _tickets[ticket]
    return {"model": model, "provider": selected["provider"], "base_url": selected["base"], "configured": True}


def permitted_base(base):
    return base == _selected_base or base.rstrip("/") in {entry[1] for entry in PROVIDERS.values()}
