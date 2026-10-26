# 小红书平台与洞察引擎：工作计划

日期：2026-10-26 · 项目：E:\DeepSeek\review-agent

## 结论

第三个平台选复用本机 xhs-batch-reader 技能作为采集底座，review-agent 只做适配层与洞察层。理由：该技能已经跑通只读后端（xiaohongshu-mcp）、登录 cookie、四排序搜索、评论样本、图片 OCR 与视频抽帧，产物是结构化 notes.json，每条带 source_url。自己重写小红书抓取会重复处理登录、xsec_token、风控与页面改版，收益低。

新增能力分三层：采集适配 → 洞察引擎 → 交付面。情绪分析、有效性判定、Trust Report 沿用现有内核，不重写。

## 工作包

### P0-1 采集适配层（scrapers/xhs_reader.py）

- available() / status()：检查解释器、脚本、后端二进制、登录态；对应 doctor 的新检查项。
- fetch(keyword|user|links, limit, with_comments, out_dir)：固定 argv 调用 python -X utf8 xhs_batch.py read … --comments --out <dir>，读取产物 notes.json。
- 归一化：笔记（note_id/title/desc/tags/author/stats/time/url/ocr/comments）与评论（comment id/content/like/ip/user/sub_count）。
- 评论映射为现有 review 结构：review_text=content、reviewer_name=user、review_date=评论时间（缺省留空，不编）、source_platform=小红书、source_url=笔记链接、product_id=note_id；按 (note_id, comment id) 去重。
- 配置：REVIEWAGENT_XHS_PYTHON、REVIEWAGENT_XHS_SCRIPT、REVIEWAGENT_XHS_RUN_DIR、REVIEWAGENT_XHS_TIMEOUT、REVIEWAGENT_XHS_LIMIT。
- 错误类型：XhsUnavailable、XhsLoginRequired、XhsCaptureError，消息直接给修复动作。

### P0-2 洞察引擎（insights/）

痛点提取 pain_points.py
- 批量结构化 LLM 调用，输出 schema：pain_point、category、severity(1-3)、evidence_quote、note_id、audience、context。
- 逐条引语校验：normalize 空白后必须能在原文/OCR 文本中找到，找不到的条目标记 unverified 并从榜单剔除（保留在原始 JSON 供审计）。
- 确定性聚合：按类别聚类，频次、互动权重（赞/藏/评）、严重度合成优先级；输出 Top N 痛点，每条带证据列表与来源链接。

产品改进方向 improvements.py
- 输入痛点榜与产品信息，LLM 给出改进项，必须引用 pain_point_id。
- 优先级 = 频次 × 严重度 ÷ 实现成本（成本由模型给理由），输出 P0/P1/P2 路线表；同区域改进项去重合并。

宣传选题与模板 topics.py
- 模板库（JSON，固定可测）：测评、避坑、教程、对比、清单、人群定制。
- 每个选题：目标人群、对应痛点、承诺、3 个标题、封面两行字、正文四段（痛点 → 办法 → 效果 → 收藏/评论钩子）、标签、风险词扫描结果。
- 规则来自 platform-playbook 小红书一节：人群词 + 痛点 + 数字标题、3:4 图集 6–9 张、正文分点、结尾收藏。
- 风险词扫描：调用 xhs-banned-words/scripts/xhs_check.py --format json（存在才启用，不存在则跳过并在报告注明）。

### P0-3 交付面

- pipeline.analyze_xhs()：评论走现有情绪/有效性/融合，笔记+评论走洞察引擎，输出 JSON + 分章 HTML：概览 / 评论情绪与可信度 / 痛点榜 / 产品改进方向 / 宣传选题与模板。
- CLI：reviewagent xhs --keyword … --limit 20 --comments --analyze、reviewagent xhs --run-dir <dir>、reviewagent insights --run-dir <dir>。
- API：POST /v1/xhs/analyze（传 run_dir 或内联 notes）、POST /v1/xhs/capture（受 REVIEWAGENT_ENABLE_SCRAPING 开关约束，未登录返回 409 与登录指引）。
- doctor 增加小红书底座、登录态、词库路径三项。

### P1 质量与文档

- 测试：适配层 fixture（含评论、缺 token、失败降级）、引语校验拒绝伪造引用、聚合排序稳定、选题 schema、词库缺失跳过、CLI 参数、API 400/409/503、HTML 章节齐全。
- README 新增小红书章节（登录一次、单次 ≤20 篇约 4–6 分钟、只读边界）；顺带补上遗留的安装与 LLM 配置章节。
- 安全审查（guidance）：新增 subprocess 边界固定 argv、不拼 shell、路径校验、不读取或输出 cookie。

### P1 三形态打包（遗留）

- DSH 插件（review_xhs_capture、review_xhs_analyze、review_insights）、skill、deploy（docker compose / setup.ps1）、CI。

### P2

- sususkill001 打包；评测基准（1500 条主集 + 300 双标 + 200 对抗集）按原方案推进。

## 验收标准

1. 输入 10 篇小红书笔记及评论（含链接），产出六章报告（含内容生产包）；每条痛点、改进项、选题都能点回原文。
2. 伪造或改写过的引语会被校验拒绝，不出现在榜单里。
3. 离线 fixture 测试全绿；无 API Key 时明确报 503；未登录抓取给出扫码指引而不是静默失败。
4. 真机抓取单次 ≤20 篇，4–6 分钟；只读，不点赞不评论不发布。

## 待确认

1. 采集底座按上述复用 xhs-batch-reader（推荐），还是要求在 review-agent 内直接对接后端 HTTP？
2. 改完后是否允许跑一次完整测试；真机抓取是否现在做（需要扫码登录，或提供带 xsec_token 的笔记/关键词）。