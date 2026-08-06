"""The triage pipeline: Classifier -> Resolver -> Action, composed into one
traced request.

Structurally `spine.reference_agent.ReferenceAgent.run` with three real stages
in place of its single model call: one `request_span` parent, every stage's own
spans nested under it, a structured log per step correlated by `trace_id`, and
exactly one `MetricRecord` on every exit path — including the blocked one.

A plain sequential in-process function chain, not A2A (Decision 1). The stages
are ordinary functions; there is no wire protocol, no second process, and
nothing here that a message bus would make simpler.

Three things worth knowing:

* **The model is wrapped once, here.** `classify()` and `resolve()` each wrap a
  bare `ModelClient` when handed one, so passing them an already-wrapped client
  keeps retry and cost accounting in a single `WrappedModelClient` whose
  `usage` delta is this request's token and cost bill.
* **A blocked input still bills a metric.** `classify()` returns
  `(None, report)` when the injection guard blocks; the pipeline short-circuits
  to `_finish` rather than returning early, so the sink sees every request.
* **Escalation is the guardrail decision for now.** Phase 5.2 replaces this
  with `triage.escalation.should_escalate`, which adds the four policy rules a
  confidence gate cannot see.
"""

from __future__ import annotations

import time
import uuid

from spine.guardrails import Decision
from spine.hitl import EscalationItem, HumanQueue, escalate_if_needed
from spine.logging import current_trace_id, get_logger, log_event
from spine.memory import InMemoryMemoryStore, InMemorySessionStore, MemoryStore, SessionStore
from spine.models import FakeModelClient, ModelClient, WrappedModelClient
from spine.obs import InMemoryMetricsSink, MetricRecord, MetricsSink
from spine.rag import Retriever
from spine.tracing import StepType, request_span

from triage import config
from triage.actions import plan_actions
from triage.classifier import classify
from triage.fakes import triage_responder
from triage.kb import load_kb
from triage.resolver import resolve
from triage.schemas import Classification, ProposedAction, Resolution, Ticket, TriageResult


class TriageAgent:
    """The whole vertical behind one `run(ticket)` call.

    Every collaborator is injectable and defaults to the in-memory,
    network-free implementation (Decision 6) — the same constructor shape as
    `ReferenceAgent.__init__`.
    """

    def __init__(
        self,
        *,
        retriever: Retriever | None = None,
        model: ModelClient | None = None,
        hitl: HumanQueue | None = None,
        session_store: SessionStore | None = None,
        memory_store: MemoryStore | None = None,
        obs_sink: MetricsSink | None = None,
        logger=None,
    ) -> None:
        self.retriever = retriever if retriever is not None else load_kb()
        base_model = model if model is not None else FakeModelClient(responder=triage_responder)
        self.model = (
            base_model
            if isinstance(base_model, WrappedModelClient)
            else WrappedModelClient(base_model, config.MODEL_CONFIG)
        )
        self.hitl = hitl if hitl is not None else HumanQueue()
        self.session_store = session_store if session_store is not None else InMemorySessionStore()
        self.memory_store = memory_store if memory_store is not None else InMemoryMemoryStore()
        self.obs_sink = obs_sink if obs_sink is not None else InMemoryMetricsSink()
        self.logger = logger if logger is not None else get_logger("triage.pipeline")

    def run(self, ticket: Ticket) -> TriageResult:
        """Triage one ticket end to end; return everything the run produced."""
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        billed = self._usage()

        with request_span(request_id=request_id, agent=config.AGENT_ID):
            trace_id = current_trace_id()
            self._log(request_id, "ticket received", step=StepType.REQUEST)

            # 1. Classify (emits `input_guardrail` + `classify`) --------------- #
            classification, input_report = classify(ticket, model=self.model, logger=self.logger)
            if classification is None:
                # Injection BLOCK: nothing downstream may run, but the request
                # still happened and still costs a metric row.
                return self._finish(
                    request_id,
                    trace_id,
                    ticket,
                    started,
                    billed,
                    classification=None,
                    resolution=None,
                    actions=[],
                    escalation=None,
                    withheld=True,
                    decision=input_report.decision,
                    tool_errors=0,
                )

            # 2. Prior context for this customer ------------------------------ #
            prior = self.memory_store.get_all(ticket.customer_id, config.AGENT_ID)
            self._log(request_id, f"{len(prior)} prior interactions", step=StepType.REQUEST)

            # 3. Resolve (emits `retrieval`, `resolve`, `output_guardrail`) ---- #
            resolution, output_report = resolve(
                ticket,
                classification,
                retriever=self.retriever,
                model=self.model,
                logger=self.logger,
            )

            # 4. Plan actions (emits one `tool.*` span per tool call) ---------- #
            actions, tool_errors = plan_actions(
                ticket, classification, resolution, logger=self.logger
            )

            # 5. Escalation / delivery decision ------------------------------- #
            escalation = escalate_if_needed(
                output_report,
                self.hitl,
                payload=escalation_payload(trace_id, ticket, resolution, actions),
            )
            withheld = output_report.decision != Decision.PASS
            if escalation is not None:
                self._log(
                    request_id,
                    "escalated to human queue",
                    step=StepType.GUARDRAIL,
                    outcome="escalated",
                    guardrail_decision=output_report.decision,
                )

            # 6. Session + memory write (delivered answers only) -------------- #
            self.session_store.append_message(
                ticket.customer_id, {"role": "user", "text": ticket.text}
            )
            if not withheld:
                self.session_store.append_message(
                    ticket.customer_id, {"role": "agent", "text": resolution.answer}
                )
                self.memory_store.add(
                    ticket.customer_id,
                    config.AGENT_ID,
                    f"Q: {ticket.subject} -> A: {resolution.answer}",
                )

            return self._finish(
                request_id,
                trace_id,
                ticket,
                started,
                billed,
                classification=classification,
                resolution=resolution,
                actions=actions,
                escalation=escalation,
                withheld=withheld,
                decision=output_report.decision,
                tool_errors=tool_errors,
            )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _usage(self) -> tuple[int, float]:
        """Cumulative `(tokens, cost)` on the shared wrapped client.

        Taken before and after a run: the difference is what this request cost,
        with no third copy of the per-stage `_cost()` arithmetic.
        """
        u = self.model.usage
        return u.input_tokens + u.output_tokens, u.cost_usd

    def _finish(
        self,
        request_id: str,
        trace_id: str | None,
        ticket: Ticket,
        started: float,
        billed: tuple[int, float],
        *,
        classification: Classification | None,
        resolution: Resolution | None,
        actions: list[ProposedAction],
        escalation: EscalationItem | None,
        withheld: bool,
        decision: str,
        tool_errors: int,
    ) -> TriageResult:
        tokens, cost = self._usage()
        metric = MetricRecord(
            request_id=request_id,
            agent=config.AGENT_ID,
            latency_ms=(time.monotonic() - started) * 1000.0,
            cost_usd=cost - billed[1],
            tokens=tokens - billed[0],
            quality_score=resolution.retrieval_score if resolution is not None else None,
            escalated=escalation is not None,
            tool_errors=tool_errors,
            decision=decision,
            outcome="withheld" if withheld else "delivered",
        )
        self.obs_sink.record(metric)
        self._log(
            request_id,
            "ticket complete",
            step=StepType.REQUEST,
            latency=metric.latency_ms,
            tokens=metric.tokens,
            cost=metric.cost_usd,
            outcome=metric.outcome,
            guardrail_decision=decision,
        )
        return TriageResult(
            request_id=request_id,
            trace_id=trace_id,
            ticket=ticket,
            classification=classification,
            resolution=resolution,
            proposed_actions=actions,
            escalation=escalation,
            withheld=withheld,
            metric=metric,
        )

    def _log(self, request_id: str, message: str, **fields) -> None:
        log_event(self.logger, message, request_id=request_id, agent=config.AGENT_ID, **fields)


def escalation_payload(
    trace_id: str | None,
    ticket: Ticket,
    resolution: Resolution,
    actions: list[ProposedAction],
) -> dict:
    """Everything a reviewer needs to decide without reading the code."""
    return {
        "trace_id": trace_id,
        "ticket_id": ticket.ticket_id,
        "ticket_text": f"{ticket.subject}. {ticket.text}",
        "draft_answer": resolution.answer,
        "citations": resolution.citations,
        "proposed_actions": [a.to_dict() for a in actions],
    }
