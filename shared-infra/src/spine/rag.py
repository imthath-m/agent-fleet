"""Shared retrieval layer: ingest + query helpers with citation plumbing so
answers are grounded and traceable back to sources (plan.md §3).

:class:`Retriever` is the interface. :class:`InMemoryRetriever` is the local,
SDK-free default — seedable with a small corpus for tests and local dev.
:class:`VertexSearchRetriever` is a lazy-import adapter behind the same
interface for production (mirrors ``spine.eval.sink``); it is never exercised
in tests.

Documents are namespaced (a plain string key per plan.md §10 tenancy) so each
product's datastore stays isolated even when sharing one retriever instance.

Citations: a retrieved :class:`Passage`'s ``doc_id`` is the citation string
that goes into ``spine.guardrails.AgentOutput.citations`` — the existing
``CitationGuard`` checks citation *count*; :func:`resolve_citations` in this
module checks citation *validity* (does the id resolve to a real doc), which
is what catches a fabricated citation.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Passage:
    """One retrieved chunk: text plus enough provenance to cite it."""

    doc_id: str
    text: str
    source: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Document:
    """One ingested document: id, full text, and arbitrary metadata."""

    doc_id: str
    text: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #


class Retriever(ABC):
    """Where documents are ingested and queried, namespaced per product."""

    @abstractmethod
    def ingest(self, namespace: str, document: Document) -> None:
        """Add (or overwrite, by ``doc_id``) one document in ``namespace``."""

    @abstractmethod
    def query(self, namespace: str, query: str, *, top_k: int = 3) -> list[Passage]:
        """Return up to ``top_k`` passages from ``namespace``, best match first."""


# --------------------------------------------------------------------------- #
# In-memory fake (deterministic, for tests + local dev)
# --------------------------------------------------------------------------- #


class InMemoryRetriever(Retriever):
    """Local, SDK-free retriever backed by a dict of namespace -> documents.

    Ranking is a simple case-insensitive keyword-overlap score — deterministic
    and good enough for tests and local dev. Seed it upfront via ``corpus`` or
    call :meth:`ingest` directly.
    """

    def __init__(self, corpus: dict[str, list[Document]] | None = None) -> None:
        self._docs: dict[str, dict[str, Document]] = {}
        for namespace, documents in (corpus or {}).items():
            for document in documents:
                self.ingest(namespace, document)

    def ingest(self, namespace: str, document: Document) -> None:
        self._docs.setdefault(namespace, {})[document.doc_id] = document

    def query(self, namespace: str, query: str, *, top_k: int = 3) -> list[Passage]:
        documents = self._docs.get(namespace, {})
        terms = _tokenize(query)

        scored: list[tuple[float, Document]] = []
        for document in documents.values():
            score = _overlap_score(terms, document.text.lower())
            if score > 0:
                scored.append((score, document))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            Passage(
                doc_id=document.doc_id,
                text=document.text,
                source=document.source,
                score=score,
                metadata=document.metadata,
            )
            for score, document in scored[:top_k]
        ]

    def get(self, namespace: str, doc_id: str) -> Document | None:
        """Fetch one ingested document by id, or ``None`` if it doesn't exist."""
        return self._docs.get(namespace, {}).get(doc_id)


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w]


def _overlap_score(query_terms: list[str], doc_text_lower: str) -> float:
    """Fraction of query terms that appear as a substring of the document
    text — e.g. the query term "refund" matches within "Refunds are ...".
    Simple and deterministic; good enough for the in-memory fake."""
    if not query_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term in doc_text_lower)
    return hits / len(query_terms)


# --------------------------------------------------------------------------- #
# Vertex AI Search adapter (lazy-import)
# --------------------------------------------------------------------------- #


class VertexSearchRetriever(Retriever):
    """Vertex AI Search (RAG Engine) adapter for production.

    The ``google-cloud-discoveryengine`` SDK is imported lazily on first use so
    importing this module (and the whole ``spine`` surface) needs no GCP deps,
    creds, or network. Install the client via the ``vertex`` extra. Namespaces
    map to Vertex AI Search data stores.
    """

    def __init__(
        self,
        project: str,
        *,
        location: str = "global",
        client: Any | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import discoveryengine  # lazy: keeps core SDK-free

            self._client = discoveryengine.DocumentServiceClient()
        return self._client

    def ingest(self, namespace: str, document: Document) -> None:
        from google.cloud import discoveryengine  # lazy: keeps core SDK-free

        client = self._get_client()
        client.create_document(
            parent=namespace,
            document=discoveryengine.Document(
                id=document.doc_id,
                content=discoveryengine.Document.Content(
                    raw_bytes=document.text.encode("utf-8")
                ),
            ),
            document_id=document.doc_id,
        )

    def query(self, namespace: str, query: str, *, top_k: int = 3) -> list[Passage]:
        client = self._get_client()
        response = client.search(request={"serving_config": namespace, "query": query})
        passages: list[Passage] = []
        for result in list(response.results)[:top_k]:
            doc = result.document
            passages.append(
                Passage(doc_id=doc.id, text=str(doc.content), source=namespace, score=0.0)
            )
        return passages


# --------------------------------------------------------------------------- #
# Citation plumbing
# --------------------------------------------------------------------------- #


def passages_to_citations(passages: list[Passage]) -> list[str]:
    """Convert retrieved passages into the citation strings ``AgentOutput``
    (``spine.guardrails``) expects — one per passage, keyed by ``doc_id``."""
    return [p.doc_id for p in passages]


def resolve_citations(retriever: Retriever, namespace: str, citations: list[str]) -> list[str]:
    """Return the subset of ``citations`` that do NOT resolve to a real
    document in ``namespace`` — i.e. fabricated or stale citations.

    An empty return means every citation is grounded in the corpus. Only
    ``InMemoryRetriever`` exposes ``get``; other retrievers can implement it to
    support this check.
    """
    getter = getattr(retriever, "get", None)
    if getter is None:
        raise NotImplementedError(
            f"{type(retriever).__name__} does not support citation resolution (no 'get')"
        )
    return [c for c in citations if getter(namespace, c) is None]
