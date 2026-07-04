import io
import json
import logging

from opentelemetry import trace

from spine.logging import (
    STANDARD_FIELDS,
    SpineJsonFormatter,
    get_logger,
    log_event,
)
from spine.tracing import StepType, configure_tracing, request_span


def _capture_logger(name):
    buffer = io.StringIO()
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(SpineJsonFormatter())
    logger.addHandler(handler)
    return logger, buffer


def _lines(buffer):
    return [json.loads(line) for line in buffer.getvalue().splitlines()]


def test_log_lines_are_json_with_standard_fields():
    logger, buffer = _capture_logger("spine.test.fields")

    log_event(
        logger,
        "model call done",
        request_id="req-1",
        agent="greeter",
        step=StepType.MODEL_CALL,
        tokens=42,
        cost=0.001,
        latency=12.5,
        outcome="ok",
    )

    (record,) = _lines(buffer)
    assert record["message"] == "model call done"
    # Every standard field is present; unset ones default to None.
    for field in STANDARD_FIELDS:
        assert field in record
    assert record["request_id"] == "req-1"
    assert record["agent"] == "greeter"
    assert record["step"] == StepType.MODEL_CALL
    assert record["tokens"] == 42
    assert record["outcome"] == "ok"
    assert record["tool"] is None
    assert record["guardrail_decision"] is None


def test_log_correlates_trace_id_with_active_span():
    configure_tracing()
    logger, buffer = _capture_logger("spine.test.trace")

    with request_span() as sp:
        expected = trace.format_trace_id(sp.get_span_context().trace_id)
        log_event(logger, "inside span", request_id="req-2", step=StepType.REQUEST)

    (record,) = _lines(buffer)
    assert record["trace_id"] == expected


def test_no_trace_id_outside_span():
    logger, buffer = _capture_logger("spine.test.notrace")

    log_event(logger, "no active span", request_id="req-3")

    (record,) = _lines(buffer)
    assert "trace_id" not in record


def test_get_logger_is_idempotent():
    logger = get_logger("spine.test.idempotent", stream=io.StringIO())
    before = len(logger.handlers)
    get_logger("spine.test.idempotent", stream=io.StringIO())
    assert len(logger.handlers) == before
