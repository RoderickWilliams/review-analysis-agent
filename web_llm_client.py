#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web LLM 客户端 — 无需 API Key 调用 ChatGPT
============================================
移植自 https://github.com/zhuweiyou/chatgpt-api (Node.js)

核心原理:
  1. 通过 OpenAI 网页版账号密码获取 access_token
  2. 使用 access_token + 反向代理调用 ChatGPT 网页版接口
  3. 提供与 openai SDK 兼容的接口 (chat.completions.create)

使用方式:
  方式一: 直接在 Python 代码中使用
      from web_llm_client import WebLLMClient
      client = WebLLMClient(access_token="你的access_token")
      response = client.chat.completions.create(
          model="gpt-4o",
          messages=[{"role": "user", "content": "你好"}]
      )
      print(response.choices[0].message.content)

  方式二: 通过 email/password 自动获取 access_token
      from web_llm_client import get_access_token, WebLLMClient
      token = get_access_token("your@email.com", "your_password")
      client = WebLLMClient(access_token=token)

  方式三: 调用独立部署的 web_proxy_server.py 服务
      client = WebLLMClient(proxy_server_url="http://localhost:3000")
"""

import json
import uuid
import os
import time
import logging
from typing import Optional, List, Dict, Any

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 默认配置（可通过环境变量覆盖）
# ═══════════════════════════════════════════════════════════════

DEFAULT_REVERSE_PROXY = os.environ.get(
    "REVERSE_PROXY_URL",
    "https://ai.fakeopen.com/api/conversation"
)

AUTH_SERVICE_URL = os.environ.get(
    "AUTH_SERVICE_URL",
    "https://chatgpt-auth.vercel.app/api"
)

TOKEN_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".access_token_cache"
)

REQUEST_TIMEOUT = 120


# ═══════════════════════════════════════════════════════════════
# 第一部分：access_token 获取
# ═══════════════════════════════════════════════════════════════

def get_access_token(email: str, password: str, proxy: str = "") -> str:
    """
    通过 OpenAI 账号密码获取 access_token

    参数:
        email:    OpenAI 账号邮箱（不支持谷歌/微软授权登录）
        password: OpenAI 密码
        proxy:    可选代理地址

    返回:
        access_token 字符串

    异常:
        ValueError: 获取失败时抛出
    """
    if not requests:
        raise ImportError("请先安装 requests: pip install requests")

    logger.info(f"正在获取 access_token (email: {email})...")

    response = requests.post(
        AUTH_SERVICE_URL,
        headers={
            "email": email,
            "password": password,
            "proxy": proxy,
        },
        timeout=60,
    )

    data = response.json()

    if not data or not data.get("access_token"):
        msg = data.get("message", "获取 access_token 失败") if data else "获取 access_token 失败"
        raise ValueError(msg)

    token = data["access_token"]
    logger.info("access_token 获取成功")

    _cache_token(token)

    return token


def get_access_token_from_file() -> Optional[str]:
    """从本地缓存文件读取 access_token"""
    if os.path.exists(TOKEN_CACHE_PATH):
        try:
            with open(TOKEN_CACHE_PATH, "r") as f:
                token = f.read().strip()
                if token:
                    logger.info("从本地缓存加载 access_token")
                    return token
        except Exception:
            pass
    return None


def _cache_token(token: str):
    """缓存 access_token 到本地文件"""
    try:
        with open(TOKEN_CACHE_PATH, "w") as f:
            f.write(token)
        logger.info("access_token 已缓存到本地")
    except Exception as e:
        logger.warning(f"缓存 access_token 失败: {e}")


def get_cached_or_fetch_token(
    email: Optional[str] = None,
    password: Optional[str] = None,
    proxy: str = ""
) -> str:
    """
    优先使用缓存的 access_token，没有则通过 email/password 获取
    """
    token = get_access_token_from_file()
    if token:
        return token

    if email and password:
        return get_access_token(email, password, proxy)

    env_token = os.environ.get("OPENAI_ACCESS_TOKEN", "")
    if env_token:
        return env_token

    raise ValueError(
        "无法获取 access_token。请通过以下方式之一提供：\n"
        "  1. 在 .env 中设置 OPENAI_EMAIL 和 OPENAI_PASSWORD\n"
        "  2. 在 .env 中设置 OPENAI_ACCESS_TOKEN（手动获取的 token）\n"
        "  3. 调用 get_access_token(email, password) 获取"
    )


# ═══════════════════════════════════════════════════════════════
# 第二部分：SSE 响应解析
# ═══════════════════════════════════════════════════════════════

def parse_sse_response(response) -> Dict[str, Any]:
    """
    解析 SSE (Server-Sent Events) 流式响应

    ChatGPT 网页版接口返回 SSE 格式:
        data: {"v": {"message": {"content": {"parts": ["回答文本"]}, ...}}}
        data: [DONE]
    """
    last_data = None
    conversation_id = None
    message_id = None

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue

        if line.startswith("data: "):
            data_str = line[6:]

            if data_str.strip() == "[DONE]":
                break

            try:
                data = json.loads(data_str)
                last_data = data

                if "conversation_id" in data:
                    conversation_id = data["conversation_id"]
                if "message" in data and "id" in data["message"]:
                    message_id = data["message"]["id"]

            except json.JSONDecodeError:
                continue

    text = ""
    if last_data and "message" in last_data:
        message = last_data["message"]
        if "content" in message and "parts" in message["content"]:
            parts = message["content"]["parts"]
            if parts:
                text = parts[0]

    return {
        "text": text,
        "conversation_id": conversation_id,
        "message_id": message_id,
    }


# ═══════════════════════════════════════════════════════════════
# 第三部分：OpenAI 兼容接口封装
# ═══════════════════════════════════════════════════════════════

class MockMessage:
    """模拟 OpenAI SDK 的 Message 对象"""
    def __init__(self, content: str, role: str = "assistant"):
        self.content = content
        self.role = role


class MockChoice:
    """模拟 OpenAI SDK 的 Choice 对象"""
    def __init__(self, message: MockMessage, index: int = 0):
        self.message = message
        self.index = index
        self.finish_reason = "stop"


class MockCompletionResponse:
    """模拟 OpenAI SDK 的 ChatCompletion 响应对象"""
    def __init__(self, text: str, model: str = "gpt-4o"):
        self.id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        self.object = "chat.completion"
        self.created = int(time.time())
        self.model = model
        self.choices = [MockChoice(MockMessage(text))]


class Completions:
    """模拟 openai.Chat.Completions 接口"""

    def __init__(self, client: "WebLLMClient"):
        self._client = client

    def create(
        self,
        model: str = "gpt-4o",
        messages: List[Dict] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> MockCompletionResponse:
        """
        创建聊天补全 — 与 openai SDK 的 chat.completions.create() 接口兼容
        """
        prompt_parts = []
        for msg in messages or []:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"[系统指令] {content}")
            elif role == "user":
                prompt_parts.append(content)
            elif role == "assistant":
                prompt_parts.append(f"[之前的回答] {content}")

        prompt = "\n\n".join(prompt_parts)

        text = self._client._send_message(prompt, model=model)

        return MockCompletionResponse(text=text, model=model)


class Chat:
    """模拟 openai.Chat 接口"""
    def __init__(self, client: "WebLLMClient"):
        self.completions = Completions(client)


class WebLLMClient:
    """
    Web LLM 客户端 — 无需 API Key 调用 ChatGPT

    使用方式:
        client = WebLLMClient(access_token="your_token")
        # 或
        client = WebLLMClient(email="your@email.com", password="your_password")
        # 或
        client = WebLLMClient(proxy_server_url="http://localhost:3000")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "你好"}],
        )
        print(response.choices[0].message.content)
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        proxy: str = "",
        reverse_proxy: Optional[str] = None,
        proxy_server_url: Optional[str] = None,
    ):
        """
        初始化 Web LLM 客户端

        参数（三选一）:
            access_token:      直接提供 access_token
            email + password:  通过账号密码自动获取 access_token
            proxy_server_url:  调用独立部署的 web_proxy_server.py 服务

        可选参数:
            reverse_proxy: 反向代理 URL
            proxy:         网络代理地址
        """
        if not requests:
            raise ImportError("请先安装 requests: pip install requests")

        self.chat = Chat(self)

        self._proxy_server_url = proxy_server_url
        self._reverse_proxy = reverse_proxy or DEFAULT_REVERSE_PROXY
        self._proxy = proxy
        self._access_token = None
        self._conversation_id = None
        self._parent_message_id = str(uuid.uuid4())

        if proxy_server_url:
            logger.info(f"使用独立代理服务: {proxy_server_url}")
        elif access_token:
            self._access_token = access_token
            logger.info("使用提供的 access_token")
        elif email and password:
            self._access_token = get_access_token(email, password, proxy)
        else:
            try:
                self._access_token = get_cached_or_fetch_token()
            except ValueError as e:
                logger.warning(f"access_token 获取失败: {e}")
                logger.info("将尝试使用独立代理服务模式")
                self._proxy_server_url = "http://localhost:3000"

    def _send_message(
        self,
        prompt: str,
        model: str = "gpt-4o",
        conversation_id: Optional[str] = None,
        parent_message_id: Optional[str] = None,
        timeout: int = REQUEST_TIMEOUT,
    ) -> str:
        """发送消息到 ChatGPT 网页版接口"""
        if self._proxy_server_url:
            return self._send_via_proxy_server(prompt, model, timeout)

        return self._send_via_reverse_proxy(
            prompt, model, conversation_id, parent_message_id, timeout
        )

    def _send_via_reverse_proxy(
        self,
        prompt: str,
        model: str,
        conversation_id: Optional[str],
        parent_message_id: Optional[str],
        timeout: int,
    ) -> str:
        """通过反向代理直接调用 ChatGPT 网页版接口"""

        if not self._access_token:
            raise ValueError("access_token 未配置，无法调用 ChatGPT")

        message_id = str(uuid.uuid4())
        parent_id = parent_message_id or self._parent_message_id

        payload = {
            "action": "next",
            "messages": [
                {
                    "id": message_id,
                    "role": "user",
                    "content": {
                        "content_type": "text",
                        "parts": [prompt],
                    },
                }
            ],
            "model": model,
            "parent_message_id": parent_id,
            "timezone": "Asia/Shanghai",
        }

        if conversation_id or self._conversation_id:
            payload["conversation_id"] = conversation_id or self._conversation_id

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/event-stream",
        }

        proxies = None
        if self._proxy:
            proxies = {"http": self._proxy, "https": self._proxy}

        logger.info(f"调用 ChatGPT 网页版 (model={model}, prompt长度={len(prompt)})")

        try:
            response = requests.post(
                self._reverse_proxy,
                json=payload,
                headers=headers,
                proxies=proxies,
                timeout=timeout,
                stream=True,
            )

            if response.status_code != 200:
                error_msg = f"ChatGPT 接口返回错误: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f" - {error_data.get('message', '')}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"
                logger.error(error_msg)
                return f'{{"error": "{error_msg}"}}'

            result = parse_sse_response(response)

            if result["conversation_id"]:
                self._conversation_id = result["conversation_id"]
            if result["message_id"]:
                self._parent_message_id = result["message_id"]

            return result["text"]

        except requests.exceptions.Timeout:
            error_msg = f"ChatGPT 接口超时 ({timeout}s)"
            logger.error(error_msg)
            return f'{{"error": "{error_msg}"}}'
        except requests.exceptions.ConnectionError as e:
            error_msg = f"连接 ChatGPT 接口失败: {e}"
            logger.error(error_msg)
            return f'{{"error": "{error_msg}"}}'
        except Exception as e:
            error_msg = f"调用 ChatGPT 接口异常: {e}"
            logger.error(error_msg)
            return f'{{"error": "{error_msg}"}}'

    def _send_via_proxy_server(self, prompt: str, model: str, timeout: int) -> str:
        """通过独立部署的 web_proxy_server.py 服务调用"""

        payload = {
            "prompt": prompt,
            "model": model,
            "timeout": timeout * 1000,
        }

        if self._access_token:
            payload["access_token"] = self._access_token

        try:
            response = requests.post(
                f"{self._proxy_server_url}/send_message",
                data=payload,
                timeout=timeout + 10,
            )

            if response.status_code != 200:
                data = response.json()
                error_msg = data.get("message", "代理服务返回错误")
                logger.error(error_msg)
                return f'{{"error": "{error_msg}"}}'

            data = response.json()
            return data.get("text", "")

        except Exception as e:
            error_msg = f"调用代理服务失败: {e}"
            logger.error(error_msg)
            return f'{{"error": "{error_msg}"}}'


# ═══════════════════════════════════════════════════════════════
# 第四部分：便捷工厂函数
# ═══════════════════════════════════════════════════════════════

def create_web_client() -> WebLLMClient:
    """
    从环境变量创建 WebLLMClient（便捷工厂函数）

    读取的环境变量:
        OPENAI_ACCESS_TOKEN:  直接提供 access_token
        OPENAI_EMAIL:         OpenAI 账号邮箱
        OPENAI_PASSWORD:      OpenAI 密码
        REVERSE_PROXY_URL:    反向代理 URL
        WEB_PROXY_SERVER_URL: 独立代理服务 URL
    """
    access_token = os.environ.get("OPENAI_ACCESS_TOKEN", "")
    email = os.environ.get("OPENAI_EMAIL", "")
    password = os.environ.get("OPENAI_PASSWORD", "")
    proxy_server_url = os.environ.get("WEB_PROXY_SERVER_URL", "")
    reverse_proxy = os.environ.get("REVERSE_PROXY_URL", "")

    return WebLLMClient(
        access_token=access_token or None,
        email=email or None,
        password=password or None,
        reverse_proxy=reverse_proxy or None,
        proxy_server_url=proxy_server_url or None,
    )


# ═══════════════════════════════════════════════════════════════
# 第五部分：测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Web LLM 客户端测试")
    print("=" * 60)

    print(f"\n反向代理: {DEFAULT_REVERSE_PROXY}")
    print(f"认证服务: {AUTH_SERVICE_URL}")

    token = get_access_token_from_file()
    if token:
        print(f"本地缓存: 有 (token前20位: {token[:20]}...)")
    else:
        print("本地缓存: 无")

    env_token = os.environ.get("OPENAI_ACCESS_TOKEN", "")
    env_email = os.environ.get("OPENAI_EMAIL", "")
    if env_token:
        print(f"环境变量 OPENAI_ACCESS_TOKEN: 已设置")
    if env_email:
        print(f"环境变量 OPENAI_EMAIL: {env_email}")
    if not env_token and not env_email and not token:
        print("\n提示: 未检测到 access_token 配置")
        print("  请通过以下方式之一配置:")
        print("  1. 设置 OPENAI_ACCESS_TOKEN 环境变量")
        print("  2. 设置 OPENAI_EMAIL 和 OPENAI_PASSWORD 环境变量")
        print("  3. 启动 web_proxy_server.py 并设置 WEB_PROXY_SERVER_URL")
        sys.exit(1)

    try:
        client = create_web_client()
        print("\n客户端创建成功！")

        print("\n发送测试消息...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "请用一句话回答。"},
                {"role": "user", "content": "你好，请做个自我介绍"},
            ],
            temperature=0.3,
        )
        print(f"\n回答: {response.choices[0].message.content}")

    except Exception as e:
        print(f"\n测试失败: {e}")
        sys.exit(1)
