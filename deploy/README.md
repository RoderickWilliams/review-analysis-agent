# 本地部署

三种部署形态共用同一份 `src/reviewagent`。

## Windows 本机（推荐）

```powershell
# 从仓库根执行
powershell -NoProfile -ExecutionPolicy Bypass -File deploy\setup.ps1
# 只装 API（不要界面、采集与 OCR）
powershell -NoProfile -ExecutionPolicy Bypass -File deploy\setup.ps1 -Minimal
# 开发环境 + Scrapling 底座 + 跑测试
powershell -NoProfile -ExecutionPolicy Bypass -File deploy\setup.ps1 -WithDev -WithScrapling
```

脚本做的事：检查 Python ≥3.10 → 建 `.venv` → 默认 `pip install -e ".[api,app,ocr,scrape]"`（`-Minimal` 只装 `api`，`-WithScrapling` 追加 `scrapling`，`-WithDev` 追加 `dev`）→ 复制 `.env.example` 为 `.env` → 跑 `reviewagent doctor`。

装完启动：

```powershell
.venv\Scripts\reviewagent.exe serve --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000/docs 看接口，`GET /healthz` 应返回 ok。

## Docker

```bash
cp .env.example .env      # 填 Key
docker compose -f deploy/docker-compose.yml up -d --build
curl http://127.0.0.1:8000/healthz
```

镜像只装 API 依赖与非图形 OCR；要跑浏览器采集，另建带 Chromium 的镜像或在宿主机跑采集后把 `run_dir` 交给容器分析。

数据落在 `data/` 与 `output/`（compose 已挂载），模板缓存进命名卷 `review-agent-cache`。

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `REVIEWAGENT_API_KEYS` | 空 | 逗号分隔多 Key，轮换 |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | 空 / api.deepseek.com / deepseek-chat | 单 Key 模式 |
| `REVIEWAGENT_HOME` | 仓库根 | 数据、输出、模板目录的根 |
| `REVIEWAGENT_ENABLE_SCRAPING` | 0 | 淘宝/京东采集开关 |
| `REVIEWAGENT_SCRAPER_BACKEND` | legacy | `legacy` 或 `scrapling` |
| `REVIEWAGENT_API_KEYS` | 空 | 也接受 JSON 数组 |
| `REVIEWAGENT_LLM_CACHE` | 1 | 设 0 关闭模型调用缓存 |

完整清单见仓库根 `.env.example`。

## 校验

```powershell
.venv\Scripts\python.exe -m pytest -q          # 全量测试
.venv\Scripts\python.exe -m reviewagent doctor  # 环境自检
.venv\Scripts\python.exe -m reviewagent demo    # 5 条演示评论跑通全链路
```
