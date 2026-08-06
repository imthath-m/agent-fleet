import io
import json

from spine.logging import get_logger
from spine.models import FakeModelClient
from spine.tracing import ATTR_STEP, StepType, configure_tracing

from triage import config
from triage.actions import find_amount, find_order_id, plan_actions, wants_refund
from triage.classifier import classify
from triage.fakes import classifier_responder, resolver_responder
from triage.kb import load_kb
from triage.resolver import resolve
from triage.schemas import Classification, Resolution, Ticket
from triage.tools.order_lookup import ORDERS_PATH

RETRIEVER = load_kb()


def _ticket(text, subject="Support request", ticket_id="TK-4001"):
    return Ticket(
        ticket_id=ticket_id,
        text=text,
        channel="email",
        customer_id="cust-4001",
        subject=subject,
        received_at="2026-02-10T09:00:00Z",
    )


def _triage(ticket, logger=None):
    """Classify then resolve for real, so the plan runs on true stage output."""
    log = logger or get_logger("test.actions", stream=io.StringIO())
    classification, _ = classify(
        ticket, model=FakeModelClient(responder=classifier_responder), logger=log
    )
    resolution, _ = resolve(
        ticket,
        classification,
        retriever=RETRIEVER,
        model=FakeModelClient(responder=resolver_responder),
        logger=log,
    )
    return classification, resolution


def _plan(ticket, logger=None):
    classification, resolution = _triage(ticket, logger)
    return plan_actions(ticket, classification, resolution, logger=logger)


def _tools(actions):
    return [a.tool for a in actions]


# --------------------------------------------------------------------------- #
# Argument extraction
# --------------------------------------------------------------------------- #


def test_find_order_id():
    assert find_order_id("please check ord-1001 for me") == "ORD-1001"
    assert find_order_id("no order here") is None


def test_find_amount_needs_a_currency_marker():
    assert find_amount("refund $49.00 please") == 49.0
    assert find_amount("refund 25 USD please") == 25.0
    # Bare numbers are version strings and disk sizes, not money.
    assert find_amount("I am on Ubuntu 24.04 with 16 GB of RAM") == 0.0


def test_wants_refund():
    assert wants_refund("I would like a refund")
    assert wants_refund("please reimburse me")
    assert not wants_refund("my wifi keeps dropping")


# --------------------------------------------------------------------------- #
# Routing rules — one test per rule
# --------------------------------------------------------------------------- #


def test_order_id_routes_to_order_lookup():
    actions, errors = _plan(_ticket("What is the status of order ORD-1001?", "Order status"))
    assert _tools(actions) == ["order_lookup"]
    assert errors == 0
    assert actions[0].args == {"order_id": "ORD-1001"}


def test_refund_language_routes_to_issue_refund():
    actions, errors = _plan(
        _ticket("I was charged twice for ORD-1001, please refund $49.00.", "Duplicate charge")
    )
    assert _tools(actions) == ["order_lookup", "issue_refund"]
    assert errors == 0
    refund = actions[1]
    assert refund.args == {
        "order_id": "ORD-1001",
        "amount": 49.0,
        "reason": "Duplicate charge",
    }


def test_complaint_routes_to_crm_update():
    actions, errors = _plan(
        _ticket(
            "This is absolutely unacceptable, the third time I have written and nobody replies.",
            "Fed up with support",
        )
    )
    assert _tools(actions) == ["crm_update"]
    assert errors == 0
    assert actions[0].args["ticket_id"] == "TK-4001"
    assert "complaint" in actions[0].args["tags"]


def test_ungrounded_resolution_routes_to_kb_search():
    # Nothing in the Ubuntu corpus matches, so the resolver grounds nothing and
    # the proposed next step is a broader search.
    ticket = _ticket("qwertyuiop zxcvbnm flibbertigibbet", "Zzyzx")
    _, resolution = _triage(ticket)
    assert resolution.grounded is False

    actions, errors = _plan(ticket)
    assert _tools(actions) == ["kb_search"]
    assert errors == 0


def test_a_plain_answerable_ticket_proposes_nothing():
    actions, errors = _plan(
        _ticket("How do I add a user to a group on Ubuntu?", "Add a user to a group")
    )
    assert actions == []
    assert errors == 0


# --------------------------------------------------------------------------- #
# Risk tiers and the no-execution guarantee
# --------------------------------------------------------------------------- #


def test_high_risk_action_is_never_auto_executed():
    before = ORDERS_PATH.read_bytes()

    actions, _ = _plan(
        _ticket(
            "This is unacceptable. Refund $49.00 for ORD-1001 immediately.",
            "Refund ORD-1001",
        )
    )

    high_risk = [a for a in actions if a.tool in config.HIGH_RISK_TOOLS]
    assert {a.tool for a in high_risk} == {"issue_refund", "crm_update"}
    for action in high_risk:
        assert action.executed is False
        assert action.risk == "high"

    # Read-only tools did run; nothing this package can reach was mutated.
    low_risk = [a for a in actions if a.tool not in config.HIGH_RISK_TOOLS]
    assert low_risk and all(a.executed is True and a.risk == "low" for a in low_risk)
    assert ORDERS_PATH.read_bytes() == before


def test_tool_span_emitted_per_call():
    exporter = configure_tracing()
    ticket = _ticket(
        "This is unacceptable. Refund $49.00 for ORD-1001 immediately.",
        "Refund ORD-1001",
    )
    classification, resolution = _triage(ticket)

    exporter.clear()
    actions, _ = plan_actions(ticket, classification, resolution)

    tool_spans = [s for s in exporter.get_finished_spans() if s.name.startswith("tool.")]
    assert [s.name for s in tool_spans] == [f"tool.{a.tool}" for a in actions]
    assert len(tool_spans) == len(actions)
    for span in tool_spans:
        assert span.attributes[ATTR_STEP] == StepType.TOOL_CALL


def test_repeat_run_produces_identical_idempotency_keys():
    ticket = _ticket(
        "This is unacceptable. Refund $49.00 for ORD-1001 immediately.",
        "Refund ORD-1001",
    )
    first, _ = _plan(ticket)
    second, _ = _plan(ticket)

    assert first == second
    assert [a.idempotency_key for a in first] == [a.idempotency_key for a in second]
    assert len({a.idempotency_key for a in first}) == len(first)


# --------------------------------------------------------------------------- #
# tool_errors
# --------------------------------------------------------------------------- #


def test_a_refund_with_no_amount_counts_a_tool_error():
    actions, errors = _plan(
        _ticket("Please refund me for order ORD-1001, I never got it.", "Refund please")
    )
    assert errors == 1
    assert "issue_refund" not in _tools(actions)
    # The rest of the plan still stands.
    assert _tools(actions) == ["order_lookup"]


def test_a_refund_for_an_unknown_order_counts_a_tool_error():
    actions, errors = _plan(_ticket("Refund $49.00 for order ORD-9999 please.", "Refund"))
    assert errors == 1
    assert _tools(actions) == ["order_lookup"]
    assert actions[0].args == {"order_id": "ORD-9999"}


def test_tool_calls_are_logged_with_the_tool_name():
    stream = io.StringIO()
    logger = get_logger("test.actions.logging", stream=stream)
    _plan(_ticket("Refund $49.00 for ORD-1001.", "Refund ORD-1001"), logger=logger)

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    tools_logged = {line["tool"] for line in lines if line.get("tool")}
    assert tools_logged == {"order_lookup", "issue_refund"}


# --------------------------------------------------------------------------- #
# plan_actions makes no model call
# --------------------------------------------------------------------------- #


def test_planning_is_deterministic_plain_code():
    # Hand-built stage output: no classifier, no resolver, no model anywhere.
    ticket = _ticket("Refund $49.00 for ORD-1001.", "Refund ORD-1001")
    classification = Classification("billing", "normal", "other", "neutral", False)
    resolution = Resolution(
        answer="ok",
        citations=["AddUsersHowto#0"],
        grounded=True,
        retrieval_score=0.9,
    )

    actions, errors = plan_actions(ticket, classification, resolution)
    assert _tools(actions) == ["order_lookup", "issue_refund"]
    assert errors == 0
