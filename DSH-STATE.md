# DSH-STATE

## 当前目标
ReviewAgent v2：以商品链接、商品名或小红书笔记为起点，跨淘宝/天猫、京东、小红书采集同款与近似款，输出口碑诊断、用户痛点、改进方向、宣传选题和可执行运营方案；CLI / HTTP API / DSH 插件 / Agent Skill 四入口保留，新增本地 Web 工作台。规格见 docs/v2-product-spec.md。

## 已完成
- 原有链路：淘宝/京东采集、9 情绪 + 8 有效性 + 交叉验证、Trust Report、HTML 报告、CLI/HTTP API、SQLite 历史、Streamlit 旧界面。
- Scrapling 可选采集底座（适配层、配置、doctor、README、测试），默认关闭。
- 小红书 P0：scrapers/xhs_reader.py（复用 xhs-batch-reader，只读，链接/搜索/主页，cookie 只报布尔与剩余天数）；insights/（痛点证据校验、P0/P1/P2 改进、选题模板、内容生产包 content_kit.py、六章 HTML xhs_report.py）；pipeline.analyze_xhs；CLI reviewagent xhs；API GET /v1/xhs/status、POST /v1/xhs/capture、POST /v1/xhs/analyze。
- 三形态：plugins/dsh-review-agent（七个工具，bridge.py 单行 JSON，verify.mjs 9/9）；skills/review-agent；deploy/（setup.ps1、Dockerfile、docker-compose.yml、.dockerignore）。
- susu-insight 接入：skills/susu-insight 整包副本 + junction；insights/susu.py（评论 scope 映射、主题/认知/选题 JSON 校验、离线 HTML）；CLI reviewagent susu；插件 review_susu。
- 评测：data/eval/sample.jsonl 44 条人工标注；reviewagent eval（rules / none / predictions 文件）；规则基线情绪 acc 0.364 / macro-F1 0.252，有效性 acc 0.705 / macro-F1 0.158。
- 内容生产包：insights/content_kit.py（主图 3 卖点方向、1:1/3:4/16:9、详情页 8 段、15 秒 5 分镜、英文本地化清单、素材索引、文字信号风格卡、分层卡片 schema、宣称边界）；已接 pipeline/JSON/六章 HTML/CLI/API/插件摘要，不生成图片、不编造参数。
- 质量：全量 pytest 123 项通过；插件自检 9/9；HUD 24/24（100%）；完整能力说明见 docs/CAPABILITIES.md。
- 安全收口：cookie 报告剥本机路径；API 无鉴权时默认只绑 127.0.0.1 并在外绑时提示；bridge 强制 UTF-8 输出。
- v2 规格：docs/v2-product-spec.md（单输入、同款/近似款、四档采集、12 个月窗口、自家/竞品、综合报告 + 行动清单、运营方案按需生成、四层真实性边界、Web 工作台布局）。
- v2 本地工作台原型：src/reviewagent/webui/{index.html,styles.css,app.js}；FastAPI 同源挂载 /app/，根路径重定向；浅色默认 + 深色，四标签，六指标，证据弹层，移动端表格卡片化，打印强制浅色；tests/test_webui.py 5 项通过。当前数据为演示样例，未接真实跨平台采集。
- README 已补 v2 产品口径、工作台说明、安装与 CLI 入口；docs/CAPABILITIES.md 仍以既有能力为主。

## 下一步
1. v2 后端：输入解析（商品链接/商品名/笔记）、同款匹配、三平台采集调度、采集档位与增量重跑、运营方案生成器。
2. 把工作台接到真实报告：输入框提交 → 任务状态 → 报告渲染；演示数据替换为真实数据时保留 x/xx 占位规则。
3. 跑 compileall + 全量 pytest（原 123 + 新 5）与插件 verify.mjs，确认无回归。
4. 更新 HUD（新增 v2 规格/UI/验收步骤），并在 E:/review-analysis-agent 建 v2 分支合入重构版后提交推送（remote 内嵌 token，勿打印）。
5. 真机采集：需要扫码登录（xhs_batch.py login）或用户提供带 xsec_token 的笔记链接/关键词。
6. 可选：Scrapling stealth 验证；git CI。

## 关键路径
- 仓库：E:\DeepSeek\review-agent；venv：.venv\Scripts\python.exe
- 采集技能：C:\Users\wzb02\.dsh\skills\xhs-batch-reader\scripts\xhs_batch.py
- 观众研究技能：C:\Users\wzb02\.dsh\skills\susu-insight（junction → E:\DeepSeek\review-agent\skills\susu-insight）
- 词库：C:\Users\wzb02\.dsh\skills\xhs-banned-words\scripts\xhs_check.py
- 插件：C:\Users\wzb02\.dsh\profiles\desktop\node_modules\dsh-review-agent（junction）＋ profiles\desktop\cordis.patch.yml 的 review-agent 条目
- HUD：.hud\progress.json + hud_publish.py
