"""Run the five triage suites, on the fake model or against the real one.

Live runs write ``results/<date>/summary.json`` plus one ``<suite>.jsonl`` per
suite (one row per example: input, expected, prediction, error, metrics). They
are never compared to ``baselines/`` — those are fake-model numbers.

Fake mode scores identically to ``EvalSuite.run()`` and writes nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spine import models_anthropic, models_openai
from spine.eval.metrics import MetricResult
from spine.models import ModelClient, ModelConfig, ModelResponse, WrappedModelClient
from spine.models_anthropic import (
    ANTHROPIC_DEFAULT_CONFIG,
    AnthropicModelClient,
    MissingApiKeyError,
    config_for_model,
)
from spine.models_openai import OPENAI_DEFAULT_CONFIG, OpenAIModelClient

from triage import config
from triage.eval import suites

RESULTS_DIR = Path(__file__).resolve().parents[3] / "results"

SUITES: dict[str, Callable[..., Any]] = {
    "classification": suites.build_classification_suite,
    "resolution": suites.build_resolution_suite,
    "actions": suites.build_actions_suite,
    "escalation": suites.build_escalation_suite,
    "triage": suites.build_triage_suite,
}


def live_provider() -> str:
    """``SPINE_LIVE_PROVIDER`` (anthropic|openai), else whichever key is set
    (Anthropic first). Raises ``MissingApiKeyError`` if neither is."""
    provider = os.environ.get("SPINE_LIVE_PROVIDER", "").strip().lower()
    if provider in ("anthropic", "openai"):
        return provider
    if provider:
        raise ValueError(f"SPINE_LIVE_PROVIDER must be 'anthropic' or 'openai', got {provider!r}")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    raise MissingApiKeyError("neither ANTHROPIC_API_KEY nor OPENAI_API_KEY is set")


def build_live_client() -> ModelClient:
    """Real client for ``live_provider()``; model from ``SPINE_LIVE_MODEL`` or the default.

    Raises ``spine.models_anthropic.MissingApiKeyError`` without a key.
    """
    override = os.environ.get("SPINE_LIVE_MODEL")
    if live_provider() == "openai":
        model = override or OPENAI_DEFAULT_CONFIG.model
        return OpenAIModelClient(config=models_openai.config_for_model(model))
    model = override or ANTHROPIC_DEFAULT_CONFIG.model
    return AnthropicModelClient(config=config_for_model(model))


# --------------------------------------------------------------------------- #
# Usage tally (one per run; main and judge calls counted separately)
# --------------------------------------------------------------------------- #


@dataclass
class _Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = 0.0  # None once any call used a model with no known price
    price: Callable[[str, int, int], float | None] = models_anthropic.cost_usd

    def add(self, r: ModelResponse) -> None:
        self.calls += 1
        self.input_tokens += r.input_tokens
        self.output_tokens += r.output_tokens
        c = self.price(r.model, r.input_tokens, r.output_tokens)
        self.cost = None if c is None or self.cost is None else self.cost + c

    def to_dict(self) -> dict[str, Any]:
        cost = None if self.cost is None else round(self.cost, 6)
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": cost,
        }


class _Tally:
    """A ``ModelClient`` that records every successful response in ``usage``."""

    def __init__(self, inner: ModelClient, usage: _Usage) -> None:
        self._inner = inner
        self.usage = usage
        self.model = ""

    def generate(self, prompt: str, **params: object) -> ModelResponse:
        response = self._inner.generate(prompt, **params)
        self.model = self.model or response.model
        self.usage.add(response)
        return response


# --------------------------------------------------------------------------- #
# Per-example capture
# --------------------------------------------------------------------------- #


def _prediction_row(name: str, p: Any) -> dict[str, Any]:
    return {
        "text": p.text,
        "fields": p.output,
        "citations": p.output.get("citations"),
        "tool_calls": list(p.tool_calls) if name == "actions" or p.tool_calls else None,
        "escalated": p.output.get("escalated"),
    }


def _fail(metric: Any, exc: Exception) -> MetricResult:
    return MetricResult(metric.name, 0.0, False, {"error": f"{type(exc).__name__}: {exc}"})


def _run_suite(name: str, suite: Any, limit: int | None) -> tuple[dict[str, Any], list[dict]]:
    """Score every example; a failure is recorded on its row, never raised."""
    examples = suite.dataset.examples[:limit] if limit else suite.dataset.examples
    metrics = suite.metrics
    tracker = getattr(suite, "metric", None)  # escalation's confusion-matrix metric
    if tracker is not None:
        tracker.reset()
    sums = {m.name: 0.0 for m in metrics}
    passes = {m.name: 0 for m in metrics}
    rows: list[dict] = []

    for ex in examples:
        error: str | None = None
        prediction = None
        results: dict[str, MetricResult] = {}
        try:
            prediction = suite.predict(ex.input)
        except Exception as exc:  # any per-example failure is data
            error = f"{type(exc).__name__}: {exc}"
        for m in metrics:
            if prediction is None:
                results[m.name] = MetricResult(m.name, 0.0, False, {"error": error})
                continue
            try:
                results[m.name] = m.score(ex, prediction)
            except Exception as exc:
                results[m.name] = _fail(m, exc)
                error = error or results[m.name].detail["error"]
        for n, r in results.items():
            sums[n] += r.score
            passes[n] += int(r.passed)
        rows.append(
            {
                "suite": name,
                "example_id": ex.id,
                "input": ex.input,
                "expected": ex.expected,
                "tags": list(ex.tags),
                "prediction": _prediction_row(name, prediction) if prediction else None,
                "error": error,
                "metrics": {
                    n: {"score": r.score, "passed": r.passed, "detail": r.detail}
                    for n, r in results.items()
                },
            }
        )

    n = len(examples)
    mean_scores = {k: v / n if n else 0.0 for k, v in sums.items()}
    if tracker is not None:
        mean_scores.update(tracker.aggregate())
    summary = {
        "n_examples": n,
        "mean_scores": mean_scores,
        "pass_rates": {k: v / n if n else 0.0 for k, v in passes.items()},
        "n_errors": sum(1 for r in rows if r["error"]),
    }
    return summary, rows


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _fresh_dir(root: Path, date: str) -> Path:
    path, i = root / date, 1
    while path.exists():
        i += 1
        path = root / f"{date}-{i}"
    path.mkdir(parents=True)
    return path


def run_all(
    live: bool,
    out_root: Path = RESULTS_DIR,
    date: str | None = None,
    *,
    names: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run the suites; return the summary dict. Only ``live`` writes files."""
    names = names or list(SUITES)
    run_at = datetime.now(UTC)
    summary: dict[str, Any] = {"mode": "live" if live else "fake", "suites": {}}

    if not live:
        for name in names:
            summary["suites"][name], _ = _run_suite(name, SUITES[name](), limit)
        return summary

    base = build_live_client()  # raises before anything is written if no key
    cfg: ModelConfig = getattr(base, "config", config.MODEL_CONFIG)
    provider = {OpenAIModelClient: "openai", AnthropicModelClient: "anthropic"}.get(
        type(base), "other"
    )
    price = models_openai.cost_usd if provider == "openai" else models_anthropic.cost_usd
    main_usage, judge_usage = _Usage(price=price), _Usage(price=price)
    main = _Tally(base, main_usage)
    judge = _Tally(base, judge_usage)
    # Wrap here (once) so classify()/resolve()/TriageAgent do not re-wrap.
    main_client = WrappedModelClient(main, cfg)
    judge_client = WrappedModelClient(judge, cfg)

    out_dir = _fresh_dir(Path(out_root), date or run_at.strftime("%Y-%m-%d"))
    for name in names:
        kwargs: dict[str, Any] = {"model": main_client}
        if name == "resolution":
            kwargs["judge"] = judge_client
        suite_summary, rows = _run_suite(name, SUITES[name](**kwargs), limit)
        summary["suites"][name] = suite_summary
        text = "".join(json.dumps(r, default=str) + "\n" for r in rows)
        (out_dir / f"{name}.jsonl").write_text(text)

    total = _Usage(
        main_usage.calls + judge_usage.calls,
        main_usage.input_tokens + judge_usage.input_tokens,
        main_usage.output_tokens + judge_usage.output_tokens,
        None if None in (main_usage.cost, judge_usage.cost) else main_usage.cost + judge_usage.cost,
    )
    model_id = cfg.model if hasattr(base, "config") else (main.model or "unknown")
    summary = {
        "mode": "live",
        "provider": provider,
        "model": model_id,
        "judge_model": model_id,
        "run_at": run_at.isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "suites": summary["suites"],
        "usage": total.to_dict(),
        "judge_usage": judge_usage.to_dict(),
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    return summary
