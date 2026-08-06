"""Resolver stage: a ticket plus its classification in, a grounded cited answer out.

Mirrors `spine.reference_agent.ReferenceAgent.run`'s retrieval -> prompt ->
model -> output-guard flow for one step, including feeding `passages[0].score`
to `ConfidenceGuard` as the confidence signal.

Two things are worth knowing about the query:

* `spine.rag.InMemoryRetriever` scores by the fraction of query terms found as a
  substring anywhere in a chunk, so stop words ("the", "a", "is") match almost
  every document and drown out the topical terms. `content_terms` drops them.
* the classifier already decided the `product_area`; prefixing it steers ties
  toward the right corner of the KB (a wifi ticket lands on `WifiDocs` rather
  than whichever chunk happened to share filler words).

Both cost raw score — a stripped query has fewer freebie hits — so more tickets
fall under `config.CONFIDENCE_THRESHOLD` and escalate. That is an honest
low-confidence signal from a keyword retriever, not a bug to tune away; Phase 5's
escalation policy is what consumes it.

The `Context:`/`User:` prompt shape is `spine.reference_agent._build_prompt`'s,
so `spine.reference_agent.default_responder` drives this stage in tests and
evals with no model. Passage text is whitespace-collapsed onto one line each so
that fake reads a whole chunk rather than its first line.
"""

from __future__ import annotations

import logging
import re

from spine.guardrails import (
    AgentOutput,
    CitationGuard,
    ConfidenceGuard,
    GuardrailReport,
    SchemaGuard,
    run_guardrails,
)
from spine.logging import log_event
from spine.models import ModelClient, WrappedModelClient
from spine.rag import Passage, Retriever, passages_to_citations
from spine.tracing import StepType, record_metrics, span

from triage import config
from triage.kb import check_grounding
from triage.schemas import Classification, Resolution, Ticket

_CONTEXT_MARKER = "Context:"
_USER_MARKER = "User:"

# Function words plus support-desk pleasantries. Every one of these appears as a
# substring of almost any KB chunk, so keeping them would score every document
# alike and hand the ranking to dict insertion order.
_STOP_WORDS = frozenset(
    """a about all also am an and any are as at be been being but by can cant could did do does
    doesnt doing dont for from get got had has have he her here him his how i id if ill im in into
    is it its ive just like me my no nor not of off on once one only or other our out over own re
    s same she should so some still such t than that the their them then there these they this
    those to too ve very was we well were what when where which while who why will with would you
    your yours
    hello hi hey thanks thank please help sorry regards cheers dear team support ticket issue
    problem trying tried want need someone anyone""".split()
)


def content_terms(text: str) -> list[str]:
    """Distinct, order-preserving, non-stop-word terms of `text`, lowercased."""
    seen: dict[str, None] = {}
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word not in _STOP_WORDS:
            seen.setdefault(word, None)
    return list(seen)


def build_query(ticket: Ticket, classification: Classification) -> str:
    """The retrieval query: product area (when it names one) then ticket terms."""
    terms = content_terms(f"{ticket.subject} {ticket.text}")
    area = classification.product_area
    if area and area != "other":
        terms = [t for t in area.split("_") if t not in terms] + terms
    return " ".join(terms)


def build_prompt(ticket: Ticket, passages: list[Passage]) -> str:
    """`Context:`/`User:` prompt, one whitespace-collapsed line per passage."""
    parts = ["You are a helpful, grounded Ubuntu support agent."]
    if passages:
        context = "\n".join(f"- {p.doc_id}: {' '.join(p.text.split())}" for p in passages)
        parts.append(f"{_CONTEXT_MARKER}\n{context}")
    parts.append(f"{_USER_MARKER} {ticket.subject}. {ticket.text}")
    return "\n\n".join(parts)


def output_guards() -> list:
    """Schema, then citations, then confidence — the resolver's output gate."""
    return [
        SchemaGuard(required_fields=["answer"]),
        CitationGuard(required=True, min_citations=1),
        ConfidenceGuard(threshold=config.CONFIDENCE_THRESHOLD),
    ]


def resolve(
    ticket: Ticket,
    classification: Classification,
    *,
    retriever: Retriever,
    model: ModelClient,
    logger: logging.Logger,
) -> tuple[Resolution, GuardrailReport]:
    """Answer one ticket from the KB. The report carries the delivery decision.

    A `Resolution` is always returned, grounded or not: whether a low-confidence
    or uncited answer is withheld is the pipeline's call (Phase 5), not this
    stage's.
    """
    with span("retrieval", step=StepType.RETRIEVAL) as rsp:
        passages = retriever.query(
            config.KB_NAMESPACE,
            build_query(ticket, classification),
            top_k=config.RETRIEVAL_TOP_K,
        )
        citations = passages_to_citations(passages)
        record_metrics(rsp, decision=f"{len(passages)} passages")
    retrieval_score = passages[0].score if passages else 0.0
    _log(
        logger,
        ticket,
        f"retrieved {len(passages)} passages",
        step=StepType.RETRIEVAL,
        outcome=",".join(citations) or "none",
    )

    wrapped = (
        model
        if isinstance(model, WrappedModelClient)
        else WrappedModelClient(model, config.MODEL_CONFIG)
    )
    with span("resolve", step=StepType.MODEL_CALL) as msp:
        response = wrapped.generate(
            build_prompt(ticket, passages),
            temperature=config.MODEL_CONFIG.temperature,
            max_output_tokens=config.MODEL_CONFIG.max_output_tokens,
        )
        cost = _cost(response.input_tokens, response.output_tokens)
        record_metrics(msp, tokens=response.total_tokens, cost=cost)
    answer = response.text
    _log(
        logger,
        ticket,
        "resolve model call",
        step=StepType.MODEL_CALL,
        tokens=response.total_tokens,
        cost=cost,
    )

    output = AgentOutput(
        data={"answer": answer},
        text=answer,
        confidence=retrieval_score,
        citations=citations,
    )
    with span("output_guardrail", step=StepType.GUARDRAIL) as osp:
        report = run_guardrails(output_guards(), output, span=osp)
    _log(
        logger,
        ticket,
        "output guardrails",
        step=StepType.GUARDRAIL,
        decision=report.decision,
    )

    # Grounded means every citation resolves to a real KB doc — a fabricated or
    # stale id fails here even though `CitationGuard` (a count check) passed.
    grounded = bool(citations) and not check_grounding(retriever, citations)
    resolution = Resolution(
        answer=answer,
        citations=citations,
        grounded=grounded,
        retrieval_score=retrieval_score,
    )
    return resolution, report


def _cost(input_tokens: int, output_tokens: int) -> float:
    c = config.MODEL_CONFIG
    return input_tokens / 1000 * c.input_cost_per_1k + output_tokens / 1000 * c.output_cost_per_1k


def _log(logger: logging.Logger, ticket: Ticket, message: str, *, decision=None, **fields) -> None:
    log_event(
        logger,
        message,
        request_id=ticket.ticket_id,
        agent=config.AGENT_ID,
        guardrail_decision=decision,
        **fields,
    )
