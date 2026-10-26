# -*- coding: utf-8 -*-
"""CLI：命令解析、doctor 自检、历史清理的保护开关。"""
from __future__ import annotations

from reviewagent import cli


def test_parser_accepts_analyze_csv():
    args = cli.build_parser().parse_args(["analyze", "--csv", "data.csv", "--max-reviews", "10"])
    assert args.csv == "data.csv"
    assert args.max_reviews == 10
    assert args.func is cli.cmd_analyze


def test_new_subcommand_is_not_misrouted_by_legacy_flags(monkeypatch):
    calls = []

    def fake_analyze(args):
        calls.append((args.csv, args.max_reviews))
        return 0

    monkeypatch.setattr(cli, "cmd_analyze", fake_analyze)
    assert cli.main(["analyze", "--csv", "data.csv", "--url", "https://example.com", "--max-reviews", "3"]) == 0
    assert calls == [("data.csv", 3)]


def test_doctor_returns_int_and_prints_matrix(capsys):
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert code in (0, 1)
    assert "ReviewAgent" in out
    assert "依赖检查" in out
    assert "数据库" in out


def test_history_clear_requires_yes(capsys):
    assert cli.main(["history", "--clear"]) == 2
    err = capsys.readouterr().err
    assert "--yes" in err


def test_history_empty_prints_message(capsys):
    assert cli.main(["history"]) == 0
    assert "暂无历史记录" in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "analyze" in out and "doctor" in out
