"""KB loader: seeds the committed Ubuntu-docs corpus into an
InMemoryRetriever. Reuses spine.rag wholesale -- no retrieval or citation
logic is reimplemented here.
"""

from __future__ import annotations

import json
from pathlib import Path

from spine.rag import Document, InMemoryRetriever, resolve_citations

from triage import config

DEFAULT_KB_PATH = Path(__file__).resolve().parents[2] / "data" / "kb" / "ubuntu_docs.jsonl"


def load_kb(path: Path = DEFAULT_KB_PATH) -> InMemoryRetriever:
    """Load the committed KB corpus into a fresh InMemoryRetriever, seeded
    into `config.KB_NAMESPACE`."""
    retriever = InMemoryRetriever()
    with Path(path).open() as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue
            retriever.ingest(config.KB_NAMESPACE, Document(**json.loads(stripped)))
    return retriever


def attribution_for(retriever: InMemoryRetriever, doc_id: str) -> dict:
    """Attribution fields for the trial UI: {title, url, license, license_url}.
    Returns {} for an unknown doc_id."""
    document = retriever.get(config.KB_NAMESPACE, doc_id)
    if document is None:
        return {}
    metadata = document.metadata
    return {
        "title": metadata.get("title", ""),
        "url": metadata.get("url", document.source),
        "license": metadata.get("license", ""),
        "license_url": metadata.get("license_url", ""),
    }


def check_grounding(retriever: InMemoryRetriever, citations: list[str]) -> list[str]:
    """Thin wrapper over spine.rag.resolve_citations: the subset of
    `citations` that do NOT resolve to a real KB doc (empty == fully grounded)."""
    return resolve_citations(retriever, config.KB_NAMESPACE, citations)
