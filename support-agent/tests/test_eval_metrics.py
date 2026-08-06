from spine.eval.dataset import GoldenExample
from spine.eval.metrics import Metric, Prediction

from triage import config
from triage.eval.metrics import GroundingRate
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
