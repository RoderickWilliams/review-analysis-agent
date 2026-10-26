# ReviewAgent 能做什么

ReviewAgent 1.0.0 是一个本地运行的评论与笔记分析工具。它把商品评论、小红书笔记和评论，变成四类可以直接使用的东西：

- 对单条评论的判断：真实情绪、是否像刷单或模板、可信度分数。
- 对一批评论的可信度报告：重复、时间集中、评分与文本矛盾等信号，以及综合风险。
- 对产品的改进线索：用户痛点、证据原句、优先级和验证方式。
- 对内容团队的选题与生产清单：小红书选题骨架、主图方向、详情页段落、15 秒脚本、英文清单和素材索引。

它有一套内核，四个入口：命令行、HTTP API、DSH 插件、Agent Skill。同一份数据从哪个入口进来，都会走同一套分析、同一套报告。

## v2 正在做什么

v2 把入口改成「商品链接 / 商品名 / 小红书笔记」，跨淘宝/天猫、京东、小红书找同款与近似款，输出口碑诊断、痛点、改进方向、选题和运营方案，并提供本地 Web 工作台。产品规格和界面原型已经落盘（docs/v2-product-spec.md、src/reviewagent/webui/），跨平台采集、同款匹配和运营方案生成仍在开发。下面第 1–14 节描述的是当前已经可用的能力，不是 v2 的完成态。

---

## 1. 它适合解决哪些问题

| 你手上的问题 | 它给出的结果 | 结果里能看到什么 |
| --- | --- | --- |
| 这批评价里有多少是刷的、模板化或 AI 写的 | Trust Report | 综合信任分、风险等级、重复评论组、时间集中、评分与文本矛盾、长度过于统一、重复短语、后验区间 |
| 用户真正不满意什么 | 痛点清单 | 痛点陈述、类别、严重程度、出现频次、代表性原句、原帖或原评论链接；引语必须能在原文中找到 |
| 下一版产品先改什么 | 改进建议 | P0 / P1 / P2、成本 1–3、影响 1–3、验证方式、对应痛点证据 |
| 小红书下一批发什么 | 选题模板 | 6 类模板、每类 3 条标题、2 行封面、4 段正文骨架、标签、风险词提示、来源笔记 |
| 主图、详情页、短视频怎么排 | 内容生产包 | 最多 3 个卖点方向、1:1 / 3:4 / 16:9 三种主图比例、详情页 8 段、15 秒 5 个镜头、英文清单、素材索引、风格卡、分层卡片 schema、宣称边界 |
| 对标账号的观众在聊什么 | susu-insight 报告 | 观众认知、讨论主题、内容机会、词频候选、证据评论；可离线打开 |
| 模型或提示词改完有没有变好 | 评测报告 | 情绪与有效性的 accuracy、macro-F1、weighted-F1；44 条人工标注样本和规则基线 |

---

## 2. 可以喂给它什么

### 2.1 CSV 评论

最小要求是一列评论正文。支持的列名不区分大小写：

| 列名 | 作用 |
| --- | --- |
| review_text | 评论正文，必须非空；空行会被跳过 |
| rating | 评分，1–5；缺失或无法解析时按 0 处理 |
| platform | 平台名，例如 淘宝、京东、小红书 |
| product_name | 产品名；不填时用第一行的值或“产品” |
| timestamp | 评论时间；Trust Report 的时间集中检测会用到 |
| user_id | 用户标识；用于后续扩展，当前分析不依赖它 |

编码支持 UTF-8（含 BOM）和 GBK。文件不存在、表头为空、没有任何有效列名时会明确报错，不会静默产出空报告。

### 2.2 淘宝或京东商品链接

命令是 reviewagent analyze --url <商品链接>。这条路径依赖项目里的实验性浏览器采集，默认关闭，需要设置 REVIEWAGENT_ENABLE_SCRAPING=1 并准备浏览器依赖。采集实现包含旧的 Selenium / DrissionPage 路径和可选的 Scrapling 后端。

这条路径的现状要分开看：代码、适配层和测试在仓库里；淘宝、京东的线上采集没有在本次审计中重新跑通，平台页面结构一变就可能失效。把评论导出成 CSV 再分析，是更稳的路径。

### 2.3 小红书笔记与评论

支持三种来源：

| 来源 | 参数 | 说明 |
| --- | --- | --- |
| 单篇或多篇笔记 | --links <链接...> | 单篇链接要带 xsec_token；不需要登录 |
| 关键词搜索 | --keyword <词> | 需要登录；会搜索并读取笔记与评论 |
| 博主主页 | --user <主页链接> | 主页链接要带 xsec_token；需要登录 |

采集调用本机的 xhs-batch-reader 技能：笔记正文、图片 OCR、视频抽帧 OCR、评论样本、互动数、作者、发布时间、原文链接。只读，不发布、不点赞、不评论。

采集上限：代码允许 1–50 篇，默认 20 篇。20 篇通常要几分钟；第一次跑要留足时间。登录用 xhs_batch.py login 扫码，cookie 默认保存在用户目录，登录一次大约可用一年。

### 2.4 已有采集目录

如果已经用 xhs-batch-reader 采过，直接把包含 notes.json 的目录传给 --run-dir，可以跳过采集，重复分析不重复抓取。

### 2.5 演示数据

reviewagent demo 用 5 条内置评论跑完整流程，不需要 CSV，也不需要采集；仍然需要配置 LLM Key 才能看到真实模型输出。

---

## 3. 单条评论怎么判

标准批量分析对每条评论做 3 次模型调用：

1. 情绪识别：判断 9 类情绪。
2. 有效性检测：判断 8 类有效性。
3. 交叉验证：把前两步结果、评分和原文放在一起，给出最终情绪、最终有效性、可信度分数、风险等级和处理建议。

9 类情绪是：真诚好评、直接差评、客观中性、反讽阴阳怪气、明褒暗贬、隐性抱怨、高分低评、低分高评、评分极端文本中性。后 3 类专门处理评分与文本不一致的情况。

8 类有效性是：真实有效、模板化好评、套话堆砌、批量复制、时间集中异常、内容偏移、用户行为异常、AI 生成。

每条结果除了分类，还会带置信度、关键短语、判断理由、具体性得分、真实性得分和可疑特征。最终结果里的 trust_score 是 0–100 的整数，risk_level 是 low / medium / high。

这些是模型判断，不是人工审核结论。温度设为 0，默认开启文件缓存；相同输入会使用缓存结果，改提示词或模型后才会重新调用。批量分析的成本按“评论条数 × 3 次调用”估算，报告生成、痛点提取和改进建议还会额外调用。条数多时先跑 20–50 条看效果，再放大。

---

## 4. 一批评论的报告里有什么

标准分析会生成两份文件：

- output/report_<时间戳>.html：给业务看的单文件报告。
- output/analysis_<时间戳>.json：完整结构化结果，包含 report、trust_report 和 detailed_results。

HTML 报告包含总体统计、情绪分布、真实好评率、可疑评论数量、刷单风险、关键发现、主要抱怨和改进建议。图表脚本从 Chart.js CDN 加载；断网时文字和表格仍在，图表不显示。

Trust Report 是另一层，独立于模型报告，使用可计算信号：

| 信号 | 它在看什么 |
| --- | --- |
| 重复评论组 | 文本高度相似或完全相同的评论，给出组内条数和代表文本 |
| 时间集中 | 多条评论是否挤在很短的时间窗口里 |
| 评分与文本矛盾 | 高分低评、低分高评，或评分与最终情绪不一致 |
| 长度过于统一 | 大量评论长度几乎一样，像同一模板生成 |
| 重复短语 | 跨评论反复出现的短语 |
| 后验区间 | 综合信任分的后验均值和 95% 区间；样本少于 30 条时区间会变宽 |

报告会给出 overall_trust_score、risk_level、signals、posterior、sensitivity 和 summary。它不是平台的审计结论，适合用来决定“这批数据要不要继续看、先看哪几条”，不适合拿来给某个商家定性。样本少于 30 条时，把它当方向线索。

---

## 5. 小红书六章报告

reviewagent xhs 分析完成后会生成：

- output/xhs_report_<时间戳>.html
- output/xhs_analysis_<时间戳>.json

HTML 是六章，单文件，不依赖 CDN：

### 第一章：概览

笔记数、成功采集数、评论数、带图片文字的数量、采集警告、样本时间范围。采集失败或登录态问题会写在这里。

### 第二章：情绪与可信度

情绪分布条形图、真实好评率、Trust Report 的综合分、风险等级、后验区间、信号列表，以及可疑评论表。每条可疑评论保留原文和来源链接。

### 第三章：用户痛点

痛点按严重程度和频次排序。每个痛点包含：

- 一句话陈述。
- 类别：使用体验、质量、效果、价格、服务、物流、包装、人群不适配、信息不符、其他。
- 严重程度：1 轻微、2 中等、3 严重。
- 出现频次和代表性原句。
- 原评论或原帖链接。

引语必须能在评论文本里逐字找到才算 verified。找不到的痛点不会混进主榜单，会单独放在“未进入榜单的痛点”里，标出原因。报告不把模型编出来的句子当用户原话。

### 第四章：产品改进方向

只对已验证痛点生成建议。每条建议包含：

- P0 / P1 / P2 优先级，由影响 1–3 和成本 1–3 计算，不靠模型随口指定。
- 具体动作。
- 成本、影响、验证方式。
- 对应痛点和证据。

没有已验证痛点时，这一章会说明原因，不会硬编建议。

### 第五章：宣传选题

从已验证痛点生成 6 类模板：

| 模板 | 适合的场景 |
| --- | --- |
| 真人实测 | 用具体使用场景验证一个卖点 |
| 避坑清单 | 把用户踩过的坑整理成可核对清单 |
| 教程攻略 | 把具体做法拆成可照做的步骤 |
| 对比选购 | 同预算或同需求下横向比较 |
| 人群定制 | 只对一个具体人群说话 |
| 清单盘点 | 把决策拆成可勾选清单 |

每个选题给 3 条标题、2 行封面文案、4 段正文骨架、标签、风险词提示和来源笔记链接。标题和正文是骨架，不是成品文案；发布前还要按账号语气重写。

### 第六章：内容生产包

这一章把痛点翻译成内容团队能直接排的东西：

| 小节 | 内容 |
| --- | --- |
| 6.1 主图与卖点方向 | 最多 3 个卖点方向，每个带场景、标题方向和主图比例建议（1:1、3:4、16:9） |
| 6.2 详情页 8 段 | 买家最在意的问题、谁在什么场景用、3 个卖点、结构与材质细节、对比与避坑、售后与下一步 |
| 6.3 15 秒短视频分镜 | 5 个时间段：近景钩子、使用场景、产品细节、参数与材质、引导看详情 |
| 6.4 英文本地化清单 | 英文标题、卖点、详情页 8 段、15 秒字幕、参数与单位、售后政策的待翻译清单 |
| 6.5 素材索引 | 采集到的图片比例、尺寸、互动量、原帖链接；只记录元数据，不下载图片 |
| 6.6 风格卡 | 只从文本提取信号；不提取色板、字体或真实版式 |
| 6.7 分层卡片结构 | 图层、安全区、文案占位的 schema，不渲染图片 |
| 6.8 宣称边界 | 可引用原话、必须由产品方确认的内容、禁用词和风险词 |

内容生产包不生成图片，也不写产品参数。参数、认证、售后政策这类内容，报告会明确标成“需要产品方确认”。

---

## 6. susu-insight：观众认知与选题报告

reviewagent susu 把一份小红书采集目录，转成 susu-insight 的观众研究报告。输入是包含 notes.json 的目录，或者一份已有的 analysis.json。

它做四件事：

- 把笔记和评论映射成内容单元，区分专业评论、作者回复、过短或纯符号的评论。
- 按笔记聚合讨论主题，给每个主题挑代表性评论。
- 从带问号的评论里提取内容机会。
- 统计高频词，作为选题和文案的候选词。

输出是离线 HTML 和同名 JSON，默认落在 output/susu/。报告包含观众认知、讨论主题、内容机会和词频。模型可选：加 --no-llm 只做确定性归类；调用模型失败时保留确定性稿，并把失败原因写进 processing_notes。

---

## 7. 评测：改模型或提示词之后怎么比

仓库带 44 条人工标注样本，覆盖 9 类情绪、8 类有效性、反讽、明褒暗贬、高分低评、低分高评、模板化、套话、批量复制、时间集中、内容偏移、AI 生成等场景。

命令：

~~~text
reviewagent eval --dataset data/eval/sample.jsonl --baseline rules
~~~

输出 accuracy、macro-F1、weighted-F1，并写入 output/eval_<时间戳>.json。也支持用 --predictions 传入模型预测结果，对比不同模型或提示词。

当前规则基线的实测值：

| 维度 | accuracy | macro-F1 | weighted-F1 |
| --- | --- | --- | --- |
| 情绪 | 0.364 | 0.252 | 0.335 |
| 有效性 | 0.705 | 0.158 | 0.628 |

这组数字是规则基线的下限，不是模型效果的上限。它的用途是给后续模型、提示词和融合策略提供同一把尺子。

---

## 8. 四个入口

### 8.1 命令行

| 命令 | 作用 |
| --- | --- |
| reviewagent doctor | 检查 Python、依赖、目录、数据库、采集端和登录状态 |
| reviewagent demo | 用 5 条演示评论跑完整分析 |
| reviewagent analyze --csv <文件> | 导入 CSV 并分析 |
| reviewagent analyze --url <商品链接> --max-reviews 50 | 采集淘宝或京东评论并分析；采集默认关闭 |
| reviewagent xhs --links <链接...> | 采集指定小红书笔记并分析 |
| reviewagent xhs --keyword <词> | 搜索并分析；需要登录 |
| reviewagent xhs --user <主页链接> | 读取博主主页笔记；需要登录 |
| reviewagent xhs --run-dir <目录> | 沿用已有采集目录，跳过采集 |
| reviewagent xhs --capture-only | 只采集，不分析 |
| reviewagent susu --run-dir <目录> | 生成 susu-insight 报告 |
| reviewagent eval | 在标注集上评测 |
| reviewagent history --limit 20 | 查看历史记录 |
| reviewagent history --clear --yes | 清空历史记录 |
| reviewagent app --port 8501 | 启动旧版 Streamlit 界面 |
| reviewagent serve --host 127.0.0.1 --port 8000 | 启动 HTTP API |

旧参数仍然可用：python main.py --url、--csv、--demo、--web。

### 8.2 HTTP API

启动：

~~~text
reviewagent serve --host 127.0.0.1 --port 8000
~~~

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | /healthz | 健康检查、版本、模型、Key 是否配置 |
| GET | /v1/config | 只读配置，不返回 Key 明文 |
| POST | /v1/analyze | 批量分析，body 含 reviews、product_name、save_history；最多 200 条 |
| POST | /v1/trust-report | 只算 Trust Report，body 含 reviews、results；最多 500 条 |
| GET | /v1/xhs/status | 小红书采集端、登录状态、cookie 剩余天数 |
| POST | /v1/xhs/capture | 只读采集，body 含 links / keyword / user、limit、with_comments 等 |
| POST | /v1/xhs/analyze | 六章分析，body 可传 capture 或 run_dir |
| GET | /v1/history | 历史记录列表 |
| GET | /v1/history/{record_id} | 单条历史 |
| DELETE | /v1/history/{record_id} | 删除单条历史 |

API 默认只绑定 127.0.0.1，本身没有鉴权。要放到局域网或公网，需要自己在反向代理上加认证，不要把端口直接暴露。

### 8.3 DSH 插件

插件目录是 plugins/dsh-review-agent，注册 7 个工具：

| 工具 | 作用 |
| --- | --- |
| review_analyze | 分析 URL、CSV 或演示数据 |
| review_xhs | 小红书采集与分析，支持 links / keyword / user / run_dir |
| review_xhs_status | 查看小红书采集端和登录状态 |
| review_susu | 生成 susu-insight 报告 |
| review_trust_report | 只算 Trust Report |
| review_history | 查看或清理历史 |
| review_doctor | 环境自检 |

插件通过 Python 桥接进程调用 CLI 内核，stdout 只返回一行 JSON。配置项是 pythonPath、workdir、timeoutMs。安装方式是把插件目录链接到 DSH profile 的 node_modules，再在 cordis.patch.yml 里加 review-agent 条目；插件在 DSH 启动时装配，新工具下次会话出现。

### 8.4 Agent Skill

skills/review-agent 是给 Agent 的调用说明，覆盖触发词、三种入口的选择、xhs 参数、susu 参数、评测和报告落盘约定。用户说“分析评论”“这批评价可信吗”“刷单检测”“小红书痛点和选题”时可以用它。

### 8.5 本地部署

deploy/setup.ps1 提供 Windows 一键安装：默认装 API、旧版界面、采集与 OCR；-Minimal 只装 API；-WithDev 装测试依赖并跑全量测试；-WithScrapling 加 Scrapling。

deploy/Dockerfile 和 docker-compose.yml 提供容器方式。容器内默认绑定 0.0.0.0:8000，compose 映射到 127.0.0.1:8000。部署前先看 .env.example，至少配置 REVIEWAGENT_API_KEYS。

---

## 9. 输出到哪里

默认数据根是仓库根，可以用 REVIEWAGENT_HOME 改。

| 路径 | 内容 |
| --- | --- |
| output/report_<时间戳>.html | 标准评论分析报告 |
| output/analysis_<时间戳>.json | 标准分析的完整 JSON |
| output/xhs_report_<时间戳>.html | 小红书六章报告 |
| output/xhs_analysis_<时间戳>.json | 小红书完整 JSON |
| output/susu/<账号>-评论研究-<日期>.html | susu-insight 报告 |
| output/eval_<时间戳>.json | 评测指标 |
| data/reviewagent.db | SQLite 历史记录 |
| data/eval/sample.jsonl | 44 条标注样本 |

可以用 REVIEWAGENT_DATA_DIR、REVIEWAGENT_OUTPUT_DIR、REVIEWAGENT_CACHE_DIR、REVIEWAGENT_DB_PATH 分别覆盖。

---

## 10. 安装与第一次运行

需要 Python 3.10 及以上。推荐用虚拟环境：

~~~powershell
cd E:\DeepSeek\review-agent
C:\Users\wzb02\.dsh\runtimes\skills\py\python.exe -m venv .venv --system-site-packages
.\.venv\Scripts\python.exe -m pip install -e ".[api,app]"
~~~

要采集、OCR 或 Scrapling，再装完整 extras：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[api,app,ocr,scrape,scrapling]"
~~~

配置 .env：

~~~text
REVIEWAGENT_API_KEYS=你的Key
REVIEWAGENT_MODEL=gpt-4o
REVIEWAGENT_BASE_URL=https://api.openai.com/v1
~~~

自检并用演示数据跑一遍：

~~~powershell
.\.venv\Scripts\python.exe -m reviewagent doctor
.\.venv\Scripts\python.exe -m reviewagent demo
~~~

分析自己的 CSV：

~~~powershell
.\.venv\Scripts\python.exe -m reviewagent analyze --csv D:\data\reviews.csv
~~~

启动 API：

~~~powershell
.\.venv\Scripts\python.exe -m reviewagent serve --port 8000
~~~

---

## 11. 边界与前置条件

| 事项 | 现状 |
| --- | --- |
| 大模型 Key | 分析、痛点、改进、选题、susu 的模型增强需要 OpenAI 兼容 Key；只采集或只算 Trust Report 不需要 |
| 小红书登录 | 关键词搜索和博主主页需要扫码登录；单篇笔记只需要带 xsec_token 的链接 |
| 小红书采集量 | 代码上限 50 篇，默认 20 篇；20 篇通常几分钟，别在高峰期一次拉太多 |
| 淘宝/京东采集 | 实验性，默认关闭；本次审计没有重新跑线上采集，页面改版会影响结果 |
| API 鉴权 | 默认只绑 127.0.0.1，没有内置登录；对外提供要加反向代理认证 |
| 图片与视频 | 内容生产包只给 brief、脚本、清单和 schema；不生成图片、不生成视频、不下载素材图 |
| 语言 | 报告和界面是中文；内容生产包的本地化清单只保留英文，不再生成日文、韩文清单 |
| Trust Report | 规则信号加后验近似，不是平台审计；样本少于 30 条时区间很宽 |
| 数据流向 | 评论文本会发给配置的模型服务；小红书 cookie 留在本机；API 和历史库默认在本机 |

采集前要确认目标站点的使用条款和账号权限。项目只读，不提供发布、点赞、评论、关注能力。

---

## 12. 当前验证状态

| 项目 | 结果 |
| --- | --- |
| Python 编译 | compileall 通过 |
| 全量测试 | 123 项通过（pytest，退出码 0） |
| 插件自检 | verify.mjs 9/9 通过 |
| doctor | 退出码 0；依赖检查全部 OK；小红书采集可用且已登录 |
| LLM Key | 本机当前未配置，所以真实模型分析需要先填 Key |
| 真实小红书采集 | 本次审计没有跑完整采集；采集适配、测试桩和报告流程由单测覆盖 |
| 淘宝/京东线上采集 | 没有重新跑；采集默认关闭 |
| Scrapling 隐身浏览器 | 代码路径和依赖检查可用；隐身浏览器二进制没有下载验证 |

---

## 13. 最短上手路径

1. 进入仓库，创建虚拟环境，装 .[api,app]。
2. 复制 .env.example 为 .env，填 REVIEWAGENT_API_KEYS。
3. 跑 reviewagent doctor，确认依赖和目录。
4. 跑 reviewagent demo，确认模型能出结果。
5. 用自己的 CSV 跑 reviewagent analyze --csv；或者扫码登录后跑 reviewagent xhs --keyword。
6. 打开 output 下的 HTML 报告，先看可信度，再看痛点和改进，最后看选题和内容生产包。

---

## 14. 项目文件在哪

| 内容 | 路径 |
| --- | --- |
| 命令行与流水线 | src/reviewagent/cli.py、pipeline.py |
| 情绪、有效性、交叉验证 | src/reviewagent/sentiment_agent_core.py |
| 可信度报告 | src/reviewagent/trust_report.py |
| 小红书采集适配 | src/reviewagent/scrapers/xhs_reader.py |
| 痛点、改进、选题、内容包 | src/reviewagent/insights/ |
| 小红书六章报告 | src/reviewagent/insights/xhs_report.py |
| 标准 HTML 报告 | src/reviewagent/report_generator.py |
| HTTP API | src/reviewagent/http_api.py |
| susu 报告 | src/reviewagent/insights/susu.py |
| DSH 插件 | plugins/dsh-review-agent/ |
| Agent Skill | skills/review-agent/SKILL.md |
| 部署 | deploy/ |
| 测试 | tests/ |
| 评测样本 | data/eval/sample.jsonl |

更细的安装、采集、API 和插件说明在 README.md 与各目录的 README 里。
