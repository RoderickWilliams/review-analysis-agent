# -*- coding: utf-8 -*-
"""命令行入口：`reviewagent <command>`。

命令：
    reviewagent analyze --url <商品链接> | --csv <文件>   采集/导入并全链路分析
    reviewagent demo                                     5 条演示评论
    reviewagent app [--port 8501]                        启动 Streamlit 界面
    reviewagent serve [--host 127.0.0.1] [--port 8000]   启动 HTTP API
    reviewagent xhs --keyword/--user/--links | --run-dir  小红书只读采集 + 洞察分析
    reviewagent susu --run-dir <采集目录>                 susu-insight 观众认知与选题报告
    reviewagent eval [--dataset 文件] [--baseline rules|none]  跑标注集评测，输出指标 JSON
    reviewagent history [--limit N] [--clear --yes]       查看/清理历史
    reviewagent doctor                                   环境自检

兼容旧入口：`python main.py --url/--csv/--demo/--web`。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from reviewagent import __version__, config


def _fail(message: str) -> int:
    print(f"错误: {message}", file=sys.stderr)
    return 2


# ── 命令实现 ──────────────────────────────────────────────────

def cmd_analyze(args: argparse.Namespace) -> int:
    from reviewagent.pipeline import analyze_reviews, collect_reviews, load_csv_reviews, summarize

    if not config.is_llm_configured():
        return _fail(
            "未配置 API Key。请设置环境变量 REVIEWAGENT_API_KEYS"
            "（或 OPENAI_API_KEY / DEEPSEEK_API_KEY），或在 .env 中配置。"
        )
    config.print_config_status()

    if args.url:
        print(f"\n[采集] 正在从 {args.url} 采集评论（最多 {args.max_reviews} 条）...")
        reviews, product_name = collect_reviews(args.url, max_reviews=args.max_reviews)
        source, platform, product_url = "url", "", args.url
    elif args.csv:
        reviews, product_name = load_csv_reviews(args.csv)
        source, platform, product_url = "csv", "", ""
    else:
        return _fail("请用 --url 或 --csv 指定数据来源")

    if not reviews:
        return _fail("未获取到评论数据")

    result = analyze_reviews(
        reviews, product_name, source=source, platform=platform, product_url=product_url
    )
    print(summarize(result))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from reviewagent.pipeline import DEMO_PRODUCT, DEMO_REVIEWS, analyze_reviews, summarize

    if not config.is_llm_configured():
        return _fail("未配置 API Key，演示模式同样需要真实调用 LLM。")
    config.print_config_status()
    result = analyze_reviews(DEMO_REVIEWS, DEMO_PRODUCT, source="demo")
    print(summarize(result))
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    """启动 Streamlit 界面（在数据根目录下运行，保证 static/ 可被挂载）。"""
    app_py = Path(__file__).resolve().parent / "app.py"
    env = dict(os.environ)
    env.setdefault("REVIEWAGENT_HOME", str(config.HOME_DIR))
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_py), "--server.port", str(args.port)]
    if args.headless:
        cmd += ["--server.headless", "true"]
    print("启动 Streamlit 界面：", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(config.HOME_DIR), env=env)


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        return _fail("缺少 uvicorn，请执行 pip install -e .[api]")
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not os.environ.get("REVIEWAGENT_ACCESS_TOKEN"):
        return _fail("非本机监听需要设置 REVIEWAGENT_ACCESS_TOKEN；本机使用 --host 127.0.0.1")
    from reviewagent.analysis_tasks import recover_interrupted

    recovered = recover_interrupted()
    if recovered:
        print("已将 %d 个中断的旧任务标记为可继续" % len(recovered))
    print(f"启动工作台：http://{args.host}:{args.port}/app/（文档 /docs）")
    uvicorn.run("reviewagent.http_api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    from reviewagent.history_manager import clear_all_history, load_history

    if args.clear:
        if not args.yes:
            return _fail("清空历史需要 --yes 确认")
        count = clear_all_history()
        print(f"已清空 {count} 条历史记录")
        return 0

    records = load_history()
    if not records:
        print("暂无历史记录")
        return 0
    for rec in records[: args.limit]:
        print(
            f"{rec.get('id')}  {rec.get('timestamp_display', rec.get('timestamp', ''))}  "
            f"{rec.get('product_name', '')}  评论 {rec.get('review_count', 0)} 条  "
            f"可信度 {rec.get('avg_trust_score', '-')}"
        )
    print(f"共 {len(records)} 条（显示 {min(len(records), args.limit)} 条）")
    return 0


def cmd_xhs(args: argparse.Namespace) -> int:
    from reviewagent.pipeline import analyze_xhs, summarize_xhs
    from reviewagent.scrapers import xhs_reader

    if args.run_dir:
        try:
            capture = xhs_reader.load_run(args.run_dir)
        except xhs_reader.XhsError as exc:
            return _fail(str(exc))
    else:
        if not (args.keyword or args.user or args.links):
            return _fail("请用 --keyword / --user / --links 指定采集目标，或用 --run-dir 复用已有采集目录")
        if not config.is_llm_configured() and not args.capture_only:
            return _fail(
                "未配置 API Key，采集后无法做情绪与痛点分析。"
                "要只采集请加 --capture-only；要分析请设置 REVIEWAGENT_API_KEYS。"
            )
        config.print_config_status()
        try:
            capture = xhs_reader.capture(
                links=args.links,
                keyword=args.keyword or "",
                user=args.user or "",
                limit=args.limit,
                with_comments=not args.no_comments,
                out_dir=args.out,
                sort=args.sort or "",
                sweep=args.sweep,
                note_type=args.note_type or "",
                with_ocr=False if args.no_ocr else None,
                max_images=args.max_images,
            )
        except xhs_reader.XhsLoginRequired as exc:
            print(f"需要登录：{exc}", file=sys.stderr)
            return 2
        except xhs_reader.XhsError as exc:
            return _fail(str(exc))

    print(xhs_reader.summarize(capture))
    if args.capture_only:
        print(f"\n采集目录: {capture.get('run_dir', '')}")
        return 0
    if not config.is_llm_configured():
        return _fail("未配置 API Key，无法分析；本次采集结果已保存在上面的目录，可稍后用 --run-dir 继续。")

    result = analyze_xhs(
        capture,
        source="cli",
        save_history=not args.no_history,
    )
    print(summarize_xhs(result))
    return 0


def cmd_susu(args: argparse.Namespace) -> int:
    from reviewagent.insights import susu
    from reviewagent.scrapers import xhs_reader

    if args.analysis:
        try:
            analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return _fail(f"读不了 analysis JSON: {exc}")
        try:
            rendered = susu.render_analysis(analysis, out_dir=args.out_dir)
        except (OSError, ValueError, KeyError) as exc:
            return _fail(f"analysis JSON 没通过技能校验: {exc}")
        print(f"susu-insight 报告: {rendered['html_path']}")
        print(f"统计: {rendered['json_path']}")
        return 0

    if not args.run_dir:
        return _fail("请用 --run-dir 指定采集目录，或用 --analysis 渲染已有 analysis.json")
    try:
        capture = xhs_reader.load_run(args.run_dir)
    except xhs_reader.XhsError as exc:
        return _fail(str(exc))

    use_llm = not args.no_llm
    if use_llm and not config.is_llm_configured():
        print("提示: 未配置 API Key，本次不调用模型，只按笔记自动归类。", file=sys.stderr)
        use_llm = False
    try:
        result = susu.analyze_capture(
            capture,
            account_name=args.account or "",
            out_dir=args.out_dir,
            use_llm=use_llm,
        )
    except FileNotFoundError as exc:
        return _fail(str(exc))
    print(susu.summarize(result))
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from datetime import datetime

    from reviewagent.eval import evaluate_dataset

    dataset = Path(args.dataset)
    if not dataset.exists():
        return _fail(f"数据集不存在: {dataset}")
    try:
        report = evaluate_dataset(
            dataset,
            predictions_path=args.predictions,
            baseline=args.baseline,
        )
    except ValueError as exc:
        return _fail(str(exc))

    out = Path(args.out) if args.out else (
        Path(config.OUTPUT_DIR) / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"数据集: {report['dataset']}（{report['samples']} 条）")
    print(f"基线: {report['baseline']}")
    for dimension, label in (("sentiment", "情绪"), ("validity", "有效性")):
        metrics = report.get("dimensions", {}).get(dimension)
        if not metrics:
            print(f"  {label}: 无标注，跳过")
            continue
        print(
            f"  {label}: accuracy {metrics['accuracy']:.3f}  "
            f"macro-F1 {metrics['macro_f1']:.3f}  "
            f"weighted-F1 {metrics['weighted_f1']:.3f}"
        )
    print(f"结果已写入: {out}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """环境自检：依赖、配置、数据库、OCR/浏览器可用性。"""
    print(f"ReviewAgent {__version__}")
    print(f"Python {sys.version.split()[0]}  ({sys.executable})")
    config.print_config_status()

    checks = {
        "openai": "LLM 客户端",
        "pandas": "数据处理",
        "numpy": "数值计算",
        "sklearn": "TF-IDF / 聚类",
        "streamlit": "Web 界面",
        "fastapi": "HTTP API",
        "uvicorn": "HTTP API 服务器",
        "jieba": "中文分词",
        "pytesseract": "OCR（可选）",
        "playwright": "浏览器采集（可选）",
        "DrissionPage": "浏览器采集（可选）",
        "scrapling": "采集后端（可选）",
        "curl_cffi": "Scrapling fetchers（可选）",
    }
    print("\n依赖检查:")
    missing_required = []
    for module, label in checks.items():
        ok = importlib.util.find_spec(module) is not None
        print(f"  {'OK  ' if ok else 'MISS'} {module:<14} {label}")
        if not ok and module in ("openai", "pandas", "numpy", "sklearn"):
            missing_required.append(module)

    from reviewagent import store

    print(f"\n数据库: {store.db_path()}（{store.count_history()} 条历史记录）")
    print(f"数据目录: {config.DATA_DIR}")
    print(f"输出目录: {config.OUTPUT_DIR}")
    print(f"缓存目录: {config.CACHE_DIR}")

    from reviewagent.scrapers import scrapling_backend

    print(
        f"\n采集: {'开启' if config.SCRAPING_ENABLED else '关闭'}"
        f" / 后端 {config.SCRAPER_BACKEND}"
    )
    print(f"  Scrapling 解析: {'可用' if scrapling_backend.available() else '未安装'}")
    print(
        "  Scrapling 抓取: "
        + ("可用" if scrapling_backend.fetchers_available() else "缺少 fetchers 依赖")
    )
    print(f"  选择器配置: {config.SCRAPLING_SELECTORS or '未配置'}")

    from reviewagent.scrapers import xhs_reader

    try:
        xhs_status = xhs_reader.status() if getattr(args, "with_sources", False) else {"available": False, "hint": "默认离线检查；--with-sources 才连接采集端"}
    except Exception as exc:  # 自检不因采集端异常中断
        xhs_status = {"available": False, "hint": f"{type(exc).__name__}: {exc}"}
    print(f"  小红书采集: {'可用' if xhs_status.get('available') else '不可用'}")
    if xhs_status.get("available"):
        print(f"    登录状态: {'已登录' if xhs_status.get('logged_in') else '未登录（搜索与主页需要扫码）'}")
        print(f"    采集脚本: {xhs_reader.xhs_script()}")
    else:
        print(f"    提示: {xhs_status.get('hint', '')}")

    if not config.is_llm_configured():
        print("\nLLM: 未配置 API Key（分析功能不可用，界面与采集仍可浏览）")
    else:
        print(f"\nLLM: 已配置 {len(config.API_KEYS)} 个 Key，模型 {config.MODEL}")

    return 1 if missing_required else 0


# ── 参数解析 ──────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reviewagent",
        description="ReviewAgent —— 跨平台用户反馈智能分析 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--version", action="version", version=f"ReviewAgent {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("analyze", help="采集/导入评论并全链路分析")
    p.add_argument("--url", help="商品链接（自动采集）")
    p.add_argument("--csv", help="CSV 文件路径")
    p.add_argument("--max-reviews", type=int, default=50, help="最大采集量（默认 50）")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("demo", help="用 5 条演示评论跑通全链路")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("app", help="启动 Streamlit 界面")
    p.add_argument("--port", type=int, default=8501)
    p.add_argument("--headless", action="store_true")
    p.set_defaults(func=cmd_app)

    p = sub.add_parser("serve", help="启动 HTTP API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("xhs", help="小红书只读采集 + 痛点/改进/选题分析")
    p.add_argument("--keyword", help="搜索关键词（需要登录）")
    p.add_argument("--user", help="博主主页链接（需带 xsec_token，需要登录）")
    p.add_argument("--links", nargs="+", help="一篇或多篇笔记链接（单篇需带 xsec_token）")
    p.add_argument("--run-dir", help="复用已有采集目录，跳过采集")
    p.add_argument("--limit", type=int, default=20, help="最多读几篇（默认 20，上限 50）")
    p.add_argument("--sort", help="排序：综合 / 最新 / 最多点赞 / 最多评论 / 最多收藏")
    p.add_argument("--sweep", action="store_true", help="轮换四种排序再合并")
    p.add_argument("--note-type", help="只要 视频 或 图文")
    p.add_argument("--out", help="采集输出目录")
    p.add_argument("--no-comments", action="store_true", help="不读评论（只看笔记正文与图片）")
    p.add_argument("--no-ocr", action="store_true", help="不识别图片文字")
    p.add_argument("--max-images", type=int, default=None, help="每篇最多下载几张图")
    p.add_argument("--capture-only", action="store_true", help="只采集，不分析")
    p.add_argument("--no-history", action="store_true", help="不写入历史记录")
    p.set_defaults(func=cmd_xhs)

    p = sub.add_parser("susu", help="把采集目录转成 susu-insight 观众认知与选题报告")
    p.add_argument("--run-dir", help="小红书采集目录（含 notes.json）")
    p.add_argument("--analysis", help="已有 analysis.json，只渲染不重新分析")
    p.add_argument("--account", help="报告里显示的账号名，默认取首篇笔记作者")
    p.add_argument("--out-dir", help="报告输出目录，默认 output/susu")
    p.add_argument("--no-llm", action="store_true", help="不调用模型，只做确定性归类")
    p.set_defaults(func=cmd_susu)

    p = sub.add_parser("eval", help="在标注集上评测规则基线或模型预测")
    p.add_argument("--dataset", default=str(Path("data") / "eval" / "sample.jsonl"), help="标注集路径（JSONL/JSON）")
    p.add_argument("--baseline", choices=["rules", "none"], default="rules", help="不提供预测时的基线")
    p.add_argument("--predictions", help="模型预测 JSON（pipeline 结果或 [{sentiment,validity}]）")
    p.add_argument("--out", help="指标输出文件（默认 output/eval_<时间>.json）")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("history", help="查看或清理历史记录")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--clear", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("doctor", help="环境自检（默认离线）")
    p.add_argument("--with-sources", action="store_true", help="同时连接采集端查看状态")
    p.set_defaults(func=cmd_doctor)

    return parser


def _legacy_main(argv: List[str]) -> int:
    """兼容旧参数：--url / --csv / --demo / --web / --max-reviews。"""
    parser = argparse.ArgumentParser(prog="reviewagent", description="ReviewAgent（兼容旧入口）")
    parser.add_argument("--url")
    parser.add_argument("--csv")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--max-reviews", type=int, default=50)
    args = parser.parse_args(argv)

    if args.web:
        return cmd_app(argparse.Namespace(port=8501, headless=False))
    if args.url or args.csv:
        return cmd_analyze(args)
    return cmd_demo(args)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    legacy_flags = {"--url", "--csv", "--demo", "--web", "--max-reviews"}
    # 只看第一个参数：`analyze --url/--csv/--max-reviews` 是新子命令，不能因参数里出现
    # 旧旗标就整体退回旧解析器。
    if argv and argv[0].split("=", 1)[0] in legacy_flags:
        return _legacy_main(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
