"""Eval suites for the triage agent.

Each factory is no-arg so `spine.eval.runner.load_suite` (and therefore
`python -m spine.eval run/baseline/gate --suite triage.eval.suites:<factory>`)
can build it from a dotted path.

The system under test is the real `classify()` — guards, spans and schema
validation included — driven by `FakeModelClient(responder=classifier_responder)`.
No network, no creds.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from spine.eval.dataset import load_dataset
from spine.eval.metrics import FieldAccuracy, Metric, Prediction, SchemaPassRate
from spine.eval.runner import EvalSuite
from spine.logging import get_logger
from spine.models import FakeModelClient

from triage.classifier import CLASSIFIED_FIELDS, classify
from triage.fakes import classifier_responder
from triage.schemas import Ticket

CLASSIFICATION_DATASET = (
    Path(__file__).resolve().parents[3] / "data" / "golden" / "classification.jsonl"
)

CLASSIFICATION_REQUIRED_FIELDS = [*CLASSIFIED_FIELDS, "pii_flag"]


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
