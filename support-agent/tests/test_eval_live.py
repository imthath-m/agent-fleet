import json

import pytest
from spine.eval.runner import load_suite
from spine.models import FakeModelClient

from triage.eval import live
from triage.eval.__main__ import main
from triage.eval.suites import build_classification_suite, build_resolution_suite
from triage.fakes import triage_responder

SUITE_NAMES = ["classification", "resolution", "actions", "escalation", "triage"]
JUDGE_MARKER = "strict evaluator"


def _responder(prompt: str) -> str:
    if JUDGE_MARKER in prompt:
        return '{"score": 0.8, "reason": "ok"}'
    return triage_responder(prompt)


@pytest.fixture
def fake_live(monkeypatch):
    monkeypatch.setattr(live, "build_live_client", lambda: FakeModelClient(responder=_responder))


def test_no_arg_factories_unchanged():
    for name in SUITE_NAMES:
        path = f"triage.eval.suites:build_{name}_suite"
        assert load_suite(path).run().n_examples > 0
    classification = build_classification_suite().run()
    captured, _ = live._run_suite("classification", build_classification_suite(), None)
    assert captured["mean_scores"] == classification.mean_scores
    assert captured["pass_rates"] == classification.pass_rates


def test_injected_judge_is_used_by_resolution_suite():
    judge = FakeModelClient(reply='{"score": 0.5, "reason": "x"}')
    result = build_resolution_suite(judge=judge).run()
    assert result.mean_scores["llm_judge"] == 0.5
    assert len(judge.calls) == result.n_examples


def test_run_all_live_writes_contract(fake_live, tmp_path):
    summary = live.run_all(True, tmp_path, "2026-01-02")

    out = tmp_path / "2026-01-02"
    assert sorted(p.name for p in out.iterdir()) == sorted(
        ["summary.json", *(f"{n}.jsonl" for n in SUITE_NAMES)]
    )
    on_disk = json.loads((out / "summary.json").read_text())
    assert on_disk["mode"] == "live"
    assert set(on_disk["suites"]) == set(SUITE_NAMES)
    assert {"model", "judge_model", "run_at", "git_sha", "usage"} <= set(on_disk)
    assert set(on_disk["usage"]) == {"calls", "input_tokens", "output_tokens", "cost_usd"}
    assert on_disk["usage"]["calls"] > 0
    assert on_disk["usage"]["cost_usd"] is None  # fake model id has no known price
    assert on_disk["judge_usage"]["calls"] == on_disk["suites"]["resolution"]["n_examples"]
    for name in SUITE_NAMES:
        s = on_disk["suites"][name]
        assert set(s) == {"n_examples", "mean_scores", "pass_rates", "n_errors"}
        rows = [json.loads(line) for line in (out / f"{name}.jsonl").read_text().splitlines()]
        assert len(rows) == s["n_examples"]
        assert set(rows[0]) == {
            "suite", "example_id", "input", "expected", "tags", "prediction", "error", "metrics",
        }  # fmt: skip
        assert set(rows[0]["prediction"]) == {
            "text", "fields", "citations", "tool_calls", "escalated",
        }  # fmt: skip
    res = [json.loads(x) for x in (out / "resolution.jsonl").read_text().splitlines()][0]
    assert res["metrics"]["llm_judge"]["score"] == 0.8
    assert res["metrics"]["llm_judge"]["detail"]["raw"]
    assert summary["suites"]["resolution"]["mean_scores"]["llm_judge"] == pytest.approx(0.8)

    # a second run the same day never overwrites
    again = live.run_all(True, tmp_path, "2026-01-02", names=["classification"], limit=1)
    assert again["out_dir"].endswith("2026-01-02-2")
    assert (out / "summary.json").exists()


def test_erroring_example_is_recorded_not_raised(monkeypatch, tmp_path):
    def responder(prompt: str) -> str:
        if JUDGE_MARKER in prompt:
            return '{"score": 1.0, "reason": "ok"}'
        if "support ticket classifier" in prompt:
            return "not json at all"  # -> ClassificationError on every ticket
        return triage_responder(prompt)

    monkeypatch.setattr(live, "build_live_client", lambda: FakeModelClient(responder=responder))
    summary = live.run_all(True, tmp_path, "d", names=["classification"], limit=3)

    s = summary["suites"]["classification"]
    assert (s["n_examples"], s["n_errors"]) == (3, 3)
    assert s["mean_scores"]["field_accuracy"] == 0.0
    text = (tmp_path / "d" / "classification.jsonl").read_text()
    rows = [json.loads(x) for x in text.splitlines()]
    assert all("ClassificationError" in r["error"] and r["prediction"] is None for r in rows)
    assert all(not m["passed"] for r in rows for m in r["metrics"].values())


def test_fake_mode_writes_nothing(tmp_path):
    summary = live.run_all(False, tmp_path, names=["actions"], limit=2)
    assert summary["mode"] == "fake"
    assert list(tmp_path.iterdir()) == []


def test_live_without_key_exits_2_and_writes_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["--live", "--out", str(tmp_path)]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
