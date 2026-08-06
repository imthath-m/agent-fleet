import pytest
from spine.tracing import ATTR_STEP, StepType, configure_tracing

from triage import config
from triage.kb import check_grounding
from triage.tools import TOOLS_BY_NAME, issue_refund, kb_search, order_lookup, risk_of
from triage.tools.kb_search import default_retriever
from triage.tools.order_lookup import ORDERS_PATH, order_exists

# --------------------------------------------------------------------------- #
# kb_search (4.1)
# --------------------------------------------------------------------------- #


def test_kb_search_returns_cited_passages():
    results = kb_search("how do I add a user to a group")

    assert results, "expected at least one passage from the committed KB"
    assert len(results) <= config.RETRIEVAL_TOP_K
    for row in results:
        assert set(row) == {"doc_id", "text", "source", "score"}
        assert row["text"] and row["source"]
        assert row["score"] > 0
    # Every returned doc_id is a real citation into the corpus.
    doc_ids = [row["doc_id"] for row in results]
    assert check_grounding(default_retriever(), doc_ids) == []


def test_kb_search_respects_top_k():
    assert len(kb_search("ubuntu network wifi install package", top_k=2)) <= 2


def test_kb_search_emits_a_tool_span():
    exporter = configure_tracing()
    kb_search("sudo permissions")
    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["tool.kb_search"]
    assert spans[0].attributes[ATTR_STEP] == StepType.TOOL_CALL


def test_kb_search_is_registered_as_a_low_risk_tool():
    assert TOOLS_BY_NAME["kb_search"].fn is kb_search
    assert risk_of("kb_search") == "low"


# --------------------------------------------------------------------------- #
# order_lookup (4.2)
# --------------------------------------------------------------------------- #


def test_order_lookup_known_and_unknown():
    known = order_lookup("ORD-1001")
    assert known["found"] is True
    assert known["order_id"] == "ORD-1001"
    assert known["amount"] > 0
    assert known["status"]

    # An unknown id is an ordinary support outcome, not a tool failure.
    unknown = order_lookup("ORD-9999")
    assert unknown == {"found": False, "order_id": "ORD-9999"}


def test_order_lookup_emits_a_tool_span():
    exporter = configure_tracing()
    order_lookup("ORD-1002")
    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["tool.order_lookup"]
    assert spans[0].attributes[ATTR_STEP] == StepType.TOOL_CALL


def test_order_lookup_never_writes_to_the_fixture_store():
    before = ORDERS_PATH.read_bytes()
    order_lookup("ORD-1001")
    order_lookup("ORD-9999")
    assert ORDERS_PATH.read_bytes() == before


def test_order_exists_matches_the_store():
    assert order_exists("ORD-1003")
    assert not order_exists("ORD-9999")


def test_order_lookup_is_registered_as_a_low_risk_tool():
    assert TOOLS_BY_NAME["order_lookup"].fn is order_lookup
    assert risk_of("order_lookup") == "low"


# --------------------------------------------------------------------------- #
# issue_refund (4.3) — high risk, drafts only
# --------------------------------------------------------------------------- #


def test_issue_refund_never_executes():
    before = ORDERS_PATH.read_bytes()

    action = issue_refund("ORD-1001", 49.0, "duplicate charge")

    assert action.executed is False
    assert action.risk == "high"
    assert action.tool == "issue_refund"
    assert action.args == {
        "order_id": "ORD-1001",
        "amount": 49.0,
        "reason": "duplicate charge",
    }
    # The only store this package can reach is byte-identical afterwards.
    assert ORDERS_PATH.read_bytes() == before


def test_issue_refund_idempotency_key_is_stable():
    first = issue_refund("ORD-1001", 49.0, "duplicate charge")
    same = issue_refund("ORD-1001", 49.0, "duplicate charge")
    assert first.idempotency_key == same.idempotency_key

    # Every arg, changed on its own, changes the key.
    assert issue_refund("ORD-1002", 49.0, "duplicate charge").idempotency_key != (
        first.idempotency_key
    )
    assert issue_refund("ORD-1001", 25.0, "duplicate charge").idempotency_key != (
        first.idempotency_key
    )
    assert issue_refund("ORD-1001", 49.0, "cancelled order").idempotency_key != (
        first.idempotency_key
    )


def test_issue_refund_validates_before_proposing():
    with pytest.raises(ValueError, match="positive"):
        issue_refund("ORD-1001", 0.0, "nothing to refund")
    with pytest.raises(ValueError, match="positive"):
        issue_refund("ORD-1001", -5.0, "negative refund")
    with pytest.raises(ValueError, match="unknown order_id"):
        issue_refund("ORD-9999", 49.0, "no such order")


def test_issue_refund_emits_a_tool_span():
    exporter = configure_tracing()
    issue_refund("ORD-1001", 49.0, "duplicate charge")
    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["tool.issue_refund"]
    assert spans[0].attributes[ATTR_STEP] == StepType.TOOL_CALL


def test_issue_refund_is_registered_as_a_high_risk_tool():
    assert TOOLS_BY_NAME["issue_refund"].fn is issue_refund
    assert risk_of("issue_refund") == "high"
    assert "issue_refund" in config.HIGH_RISK_TOOLS
