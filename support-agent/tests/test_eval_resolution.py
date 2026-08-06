from spine.eval.metrics import Prediction
from spine.eval.runner import EvalSuite, load_suite

from triage import config
from triage.eval.metrics import GroundingRate
from triage.eval.suites import RESOLUTION_REQUIRED_FIELDS, build_resolution_suite
from triage.kb import load_kb

SUITE_PATH = "triage.eval.suites:build_resolution_suite"

# Phase 3 exit criteria. Never lower these to make a run pass.
MIN_GROUNDING_RATE = 0.90
MIN_LLM_JUDGE = 0.70
MIN_EXAMPLES = 15


# --------------------------------------------------------------------------- #
# Suite construction
# --------------------------------------------------------------------------- #


def test_suite_factory_is_loadable_by_dotted_path():
    assert isinstance(load_suite(SUITE_PATH), EvalSuite)


def test_dataset_is_big_enough_and_labels_real_kb_docs():
    retriever = load_kb()
    dataset = build_resolution_suite().dataset

    assert len(dataset) >= MIN_EXAMPLES
    for example in dataset:
        assert set(RESOLUTION_REQUIRED_FIELDS) <= set(example.expected)
        for doc_id in example.expected["citations"]:
            # A label naming a doc the KB does not hold would be unreachable,
            # which is a broken label rather than a wrong agent.
            assert retriever.get(config.KB_NAMESPACE, doc_id) is not None, doc_id


# --------------------------------------------------------------------------- #
# Phase 3 exit criteria
# --------------------------------------------------------------------------- #


def test_resolution_suite_meets_its_thresholds():
    result = build_resolution_suite().run()

    assert result.mean_scores["schema_pass_rate"] == 1.0
    assert result.mean_scores["grounding_rate"] >= MIN_GROUNDING_RATE
    assert result.mean_scores["llm_judge"] >= MIN_LLM_JUDGE


def test_every_answer_cites_only_real_kb_docs():
    result = build_resolution_suite().run()

    for row in result.per_example:
        grounding = row.metrics["grounding_rate"]
        assert grounding.detail["citations"], row.example_id
        assert grounding.detail["unresolved"] == [], row.example_id


def test_one_fabricated_citation_collapses_the_grounding_rate():
    # The metric's reason to exist: CitationGuard counts this citation and
    # passes, because a fabricated id is still an id.
    suite = build_resolution_suite()
    example = suite.dataset.examples[0]
    grounding = GroundingRate(retriever=load_kb())
    fabricated = Prediction(output={"answer": "made up", "citations": ["not-a-real-doc#0"]})

    assert grounding.score(example, suite.predict(example.input)).score == 1.0
    assert grounding.score(example, fabricated).score == 0.0
