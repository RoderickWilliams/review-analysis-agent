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
| 京东评论采集 | 五级降级抓取（DrissionPage → Patchright → API → OCR） | 融合多个开源项目 |
| 截图 OCR 分析 | 上传评论截图，OCR + LLM 识别评论 | Tesseract + LLM Vision |
| CSV 批量分析 | 上传 CSV 文件批量分析评论 | Pandas + 并发 LLM |
| HTML 报告 | 可视化分析报告（Chart.js 图表） | Jinja2 模板 |
| Web UI | 浅色 SaaS 风格侧边栏导航界面 | Streamlit |

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

## Web UI 功能

ReviewPilot 采用浅色 SaaS 设计风格，侧边栏导航，包含 6 个功能页面：

| 页面 | 功能 |
|------|------|
| 🏠 首页 | 仪表盘概览：Hero 横幅、核心指标卡片、情绪分布环形图、最近分析记录 |
| 💬 单条评论分析 | 输入单条评论 + 评分，即时获得情绪/有效性/交叉验证结果 |
| 🔗 链接采集分析 | 输入淘宝/京东商品链接，自动采集评论并全链路分析 |
| 🖼️ 截图识别分析 | 上传评论截图，OCR 识别文字后进行 LLM 分析 |
| 📁 批量 CSV 分析 | 上传 CSV 文件，并发批量分析，导出结果 |
| 📜 分析历史 | 查看历史分析记录，一键重新分析或删除 |

侧边栏还提供 Cookie 管理（淘宝/京东登录）、LLM 缓存清理和版本信息。

## 项目结构

```
review-analysis-agent/
├── app.py                       # Streamlit Web UI（浅色 SaaS 风格）
├── _ui_styles.py                # UI 样式模块（CSS 主题）
├── main.py                      # CLI 主入口（--url / --csv / --demo / --web）
├── config.py                    # 全局配置（多 Key 轮换、.env 加载、伦理校验）
├── sentiment_agent_core.py      # 核心分析引擎（9 情绪 + 8 有效性 + 交叉验证）
├── fallback_client.py           # LLM 自动降级客户端（API → 网页端）
├── deepseek_web_client.py       # DeepSeek 网页端访问（PoW 求解）
├── web_llm_client.py            # Web 模式 LLM 客户端
├── ocr_engine.py                # 多引擎 OCR（Tesseract + LLM Vision）
├── report_generator.py          # HTML 可视化报告生成（Chart.js）
├── trust_report.py              # Trust Report 引擎（突发/重复/异常检测）
├── history_manager.py           # 分析历史记录管理
├── data_collector.py            # 数据采集
├── data_preprocessor.py         # 数据预处理（清洗 + 去重 + 分词）
├── auto_login.py                # 自动登录
├── login_subprocess.py          # 登录子进程
├── web_proxy_server.py          # Web 代理服务器
├── desktop_app.py               # 桌面应用入口（pywebview）
├── .env.example                 # 环境变量模板
├── .streamlit/config.toml       # Streamlit 浅色主题配置
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
│   ├── jd_unified_scraper.py        # 京东降级调度器
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
├── data/                        # 示例数据
│   ├── sample_reviews.csv
│   └── test_reviews.csv
│
├── cookies/                     # Cookie 持久化（gitignore）
├── output/                      # 分析报告输出（gitignore）
└── .llm_cache/                  # LLM 响应缓存（gitignore）
```

## 快速开始

### 环境要求

- Python 3.10+（推荐 3.12；3.14 下 PaddleOCR 不可用，Tesseract 正常）
- Windows / macOS / Linux
- 淘宝/京东采集需要 Chrome 浏览器（DrissionPage 调用系统 Chrome）

### 安装

```bash
# 1. 克隆项目
git clone https://github.com/RoderickWilliams/review-analysis-agent.git
cd review-analysis-agent

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装 Patchright 浏览器（反检测自动化）
patchright install chromium

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 DeepSeek API Key

# 5. 启动 Web UI
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

### 淘宝评论采集（四级降级）

| 优先级 | 方法 | 技术 | 说明 |
|--------|------|------|------|
| 1 | Patchright 持久化登录 | Patchright + 精准 DOM 提取 + 网络拦截 | 最抗检测，首次扫码登录后 Cookie 永久复用 |
| 2 | rate.taobao.com API | requests + 卖家 ID | 无需 mtop 签名 |
| 3 | JSONP API | requests + JSONP | 轻量级接口直连 |
| 4 | mtop API 签名 | requests + MD5 签名 | 需要 `_m_h5_tk` Cookie |

**反污染与去重机制**：精准卡片选择器定位评论容器 → 叶子节点过滤非评论文本 → 黑名单排除广告/推荐/时间戳 → 文本指纹（SimHash）去重，确保采集结果纯净无重复。

### 京东评论采集（五级降级）

融合多个开源项目的抓取策略，按反爬能力从强到弱自动降级：

| 级别 | 方法 | 说明 |
|------|------|------|
| L1 | DrissionPage 真实 Chrome | 调用系统 Chrome，持久化 profile，手动扫码登录，DOM 虚拟滚动 |
| L2 | Patchright 反检测浏览器 | 反检测浏览器 + API 网络拦截 + DOM 提取，登录优先 + 截图兜底 |
| L3 | requests JSONP API | 直连 club.jd.com JSONP 接口，遍历 score=0~5 |
| L4 | requests API（增强） | 随机 UA、指数退避重试、排序方式遍历 |
| L5 | 截图 OCR 兜底 | 收集前序浏览器截图，Tesseract + LLM Vision 识别 |

任意一级成功抓到评论即返回；全部失败时，截图交由 OCR 管道兜底识别。

**DrissionPage 关键修复**：
- 页面加载策略设为 `eager()`，避免京东第三方资源（广告/统计脚本）加载不完导致 `tab.get()` 卡死
- 评论弹窗虚拟滚动不依赖硬编码 class 名，改为从评论卡片向上遍历 DOM 树查找可滚动祖先容器
- `run_js()` 使用显式 `return` 语句确保 JS 返回值被正确接收

### 截图评论分析

支持上传评论页面截图，通过 OCR 引擎识别文字后进行 LLM 分析：

1. **Tesseract OCR**（主力）— 已封装在项目中，支持中英文识别
2. **LLM Vision**（兜底）— 调用 DeepSeek/OpenAI 视觉模型识别截图

### CSV 批量分析

上传包含评论内容的 CSV 文件（需有 `review_text` 列，可选 `rating`、`platform` 列），系统会：
- 自动清洗去重
- 并发调用 LLM 分析（控制速率）
- 实时展示分析进度
- 支持导出结果为 CSV

## LLM 配置

复制 `.env.example` 为 `.env`，填入以下配置：

```env
# DeepSeek API（推荐）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 可选：OpenAI 兼容 API
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=

# 可选：DeepSeek 网页端 Token（API 不可用时自动降级）
DEEPSEEK_USER_TOKEN=
```

支持多 API Key 轮换，当某个 Key 触发限流时自动切换。API 不可用时自动降级到网页端模式。

## 分析报告

每次分析完成后可生成 HTML 可视化报告，包含：

- **情绪分布**：9 类情绪占比环形图
- **评分分布**：1-5 星评分柱状图
- **有效性分布**：真实/无效评论比例
- **Trust Report**：突发检测、重复检测、异常时间分布
- **红旗检测**：促销语言、奖励诱导、空洞重复等警示
- **评论详情**：每条评论的情绪标签、有效性标签、交叉验证结果

报告使用 Chart.js 渲染，可在浏览器中独立打开。

## 技术栈

| 类别 | 技术 |
|------|------|
| Web UI | Streamlit |
| LLM | DeepSeek API / OpenAI 兼容 API |
| 浏览器自动化 | DrissionPage、Patchright（Playwright 反检测分支） |
| OCR | Tesseract + LLM Vision |
| 数据分析 | Pandas、scikit-learn（TF-IDF） |
| 报告生成 | Jinja2 + Chart.js |
| 桌面应用 | pywebview |

## 伦理准则

- AI 无法自主生成虚假评论并进行虚假分析
- 每条用于分析的评论都有可追溯的来源
- 不编造评论，不抓取非评论内容凑数
- 若网页实际评论数小于用户输入的最大采集数，直接返回全部真实评论

## License

MIT License — 详见 [LICENSE](LICENSE) 文件。
