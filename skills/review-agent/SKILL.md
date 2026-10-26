---
name: review-agent
description: 分析商品评论或小红书笔记与评论，输出情绪分布、刷单与反讽识别、Trust Report、用户痛点、产品改进方向、宣传选题模板、内容生产包（主图/详情页/15 秒脚本/英文清单/素材索引），或只想算一份统计可信度报告时使用。用户说「分析评论」「这批评价可信吗」「刷单检测」「小红书痛点和选题」「主图 brief」「review 报告」时调用。
---

# ReviewAgent

跨平台评价分析：评论 → 情绪与有效性 → 可信度 → 痛点 → 改进建议 → 宣传选题。三种入口共用一套内核。

## 先判断入口

| 场景 | 用什么 |
|------|--------|
| 在 DSH 里直接对话 | 插件工具 `review_analyze` / `review_xhs` / `review_susu` / `review_trust_report` / `review_xhs_status` / `review_history` / `review_doctor` |
| 本地命令行、脚本、批处理 | `reviewagent` 子命令 |
| 别的服务对接 | `reviewagent serve`，HTTP API |

插件没装或工具不可用时，退回 CLI（下面命令都在仓库根目录执行，Windows 用 `.venv\Scripts\python.exe`）。

## 标准流程

1. 先自检：`reviewagent doctor`。看模型配置、依赖、采集后端、小红书登录。
2. 小红书先看状态：`reviewagent xhs` 不带来源会报用法；正式跑之前确认登录没过期。
3. 采集与分析：
   - 淘宝/京东：`reviewagent analyze --url <链接> --max-reviews 50`（采集默认关闭，要先开 `REVIEWAGENT_ENABLE_SCRAPING=1`）
   - CSV：`reviewagent analyze --csv reviews.csv`，必须有 `review_text` 列
   - 小红书：`reviewagent xhs --keyword "关键词" --limit 20`；或 `--links <链接1> <链接2>`；或 `--user <主页链接>`（带 `xsec_token`）；已采集过用 `--run-dir <目录>`
   - 只要可信度：插件 `review_trust_report`，或 `POST /v1/trust-report`（不调模型）
   - 对标账号的观众认知与选题：`reviewagent susu --run-dir <采集目录>`（`--no-llm` 只做确定性归类；`--analysis <json>` 只重新渲染）
   - 评测：`reviewagent eval --dataset data/eval/sample.jsonl --baseline rules`，或 `--predictions <文件>`
4. 读结果：终端摘要先看信任分、风险等级、可疑评论数、痛点条数、选题条数；报告在 `output/`。
5. 引用时带出处：痛点、改进项、选题都必须附原帖或评论链接。模型推断写成推断，不冒充实测结论。

## 参数要点

`reviewagent xhs`：`--limit` 默认 20、上限 50；`--sort` 综合/最新/最多点赞/最多评论/最多收藏；`--sweep` 四种排序轮换合并；`--note-type 视频|图文`；`--no-comments`、`--no-ocr`、`--max-images`；`--capture-only` 只采集；`--run-dir` 复用已有目录；`--no-history` 不写历史。

`reviewagent susu`：`--run-dir` 采集目录；`--analysis` 已有 analysis.json；`--account` 账号名；`--out-dir` 输出目录；`--no-llm` 跳过模型。主题与选题由模型生成后要过技能校验：每条专业评论只能落在一个主题里，选题证据必须属于它的主题。

HTTP API：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 健康检查 |
| GET | `/v1/config` | 模型与目录状态（不返回 Key） |
| POST | `/v1/analyze` | 评论分析（`reviews` 数组或 `csv_path`） |
| POST | `/v1/trust-report` | 只算 Trust Report |
| GET/POST/DELETE | `/v1/history` | 历史记录 |
| GET | `/v1/xhs/status` | 小红书采集状态 |
| POST | `/v1/xhs/capture` | 只采集 |
| POST | `/v1/xhs/analyze` | 采集并分析（或传 `run_dir` 复用） |

## 报告结构

普通评论报告：情绪分布、有效性、Trust Report（突发、近重复、评分与文本矛盾）、红旗、逐条明细。

小红书六章：总览（笔记数/评论数/带图文字）、情绪与可信度、用户痛点（频次、严重度、代表引语、原帖）、改进方向（P0/P1/P2、成本、影响、验证方式）、宣传选题（人群、标题、封面文案、正文骨架、标签、风险词）、内容生产包（主图卖点与比例、详情页 8 段、15 秒分镜、英文本地化清单、素材索引、风格卡、分层卡片 schema、宣称边界）。内容生产包只给结构和待确认项，不生成图片、不编造产品参数。

susu-insight 观众研究报告：账号概览、观众认知、讨论主题（每条附代表原话）、内容选题（场景、为什么值得讲、可以怎么讲）。默认落 `output/susu/`。

## 失败排查

- `未配置大模型 API Key`：填 `.env` 的 `DEEPSEEK_API_KEY`，或设置 `REVIEWAGENT_API_KEYS`（多个用逗号分隔）。
- `需要登录` / 409：小红书扫码一次，cookie 约一年有效。
- `没有可分析的评论文本`：笔记没评论或采集被限流；换关键词、缩小 limit、稍后再试。
- 依赖缺失：`pip install -e ".[api,scrapling]"`；OCR 再装 Tesseract。

## 边界

- 采集默认关闭；开启前确认目标站点条款。
- 只读：不发布、不点赞、不评论、不关注。
- 单次建议 ≤20 篇；限流时降速，不并发轰炸。
- 没有 Key 时不假装分析：报告会写明缺哪一步。
