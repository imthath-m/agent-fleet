"""Triage-specific eval metrics. Everything generic lives in `spine.eval.metrics`.

`spine.guardrails.CitationGuard` counts citations; `GroundingRate` checks they
are real. That distinction is the whole point — an agent that invents a
plausible `doc_id` satisfies the guard and fails this metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spine.eval.metrics import MetricResult, Prediction
from spine.rag import Retriever

from triage.kb import check_grounding


@dataclass
class GroundingRate:
    """1.0 when the prediction cites at least one doc and every id resolves.

    No citations scores 0.0: an uncited answer is ungrounded by definition, not
    vacuously grounded. `detail["unresolved"]` names the ids that did not exist.
    """

    retriever: Retriever
    citations_key: str = "citations"
    name: str = "grounding_rate"

    def score(self, example: Any, prediction: Prediction) -> MetricResult:
        citations = list(prediction.output.get(self.citations_key) or [])
        unresolved = check_grounding(self.retriever, citations) if citations else []
        grounded = bool(citations) and not unresolved
        return MetricResult(
            name=self.name,
            score=1.0 if grounded else 0.0,
            passed=grounded,
            detail={"citations": citations, "unresolved": unresolved},
        )


PRECISION_KEY = "escalation_precision"
RECALL_KEY = "escalation_recall"


@dataclass
class EscalationPrecisionRecall:
    """Exact match on `expected["escalated"]`, plus a running confusion matrix.

    Per-example scoring has to be a mean, and precision/recall are not means —
    so the score is the exact match (the gate's single number) and the
    aggregate lives in `detail`, where the last example's detail carries the
    whole dataset's matrix. `triage.eval.suites.build_escalation_suite` lifts
    `aggregate()` into `mean_scores` so both numbers are printed and gated.

    Recall is the one to watch: a missed escalation is the expensive error.
    """

    field_name: str = "escalated"
    name: str = "escalation_accuracy"
    counts: dict[str, int] = field(
        default_factory=lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    )

    def reset(self) -> None:
        """Zero the matrix so one metric instance can score several runs."""
        self.counts.update(tp=0, fp=0, fn=0, tn=0)

    def score(self, example: Any, prediction: Prediction) -> MetricResult:
        want = bool(example.expected.get(self.field_name))
        got = bool(prediction.output.get(self.field_name))
        if want:
            self.counts["tp" if got else "fn"] += 1
        else:
            self.counts["fp" if got else "tn"] += 1
        correct = want == got
        return MetricResult(
            name=self.name,
            score=1.0 if correct else 0.0,
            passed=correct,
            detail={
                "expected": want,
                "got": got,
                "reason": prediction.output.get("reason", ""),
                **self.counts,
                **self.aggregate(),
            },
        )

    def aggregate(self) -> dict[str, float]:
        """Precision and recall over everything scored so far.

        An empty denominator scores 1.0: a run with nothing to escalate has not
        got anything wrong.
        """
        tp, fp, fn = self.counts["tp"], self.counts["fp"], self.counts["fn"]
        return {
            PRECISION_KEY: tp / (tp + fp) if tp + fp else 1.0,
            RECALL_KEY: tp / (tp + fn) if tp + fn else 1.0,
        }
