"""Frozen desktop entry; user data stays outside the application installation."""
import os
from pathlib import Path

def main():
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ReviewAgent"
    os.environ.setdefault("REVIEWAGENT_HOME", str(root))
    import uvicorn
    print("ReviewAgent: http://127.0.0.1:8000/app/ — Ctrl+C 停止服务")
    uvicorn.run("reviewagent.http_api:app", host="127.0.0.1", port=8000, workers=1)

if __name__ == "__main__":
    main()
