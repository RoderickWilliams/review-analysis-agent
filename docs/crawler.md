# 命令行采集工具（crawler.py）

不启动工作台界面，直接从一个商品链接采集真实评论，输出 JSON。适合脚本、批处理、给下游分析程序喂数据。

## 用法

```cmd
venv\Scripts\python.exe crawler.py --url "https://detail.tmall.com/item.htm?id=568742960823" --limit 300 --out reviews.json
```

参数：

| 参数 | 说明 |
| --- | --- |
| `--url` | 商品/笔记链接，只接受 https |
| `--platform` | `auto`（默认，按域名判断）或 jd / taobao / tmall / xhs |
| `--limit` | 单链接最多读取条数，默认 300 |
| `--out` | 输出 JSON 路径，默认 reviews.json |
| `--home` | 数据与专用浏览器配置目录，默认项目下 runtime/ |
| `--browser` | chrome（默认）/ edge / firefox / auto |
| `--quiet` | 不打印过程状态 |

## 输出

```json
{
 "url": "...",
 "platform": "tmall",
 "status": "ok",
 "count": 33,
 "facts": {"displayed": 33, "folded": 22, "selected": 14},
 "reviews": [{"review_text": "...", "review_date": "2026-10-08", "reviewer_name": "匿名买家", "sku": "...", "comment_id": "..."}]
}
```

失败时 `status` 为 `paused` 或 `failed`，带 `code` 与 `error`；退出码 2。
平台只有星级、正文是占位文案的评价不会写进 `reviews`，数量在 `facts.rating_only`。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 采集完成 |
| 1 | 参数错误（非 https、平台无法判断） |
| 2 | 平台暂停或采集失败（登录、限流、精简页面、导航失败等） |

## 与工作台的关系

- 共用 `src/reviewagent` 的采集实现：专用浏览器、可信点击、天猫分页接口、去重与字段归一。
- 不依赖 FastAPI、不写数据库、不调用模型，因此可以单独拷到别的机器上用同一套 venv 运行。
- 登录状态仍保存在 `--home` 下的专用浏览器配置里；首次使用需要人工完成扫码或身份校验。

## 边界

- 平台限流时会返回 `degraded_page`（只给购买区、不下发评价模块），此时不循环重试，等一段时间再跑。
- 验证码/身份校验必须人工完成；工具不破解、不轮换 Cookie。
- 只做只读采集，不发布、不互动、不改商品数据。
