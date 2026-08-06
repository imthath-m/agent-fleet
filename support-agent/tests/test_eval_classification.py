from spine.eval.runner import EvalSuite, load_suite

from triage.eval.suites import CLASSIFICATION_REQUIRED_FIELDS, build_classification_suite
from triage.schemas import INTENTS, PRIORITIES, PRODUCT_AREAS, SENTIMENTS

SUITE_PATH = "triage.eval.suites:build_classification_suite"

# Phase 2 exit criteria. Never lower these to make a run pass.
MIN_FIELD_ACCURACY = 0.90
MIN_EXAMPLES = 15


# --------------------------------------------------------------------------- #
# Suite construction
# --------------------------------------------------------------------------- #


def test_suite_factory_is_loadable_by_dotted_path():
    # load_suite requires a no-arg factory; this is what the CLI and gate call.
    assert isinstance(load_suite(SUITE_PATH), EvalSuite)


def test_dataset_is_big_enough_and_covers_every_enum_value():
    dataset = build_classification_suite().dataset

    assert len(dataset) >= MIN_EXAMPLES
    for field, vocabulary in (
        ("intent", INTENTS),
        ("priority", PRIORITIES),
        ("product_area", PRODUCT_AREAS),
        ("sentiment", SENTIMENTS),
    ):
        labelled = {ex.expected[field] for ex in dataset}
        assert labelled == set(vocabulary), f"{field} coverage: {labelled}"


# --------------------------------------------------------------------------- #
# Phase 2 exit criteria
# --------------------------------------------------------------------------- #


def test_classification_suite_meets_its_thresholds():
    result = build_classification_suite().run()

    assert result.mean_scores["schema_pass_rate"] == 1.0
    assert result.mean_scores["field_accuracy"] >= MIN_FIELD_ACCURACY


def test_every_prediction_carries_the_full_classification_schema():
    result = build_classification_suite().run()

    for row in result.per_example:
        assert row.metrics["schema_pass_rate"].detail["missing"] == []
    assert "pii_flag" in CLASSIFICATION_REQUIRED_FIELDS
