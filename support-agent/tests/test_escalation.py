import io

from spine.guardrails import Decision, GuardrailReport, GuardrailResult
from spine.hitl import HumanQueue
from spine.logging import get_logger

from triage.escalation import escalate, should_escalate
from triage.pipeline import TriageAgent
from triage.schemas import Classification, ProposedAction, Resolution, Ticket

# Baselines that escalate on nothing: every rule has to be switched on
# deliberately by the test that owns it.
CALM = Classification(
    intent="how_to",
    priority="normal",
    product_area="users_permissions",
    sentiment="neutral",
    pii_flag=False,
)
GROUNDED = Resolution(
    answer="Use `adduser` then `adduser <user> <group>`.",
    citations=["RootSudo#11"],
    grounded=True,
    retrieval_score=0.8,
)
PASSED = GuardrailReport(
    decision=Decision.PASS,
    results=[GuardrailResult(name="confidence", decision=Decision.PASS)],
)
ESCALATED = GuardrailReport(
    decision=Decision.ESCALATE,
    results=[
        GuardrailResult(name="confidence", decision=Decision.ESCALATE, reason="confidence 0.43")
    ],
)


def _action(tool: str, risk: str) -> ProposedAction:
    return ProposedAction(
        tool=tool, args={}, idempotency_key="k", risk=risk, executed=risk == "low"
    )


# --------------------------------------------------------------------------- #
# One test per rule, each firing in isolation
# --------------------------------------------------------------------------- #


def test_nothing_escalates_a_confident_grounded_calm_ticket():
    assert should_escalate(CALM, GROUNDED, [], PASSED) == (False, "")


def test_rule_1_low_confidence():
    ungated = Resolution(**{**GROUNDED.to_dict(), "retrieval_score": 0.43})

    escalated, reason = should_escalate(CALM, ungated, [], ESCALATED)

    assert escalated
    assert "low confidence" in reason


def test_rule_2_ungrounded_answer():
    ungrounded = Resolution(**{**GROUNDED.to_dict(), "grounded": False})

    escalated, reason = should_escalate(CALM, ungrounded, [], PASSED)

    assert escalated
    assert "not grounded" in reason


def test_rule_3_high_risk_action():
    # Risk comes from the tool name, never from `executed`: low-risk tools come
    # back executed=True and must not escalate.
    assert should_escalate(CALM, GROUNDED, [_action("order_lookup", "low")], PASSED)[0] is False

    escalated, reason = should_escalate(CALM, GROUNDED, [_action("issue_refund", "high")], PASSED)

    assert escalated
    assert "issue_refund" in reason


def test_rule_4_urgent_priority():
    urgent = Classification(**{**CALM.to_dict(), "priority": "urgent"})

    escalated, reason = should_escalate(urgent, GROUNDED, [], PASSED)

    assert escalated
    assert "urgent" in reason


def test_rule_5_angry_on_an_important_ticket():
    # Anger alone is not enough — a furious how-to question is still a how-to.
    angry_normal = Classification(**{**CALM.to_dict(), "sentiment": "angry"})
    assert should_escalate(angry_normal, GROUNDED, [], PASSED)[0] is False

    angry_high = Classification(**{**CALM.to_dict(), "sentiment": "angry", "priority": "high"})
    escalated, reason = should_escalate(angry_high, GROUNDED, [], PASSED)

    assert escalated
    assert "angry" in reason


# --------------------------------------------------------------------------- #
# Routing into the queue
# --------------------------------------------------------------------------- #


def test_escalate_records_the_policy_reason_on_the_queue_item():
    queue = HumanQueue()

    item = escalate(PASSED, queue, reason="urgent priority", payload={"trace_id": "abc"})

    assert item is not None
    # Nothing in the output report escalated, so the reason is the policy's own
    # synthetic result — the rule that fired, not a guardrail message.
    assert item.reason == "urgent priority"
    assert queue.pending() == [item]
    assert item.payload["trace_id"] == "abc"


def test_escalate_keeps_the_guardrail_reason_when_one_escalated_too():
    queue = HumanQueue()

    item = escalate(ESCALATED, queue, reason="low confidence: 0.43", payload={})

    assert item is not None
    assert item.reason == "confidence 0.43; low confidence: 0.43"


# --------------------------------------------------------------------------- #
# End to end through the pipeline
# --------------------------------------------------------------------------- #


def _ticket(ticket_id: str, subject: str, text: str) -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        text=text,
        channel="email",
        customer_id="cust-7",
        subject=subject,
        received_at="2026-02-01T09:00:00Z",
    )


def test_escalated_ticket_withholds_answer():
    agent = TriageAgent(logger=get_logger("test.triage.escalation", stream=io.StringIO()))
    # A refund drafts a high-risk action (rule 3) — nothing a human has not
    # approved may be delivered.
    ticket = _ticket(
        "TK-5101",
        "Charged twice for ORD-1001",
        "My card was charged twice for order ORD-1001. Please refund $49.00 of it.",
    )

    result = agent.run(ticket)

    assert result.withheld is True
    assert result.escalation is not None
    assert "issue_refund" in [a.tool for a in result.proposed_actions]

    # The draft answer went to the reviewer, not to the customer: no agent
    # message was appended to the session.
    session = agent.session_store.get_or_create(ticket.customer_id)
    assert [m["role"] for m in session.messages] == ["user"]
    assert agent.memory_store.get_all(ticket.customer_id, "triage-agent") == []

    pending = agent.hitl.pending()
    assert len(pending) == 1
    payload = pending[0].payload
    assert payload["trace_id"] == result.trace_id
    assert payload["ticket_text"].endswith(ticket.text)
    assert payload["draft_answer"] == result.resolution.answer
    assert payload["citations"] == result.resolution.citations
    assert [a["tool"] for a in payload["proposed_actions"]] == [
        a.tool for a in result.proposed_actions
    ]


def test_low_confidence_ticket_lands_in_the_queue_too():
    agent = TriageAgent(logger=get_logger("test.triage.escalation.conf", stream=io.StringIO()))
    ticket = _ticket(
        "TK-5102",
        "Wifi keeps dropping",
        "My wireless connection on Ubuntu drops every few minutes and I have to reconnect.",
    )

    result = agent.run(ticket)

    assert result.resolution.retrieval_score < 0.6
    assert result.withheld
    assert "low confidence" in agent.hitl.pending()[0].reason
