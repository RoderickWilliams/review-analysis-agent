# -*- coding: utf-8 -*-
"""susu-insight 接入层的映射、渲染与 CLI 行为。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from reviewagent.insights import susu


def _capture():
    return {
        "notes": [
            {
                "note_id": "abc123",
                "title": "早八人十分钟通勤妆，手残也能学会",
                "source_url": "https://www.xiaohongshu.com/explore/abc123",
                "published_at": "2026-10-20",
                "author": {"nickname": "小鹿不迟到", "user_id": "u1"},
                "comments": [
                    {"comment_id": "c1", "content": "混油皮能用吗？夏天会不会脱妆啊", "like": 42, "user": "momo"},
                    {"comment_id": "c2", "content": "第三步那个遮瑕是什么色号，我黄二白", "like": 18, "user": "阿圆"},
                    {"comment_id": "c3", "content": "这个粉底持妆多久？需要定妆喷雾吗", "like": 9, "user": "小圆"},
                    {"comment_id": "c4", "content": "作者本人回复：混油皮建议薄涂加散粉", "like": 3, "user": "小鹿不迟到"},
                    {"comment_id": "c5", "content": "好看", "like": 1, "user": "momo"},
                ],
            }
        ]
    }


def test_build_analysis_scopes_comments_and_topics():
    analysis = susu.build_analysis(_capture(), account_name="小鹿不迟到", use_llm=False)

    assert analysis["account"]["name"] == "小鹿不迟到"
    assert len(analysis["contents"]) == 1
    by_text = {item["text"]: item for item in analysis["comments"]}
    assert by_text["作者本人回复：混油皮建议薄涂加散粉"]["scope"] == "context"
    assert by_text["好看"]["scope"] == "exclude"
    assert by_text["好看"]["reason"]
    assert by_text["混油皮能用吗？夏天会不会脱妆啊"]["scope"] == "professional"

    assert [topic["id"] for topic in analysis["topics"]] == ["t1"]
    assert len(analysis["topics"][0]["comment_ids"]) == 3
    assert len(analysis["topics"][0]["representative_ids"]) <= 3
    assert analysis["opportunities"]
    assert analysis["opportunities"][0]["signals"] == ["question"]


def test_render_analysis_writes_html_and_passes_skill_validation(tmp_path):
    analysis = susu.build_analysis(_capture(), account_name="小鹿不迟到", use_llm=False)
    result = susu.render_analysis(analysis, out_dir=str(tmp_path))

    html = Path(result["html_path"])
    assert html.is_file() and html.stat().st_size > 10000
    assert "小鹿不迟到" in html.read_text(encoding="utf-8")
    assert result["statistics"]["professional"] == 3
    assert Path(result["json_path"]).is_file()


def test_render_analysis_rejects_invalid_analysis(tmp_path):
    with pytest.raises((ValueError, KeyError)):
        susu.render_analysis({}, out_dir=str(tmp_path))


def _write_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "notes.json").write_text(
        json.dumps({"notes": _capture()["notes"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return run_dir


def test_cli_susu_renders_from_run_dir(tmp_path, capsys):
    from reviewagent.cli import cmd_susu

    run_dir = _write_run(tmp_path)
    out_dir = tmp_path / "out"
    code = cmd_susu(
        argparse.Namespace(
            run_dir=str(run_dir),
            analysis=None,
            account="小鹿不迟到",
            out_dir=str(out_dir),
            no_llm=True,
        )
    )
    assert code == 0
    assert list(out_dir.glob("*.html"))
    assert "susu-insight 报告已生成" in capsys.readouterr().out


def test_cli_susu_requires_source(capsys):
    from reviewagent.cli import cmd_susu

    code = cmd_susu(
        argparse.Namespace(run_dir=None, analysis=None, account="", out_dir=None, no_llm=True)
    )
    assert code == 2
    assert "--run-dir" in capsys.readouterr().err
