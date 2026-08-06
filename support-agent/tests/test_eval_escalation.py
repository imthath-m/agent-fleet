from spine.eval.runner import EvalSuite, load_suite

from triage.eval.metrics import PRECISION_KEY, RECALL_KEY
from triage.eval.suites import build_escalation_suite

SUITE_PATH = "triage.eval.suites:build_escalation_suite"

# Phase 5 exit criteria. Recall is the higher bar on purpose: a missed
# escalation reaches a customer, a spurious one only costs a reviewer a minute.
MIN_PRECISION = 0.80
MIN_RECALL = 0.90
MIN_EXAMPLES = 15


def test_suite_factory_is_loadable_by_dotted_path():
    assert isinstance(load_suite(SUITE_PATH), EvalSuite)


def test_dataset_labels_both_outcomes():
    dataset = build_escalation_suite().dataset

    assert len(dataset) >= MIN_EXAMPLES
    labels = [e.expected["escalated"] for e in dataset]
    assert True in labels and False in labels
    # A set that is nearly all escalations would make recall meaningless.
    assert 0.2 <= sum(labels) / len(labels) <= 0.5


def test_escalation_suite_meets_its_thresholds():
    result = build_escalation_suite().run()

    assert result.mean_scores[PRECISION_KEY] >= MIN_PRECISION
    assert result.mean_scores[RECALL_KEY] >= MIN_RECALL


def test_the_confusion_matrix_is_reported_in_the_metric_detail():
    suite = build_escalation_suite()
    result = suite.run()

    # The last example's detail carries the whole run's matrix.
    detail = result.per_example[-1].metrics["escalation_accuracy"].detail
    assert detail["tp"] + detail["fp"] + detail["fn"] + detail["tn"] == len(suite.dataset)
    assert detail[RECALL_KEY] == result.mean_scores[RECALL_KEY]

    # Re-running the same suite must not double-count.
    again = suite.run()
    assert again.mean_scores == result.mean_scores
