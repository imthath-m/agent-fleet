"""`crm_update` — high-risk, drafts-only. Same contract as `issue_refund`.

Q2 is resolved as (a): no real CRM adapter lands until a paying customer names
one. So this module has no write path either — it builds a `ProposedAction`
describing the record change a human would approve, and stops there.
"""

from __future__ import annotations

from spine.tracing import StepType, timed_span

from triage.schemas import ProposedAction, idempotency_key


def crm_update(ticket_id: str, resolution_summary: str, tags: list[str]) -> ProposedAction:
    """Draft a CRM record update. Raises `ValueError` on an empty `ticket_id`."""
    with timed_span("tool.crm_update", step=StepType.TOOL_CALL):
        if not ticket_id:
            raise ValueError("crm_update needs a ticket_id")
        # Tags are order-insensitive to the CRM, so the key sorts them: the same
        # update proposed twice must not key twice.
        ordered_tags = sorted(tags)
        return ProposedAction(
            tool="crm_update",
            args={
                "ticket_id": ticket_id,
                "resolution_summary": resolution_summary,
                "tags": ordered_tags,
            },
            idempotency_key=idempotency_key(
                ticket_id, resolution_summary, ",".join(ordered_tags)
            ),
            risk="high",
            executed=False,
        )
