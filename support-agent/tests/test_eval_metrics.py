from spine.eval.dataset import GoldenExample
from spine.eval.metrics import Metric, Prediction

from triage import config
from triage.eval.metrics import (
    PRECISION_KEY,
    RECALL_KEY,
    EscalationPrecisionRecall,
    GroundingRate,
)
from triage.kb import load_kb

RETRIEVER = load_kb()
EXAMPLE = GoldenExample(id="ex-1", input="how do I add a user", expected={"answer": "use adduser"})

REAL_DOC_ID = RETRIEVER.query(config.KB_NAMESPACE, "sudo", top_k=1)[0].doc_id


def score(citations):
    return GroundingRate(retriever=RETRIEVER).score(
        EXAMPLE, Prediction(output={"answer": "a", "citations": citations})
    )


# --------------------------------------------------------------------------- #
# Protocol conformance
# --------------------------------------------------------------------------- #


def test_grounding_rate_satisfies_the_metric_protocol():
    assert isinstance(GroundingRate(retriever=RETRIEVER), Metric)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def test_real_citation_scores_one():
    result = score([REAL_DOC_ID])

    assert result.score == 1.0
    assert result.passed
    assert result.detail["unresolved"] == []


def test_fabricated_citation_scores_zero_and_is_named_in_detail():
    result = score([REAL_DOC_ID, "not-a-real-doc#0"])

    assert result.score == 0.0
    assert not result.passed
    assert result.detail["unresolved"] == ["not-a-real-doc#0"]


def test_no_citations_scores_zero():
    result = score([])

    assert result.score == 0.0
    assert result.detail["unresolved"] == []


def test_missing_citations_key_scores_zero():
    result = GroundingRate(retriever=RETRIEVER).score(EXAMPLE, Prediction(output={"answer": "a"}))

    assert result.score == 0.0


# --------------------------------------------------------------------------- #
# Escalation precision / recall
# --------------------------------------------------------------------------- #


def _feed(metric: EscalationPrecisionRecall, pairs: list[tuple[bool, bool]]) -> None:
    """Score `(expected, predicted)` pairs through the metric in order."""
    for want, got in pairs:
        metric.score(
            GoldenExample(id="x", input="t", expected={"escalated": want}),
            Prediction(output={"escalated": got}),
        )


def test_escalation_metric_satisfies_the_metric_protocol():
    assert isinstance(EscalationPrecisionRecall(), Metric)


def test_per_example_score_is_exact_match():
    metric = EscalationPrecisionRecall()

    hit = metric.score(
        GoldenExample(id="x", input="t", expected={"escalated": True}),
        Prediction(output={"escalated": True}),
    )
    miss = metric.score(
        GoldenExample(id="y", input="t", expected={"escalated": True}),
        Prediction(output={"escalated": False}),
    )

    assert (hit.score, hit.passed) == (1.0, True)
    assert (miss.score, miss.passed) == (0.0, False)


def test_aggregate_counts_the_confusion_matrix():
    metric = EscalationPrecisionRecall()

    # 2 true positives, 1 false positive, 1 false negative, 1 true negative.
    _feed(metric, [(True, True), (True, True), (False, True), (True, False), (False, False)])

    assert metric.counts == {"tp": 2, "fp": 1, "fn": 1, "tn": 1}
    assert metric.aggregate() == {PRECISION_KEY: 2 / 3, RECALL_KEY: 2 / 3}


def test_reset_clears_the_matrix_between_runs():
    metric = EscalationPrecisionRecall()
    _feed(metric, [(True, False)])

    metric.reset()
    _feed(metric, [(True, True)])

    assert metric.aggregate() == {PRECISION_KEY: 1.0, RECALL_KEY: 1.0}


def test_nothing_to_escalate_is_not_a_failure():
    assert EscalationPrecisionRecall().aggregate() == {PRECISION_KEY: 1.0, RECALL_KEY: 1.0}
