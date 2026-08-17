# 跨平台用户反馈智能分析 Agent

> 基于 LLM 的中文评论深度分析工具 — 深度情绪识别 · 反讽检测 · 评价有效性分析 · 淘宝+京东评论采集

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![LLM](https://img.shields.io/badge/LLM-DeepSeek%20%7C%20OpenAI-green.svg)](#llm-配置)

## 项目简介

利用大语言模型（LLM）的深度语义理解能力，结合 TF-IDF 文本相似度算法和 Trust Report 统计分析引擎，实现对淘宝/京东用户评论的**深度情绪识别**和**评价有效性检测**。

### 核心能力

| 能力 | 说明 | 技术实现 |
|------|------|----------|
| 深度情绪识别 | 9 类情绪分类，含反讽/阴阳怪气检测 | LLM 零样本 + Prompt 工程 |
| 评价有效性检测 | 8 类有效性分类（模板化/刷单/AI生成等） | LLM + TF-IDF 相似度 |
| 交叉验证 | 情绪 × 有效性多维融合分析 | LLM 推理 + 综合评分 |
| Trust Report | 突发检测、重复检测、异常分析 | 统计分析 + TF-IDF |
| 红旗引擎 | 促销语言、奖励诱导、空洞重复等模式检测 | 正则匹配 + 模式识别 |
| Playwright 评论采集 | 持久化登录 + 启发式DOM提取，最抗检测 | Playwright + 网络拦截 |
| 截图 OCR 分析 | 上传评论截图，OCR+LLM 识别评论 | Tesseract + LLM Vision |
| Web UI | 可视化分析界面 | Streamlit |

### 分类体系

**情绪分类（9 类）**

| 大类 | 细分类 | 说明 |
|------|--------|------|
| 显性情绪 | 真诚好评 / 直接差评 / 客观中性 | 用户直接表达的情绪 |
| 隐性情绪 | 反讽阴阳怪气 / 明褒暗贬 / 隐性抱怨 | 需要深度语义理解 |
| 评分矛盾 | 高分低评 / 低分高评 / 评分极端文本中性 | 评分与评论不一致 |

**有效性分类（8 类 = 1 真实 + 7 无效）**

| 类型 | 细分类 |
|------|--------|
| 真实 | 真实有效 (authentic) |
| 无效 | 模板化好评 / 套话堆砌 / 批量复制 / 时间集中异常 / 内容偏移 / 用户行为异常 / AI生成 |

## 项目结构

```
review-analysis-agent/
├── config.py                    # 全局配置（多Key轮换、.env加载、降级机制）
├── sentiment_agent_core.py      # 核心分析引擎（分类体系 + Prompt + Agent逻辑）
├── main.py                      # 主入口（CLI + 全流程集成）
├── app.py                       # Streamlit Web UI（4种分析模式）
├── fallback_client.py           # LLM 自动降级客户端（API → 网页端）
├── deepseek_web_client.py       # DeepSeek 网页端访问（PoW求解）
├── setup.py                     # 一键环境安装脚本
├── .env.example                 # 环境变量模板
├── requirements.txt
│
├── tools/
│   └── Tesseract-OCR/           # Tesseract OCR 引擎（已封装，含中文语言包）
│
├── scrapers/                    # 多平台爬虫（5种抓取方式）
│   ├── __init__.py
│   ├── base_scraper.py          # 基类（反检测、重试、去重）
│   ├── taobao_playwright_scraper.py  # Playwright 持久化登录抓取（首选）
│   ├── taobao_comment_v2.py     # rate.taobao.com API 抓取
│   ├── taobao_scraper.py        # mtop API 签名 + Selenium 浏览器抓取
│   ├── jd_scraper.py            # 京东评论采集（API + Selenium）
│   ├── jd_playwright_scraper.py # 京东 Playwright 抓取
│   ├── multi_platform.py        # 多平台聚合调度
│   └── login_manager.py         # 自动登录 + Cookie获取
│
├── ocr_engine.py                # 多引擎 OCR（Tesseract + LLM Vision）
├── screenshot_analyzer.py       # 截图评论分析（OCR → LLM 管道）
├── report_generator.py          # HTML可视化报告生成（Chart.js）
├── trust_report.py              # Trust Report 引擎（突发/重复/异常检测）
├── red_flags.py                 # 红旗引擎（模式检测）
├── data_collector.py            # 数据采集
├── data_preprocessor.py         # 数据预处理（清洗 + 去重 + 分词）
│
├── dsk/                         # DeepSeek 网页端工具
│   ├── api.py                   # API 封装
│   ├── pow.py                   # PoW 挑战求解
│   └── CloudflareBypasser.py    # Cloudflare 绕过
│
├── chains/                      # LangChain 集成
│   └── review_chain.py
│
├── utils/                       # 工具函数
│   └── helpers.py
│
├── data/                        # 数据目录
└── output/                      # 输出目录（gitignored）
```

## 快速开始

### 一键安装（推荐）

项目已内置 Tesseract OCR 引擎（含中文语言包），无需单独安装系统依赖：

```bash
# 1. 克隆项目
git clone https://github.com/RoderickWilliams/review-analysis-agent.git
cd review-analysis-agent

# 2. 一键安装（自动检测Python版本、安装pip依赖、Playwright浏览器、Tesseract）
python setup.py

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 4. 启动 Web UI
streamlit run app.py
```

### 手动安装

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 安装 Playwright 浏览器
python -m playwright install chromium

# 3. 配置环境变量
cp .env.example .env

# 4. 启动 Web UI
streamlit run app.py
```

> **注意**：Tesseract OCR 已封装在 `tools/Tesseract-OCR/` 目录中（Windows，含简体中文和繁体中文语言包）。
> macOS/Linux 用户请通过包管理器安装：
> - macOS: `brew install tesseract tesseract-lang`
> - Ubuntu/Debian: `sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra`

### 验证安装

```bash
python setup.py --check
```

## 评论采集方式

### 淘宝评论采集（4级降级）

| 优先级 | 方法 | 技术 | 说明 |
|--------|------|------|------|
| 方法1 | Playwright 持久化登录 | Playwright + DOM提取 + 网络拦截 | 最抗检测，首次登录后永久复用 |
| 方法2 | rate.taobao.com API | requests + 卖家ID | 无需mtop签名 |
| 方法3 | mtop API 签名 | requests + MD5签名 | 需要 `_m_h5_tk` Cookie |
| 方法4 | 基础页面抓取 | requests + HTML解析 | 最后兜底 |

### 京东评论采集

API 分页抓取为主，Selenium 浏览器抓取为辅。

### 截图评论分析

支持上传评论页面截图，通过 OCR 引擎识别文字后进行 LLM 分析：

1. **Tesseract OCR**（主力）— 已封装在项目中，支持中英文识别，无需额外安装
2. **LLM Vision**（兜底）— 调用 GPT-4o/DeepSeek 视觉模型识别截图

> **可选 PaddleOCR**：如需更高精度的中文 OCR，可在 Python 3.10~3.13 环境中安装：
> ```bash
> pip install paddlepaddle==3.2.0 paddleocr -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
> ```
> PaddleOCR 不支持 Python 3.14，安装后将自动作为首选 OCR 引擎。

## LLM 配置

### 方式一：DeepSeek API（推荐）

在 `.env` 文件中配置：

```env
LLM_MODE=api
LLM_API_KEYS=sk-your-deepseek-api-key
MODEL=deepseek-chat
BASE_URL=https://api.deepseek.com/v1
```

获取免费 API Key: https://platform.deepseek.com/

### 方式二：DeepSeek 网页端（免费备用）

无需 API Key，通过 DeepSeek 网页端 Token 调用：

```env
DEEPSEEK_USER_TOKEN=your-web-token
```

当 API Key 额度用尽时，系统自动切换到网页端模式。

### 方式三：OpenAI API

```env
LLM_MODE=api
LLM_API_KEYS=sk-your-openai-api-key
MODEL=gpt-4o
BASE_URL=https://api.openai.com/v1
```

## Python 版本兼容性

| Python 版本 | 支持状态 | 说明 |
|-------------|---------|------|
| 3.10 ~ 3.13 | ✅ 完全支持 | 所有功能可用，含可选 PaddleOCR |
| 3.14+ | ✅ 主要功能支持 | Tesseract + LLM Vision 作为 OCR 引擎；PaddleOCR 暂不支持 |

## 伦理准则

- **严禁使用AI生成虚假评论进行虚假分析**
- 所有评论必须来自真实平台抓取
- 每条评论包含完整溯源字段（source_platform/source_url/product_id 等）
- 爬取失败时如实告知，不得用虚假数据替代

## 技术栈

- Python 3.10+
- Streamlit（Web UI）
- Playwright（浏览器自动化）
- Tesseract OCR（文字识别，已内置）
- LangChain（Prompt管理）
- DeepSeek / OpenAI（LLM）
- Pandas / jieba / scikit-learn（数据处理）

## License

[MIT](LICENSE)
