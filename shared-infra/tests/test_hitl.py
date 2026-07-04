import pytest

from spine.guardrails import AgentOutput, ConfidenceGuard, Decision, run_guardrails
from spine.hitl import (
    STATUS_RESOLVED,
    EscalationItem,
    HumanQueue,
    InMemoryEscalationStore,
    escalate_if_needed,
)

# --------------------------------------------------------------------------- #
# In-memory store round-trip
# --------------------------------------------------------------------------- #


def test_in_memory_store_round_trip():
    store = InMemoryEscalationStore()
    item = EscalationItem(id="e1", reason="low confidence", payload={"q": "hi"})

    store.put(item)
    assert store.get("e1") == item
    assert [i.id for i in store.list_pending()] == ["e1"]

    item.status = STATUS_RESOLVED
    store.put(item)
    assert store.list_pending() == []
    assert store.get("e1").status == STATUS_RESOLVED


def test_store_get_missing_returns_none():
    assert InMemoryEscalationStore().get("nope") is None


# --------------------------------------------------------------------------- #
# HumanQueue: enqueue / pending / resolve
# --------------------------------------------------------------------------- #


def test_queue_enqueue_lists_pending():
    queue = HumanQueue()
    item = queue.enqueue(reason="high risk action", payload={"action": "refund"})

    pending = queue.pending()
    assert len(pending) == 1
    assert pending[0].id == item.id
    assert pending[0].is_pending


def test_queue_resolve_transitions_state():
    queue = HumanQueue()
    item = queue.enqueue(reason="needs review")

    resolved = queue.resolve(item.id, resolution="approved")

    assert resolved.status == STATUS_RESOLVED
    assert resolved.resolution == "approved"
    assert resolved.resolved_at is not None
    assert queue.pending() == []


def test_queue_resolve_missing_item_raises():
    queue = HumanQueue()
    with pytest.raises(KeyError):
        queue.resolve("missing", resolution="n/a")


def test_queue_notify_hook_called_on_enqueue():
    notified = []
    queue = HumanQueue(notify=notified.append)

    item = queue.enqueue(reason="test")

    assert notified == [item]


# --------------------------------------------------------------------------- #
# KEY TEST (plan.md §5 verify criterion): low-confidence routes to the human
# queue and the response is paused/withheld until resolved.
# --------------------------------------------------------------------------- #


def test_low_confidence_output_routes_to_human_queue_and_resolves():
    queue = HumanQueue()
    low_confidence_output = AgentOutput(text="maybe the refund is approved?", confidence=0.15)

    report = run_guardrails([ConfidenceGuard(threshold=0.6)], low_confidence_output)
    assert report.decision == Decision.ESCALATE

    # The agent must not hand back the response yet — it's paused pending review.
    response = None
    item = escalate_if_needed(report, queue, payload={"draft_output": low_confidence_output.text})

    assert item is not None
    assert response is None  # response withheld

    pending = queue.pending()
    assert len(pending) == 1
    assert pending[0].id == item.id
    assert pending[0].payload["draft_output"] == low_confidence_output.text
    assert "confidence" in pending[0].reason

    # A human reviews and resolves the case; only then can a response go out.
    resolved = queue.resolve(item.id, resolution="approved: refund confirmed")
    assert resolved.status == STATUS_RESOLVED
    assert queue.pending() == []
    response = resolved.resolution
    assert response == "approved: refund confirmed"


def test_escalate_if_needed_is_noop_when_not_escalated():
    queue = HumanQueue()
    report = run_guardrails([ConfidenceGuard(threshold=0.6)], AgentOutput(confidence=0.9))
    assert escalate_if_needed(report, queue) is None
    assert queue.pending() == []
