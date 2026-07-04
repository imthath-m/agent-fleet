"""Reference agent: a "hello" agent composing every spine component end to end.

One :meth:`ReferenceAgent.run` threads a request through the whole platform:
input guardrails -> RAG retrieval with citations -> a wrapped model call
(retry + cost accounting) -> output guardrails with confidence gating -> HITL
escalation when low-confidence -> session/memory read+write -> a tracing span
per step -> structured logs correlated by ``trace_id`` -> a metric record to the
observability sink. It runs entirely on in-memory fakes: no GCP creds, no
network.

This module is the local proof of the plan's "Definition of done" (minus the
GCP deploy). :func:`demo` runs one scripted request and prints the span tree,
correlated logs, guardrail decisions, and a metrics summary;
``python -m spine.reference_agent`` invokes it. :func:`build_reference_suite`
exposes the agent as an eval suite so the CI gate can run over it.
"""

from __future__ import annotations

import io
import time
import uuid
from dataclasses import dataclass, field

from spine.eval.dataset import GoldenDataset, GoldenExample
from spine.eval.metrics import FieldAccuracy, Metric, Prediction, SchemaPassRate
from spine.eval.runner import EvalSuite
from spine.guardrails import (
    AgentOutput,
    CitationGuard,
    ConfidenceGuard,
    Decision,
    GuardrailReport,
    InputGuard,
    OutputGuard,
    PiiGuard,
    PromptInjectionGuard,
    SchemaGuard,
    run_guardrails,
)
from spine.hitl import EscalationItem, HumanQueue, escalate_if_needed
from spine.logging import current_trace_id, get_logger, log_event
from spine.memory import InMemoryMemoryStore, InMemorySessionStore, MemoryStore, SessionStore
from spine.models import (
    DEFAULT_CONFIG,
    FakeModelClient,
    ModelClient,
    ModelConfig,
    WrappedModelClient,
)
from spine.obs import InMemoryMetricsSink, MetricRecord, MetricsSink
from spine.rag import Document, InMemoryRetriever, Retriever, passages_to_citations
from spine.tracing import StepType, record_metrics, request_span, span

# --------------------------------------------------------------------------- #
# Request / result
# --------------------------------------------------------------------------- #


@dataclass
class ReferenceRequest:
    """One request into the reference agent."""

    text: str
    user_id: str = "user-1"
    session_id: str = "session-1"


@dataclass
class ReferenceResult:
    """Everything one run produced, for callers and assertions."""

    request_id: str
    trace_id: str | None
    answer: str | None
    withheld: bool
    output: AgentOutput
    input_report: GuardrailReport
    output_report: GuardrailReport | None
    citations: list[str] = field(default_factory=list)
    escalation: EscalationItem | None = None
    metric: MetricRecord | None = None


# --------------------------------------------------------------------------- #
# Default corpus + model responder
# --------------------------------------------------------------------------- #

_DEFAULT_CORPUS = {
    "support": [
        Document(
            doc_id="refund-policy",
            text=(
                "Our refund window is 30 days from purchase. Refunds requested "
                "outside the window are offered as store credit instead."
            ),
            source="policies/refunds",
        ),
        Document(
            doc_id="password-reset",
            text=(
                "To reset password access, request a fresh reset email and check "
                "the spam folder if it does not arrive within a few minutes."
            ),
            source="policies/accounts",
        ),
        Document(
            doc_id="shipping-delay",
            text=(
                "Delayed packages are usually delivered within two business days; "
                "updated tracking is provided when a package is delayed."
            ),
            source="policies/shipping",
        ),
    ]
}

_CONTEXT_MARKER = "Context:"
_USER_MARKER = "User:"


def default_responder(prompt: str) -> str:
    """Deterministic grounded answer: echo the top retrieved passage's body.

    Mirrors the prompt-parsing fake in ``spine.eval.example`` — the agent embeds
    a ``Context:`` block, and the fake turns the first line into an answer so
    tests need no real model.
    """
    _, _, tail = prompt.partition(_CONTEXT_MARKER)
    context = tail.partition(_USER_MARKER)[0].strip()
    if not context:
        return "I don't have enough grounded information to answer that confidently."
    first_line = context.splitlines()[0].lstrip("- ").strip()
    _, _, body = first_line.partition(": ")
    return f"Based on our documentation: {body or first_line}"


# --------------------------------------------------------------------------- #
# Reference agent
# --------------------------------------------------------------------------- #


class ReferenceAgent:
    """Composes the whole spine stack behind a single :meth:`run` entry point."""

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
        config: ModelConfig = DEFAULT_CONFIG,
        namespace: str = "support",
        agent_id: str = "reference-agent",
        confidence_threshold: float = 0.6,
    ) -> None:
        self.config = config
        self.namespace = namespace
        self.agent_id = agent_id
        self.retriever = retriever if retriever is not None else InMemoryRetriever(_DEFAULT_CORPUS)
        base_model = model if model is not None else FakeModelClient(responder=default_responder)
        # Wrap for retry + cost accounting unless already wrapped by the caller.
        self.model = (
            base_model
            if isinstance(base_model, WrappedModelClient)
            else WrappedModelClient(base_model, config)
        )
        self.hitl = hitl if hitl is not None else HumanQueue()
        self.session_store = session_store if session_store is not None else InMemorySessionStore()
        self.memory_store = memory_store if memory_store is not None else InMemoryMemoryStore()
        self.obs_sink = obs_sink if obs_sink is not None else InMemoryMetricsSink()
        self.logger = logger if logger is not None else get_logger("spine.reference_agent")

        self.input_guards: list[InputGuard] = [PromptInjectionGuard(), PiiGuard()]
        self.output_guards: list[OutputGuard] = [
            SchemaGuard(required_fields=["answer"]),
            CitationGuard(required=True, min_citations=1),
            ConfidenceGuard(threshold=confidence_threshold),
        ]

    def run(self, request: ReferenceRequest | str) -> ReferenceResult:
        """Run one request through the full pipeline; return everything it did."""
        if isinstance(request, str):
            request = ReferenceRequest(text=request)

        request_id = str(uuid.uuid4())
        started = time.monotonic()

        with request_span(request_id=request_id, agent=self.agent_id):
            trace_id = current_trace_id()
            self._log(request_id, "request received", step=StepType.REQUEST)

            # 1. Input guardrails --------------------------------------------- #
            with span("input_guardrail", step=StepType.GUARDRAIL) as gsp:
                input_report = run_guardrails(self.input_guards, request.text, span=gsp)
            self._log(
                request_id,
                "input guardrails",
                step=StepType.GUARDRAIL,
                guardrail_decision=input_report.decision,
            )
            if input_report.decision == Decision.BLOCK:
                return self._finish(
                    request_id,
                    trace_id,
                    started,
                    answer=None,
                    withheld=True,
                    output=AgentOutput(),
                    input_report=input_report,
                    output_report=None,
                    citations=[],
                    escalation=None,
                    decision=input_report.decision,
                    quality=None,
                )

            # 2. Retrieval (grounding + citations) ---------------------------- #
            with span("retrieval", step=StepType.RETRIEVAL) as rsp:
                passages = self.retriever.query(self.namespace, request.text, top_k=3)
                citations = passages_to_citations(passages)
                record_metrics(rsp, decision=f"{len(passages)} passages")
            confidence = passages[0].score if passages else 0.0
            self._log(
                request_id,
                f"retrieved {len(passages)} passages",
                step=StepType.RETRIEVAL,
                outcome=",".join(citations) or "none",
            )

            # 3. Memory read (prior cross-session context) -------------------- #
            prior = self.memory_store.get_all(request.user_id, self.agent_id)

            # 4. Model call (wrapped: retry + cost) --------------------------- #
            with span("model_call", step=StepType.MODEL_CALL) as msp:
                prompt = self._build_prompt(request.text, passages, prior)
                response = self.model.generate(
                    prompt,
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_output_tokens,
                )
                cost = self._cost(response.input_tokens, response.output_tokens)
                record_metrics(msp, tokens=response.total_tokens, cost=cost)
            answer = response.text
            self._log(
                request_id,
                "model call",
                step=StepType.MODEL_CALL,
                tokens=response.total_tokens,
                cost=cost,
            )

            # 5. Output guardrails + confidence gating ------------------------ #
            output = AgentOutput(
                data={"answer": answer},
                text=answer,
                confidence=confidence,
                citations=citations,
            )
            with span("output_guardrail", step=StepType.GUARDRAIL) as osp:
                output_report = run_guardrails(self.output_guards, output, span=osp)
            self._log(
                request_id,
                "output guardrails",
                step=StepType.GUARDRAIL,
                guardrail_decision=output_report.decision,
            )

            # 6. Escalation / delivery decision ------------------------------- #
            escalation: EscalationItem | None = None
            withheld = output_report.decision != Decision.PASS
            delivered = None if withheld else answer
            if output_report.decision == Decision.ESCALATE:
                escalation = escalate_if_needed(
                    output_report,
                    self.hitl,
                    payload={"request": request.text, "draft_answer": answer},
                )
                self._log(
                    request_id,
                    "escalated to human queue",
                    step=StepType.GUARDRAIL,
                    outcome="escalated",
                    guardrail_decision=output_report.decision,
                )

            # 7. Session + memory write (only for delivered answers) ---------- #
            self.session_store.append_message(
                request.session_id, {"role": "user", "text": request.text}
            )
            if delivered is not None:
                self.session_store.append_message(
                    request.session_id, {"role": "agent", "text": delivered}
                )
                self.memory_store.add(
                    request.user_id,
                    self.agent_id,
                    f"Q: {request.text} -> A: {delivered}",
                )

            return self._finish(
                request_id,
                trace_id,
                started,
                answer=delivered,
                withheld=withheld,
                output=output,
                input_report=input_report,
                output_report=output_report,
                citations=citations,
                escalation=escalation,
                decision=output_report.decision,
                quality=confidence,
                tokens=response.total_tokens,
                cost=cost,
            )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _finish(
        self,
        request_id: str,
        trace_id: str | None,
        started: float,
        *,
        answer: str | None,
        withheld: bool,
        output: AgentOutput,
        input_report: GuardrailReport,
        output_report: GuardrailReport | None,
        citations: list[str],
        escalation: EscalationItem | None,
        decision: str,
        quality: float | None,
        tokens: int = 0,
        cost: float = 0.0,
    ) -> ReferenceResult:
        latency_ms = (time.monotonic() - started) * 1000.0
        metric = MetricRecord(
            request_id=request_id,
            agent=self.agent_id,
            latency_ms=latency_ms,
            cost_usd=cost,
            tokens=tokens,
            quality_score=quality,
            escalated=escalation is not None,
            tool_errors=0,
            decision=decision,
            outcome="withheld" if withheld else "delivered",
        )
        self.obs_sink.record(metric)
        self._log(
            request_id,
            "request complete",
            step=StepType.REQUEST,
            latency=latency_ms,
            cost=cost,
            tokens=tokens,
            outcome=metric.outcome,
            guardrail_decision=decision,
        )
        return ReferenceResult(
            request_id=request_id,
            trace_id=trace_id,
            answer=answer,
            withheld=withheld,
            output=output,
            input_report=input_report,
            output_report=output_report,
            citations=citations,
            escalation=escalation,
            metric=metric,
        )

    def _build_prompt(self, text: str, passages, prior) -> str:
        parts = ["You are a helpful, grounded support agent."]
        if prior:
            memory = "\n".join(f"- {e.text}" for e in prior)
            parts.append(f"Known context about this user:\n{memory}")
        if passages:
            context = "\n".join(f"- {p.doc_id}: {p.text}" for p in passages)
            parts.append(f"{_CONTEXT_MARKER}\n{context}")
        parts.append(f"{_USER_MARKER} {text}")
        return "\n\n".join(parts)

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        c = self.config
        return (
            input_tokens / 1000 * c.input_cost_per_1k
            + output_tokens / 1000 * c.output_cost_per_1k
        )

    def _log(self, request_id: str, message: str, **fields) -> None:
        log_event(self.logger, message, request_id=request_id, agent=self.agent_id, **fields)


# --------------------------------------------------------------------------- #
# Eval suite (reference agent as the system under test)
# --------------------------------------------------------------------------- #


def reference_metrics() -> list[Metric]:
    return [SchemaPassRate(required_fields=["answer"]), FieldAccuracy(fields=["grounded"])]


def build_reference_suite(agent: ReferenceAgent | None = None) -> EvalSuite:
    """A tiny golden suite that runs the reference agent as the predictor.

    Each input strongly matches a seeded doc, so a healthy agent grounds its
    answer (``grounded=True``) and returns a non-empty ``answer`` — the gate
    passes against a baseline captured from this good agent.
    """
    agent = agent if agent is not None else ReferenceAgent()
    examples = (
        GoldenExample(id="refund", input="refund window policy", expected={"grounded": True}),
        GoldenExample(id="reset", input="reset password email", expected={"grounded": True}),
        GoldenExample(id="shipping", input="delayed package tracking", expected={"grounded": True}),
    )
    dataset = GoldenDataset(name="reference_agent", version="1", examples=examples)

    def predict(agent_input) -> Prediction:
        result = agent.run(ReferenceRequest(text=str(agent_input)))
        grounded = bool(result.citations) and not result.withheld
        answer = result.answer or ""
        return Prediction(output={"answer": answer, "grounded": grounded}, text=answer)

    return EvalSuite(dataset, predict, reference_metrics())


# --------------------------------------------------------------------------- #
# Runnable end-to-end demo
# --------------------------------------------------------------------------- #


def demo(request_text: str = "What is the refund window policy?") -> dict:
    """Run one scripted request through the whole pipeline and print/return the
    span tree, correlated logs, guardrail decisions, and a metrics summary."""
    from spine.obs import metrics_report
    from spine.tracing import configure_tracing

    exporter = configure_tracing(service_name="reference-agent-demo")
    log_stream = io.StringIO()
    logger = get_logger("spine.reference_agent.demo", stream=log_stream)
    sink = InMemoryMetricsSink()

    agent = ReferenceAgent(logger=logger, obs_sink=sink)
    result = agent.run(ReferenceRequest(text=request_text))

    spans = exporter.get_finished_spans()
    report = metrics_report(sink.read())

    print(f"=== SPAN TREE (trace_id={result.trace_id}) ===")
    for line in _render_span_tree(spans):
        print(line)

    print("\n=== CORRELATED LOGS ===")
    print(log_stream.getvalue().strip())

    print("\n=== GUARDRAIL DECISIONS ===")
    print(f"  input : {result.input_report.decision}")
    if result.output_report is not None:
        print(f"  output: {result.output_report.decision}")

    print("\n=== ANSWER ===")
    print(f"  withheld: {result.withheld}")
    print(f"  answer  : {result.answer}")
    print(f"  citations: {result.citations}")

    print("\n=== METRICS SUMMARY ===")
    print(report.render())

    return {
        "result": result,
        "spans": spans,
        "logs": log_stream.getvalue(),
        "report": report,
    }


def _render_span_tree(spans) -> list[str]:
    by_id = {s.context.span_id: s for s in spans}
    children: dict[int | None, list] = {}
    for s in spans:
        parent_id = s.parent.span_id if s.parent is not None else None
        children.setdefault(parent_id, []).append(s)

    lines: list[str] = []

    def walk(parent_id, depth):
        for s in children.get(parent_id, []):
            lines.append(f"{'  ' * depth}- {s.name}")
            walk(s.context.span_id, depth + 1)

    roots = [pid for pid in children if pid is None or pid not in by_id]
    for root in roots:
        walk(root, 0)
    return lines


if __name__ == "__main__":
    demo()
