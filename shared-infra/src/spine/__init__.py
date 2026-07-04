"""spine — shared agentic-AI platform library for production agents on GCP.

Phase 1 surface: centralized model config + client interface, a base Agent
runnable with an in-memory fake model, and a local tool backend.

Phase 2 surface: OpenTelemetry tracing setup + span helpers and a structured
JSON logger correlated to traces by ``trace_id``.

Phase 3 surface: an offline evaluation harness (``spine.eval``) with versioned
golden datasets, deterministic + LLM-judge metrics, a runner, a CI regression
gate, and result sinks.

Phase 4 surface: input/output guardrails (``spine.guardrails``) — PII,
prompt-injection, and topic checks on input; schema, citation, and confidence
checks on output — plus a human-in-the-loop escalation queue (``spine.hitl``)
that low-confidence or high-risk cases route to.

Phase 5 surface: a shared retrieval layer (``spine.rag``) — ingest/query with
namespacing and citation plumbing compatible with ``CitationGuard`` — plus a
memory abstraction (``spine.memory``) for per-session state and long-term,
cross-session agent memory.

Phase 6 surface: an observability sink + metric emitters (``spine.obs``) with a
local and lazy-GCP BigQuery implementation and a metrics-report summary, plus a
reference agent (``spine.reference_agent``) that composes every component end to
end behind one ``run`` entry point (the local "Definition of done" proof).
"""

from spine import eval
from spine.agent import Agent, Tool
from spine.guardrails import (
    AgentOutput,
    CitationGuard,
    ConfidenceGuard,
    Decision,
    GuardrailReport,
    GuardrailResult,
    InputGuard,
    OutputGuard,
    PiiGuard,
    PromptInjectionGuard,
    SchemaGuard,
    TopicGuard,
    run_guardrails,
)
from spine.hitl import (
    EscalationItem,
    EscalationStore,
    FirestoreEscalationStore,
    HumanQueue,
    InMemoryEscalationStore,
    escalate_if_needed,
)
from spine.logging import (
    SpineJsonFormatter,
    current_trace_id,
    get_logger,
    log_event,
)
from spine.memory import (
    FirestoreSessionStore,
    InMemoryMemoryStore,
    InMemorySessionStore,
    MemoryBankStore,
    MemoryEntry,
    MemoryStore,
    SessionState,
    SessionStore,
)
from spine.models import (
    FakeModelClient,
    ModelClient,
    ModelConfig,
    ModelResponse,
    WrappedModelClient,
)
from spine.obs import (
    BigQueryMetricsSink,
    InMemoryMetricsSink,
    JsonlMetricsSink,
    MetricRecord,
    MetricsReport,
    MetricsSink,
    metrics_report,
    percentile,
    record_to_row,
)
from spine.rag import (
    Document,
    InMemoryRetriever,
    Passage,
    Retriever,
    VertexSearchRetriever,
    passages_to_citations,
    resolve_citations,
)
from spine.reference_agent import (
    ReferenceAgent,
    ReferenceRequest,
    ReferenceResult,
    build_reference_suite,
    demo,
)
from spine.tracing import (
    StepType,
    configure_tracing,
    get_tracer,
    record_metrics,
    request_span,
    span,
    timed_span,
)

__all__ = [
    "eval",
    "Agent",
    "Tool",
    "ModelClient",
    "ModelConfig",
    "ModelResponse",
    "FakeModelClient",
    "WrappedModelClient",
    # guardrails
    "AgentOutput",
    "CitationGuard",
    "ConfidenceGuard",
    "Decision",
    "GuardrailReport",
    "GuardrailResult",
    "InputGuard",
    "OutputGuard",
    "PiiGuard",
    "PromptInjectionGuard",
    "SchemaGuard",
    "TopicGuard",
    "run_guardrails",
    # hitl
    "EscalationItem",
    "EscalationStore",
    "FirestoreEscalationStore",
    "HumanQueue",
    "InMemoryEscalationStore",
    "escalate_if_needed",
    # tracing
    "StepType",
    "configure_tracing",
    "get_tracer",
    "record_metrics",
    "request_span",
    "span",
    "timed_span",
    # logging
    "SpineJsonFormatter",
    "current_trace_id",
    "get_logger",
    "log_event",
    # rag
    "Document",
    "InMemoryRetriever",
    "Passage",
    "Retriever",
    "VertexSearchRetriever",
    "passages_to_citations",
    "resolve_citations",
    # memory
    "FirestoreSessionStore",
    "InMemoryMemoryStore",
    "InMemorySessionStore",
    "MemoryBankStore",
    "MemoryEntry",
    "MemoryStore",
    "SessionState",
    "SessionStore",
    # obs
    "BigQueryMetricsSink",
    "InMemoryMetricsSink",
    "JsonlMetricsSink",
    "MetricRecord",
    "MetricsReport",
    "MetricsSink",
    "metrics_report",
    "percentile",
    "record_to_row",
    # reference agent
    "ReferenceAgent",
    "ReferenceRequest",
    "ReferenceResult",
    "build_reference_suite",
    "demo",
]
