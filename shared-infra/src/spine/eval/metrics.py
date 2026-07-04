"""Eval metrics: deterministic scorers plus an LLM-as-judge.

Every metric scores one ``(GoldenExample, Prediction)`` pair into a
:class:`MetricResult` (score in ``[0, 1]``, higher is better, plus a boolean
``passed``). Deterministic metrics are plain code. The LLM judge scores against
the :class:`~spine.models.ModelClient` Protocol, so a ``FakeModelClient`` drives
it in tests with no real model call.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from spine.models import DEFAULT_CONFIG, ModelClient, ModelConfig


@dataclass
class Prediction:
    """An agent's structured output for one example.

    ``output`` holds the parsed fields deterministic metrics compare against
    ``expected``. ``tool_calls`` is the ordered list of tool names the agent
    invoked. ``text`` is the free-form response the LLM judge reads.
    """

    output: dict[str, Any] = field(default_factory=dict)
    tool_calls: tuple[str, ...] = ()
    text: str = ""


@dataclass
class MetricResult:
    """Score for one metric on one example."""

    name: str
    score: float
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Metric(Protocol):
    """A scorer over one labelled example and its prediction."""

    name: str

    def score(self, example: Any, prediction: Prediction) -> MetricResult: ...


# --------------------------------------------------------------------------- #
# Deterministic metrics
# --------------------------------------------------------------------------- #


@dataclass
class FieldAccuracy:
    """Fraction of ``fields`` whose predicted value equals the expected value.

    Fields absent from an example's ``expected`` are skipped for that example.
    ``pass_threshold`` is the minimum score counted as a pass.
    """

    fields: Sequence[str]
    pass_threshold: float = 1.0
    name: str = "field_accuracy"

    def score(self, example: Any, prediction: Prediction) -> MetricResult:
        checked = 0
        correct = 0
        mismatches: dict[str, Any] = {}
        for f in self.fields:
            if f not in example.expected:
                continue
            checked += 1
            want = example.expected[f]
            got = prediction.output.get(f)
            if got == want:
                correct += 1
            else:
                mismatches[f] = {"expected": want, "got": got}
        score = 1.0 if checked == 0 else correct / checked
        return MetricResult(
            name=self.name,
            score=score,
            passed=score >= self.pass_threshold,
            detail={"checked": checked, "correct": correct, "mismatches": mismatches},
        )


@dataclass
class SchemaPassRate:
    """Whether the prediction output contains every required field (score 1/0).

    Optionally enforce Python types via ``types`` (field -> type).
    """

    required_fields: Sequence[str]
    types: dict[str, type] | None = None
    name: str = "schema_pass_rate"

    def score(self, example: Any, prediction: Prediction) -> MetricResult:
        missing = [f for f in self.required_fields if f not in prediction.output]
        bad_types: dict[str, str] = {}
        if self.types:
            for f, typ in self.types.items():
                if f in prediction.output and not isinstance(prediction.output[f], typ):
                    bad_types[f] = type(prediction.output[f]).__name__
        ok = not missing and not bad_types
        return MetricResult(
            name=self.name,
            score=1.0 if ok else 0.0,
            passed=ok,
            detail={"missing": missing, "bad_types": bad_types},
        )


@dataclass
class ToolCallCorrectness:
    """Compare the agent's tool calls against ``expected['tool_calls']``.

    With ``ordered=False`` (default) the multiset of tool names must match; with
    ``ordered=True`` the exact sequence must match. Examples without an expected
    tool-call list are skipped (score 1.0).
    """

    expected_key: str = "tool_calls"
    ordered: bool = False
    name: str = "tool_call_correctness"

    def score(self, example: Any, prediction: Prediction) -> MetricResult:
        if self.expected_key not in example.expected:
            return MetricResult(self.name, 1.0, True, {"skipped": True})
        expected = list(example.expected[self.expected_key])
        got = list(prediction.tool_calls)
        if self.ordered:
            ok = expected == got
        else:
            ok = sorted(expected) == sorted(got)
        return MetricResult(
            name=self.name,
            score=1.0 if ok else 0.0,
            passed=ok,
            detail={"expected": expected, "got": got, "ordered": self.ordered},
        )


# --------------------------------------------------------------------------- #
# LLM-as-judge
# --------------------------------------------------------------------------- #

DEFAULT_JUDGE_TEMPLATE = """You are a strict evaluator for a support agent.
Judge the agent's answer for {criterion}.

User request:
{input}

Reference / expected:
{reference}

Agent answer:
{answer}

Reply with a JSON object: {{"score": <float 0..1>, "reason": "<short>"}}.
A score of 1.0 is perfect; 0.0 is unacceptable."""


def parse_judge_score(text: str) -> float:
    """Extract a ``[0, 1]`` score from a judge response.

    Accepts a JSON object with a ``score`` key, or a ``SCORE: <float>`` line.
    Raises ``ValueError`` if neither is found. The result is clamped to ``[0, 1]``.
    """
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "score" in obj:
            return _clamp(float(obj["score"]))
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    match = re.search(r"score[\"']?\s*[:=]\s*([01](?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        return _clamp(float(match.group(1)))
    raise ValueError(f"could not parse a judge score from: {text!r}")


@dataclass
class LlmJudge:
    """LLM-as-judge metric for domain quality (resolution correctness,
    hallucination, citation validity, ...).

    Builds a prompt from the example + prediction, calls a ``ModelClient``, and
    parses a numeric score. Deterministic in tests when driven by a
    ``FakeModelClient`` returning canned JSON scores.

    ``reference_key`` selects which ``expected`` field is shown to the judge as
    the reference answer (default ``"answer"``); falls back to the whole
    ``expected`` mapping when the key is absent.
    """

    client: ModelClient
    criterion: str = "resolution correctness"
    reference_key: str = "answer"
    pass_threshold: float = 0.7
    template: str = DEFAULT_JUDGE_TEMPLATE
    config: ModelConfig = DEFAULT_CONFIG
    name: str = "llm_judge"

    def score(self, example: Any, prediction: Prediction) -> MetricResult:
        reference = example.expected.get(self.reference_key, example.expected)
        prompt = self.template.format(
            criterion=self.criterion,
            input=example.input,
            reference=reference,
            answer=prediction.text,
        )
        response = self.client.generate(
            prompt,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
        )
        score = parse_judge_score(response.text)
        return MetricResult(
            name=self.name,
            score=score,
            passed=score >= self.pass_threshold,
            detail={"criterion": self.criterion, "raw": response.text},
        )


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))
