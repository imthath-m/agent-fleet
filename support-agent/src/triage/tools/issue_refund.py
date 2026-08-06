"""`issue_refund` — high-risk, drafts-only. Proposes; never executes.

This module has no write path: no HTTP client, no file handle, no payment SDK,
not even a disabled branch behind a flag. The only thing it can produce is a
`ProposedAction` with `executed=False`, which Phase 5 routes to a human. That is
Decision 4, and the phase's exit grep enforces it.

Validation happens *before* proposing, so a reviewer never sees a draft that
could not have been valid in the first place.
"""

from __future__ import annotations

from spine.tracing import StepType, timed_span

from triage.schemas import ProposedAction, idempotency_key
from triage.tools.order_lookup import order_exists


def issue_refund(order_id: str, amount: float, reason: str) -> ProposedAction:
    """Draft a refund. Raises `ValueError` if the refund could never be valid."""
    with timed_span("tool.issue_refund", step=StepType.TOOL_CALL):
        if amount <= 0:
            raise ValueError(f"refund amount must be positive, got {amount!r}")
        if not order_exists(order_id):
            raise ValueError(f"unknown order_id {order_id!r}")
        return ProposedAction(
            tool="issue_refund",
            args={"order_id": order_id, "amount": amount, "reason": reason},
            idempotency_key=idempotency_key(order_id, amount, reason),
            risk="high",
            executed=False,
        )
