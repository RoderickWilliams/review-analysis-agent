# -*- coding: utf-8 -*-
"""
OCR 文字识别引擎 (OCREngine) — 增强版
=====================================
集成 3 大图片识别工具：
  1. PaddleOCR (主引擎) — https://github.com/PaddlePaddle/PaddleOCR (87K+ stars)
     精度高，支持中文，离线运行
  2. Tesseract (备用引擎) — https://github.com/tesseract-ocr/tesseract (75K+ stars)
     经典引擎，轻量级
  3. LLM Vision (第三引擎) — GPT-4o 视觉能力
     用于 OCR 无法识别时的兜底方案

架构参考: Umi-OCR https://github.com/mucheng2035/Umi-OCR (19.7K+ stars)

工作流程：
  PaddleOCR → Tesseract → LLM Vision → 返回空

使用方式：
    from ocr_engine import OCREngine
    engine = OCREngine()
    text = engine.extract_text(image_bytes)
"""

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class OCREngine:
    """多引擎 OCR 文字识别器 — PaddleOCR + Tesseract + LLM Vision。"""

    def __init__(self, llm_client=None, llm_model: str = "gpt-4o"):
        """
        :param llm_client: LLM 客户端实例（用于 LLM Vision 引擎）
        :param llm_model: LLM 模型名称
        """
        self._paddle = None
        self._tesseract = None
        self._llm_client = llm_client
        self._llm_model = llm_model
        self._engine_name = "none"
        self._init_paddleocr()
        if self._paddle is None:
            self._init_tesseract()

    def _init_paddleocr(self):
        """初始化 PaddleOCR 引擎。"""
        try:
            from paddleocr import PaddleOCR
            self._paddle = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                show_log=False,
            )
            self._engine_name = "paddleocr"
            logger.info("[ocr] PaddleOCR 引擎已加载")
            print("[ocr] PaddleOCR 引擎已加载")
        except ImportError:
            logger.info("[ocr] PaddleOCR 未安装，尝试 Tesseract")
            print("[ocr] PaddleOCR 未安装，尝试 Tesseract")
        except Exception as e:
            logger.warning(f"[ocr] PaddleOCR 初始化失败: {e}")
            print(f"[ocr] PaddleOCR 初始化失败: {e}")

    def _init_tesseract(self):
        """初始化 Tesseract 引擎。"""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self._tesseract = pytesseract
            if self._engine_name == "none":
                self._engine_name = "tesseract"
            logger.info("[ocr] Tesseract 引擎已加载")
            print("[ocr] Tesseract 引擎已加载")
        except ImportError:
            logger.info("[ocr] pytesseract 未安装")
            print("[ocr] pytesseract 未安装")
        except Exception as e:
            logger.warning(f"[ocr] Tesseract 不可用: {e}")
            print(f"[ocr] Tesseract 不可用: {e}")

    @property
    def engine_name(self) -> str:
        """当前使用的引擎名称。"""
        return self._engine_name

    @property
    def is_available(self) -> bool:
        """OCR 引擎是否可用（任一引擎可用即返回 True）。"""
        return (self._paddle is not None or
                self._tesseract is not None or
                self._llm_client is not None)

    @property
    def has_local_engine(self) -> bool:
        """本地 OCR 引擎是否可用（PaddleOCR 或 Tesseract）。"""
        return self._paddle is not None or self._tesseract is not None

    def extract_text(self, image_bytes: bytes) -> str:
        """从图片字节中提取文字（依次尝试所有引擎）。

        :param image_bytes: 图片字节数据
        :return: 提取的文字内容
        """
        if not image_bytes:
            return ""

        # 引擎1: PaddleOCR
        if self._paddle is not None:
            text = self._extract_with_paddle(image_bytes)
            if text.strip():
                return text

        # 引擎2: Tesseract
        if self._tesseract is not None:
            text = self._extract_with_tesseract(image_bytes)
            if text.strip():
                return text

        # 引擎3: LLM Vision (兜底)
        if self._llm_client is not None:
            text = self._extract_with_llm_vision(image_bytes)
            if text.strip():
                return text

        logger.warning("[ocr] 所有 OCR 引擎均未能提取文字")
        return ""

    def extract_text_with_method(self, image_bytes: bytes) -> tuple:
        """提取文字并返回使用的方法。

        :return: (text, method_name)
        """
        if not image_bytes:
            return "", "none"

        if self._paddle is not None:
            text = self._extract_with_paddle(image_bytes)
            if text.strip():
                return text, "paddleocr"

        if self._tesseract is not None:
            text = self._extract_with_tesseract(image_bytes)
            if text.strip():
                return text, "tesseract"

        if self._llm_client is not None:
            text = self._extract_with_llm_vision(image_bytes)
            if text.strip():
                return text, "llm_vision"

        return "", "none"

    def _extract_with_paddle(self, image_bytes: bytes) -> str:
        """使用 PaddleOCR 提取文字。"""
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode == "RGBA":
                img = img.convert("RGB")
            import numpy as np
            img_array = np.array(img)
            result = self._paddle.ocr(img_array, cls=True)
            if not result or not result[0]:
                return ""
            lines = []
            for line in result[0]:
                if line and len(line) >= 2:
                    text_info = line[1]
                    if isinstance(text_info, tuple) and len(text_info) >= 1:
                        lines.append(text_info[0])
                    elif isinstance(text_info, str):
                        lines.append(text_info)
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[ocr] PaddleOCR 提取失败: {e}")
            print(f"[ocr] PaddleOCR 提取失败: {e}")
            return ""

    def _extract_with_tesseract(self, image_bytes: bytes) -> str:
        """使用 Tesseract 提取文字。"""
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode == "RGBA":
                img = img.convert("RGB")
            text = self._tesseract.image_to_string(img, lang="chi_sim+eng")
            return text.strip()
        except Exception as e:
            logger.error(f"[ocr] Tesseract 提取失败: {e}")
            print(f"[ocr] Tesseract 提取失败: {e}")
            return ""

    def _extract_with_llm_vision(self, image_bytes: bytes) -> str:
        """使用 LLM Vision 提取文字（兜底方案）。"""
        if not self._llm_client:
            return ""
        try:
            import base64
            # 压缩图片
            compressed = self._compress_image(image_bytes)
            base64_image = base64.b64encode(compressed).decode("utf-8")

            response = self._llm_client.chat.completions.create(
                model=self._llm_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请提取这张图片中的所有文字内容，按原始顺序输出，不要添加任何解释或格式化。只输出纯文字。"},
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
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[ocr] LLM Vision 提取失败: {e}")
            print(f"[ocr] LLM Vision 提取失败: {e}")
            return ""

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
            return output.getvalue()
        except Exception:
            return image_bytes


# 全局单例
_engine_instance: Optional[OCREngine] = None


def get_ocr_engine(llm_client=None, llm_model: str = "gpt-4o") -> OCREngine:
    """获取全局 OCR 引擎单例。

    :param llm_client: LLM 客户端（首次调用时传入）
    :param llm_model: LLM 模型名称
    :return: OCREngine 实例
    """
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = OCREngine(llm_client=llm_client, llm_model=llm_model)
    return _engine_instance
