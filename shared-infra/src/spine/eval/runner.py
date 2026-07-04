"""Eval runner: execute a predictor over a dataset and aggregate metrics.

A predictor is any ``Callable[[input], Prediction]`` — a plain function or a
spine ``Agent`` adapted via :func:`agent_predictor`. The runner scores every
example with every metric and aggregates per-metric mean scores and pass rates.
"""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from spine.agent import Agent
from spine.eval.dataset import GoldenDataset, GoldenExample
from spine.eval.metrics import Metric, MetricResult, Prediction

Predictor = Callable[[Any], Prediction]


@dataclass
class ExampleResult:
    """Every metric's result for a single example."""

    example_id: str
    metrics: dict[str, MetricResult] = field(default_factory=dict)


@dataclass
class EvalResult:
    """Aggregated outcome of a run over a dataset."""

    dataset_name: str
    dataset_version: str
    n_examples: int
    mean_scores: dict[str, float] = field(default_factory=dict)
    pass_rates: dict[str, float] = field(default_factory=dict)
    per_example: list[ExampleResult] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Compact JSON-serialisable summary (no per-example detail)."""
        return {
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "n_examples": self.n_examples,
            "mean_scores": self.mean_scores,
            "pass_rates": self.pass_rates,
        }


class EvalSuite:
    """A dataset + predictor + metrics, ready to run. The CLI builds one from a
    factory dotted-path; tests construct one directly."""

    def __init__(
        self,
        dataset: GoldenDataset,
        predict: Predictor,
        metrics: Sequence[Metric],
    ) -> None:
        self.dataset = dataset
        self.predict = predict
        self.metrics = list(metrics)

    def run(self) -> EvalResult:
        return run_eval(self.dataset, self.predict, self.metrics)


def run_eval(
    dataset: GoldenDataset,
    predict: Predictor,
    metrics: Sequence[Metric],
) -> EvalResult:
    """Score every example with every metric and aggregate the results."""
    per_example: list[ExampleResult] = []
    sums: dict[str, float] = {m.name: 0.0 for m in metrics}
    passes: dict[str, int] = {m.name: 0 for m in metrics}

    for example in dataset.examples:
        prediction = predict(example.input)
        row = ExampleResult(example_id=example.id)
        for metric in metrics:
            result = metric.score(example, prediction)
            row.metrics[metric.name] = result
            sums[metric.name] += result.score
            passes[metric.name] += int(result.passed)
        per_example.append(row)

    n = len(dataset.examples)
    mean_scores = {name: (total / n if n else 0.0) for name, total in sums.items()}
    pass_rates = {name: (count / n if n else 0.0) for name, count in passes.items()}

    return EvalResult(
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        n_examples=n,
        mean_scores=mean_scores,
        pass_rates=pass_rates,
        per_example=per_example,
    )


def agent_predictor(
    agent: Agent,
    parse: Callable[[str], Prediction] | None = None,
) -> Predictor:
    """Adapt a spine ``Agent`` into a predictor.

    Runs ``agent.run(input)`` and turns the response text into a
    :class:`Prediction` via ``parse`` (defaults to :func:`parse_json_prediction`,
    which reads a JSON object out of the agent's reply).
    """
    parse = parse or parse_json_prediction

    def predict(agent_input: Any) -> Prediction:
        text = agent.run(str(agent_input))
        return parse(text)

    return predict


def load_suite(dotted_path: str) -> EvalSuite:
    """Import and call a ``"module:factory"`` path returning an :class:`EvalSuite`.

    The factory must be callable with no arguments (defaults are fine). Used by
    the CLI and gate to build a suite from a config string without hard-coding it.
    """
    if ":" not in dotted_path:
        raise ValueError(f"suite path must be 'module:factory', got {dotted_path!r}")
    module_name, factory_name = dotted_path.split(":", 1)
    module = importlib.import_module(module_name)
    try:
        factory = getattr(module, factory_name)
    except AttributeError as exc:
        raise ValueError(f"{module_name!r} has no attribute {factory_name!r}") from exc
    suite = factory()
    if not isinstance(suite, EvalSuite):
        raise TypeError(f"{dotted_path!r} did not return an EvalSuite (got {type(suite).__name__})")
    return suite


def parse_json_prediction(text: str) -> Prediction:
    """Parse an agent reply into a :class:`Prediction`.

    Extracts the first ``{...}`` JSON object from ``text``; its ``tool_calls``
    key (if any) becomes ``Prediction.tool_calls`` and the remaining keys become
    ``Prediction.output``. A reply with no JSON yields an empty output with the
    raw text preserved for the LLM judge.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return Prediction(output={}, tool_calls=(), text=text)
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return Prediction(output={}, tool_calls=(), text=text)
    if not isinstance(obj, dict):
        return Prediction(output={}, tool_calls=(), text=text)

    tool_calls = tuple(obj.pop("tool_calls", ()) or ())
    return Prediction(output=obj, tool_calls=tool_calls, text=text)


def prediction_from_expected(example: GoldenExample) -> Prediction:
    """A perfect predictor's output for an example. Handy for baselines/tests."""
    output = dict(example.expected)
    tool_calls = tuple(output.get("tool_calls", ()) or ())
    text = json.dumps(output)
    return Prediction(output=output, tool_calls=tool_calls, text=text)
