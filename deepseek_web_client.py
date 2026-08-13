# -*- coding: utf-8 -*-
"""
DeepSeek 网页端客户端 V3 — 直接 API 调用（无需浏览器）
=====================================================
通过 curl_cffi 直接调用 chat.deepseek.com API，自动解决 PoW 挑战。

原理:
  1. 获取 PoW challenge
  2. 用 WASM 求解器解决 PoW
  3. 发送消息，解析流式 SSE 响应
  4. 提供 OpenAI SDK 兼容接口

参考项目:
  - https://github.com/xtekky/deepseek4free（PoW + API 逆向）
  - https://github.com/LazyBoyJgn99/deepseek-webui（API 文档）

使用方式:
  from deepseek_web_client import DeepSeekWebClient
  client = DeepSeekWebClient(user_token="your_token")
  response = client.chat.completions.create(
      model="deepseek-chat",
      messages=[{"role": "user", "content": "你好"}]
  )
"""

import os
import sys
import json
import uuid
import time
import logging
from typing import Optional, List, Dict, Any

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

logger = logging.getLogger(__name__)

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


class MockMessage:
    def __init__(self, content: str, role: str = "assistant"):
        self.content = content
        self.role = role


class MockChoice:
    def __init__(self, message: MockMessage, index: int = 0):
        self.message = message
        self.index = index
        self.finish_reason = "stop"


class MockCompletionResponse:
    def __init__(self, text: str, model: str = "deepseek-chat"):
        self.id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        self.object = "chat.completion"
        self.created = int(time.time())
        self.model = model
        self.choices = [MockChoice(MockMessage(text))]


class Completions:
    def __init__(self, client):
        self._client = client

    def create(self, model="deepseek-chat", messages=None, temperature=0.3,
               max_tokens=None, stream=False, **kwargs):
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
        text = self._client._send_message(prompt)
        return MockCompletionResponse(text=text, model=model)


class Chat:
    def __init__(self, client):
        self.completions = Completions(client)


class DeepSeekWebClient:
    """
    DeepSeek 网页端客户端 — 通过 PoW + API 直接调用

    使用方式:
        client = DeepSeekWebClient(user_token="your_token")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": "你好"}],
        )
        print(response.choices[0].message.content)
    """

    BASE_URL = "https://chat.deepseek.com/api/v0"

    def __init__(self, user_token: str = None):
        self.chat = Chat(self)

        if not user_token:
            user_token = os.environ.get("DEEPSEEK_USER_TOKEN", "")

        if not user_token:
            raise ValueError(
                "DEEPSEEK_USER_TOKEN 未配置。\n"
                "获取方式:\n"
                "  1. 登录 https://chat.deepseek.com/\n"
                "  2. F12 → Console → JSON.parse(localStorage.getItem('userToken')).value\n"
                "  3. 将 token 填入 .env 的 DEEPSEEK_USER_TOKEN"
            )

        self._user_token = user_token
        self._pow_solver = None
        self._init_pow()

    def _init_pow(self):
        """初始化 PoW 求解器"""
        try:
            from dsk.pow import DeepSeekPOW
            self._pow_solver = DeepSeekPOW()
            logger.info("PoW 求解器初始化成功")
        except Exception as e:
            logger.error(f"PoW 求解器初始化失败: {e}")
            raise

    def _get_headers(self, pow_response: str = None) -> Dict[str, str]:
        """构建请求头"""
        headers = {
            'Authorization': f'Bearer {self._user_token}',
            'Content-Type': 'application/json',
        }
        if pow_response:
            headers['x-ds-pow-response'] = pow_response
        return headers

    def _get_pow_solution(self) -> str:
        """获取并解决 PoW 挑战"""
        from curl_cffi import requests as cffi_requests

        # 获取 challenge
        resp = cffi_requests.post(
            f'{self.BASE_URL}/chat/create_pow_challenge',
            headers=self._get_headers(),
            json={'target_path': '/api/v0/chat/completion'},
            impersonate='chrome120',
            timeout=30
        )

        if resp.status_code != 200:
            raise RuntimeError(f"PoW challenge 获取失败: {resp.status_code}")

        challenge = resp.json()['data']['biz_data']['challenge']

        # 解决 challenge
        solution = self._pow_solver.solve_challenge(challenge)
        return solution

    def _parse_sse_line(self, line: str) -> Optional[Dict]:
        """解析 SSE 格式的一行数据"""
        if not line:
            return None

        if isinstance(line, bytes):
            line = line.decode('utf-8', 'ignore')

        if not line.startswith('data: '):
            return None

        try:
            data = json.loads(line[6:])
            return data
        except json.JSONDecodeError:
            return None

    def _extract_content(self, data: Dict) -> str:
        """从 SSE 数据中提取文本内容

        DeepSeek 网页端 SSE 响应格式:
        - {"v":"文本"} — 直接内容
        - {"p":"response/content","o":"APPEND","v":"文本"} — 追加内容
        - {"p":"response/status","v":"FINISHED"} — 结束标记
        - {"v":{"response":{...}}} — 初始响应对象（忽略）
        """
        v = data.get('v')
        p = data.get('p')

        # 内容追加
        if p == 'response/content':
            if isinstance(v, str):
                return v
        # 直接内容（无 p 字段）
        elif p is None and isinstance(v, str):
            return v
        # 状态更新
        elif p == 'response/status':
            return ''  # 不提取内容

        return ''

    def _send_message(self, prompt: str) -> str:
        """发送消息到 DeepSeek，返回完整文本"""
        from curl_cffi import requests as cffi_requests

        try:
            # Step 1: 获取 PoW solution
            logger.info("正在获取 PoW solution...")
            pow_solution = self._get_pow_solution()

            # Step 2: 创建聊天会话
            logger.info("创建聊天会话...")
            resp = cffi_requests.post(
                f'{self.BASE_URL}/chat_session/create',
                headers=self._get_headers(),
                json={'character_id': None},
                impersonate='chrome120',
                timeout=30
            )
            if resp.status_code != 200:
                return json.dumps({"error": f"创建会话失败: {resp.status_code}"}, ensure_ascii=False)

            chat_id = resp.json()['data']['biz_data']['id']
            logger.info(f"聊天会话: {chat_id}")

            # Step 3: 发送消息（带 PoW solution）
            logger.info("发送消息...")
            headers = self._get_headers(pow_solution)
            resp = cffi_requests.post(
                f'{self.BASE_URL}/chat/completion',
                headers=headers,
                json={
                    'chat_session_id': chat_id,
                    'parent_message_id': None,
                    'prompt': prompt,
                    'ref_file_ids': [],
                    'thinking_enabled': False,
                    'search_enabled': False,
                },
                impersonate='chrome120',
                stream=True,
                timeout=120
            )

            if resp.status_code != 200:
                error_text = resp.text[:200]
                return json.dumps({"error": f"API 返回 {resp.status_code}: {error_text}"}, ensure_ascii=False)

            # Step 4: 解析流式响应
            text_parts = []
            for line in resp.iter_lines():
                data = self._parse_sse_line(line)
                if data:
                    content = self._extract_content(data)
                    if content:
                        text_parts.append(content)

                    # 检查是否结束
                    if data.get('p') == 'response/status' and data.get('v') == 'FINISHED':
                        break

            result = ''.join(text_parts)
            if not result:
                return json.dumps({"error": "DeepSeek 网页端返回空响应"}, ensure_ascii=False)

            logger.info(f"响应长度: {len(result)}")
            return result

        except Exception as e:
            error_msg = f"DeepSeek 网页端调用失败: {str(e)[:200]}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)


def create_deepseek_web_client() -> DeepSeekWebClient:
    """从环境变量创建 DeepSeekWebClient"""
    return DeepSeekWebClient(
        user_token=os.environ.get("DEEPSEEK_USER_TOKEN", ""),
    )
