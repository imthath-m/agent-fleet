"""The triage tools, wrapped as `spine.agent.Tool` registry entries.

Every tool in this package is read-only or drafts-only (Decision 4): there is
no write path anywhere under `src/triage/tools/`, not even a disabled one. The
high-risk tools return a `ProposedAction` with `executed=False` and nothing
else; a human approves them in the Phase 5 HITL queue or they never happen.

Risk is derived from `config.HIGH_RISK_TOOLS` rather than restated per module,
so the escalation policy and the tools cannot drift apart.
"""

from __future__ import annotations

from spine.agent import Tool

from triage import config
from triage.tools.kb_search import kb_search


def risk_of(tool_name: str) -> str:
    """`"high"` for anything in `config.HIGH_RISK_TOOLS`, else `"low"`."""
    return "high" if tool_name in config.HIGH_RISK_TOOLS else "low"


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="kb_search",
        description="Search the Ubuntu knowledge base and return cited passages.",
        fn=kb_search,
    ),
)

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}

__all__ = ["TOOLS", "TOOLS_BY_NAME", "kb_search", "risk_of"]
