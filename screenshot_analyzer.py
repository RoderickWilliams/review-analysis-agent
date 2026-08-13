# -*- coding: utf-8 -*-
"""
截图评论提取器 (ScreenshotAnalyzer) — 增强版
==============================================
集成 OCR 引擎 + LLM 视觉能力的双管道评论提取。

3 大图片识别工具管道：
  1. PaddleOCR 提取文字 → LLM 结构化解析（首选，高效精准）
  2. Tesseract 提取文字 → LLM 结构化解析（备用）
  3. LLM Vision 直接从图片提取结构化评论（兜底）

伦理准则：
  - 严禁使用AI生成虚假评论进行虚假分析
  - 截图中的评论来自真实网页，非AI生成
  - 每条评论保留溯源信息（source_platform/source_url/product_id等）
  - LLM 仅用于解析已有文字，不得生成新评论
"""

import base64
import json
import io
import time
from typing import Dict, List, Optional, Tuple


class ScreenshotAnalyzer:
    """截图评论提取器 — OCR + LLM 双管道。"""

    def __init__(self, api_key: str = None, model: str = "gpt-4o",
                 base_url: str = None, web_client=None):
        self.model = model
        self._web_mode = web_client is not None
        self._last_error = ""
        # 判断模型是否支持视觉（图片输入）
        self._supports_vision = model in (
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview",
            "gpt-4o-2024-05-13", "gpt-4o-2024-08-06",
            "claude-3-opus", "claude-3-sonnet", "claude-3.5-sonnet",
        )

        if web_client is not None:
            self.client = web_client
        else:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=120.0,
            )

        # 初始化 OCR 引擎（传入 LLM client 作为第三引擎）
        self._ocr = None
        try:
            from ocr_engine import OCREngine
            self._ocr = OCREngine(
                llm_client=self.client if not self._web_mode else None,
                llm_model=model,
            )
            if self._ocr.has_local_engine:
                print(f"[screenshot] OCR 引擎已就绪: {self._ocr.engine_name}")
            else:
                print("[screenshot] 本地 OCR 引擎不可用，将使用 LLM Vision")
        except Exception as e:
            print(f"[screenshot] OCR 引擎初始化失败: {e}")

    @staticmethod
    def _compress_image(image_bytes: bytes, max_size: int = 1920) -> bytes:
        """压缩图片：缩放到最大宽度1920px，转为JPEG quality=85。"""
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode == "RGBA":
                img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > max_size:
                ratio = max_size / max(w, h)
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=85)
            compressed = output.getvalue()
            orig_kb = len(image_bytes) / 1024
            new_kb = len(compressed) / 1024
            print(f"[screenshot] 图片压缩: {orig_kb:.0f}KB -> {new_kb:.0f}KB")
            return compressed
        except ImportError:
            print("[screenshot] PIL未安装，使用原始图片")
            return image_bytes
        except Exception as e:
            print(f"[screenshot] 图片压缩失败: {e}，使用原始图片")
            return image_bytes

    @staticmethod
    def _encode_image(image_bytes: bytes) -> str:
        return base64.b64encode(image_bytes).decode("utf-8")

    def _build_parse_prompt(self, ocr_text: str, platform: str) -> str:
        """构建 LLM 结构化解析 Prompt（从 OCR 文字中提取评论）。"""
        platform_names = {
            "taobao": "淘宝/天猫",
            "jd": "京东",
        }
        platform_name = platform_names.get(platform, platform)
        return f"""你是一位{platform_name}平台的评论分析专家。
以下是从{platform_name}网页截图中通过 OCR 提取的文字内容。请从中识别并提取所有用户评论。

OCR 提取的文字：
---
{ocr_text}
---

提取要求：
1. 识别文字中所有的用户评论（不包括系统提示、广告、按钮文字、页面标题）
2. 对每条评论提取以下信息：
   - review_text: 评论正文内容
   - rating: 评分（数字1-5，如果看不到评分则默认为5）
   - reviewer_name: 评论者昵称（看不到则填"匿名用户"）
   - review_date: 评论日期（看不到则填空字符串）
   - sku: 购买的商品规格/型号（看不到则填空字符串）
3. 如果评论中有追评，一并合并到 review_text 中
4. 只提取文字中已有的评论，严禁生成新评论

请严格以JSON数组格式输出，不要输出任何其他文字：
[{{"review_text": "评论内容", "rating": 5, "reviewer_name": "买家", "review_date": "2024-01-01", "sku": ""}}]"""

    def _build_vision_prompt(self, platform: str) -> str:
        """构建 LLM 视觉直接解析 Prompt（兜底方案）。"""
        platform_names = {
            "taobao": "淘宝/天猫",
            "jd": "京东",
        }
        platform_name = platform_names.get(platform, platform)
        return f"""你是一位{platform_name}平台的评论分析专家。
请仔细分析这张网页截图，提取所有用户评论。

提取要求：
1. 识别截图中所有的用户评论（不包括系统提示、广告、按钮文字）
2. 对每条评论提取以下信息：
   - review_text: 评论正文内容
   - rating: 评分（数字1-5，如果截图中看不到评分则默认为5）
   - reviewer_name: 评论者昵称（看不到则填"匿名用户"）
   - review_date: 评论日期（看不到则填空字符串）
   - sku: 购买的商品规格/型号（看不到则填空字符串）
3. 如果评论中有追评，一并合并到 review_text 中
4. 只提取截图中可见的真实用户评论，严禁生成新评论

请严格以JSON数组格式输出，不要输出任何其他文字：
[{{"review_text": "评论内容", "rating": 5, "reviewer_name": "买家", "review_date": "2024-01-01", "sku": ""}}]"""

    def analyze_screenshot(self, image_bytes: bytes,
                           platform: str = "taobao",
                           product_url: str = "",
                           product_id: str = "",
                           product_name: str = "") -> Tuple[List[Dict], str]:
        """分析单张截图 — OCR优先，LLM Vision兜底。

        :return: (reviews, error_message)  error_message为空表示成功
        """
        if self._web_mode:
            return [], "Web 模式不支持截图分析，请在 .env 中设置 LLM_MODE=api"

        # === 阶段1: OCR 提取文字 ===
        ocr_text = ""
        ocr_method = "none"
        if self._ocr and self._ocr.has_local_engine:
            print("[screenshot] 正在执行 OCR 文字识别...")
            ocr_text, ocr_method = self._ocr.extract_text_with_method(image_bytes)
            if ocr_text.strip():
                print(f"[screenshot] OCR ({ocr_method}) 提取到 {len(ocr_text)} 字符")
            else:
                print("[screenshot] 本地 OCR 未提取到文字，使用 LLM Vision")
        else:
            print("[screenshot] 本地 OCR 引擎不可用，使用 LLM Vision")

        # === 阶段2: LLM 解析 ===
        reviews = []

        # 路径A: OCR 成功 → LLM 文字解析（高效精准）
        if ocr_text.strip():
            prompt = self._build_parse_prompt(ocr_text, platform)
            reviews = self._call_llm_text(prompt)

        # 路径B: OCR 失败或无结果 → LLM Vision 直接解析（兜底）
        if not reviews and self._supports_vision:
            print("[screenshot] 使用 LLM Vision 直接分析截图...")
            compressed = self._compress_image(image_bytes)
            base64_image = self._encode_image(compressed)
            prompt = self._build_vision_prompt(platform)
            reviews = self._call_llm_vision(prompt, base64_image)
            ocr_method = "llm_vision"
        elif not reviews and not self._supports_vision:
            print(f"[screenshot] 当前模型 {self.model} 不支持视觉，跳过 Vision 路径")
            return [], f"OCR 未能提取到文字，且当前模型 {self.model} 不支持图片视觉分析。请安装 PaddleOCR/Tesseract，或使用 GPT-4o 等视觉模型。"

        if not reviews:
            return [], "未能从截图中提取到任何评论（OCR 和 LLM Vision 均未成功）"

        # 补全溯源字段
        for r in reviews:
            r.setdefault("platform", platform)
            r.setdefault("product_name", product_name)
            r["source_platform"] = platform
            r["source_url"] = product_url
            r["product_id"] = product_id
            r["review_permalink"] = f"{product_url}#review" if product_url else ""
            r["reviewer_id"] = ""
            r["is_demo"] = False
            r["extraction_method"] = f"screenshot_{ocr_method}"
            if "reviewer_name" not in r:
                r["reviewer_name"] = "匿名用户"
            r.setdefault("review_date", r.get("timestamp", ""))
            r.setdefault("sku", "")
            r.setdefault("timestamp", r.get("review_date", ""))
            r.setdefault("user_id", r.get("reviewer_name", ""))
            r.setdefault("rating", 5)
            try:
                r["rating"] = int(r["rating"]) if str(r.get("rating", "5")).isdigit() else 5
            except (ValueError, TypeError):
                r["rating"] = 5

        print(f"[screenshot] 提取到 {len(reviews)} 条评论（方法: {ocr_method}）")
        return reviews, ""

    def _call_llm_text(self, prompt: str) -> List[Dict]:
        """调用 LLM 进行文字解析。"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=4000,
                    timeout=60.0,
                )
                result_text = response.choices[0].message.content.strip()
                return self._parse_response(result_text)
            except Exception as e:
                print(f"[screenshot] LLM文字解析失败 (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
        return []

    def _call_llm_vision(self, prompt: str, base64_image: str) -> List[Dict]:
        """调用 LLM Vision 进行图片解析。"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }}
                            ]
                        }
                    ],
                    temperature=0.1,
                    max_tokens=4000,
                    timeout=120.0,
                )
                result_text = response.choices[0].message.content.strip()
                return self._parse_response(result_text)
            except Exception as e:
                print(f"[screenshot] LLM视觉解析失败 (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
        return []

    def analyze_screenshots(self, image_list: List[bytes],
                            platform: str = "taobao",
                            product_url: str = "",
                            product_id: str = "",
                            product_name: str = "") -> Tuple[List[Dict], str]:
        """分析多张截图。

        :return: (reviews, error_message)
        """
        all_reviews: List[Dict] = []
        errors: List[str] = []

        for i, img_bytes in enumerate(image_list):
            print(f"[screenshot] 正在分析第 {i+1}/{len(image_list)} 张截图...")
            reviews, err = self.analyze_screenshot(
                img_bytes, platform=platform, product_url=product_url,
                product_id=product_id, product_name=product_name,
            )
            if err:
                errors.append(f"截图{i+1}: {err}")
            else:
                all_reviews.extend(reviews)
            if i < len(image_list) - 1:
                time.sleep(1)

        # 去重
        seen = set()
        unique = []
        for r in all_reviews:
            text = r.get("review_text", "")[:150].strip().lower()
            if text and text not in seen:
                seen.add(text)
                unique.append(r)

        combined_err = "; ".join(errors) if errors else ""
        print(f"[screenshot] 共提取 {len(all_reviews)} 条，去重后 {len(unique)} 条")
        return unique, combined_err

    @staticmethod
    def _parse_response(text: str) -> List[Dict]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "reviews" in data:
                return data["reviews"]
        except (json.JSONDecodeError, ValueError):
            import re
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except (json.JSONDecodeError, ValueError):
                    pass
        return []


def create_screenshot_analyzer():
    """工厂函数：根据当前配置创建 ScreenshotAnalyzer 实例。"""
    try:
        from config import (
            get_next_api_key, MODEL, BASE_URL,
            is_web_mode, is_web_configured, get_web_client,
            is_api_key_configured,
        )

        if is_web_mode():
            print("[screenshot] Web 模式不支持视觉分析")
            return None

        if not is_api_key_configured():
            print("[screenshot] API Key 未配置")
            return None

        return ScreenshotAnalyzer(
            api_key=get_next_api_key(),
            model=MODEL,
            base_url=BASE_URL,
        )
    except Exception as e:
        print(f"[screenshot] 初始化失败: {e}")
        return None
