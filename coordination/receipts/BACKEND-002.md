# BACKEND-002 回执 — 后端与独立爬虫最小修复

- 任务 ID：BACKEND-002
- 执行：DSH 会话 session-e15676c3-5681-4edb-b0e1-8c2c33354dbe
- 时间：2026-10-28 23:22 – 23:45（Asia/Shanghai）
- 基线：`codex/reviewagent-upgrade` @ `e339339`；工作树保留 Codex 未提交的 webui/* 与 http_api.py，本对话未修改、未纳入。
- 结论：四项修复完成，定向离线回归 45 项通过。未访问真实平台，未调用模型，未 commit，未 push。

## 一、修改文件与行为变化

| 文件 | 行为变化 |
| --- | --- |
| `crawler.py` | 平台自动识别补 `xhslink.cn` / `www.xhslink.cn` → `xhs`；`xhslink.com`、`xiaohongshu.com`、淘宝/天猫、京东行为不变 |
| `src/reviewagent/object_resolver.py` | 淘宝/天猫短链：最终 URL 不含商品 ID 时，从 canonical、`itemId`/`auctionId` 字段、`itemId=` 参数、item.htm 链接（按可信度排序）取 ID，重建 `https://detail.tmall.com/item.htm?id=<id>`（或 item.taobao.com）；只接受 6 位以上数字；最终 URL 既无 ID 又无可信字段时保留原始短链，不再返回带 `app=chrome`/`bxsign` 的移动端地址；`input_url` 仍保留原始分享链接 |
| `src/reviewagent/browser_collection.py` | 京东落到 `*.pf.jd.com` 频控主机直接返回 `rate_limited`；页面文案“暂时无法展示该商品的信息”归入限流；新增 `_degraded_page(snapshot)`，精简页（正文 <600 字、无评价词、文档高度 <1200）在等待 30 秒后抛 `degraded_page`，不再落到“成功 0 条” |
| `src/reviewagent/public_collection.py` | 京东评论接口返回“活动太火爆/请稍微再试/访问频繁”（短文本）时抛 `rate_limited`，停止该平台本轮请求 |
| `src/reviewagent/analysis_tasks.py` | 新增 `recover_interrupted()`：启动时把 `queued/running/cancel_requested` 且不在本进程 `_active` 的记录标为 `interrupted`（“任务已中断，可继续”），不动评论/结果/草稿 |
| `run_local.py`、`src/reviewagent/cli.py` | 启动服务前调用 `recover_interrupted()`；单 Uvicorn worker 架构，不引入分布式任务系统 |

## 二、新增测试

| 文件 | 覆盖 | 数量 |
| --- | --- | --- |
| `tests/test_crawler_cli.py` | CLI 自己的 `platform_from_url`（xhslink.cn/www、既有域名不变）；CLI 主流程把识别出的平台传给采集并写出 JSON | 3 |
| `tests/test_shortlink_canonicalization.py` | 最终 URL 无 ID + HTML canonical/内嵌 itemId → 重建规范入口；丢弃移动端参数；随机数字/5 位编号不被当 ID；最终 URL 有 ID 时保持原样；无 ID 时保留短链 | 5 |
| `tests/test_task_recovery.py` | 启动恢复标记 interrupted 且保留原文；活动任务不被误标；恢复后可执行历史重置 | 3 |
| `tests/test_platform_blocked.py` | 京东频控主机 → rate_limited；正常京东域名不误判；精简页判定；等待时抛 degraded_page；京东接口限流文案 → rate_limited | 6 |

既有受影响用例也重跑：`test_source_selection.py`、`test_collection_routes.py`、`test_taobao_share_flow.py`、`test_tmall_review_expansion.py`、`test_navigation_abort.py`。
期间修正了一处兼容：旧测试的假响应对象没有 `.text`，现在按 `.text` → `.content` 回退读取，未放宽任何断言。

## 三、实际执行命令与结果

```
# 定向回归（9 个文件）
HOME=... USERPROFILE=... PYTHONPATH=src venv/Scripts/python.exe -m pytest \
  tests/test_crawler_cli.py tests/test_shortlink_canonicalization.py \
  tests/test_task_recovery.py tests/test_platform_blocked.py \
  tests/test_source_selection.py tests/test_collection_routes.py \
  tests/test_taobao_share_flow.py tests/test_tmall_review_expansion.py \
  tests/test_navigation_abort.py -p no:cacheprovider

结果：45 passed, 1 warning in 1.00s
```

单项运行结果（用于区分新增与既有）：

- `test_crawler_cli.py` + `test_shortlink_canonicalization.py`：8 passed
- `test_task_recovery.py`：3 passed
- `test_platform_blocked.py`：6 passed

语法检查：`py_compile` 对 crawler.py、object_resolver.py、analysis_tasks.py、browser_collection.py、public_collection.py、cli.py、run_local.py 全部 exit 0。

未运行全量测试，定向通过不等于全量通过。

## 四、接口与数据结构

- 无 HTTP 接口、字段、数据库结构变化。
- 新增内部函数 `analysis_tasks.recover_interrupted()`，不对外暴露。
- 采集结果的既有字段不变；新增的失败码沿用 `rate_limited`，精简页沿用 `degraded_page`（此前已存在）。

## 五、未解决风险

1. 短链 HTML 若同时出现他人商品链接，可信度排序只能降低误取概率；本批未在真实页面验证（禁止访问）。
2. 京东频控主机判断基于 `*.pf.jd.com` 与页面文案；平台改版后需补规则。
3. 启动恢复依赖进程内 `_active` 为空；若未来改成多 worker，需要独立任务表，本批未扩展。
4. 精简页阈值（600 字 / 1200 高度）来自一次实测证据，页面结构变化可能需要调整。
5. 真实平台采集仍未复测，淘宝/京东限流是否解除未知。

## 六、声明

- 没有访问真实平台链接（测试全部使用 fixture / 模拟页面与保存的证据字符串）。
- 没有调用模型或 OCR，模型费用 0。
- 没有 commit、没有 push，没有恢复或修改用户已重置的记录。
- 没有修改前端、showcase、README 或其他纯文字交付物。

（说明：本批完成后，用户另行指示把两份 README 草稿格式化并连同最新更新上传 GitHub；该发布动作在回执之后单独执行，不属于本批验收范围。）
