"""JSON trace serialization: the span tree the trial page renders.

Generalizes `spine.reference_agent._render_span_tree` (a list of indented
`"- name"` text lines) into structured JSON a frontend can walk without
importing OpenTelemetry: `{name, step, depth, latency_ms, tokens, cost_usd,
decision, children}`, nested exactly as the spans were parented.

Key on the attribute, not the name: tool-call spans are named `tool.<name>`
(`tool.kb_search`, `tool.issue_refund`, ...) but all carry
`spine.step == "tool_call"`. This module never branches on `span.name` — only
`ATTR_STEP` and friends decide what a node *is*; the name is display-only.
"""

from __future__ import annotations

from typing import Any

from spine.tracing import ATTR_COST, ATTR_DECISION, ATTR_LATENCY, ATTR_STEP, ATTR_TOKENS

# OTel span start/end times are nanoseconds since epoch; spans that never set
# `ATTR_LATENCY` explicitly (every stage span except `timed_span`-wrapped tool
# calls) still get a latency computed from these.
_NANOS_PER_MS = 1_000_000


def span_tree(exporter) -> list[dict[str, Any]]:
    """The finished spans on `exporter`, as a nested tree of root node(s).

    Mirrors `_render_span_tree`'s parent/child grouping by `span_id`, but
    returns JSON nodes instead of printing indented lines.
    """
    spans = exporter.get_finished_spans()
    by_id = {s.context.span_id: s for s in spans}
    children: dict[int | None, list] = {}
    for s in spans:
        parent_id = s.parent.span_id if s.parent is not None else None
        children.setdefault(parent_id, []).append(s)

    def to_node(s, depth: int) -> dict[str, Any]:
        attrs = s.attributes or {}
        latency_ms = attrs.get(ATTR_LATENCY)
        if latency_ms is None and s.start_time is not None and s.end_time is not None:
            latency_ms = (s.end_time - s.start_time) / _NANOS_PER_MS
        return {
            "name": s.name,
            "step": attrs.get(ATTR_STEP),
            "depth": depth,
            "latency_ms": latency_ms,
            "tokens": attrs.get(ATTR_TOKENS),
            "cost_usd": attrs.get(ATTR_COST),
            "decision": attrs.get(ATTR_DECISION),
            "children": [to_node(c, depth + 1) for c in children.get(s.context.span_id, [])],
        }

    roots = [pid for pid in children if pid is None or pid not in by_id]
    return [to_node(s, 0) for pid in roots for s in children[pid]]
