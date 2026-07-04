"""Structured JSON logging, correlated to traces by ``trace_id``.

A preconfigured logger emits one JSON object per line with the standard spine
fields (request id, agent, step, tool, tokens, cost, latency, outcome,
guardrail decision). When a log is emitted while an OTel span is active, the
active span's ``trace_id`` is attached automatically (hex, as OTel formats it).

Import-safe / no-network: standard-library ``logging`` + ``json`` plus the OTel
API for the trace-id lookup. The GCP Cloud Logging exporter is optional and
imported lazily.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import IO

from opentelemetry import trace

# Standard structured fields, always present in the payload (``None`` if unset).
STANDARD_FIELDS = (
    "request_id",
    "agent",
    "step",
    "tool",
    "tokens",
    "cost",
    "latency",
    "outcome",
    "guardrail_decision",
)


def current_trace_id() -> str | None:
    """Return the active span's trace id as a 32-char hex string, or ``None``
    when no valid span is in context."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return trace.format_trace_id(ctx.trace_id)


class SpineJsonFormatter(logging.Formatter):
    """Render log records as single-line JSON with the standard spine fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object | None] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for field in STANDARD_FIELDS:
            payload[field] = getattr(record, field, None)

        trace_id = current_trace_id()
        if trace_id is not None:
            payload["trace_id"] = trace_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def get_logger(
    name: str = "spine",
    *,
    level: int = logging.INFO,
    stream: IO[str] | None = None,
) -> logging.Logger:
    """Return a logger configured with :class:`SpineJsonFormatter`.

    Idempotent: a spine JSON handler is attached only once per logger. Pass
    ``stream`` (e.g. a ``StringIO``) to capture output; defaults to stderr.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not any(getattr(h, "_spine_json", False) for h in logger.handlers):
        handler = logging.StreamHandler(stream)
        handler.setFormatter(SpineJsonFormatter())
        handler._spine_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
        logger.propagate = False

    return logger


def log_event(
    logger: logging.Logger,
    message: str,
    *,
    level: int = logging.INFO,
    request_id: str | None = None,
    agent: str | None = None,
    step: str | None = None,
    tool: str | None = None,
    tokens: int | None = None,
    cost: float | None = None,
    latency: float | None = None,
    outcome: str | None = None,
    guardrail_decision: str | None = None,
) -> None:
    """Emit one structured event, populating the standard fields as ``extra``."""
    extra = {
        "request_id": request_id,
        "agent": agent,
        "step": step,
        "tool": tool,
        "tokens": tokens,
        "cost": cost,
        "latency": latency,
        "outcome": outcome,
        "guardrail_decision": guardrail_decision,
    }
    logger.log(level, message, extra=extra)


def cloud_logging_handler(*, name: str = "spine"):
    """Return a GCP Cloud Logging handler.

    Lazy import: ``google-cloud-logging`` is optional (install via the
    ``logging-gcp`` extra). Keeps this module importable without any GCP
    dependency, creds, or network.
    """
    try:
        import google.cloud.logging  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise ImportError(
            "Cloud Logging requires the 'logging-gcp' extra: "
            "pip install 'spine[logging-gcp]'"
        ) from exc

    client = google.cloud.logging.Client()
    return client.get_default_handler_class()(client, name=name)
