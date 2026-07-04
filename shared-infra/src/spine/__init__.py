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
from spine.models import (
    FakeModelClient,
    ModelClient,
    ModelConfig,
    ModelResponse,
    WrappedModelClient,
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
]
