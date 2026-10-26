# -*- coding: utf-8 -*-
"""小红书采集适配层（只读）
================================

不自研抓取：登录、xsec_token、风控与页面解析都由本机的 xhs-batch-reader 技能负责
（xiaohongshu-mcp 只读后端 + 本地 OCR），这里只做三件事：

1. 用固定 argv 调技能 CLI 的 `read` / `status`，不经 shell、不拼接字符串；
2. 把 `notes.json` 归一化成 ReviewAgent 的数据模型（笔记 + 评论）；
3. 把失败翻译成可执行的中文错误：技能缺失、未登录、超时、部分失败。

边界：只读，不点赞、不评论、不发布；不读取也不输出 cookie 内容，登录态只问技能
的 `status` 子命令。

环境变量::

    REVIEWAGENT_XHS_PYTHON   技能解释器（默认技能运行时的 python.exe）
    REVIEWAGENT_XHS_SCRIPT   xhs_batch.py 路径（默认 ~/.dsh/skills/xhs-batch-reader）
    REVIEWAGENT_XHS_RUN_DIR  默认运行目录（默认 <OUTPUT_DIR>/xhs-runs/<时间戳>）
    REVIEWAGENT_XHS_TIMEOUT  单次采集超时秒数，默认 900
    REVIEWAGENT_XHS_LIMIT    默认读取篇数，默认 20（技能上限 50）
    REVIEWAGENT_XHS_OCR      0 关闭图片 OCR（默认开启）
    REVIEWAGENT_XHS_MAX_IMAGES 每篇最多下载几张图
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from reviewagent import config

PLATFORM = "小红书"

# 技能与解释器的已知位置；环境变量优先。
SKILL_DIR = Path.home() / ".dsh" / "skills" / "xhs-batch-reader"
_CANDIDATE_SCRIPTS = (
    SKILL_DIR / "scripts" / "xhs_batch.py",
)
_CANDIDATE_PYTHONS = (
    Path.home() / ".dsh" / "runtimes" / "skills" / "py" / "python.exe",
)

_LOGIN_TOKENS = (
    "需要登录", "未登录", "登录已过期", "登录失效", "扫码登录",
    "login required", "not logged in", "login expired", "unauthorized",
)


# ── 异常 ──────────────────────────────────────────────────────

class XhsError(RuntimeError):
    """小红书采集异常基类。消息直接面向用户，包含修复动作。"""


class XhsUnavailable(XhsError):
    """技能、解释器或只读后端不可用。"""


class XhsLoginRequired(XhsError):
    """需要扫码登录。"""


class XhsCaptureError(XhsError):
    """采集失败（网络、风控、页面改版、超时等）。"""


# ── 路径解析 ──────────────────────────────────────────────────

def _first_existing(candidates: Iterable[Path]) -> str:
    for candidate in candidates:
        try:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate))
        except OSError:
            continue
    return ""


def xhs_python() -> str:
    """技能解释器：环境变量 → 已知运行时 → 当前解释器。"""
    explicit = (os.environ.get("REVIEWAGENT_XHS_PYTHON") or config.XHS_PYTHON or "").strip()
    if explicit:
        return explicit
    return _first_existing(_CANDIDATE_PYTHONS) or sys.executable


def xhs_script() -> str:
    """xhs_batch.py 路径：环境变量 → 已知技能目录 → 默认技能路径。"""
    explicit = (os.environ.get("REVIEWAGENT_XHS_SCRIPT") or config.XHS_SCRIPT or "").strip()
    if explicit:
        return explicit
    found = _first_existing(_CANDIDATE_SCRIPTS)
    return found or str(_CANDIDATE_SCRIPTS[0])


def describe() -> Dict[str, Any]:
    """技能是否可用的静态信息（不启动后端）。"""
    python = xhs_python()
    script = xhs_script()
    python_ok = Path(python).is_file()
    script_ok = Path(script).is_file()
    return {
        "available": bool(python_ok and script_ok),
        "python": python,
        "python_exists": python_ok,
        "script": script,
        "script_exists": script_ok,
    }


def available() -> bool:
    """解释器与技能脚本都在才算可用。"""
    return bool(describe()["available"])


# ── 子进程 ────────────────────────────────────────────────────

def _run(argv: Sequence[str], timeout: float) -> subprocess.CompletedProcess:
    """固定 argv 调外部程序：不经 shell，控制台窗口不弹出。"""
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    kwargs: Dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        **kwargs,
    )


def _tail(text: Optional[str], limit: int = 500) -> str:
    value = (text or "").strip()
    return value if len(value) <= limit else "…" + value[-limit:]


def _json_tail(text: Optional[str]) -> Optional[dict]:
    """从混杂日志的 stdout 里取最后一个 JSON 对象。"""
    value = (text or "").strip()
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    for index in range(len(value) - 1, -1, -1):
        if value[index] != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(value[index:])
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _looks_like_login(text: str) -> bool:
    low = (text or "").lower()
    return any(token.lower() in low for token in _LOGIN_TOKENS)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _fingerprint(text: str) -> str:
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


# ── 状态与登录 ────────────────────────────────────────────────

_COOKIE_PUBLIC_KEYS = (
    "exists", "count", "has_session", "has_id_token",
    "saved_at", "expires_at", "days_left", "logged_in", "reason",
)


def _public_cookie_report(raw: Any) -> Dict[str, Any]:
    """只保留 cookie 状态，不把本机路径带进 API / 日志。"""
    if not isinstance(raw, dict):
        return {}
    return {key: raw[key] for key in _COOKIE_PUBLIC_KEYS if key in raw}


def status() -> Dict[str, Any]:
    """问技能的 `status`：后端、登录态、cookie 到期提示。

    只解析技能打印的 JSON，不读 cookie 文件本身。未安装技能时返回 available=False，
    不抛异常，方便 doctor 与 API 做健康检查。
    """
    info = describe()
    if not info["available"]:
        info.update({
            "ok": False,
            "logged_in": False,
            "hint": "未找到 xhs-batch-reader 技能或它的解释器；安装技能，"
                    "或用 REVIEWAGENT_XHS_SCRIPT / REVIEWAGENT_XHS_PYTHON 指向实际路径。",
        })
        return info

    argv = [info["python"], "-X", "utf8", info["script"], "status"]
    timeout = min(float(config.XHS_TIMEOUT or 180), 180.0)
    try:
        proc = _run(argv, timeout=timeout)
    except subprocess.TimeoutExpired:
        info.update({
            "ok": False,
            "logged_in": False,
            "hint": f"小红书只读后端 {int(timeout)} 秒内没有响应；确认后端二进制可用后重试。",
        })
        return info

    payload = _json_tail(proc.stdout) or {}
    hint = str(payload.get("hint") or "")
    if proc.returncode != 0 and not payload.get("backend"):
        hint = _tail(proc.stderr) or "小红书状态检查失败"
    info.update({
        "ok": proc.returncode == 0,
        "logged_in": bool(payload.get("logged_in")),
        "backend": payload.get("backend") or {},
        "cookies": _public_cookie_report(payload.get("cookies")),
        "hint": hint,
        "returncode": proc.returncode,
    })
    return info


def login_message(status_info: Optional[Dict[str, Any]] = None) -> str:
    """给 API / CLI 复用的扫码指引。"""
    info = status_info or status()
    detail = info.get("hint") or "需要扫码登录一次"
    script = info.get("script") or xhs_script()
    return (
        "小红书搜索与博主主页需要登录，当前未登录或登录已过期。"
        f"请先扫码：运行 \"python {script} login\"（或调 DSH 的 xhs_login 工具），"
        f"登录成功后重试。状态提示：{detail}"
    )


def ensure_login() -> Dict[str, Any]:
    """搜索 / 博主主页前确认登录态；未登录直接抛带指引的错。"""
    info = status()
    if not info.get("available", True):
        raise XhsUnavailable(str(info.get("hint") or "xhs-batch-reader 技能不可用"))
    if not info.get("logged_in"):
        raise XhsLoginRequired(login_message(info))
    return info


# ── 归一化 ────────────────────────────────────────────────────

def normalize_note(raw: Dict[str, Any]) -> Dict[str, Any]:
    """把技能产出的单篇笔记压成 ReviewAgent 的笔记模型。"""
    author = raw.get("author") or {}
    stats = raw.get("stats") or {}
    desc = str(raw.get("desc") or "")
    ocr_text = str((raw.get("ocr") or {}).get("text") or "")
    text = str(raw.get("text") or "").strip()
    if not text:
        text = "\n".join(part for part in (desc, ocr_text) if part)

    comments: List[Dict[str, Any]] = []
    for item in raw.get("comments") or []:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        comments.append({
            "comment_id": str(item.get("id") or ""),
            "content": content,
            "user": str(item.get("user") or ""),
            "like": _int(item.get("like")),
            "ip": str(item.get("ip") or ""),
            "sub_count": _int(item.get("sub_count")),
        })

    images: List[Dict[str, Any]] = []
    for pos, item in enumerate(raw.get("images") or []):
        if not isinstance(item, dict):
            continue
        src = str(item.get("src") or item.get("url") or "").strip()
        if not src:
            continue
        images.append({
            "index": _int(item.get("index")) if item.get("index") is not None else pos,
            "width": _int(item.get("width")),
            "height": _int(item.get("height")),
            "src": src,
        })

    fetch = raw.get("fetch") or {}
    return {
        "note_id": str(raw.get("note_id") or ""),
        "title": str(raw.get("title") or "").strip(),
        "type": str(raw.get("type") or ""),
        "desc": desc,
        "ocr_text": ocr_text,
        "text": text,
        "tags": [str(tag) for tag in (raw.get("tags") or []) if str(tag).strip()],
        "author": {
            "user_id": str(author.get("user_id") or ""),
            "nickname": str(author.get("nickname") or ""),
        },
        "published_at": str(raw.get("time") or ""),
        "ip_location": str(raw.get("ip_location") or ""),
        "source_url": str(raw.get("source_url") or raw.get("url") or ""),
        "stats": {
            "liked": _int(stats.get("liked")),
            "collected": _int(stats.get("collected")),
            "comment": _int(stats.get("comment")),
            "shared": _int(stats.get("shared")),
        },
        "image_count": len(images),
        "images": images,
        "comments": comments,
        "fetch_ok": bool(fetch.get("ok", True)),
        "errors": [str(err) for err in (raw.get("errors") or [])],
    }


def notes_to_reviews(notes: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """评论 → 现有分析内核认识的 review 结构；按 (note_id, comment_id) 去重。

    小红书评论没有星级与日期：rating 置 0 并标 rating_missing，review_date 留空，
    不编造。平台与原文链接逐条带上，保证可溯源。
    """
    reviews: List[Dict[str, Any]] = []
    seen: set = set()
    for note in notes:
        note_id = note.get("note_id") or ""
        source_url = note.get("source_url") or ""
        for comment in note.get("comments") or []:
            content = str(comment.get("content") or "").strip()
            if not content:
                continue
            comment_id = comment.get("comment_id") or _fingerprint(content)
            key = (note_id, comment_id)
            if key in seen:
                continue
            seen.add(key)
            reviews.append({
                "review_text": content,
                "rating": 0,
                "rating_missing": True,
                "platform": PLATFORM,
                "source_platform": PLATFORM,
                "source_url": source_url,
                "product_id": note_id,
                "reviewer_name": comment.get("user") or "",
                "review_date": "",
                "sku": "",
                "note_id": note_id,
                "note_title": note.get("title") or "",
                "comment_id": comment_id,
                "comment_like": comment.get("like") or 0,
                "ip_location": comment.get("ip") or "",
                "sub_comment_count": comment.get("sub_count") or 0,
                "is_demo": False,
            })
    return reviews


# ── 采集与读取 ────────────────────────────────────────────────

def _default_run_dir() -> Path:
    base = (os.environ.get("REVIEWAGENT_XHS_RUN_DIR") or config.XHS_RUN_DIR or "").strip()
    if base:
        return Path(base).expanduser() / time.strftime("%Y%m%d-%H%M%S")
    return Path(config.OUTPUT_DIR) / "xhs-runs" / time.strftime("%Y%m%d-%H%M%S")


def _build_capture(run_dir: Path, raw_saved: Dict[str, Any], meta_extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    raw_notes = raw_saved.get("notes") or []
    notes = [normalize_note(item) for item in raw_notes if isinstance(item, dict)]
    notes = [note for note in notes if note.get("note_id") or note.get("title")]
    reviews = notes_to_reviews(notes)
    meta = dict(raw_saved.get("meta") or {})
    if meta_extra:
        meta.update(meta_extra)
    errors: List[str] = []
    for note in notes:
        for error in note.get("errors") or []:
            errors.append(f"{note.get('title') or note.get('note_id')}: {error}")
    return {
        "platform": PLATFORM,
        "run_dir": str(run_dir),
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "meta": meta,
        "notes": notes,
        "reviews": reviews,
        "stats": {
            "notes": len(notes),
            "notes_ok": len([note for note in notes if note.get("fetch_ok")]),
            "comments": len(reviews),
            "with_ocr": len([note for note in notes if note.get("ocr_text")]),
        },
        "errors": errors,
    }


def load_run(run_dir: str | Path) -> Dict[str, Any]:
    """读一次已有运行目录里的 notes.json，不重新抓取。"""
    path = Path(run_dir).expanduser().resolve()
    notes_file = path / "notes.json"
    if not notes_file.is_file():
        raise XhsCaptureError(
            f"找不到 {notes_file}；需要一个由 xhs-batch-reader 产出的运行目录（含 notes.json）。"
        )
    try:
        saved = json.loads(notes_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise XhsCaptureError(f"读取 {notes_file} 失败：{exc}") from exc
    if not isinstance(saved, dict):
        raise XhsCaptureError(f"{notes_file} 结构不是对象，无法解析")
    return _build_capture(path, saved)


def capture(
    *,
    links: Optional[Sequence[str]] = None,
    keyword: str = "",
    user: str = "",
    limit: Optional[int] = None,
    with_comments: bool = True,
    out_dir: str | Path | None = None,
    sort: str = "",
    sweep: bool = False,
    note_type: str = "",
    with_ocr: Optional[bool] = None,
    max_images: Optional[int] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """调用技能采集一次，返回归一化结果。

    来源三选一：笔记链接列表 / 搜索关键词 / 博主主页。搜索与主页需要登录，
    未登录在开跑前就抛 XhsLoginRequired，避免白等到超时。
    """
    targets = [str(item).strip() for item in (links or []) if str(item).strip()]
    keyword = (keyword or "").strip()
    user = (user or "").strip()
    kinds = int(bool(targets)) + int(bool(keyword)) + int(bool(user))
    if kinds == 0:
        raise XhsCaptureError("请提供笔记链接、搜索关键词或博主主页之一")
    if kinds > 1:
        raise XhsCaptureError("一次只支持一种来源：笔记链接 / 搜索关键词 / 博主主页")

    info = describe()
    if not info["available"]:
        raise XhsUnavailable(
            "xhs-batch-reader 不可用："
            + ("找不到技能脚本；" if not info["script_exists"] else "")
            + ("找不到解释器；" if not info["python_exists"] else "")
            + "安装技能，或用 REVIEWAGENT_XHS_SCRIPT / REVIEWAGENT_XHS_PYTHON 指向实际路径。"
        )
    if keyword or user:
        ensure_login()

    limit_value = max(1, min(int(limit or config.XHS_LIMIT or 20), 50))
    run_dir = Path(out_dir).expanduser().resolve() if out_dir else _default_run_dir().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    argv = [info["python"], "-X", "utf8", info["script"], "read"]
    argv += targets
    if keyword:
        argv += ["--keyword", keyword]
    if user:
        argv += ["--user", user]
    if with_comments:
        argv.append("--comments")
    argv += ["--limit", str(limit_value), "--out", str(run_dir)]
    if sort:
        argv += ["--sort", sort]
    if sweep:
        argv.append("--sweep")
    if note_type:
        argv += ["--note-type", note_type]
    ocr_enabled = config.XHS_WITH_OCR if with_ocr is None else bool(with_ocr)
    if not ocr_enabled:
        argv.append("--no-ocr")
    if max_images:
        argv += ["--max-images", str(int(max_images))]

    wait = float(timeout or config.XHS_TIMEOUT or 900)
    started = time.time()
    try:
        proc = _run(argv, timeout=wait)
    except subprocess.TimeoutExpired as exc:
        raise XhsCaptureError(
            f"小红书采集超时（{int(wait)} 秒）。已读部分通常已落盘：{run_dir}；"
            "可以加 --resume 续跑，或减少 --limit / 关掉 OCR。"
        ) from exc

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    payload = _json_tail(stdout) or {}
    if proc.returncode not in (0, 3):
        combined = stdout + "\n" + stderr
        if _looks_like_login(combined):
            raise XhsLoginRequired(login_message(status()))
        reason = _tail(stderr) or _tail(stdout) or "技能没有返回原因"
        raise XhsCaptureError(
            f"小红书采集失败（退出码 {proc.returncode}）：{reason}\n运行目录：{run_dir}"
        )

    notes_file = run_dir / "notes.json"
    if not notes_file.is_file():
        raise XhsCaptureError(
            f"采集结束但没有写出 notes.json：{run_dir}；技能输出：{_tail(stderr) or '（空）'}"
        )
    try:
        saved = json.loads(notes_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise XhsCaptureError(f"采集产物无法解析：{notes_file}（{exc}）") from exc

    failed_notes = payload.get("failed_notes") or []
    meta_extra = {
        "elapsed_seconds": round(time.time() - started, 1),
        "failed_notes": failed_notes,
        "returncode": proc.returncode,
        "source": {"links": len(targets), "keyword": keyword, "user": user},
    }
    result = _build_capture(run_dir, saved, meta_extra)
    result["warnings"] = []
    if proc.returncode == 3 and failed_notes:
        result["warnings"].append(f"{len(failed_notes)} 篇笔记读取失败，详情见 errors")
    if not result["reviews"]:
        result["warnings"].append("这次没有读到评论；报告只能做笔记层洞察，情绪分析会跳过")
    return result


def summarize(result: Dict[str, Any]) -> str:
    """一行摘要，CLI 直接用。"""
    stats = result.get("stats") or {}
    elapsed = (result.get("meta") or {}).get("elapsed_seconds")
    tail = f"，耗时 {elapsed} 秒" if elapsed else ""
    warnings = "；".join(result.get("warnings") or [])
    line = (
        f"小红书采集：笔记 {stats.get('notes', 0)} 篇（成功 "
        f"{stats.get('notes_ok', 0)}）· 评论 {stats.get('comments', 0)} 条"
        f" · 带图文字 {stats.get('with_ocr', 0)} 篇{tail}\n运行目录：{result.get('run_dir')}"
    )
    return line + (f"\n注意：{warnings}" if warnings else "")
