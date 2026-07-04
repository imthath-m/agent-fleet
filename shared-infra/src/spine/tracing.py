"""OpenTelemetry tracing setup + span helpers.

Defaults to an in-memory span exporter suitable for tests; the real Cloud
Trace exporter is imported lazily (mirroring ``spine.models_vertex``) so this
module imports fine with zero GCP packages, no creds, and no network.

Every request is a parent span; each step (retrieval, tool call, model call,
guardrail) is a child span carrying standard attributes (tokens, cost,
latency, decision). Child spans nest under whatever span is current via normal
OTel context propagation.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span

# --------------------------------------------------------------------------- #
# Standard step types + attribute keys
# --------------------------------------------------------------------------- #

TRACER_NAME = "spine"

# The provider from the most recent ``configure_tracing`` call. Kept here so
# span helpers use it directly: OTel forbids overriding the *global* provider
# more than once, which would otherwise leave re-configured exporters unwired.
_provider: TracerProvider | None = None


class StepType:
    """Canonical step names used as span names / the ``spine.step`` attribute."""

    RETRIEVAL = "retrieval"
    TOOL_CALL = "tool_call"
    MODEL_CALL = "model_call"
    GUARDRAIL = "guardrail"
    REQUEST = "request"


# Attribute keys kept in one place so logs/traces/dashboards agree.
ATTR_STEP = "spine.step"
ATTR_TOKENS = "spine.tokens"
ATTR_COST = "spine.cost_usd"
ATTR_LATENCY = "spine.latency_ms"
ATTR_DECISION = "spine.decision"


# --------------------------------------------------------------------------- #
# Provider setup
# --------------------------------------------------------------------------- #


def configure_tracing(
    exporter: object | None = None,
    *,
    service_name: str = "spine",
    set_global: bool = True,
) -> InMemorySpanExporter:
    """Build a ``TracerProvider`` wired to ``exporter`` and (by default) install
    it as the global provider.

    ``exporter`` defaults to an :class:`InMemorySpanExporter` so tests can read
    finished spans back. Pass :func:`cloud_trace_exporter` in production. The
    exporter is returned so callers/tests can inspect it.
    """
    if exporter is None:
        exporter = InMemorySpanExporter()

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    global _provider
    _provider = provider
    if set_global:
        trace.set_tracer_provider(provider)

    return exporter  # type: ignore[return-value]


def get_tracer() -> trace.Tracer:
    """Return the spine tracer from the configured provider (falling back to the
    global provider if :func:`configure_tracing` was never called)."""
    if _provider is not None:
        return _provider.get_tracer(TRACER_NAME)
    return trace.get_tracer(TRACER_NAME)


def cloud_trace_exporter(*, project: str | None = None):
    """Return a GCP Cloud Trace span exporter.

    Lazy import: the ``opentelemetry-exporter-gcp-trace`` package is optional
    (install via the ``tracing-gcp`` extra). Keeps the core module importable
    without any GCP dependency, creds, or network.
    """
    try:
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise ImportError(
            "Cloud Trace export requires the 'tracing-gcp' extra: "
            "pip install 'spine[tracing-gcp]'"
        ) from exc

    return CloudTraceSpanExporter(project_id=project)


# --------------------------------------------------------------------------- #
# Span helpers
# --------------------------------------------------------------------------- #


def record_metrics(
    span: Span,
    *,
    tokens: int | None = None,
    cost: float | None = None,
    latency_ms: float | None = None,
    decision: str | None = None,
) -> None:
    """Set the standard metric attributes on an active span (skips ``None``)."""
    if tokens is not None:
        span.set_attribute(ATTR_TOKENS, tokens)
    if cost is not None:
        span.set_attribute(ATTR_COST, cost)
    if latency_ms is not None:
        span.set_attribute(ATTR_LATENCY, latency_ms)
    if decision is not None:
        span.set_attribute(ATTR_DECISION, decision)


@contextmanager
def span(
    name: str,
    *,
    step: str | None = None,
    tokens: int | None = None,
    cost: float | None = None,
    latency_ms: float | None = None,
    decision: str | None = None,
    attributes: Mapping[str, object] | None = None,
) -> Iterator[Span]:
    """Start a span as the current span, yielding it for further attributes.

    Started under whatever span is already current, so nesting a child inside a
    request span happens automatically via OTel context propagation. Standard
    metric attributes may be passed up front or set later on the yielded span
    (e.g. ``latency_ms`` once the step finishes).
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as sp:
        if step is not None:
            sp.set_attribute(ATTR_STEP, step)
        if attributes:
            for key, value in attributes.items():
                sp.set_attribute(key, value)  # type: ignore[arg-type]
        record_metrics(
            sp, tokens=tokens, cost=cost, latency_ms=latency_ms, decision=decision
        )
        yield sp


@contextmanager
def request_span(name: str = StepType.REQUEST, **attrs: object) -> Iterator[Span]:
    """Convenience parent span for a whole request. Its ``trace_id`` is the id
    every child span (and correlated log line) inherits."""
    with span(name, step=StepType.REQUEST, attributes=attrs or None) as sp:
        yield sp


@contextmanager
def timed_span(name: str, *, step: str | None = None) -> Iterator[Span]:
    """Like :func:`span` but records wall-clock ``latency_ms`` on exit."""
    start = time.monotonic()
    with span(name, step=step) as sp:
        try:
            yield sp
        finally:
            sp.set_attribute(ATTR_LATENCY, (time.monotonic() - start) * 1000.0)
