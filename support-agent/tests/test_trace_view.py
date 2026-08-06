from spine.tracing import configure_tracing

from triage.pipeline import TriageAgent
from triage.schemas import Ticket
from triage.trace_view import span_tree


def _ticket() -> Ticket:
    return Ticket(
        ticket_id="TK-TRACE-1",
        text="I need to add a new user account on Ubuntu and put that username in a group.",
        channel="email",
        customer_id="cust-trace-1",
        subject="How do I add a user to a group?",
        received_at="2026-03-01T09:00:00Z",
    )


def _flatten(nodes):
    for n in nodes:
        yield n
        yield from _flatten(n["children"])


def test_root_is_request_containing_every_stage_span():
    exporter = configure_tracing()
    TriageAgent().run(_ticket())

    tree = span_tree(exporter)
    assert len(tree) == 1
    root = tree[0]
    assert root["name"] == "request"
    assert root["step"] == "request"
    assert root["depth"] == 0

    by_name = {n["name"]: n for n in _flatten(tree)}
    for name in ("classify", "retrieval", "resolve", "output_guardrail"):
        assert name in by_name, f"missing {name} in {sorted(by_name)}"
        assert by_name[name]["step"] is not None
        assert by_name[name]["depth"] == 1


def test_leaf_node_has_no_children_and_a_latency():
    exporter = configure_tracing()
    TriageAgent().run(_ticket())
    tree = span_tree(exporter)
    leaf = next(n for n in _flatten(tree) if n["name"] == "classify")
    assert leaf["children"] == []
    assert leaf["latency_ms"] is not None and leaf["latency_ms"] >= 0


def test_tool_span_step_is_tool_call_not_the_span_name():
    # Order-lookup ticket: exercises a `tool.order_lookup` child span.
    exporter = configure_tracing()
    ticket = Ticket(
        ticket_id="TK-TRACE-2",
        text="Order ORD-1001: how do I add a user to a group?",
        channel="email",
        customer_id="cust-trace-2",
        subject="Order ORD-1001 question",
        received_at="2026-03-01T09:00:00Z",
    )
    TriageAgent().run(ticket)
    tree = span_tree(exporter)
    tool_node = next(n for n in _flatten(tree) if n["name"] == "tool.order_lookup")
    assert tool_node["step"] == "tool_call"
