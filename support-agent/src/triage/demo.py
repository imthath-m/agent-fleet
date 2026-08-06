"""Runnable local demo: one scripted ticket through the whole triage pipeline.

Copies `spine.reference_agent.demo`'s shape (same `configure_tracing()` +
`get_logger(stream=...)` wiring, same five printed sections) so this is the
one command a reader can run to see the pipeline for real, no API required:
`python -m triage.demo`.
"""

from __future__ import annotations

import io
import json

from spine.logging import get_logger
from spine.obs import InMemoryMetricsSink, metrics_report
from spine.tracing import configure_tracing

from triage.kb import attribution_for
from triage.pipeline import TriageAgent
from triage.schemas import Ticket
from triage.trace_view import span_tree

# The escalated refund ticket from data/golden/escalation.jsonl
# ("duplicate-charge-refund") — real and committed, not invented. Chosen
# because it's the richer of the two demo cases: it exercises retrieval, a
# model call, two tool calls (order_lookup, issue_refund), and the escalation
# policy, so one run touches nearly every stage the pipeline has.
DEMO_TICKET = Ticket(
    ticket_id="TK-5501",
    text="My card was charged twice for order ORD-1001. Please refund $49.00 of it.",
    channel="email",
    customer_id="cust-5501",
    subject="Charged twice for ORD-1001",
    received_at="2026-03-01T09:00:00Z",
)


def _print_span_tree(nodes: list[dict]) -> None:
    for node in nodes:
        bits = [f"[{node['step'] or '-'}]"]
        if node["latency_ms"] is not None:
            bits.append(f"{node['latency_ms']:.3f}ms")
        if node["tokens"] is not None:
            bits.append(f"{node['tokens']} tok")
        if node["cost_usd"] is not None:
            bits.append(f"${node['cost_usd']:.6f}")
        if node["decision"] is not None:
            bits.append(f"decision={node['decision']}")
        print("  " * node["depth"] + f"- {node['name']}  " + "  ".join(bits))
        _print_span_tree(node["children"])


def demo(ticket: Ticket = DEMO_TICKET) -> dict:
    """Run one scripted ticket through the whole pipeline and print/return the
    span tree, correlated logs, guardrail decisions, the resolution (citations
    with URLs, proposed actions, escalation status), and a metrics summary."""
    exporter = configure_tracing(service_name="triage-demo")
    log_stream = io.StringIO()
    logger = get_logger("triage.demo", stream=log_stream)
    sink = InMemoryMetricsSink()

    agent = TriageAgent(logger=logger, obs_sink=sink)
    result = agent.run(ticket)

    tree = span_tree(exporter)
    report = metrics_report(sink.read())
    log_text = log_stream.getvalue().strip()

    print(f"=== SPAN TREE (trace_id={result.trace_id}) ===")
    _print_span_tree(tree)

    print("\n=== CORRELATED LOGS ===")
    print(log_text)

    print("\n=== GUARDRAIL DECISIONS ===")
    for line in log_text.splitlines():
        entry = json.loads(line)
        if entry["message"] in ("input guardrails", "output guardrails"):
            print(f"  {entry['message']}: {entry['guardrail_decision']}")

    print("\n=== RESULT ===")
    print(f"  withheld: {result.withheld}")
    if result.resolution is not None:
        print(f"  answer  : {result.resolution.answer}")
        print(
            f"  grounded: {result.resolution.grounded}"
            f"  (retrieval_score={result.resolution.retrieval_score:.2f})"
        )
        print("  citations:")
        for doc_id in result.resolution.citations:
            attribution = attribution_for(agent.retriever, doc_id)
            if attribution:
                print(
                    f"    {doc_id} — {attribution['title']}  {attribution['url']}"
                    f"  ({attribution['license']})"
                )
            else:
                print(f"    {doc_id} — UNRESOLVED (not in the knowledge base)")
    print("  proposed actions:")
    if not result.proposed_actions:
        print("    (none)")
    for action in result.proposed_actions:
        print(f"    {action.tool}  risk={action.risk}  executed={action.executed}")
    escalation_note = f"ESCALATED — {result.escalation.reason}" if result.escalation else "none"
    print(f"  escalation: {escalation_note}")

    print("\n=== METRICS SUMMARY ===")
    print(report.render())

    return {"result": result, "trace": tree, "logs": log_stream.getvalue(), "report": report}


if __name__ == "__main__":
    demo()
