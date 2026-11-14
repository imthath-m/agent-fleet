"""Tests for the eval report scripts. Fixtures are synthetic and built in tmp_path."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


error_analysis = _load("error_analysis")
judge_sheet = _load("judge_sheet")
judge_agreement = _load("judge_agreement")


def _res_row(i: int, score: float, passed: bool, error=None) -> dict:
    return {
        "suite": "resolution", "example_id": f"ex{i}",
        "input": {"ticket_id": f"T{i}", "text": f"ticket text {i}", "subject": f"subj {i}"},
        "expected": {"answer": f"ref {i}", "citations": []}, "tags": ["t"],
        "prediction": {"text": f"answer {i}", "fields": None, "citations": [],
                       "tool_calls": None, "escalated": None},
        "error": error,
        "metrics": {"llm_judge": {"score": score, "passed": passed,
                                  "detail": {"criterion": "c",
                                             "raw": json.dumps({"score": score, "reason": "r"})}}},
    }


def _make_dir(tmp_path: Path, mode: str = "live") -> Path:
    d = tmp_path / "2000-01-01"
    d.mkdir()
    rows = [_res_row(1, 0.9, True), _res_row(2, 0.1, False), _res_row(3, 0.8, True),
            _res_row(4, 0.2, False), _res_row(5, 0.0, False, error="boom")]
    (d / "resolution.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    cls = {"suite": "classification", "example_id": "c1",
           "input": {"text": "x"}, "expected": {"priority": "high"}, "tags": [],
           "prediction": {"text": "", "fields": {"priority": "normal"}, "citations": None,
                          "tool_calls": None, "escalated": None}, "error": None,
           "metrics": {"field_accuracy": {"score": 0.0, "passed": False, "detail": {
               "mismatches": {"priority": {"expected": "high", "got": "normal"}}}}}}
    (d / "classification.jsonl").write_text(json.dumps(cls) + "\n")
    summary = {"mode": mode, "model": "m", "judge_model": "j", "run_at": "t", "git_sha": "abc",
               "suites": {"resolution": {"n_examples": 5, "mean_scores": {"llm_judge": 0.4},
                                         "pass_rates": {"llm_judge": 0.4}, "n_errors": 1}},
               "usage": {"calls": 1, "input_tokens": 2, "output_tokens": 3, "cost_usd": None}}
    (d / "summary.json").write_text(json.dumps(summary))
    return d


def test_error_analysis_writes_report(tmp_path):
    d = _make_dir(tmp_path)
    assert error_analysis.main([str(d)]) == 0
    text = (d / "error_analysis.md").read_text()
    assert "LIVE" in text
    assert "priority: expected high -> got normal" in text
    assert "judge score < 0.3" in text
    assert "pipeline error" in text
    assert "No actions.jsonl rows found." in text


def test_error_analysis_refuses_non_live(tmp_path):
    d = _make_dir(tmp_path, mode="fake")
    assert error_analysis.main([str(d)]) == 2
    assert not (d / "error_analysis.md").exists()
    assert error_analysis.main([str(d), "--allow-fake"]) == 0
    assert "FAKE" in (d / "error_analysis.md").read_text()


def test_judge_sheet_blank_human_columns_and_no_judge_scores(tmp_path, capsys):
    d = _make_dir(tmp_path)
    assert judge_sheet.main([str(d)]) == 0
    err = capsys.readouterr().err
    assert "WARNING" in err and "only 4" in err
    sheet = list(csv.DictReader((d / "judge_sheet.csv").open()))
    assert len(sheet) == 4  # errored row excluded
    assert list(sheet[0]) == judge_sheet.SHEET_COLS
    for r in sheet:
        assert r["human_score"] == r["human_pass"] == r["human_notes"] == ""
    raw = (d / "judge_sheet.csv").read_text()
    assert "judge" not in raw.splitlines()[0]
    key = list(csv.DictReader((d / "judge_key.csv").open()))
    assert {k["item_id"] for k in key} == {r["item_id"] for r in sheet}
    assert (d / "judge_sheet_README.md").exists()


def _fill(d: Path, human: dict[str, str]) -> None:
    rows = list(csv.DictReader((d / "judge_sheet.csv").open()))
    for r in rows:
        r["human_pass"] = human.get(r["item_id"].split(":")[1], "")
    with (d / "judge_sheet.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=judge_sheet.SHEET_COLS)
        w.writeheader()
        w.writerows(rows)


def test_judge_agreement_exit_2_on_blank(tmp_path, capsys):
    d = _make_dir(tmp_path)
    judge_sheet.main([str(d)])
    assert judge_agreement.main([str(d)]) == 2
    assert "4 of 4 unlabelled" in capsys.readouterr().err
    assert not (d / "judge_agreement.md").exists()


def test_judge_agreement_kappa(tmp_path):
    d = _make_dir(tmp_path)
    judge_sheet.main([str(d)])
    # judge: ex1 P, ex2 F, ex3 P, ex4 F. human: P, F, F, F -> agree 3/4.
    _fill(d, {"ex1": "y", "ex2": "n", "ex3": "n", "ex4": "n"})
    assert judge_agreement.main([str(d)]) == 0
    text = (d / "judge_agreement.md").read_text()
    # po=.75, pj=.5, ph=.25 -> pe=.5 -> kappa=.5
    assert "Cohen's kappa: 0.500" in text
    assert "raw agreement (pass/fail): 0.750" in text
    assert "| judge pass | 1 | 1 |" in text and "| judge fail | 0 | 2 |" in text
    assert "ex3" in text.split("## Disagreements")[1]
    assert "human_score not (fully) filled" in text


def test_kappa_undefined_when_constant():
    assert judge_agreement.kappa([(True, True), (True, True)]) is None
    assert judge_agreement.kappa([(True, True), (False, False)]) == pytest.approx(1.0)
