from spine.hitl import EscalationItem
from spine.obs import MetricRecord

from triage.schemas import (
    Classification,
    ProposedAction,
    Resolution,
    Ticket,
    TriageResult,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _ticket() -> Ticket:
    return Ticket(
        ticket_id="t-1",
        text="my wifi keeps dropping",
        channel="email",
        customer_id="c-1",
        subject="wifi issue",
        received_at="2026-08-06T00:00:00Z",
    )


def _classification() -> Classification:
    return Classification(
        intent="technical",
        priority="high",
        product_area="networking",
        sentiment="frustrated",
        pii_flag=False,
    )


def _resolution() -> Resolution:
    return Resolution(
        answer="Restart NetworkManager and check driver logs.",
        citations=["networking-wifi#0"],
        grounded=True,
        retrieval_score=0.82,
    )


def _proposed_action() -> ProposedAction:
    return ProposedAction(
        tool="crm_update",
        args={"ticket_id": "t-1", "tags": ["networking"]},
        idempotency_key="abc123",
        risk="high",
        executed=False,
    )


def _triage_result() -> TriageResult:
    return TriageResult(
        request_id="r-1",
        trace_id="trace-1",
        ticket=_ticket(),
        classification=_classification(),
        resolution=_resolution(),
        proposed_actions=[_proposed_action()],
        escalation=EscalationItem(id="e-1", reason="low confidence", payload={"q": "hi"}),
        withheld=True,
        metric=MetricRecord(request_id="r-1", agent="triage-agent", latency_ms=12.5),
    )


# --------------------------------------------------------------------------- #
# Round-trip
# --------------------------------------------------------------------------- #


def test_every_schema_round_trips_through_dict():
    for x in (
        _ticket(),
        _classification(),
        _resolution(),
        _proposed_action(),
        _triage_result(),
    ):
        assert type(x).from_dict(x.to_dict()) == x


def test_triage_result_round_trips_with_none_fields():
    result = TriageResult(
        request_id="r-2",
        trace_id=None,
        ticket=_ticket(),
        classification=None,
        resolution=None,
        proposed_actions=[],
        escalation=None,
        withheld=False,
        metric=None,
    )
    assert TriageResult.from_dict(result.to_dict()) == result
