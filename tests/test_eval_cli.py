# -*- coding: utf-8 -*-
"""评测：数据集加载、规则基线与 CLI 输出。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from reviewagent import eval as eval_mod
from reviewagent.cli import cmd_eval

DATASET = [
    {"id": "e1", "text": "质量很好，物流也快，满意", "rating": 5, "date": "2026-10-01", "sentiment": "真诚好评", "validity": "真实有效"},
    {"id": "e2", "text": "用了三天就坏了，垃圾", "rating": 1, "date": "2026-10-02", "sentiment": "直接差评", "validity": "真实有效"},
    {"id": "e3", "text": "好评，物流很快，客服很好", "rating": 5, "date": "2026-10-02", "sentiment": "真诚好评", "validity": "模板化好评"},
    {"id": "e4", "text": "东西一般般吧，说不上好也说不上差", "rating": 3, "date": "2026-10-03", "sentiment": "客观中性", "validity": "真实有效"},
]


def _write_dataset(tmp_path: Path) -> Path:
    path = tmp_path / "dataset.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in DATASET) + "\n", encoding="utf-8")
    return path


def test_load_dataset_joins_lines_and_skips_comments(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text('// 说明\n{"id":"a","text":"好","sentiment":"真诚好评"}\n{"id":"b","text":"差","sentiment":"直接差评"}\n', encoding="utf-8")
    items = eval_mod.load_dataset(path)
    assert [item["id"] for item in items] == ["a", "b"]


def test_rules_baseline_returns_metrics(tmp_path):
    report = eval_mod.evaluate_dataset(_write_dataset(tmp_path), baseline="rules")
    assert report["samples"] == 4
    assert report["baseline"] == "rules"
    sentiment = report["dimensions"]["sentiment"]
    assert sentiment["samples"] == 4
    assert 0.0 <= sentiment["accuracy"] <= 1.0
    assert 0.0 <= sentiment["macro_f1"] <= 1.0
    assert report["dimensions"]["validity"]["samples"] == 4


def test_predictions_file_overrides_baseline(tmp_path):
    dataset = _write_dataset(tmp_path)
    preds = tmp_path / "preds.json"
    preds.write_text(
        json.dumps([{"sentiment": row["sentiment"], "validity": row["validity"]} for row in DATASET], ensure_ascii=False),
        encoding="utf-8",
    )
    report = eval_mod.evaluate_dataset(dataset, predictions_path=preds, baseline="rules")
    assert report["baseline"] == "predictions-file"
    assert report["dimensions"]["sentiment"]["accuracy"] == 1.0
    assert report["dimensions"]["validity"]["accuracy"] == 1.0


def test_predictions_length_mismatch_is_rejected(tmp_path):
    dataset = _write_dataset(tmp_path)
    preds = tmp_path / "preds.json"
    preds.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        eval_mod.evaluate_dataset(dataset, predictions_path=preds)


def test_cmd_eval_writes_report_and_prints_metrics(tmp_path, capsys):
    dataset = _write_dataset(tmp_path)
    out = tmp_path / "eval-out.json"
    code = cmd_eval(
        argparse.Namespace(dataset=str(dataset), baseline="rules", predictions=None, out=str(out))
    )
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["dataset"] == str(dataset)
    assert report["samples"] == 4
    printed = capsys.readouterr().out
    assert "情绪" in printed and "有效性" in printed and "accuracy" in printed


def test_cmd_eval_missing_dataset_returns_2(tmp_path, capsys):
    code = cmd_eval(
        argparse.Namespace(dataset=str(tmp_path / "nope.jsonl"), baseline="rules", predictions=None, out=None)
    )
    assert code == 2
    assert "数据集不存在" in capsys.readouterr().err
