# -*- coding: utf-8 -*-
"""xhs_reader（小红书采集适配层）的离线测试：不启动后端、不联网。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from reviewagent.scrapers import xhs_reader


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["xhs_batch.py"], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def _note(note_id: str = "n1", title: str = "一支防晒", comments=None, **extra) -> dict:
    note = {
        "note_id": note_id,
        "xsec_token": "token",
        "url": f"https://www.xiaohongshu.com/explore/{note_id}",
        "source_url": f"https://www.xiaohongshu.com/explore/{note_id}",
        "type": "normal",
        "title": title,
        "desc": "油皮夏天通勤，成膜快。",
        "tags": ["防晒", "油皮"],
        "author": {"user_id": "u1", "nickname": "阿禾"},
        "time": "2026-09-01 10:00",
        "ip_location": "上海",
        "stats": {"liked": 120, "collected": 40, "comment": 3, "shared": 1},
        "images": [{"index": 0, "src": "http://img"}],
        "comments": comments or [],
        "text": "",
        "ocr": {"items": [], "text": "", "files": [], "chars": 0},
        "fetch": {"ok": True},
        "errors": [],
    }
    note.update(extra)
    return note


def _comment(cid: str = "c1", content: str = "油皮用着有点闷痘", user: str = "豆豆", like: int = 2) -> dict:
    return {"id": cid, "content": content, "like": like, "ip": "北京", "user": user, "sub_count": 0}


def _write_notes(path, notes) -> None:
    path.mkdir(parents=True, exist_ok=True)
    payload = {"meta": {"planned": len(notes), "read": len(notes), "failed": 0}, "notes": notes}
    (path / "notes.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _install_fake_skill(monkeypatch, tmp_path):
    """让 describe() 认为技能可用，避免依赖本机安装位置。"""
    script = tmp_path / "xhs_batch.py"
    script.write_text("# fake skill", encoding="utf-8")
    monkeypatch.setenv("REVIEWAGENT_XHS_PYTHON", sys.executable)
    monkeypatch.setenv("REVIEWAGENT_XHS_SCRIPT", str(script))
    return script


# ── 可用性与状态 ──────────────────────────────────────────────

def test_available_requires_both_files(monkeypatch, tmp_path):
    script = tmp_path / "xhs_batch.py"
    script.write_text("# fake", encoding="utf-8")
    monkeypatch.setenv("REVIEWAGENT_XHS_PYTHON", sys.executable)
    monkeypatch.setenv("REVIEWAGENT_XHS_SCRIPT", str(script))
    assert xhs_reader.available() is True

    monkeypatch.setenv("REVIEWAGENT_XHS_SCRIPT", str(tmp_path / "missing.py"))
    assert xhs_reader.available() is False
    info = xhs_reader.describe()
    assert info["script_exists"] is False and info["python_exists"] is True


def test_status_reports_missing_skill(monkeypatch, tmp_path):
    monkeypatch.setenv("REVIEWAGENT_XHS_PYTHON", str(tmp_path / "no-python.exe"))
    monkeypatch.setenv("REVIEWAGENT_XHS_SCRIPT", str(tmp_path / "no-script.py"))
    info = xhs_reader.status()
    assert info["available"] is False
    assert info["logged_in"] is False
    assert "REVIEWAGENT_XHS_SCRIPT" in info["hint"]


def test_status_parses_skill_json(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)
    payload = {"backend": {"port": 18861, "pid": 42}, "logged_in": True,
               "login": {"is_logged_in": True}, "cookies": {"has_id_token": True},
               "hint": "已登录"}
    calls = []

    def fake_run(argv, timeout):
        calls.append((argv, timeout))
        return _proc(0, json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    info = xhs_reader.status()
    assert info["logged_in"] is True
    assert info["hint"] == "已登录"
    assert calls[0][0][-1] == "status"


def test_status_cookie_report_strips_local_path(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)
    payload = {"logged_in": True, "cookies": {
        "path": "C:/Users/someone/.xhs-batch-reader/cookies.json",
        "exists": True, "count": 7, "has_id_token": True, "days_left": 300,
    }}

    monkeypatch.setattr(xhs_reader, "_run", lambda argv, timeout: _proc(0, json.dumps(payload)))
    info = xhs_reader.status()
    assert "path" not in info["cookies"]
    assert info["cookies"]["has_id_token"] is True and info["cookies"]["days_left"] == 300


def test_status_timeout_is_reported(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)

    def fake_run(argv, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    info = xhs_reader.status()
    assert info["ok"] is False and info["logged_in"] is False
    assert "没有响应" in info["hint"]


# ── 登录边界 ──────────────────────────────────────────────────

def test_keyword_capture_requires_login(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)
    monkeypatch.setattr(xhs_reader, "status", lambda: {
        "available": True, "logged_in": False, "script": "xhs_batch.py", "hint": "会话过期"})
    with pytest.raises(xhs_reader.XhsLoginRequired) as exc:
        xhs_reader.capture(keyword="防晒", out_dir=tmp_path / "run")
    assert "扫码" in str(exc.value) and "会话过期" in str(exc.value)


def test_link_capture_does_not_require_login(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)
    monkeypatch.setattr(xhs_reader, "status", lambda: (_ for _ in ()).throw(
        AssertionError("链接采集不应检查登录态")))

    def fake_run(argv, timeout):
        out = argv[argv.index("--out") + 1]
        _write_notes(Path(out), [_note()])
        return _proc(0, "{}")

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    result = xhs_reader.capture(links=["https://www.xiaohongshu.com/explore/n1?xsec_token=t"],
                                out_dir=tmp_path / "run")
    assert result["stats"]["notes"] == 1


def test_login_failure_maps_to_login_required(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)
    monkeypatch.setattr(xhs_reader, "status", lambda: {
        "available": True, "logged_in": False, "script": "xhs_batch.py", "hint": "需要扫码登录一次"})

    def fake_run(argv, timeout):
        return _proc(2, stderr="BackendError: 需要登录")

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    with pytest.raises(xhs_reader.XhsLoginRequired):
        xhs_reader.capture(keyword="防晒", out_dir=tmp_path / "run")


# ── 归一化与去重 ──────────────────────────────────────────────

def test_capture_builds_argv_and_normalizes(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)
    seen = {}

    def fake_run(argv, timeout):
        seen["argv"] = argv
        out = Path(argv[argv.index("--out") + 1])
        note = _note(comments=[_comment()], ocr={"items": [], "text": "SPF50 油皮", "files": [], "chars": 8})
        note["text"] = "油皮夏天通勤，成膜快。\nSPF50 油皮"
        _write_notes(out, [note, _note(note_id="n2", title="第二篇")])
        return _proc(0, "{}")

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    result = xhs_reader.capture(links=["https://www.xiaohongshu.com/explore/n1?xsec_token=t"],
                                limit=3, out_dir=tmp_path / "run", sort="最新")

    argv = seen["argv"]
    assert "--comments" in argv and "--limit" in argv
    assert argv[argv.index("--limit") + 1] == "3"
    assert "--sort" in argv and argv[argv.index("--sort") + 1] == "最新"
    assert "--keyword" not in argv

    assert result["stats"] == {"notes": 2, "notes_ok": 2, "comments": 1, "with_ocr": 1}
    review = result["reviews"][0]
    assert review["review_text"] == "油皮用着有点闷痘"
    assert review["source_platform"] == "小红书"
    assert review["platform"] == "小红书"
    assert review["product_id"] == "n1"
    assert review["comment_id"] == "c1"
    assert review["review_date"] == ""
    assert review["rating"] == 0 and review["rating_missing"] is True
    assert review["source_url"].endswith("/n1")
    note = result["notes"][0]
    assert note["ocr_text"] == "SPF50 油皮"
    assert note["image_count"] == 1
    assert note["images"][0]["src"] == "http://img"
    assert note["comments"][0]["like"] == 2


def test_capture_dedupes_comments(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)

    def fake_run(argv, timeout):
        out = Path(argv[argv.index("--out") + 1])
        same = _comment(cid="c1")
        _write_notes(out, [
            _note(note_id="n1", comments=[same, _comment(cid="c2", content="第二个")]),
            _note(note_id="n1", comments=[same]),
        ])
        return _proc(0, "{}")

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    result = xhs_reader.capture(links=["x"], out_dir=tmp_path / "run")
    ids = [r["comment_id"] for r in result["reviews"]]
    assert ids == ["c1", "c2"]


def test_empty_comments_warn_without_inventing(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)

    def fake_run(argv, timeout):
        out = Path(argv[argv.index("--out") + 1])
        _write_notes(out, [_note(comments=[])])
        return _proc(0, "{}")

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    result = xhs_reader.capture(links=["x"], out_dir=tmp_path / "run")
    assert result["reviews"] == []
    assert any("没有读到评论" in warning for warning in result["warnings"])


def test_capture_disables_ocr_through_flag(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)
    seen = {}

    def fake_run(argv, timeout):
        seen["argv"] = argv
        out = Path(argv[argv.index("--out") + 1])
        _write_notes(out, [_note()])
        return _proc(0, "{}")

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    xhs_reader.capture(links=["x"], out_dir=tmp_path / "run", with_ocr=False)
    assert "--no-ocr" in seen["argv"]


# ── 失败与部分失败 ────────────────────────────────────────────

def test_generic_failure_carries_reason(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)

    def fake_run(argv, timeout):
        return _proc(1, stderr="boom: browser crashed")

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    with pytest.raises(xhs_reader.XhsCaptureError) as exc:
        xhs_reader.capture(links=["x"], out_dir=tmp_path / "run")
    assert "退出码 1" in str(exc.value) and "browser crashed" in str(exc.value)


def test_timeout_points_to_resume(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)

    def fake_run(argv, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    with pytest.raises(xhs_reader.XhsCaptureError) as exc:
        xhs_reader.capture(links=["x"], out_dir=tmp_path / "run", timeout=5)
    assert "超时" in str(exc.value) and "--resume" in str(exc.value)


def test_partial_failure_warns_but_keeps_notes(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)

    def fake_run(argv, timeout):
        out = Path(argv[argv.index("--out") + 1])
        good = _note(comments=[_comment()])
        bad = _note(note_id="n2", comments=[])
        bad["errors"] = ["缺少 xsec_token，无法读取"]
        _write_notes(out, [good, bad])
        payload = {"count": 2, "failed_notes": [{"note_id": "n2", "error": "缺少 xsec_token"}]}
        return _proc(3, json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    result = xhs_reader.capture(links=["x"], out_dir=tmp_path / "run")
    assert result["stats"]["notes"] == 2 and result["stats"]["comments"] == 1
    assert any("1 篇笔记读取失败" in warning for warning in result["warnings"])
    assert any("xsec_token" in error for error in result["errors"])


def test_missing_notes_json_is_explicit(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)
    monkeypatch.setattr(xhs_reader, "_run", lambda argv, timeout: _proc(0, "{}"))
    with pytest.raises(xhs_reader.XhsCaptureError) as exc:
        xhs_reader.capture(links=["x"], out_dir=tmp_path / "run")
    assert "notes.json" in str(exc.value)


def test_load_run_missing_file(tmp_path):
    with pytest.raises(xhs_reader.XhsCaptureError) as exc:
        xhs_reader.load_run(tmp_path / "nope")
    assert "notes.json" in str(exc.value)


def test_load_run_reads_notes(tmp_path):
    _write_notes(tmp_path, [_note(comments=[_comment()])])
    result = xhs_reader.load_run(tmp_path)
    assert result["stats"]["notes"] == 1 and result["stats"]["comments"] == 1
    assert result["run_dir"].endswith(str(tmp_path))


def test_json_tail_skips_log_prefix():
    assert xhs_reader._json_tail('log line\n{"count": 2}\n') == {"count": 2}
    assert xhs_reader._json_tail("no json here") is None


def test_summarize_mentions_counts(monkeypatch, tmp_path):
    _install_fake_skill(monkeypatch, tmp_path)

    def fake_run(argv, timeout):
        out = Path(argv[argv.index("--out") + 1])
        _write_notes(out, [_note(comments=[_comment()])])
        return _proc(0, "{}")

    monkeypatch.setattr(xhs_reader, "_run", fake_run)
    result = xhs_reader.capture(links=["x"], out_dir=tmp_path / "run")
    line = xhs_reader.summarize(result)
    assert "笔记 1 篇" in line and "评论 1 条" in line
