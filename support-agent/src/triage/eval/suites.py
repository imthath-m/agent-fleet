"""Eval suites for the triage agent.

Each factory is no-arg so `spine.eval.runner.load_suite` (and therefore
`python -m spine.eval run/baseline/gate --suite triage.eval.suites:<factory>`)
can build it from a dotted path.

The system under test is always the real stage — guards, spans and schema
validation included — driven by a `FakeModelClient`. No network, no creds.

The resolution suite's `llm_judge` is a keyword-overlap grader over the whole
retrieved context (see `triage.fakes.resolution_judge_client`), so what it
really measures is whether retrieval put the facts a correct answer needs in
front of the model. That is the resolver's job; judging prose is Phase 8's real
judge.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from spine.eval.dataset import load_dataset
from spine.eval.metrics import (
    FieldAccuracy,
    LlmJudge,
    Metric,
    Prediction,
    SchemaPassRate,
    ToolCallCorrectness,
)
from spine.eval.runner import EvalSuite
from spine.logging import get_logger
from spine.models import FakeModelClient

from triage.actions import plan_actions
from triage.classifier import CLASSIFIED_FIELDS, classify
from triage.eval.metrics import GroundingRate
from triage.fakes import classifier_responder, resolution_judge_client, resolver_responder
from triage.kb import load_kb
from triage.resolver import resolve
from triage.schemas import Ticket

_GOLDEN = Path(__file__).resolve().parents[3] / "data" / "golden"

CLASSIFICATION_DATASET = _GOLDEN / "classification.jsonl"
RESOLUTION_DATASET = _GOLDEN / "resolution.jsonl"
ACTIONS_DATASET = _GOLDEN / "actions.jsonl"

CLASSIFICATION_REQUIRED_FIELDS = [*CLASSIFIED_FIELDS, "pii_flag"]

RESOLUTION_REQUIRED_FIELDS = ["answer", "citations"]


def classification_metrics() -> list[Metric]:
    return [
        SchemaPassRate(required_fields=CLASSIFICATION_REQUIRED_FIELDS),
        FieldAccuracy(fields=list(CLASSIFIED_FIELDS)),
    ]


def build_classification_suite() -> EvalSuite:
    """Run every golden ticket through `classify()` and score the labels."""
    dataset = load_dataset(CLASSIFICATION_DATASET)
    model = FakeModelClient(responder=classifier_responder)
    # Discard the per-example structured logs: the eval CLI's stdout is the
    # summary, not a log stream.
    logger = get_logger("triage.eval.classification", stream=io.StringIO())

    def predict(agent_input: Any) -> Prediction:
        classification, _ = classify(Ticket.from_dict(agent_input), model=model, logger=logger)
        output = classification.to_dict()
        return Prediction(output=output, text=json.dumps(output))

    return EvalSuite(dataset, predict, classification_metrics())


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def resolution_metrics(retriever) -> list[Metric]:
    return [
        GroundingRate(retriever=retriever),
        LlmJudge(
            client=resolution_judge_client(),
            criterion="resolution correctness",
            reference_key="answer",
        ),
        SchemaPassRate(required_fields=RESOLUTION_REQUIRED_FIELDS),
    ]


def build_resolution_suite() -> EvalSuite:
    """Classify then resolve every golden ticket against the committed KB.

    The stages run composed rather than with hand-fed labels because
    `resolve()` steers retrieval with `classification.product_area` — scoring it
    on a classification the classifier would never produce would measure a
    pipeline that does not exist.
    """
    dataset = load_dataset(RESOLUTION_DATASET)
    retriever = load_kb()
    classifier_model = FakeModelClient(responder=classifier_responder)
    resolver_model = FakeModelClient(responder=resolver_responder)
    logger = get_logger("triage.eval.resolution", stream=io.StringIO())

    def predict(agent_input: Any) -> Prediction:
        ticket = Ticket.from_dict(agent_input)
        classification, _ = classify(ticket, model=classifier_model, logger=logger)
        resolution, _ = resolve(
            ticket,
            classification,
            retriever=retriever,
            model=resolver_model,
            logger=logger,
        )
        output = resolution.to_dict()
        # `text` is what the judge reads: the answer, not the serialized record.
        return Prediction(output=output, text=resolution.answer)

    return EvalSuite(dataset, predict, resolution_metrics(retriever))


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #


def actions_metrics() -> list[Metric]:
    """`ordered=False`: the routing rules fire in a fixed order, but which tools
    a ticket needs is the claim under test, not the sequence."""
    return [
        ToolCallCorrectness(ordered=False),
        FieldAccuracy(fields=["tool_errors"]),
    ]


def build_actions_suite() -> EvalSuite:
    """Classify, resolve, then plan actions for every golden ticket.

    Composed rather than hand-fed for the same reason as the resolution suite:
    `plan_actions` routes on `classification.intent`/`sentiment` and on whether
    the resolution grounded, so scoring it against labels the earlier stages
    would never produce would measure a pipeline that does not exist.

    `kb_search` is deliberately absent from every expected list. Its rule fires
    only when the KB grounded nothing at all, which a 382-chunk corpus and
    substring scoring make unreachable for realistic ticket text — that path is
    covered by `tests/test_actions.py` instead, where the input can be made
    genuinely unanswerable.
    """
    dataset = load_dataset(ACTIONS_DATASET)
    retriever = load_kb()
    classifier_model = FakeModelClient(responder=classifier_responder)
    resolver_model = FakeModelClient(responder=resolver_responder)
    logger = get_logger("triage.eval.actions", stream=io.StringIO())

    def predict(agent_input: Any) -> Prediction:
        ticket = Ticket.from_dict(agent_input)
        classification, _ = classify(ticket, model=classifier_model, logger=logger)
        resolution, _ = resolve(
            ticket,
            classification,
            retriever=retriever,
            model=resolver_model,
            logger=logger,
        )
        actions, tool_errors = plan_actions(ticket, classification, resolution, logger=logger)
        output = {
            "actions": [a.to_dict() for a in actions],
            "tool_errors": tool_errors,
        }
        return Prediction(
            output=output,
            tool_calls=tuple(a.tool for a in actions),
            text=json.dumps(output),
        )

    return EvalSuite(dataset, predict, actions_metrics())
