import io

from spine.guardrails import Decision
from spine.logging import get_logger
from spine.models import FakeModelClient
from spine.rag import InMemoryRetriever, Passage
from spine.reference_agent import default_responder
from spine.tracing import configure_tracing

from triage import config
from triage.kb import check_grounding, load_kb
from triage.resolver import build_prompt, build_query, content_terms, resolve
from triage.schemas import Classification, Ticket

RETRIEVER = load_kb()


def make_ticket(text: str, subject: str = "Ubuntu question") -> Ticket:
    return Ticket(
        ticket_id="TK-9001",
        text=text,
        channel="email",
        customer_id="cust-900",
        subject=subject,
        received_at="2026-02-01T09:00:00Z",
    )


def make_classification(product_area: str = "users_permissions") -> Classification:
    return Classification(
        intent="how_to",
        priority="normal",
        product_area=product_area,
        sentiment="neutral",
        pii_flag=False,
    )


def run(ticket, classification, *, retriever=RETRIEVER, model=None):
    model = model if model is not None else FakeModelClient(responder=default_responder)
    logger = get_logger("triage.test_resolver", stream=io.StringIO())
    return resolve(ticket, classification, retriever=retriever, model=model, logger=logger)


# --------------------------------------------------------------------------- #
# Query construction
# --------------------------------------------------------------------------- #


def test_content_terms_drop_stop_words_and_duplicates():
    terms = content_terms("How do I add a user to a group, and add a user again?")

    assert "the" not in terms and "a" not in terms and "do" not in terms
    assert terms.count("user") == 1
    assert {"add", "user", "group"} <= set(terms)


def test_query_is_prefixed_with_the_classified_product_area():
    query = build_query(make_ticket("wifi drops constantly"), make_classification("networking"))

    assert query.split()[0] == "networking"


def test_generic_product_area_adds_no_query_terms():
    # "other" is not a topic; as a query term it would match "another"/"others"
    # in nearly every chunk and inflate the score for free.
    ticket = make_ticket("wifi drops constantly")

    assert build_query(ticket, make_classification("other")) == build_query(
        ticket, make_classification("")
    )


# --------------------------------------------------------------------------- #
# Prompt shape (must stay parseable by `default_responder`-style fakes)
# --------------------------------------------------------------------------- #


def test_prompt_puts_each_passage_on_one_context_line():
    passages = [Passage(doc_id="d#0", text="first line\n\nsecond line", score=1.0)]

    prompt = build_prompt(make_ticket("hello"), passages)
    context = prompt.partition("Context:")[2].partition("User:")[0].strip()

    assert context == "- d#0: first line second line"
    assert "User: Ubuntu question. hello" in prompt


# --------------------------------------------------------------------------- #
# Grounding
# --------------------------------------------------------------------------- #


def test_answer_cites_a_real_kb_doc():
    resolution, report = run(
        make_ticket("How do I add a new user to a group?", "Adding a user to a group"),
        make_classification("users_permissions"),
    )

    assert resolution.citations
    assert check_grounding(RETRIEVER, resolution.citations) == []
    assert resolution.grounded is True
    assert resolution.answer
    assert report.decision in (Decision.PASS, Decision.ESCALATE)


def test_retrieval_score_is_the_top_passage_score():
    ticket = make_ticket("How do I add a new user to a group?", "Adding a user to a group")
    classification = make_classification("users_permissions")
    passages = RETRIEVER.query(
        config.KB_NAMESPACE, build_query(ticket, classification), top_k=config.RETRIEVAL_TOP_K
    )

    resolution, _ = run(ticket, classification)

    assert resolution.retrieval_score == passages[0].score
    assert resolution.citations == [p.doc_id for p in passages]


def test_no_retrieval_hits_yields_ungrounded_resolution():
    resolution, report = run(
        make_ticket("How do I add a new user to a group?"),
        make_classification(),
        retriever=InMemoryRetriever(),
    )

    assert resolution.citations == []
    assert resolution.grounded is False
    assert resolution.retrieval_score == 0.0
    assert report.decision == Decision.BLOCK
    assert [r.name for r in report.blocked] == ["citation"]


class _FabricatingRetriever(InMemoryRetriever):
    """Returns a citation for a doc it never ingested — a hallucinated source."""

    def query(self, namespace, query, *, top_k=3):
        return [Passage(doc_id="not-a-real-doc#0", text="invented guidance", score=1.0)]


def test_fabricated_citation_marks_ungrounded():
    resolution, report = run(
        make_ticket("How do I add a new user to a group?"),
        make_classification(),
        retriever=_FabricatingRetriever(),
    )

    # CitationGuard only counts citations, so it passes; only the resolution
    # check against the corpus catches the fabrication.
    assert report.decision == Decision.PASS
    assert resolution.citations == ["not-a-real-doc#0"]
    assert resolution.grounded is False


# --------------------------------------------------------------------------- #
# Confidence gating
# --------------------------------------------------------------------------- #


def test_low_retrieval_score_escalates_rather_than_blocks():
    class _WeakRetriever(InMemoryRetriever):
        def query(self, namespace, query, *, top_k=3):
            return [Passage(doc_id="d#0", text="barely related", score=0.1)]

    resolution, report = run(
        make_ticket("something obscure"), make_classification(), retriever=_WeakRetriever()
    )

    assert resolution.retrieval_score == 0.1
    assert report.decision == Decision.ESCALATE
    assert [r.name for r in report.escalated] == ["confidence"]


# --------------------------------------------------------------------------- #
# Tracing
# --------------------------------------------------------------------------- #


def test_each_step_emits_its_own_span():
    exporter = configure_tracing(service_name="triage-test-resolver")

    run(make_ticket("How do I add a new user to a group?"), make_classification())

    names = {s.name for s in exporter.get_finished_spans()}
    assert {"retrieval", "resolve", "output_guardrail"} <= names
