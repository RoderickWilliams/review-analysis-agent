# ReviewAgent — 跨平台用户反馈智能分析 Agent

> 基于 LLM 的中文评论深度分析工具 — 情绪识别 · 反讽/刷单检测 · Trust Report · 淘宝/京东/小红书采集 · 跨平台口碑与运营分析（v2 对象层可用）

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![LLM](https://img.shields.io/badge/LLM-DeepSeek%20%7C%20OpenAI-green.svg)](#llm-配置)
[![UI](https://img.shields.io/badge/UI-本地%20Web%20工作台-0b63c5.svg)](#v2-本地-web-工作台对象层已接入)

## 项目简介

ReviewAgent 利用大语言模型（LLM）的深度语义理解能力，结合 TF-IDF 文本相似度算法和 Trust Report 统计分析引擎，实现对淘宝/京东/小红书用户评论与笔记的**深度情绪识别**、**反讽/刷单检测**、**痛点与改进方向提取**。内置浏览器自动化采集模块，支持多级降级抓取；v2 规格进一步把入口收敛为「商品链接 / 商品名 / 小红书笔记」，跨平台找同款与近似款，输出口碑诊断、增长机会和可执行运营方案。

完整能力说明（能做什么、怎么用、输出什么、边界在哪）见 [docs/CAPABILITIES.md](docs/CAPABILITIES.md)；v2 产品规格见 [docs/v2-product-spec.md](docs/v2-product-spec.md)。

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
| HTML 报告 | 可视化分析报告（Chart.js 图表） | 自研单文件 HTML 模板 |
| 跨平台商品分析（v2 对象层） | 京东商品链接解析标题/品牌/店铺/同 SPU 规格；京东、淘宝/天猫、小红书链接识别；同款/近似款候选；对象层报告与证据缺口 | 公开商品页解析 + 规则匹配 + 模板报告，不登录、不猜价格销量 |
| 本地 Web 工作台（对象层已接入） | 单一输入框，粘贴京东链接即可生成真实对象报告；五个一级标签、十二个侧栏章节、证据与缺口、深色与打印 | 原生 HTML/CSS/JS，FastAPI 同源挂载 |

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

## v2 本地 Web 工作台（对象层已接入）

v2 不再把 Streamlit 作为默认界面。新的本地工作台是单页应用，由 FastAPI 同源挂载到 /app/，不依赖 CDN：

| 区域 | 内容 |
|------|------|
| 首屏 | 单输入框（商品链接 / 小红书链接 / 商品名）、采集档位、分析对象卡片、六个指标 |
| 总览 | 结论、平台覆盖、情绪分布、优先动作、证据与方法 |
| 口碑诊断 | Trust Score、有效性分布、风险信号、痛点图谱、竞品入口 |
| 增长机会 | P0/P1/P2 改进卡、选题卡、内容生产包 |
| 运营方案 | 商品页、定价促销、内容流量、本周行动清单、商家确认清单 |

界面默认浅色，可切换深色或跟随系统；桌面为左侧目录 + 顶部四个一级标签，平板收起目录，移动端单列长页 + 吸顶分段标签。图表同时给出文字说明与可展开数据表，打印时强制浅色并展开全部标签页。

**当前状态**：对象层已经接通真实后端。粘贴京东商品链接后，页面会解析标题、品牌、店铺、类目与同 SPU 规格，生成真实的对象报告和同款候选；没有评论时，口碑分、风险等级、痛点与运营方案明确显示「未评估 / 未采集」，不用占位数字冒充结论。淘宝/天猫/小红书目前只识别链接并提示需要补采集，不猜标题；评论采集、跨平台同款搜索与完整运营方案仍按 [docs/v2-product-spec.md](docs/v2-product-spec.md) 实现。

启动服务后打开 <http://127.0.0.1:8000/app/>。旧版 Streamlit 界面保留为兼容入口（reviewagent app），不再是默认部署目标。

## 项目结构

```
review-agent/
├── pyproject.toml                  # 打包配置：reviewagent / reviewagent[api,dev,scrapling,all]
├── README.md / ETHICS.md / LICENSE
├── .env.example                    # 环境变量模板
├── config/
│   └── scrapling_selectors.example.json   # Scrapling 选择器模板
├── data/                           # 示例 CSV（sample_reviews / test_reviews / cleaned_sample）
├── tests/                          # pytest 测试
├── docs/                           # 能力说明、v2 产品规格、平台计划
├── deploy/                         # setup.ps1 / Dockerfile / docker-compose.yml
├── plugins/dsh-review-agent/       # DSH 插件（七个工具 + lib/bridge.py）
├── skills/review-agent/            # Agent Skill（SKILL.md）
├── skills/susu-insight/            # 观众研究报告技能（模板 + 校验 + 渲染器）
├── data/eval/sample.jsonl          # 44 条人工标注评测集
├── .hud/                           # 本对话任务进度悬浮窗的发布数据
└── src/reviewagent/
    ├── __main__.py                 # python -m reviewagent
    ├── cli.py                      # analyze / xhs / susu / eval / demo / app / serve / history / doctor
    ├── config.py                   # 配置：多 Key 轮换、采集开关与后端
    ├── llm.py                      # LLM 客户端与响应缓存
    ├── sentiment_agent_core.py     # 分析引擎：9 情绪 + 8 有效性 + 交叉验证
    ├── trust_report.py             # Trust Report：突发/重复/评分异常 + 后验区间 + 敏感性
    ├── pipeline.py                 # 采集 → 清洗 → 分析 → 报告（含 analyze_xhs）
    ├── http_api.py                 # FastAPI HTTP API（评论 + 小红书 + /app/ 工作台）
    ├── webui/                      # v2 本地工作台（index.html / styles.css / app.js）
    ├── app.py / _ui_styles.py      # Streamlit 旧界面（兼容入口）
    ├── report_generator.py         # 评论 HTML 报告（Chart.js）
    ├── store.py                    # SQLite：历史 / 运行 / 评测
    ├── history_manager.py          # 历史记录与报告文件管理
    ├── eval.py                     # 评测集与基线指标
    ├── data_collector.py           # 采集编排
    ├── data_preprocessor.py        # 清洗、去重、分词
    ├── ocr_engine.py / screenshot_analyzer.py   # 截图 OCR 分析
    ├── auto_login.py / login_subprocess.py      # 登录辅助
    ├── red_flags.py                # 促销话术与红旗词检测
    ├── launcher.py / main.py       # 启动器与兼容入口
    ├── insights/                   # 小红书洞察：痛点、改进、选题、内容生产包、六章报告
    │   ├── pain_points.py          # 痛点抽取与「引语必须出现」校验
    │   ├── improvements.py         # P0/P1/P2 改进方向
    │   ├── topics.py               # 宣传选题模板
    │   ├── content_kit.py          # 内容 brief、素材索引、风格卡、英文清单与分层卡片
    │   ├── susu.py                 # 接 susu-insight：观众认知 / 主题 / 选题报告
    │   └── xhs_report.py           # 单文件 HTML 报告
    └── scrapers/
        ├── multi_platform.py                  # 多平台调度
        ├── xhs_reader.py                      # 小红书只读采集（复用 xhs-batch-reader）
        ├── scrapling_backend.py               # 可选 Scrapling 后端
        ├── taobao_playwright_scraper.py       # 淘宝：Patchright 持久化登录抓取
        ├── taobao_comment_v2.py               # 淘宝：rate.taobao.com API
        ├── taobao_jsonp_scraper.py            # 淘宝：JSONP API
        ├── taobao_scraper.py                  # 淘宝：mtop 签名
        ├── jd_unified_scraper.py              # 京东：降级调度
        ├── jd_drissionpage_scraper.py         # 京东：DrissionPage
        ├── jd_playwright_scraper.py           # 京东：Patchright
        ├── jd_api_scraper.py                  # 京东：club.jd.com JSONP
        ├── jd_scraper.py                      # 京东：基础抓取
        ├── base_scraper.py / login_manager.py
        └── ...
```

## 快速开始

### 环境要求

- Python 3.10+（推荐 3.12；3.14 下 PaddleOCR 不可用，Tesseract 正常）
- Windows / macOS / Linux
- 淘宝/京东采集需要 Chrome 浏览器（DrissionPage 调用系统 Chrome）

### 安装

```powershell
# 1. 克隆并进入项目
git clone https://github.com/RoderickWilliams/review-analysis-agent.git
cd review-analysis-agent

# 2. 建虚拟环境
python -m venv .venv

# 3. 安装本体与 API（/app/ 工作台也在这里）
.venv\Scripts\python.exe -m pip install -e ".[api]"
# 需要浏览器采集、截图 OCR、旧版 Streamlit 或 Scrapling 底座时：
# .venv\Scripts\python.exe -m pip install -e ".[api,app,ocr,scrape,scrapling]"

# 4. 配置环境变量
Copy-Item .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY 或 REVIEWAGENT_API_KEYS

# 5. 自检、跑演示、启动本地工作台
.venv\Scripts\python.exe -m reviewagent doctor
.venv\Scripts\python.exe -m reviewagent demo
.venv\Scripts\python.exe -m reviewagent serve --host 127.0.0.1 --port 8000
# 然后打开 http://127.0.0.1:8000/app/
```

Windows 一键脚本：`powershell -NoProfile -ExecutionPolicy Bypass -File deploy\setup.ps1`（默认装 API、旧版界面、采集与 OCR；加 `-Minimal` 只装 API，加 `-WithDev` 装测试依赖并跑全量测试）。

需要淘宝/京东浏览器采集时再执行 `patchright install chromium`；只做 CSV 或小红书分析不必装。旧版 `streamlit run app.py` 仍可用（`.venv\Scripts\python.exe -m reviewagent app`），不再是默认入口。

> **Tesseract OCR**：Windows 需安装 Tesseract 并让 PATH 能找到 `tesseract.exe`（常见路径 `C:\Program Files\Tesseract-OCR\tesseract.exe`）；仓库不内置 OCR 二进制，`reviewagent doctor` 会检查。
> macOS/Linux 通过包管理器安装：
> - macOS: `brew install tesseract tesseract-lang`
> - Ubuntu/Debian: `sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra`

### CLI 使用

安装后提供 `reviewagent` 命令，子命令与旧入口并存：

```bash
reviewagent demo                                    # 5 条演示评论跑通全链路
reviewagent analyze --url <商品链接> [--max-reviews 50]
reviewagent analyze --csv <CSV文件路径>
reviewagent app [--port 8501]                       # 旧版 Streamlit 界面（兼容）
reviewagent serve [--host 127.0.0.1] [--port 8000]  # HTTP API + /app/ 本地工作台
reviewagent xhs --keyword <关键词>                   # 小红书采集 + 六章分析
reviewagent susu --run-dir <采集目录>                # 观众研究报告（susu-insight）
reviewagent eval --dataset data/eval/sample.jsonl    # 评测集基线
reviewagent history [--limit 20] [--clear --yes]
reviewagent doctor                                  # 环境自检
```

旧入口继续可用：`python main.py --url/--csv/--demo/--web`。两种入口调用同一套流水线。

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

### 可选采集后端：Scrapling

Scrapling 负责取回页面、按选择器解析成统一的评论结构；平台特有逻辑（淘宝 mtop 签名、京东 JSONP、登录态与验证码）仍走原来的爬虫。它不替换现有降级链，只多一条可选的请求 / 解析管道。

**安装**

```bash
pip install "reviewagent[scrapling]"     # 含 fetchers：curl_cffi、playwright、patchright 等
pip install scrapling                    # 只要 HTTP + 解析、不要浏览器
```

需要隐身渲染时，浏览器内核装到 E: 盘：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH='E:\DeepSeek\local-data\ms-playwright'
patchright install chromium
```

**启用**

```env
REVIEWAGENT_ENABLE_SCRAPING=1
REVIEWAGENT_SCRAPER_BACKEND=scrapling
REVIEWAGENT_SCRAPLING_SELECTORS=config/scrapling_selectors.json
REVIEWAGENT_SCRAPLING_MODE=auto        # auto | http | stealth
REVIEWAGENT_SCRAPLING_TIMEOUT=30
```

选择器写在 JSON 里，站点改版只改配置：

```json
{
  "platform": "taobao",
  "platform_name": "淘宝",
  "item": "div.comment-item",
  "fields": {
    "review_text": ".content::text",
    "rating": ".rating::attr(title)",
    "review_date": "time::attr(datetime)",
    "reviewer_name": ".user::text"
  },
  "rating_pattern": "(\\d+(?:\\.\\d+)?)"
}
```

模板见 `config/scrapling_selectors.example.json`。`fields` 的选择器必须带 `::text` 或 `::attr(...)`：不带伪类时 Scrapling 返回元素内部 HTML。

`mode=auto` 先用 HTTP 请求；遇到 401/403/407/429/503 或 Cloudflare、滑动验证一类挑战页，自动升级到隐身浏览器重取。`mode=stealth` 直接走隐身浏览器，`mode=http` 只走 HTTP。

**边界**

- 默认关闭。要采集先设 `REVIEWAGENT_ENABLE_SCRAPING=1`；目标站点的使用条款由使用者确认。
- 淘宝 mtop 的 `_m_h5_tk` 签名、京东 `club.jd.com` 的 JSONP 参数、扫码登录流程都不迁移到 Scrapling。
- 未装 `scrapling` 时模块仍可导入，只在调用抓取时抛 `ScraplingUnavailable`；未装 fetchers 时 HTTP 抓取不可用，解析不受影响。
- 隐身浏览器二进制没下载时，`mode=stealth` 失败并给出安装命令。

`reviewagent doctor` 会打印采集开关、当前后端、Scrapling 解析 / 抓取是否可用，以及选择器配置路径。

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

## v2 跨平台商品分析（对象层已实现，采集与运营待接入）

v2 把入口收敛成一句话：输入一个商品链接、一个商品名，或一篇小红书笔记，输出跨平台口碑与下一步运营动作。完整产品规格见 [docs/v2-product-spec.md](docs/v2-product-spec.md)，这里只列已经确认的口径。

### 输入与识别

- 淘宝/天猫、京东商品链接：直接进入采集，不打断。
- 商品名：先在淘宝、京东、小红书找候选，置信度高直接跑，置信度低先给候选让用户确认。
- 小红书笔记链接：先识别笔记里提到的商品；识别不出时给 2–3 个候选并允许手动输入，不选则只分析笔记正文、图片文字和评论，并标注「未做跨平台同款采集」。
- 识别后显示「分析对象」卡片，类型和「自家 / 竞品」都可手动改，默认自家。

### 同款、平台与采集量

- 同款范围：同型号、同系列、同规格，允许颜色、容量、套装不同；品类竞品只在用户明确要求时单列，不混入本品主评分。
- 平台：淘宝/天猫（按一个平台处理）、京东、小红书。抖音、拼多多后续再加。
- 档位：轻量 / 标准 / 深度 / 自定义，默认标准。标准档上限为 5 个同款或近似款商品/商家、每个 100 条评论、小红书 20 篇笔记；生成后可升档或降档并增量重跑。
- 取样：匹配度优先，其次销量，再做价格带去重。
- 时间：默认最近 12 个月，从新到旧；不足 30 条时自动向前补，报告写清补采数量、最老一条时间和各平台缺口。

### 输出

一份综合报告加一份独立行动清单（CSV / Markdown）。报告分四块：总览、口碑诊断（Trust Score、情绪、有效性、风险信号、痛点）、增长机会（改进方向、内容选题、内容生产包）、运营方案（商品页转化、定价促销、内容流量、本周行动清单）。点「运营方案」才按需生成详细方案，生成后缓存，报告本身不自动下载，只给下载按钮。

### 真实性边界

事实层只用采集到的原句、评分、时间、链接和数量，引用可回查；统计层由程序计算；建议层标「建议」并附依据，没有依据就写样本不足；文案层标「建议 / 草稿」，不冒充真实用户原话，不编参数、认证、销量或效果承诺。模型生成的草稿里的数字用 x / xx 占位，真实采集统计照实展示。

**实现状态**：对象解析、同 SPU 匹配、对象层报告与本地工作台已完成并接入真实京东商品页；跨平台评论采集、跨平台同款搜索和运营方案生成仍在开发。当前可用的真实能力是对象层报告、下文的小红书分析与选题，以及淘宝/京东评论分析。

## 小红书分析与选题

小红书链路做四件事：只读采集（笔记正文、评论、图片文字）、情绪与可信度打分、痛点归并与证据引用、改进方向与宣传选题。采集复用本机 `xhs-batch-reader` 技能里的只读后端，分析走与淘宝/京东相同的 LLM 与 Trust Report 内核。

### 前置：登录与自检

搜索关键词和博主主页需要登录态；只分析单篇笔记链接时，链接要带 `xsec_token`。

```powershell
# 扫码登录一次，cookie 存在 ~/.xhs-batch-reader/cookies.json
& 'C:\Users\wzb02\.dsh\runtimes\skills\py\python.exe' -X utf8 `
  C:\Users\wzb02\.dsh\skills\xhs-batch-reader\scripts\xhs_batch.py login

reviewagent doctor   # 打印小红书采集可用性、登录状态与采集脚本路径
```

### CLI

```powershell
reviewagent xhs --keyword 粉底液 --limit 20 --sweep
reviewagent xhs --links https://www.xiaohongshu.com/explore/<id>?xsec_token=...
reviewagent xhs --user "https://www.xiaohongshu.com/user/profile/<id>?xsec_token=..."
reviewagent xhs --run-dir output/xhs_runs/<时间戳>    # 复用已采集目录，只跑分析
reviewagent xhs --keyword 粉底液 --capture-only       # 只采集，不调用大模型
```

| 参数 | 作用 |
|------|------|
| `--limit` | 单次最多读几篇，默认 20，上限 50 |
| `--sort` | 综合 / 最新 / 最多点赞 / 最多评论 / 最多收藏 |
| `--sweep` | 轮换四种排序再合并去重，覆盖面更大 |
| `--note-type` | 只取 `视频` 或 `图文` |
| `--no-comments` | 不读评论，只保留笔记正文与图片 |
| `--no-ocr` | 跳过图片文字识别 |
| `--max-images` | 每篇最多下载几张图 |
| `--capture-only` | 只采集并打印目录，不分析 |
| `--no-history` | 不写历史记录 |

### HTTP API

`reviewagent serve` 启动后：

| 方法与路径 | 作用 |
|------------|------|
| `GET /v1/xhs/status` | 采集端可用性、登录状态、脚本路径 |
| `POST /v1/xhs/capture` | 传 `keyword` / `user` / `links` 之一，返回笔记摘要与评论列表 |
| `POST /v1/xhs/analyze` | 传 `capture` 对象或 `run_dir`，返回六章分析结果 |

采集错误按类型映射：未登录 `409`，后端不可用 `503`，采集失败 `502`，参数缺失 `400`；未配置模型时分析返回 `503`。

### 输出

一份 HTML 六章报告，默认落在 `output/xhs_report_<时间戳>.html`，同目录另存 `xhs_analysis_<时间戳>.json`：

1. **总览**：笔记数、评论数、带图文字比例、可信度与风险等级。
2. **情绪与可信度**：情绪分布、总体信任分、95% 区间、可疑评论与触发信号。
3. **用户痛点**：按频次与严重度排序，每条附代表原句与原帖链接；未通过验证的痛点单列，不进榜单。
4. **改进方向**：P0/P1/P2 分级，写清依据、成本、预期影响与验证方式。
5. **宣传选题**：人群词、三条标题、封面两行文案、四段正文骨架、标签与风险词预检。
6. **内容生产包**：主图 3 个卖点方向、1:1/3:4/16:9 比例、详情页 8 段、15 秒短视频分镜、英文本地化清单、素材索引、文字信号风格卡、分层卡片 schema 与宣称边界。只给结构和待确认项，不生成图片，不编造产品参数。

内容生产包（JSON 里的 `content_kit`）是确定性输出，不额外调用模型，也不生成图片：

- **主图**：最多 3 个来自已验证痛点的卖点方向；每个卖点带原句、原帖和「不可宣称」清单。比例为 1:1 电商主图、3:4 小红书封面、16:9 详情页头图。
- **详情页**：固定 8 段，逐段给目的、写法、证据和必须人工确认的项；产品参数、认证、售后政策没有输入时留空，不补写。
- **15 秒短视频**：5 个 beat，分别给时长、镜头、口播、字幕和证据。
- **英文清单**：英文目标市场字段、术语表和 6 条本地化检查项；状态是「待翻译」，不把机器翻译当成成品。
- **素材索引**：笔记图片的尺寸、比例、所属笔记和互动量，按互动排序；有图笔记少于 3 篇时标低置信。只读元数据，不下载图片。
- **风格卡**：只从标题、标签和笔记类型提取文字信号；色板、字体、版式没有接视觉模型，明确标为「未提取」，不编造视觉结论。
- **分层卡片**：给设计工具的主图/详情头图/小红书封面图层 schema，标安全区，不渲染图片。
- **宣称边界**：用户原话只能证明「用户遇到过这个问题」，不能证明产品功效；绝对化、医疗化和风险词会被列出，发布前要人工确认。

### 边界

- 只读：不发布、不点赞、不评论、不关注。登录 cookie 留在本机。
- 单次采集建议不超过 20 篇，约 4–6 分钟；`--limit` 上限 50。
- 痛点提取与改进建议需要大模型；没有 Key 时只能采集与出统计，报告会写明缺哪一步。
- 采集端缺失或未登录时 CLI 提示「需要登录」，API 返回 `409`，不会静默降级成空结果。

### 观众研究报告：susu-insight

六章报告回答「产品哪里不好、怎么改、怎么讲、素材怎么落地」；内容生产包把痛点转成可执行的 brief，但不会替代产品参数、法务审核或真实拍摄。如果目标是研究一个对标账号的观众认知与内容选题，用同一份采集目录跑 susu-insight 技能生成的报告。技能本体在 `skills/susu-insight`（随仓库交付，模板、校验规则与渲染器都按原样保留），`insights/susu.py` 只负责把采集结果映射成技能要求的 `analysis.json` 并调用它的渲染器。

```powershell
reviewagent susu --run-dir output\xhs-runs\<时间戳>          # 默认调用大模型细分主题
reviewagent susu --run-dir <目录> --no-llm                   # 不调模型，按笔记确定性归类
reviewagent susu --analysis output\susu\<名字>.json          # 只重新渲染已有 analysis
```

| 参数 | 作用 |
|------|------|
| `--run-dir` | 小红书采集目录（含 `notes.json`） |
| `--analysis` | 已有 analysis.json，只渲染不重新分析 |
| `--account` | 报告里显示的账号名，默认取首篇笔记作者 |
| `--out-dir` | 输出目录，默认 `output/susu` |
| `--no-llm` | 跳过模型，只做确定性归类 |

映射规则：评论短于 10 字、纯符号或纯 @ 标为 `exclude` 并写原因；作者本人的回复标为 `context`，只作上下文；其余进入 `professional`。模型只输出主题、观众认知与选题三块 JSON，写回前逐项校验——每条专业评论必须且只能落在一个主题里，代表评论必须在同主题内，选题的证据必须属于它的主题；校验不过的条目丢弃，未归类的评论进「其他讨论」。模型调用失败时保留确定性稿，并在 `processing_notes` 里写明原因。

报告默认落 `output/susu/<账号>-评论研究-<日期>.html`，同名自动加序号；同目录 `.json` 是技能输出的统计与自检结果。

## 四种入口 + 本地工作台

同一套内核，四个入口，外加一个浏览器界面：

| 形态 | 入口 | 适合 |
|------|------|------|
| CLI | `reviewagent <子命令>` | 本机脚本、批处理、调试 |
| HTTP API | `reviewagent serve` | 其他服务、容器、远程调用 |
| DSH 插件 | `plugins/dsh-review-agent` | 在 DeepSeek Harness 对话里直接调用 |
| Agent Skill | `skills/review-agent` | 任意支持 SKILL.md 的代理加载操作手册 |
| 本地工作台 | `reviewagent serve` 后打开 /app/ | 商家、运营直接看报告与行动清单 |

### DSH 插件

```powershell
# 1. 链进 profile（实体留在 E 盘，用 junction）
New-Item -ItemType Junction -Path "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-review-agent" -Target 'E:\DeepSeek\review-agent\plugins\dsh-review-agent'
```

2. 在 profile 的 `cordis.patch.yml` 追加：

```yaml
- id: review-agent
  name: dsh-review-agent
  config:
    pythonPath: 'E:\DeepSeek\review-agent\.venv\Scripts\python.exe'
    workdir: 'E:\DeepSeek\review-agent'
    timeoutMs: 900000
```

3. 重载 DSH，新会话里出现七个工具：`review_analyze`、`review_xhs`、`review_susu`、`review_xhs_status`、`review_trust_report`、`review_history`、`review_doctor`。

自检：`node plugins\dsh-review-agent\verify.mjs`。细节见 [插件 README](plugins/dsh-review-agent/README.md)。

### Agent Skill

```powershell
# 已安装时可建 junction，复制也可以
New-Item -ItemType Junction -Path "$env:USERPROFILE\.dsh\skills\review-agent" -Target 'E:\DeepSeek\review-agent\skills\review-agent'
```

SKILL.md 里写了入口选择、标准流程、参数表、HTTP 路由与失败排查；代理读到「分析评论」「小红书痛点选题」这类任务就会加载。

### 本地部署

- Windows：`powershell -NoProfile -ExecutionPolicy Bypass -File deploy\setup.ps1`（`-WithDev` 装测试依赖并跑全量测试）。
- Docker：`docker compose -f deploy/docker-compose.yml up -d --build`，映射 `127.0.0.1:8000`，`GET /healthz` 校验。

说明见 [deploy/README.md](deploy/README.md)。

## 离线评测（eval）

`data/eval/sample.jsonl` 是 44 条人工标注样本，覆盖 9 类情绪与 8 类有效性，含反讽、明褒暗贬、评分与文本矛盾、模板化、批量复制、时间集中、内容偏移与 AI 生成。评测命令把规则基线或外部预测文件换算成准确率、macro-F1 与 weighted-F1：

```powershell
reviewagent eval --dataset data/eval/sample.jsonl --baseline rules --out output/eval_baseline.json
reviewagent eval --dataset data/eval/sample.jsonl --predictions preds.json
```

当前规则基线（只用词表与模板短语，不调用模型）：情绪 accuracy 0.364 / macro-F1 0.252，有效性 accuracy 0.705 / macro-F1 0.158。这个数字是下限参照，不是内核效果；接上模型的预测文件用同一条命令跑，报告写在同一个 JSON 里。

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

```

支持多 Key 轮换：`REVIEWAGENT_API_KEYS=sk-a,sk-b`（也接受 JSON 数组），某个 Key 限流时自动换下一个。只走 OpenAI 兼容 API，网页端通道已移除。

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
| CLI / API / 插件 | Typer 风格 argparse、FastAPI + Uvicorn、DSH 插件（Node ESM + subprocess 桥） |
| LLM | DeepSeek API / OpenAI 兼容 API（多 Key 轮换） |
| 浏览器自动化 | DrissionPage、Patchright（Playwright 反检测分支） |
| 可选采集后端 | Scrapling（HTTP + 隐身浏览器 + 选择器配置驱动解析）、xiaohongshu-mcp（小红书只读） |
| OCR | Tesseract + LLM Vision |
| 数据分析 | Pandas、scikit-learn（TF-IDF） |
| 报告生成 | 自研单文件 HTML 模板 + Chart.js 4（CDN） |
| 本地工作台 | 原生 HTML/CSS/JS（无 CDN），FastAPI StaticFiles 同源挂载 |
| 旧版界面 | Streamlit（reviewagent app，兼容入口） |

## 伦理准则

- AI 无法自主生成虚假评论并进行虚假分析
- 每条用于分析的评论都有可追溯的来源
- 不编造评论，不抓取非评论内容凑数
- 若网页实际评论数小于用户输入的最大采集数，直接返回全部真实评论

## License

MIT License — 详见 [LICENSE](LICENSE) 文件。
