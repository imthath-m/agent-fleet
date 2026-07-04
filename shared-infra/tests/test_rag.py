from spine.guardrails import AgentOutput, CitationGuard, Decision, run_guardrails
from spine.rag import Document, InMemoryRetriever, passages_to_citations, resolve_citations

# --------------------------------------------------------------------------- #
# Ingest + query
# --------------------------------------------------------------------------- #


def test_ingest_then_query_returns_relevant_seeded_passage():
    retriever = InMemoryRetriever()
    retriever.ingest(
        "support",
        Document(doc_id="doc-1", text="Refunds are processed within 5 business days."),
    )
    retriever.ingest(
        "support",
        Document(doc_id="doc-2", text="Shipping typically takes 2 to 3 days."),
    )

    results = retriever.query("support", "how long does a refund take", top_k=3)

    assert len(results) >= 1
    assert results[0].doc_id == "doc-1"
    assert "Refunds" in results[0].text


def test_query_with_no_match_returns_empty():
    retriever = InMemoryRetriever()
    retriever.ingest("support", Document(doc_id="doc-1", text="Refunds take 5 days."))

    assert retriever.query("support", "zzz nonexistent query zzz") == []


def test_seeded_corpus_via_constructor():
    retriever = InMemoryRetriever(
        corpus={
            "support": [
                Document(doc_id="doc-1", text="Refund policy: 5 business days."),
            ]
        }
    )
    results = retriever.query("support", "refund policy")
    assert [p.doc_id for p in results] == ["doc-1"]


# --------------------------------------------------------------------------- #
# Namespacing (plan.md §10 tenancy)
# --------------------------------------------------------------------------- #


def test_namespacing_isolates_queries():
    retriever = InMemoryRetriever()
    retriever.ingest("product-a", Document(doc_id="a-1", text="Widget assembly instructions."))
    retriever.ingest("product-b", Document(doc_id="b-1", text="Widget assembly instructions."))

    results_a = retriever.query("product-a", "widget assembly")
    results_b = retriever.query("product-b", "widget assembly")

    assert [p.doc_id for p in results_a] == ["a-1"]
    assert [p.doc_id for p in results_b] == ["b-1"]

    # Querying a namespace with no ingested docs returns nothing, even though
    # other namespaces have matching content.
    assert retriever.query("product-c", "widget assembly") == []


# --------------------------------------------------------------------------- #
# KEY TEST (plan.md §5 verify criterion): a grounded answer's citations
# resolve to the seeded fake-corpus docs; a fabricated citation fails.
# --------------------------------------------------------------------------- #


def test_grounded_answer_citations_resolve_and_pass_citation_guard():
    retriever = InMemoryRetriever()
    retriever.ingest(
        "support",
        Document(doc_id="doc-1", text="Refunds are processed within 5 business days."),
    )

    passages = retriever.query("support", "refund processing time")
    assert passages

    output = AgentOutput(
        text="Refunds are processed within 5 business days.",
        citations=passages_to_citations(passages),
    )

    report = run_guardrails([CitationGuard(required=True, min_citations=1)], output)
    assert report.decision == Decision.PASS

    # Citations must also resolve to real docs in the corpus/namespace.
    unresolved = resolve_citations(retriever, "support", list(output.citations))
    assert unresolved == []


def test_fabricated_citation_fails_to_resolve():
    retriever = InMemoryRetriever()
    retriever.ingest("support", Document(doc_id="doc-1", text="Refunds take 5 days."))

    output = AgentOutput(text="Refunds take 5 days.", citations=["doc-999-does-not-exist"])

    # CitationGuard only checks count, so a fabricated citation still passes it...
    report = run_guardrails([CitationGuard(required=True, min_citations=1)], output)
    assert report.decision == Decision.PASS

    # ...but grounding resolution catches it.
    unresolved = resolve_citations(retriever, "support", list(output.citations))
    assert unresolved == ["doc-999-does-not-exist"]
