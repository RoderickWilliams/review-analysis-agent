#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web 代理服务器 — Python 版 chatgpt-api
=======================================
移植自 https://github.com/zhuweiyou/chatgpt-api (Node.js/Express)

提供 HTTP 接口，无需 API Key 即可调用 ChatGPT 网页版

启动方式:
    python web_proxy_server.py              # 默认端口 3000
    python web_proxy_server.py --port 8080  # 自定义端口

接口:
    POST /get_access_token  — 获取 access_token
    POST /send_message      — 向 ChatGPT 提问
    GET  /                  — 首页
"""

import json
import argparse
from web_llm_client import (
    get_access_token,
    WebLLMClient,
    DEFAULT_REVERSE_PROXY,
    get_cached_or_fetch_token,
    get_access_token_from_file,
)


def create_app():
    """创建 Flask 应用"""
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        print("错误：请先安装 Flask: pip install flask")
        print("或者使用 web_llm_client.py 直接在 Python 代码中调用")
        import sys
        sys.exit(1)

    app = Flask(__name__)

    @app.route("/")
    def home_page():
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"/>
    <title>Web LLM 代理服务</title>
</head>
<body>
<h3>部署成功</h3>
<p>Web LLM 代理服务已启动</p>
<p>接口文档请查看 <a href="https://github.com/zhuweiyou/chatgpt-api">chatgpt-api</a></p>
<p>Python 版本移植自 Node.js 原项目</p>
<hr>
<p><b>POST /get_access_token</b> — 获取 access_token (参数: email, password)</p>
<p><b>POST /send_message</b> — 向 ChatGPT 提问 (参数: access_token, prompt, model)</p>
</body>
</html>
        """

    @app.route("/get_access_token", methods=["POST"])
    def api_get_access_token():
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        proxy = request.form.get("proxy", "")

        if not email or not password:
            return jsonify({"message": "invalid [email] or [password]"}), 500

        try:
            token = get_access_token(email, password, proxy)
            return jsonify({"access_token": token})
        except Exception as e:
            return jsonify({"message": str(e)}), 500

    @app.route("/send_message", methods=["POST"])
    def api_send_message():
        access_token = request.form.get("access_token", "")
        prompt = request.form.get("prompt", "")
        model = request.form.get("model", "gpt-4o")
        reverse_proxy = request.form.get("reverse_proxy", DEFAULT_REVERSE_PROXY)
        timeout = int(request.form.get("timeout", "0"))
        conversation_id = request.form.get("conversation_id", "")
        parent_message_id = request.form.get("parent_message_id", "")

        if not access_token or not prompt:
            return jsonify({"message": "invalid [access_token] or [prompt]"}), 500

        try:
            client = WebLLMClient(
                access_token=access_token,
                reverse_proxy=reverse_proxy,
            )

            text = client._send_message(
                prompt=prompt,
                model=model,
                conversation_id=conversation_id or None,
                parent_message_id=parent_message_id or None,
                timeout=timeout or 120,
            )

            return jsonify({
                "text": text,
                "conversation_id": client._conversation_id,
                "parent_message_id": client._parent_message_id,
            })
        except Exception as e:
            return jsonify({"message": str(e)}), 500

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web LLM 代理服务器")
    parser.add_argument("--port", type=int, default=3000, help="端口号 (默认: 3000)")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    args = parser.parse_args()

    app = create_app()
    print(f"Web LLM 代理服务启动中...")
    print(f"监听地址: http://localhost:{args.port}")
    print(f"反向代理: {DEFAULT_REVERSE_PROXY}")
    print(f"文档: http://localhost:{args.port}/")
    app.run(host=args.host, port=args.port, debug=False)
