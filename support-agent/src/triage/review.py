"""`python -m triage.review list|show <id>|resolve <id> --note "..."` — the
human queue, from a terminal.

Deliberately a CLI and not a web app: the reviewer's job is to read a draft and
say yes or no, and a page that renders the same six fields is Phase 7.3's
problem. `show` prints everything the escalation payload carries, with each
citation resolved to its real help.ubuntu.com URL and licence (Decision 2's
attribution obligation follows the KB text wherever it is displayed).

`queue=` is injectable because a `HumanQueue` over the default in-memory store
lives and dies with the process — a standalone invocation sees an empty queue
until the Firestore store lands in 8.3. Tests and the API pass their own.
"""

from __future__ import annotations

import argparse
import sys

from spine.hitl import EscalationItem, HumanQueue

from triage.kb import attribution_for


def render_list(items: list[EscalationItem]) -> str:
    """One line per pending case: enough to pick which one to open."""
    if not items:
        return "queue empty"
    return "\n".join(f"{i.id}  {i.payload.get('ticket_id', '-')}  {i.reason}" for i in items)


def render_item(item: EscalationItem, retriever) -> str:
    """The full case: why it escalated, what the agent drafted, what it cited,
    and what it wants to do."""
    p = item.payload
    lines = [
        f"id        : {item.id}",
        f"status    : {item.status}",
        f"reason    : {item.reason}",
        f"trace_id  : {p.get('trace_id', '-')}",
        f"ticket    : {p.get('ticket_text', '-')}",
        "",
        "draft answer:",
        f"  {p.get('draft_answer', '-')}",
        "",
        "citations:",
    ]
    for doc_id in p.get("citations", []) or ["(none)"]:
        attribution = attribution_for(retriever, doc_id)
        if attribution:
            lines.append(f"  {doc_id} — {attribution['title']}")
            lines.append(f"    {attribution['url']}  ({attribution['license']})")
        else:
            lines.append(f"  {doc_id} — UNRESOLVED (not in the knowledge base)")

    lines += ["", "proposed actions:"]
    actions = p.get("proposed_actions", [])
    if not actions:
        lines.append("  (none)")
    for action in actions:
        executed = "executed" if action.get("executed") else "awaiting approval"
        lines.append(f"  {action['tool']}  risk={action['risk']}  {executed}")
        lines.append(f"    args={action['args']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, queue: HumanQueue | None = None, retriever=None) -> int:
    parser = argparse.ArgumentParser(prog="triage.review", description="Review escalated tickets.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list pending escalations")
    p_show = sub.add_parser("show", help="show one escalation in full")
    p_show.add_argument("id")
    p_resolve = sub.add_parser("resolve", help="mark one escalation resolved")
    p_resolve.add_argument("id")
    p_resolve.add_argument("--note", required=True, help="what the reviewer decided")

    args = parser.parse_args(argv)
    queue = queue if queue is not None else HumanQueue()

    if args.command == "list":
        print(render_list(queue.pending()))
        return 0

    item = queue.store.get(args.id)
    if item is None:
        print(f"no escalation with id {args.id!r}", file=sys.stderr)
        return 1

    if args.command == "show":
        if retriever is None:
            # The tool's cached retriever: `list` must not pay to load the KB.
            from triage.tools.kb_search import default_retriever

            retriever = default_retriever()
        print(render_item(item, retriever))
        return 0

    resolved = queue.resolve(args.id, resolution=args.note)
    print(f"resolved {resolved.id}: {resolved.resolution}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
