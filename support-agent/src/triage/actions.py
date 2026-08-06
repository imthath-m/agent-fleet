"""Action agent: what should happen to this ticket beyond answering it.

Deterministic plain code, not a model call — `shared-infra/plan.md` says
"deterministic where possible" and routing on four rules is very possible. A
model here would buy nothing but non-reproducible eval numbers and a per-ticket
bill.

Two risk tiers, and the difference is real:

* **low risk** (`kb_search`, `order_lookup`) is read-only, so it *runs*. The
  returned `ProposedAction` carries `executed=True` and is a record of what the
  agent already did.
* **high risk** (`config.HIGH_RISK_TOOLS`) is *drafted*. Calling the tool
  produces a `ProposedAction(executed=False)` and nothing else — the tool has no
  write path to take (Decision 4). Phase 5 escalates on any such action, so a
  human is the only thing that can turn a draft into an effect.

The rules, in the order they fire:

1. an order id in the ticket -> `order_lookup` (the agent needs the order before
   it can say anything useful about it)
2. refund language -> `issue_refund` (high risk; drafted)
3. `intent == "complaint"` or `sentiment == "angry"` -> `crm_update` (high risk;
   the customer record should carry the flag, but a human decides the wording)
4. `not resolution.grounded` -> `kb_search` (the KB had nothing to answer from,
   so the proposed next step is a broader search)

A tool that refuses its arguments — a refund with no amount, an unknown order —
raises `ValueError`, which is counted into `tool_errors` rather than propagated.
The ticket still gets a plan; the failure is a number on `MetricRecord`.
"""

from __future__ import annotations

import logging
import re

from spine.logging import log_event

from triage import config
from triage.schemas import Classification, ProposedAction, Resolution, Ticket, idempotency_key
from triage.tools import crm_update, issue_refund, kb_search, order_lookup

# Order ids in the fixture store are `ORD-` plus four digits.
_ORDER_ID = re.compile(r"\bORD-\d{4}\b", re.IGNORECASE)

# "$49", "$49.00", "49.00 USD", "49 dollars" — a currency symbol or an explicit
# unit, never a bare number (ticket text is full of version numbers and sizes).
_AMOUNT = re.compile(
    r"[$£€]\s?(\d+(?:\.\d{1,2})?)|\b(\d+(?:\.\d{1,2})?)\s?(?:usd|eur|gbp|dollars|euros|pounds)\b",
    re.IGNORECASE,
)

_REFUND = re.compile(r"\brefund|\bmoney back|\bchargeback|\bcharge back|\breimburse", re.IGNORECASE)

# A CRM summary is a note on a record, not the whole answer.
_SUMMARY_CHARS = 280


def find_order_id(text: str) -> str | None:
    """The first order id mentioned, uppercased, or `None`."""
    match = _ORDER_ID.search(text)
    return match.group(0).upper() if match else None


def find_amount(text: str) -> float:
    """The first currency amount mentioned, or `0.0` if the ticket names none.

    `0.0` is deliberately not `None`: it is passed straight to `issue_refund`,
    which rejects it. A refund request with no amount in it is a tool error, and
    the metric should say so.
    """
    match = _AMOUNT.search(text)
    if not match:
        return 0.0
    return float(match.group(1) or match.group(2))


def wants_refund(text: str) -> bool:
    return bool(_REFUND.search(text))


def plan_actions(
    ticket: Ticket,
    classification: Classification,
    resolution: Resolution,
    *,
    logger: logging.Logger | None = None,
) -> tuple[list[ProposedAction], int]:
    """Route one triaged ticket to tools. Returns `(actions, tool_errors)`.

    The tuple mirrors `classify()` and `resolve()`, which likewise return their
    value plus the bookkeeping the pipeline has to record. `tool_errors` flows
    to `MetricRecord.tool_errors` in Phase 5.
    """
    text = f"{ticket.subject} {ticket.text}"
    actions: list[ProposedAction] = []
    tool_errors = 0

    def attempt(tool_name: str, call) -> None:
        nonlocal tool_errors
        try:
            actions.append(call())
        except ValueError as exc:
            tool_errors += 1
            _log(logger, ticket, f"tool refused: {exc}", tool=tool_name, outcome="error")
        else:
            _log(logger, ticket, "tool called", tool=tool_name, outcome="ok")

    # 1. Anything about an order needs the order first.
    order_id = find_order_id(text)
    if order_id is not None:
        attempt(
            "order_lookup",
            lambda: _ran(
                "order_lookup",
                {"order_id": order_id},
                lambda: order_lookup(order_id),
            ),
        )

    # 2. Refund language drafts a refund. High risk: never executed here.
    if wants_refund(text):
        amount = find_amount(text)
        attempt(
            "issue_refund",
            lambda: issue_refund(order_id or "", amount, ticket.subject),
        )

    # 3. Complaints and anger belong on the customer record.
    if classification.intent == "complaint" or classification.sentiment == "angry":
        attempt(
            "crm_update",
            lambda: crm_update(
                ticket.ticket_id,
                resolution.answer[:_SUMMARY_CHARS],
                [classification.intent, classification.priority, classification.sentiment],
            ),
        )

    # 4. Nothing grounded the answer, so the next step is to search again.
    if not resolution.grounded:
        query = ticket.subject
        attempt(
            "kb_search",
            lambda: _ran(
                "kb_search",
                {"query": query, "top_k": config.RETRIEVAL_TOP_K},
                lambda: kb_search(query),
            ),
        )

    return actions, tool_errors


def _ran(tool_name: str, args: dict, invoke) -> ProposedAction:
    """Invoke a read-only tool and record it as already executed.

    Low-risk tools have no approval step to wait for — running them *is* the
    action, and the `ProposedAction` is the audit record of it. `invoke` is a
    zero-arg call; `args` is the same call written down for the record.
    """
    invoke()
    return ProposedAction(
        tool=tool_name,
        args=args,
        idempotency_key=idempotency_key(tool_name, *args.values()),
        risk="low",
        executed=True,
    )


def _log(logger: logging.Logger | None, ticket: Ticket, message: str, **fields) -> None:
    if logger is None:
        return
    log_event(
        logger,
        message,
        request_id=ticket.ticket_id,
        agent=config.AGENT_ID,
        **fields,
    )
