"""spine — shared agentic-AI platform library for production agents on GCP.

Phase 1 surface: centralized model config + client interface, a base Agent
runnable with an in-memory fake model, and a local tool backend.

Phase 2 surface: OpenTelemetry tracing setup + span helpers and a structured
JSON logger correlated to traces by ``trace_id``.

Phase 3 surface: an offline evaluation harness (``spine.eval``) with versioned
golden datasets, deterministic + LLM-judge metrics, a runner, a CI regression
gate, and result sinks.
"""

from spine import eval
from spine.agent import Agent, Tool
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
