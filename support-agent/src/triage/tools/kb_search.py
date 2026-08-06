"""`kb_search` — read-only lookup into the committed Ubuntu KB corpus.

The retriever is loaded once and cached: `load_kb()` parses a 382-row JSONL
file, and a tool called several times per ticket should not re-read it.
`retriever=` overrides the cached one so tests can point at a corpus of their
own without touching module state.
"""

from __future__ import annotations

from functools import lru_cache

from spine.rag import Retriever
from spine.tracing import StepType, timed_span

from triage import config
from triage.kb import load_kb


@lru_cache(maxsize=1)
def default_retriever() -> Retriever:
    """The committed KB, loaded on first use."""
    return load_kb()


def kb_search(
    query: str,
    top_k: int = config.RETRIEVAL_TOP_K,
    *,
    retriever: Retriever | None = None,
) -> list[dict]:
    """Return up to `top_k` passages as `{doc_id, text, source, score}` dicts.

    Plain dicts rather than `Passage` objects because a tool result has to
    survive JSON serialization into the HTTP backend and the trace view.
    """
    with timed_span("tool.kb_search", step=StepType.TOOL_CALL):
        target = retriever if retriever is not None else default_retriever()
        passages = target.query(config.KB_NAMESPACE, query, top_k=top_k)
        return [
            {
                "doc_id": p.doc_id,
                "text": p.text,
                "source": p.source,
                "score": p.score,
            }
            for p in passages
        ]
