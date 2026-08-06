"""Escalation policy: which triaged tickets a human has to see.

Five rules, checked in order, first match wins. They are deliberately separate
and side-effect free so each one can be tested on its own and read by someone
who has to defend the escalation rate to a customer:

1. **low confidence** — the output guardrails escalated (`ConfidenceGuard`
   tripped on `retrieval_score < config.CONFIDENCE_THRESHOLD`). This is the
   rule that actually fires most: a keyword retriever over 382 chunks puts
   roughly two in five tickets under the threshold.
2. **ungrounded** — a citation did not resolve to a real KB document. Note what
   this is and is not: `kb.check_grounding` verifies that cited ids *exist*,
   not that they are relevant, so this rule guards against *fabricated*
   citations and little else. Expect it to fire almost never against a fake
   that quotes real passages; that is correct, not broken.
3. **high-risk action** — any proposed action whose tool is in
   `config.HIGH_RISK_TOOLS`. Keyed on the tool, never on `executed`: low-risk
   tools come back `executed=True` because running them *is* the action, so
   `executed` says nothing about risk.
4. **urgent priority** — an urgent ticket gets a human regardless of how
   confident the retriever was.
5. **angry and important** — anger alone is not an escalation (a frustrated
   how-to question is still a how-to question), but anger on a high or urgent
   ticket is.

Escalating routes through `spine.hitl.escalate_if_needed` with a payload that
carries the trace id, the ticket, the draft answer, its citations and the
proposed actions — enough for a reviewer to decide without opening the code.
"""

from __future__ import annotations

from spine.guardrails import Decision, GuardrailReport, GuardrailResult
from spine.hitl import EscalationItem, HumanQueue, escalate_if_needed

from triage import config
from triage.schemas import Classification, ProposedAction, Resolution

# The synthetic guard name policy escalations are recorded under, so a queue
# item's reason names the rule and not just the confidence guard.
POLICY_GUARD = "escalation_policy"

_ESCALATING_PRIORITIES = ("high", "urgent")


def should_escalate(
    classification: Classification,
    resolution: Resolution,
    actions: list[ProposedAction],
    output_report: GuardrailReport,
) -> tuple[bool, str]:
    """`(escalate?, reason)` for one triaged ticket. Pure; no side effects."""
    if output_report.decision == Decision.ESCALATE:
        return True, f"low confidence: retrieval score {resolution.retrieval_score:.2f}"

    if not resolution.grounded:
        return True, "answer is not grounded in the knowledge base"

    high_risk = [a.tool for a in actions if a.tool in config.HIGH_RISK_TOOLS]
    if high_risk:
        return True, f"high-risk action proposed: {', '.join(high_risk)}"

    if classification.priority == "urgent":
        return True, "urgent priority"

    if classification.sentiment == "angry" and classification.priority in _ESCALATING_PRIORITIES:
        return True, f"angry customer on a {classification.priority}-priority ticket"

    return False, ""


def escalate(
    output_report: GuardrailReport,
    queue: HumanQueue,
    *,
    reason: str,
    payload: dict,
) -> EscalationItem | None:
    """Enqueue one case for human review through `spine.hitl`.

    The policy reason is appended to the output report as a synthetic
    `ESCALATE` result, so the queue item's reason names the rule that fired
    even when no guardrail escalated on its own.
    """
    report = GuardrailReport(
        decision=Decision.ESCALATE,
        results=[
            *output_report.results,
            GuardrailResult(name=POLICY_GUARD, decision=Decision.ESCALATE, reason=reason),
        ],
    )
    return escalate_if_needed(report, queue, payload=payload)
