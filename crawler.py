#!/usr/bin/env python
"""ReviewAgent 独立采集工具（命令行）。

从商品/笔记链接采集真实评论，输出 JSON，不启动工作台界面。

示例：
    python crawler.py --url "https://detail.tmall.com/item.htm?id=568742960823" --limit 300 --out reviews.json
    python crawler.py --url "https://item.jd.com/100012043978.html" --platform jd --out jd.json

退出码：0 成功；2 平台暂停/失败（原因写在输出的 error 字段）；1 参数或环境错误。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def platform_from_url(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith("jd.com"):
        return "jd"
    if host.endswith(("tmall.com", "taobao.com", "tb.cn")):
        return "tmall" if host.startswith("detail.") else "taobao"
    if host.endswith(("xiaohongshu.com", "xhslink.com", "xhslink.cn")):
        return "xhs"
    raise SystemExit("无法从链接判断平台，请用 --platform 指定 jd / taobao / tmall / xhs")


def main() -> int:
    parser = argparse.ArgumentParser(description="采集平台真实评论并输出 JSON")
    parser.add_argument("--url", required=True, help="商品或笔记链接（HTTPS）")
    parser.add_argument("--platform", choices=["auto", "jd", "taobao", "tmall", "xhs"], default="auto")
    parser.add_argument("--limit", type=int, default=300, help="单链接最多读取条数（默认 300）")
    parser.add_argument("--out", default="reviews.json", help="输出文件路径")
    parser.add_argument("--home", default=str(ROOT / "runtime"), help="数据与浏览器配置目录")
    parser.add_argument("--browser", default="chrome", choices=["chrome", "edge", "firefox", "auto"])
    parser.add_argument("--quiet", action="store_true", help="不打印过程状态")
    args = parser.parse_args()

    if not args.url.startswith("https://"):
        print("只支持 https 链接", file=sys.stderr)
        return 1

    os.environ.setdefault("REVIEWAGENT_HOME", args.home)
    os.environ.setdefault("REVIEWAGENT_BROWSER", args.browser)
    os.environ.setdefault("REVIEWAGENT_BROWSER_NETWORK", "direct")
    os.environ.setdefault("REVIEWAGENT_ENABLE_SCRAPING", "1")
    sys.path.insert(0, str(ROOT / "src"))

    from reviewagent.browser_collection import CollectionPaused, collect_source
    from reviewagent.browser_session import platform_key

    platform = args.platform if args.platform != "auto" else platform_from_url(args.url)

    def state(event):
        if not args.quiet:
            print("[" + str(event.get("platform", "")) + "] " + str(event.get("message", "")), file=sys.stderr)

    def cancelled():
        return False

    payload = {"url": args.url, "platform": platform, "collected_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    try:
        rows = collect_source({"url": args.url, "platform": platform}, args.limit, cancelled, on_state=state)
    except CollectionPaused as exc:
        payload.update(status="paused", code=exc.code, error=str(exc), reviews=[])
        _write(args.out, payload)
        print("采集暂停：" + str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # 环境或驱动异常
        payload.update(status="failed", code=type(exc).__name__, error=str(exc)[:300], reviews=[])
        _write(args.out, payload)
        print("采集失败：" + type(exc).__name__ + " " + str(exc)[:200], file=sys.stderr)
        return 2

    payload.update(status="ok", count=len(rows), facts=getattr(rows, "facts", {}) or {}, reviews=list(rows))
    _write(args.out, payload)
    print("已采集 %d 条真实评论 → %s" % (len(rows), args.out))
    return 0


def _write(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
