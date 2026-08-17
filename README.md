# ReviewPilot — 跨平台用户反馈智能分析 Agent

> 基于 LLM 的中文评论深度分析工具 — 深度情绪识别 · 反讽检测 · 评价有效性分析 · 淘宝/京东多级降级采集

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![LLM](https://img.shields.io/badge/LLM-DeepSeek%20%7C%20OpenAI-green.svg)](#llm-配置)
[![UI](https://img.shields.io/badge/UI-Streamlit-ff4b4b.svg)](https://streamlit.io)

## 项目简介

ReviewPilot 利用大语言模型（LLM）的深度语义理解能力，结合 TF-IDF 文本相似度算法和 Trust Report 统计分析引擎，实现对淘宝/京东用户评论的**深度情绪识别**、**反讽检测**和**评价有效性检测**。内置浏览器自动化采集模块，支持多级降级抓取，可直接输入商品链接获取评论并完成全链路分析。

### 核心能力

| 能力 | 说明 | 技术实现 |
|------|------|----------|
| 深度情绪识别 | 9 类情绪分类，含反讽/阴阳怪气检测 | LLM 零样本 + Prompt 工程 |
| 评价有效性检测 | 8 类有效性分类（模板化/刷单/AI生成等） | LLM + TF-IDF 相似度 |
| 交叉验证 | 情绪 × 有效性多维融合分析 | LLM 推理 + 综合评分 |
| Trust Report | 突发检测、重复检测、异常分析 | 统计分析 + TF-IDF |
| 红旗引擎 | 促销语言、奖励诱导、空洞重复等模式检测 | 正则匹配 + 模式识别 |
| 淘宝评论采集 | 持久化登录 + 精准 DOM 提取 + 指纹去重 | Patchright + 网络拦截 |
| 京东评论采集 | 五级降级抓取（DrissionPage → Patchright → API → OCR） | 融合 5 个开源项目 |
| 截图 OCR 分析 | 上传评论截图，OCR + LLM 识别评论 | Tesseract + LLM Vision |
| HTML 报告 | 可视化分析报告（Chart.js 图表） | Jinja2 模板 |
| Web UI | Spotify 风格深色主题可视化界面 | Streamlit |

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
| 无效 | 模板化好评 / 套话堆砌 / 批量复制 / 时间集中异常 / 内容偏移 / 用户行为异常 / AI 生成 |

### 评论溯源

每条评论包含 15 个标准化字段，其中 6 个为必填溯源字段：`source_platform`、`source_url`、`product_id`、`reviewer_name`、`review_date`、`sku`，确保分析结果可追溯到原始平台。

## 项目结构

```
review-analysis-agent/
├── app.py                       # Streamlit Web UI（4 种分析模式）
├── main.py                      # CLI 主入口（--url / --csv / --demo / --web）
├── config.py                    # 全局配置（多 Key 轮换、.env 加载、伦理校验）
├── sentiment_agent_core.py      # 核心分析引擎（9 情绪 + 8 有效性 + 交叉验证）
├── fallback_client.py           # LLM 自动降级客户端（API → 网页端）
├── deepseek_web_client.py       # DeepSeek 网页端访问（PoW 求解）
├── web_llm_client.py            # Web 模式 LLM 客户端
├── ocr_engine.py                # 多引擎 OCR（Tesseract + LLM Vision）
├── screenshot_analyzer.py       # 截图评论分析（OCR → LLM 管道）
├── report_generator.py          # HTML 可视化报告生成（Chart.js）
├── trust_report.py              # Trust Report 引擎（突发/重复/异常检测）
├── red_flags.py                 # 红旗引擎（模式检测）
├── data_collector.py            # 数据采集
├── data_preprocessor.py         # 数据预处理（清洗 + 去重 + 分词）
├── auto_login.py                # 自动登录
├── login_subprocess.py          # 登录子进程
├── web_proxy_server.py          # Web 代理服务器
├── setup.py                     # 一键环境安装脚本
├── .env.example                 # 环境变量模板
├── requirements.txt
│
├── scrapers/                    # 多平台爬虫
│   ├── base_scraper.py              # 基类（反检测、重试、去重）
│   ├── multi_platform.py            # 多平台聚合调度
│   ├── login_manager.py             # 自动登录 + Cookie 管理
│   ├── taobao_playwright_scraper.py # 淘宝 Patchright 持久化登录抓取（首选）
│   ├── taobao_comment_v2.py         # 淘宝 rate.taobao.com API 抓取
│   ├── taobao_jsonp_scraper.py      # 淘宝 JSONP API 抓取
│   ├── taobao_scraper.py            # 淘宝 mtop API 签名抓取
│   ├── jd_unified_scraper.py        # 京东三级降级调度器
│   ├── jd_drissionpage_scraper.py   # 京东 DrissionPage 真实 Chrome 抓取
│   ├── jd_playwright_scraper.py     # 京东 Patchright 反检测抓取
│   ├── jd_api_scraper.py            # 京东 club.jd.com JSONP API 直连
│   └── jd_scraper.py                # 京东基础抓取（旧版）
│
├── dsk/                         # DeepSeek 网页端工具
│   ├── api.py                       # API 封装
│   ├── pow.py                       # PoW 挑战求解
│   └── CloudflareBypasser.py        # Cloudflare 绕过
│
├── chains/                      # LangChain 集成
│   └── review_chain.py
│
├── utils/                       # 工具函数
│   └── helpers.py
│
├── tools/
│   └── Tesseract-OCR/           # Tesseract OCR 引擎（已封装，含中文语言包）
│
├── cookies/                     # Cookie 持久化
├── data/                        # 示例数据
└── output/                      # 分析报告输出
```

## 快速开始

### 环境要求

- Python 3.10+（推荐 3.12；3.14 下 PaddleOCR 不可用，Tesseract 正常）
- Windows / macOS / Linux
- 淘宝/京东采集需要 Chrome 浏览器（DrissionPage 调用系统 Chrome）

### 一键安装（推荐）

项目已内置 Tesseract OCR 引擎（Windows 版，含简体中文和繁体中文语言包），无需单独安装系统依赖：

```bash
# 1. 克隆项目
git clone https://github.com/RoderickWilliams/review-analysis-agent.git
cd review-analysis-agent

# 2. 一键安装（自动检测 Python 版本、安装 pip 依赖、Patchright 浏览器、Tesseract）
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

# 2. 安装 Patchright 浏览器（反检测自动化）
patchright install chromium

# 3. 配置环境变量
cp .env.example .env

# 4. 启动 Web UI
streamlit run app.py
```

> **Tesseract OCR**：Windows 版已封装在 `tools/Tesseract-OCR/` 目录。
> macOS/Linux 用户请通过包管理器安装：
> - macOS: `brew install tesseract tesseract-lang`
> - Ubuntu/Debian: `sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra`

### CLI 使用

```bash
python main.py --demo                    # 5 条演示数据快速体验
python main.py --url <商品链接>           # 从商品链接采集 + 全链路分析
python main.py --csv <CSV文件路径>        # 从 CSV 文件批量分析
python main.py --web                     # 启动 Streamlit Web 界面
```

## 评论采集

### 淘宝评论采集

| 优先级 | 方法 | 技术 | 说明 |
|--------|------|------|------|
| 1 | Patchright 持久化登录 | Patchright + 精准 DOM 提取 + 网络拦截 | 最抗检测，首次扫码登录后 Cookie 永久复用 |
| 2 | rate.taobao.com API | requests + 卖家 ID | 无需 mtop 签名 |
| 3 | JSONP API | requests + JSONP | 轻量级接口直连 |
| 4 | mtop API 签名 | requests + MD5 签名 | 需要 `_m_h5_tk` Cookie |

**反污染与去重机制**：精准卡片选择器定位评论容器 → 叶子节点过滤非评论文本 → 黑名单排除广告/推荐/时间戳 → 文本指纹（SimHash）去重，确保采集结果纯净无重复。

### 京东评论采集（五级降级）

融合 5 个开源项目的抓取策略，按反爬能力从强到弱自动降级：

| 级别 | 方法 | 技术来源 | 说明 |
|------|------|----------|------|
| L1 | DrissionPage 真实 Chrome | [JD_Spider](https://github.com/LacYCle/JD_Spider) | 调用系统 Chrome，持久化 profile，手动扫码登录，DOM 虚拟滚动 |
| L2 | Patchright 反检测浏览器 | 自研 | 反检测浏览器 + API 网络拦截 + DOM 提取，登录优先 + 截图兜底 |
| L3 | requests JSONP API | [JDComment_Spider](https://github.com/YuleZhang/JDComment_Spider) + [rupu-product-analysis](https://github.com/jameszhi2/rupu-product-analysis) | 直连 club.jd.com JSONP 接口，遍历 score=0~5 |
| L4 | requests API（增强） | [JRAS](https://github.com/Liuliu2333/JRAS) + [XiaoBai-Data](https://github.com/...) | fake-useragent 随机 UA、指数退避重试、排序方式遍历 |
| L5 | 截图 OCR 兜底 | 自研 | 收集前序浏览器截图，Tesseract + LLM Vision 识别 |

任意一级成功抓到评论即返回；全部失败时，截图交由 OCR 管道兜底识别。

### 截图评论分析

支持上传评论页面截图，通过 OCR 引擎识别文字后进行 LLM 分析：

1. **Tesseract OCR**（主力）— 已封装在项目中，支持中英文识别
2. **LLM Vision**（兜底）— 调用 DeepSeek/OpenAI 视觉模型识别截图

> **可选 PaddleOCR**：在 Python 3.10~3.13 环境中可安装更高精度的中文 OCR：
> ```bash
> pip install paddlepaddle==3.2.0 paddleocr -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
> ```

## Web UI 功能

| 模式 | 说明 |
|------|------|
| 📝 单条评论分析 | 粘贴一条评论，即时获取情绪识别、有效性检测和综合分析 |
| 🔍 截图评论识别 | 上传评论截图，OCR 识别后自动分析 |
| 📁 CSV 批量分析 | 上传 CSV 文件（支持 review_text/rating/platform 字段）批量分析 |
| 🌐 链接采集分析 | 输入淘宝/京东商品链接，自动采集评论并全链路分析 |

UI 采用 Spotify 官网风格深色设计：近黑背景（#121212）、深色卡片（#181818）、蓝紫渐变强调色（#6366f1 → #8b5cf6）、药丸按钮、重阴影分层。

## LLM 配置

### 方式一：DeepSeek API（推荐）

在 `.env` 文件中配置：

```env
LLM_MODE=api
LLM_API_KEYS=sk-your-deepseek-api-key
MODEL=deepseek-chat
BASE_URL=https://api.deepseek.com/v1
```

支持多 Key 轮换（逗号分隔），自动负载均衡和故障转移。获取免费 API Key: https://platform.deepseek.com/

### 方式二：DeepSeek 网页端（免费备用）

无需 API Key，通过 DeepSeek 网页端 Token 调用。当 API Key 额度用尽时自动降级：

```env
DEEPSEEK_USER_TOKEN=your-web-token
```

### 方式三：OpenAI 兼容 API

```env
LLM_MODE=api
LLM_API_KEYS=sk-your-api-key
MODEL=gpt-4o
BASE_URL=https://api.openai.com/v1
```

## Python 版本兼容性

| Python 版本 | 支持状态 | 说明 |
|-------------|---------|------|
| 3.10 ~ 3.13 | ✅ 完全支持 | 所有功能可用，含可选 PaddleOCR |
| 3.14+ | ✅ 主要功能支持 | Tesseract + LLM Vision 作为 OCR 引擎；PaddleOCR 暂不支持 |

## 伦理准则

- **严禁使用 AI 生成虚假评论进行虚假分析**（强制开启，不可关闭）
- 所有评论必须来自真实平台抓取
- 每条评论包含完整溯源字段（source_platform / source_url / product_id 等）
- 爬取失败时如实告知，不得用虚假数据替代
- 演示数据标注为 DEMO，不得冒充真实评论

## 技术栈

| 类别 | 技术 |
|------|------|
| LLM | DeepSeek / OpenAI 兼容 API |
| Web UI | Streamlit |
| 浏览器自动化 | Patchright（反检测 Playwright fork）、DrissionPage、Playwright |
| OCR | Tesseract 5.5.3（内置中文语言包）、LLM Vision、可选 PaddleOCR |
| 数据处理 | Pandas、scikit-learn（TF-IDF）、jieba 分词 |
| 报告生成 | Jinja2 + Chart.js |
| LLM 编排 | LangChain |
| HTTP | requests、curl_cffi（TLS 指纹模拟）、fake-useragent |

## License

[MIT](LICENSE)
