"""A self-contained demo eval suite over the packaged golden dataset.

Everything here is deterministic and SDK-free: the predictor is a lookup over the
dataset and the LLM judge is driven by a :class:`~spine.models.FakeModelClient`,
so ``python -m spine.eval`` runs locally with no model, creds, or network. The
``build_suite`` factory is what the CLI/gate load via ``spine.eval.example:build_suite``.
"""

from __future__ import annotations

import json
from typing import Any

from spine.eval.dataset import GoldenDataset, example_dataset_path, load_dataset
from spine.eval.metrics import (
    FieldAccuracy,
    LlmJudge,
    Metric,
    Prediction,
    SchemaPassRate,
    ToolCallCorrectness,
)
from spine.eval.runner import EvalSuite, Predictor, prediction_from_expected
from spine.models import FakeModelClient


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def demo_judge_client() -> FakeModelClient:
    """A deterministic judge: full marks when the answer echoes the reference."""

    def respond(prompt: str) -> str:
        # The prompt embeds both the reference and the agent answer; a faithful
        # answer repeats the reference text, a degraded one does not.
        _, _, tail = prompt.partition("Reference / expected:")
        reference, _, answer = tail.partition("Agent answer:")
        reference = reference.strip().splitlines()[0] if reference.strip() else ""
        score = 1.0 if reference and reference in answer else 0.2
        return json.dumps({"score": score, "reason": "demo judge"})

    return FakeModelClient(responder=respond)


def support_metrics(judge_client: FakeModelClient | None = None) -> list[Metric]:
    client = judge_client or demo_judge_client()
    return [
        FieldAccuracy(fields=["category", "priority"]),
        SchemaPassRate(required_fields=["category", "priority", "answer"]),
        ToolCallCorrectness(),
        LlmJudge(client=client, reference_key="answer"),
    ]


def _perfect_predictor(dataset: GoldenDataset) -> Predictor:
    by_input = {_key(ex.input): ex for ex in dataset}

    def predict(agent_input: Any) -> Prediction:
        return prediction_from_expected(by_input[_key(agent_input)])

    return predict


def _degraded_predictor(dataset: GoldenDataset) -> Predictor:
    """A worse agent: mislabels category and gives an unrelated answer."""
    by_input = {_key(ex.input): ex for ex in dataset}

    def predict(agent_input: Any) -> Prediction:
        ex = by_input[_key(agent_input)]
        output = dict(ex.expected)
        output["category"] = "other"  # wrong -> FieldAccuracy drops
        output["answer"] = "I am not sure how to help with that."  # judge drops
        tool_calls = tuple(output.get("tool_calls", ()) or ())
        return Prediction(output=output, tool_calls=tool_calls, text=json.dumps(output))

    return predict


def build_suite(
    *,
    degrade: bool = False,
    judge_client: FakeModelClient | None = None,
    dataset_path: Any | None = None,
) -> EvalSuite:
    """Build the demo support-resolution eval suite.

    ``degrade=True`` swaps in a deliberately worse predictor so the gate can be
    shown to trip against a baseline captured from the good one.
    """
    dataset = load_dataset(dataset_path or example_dataset_path())
    predict = _degraded_predictor(dataset) if degrade else _perfect_predictor(dataset)
    return EvalSuite(dataset, predict, support_metrics(judge_client))


def degraded_suite() -> EvalSuite:
    """No-arg factory for the deliberately-worse suite (for CLI/gate demos)."""
    return build_suite(degrade=True)
