"""Triage-specific eval metrics. Everything generic lives in `spine.eval.metrics`.

`spine.guardrails.CitationGuard` counts citations; `GroundingRate` checks they
are real. That distinction is the whole point — an agent that invents a
plausible `doc_id` satisfies the guard and fails this metric.
"""

from __future__ import annotations

from dataclasses import dataclass
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
