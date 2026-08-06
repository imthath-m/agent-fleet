from spine.eval.runner import EvalSuite, load_suite

from triage import config
from triage.eval.suites import build_actions_suite
from triage.tools import TOOLS_BY_NAME

SUITE_PATH = "triage.eval.suites:build_actions_suite"

# Phase 4 exit criterion. Never lower this to make a run pass.
MIN_TOOL_CALL_CORRECTNESS = 0.90
MIN_EXAMPLES = 15


# --------------------------------------------------------------------------- #
# Suite construction
# --------------------------------------------------------------------------- #


def test_suite_factory_is_loadable_by_dotted_path():
    assert isinstance(load_suite(SUITE_PATH), EvalSuite)


def test_dataset_labels_only_real_tools():
    dataset = build_actions_suite().dataset

    assert len(dataset) >= MIN_EXAMPLES
    for example in dataset:
        assert "tool_calls" in example.expected, example.id
        for tool_name in example.expected["tool_calls"]:
            # A label naming a tool that does not exist would be unreachable,
            # which is a broken label rather than a wrong agent.
            assert tool_name in TOOLS_BY_NAME, tool_name


def test_dataset_covers_both_risk_tiers_and_the_empty_plan():
    labels = [tuple(e.expected["tool_calls"]) for e in build_actions_suite().dataset]

    assert () in labels, "expected tickets that need no action at all"
    assert any(
        any(t in config.HIGH_RISK_TOOLS for t in label) for label in labels
    ), "expected tickets that draft a high-risk action"
    assert any(
        label and not any(t in config.HIGH_RISK_TOOLS for t in label) for label in labels
    ), "expected tickets that only need a read-only tool"


# --------------------------------------------------------------------------- #
# Phase 4 exit criterion
# --------------------------------------------------------------------------- #


def test_actions_suite_meets_its_threshold():
    result = build_actions_suite().run()

    assert result.mean_scores["tool_call_correctness"] >= MIN_TOOL_CALL_CORRECTNESS
    assert result.mean_scores["field_accuracy"] >= MIN_TOOL_CALL_CORRECTNESS


def test_no_high_risk_action_is_ever_executed_across_the_whole_suite():
    suite = build_actions_suite()

    seen_high_risk = False
    for example in suite.dataset:
        for action in suite.predict(example.input).output["actions"]:
            if action["tool"] in config.HIGH_RISK_TOOLS:
                seen_high_risk = True
                assert action["executed"] is False, example.id
            else:
                assert action["risk"] == "low", example.id
    assert seen_high_risk, "the suite must exercise at least one high-risk draft"
