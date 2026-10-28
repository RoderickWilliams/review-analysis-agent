# PLATFORM-001 回执 — 三平台真实链接测试

- 任务 ID：PLATFORM-001
- 执行：DSH 会话 session-e15676c3-5681-4edb-b0e1-8c2c33354dbe
- 时间：2026-10-28 22:49 – 23:08（Asia/Shanghai）
- 基线：`codex/reviewagent-upgrade` @ `e339339`；工作树另有 Codex 尚未提交的前端改动（webui/*、http_api.py），本对话未触碰、未提交。
- 结论：淘宝、京东被平台限流/频控挡住；小红书取得 10 条真实评论。三端均未调用模型，费用 0。未 push。

## 逐平台结果

### 1. 淘宝 / 天猫 — 部分受阻（平台返回精简页）

| 项 | 内容 |
| --- | --- |
| 输入 | 用户淘宝分享文案（e.tb.cn/h.jUVuziuunaR8cSd） |
| 记录 ID | `ra_417f4ec326034bdb`（测试期间被外部重置置为 trashed，见“异常事件”） |
| 开始 / 结束 | 22:49:56 / 22:52:00 |
| 落地 URL | `detail.tmall.com/item.htm`；短链 HTML 返回 200，正文含 `id=568742960823` |
| 商品身份 | 568742960823，标题「Folkmanis小浣熊玩偶娃娃毛绒婴儿仿真玩具礼物早教手偶抱睡公仔」，￥408，与分享文案一致 |
| 页面显示数 | 未知（评价模块未下发） |
| 采集原始 / 去重 / 正文 / 星级占位 | 0 / 0 / 0 / 0 |
| 失败码 | `comment_section_not_loaded`：等待 90 秒后评价区未出现；页面诊断 `text_length=240`，只有购买区 |
| 说明 | 当时运行的服务进程启动于 19:13，早于 `degraded_page` 识别；源码已能区分“精简页”，但按“同一阻碍不重复请求”未再复测 |
| 代码修改 | 无（本平台） |
| 费用 | 0 |

### 2. 京东 — 受阻（PC 频控页 + 接口限流），归属无法核对

| 项 | 内容 |
| --- | --- |
| 输入 | 用户京东分享文案（3.cn/39-kAvQC） |
| 记录 ID | `ra_bfbe71167985448d`（被外部重置置为 trashed） |
| 开始 / 结束 | 22:54:09 / 22:58:56（主动取消） |
| 落地 URL | `https://item.jd.com/100394190476.html` |
| 商品身份 | 100394190476，标题「叩素钥匙扣挂件豆袋安抚玩偶公仔捏捏陪伴手偶毛绒玩具娃娃生日礼物」，与「豆袋安抚狐狸挂件」为同款口径，但未取得规格证据 |
| 页面 | 落到 `pc-frequent-pro.pf.jd.com`（PC频控页），提示“暂时无法展示该商品的信息，请稍后重试” |
| 公开接口 | `club.jd.com/comment/productPageComments.action` 返回“活动太火爆，请稍微再试”（11 字节），无 JSON |
| “只看本商品” | **未到达评价区，无法勾选**；没有逐条商品 ID/SKU 可核对，因此这批评论归属记为不明，未纳入任何商品评论 |
| 采集数 | 0 |
| 代码修改 | 有：停止把未确认的同款候选自动当采集对象（详见“代码变更”） |
| 费用 | 0 |

### 3. 小红书 — 部分成功（10 条社交评论，无发布日期）

| 项 | 内容 |
| --- | --- |
| 输入 | 用户小红书分享文案（xhslink.cn/o/7zUsGv1lB2l） |
| 记录 ID | `ra_fe37d2164e3b4732`（status=partial） |
| 开始 / 结束 | 23:05:37 / 23:06:40 |
| 落地 URL | `xiaohongshu.com/discovery/item/69120b0d0000000003011c78`（分享参数原样保留） |
| 笔记 ID | 69120b0d0000000003011c78；标题为空（页面需登录，未猜测） |
| 采集方式 | 本机只读后端 `xhs_batch_reader`，关闭 OCR，不调用模型 |
| 评论数 | 10 条，去重后 10 条，全部有用户名；发布日期 0 条（后端未提供） |
| 内容类型 | `social_comment`（社交评论，**不是**已购评价） |
| 缺口 | `insufficient_reviews`：上限 300、目标 300，本次读取 10 条；页面实际总数未知 |
| 代码修改 | 有：补 `xhslink.cn` 域名（修复前该输入被判为 unknown 平台，记录 `ra_8b05ee9832244236`） |
| 费用 | 0 |

## 代码变更（仅最小后端修复）

1. **未确认候选不再自动采集**（`src/reviewagent/collection.py`、`src/reviewagent/analysis_tasks.py`）
   - 触发：京东单链接出现 25 个同款候选，采集会逐个尝试（每个带 20–40 秒冷却），任务无法在合理时间内结束。
   - 改动：没有 `selected_urls` 时只采当前对象；用户补充的链接以 `user_supplied` 标记后照常采集；显式选择逻辑不变。
   - 回归：`tests/test_source_selection.py`（3 项）；`tests/test_collection_routes.py`、`tests/test_upgrade_workbench.py` 通过（exit 0）。
2. **支持 xhslink.cn 短链**（`src/reviewagent/object_resolver.py`、`src/reviewagent/browser_collection.py`）
   - 触发：用户分享链接使用 `xhslink.cn`，原白名单只有 `xhslink.com`，被判为未知平台。
   - 回归：`tests/test_source_selection.py::test_xhslink_cn_is_recognized_as_xhs` 通过（exit 0）。
   - 修复后同一输入成功落地到笔记 ID 并取到 10 条评论。

以上均未运行全量测试（任务只要求受影响的离线回归），不能据此宣称全部通过。

## 服务与配置

- 为加载上述两处修复，服务重启 2 次（22:5x、23:0x），均先确认为 0 个活动任务。
- 重启后 `llm_configured` 由 true 变 false：**内存中的模型 Key 已清空**，本批未做任何模型调用；用户若要继续分析需重新填写。未读取或记录 Key 内容。
- 采集开关保持开启；浏览器仍为 chrome + 直连。

## 异常事件（需 Codex 知悉）

测试期间发生一次工作区重置，淘宝、京东两条记录被置为 `trashed`，API 对它们返回“分析任务不存在”。本对话未执行重置。为保住证据，我用只读 SQLite 查询从本机库中取出这两条记录 JSON 存到产物目录，未恢复、未修改任何运行中的记录。若需要它们在界面里可见，需要用户/Codex 决定是否撤销这次重置。

## 产物路径

`coordination/artifacts/PLATFORM-001/`

- `taobao.json`、`jd.json`、`xhs.json`、`xhs_before_fix.json`：恢复出的记录快照
- `summary.json`：三端摘要
- `evidence.json`：短链解析、频控页/接口原文、页面诊断与重置说明
- 无截图：窗口在任务结束时按既有逻辑关闭，未为截图重新开窗（遵守“同一阻碍不重复请求”）

## 执行过的命令（摘要）

- `git rev-parse` / `git status` / `git worktree list`（只读确认基线）
- `curl` 调 `/v1/analysis`、`/run`、`/cancel`、`/healthz` 完成建记录、采集、取消与状态轮询
- `curl -I` 与短链 HTML 解析确认淘宝商品 ID
- `curl` 调京东公开评论接口（结果为限流提示）
- `pytest tests/test_source_selection.py`、`tests/test_collection_routes.py`、`tests/test_upgrade_workbench.py`（均 exit 0）
- 只读 `sqlite3` 查询恢复两条被 trashed 的记录 JSON

## 费用

模型调用 0 次，费用 0 元；未使用 OCR、未调用付费第三方服务。

## 未完成与不确定

1. 淘宝、京东仍受平台限流，本轮没有取得任何评论；两者的失败是平台侧限制，不是“已验证通过”。
2. 京东的“只看本商品”证据未取得，评论归属问题悬空。
3. 小红书只有 10 条社交评论、无发布日期，不能当作购买评价，也没有达到 300 条上限。
4. 补充：本机存在未提交的前端改动（Codex 负责），本回执不对其做判断。
