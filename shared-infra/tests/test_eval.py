import json

import pytest

from spine.eval import (
    Baseline,
    DatasetError,
    FieldAccuracy,
    GoldenExample,
    JsonlResultSink,
    LlmJudge,
    Prediction,
    SchemaPassRate,
    ToolCallCorrectness,
    compare_to_baseline,
    dump_dataset,
    example_dataset_path,
    load_baseline,
    load_dataset,
    load_suite,
    parse_judge_score,
    run_eval,
    run_gate,
    save_baseline,
)
from spine.eval.example import build_suite, support_metrics
from spine.eval.gate import gate_main
from spine.models import FakeModelClient

# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #


def test_example_dataset_loads():
    ds = load_dataset(example_dataset_path())
    assert ds.name == "support_resolution"
    assert ds.version == "1"
    assert len(ds) == 5
    assert all(isinstance(ex, GoldenExample) for ex in ds)


def test_dataset_round_trip(tmp_path):
    original = load_dataset(example_dataset_path())
    out = tmp_path / "rt.jsonl"
    dump_dataset(original, out)
    reloaded = load_dataset(out)
    assert reloaded.name == original.name
    assert reloaded.version == original.version
    assert reloaded.examples == original.examples


def test_dataset_rejects_duplicate_ids(tmp_path):
    p = tmp_path / "dup.jsonl"
    p.write_text(
        '{"id": "a", "input": "x", "expected": {"k": 1}}\n'
        '{"id": "a", "input": "y", "expected": {"k": 2}}\n'
    )
    with pytest.raises(DatasetError, match="duplicate"):
        load_dataset(p)


def test_dataset_rejects_bad_expected(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"id": "a", "input": "x", "expected": 3}\n')
    with pytest.raises(DatasetError, match="expected"):
        load_dataset(p)


def test_dataset_rejects_unsupported_schema(tmp_path):
    p = tmp_path / "ver.jsonl"
    p.write_text('{"schema_version": 99, "name": "z"}\n{"id": "a", "input": "x", "expected": {}}\n')
    with pytest.raises(DatasetError, match="schema_version"):
        load_dataset(p)


# --------------------------------------------------------------------------- #
# Deterministic metrics
# --------------------------------------------------------------------------- #


def _ex(expected):
    return GoldenExample(id="e", input="in", expected=expected)


def test_field_accuracy():
    ex = _ex({"a": 1, "b": 2})
    metric = FieldAccuracy(fields=["a", "b"])

    perfect = metric.score(ex, Prediction(output={"a": 1, "b": 2}))
    assert perfect.score == 1.0 and perfect.passed

    half = metric.score(ex, Prediction(output={"a": 1, "b": 999}))
    assert half.score == 0.5 and not half.passed
    assert half.detail["mismatches"] == {"b": {"expected": 2, "got": 999}}


def test_field_accuracy_skips_unlabelled_fields():
    ex = _ex({"a": 1})  # 'b' not labelled
    metric = FieldAccuracy(fields=["a", "b"])
    res = metric.score(ex, Prediction(output={"a": 1}))
    assert res.score == 1.0
    assert res.detail["checked"] == 1


def test_schema_pass_rate():
    metric = SchemaPassRate(required_fields=["a", "b"], types={"a": int})
    ok = metric.score(_ex({}), Prediction(output={"a": 1, "b": 2}))
    assert ok.score == 1.0 and ok.passed

    missing = metric.score(_ex({}), Prediction(output={"a": 1}))
    assert missing.score == 0.0 and missing.detail["missing"] == ["b"]

    bad_type = metric.score(_ex({}), Prediction(output={"a": "x", "b": 2}))
    assert bad_type.score == 0.0 and bad_type.detail["bad_types"] == {"a": "str"}


def test_tool_call_correctness_unordered_and_ordered():
    ex = _ex({"tool_calls": ["a", "b"]})

    unordered = ToolCallCorrectness()
    assert unordered.score(ex, Prediction(tool_calls=("b", "a"))).passed

    ordered = ToolCallCorrectness(ordered=True)
    assert not ordered.score(ex, Prediction(tool_calls=("b", "a"))).passed
    assert ordered.score(ex, Prediction(tool_calls=("a", "b"))).passed


def test_tool_call_correctness_skips_when_unlabelled():
    res = ToolCallCorrectness().score(_ex({}), Prediction(tool_calls=("a",)))
    assert res.score == 1.0 and res.detail["skipped"]


# --------------------------------------------------------------------------- #
# LLM-as-judge (driven by FakeModelClient — no real calls)
# --------------------------------------------------------------------------- #


def test_parse_judge_score_variants():
    assert parse_judge_score('{"score": 0.8}') == pytest.approx(0.8)
    assert parse_judge_score("SCORE: 0.5") == pytest.approx(0.5)
    assert parse_judge_score('{"score": 5}') == 1.0  # clamped
    with pytest.raises(ValueError):
        parse_judge_score("no score here")


def test_llm_judge_pass_and_fail():
    ex = _ex({"answer": "ref"})

    high = LlmJudge(client=FakeModelClient(reply='{"score": 0.9}'), pass_threshold=0.7)
    hr = high.score(ex, Prediction(text="agent answer"))
    assert hr.score == pytest.approx(0.9) and hr.passed

    low = LlmJudge(client=FakeModelClient(reply='{"score": 0.1}'), pass_threshold=0.7)
    lr = low.score(ex, Prediction(text="agent answer"))
    assert lr.score == pytest.approx(0.1) and not lr.passed


def test_llm_judge_no_real_call_needed():
    fake = FakeModelClient(reply='{"score": 1.0}')
    LlmJudge(client=fake).score(_ex({"answer": "r"}), Prediction(text="a"))
    assert len(fake.calls) == 1  # exactly one fake generate, no network


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def test_runner_aggregates_over_example_dataset():
    ds = load_dataset(example_dataset_path())
    predict = build_suite().predict
    result = run_eval(ds, predict, support_metrics())
    assert result.n_examples == 5
    # the perfect demo predictor should ace every metric
    assert result.mean_scores["field_accuracy"] == pytest.approx(1.0)
    assert result.pass_rates["schema_pass_rate"] == pytest.approx(1.0)
    assert result.mean_scores["llm_judge"] == pytest.approx(1.0)
    assert set(result.summary()) == {
        "dataset_name",
        "dataset_version",
        "n_examples",
        "mean_scores",
        "pass_rates",
    }


# --------------------------------------------------------------------------- #
# Gate — BOTH directions (plan.md verify criterion)
# --------------------------------------------------------------------------- #


def test_gate_passes_good_agent_and_trips_degraded_agent():
    good = build_suite()
    baseline = Baseline.from_result(good.run())

    good_code, good_report, _ = run_gate(good, baseline)
    assert good_code == 0
    assert good_report.passed
    assert good_report.regressions == []

    degraded = build_suite(degrade=True)
    bad_code, bad_report, _ = run_gate(degraded, baseline)
    assert bad_code == 1
    assert not bad_report.passed
    regressed = {r.metric for r in bad_report.regressions}
    assert "field_accuracy" in regressed
    assert "llm_judge" in regressed


def test_compare_to_baseline_within_threshold_passes():
    good = build_suite()
    result = good.run()
    baseline = Baseline.from_result(result)
    # nudge one baseline metric down by less than threshold -> still passes
    baseline.mean_scores["field_accuracy"] -= 0.005
    report = compare_to_baseline(result, baseline, threshold=0.01)
    assert report.passed


def test_baseline_file_round_trip(tmp_path):
    result = build_suite().run()
    path = tmp_path / "baseline.json"
    save_baseline(Baseline.from_result(result), path)
    loaded = load_baseline(path)
    assert loaded.dataset_name == result.dataset_name
    assert loaded.mean_scores == pytest.approx(result.mean_scores)


# --------------------------------------------------------------------------- #
# CLI gate end-to-end via dotted-path factory
# --------------------------------------------------------------------------- #


def test_gate_main_cli_both_directions(tmp_path, capsys):
    baseline_path = tmp_path / "b.json"
    save_baseline(Baseline.from_result(build_suite().run()), baseline_path)

    factory = "spine.eval.example:build_suite"
    ok = gate_main(["--suite", factory, "--baseline", str(baseline_path)])
    assert ok == 0
    assert "PASS" in capsys.readouterr().out

    degraded_factory = "spine.eval.example:degraded_suite"
    fail = gate_main(["--suite", degraded_factory, "--baseline", str(baseline_path)])
    assert fail == 1
    assert "FAIL" in capsys.readouterr().out


def test_load_suite_errors():
    with pytest.raises(ValueError, match="module:factory"):
        load_suite("no_colon_here")
    with pytest.raises(ValueError, match="attribute"):
        load_suite("spine.eval.example:does_not_exist")


# --------------------------------------------------------------------------- #
# Result sink — local JSONL write + readback round-trip
# --------------------------------------------------------------------------- #


def test_jsonl_sink_round_trip(tmp_path):
    sink = JsonlResultSink(tmp_path / "runs" / "results.jsonl")
    r1 = build_suite().run()
    r2 = build_suite(degrade=True).run()
    sink.write(r1)
    sink.write(r2)

    rows = sink.read()
    assert len(rows) == 2
    assert rows[0]["dataset_name"] == r1.dataset_name
    assert rows[0]["mean_scores"]["field_accuracy"] == pytest.approx(1.0)
    assert rows[1]["mean_scores"]["field_accuracy"] == pytest.approx(0.5)
    assert all("run_at" in row for row in rows)


def test_jsonl_sink_read_missing_file_is_empty(tmp_path):
    assert JsonlResultSink(tmp_path / "nope.jsonl").read() == []


# --------------------------------------------------------------------------- #
# Core imports SDK-free
# --------------------------------------------------------------------------- #


def test_eval_surface_imports_without_gcp():
    import spine

    assert hasattr(spine, "eval")
    # sanity: a full run of the demo suite serialises to JSON with no network
    json.dumps(build_suite().run().summary())
