import json

import httpx
import pytest
from spine.eval.runner import load_suite
from spine.models import FakeModelClient
from spine.models_openai import OpenAIModelClient

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


def _clear_env(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SPINE_LIVE_PROVIDER", "SPINE_LIVE_MODEL"):
        monkeypatch.delenv(var, raising=False)


def test_live_without_key_exits_2_and_writes_nothing(monkeypatch, tmp_path, capsys):
    _clear_env(monkeypatch)
    assert main(["--live", "--out", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err and "OPENAI_API_KEY" in err
    assert list(tmp_path.iterdir()) == []


def test_provider_auto_selection(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert live.live_provider() == "openai"
    assert type(live.build_live_client()).__name__ == "OpenAIModelClient"
    assert live.build_live_client().config.model == "gpt-6-luna"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert live.live_provider() == "anthropic"  # anthropic wins when both set
    assert type(live.build_live_client()).__name__ == "AnthropicModelClient"


def test_provider_explicit_and_model_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("SPINE_LIVE_PROVIDER", "openai")
    monkeypatch.setenv("SPINE_LIVE_MODEL", "gpt-x")
    client = live.build_live_client()
    assert (type(client).__name__, client.config.model) == ("OpenAIModelClient", "gpt-x")
    monkeypatch.setenv("SPINE_LIVE_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="SPINE_LIVE_PROVIDER"):
        live.build_live_client()


def test_explicit_provider_missing_its_key_exits_2(monkeypatch, tmp_path, capsys):
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("SPINE_LIVE_PROVIDER", "openai")
    assert main(["--live", "--out", str(tmp_path)]) == 2
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_summary_records_provider_and_uses_its_prices(monkeypatch, tmp_path):
    def handler(request):
        text = '{"score": 0.8, "reason": "ok"}' if JUDGE_MARKER in json.loads(
            request.content
        )["messages"][0]["content"] else "x"
        return httpx.Response(
            200,
            json={
                "model": "gpt-6-luna",
                "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0},
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAIModelClient(api_key="k", client=http)
    monkeypatch.setattr(live, "build_live_client", lambda: client)
    summary = live.run_all(True, tmp_path, "d", names=["classification"], limit=1)
    assert summary["provider"] == "openai"
    assert summary["usage"]["cost_usd"] == pytest.approx(0.10 * summary["usage"]["calls"])
    assert json.loads((tmp_path / "d" / "summary.json").read_text())["provider"] == "openai"
