"""本地启动 ReviewAgent 工作台（源码运行）。

用法：python run_local.py [--port 64628]
数据目录固定为项目下的 runtime/；不读取 .env 中的模型密钥，模型在本机界面里配置。
"""
import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=64628)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    for name in ("REVIEWAGENT_API_KEYS", "LLM_API_KEYS", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "REVIEWAGENT_ACCESS_TOKEN"):
        os.environ[name] = ""
    os.environ.update(
        REVIEWAGENT_HOME=str(RUNTIME),
        REVIEWAGENT_DATA_DIR=str(RUNTIME / "data"),
        REVIEWAGENT_OUTPUT_DIR=str(RUNTIME / "output"),
        REVIEWAGENT_CACHE_DIR=str(RUNTIME / "cache"),
        REVIEWAGENT_DB_PATH=str(RUNTIME / "data/reviewagent.db"),
        REVIEWAGENT_ENABLE_SCRAPING="1",
        REVIEWAGENT_BROWSER="chrome",
        REVIEWAGENT_BROWSER_NETWORK="direct",
    )
    sys.path.insert(0, str(ROOT / "src"))
    os.chdir(ROOT)
    (RUNTIME / "server-owner.json").write_text(
        json.dumps({"pid": os.getpid(), "script": str(ROOT / "run_local.py"), "port": args.port}),
        encoding="utf-8",
    )
    import uvicorn

    uvicorn.run("reviewagent.http_api:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
