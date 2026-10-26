# dsh-review-agent

把 ReviewAgent 接到 DeepSeek Harness 里：评论分析、小红书采集与选题洞察、susu-insight 观众研究报告、Trust Report、历史记录、环境自检，七个工具。

插件本身没有运行时依赖：进程由宿主 `ctx.subprocess` 以 argv 启动，Python 侧由 `lib/bridge.py` 承接，只在标准输出回一行 JSON。

## 工具

| 工具 | 作用 | 关键参数 |
|------|------|----------|
| `review_analyze` | 跑完整流水线：情绪、反讽/刷单、Trust Report、HTML 报告、历史 | `url` / `csv` / `demo` 三选一 |
| `review_xhs` | 小红书笔记 + 评论 + 图片文字 → 六章报告（总览、情绪与可信度、痛点、改进、选题、内容生产包） | `keyword` / `user` / `links` / `run_dir` 四选一 |
| `review_susu` | 采集目录 → susu-insight 观众认知、讨论主题、选题与代表评论（离线 HTML） | `run_dir` / `analysis` 二选一，`use_llm` 默认 true |
| `review_xhs_status` | 采集端是否可用、登录状态、cookie 剩余天数 | 无 |
| `review_trust_report` | 只算统计信号，不调大模型 | `csv` |
| `review_history` | 查看或清空历史（清空要 `clear: true, yes: true`） | `limit` / `clear` / `yes` |
| `review_doctor` | 依赖、模型配置、目录、采集后端、小红书登录、数据库 | 无 |

## 安装

1. 本机先装好 ReviewAgent（见仓库根 README）。默认路径 `E:\DeepSeek\review-agent`，虚拟环境 `.venv`。
2. 把插件包链进 profile 的 node_modules（实体留在 E 盘）：

```powershell
New-Item -ItemType Junction -Path 'C:\Users\<你>\.dsh\profiles\desktop\node_modules\dsh-review-agent' -Target 'E:\DeepSeek\review-agent\plugins\dsh-review-agent'
```

3. 在 profile 的 `cordis.patch.yml` 追加：

```yaml
- id: review-agent
  name: dsh-review-agent
  config:
    pythonPath: 'E:\DeepSeek\review-agent\.venv\Scripts\python.exe'
    workdir: 'E:\DeepSeek\review-agent'
    timeoutMs: 900000
```

4. 重载或重启 DSH。插件在启动时装配，工具出现在下一次会话。

## 配置

| 字段 | 默认 | 说明 |
|------|------|------|
| `pythonPath` | `E:\DeepSeek\review-agent\.venv\Scripts\python.exe` | 装了 reviewagent 的解释器 |
| `workdir` | `E:\DeepSeek\review-agent` | 子进程工作目录；`.env` 与 `data/` 相对这里 |
| `timeoutMs` | `900000` | 单次工具调用上限，毫秒 |
| `graceMs` | `3000` | 超时后强制结束进程的宽限 |

## 错误与排查

工具失败时抛出中文错误，带 `ErrorType：说明 + 下一步提示`：

- `LLMNotConfigured`：`.env` 或 `REVIEWAGENT_API_KEYS` 没配 Key。
- `XhsLoginRequired`：搜索与博主主页要扫码，先跑 `reviewagent xhs --keyword ...` 或 `xhs_batch.py login`。
- `XhsUnavailable`：xiaohongshu-mcp 后端缺失，装好后 `review_xhs_status` 会变成可用。
- 桥返回非 JSON：多半是 Python 路径错、依赖没装或脚本被改坏，用 `review_doctor` 先看。

自检脚本：

```powershell
node E:\DeepSeek\review-agent\plugins\dsh-review-agent\verify.mjs
```

## 边界

- 采集默认关闭（`REVIEWAGENT_ENABLE_SCRAPING=0`）；开启前确认目标站点的使用条款。
- 小红书采集只读：不发布、不点赞、不评论、不关注。登录 cookie 留在本机。
- 痛点与选题都由模型生成，但每条必须挂原文链接；模型给出的推断不能写成已证实事实。
