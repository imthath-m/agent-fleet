from spine.tracing import ATTR_STEP, StepType, configure_tracing

from triage import config
from triage.kb import check_grounding
from triage.tools import TOOLS_BY_NAME, kb_search, risk_of
from triage.tools.kb_search import default_retriever

# --------------------------------------------------------------------------- #
# kb_search (4.1)
# --------------------------------------------------------------------------- #


def test_kb_search_returns_cited_passages():
    results = kb_search("how do I add a user to a group")

    assert results, "expected at least one passage from the committed KB"
    assert len(results) <= config.RETRIEVAL_TOP_K
    for row in results:
        assert set(row) == {"doc_id", "text", "source", "score"}
        assert row["text"] and row["source"]
        assert row["score"] > 0
    # Every returned doc_id is a real citation into the corpus.
    doc_ids = [row["doc_id"] for row in results]
    assert check_grounding(default_retriever(), doc_ids) == []


def test_kb_search_respects_top_k():
    assert len(kb_search("ubuntu network wifi install package", top_k=2)) <= 2


def test_kb_search_emits_a_tool_span():
    exporter = configure_tracing()
    kb_search("sudo permissions")
    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["tool.kb_search"]
    assert spans[0].attributes[ATTR_STEP] == StepType.TOOL_CALL


def test_kb_search_is_registered_as_a_low_risk_tool():
    assert TOOLS_BY_NAME["kb_search"].fn is kb_search
    assert risk_of("kb_search") == "low"
