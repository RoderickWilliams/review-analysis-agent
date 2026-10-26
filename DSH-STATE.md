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
- 质量：全量 pytest 138 项通过；插件自检 9/9；完整能力说明见 docs/CAPABILITIES.md。
- 安全收口：cookie 报告剥本机路径；API 无鉴权时默认只绑 127.0.0.1 并在外绑时提示；bridge 强制 UTF-8 输出。
- v2 规格：docs/v2-product-spec.md（单输入、同款/近似款、四档采集、12 个月窗口、自家/竞品、综合报告 + 行动清单、运营方案按需生成、四层真实性边界、Web 工作台布局）。
- v2 对象层（已完成）：object_resolver.py 解析京东公开商品页（标题/品牌/店铺/类目/同 SPU 规格），淘宝/天猫/小红书只识别链接不猜内容，纯商品名返回搜索入口；same_product.py 做品牌 + 型号词 + 标题相似度 + 类目匹配，同 SPU 强制同款；report_builder.py 生成对象层报告，无评论时所有口碑指标为 null 并列出证据缺口；http_api.py 增加 /v1/object/resolve、/v1/analysis 创建/列表/详情/报告/行动清单/证据；tests/test_object_layer.py 10 项覆盖解析、匹配、报告与 API。
- v2 本地工作台（对象层已接入）：src/reviewagent/webui/{index.html,styles.css,app.js}；FastAPI 同源挂载 /app/，根路径重定向；浅色默认 + 深色，五标签、十二侧栏章节、真实对象卡与候选表、评论补样、最近分析、证据与缺口、移动端卡片表、打印/PDF；Playwright 桌面 1440x1000 与移动 390x844 无 console 错误、无横向溢出；打印 10 页。
- README 已补 v2 产品口径、工作台说明、安装与 CLI 入口；docs/CAPABILITIES.md 增加 v2 状态说明。
- v2 分支已提交并推送到 origin/v2：b2d4e8c「feat: ReviewAgent v2 cross-platform workbench (spec + local UI)」，257 个文件变更；全量 pytest 128 项、compileall、插件 verify 9/9 均通过。
- 当前本机运行：refactor 工作区 E:/DeepSeek/review-agent；v2 git worktree E:/DeepSeek/tmp/review-agent-v2；Web 工作台本地服务 http://127.0.0.1:8000/app/（uvicorn，对象层真实数据）。

## 下一步
1. 跨平台采集与自动找同款：淘宝/天猫、京东、小红书评论区登录采集；候选匹配度优先、销量次之、价格带去重；四档采集上限与 12 个月窗口。
2. 运营方案生成器：痛点 → 改进 → 选题 → 商品页/定价/内容流量/行动清单；事实、统计、建议、文案四层标注。
3. 真机采集：需要扫码登录（xhs_batch.py login）或用户提供带 xsec_token 的笔记链接/关键词。
4. 可选：Scrapling stealth 验证；git CI；把 v2 分支的本轮对象层提交给用户确认后再合并 main。

## 关键路径
- 仓库：E:\DeepSeek\review-agent；venv：.venv\Scripts\python.exe
- 采集技能：C:\Users\wzb02\.dsh\skills\xhs-batch-reader\scripts\xhs_batch.py
- 观众研究技能：C:\Users\wzb02\.dsh\skills\susu-insight（junction → E:\DeepSeek\review-agent\skills\susu-insight）
- 词库：C:\Users\wzb02\.dsh\skills\xhs-banned-words\scripts\xhs_check.py
- 插件：C:\Users\wzb02\.dsh\profiles\desktop\node_modules\dsh-review-agent（junction）＋ profiles\desktop\cordis.patch.yml 的 review-agent 条目
- HUD：.hud\progress.json + hud_publish.py
