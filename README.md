# ReviewAgent · 评论研究工作台

本地运行的中文评论分析工具：导入原文，分析情绪与内容疑点，提炼有原句支持的痛点，再整理改进建议和行动计划。

**本次升级为源码实施状态，尚未进行本轮测试、构建或界面验收。** 当前行为与边界以 [升级交付说明](docs/upgrade-implementation.md) 为准；[v2 产品规格](docs/v2-product-spec.md) 包含规划能力，不代表全部已实现。

## 默认工作台

界面参考用户指定的 Vesper / oil-ui 设计语言：浅灰绿侧栏、白色工作区、细边框、紧凑表格、绿色强调。保留浅色、深色和系统主题。

| 区域 | 功能 |
| --- | --- |
| 总览 | 实际样本量、成功数量、需复核数量、模型平均分、原始发布日期分布、来源缺口 |
| 评论库 | 全文搜索、来源与状态筛选、排序、分页、原文证据与逐步结果 |
| 用户洞察 | 原句校验后的痛点、改进方向、选题与内容生产草稿 |
| 行动计划 | 从改进建议整理任务，编辑负责人、截止日期、状态和验证指标 |
| 分析历史 | 恢复完整输入、评论、结果和进度；进程中断后手动继续 |

旧版 A：/app-classic/；旧版 B：/app-redesign/。旧 Streamlit 入口仍为 reviewagent app。新增功能以默认 /app/ 为准。

## Windows 安装与启动

需要 Python 3.10 或更新版本。在项目根目录使用 cmd：

~~~cmd
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[api,import]"
.venv\Scripts\python.exe -m reviewagent serve --host 127.0.0.1 --port 8000
~~~

打开 http://127.0.0.1:8000/app/。也可先运行 deploy\setup.cmd，再运行 start.bat。安装脚本不会自动执行测试或调用真实模型。

首次使用：新建分析 → 导入 CSV / XLSX / JSON / TXT 或粘贴原文 → 确认字段映射 → 开始深度分析。创建草稿和导入不调用模型；输入平台链接创建对象时会尝试读取公开页面。没有模型配置时可以保存数据，配置后再分析。

Linux / macOS 使用对应虚拟环境中的 python -m pip 和 python -m reviewagent 命令。容器与桌面打包见 [部署说明](deploy/README.md)。

## 模型配置

支持 OpenAI 兼容 Chat Completions API。在运行环境或本地 .env 中配置。不要把真实 Key 放进仓库或分发包。

| 变量 | 说明 |
| --- | --- |
| REVIEWAGENT_API_KEYS | 逗号分隔列表或 JSON 数组；同一组 Key 使用同一个网关 |
| REVIEWAGENT_MODEL | 模型名称 |
| REVIEWAGENT_BASE_URL | 兼容网关地址，省略时使用默认配置 |
| DEEPSEEK_API_KEY / DEEPSEEK_MODEL / DEEPSEEK_BASE_URL | DeepSeek 单 Key 配置；仅配置 DeepSeek Key 时默认 deepseek-chat 与 api.deepseek.com |
| REVIEWAGENT_HOME | 用户数据根目录，开发版默认仓库根 |
| REVIEWAGENT_ACCESS_TOKEN | 服务访问令牌；非本机监听时必须配置 |
| REVIEWAGENT_ENABLE_SCRAPING | 1 才启用采集任务，默认 0 |

通用配置优先于供应商别名。Key 在认证、配额或限流失败时按请求尝试其他已配置通道；响应错误不展示 Key。完整示例见 [.env.example](.env.example)。

模型调用会向你配置的供应商发送评论文本。逐条分析一般包含三个模型阶段，痛点与改进还会产生批次请求。只有点击开始分析或显式调用分析接口才执行。取消后续请求不会撤销已发出的请求，也无法退回其费用。

## 输入与结果口径

- 工作台每份研究最多 500 条；文件最多 8 MB，Excel 解压后最多 40 MB。Excel 支持由可选 import 扩展提供。
- 评分仅接受 1–5 整数或空值。未知日期与评分不补造；导入时间单独保存。
- 正面、负面、中性为互斥三类；反讽是独立表达标志。失败和未完成条目不计入成功样本的情绪比例或可信度平均值。
- 负面、低星和反讽不自动构成真实性疑点；评分与文本矛盾作为一致性提示，不直接作真实性扣分。
- 模型可信度与规则 Trust Report 分开呈现，均不能认证作者、购买记录或 AI 来源。规则区间未经真实性概率校准。
- 痛点最多覆盖 200 条成功评论，超出时均匀抽样并记录范围；引语必须在对应原文中找到。选题、改进和内容包属于草稿或建议。
- 导出包括完整原文 CSV、行动 CSV、离线 HTML 与工作台 JSON 快照；HTML 无 CDN，文本做转义，CSV 处理公式前缀。

## 采集边界

复用现有京东、淘宝和小红书适配器。轻量、标准、深度、自定义档位实际控制来源及评论上限；时间窗优先，不足时最多补充 30 条更早样本。未取得评论时记录缺口，不制造样本。

公开同款搜索只尝试从京东与淘宝页面提取实际商品链接；受登录、页面变化或风控影响时可能返回空结果。小红书需要已有采集端，自动跨平台确认同款尚未完整实现。没有价格与销量证据时不按这些指标排序。本轮没有执行真实平台采集或登录。

## 任务与数据

SQLite 保存请求、原文、逐条结果与进度。刷新后可恢复；重启时未结束任务标记为中断，需要显式继续。成功结果只在原文、模型、提示词版本和同批相似度上下文仍匹配时复用。

使用一个服务进程、一个 Uvicorn worker。当前调度器是本地线程池，适合单工作区；多实例分布式调度、多用户角色和组织隔离尚未实现。

开发版默认写入 data、output、.cache，可通过路径环境变量指定新目录。桌面打包版默认使用用户 LocalAppData/ReviewAgent。旧 history.json 默认不自动迁移；迁移前先备份整个数据目录，再显式设置 REVIEWAGENT_MIGRATE_LEGACY_HISTORY=1。

## API 与兼容入口

API 文档位于 /docs。主要接口见 [升级交付说明](docs/upgrade-implementation.md)。

~~~cmd
reviewagent analyze --csv reviews.csv
reviewagent serve --host 127.0.0.1 --port 8000
reviewagent app
reviewagent history --limit 20
~~~

CLI analyze 和 demo 会调用真实模型。doctor 默认离线检查；加 --with-sources 才连接采集端。DSH 插件和已有 Agent Skill 保留，接口扩展不要求重新安装它们。

## 验证状态

本次升级新增离线回归用例、前端脚本语法验证入口和 wheel 资源边界脚本，**均未在本轮执行**。手动 CI 仅 workflow_dispatch，未触发也未上传制品。

获得一次约定范围的检查批准后，可执行离线 pytest、脚本语法、wheel 资源检查及假模型隔离 UI 流程。真实模型质量需要独立标注评测；现有 44 条样例与假模型测试不能证明生产准确率。

项目采用 [MIT License](LICENSE)。
