from spine.tracing import (
    ATTR_COST,
    ATTR_LATENCY,
    ATTR_TOKENS,
    StepType,
    configure_tracing,
    record_metrics,
    request_span,
    span,
)


def _spans_by_name(exporter):
    return {s.name: s for s in exporter.get_finished_spans()}


def test_child_spans_nest_under_request_span():
    exporter = configure_tracing()

    with request_span() as parent:
        parent_span_id = parent.get_span_context().span_id
        with span(StepType.MODEL_CALL, step=StepType.MODEL_CALL) as model_sp:
            record_metrics(model_sp, tokens=42, cost=0.001, latency_ms=12.5)
        with span(StepType.TOOL_CALL, step=StepType.TOOL_CALL) as tool_sp:
            record_metrics(tool_sp, tokens=7, cost=0.0002, latency_ms=3.0)

    spans = _spans_by_name(exporter)
    assert set(spans) == {StepType.REQUEST, StepType.MODEL_CALL, StepType.TOOL_CALL}

    # Each child's parent span id is the request span's span id.
    assert spans[StepType.MODEL_CALL].parent.span_id == parent_span_id
    assert spans[StepType.TOOL_CALL].parent.span_id == parent_span_id
    # The request span itself is a root (no parent).
    assert spans[StepType.REQUEST].parent is None


def test_all_spans_share_one_trace_id():
    exporter = configure_tracing()

    with request_span():
        with span(StepType.MODEL_CALL):
            pass
        with span(StepType.TOOL_CALL):
            pass

    trace_ids = {s.context.trace_id for s in exporter.get_finished_spans()}
    assert len(trace_ids) == 1


def test_standard_metric_attributes_present():
    exporter = configure_tracing()

    with request_span():
        with span(StepType.MODEL_CALL) as sp:
            record_metrics(sp, tokens=100, cost=0.0025, latency_ms=42.0)

    model_sp = _spans_by_name(exporter)[StepType.MODEL_CALL]
    assert model_sp.attributes[ATTR_TOKENS] == 100
    assert model_sp.attributes[ATTR_COST] == 0.0025
    assert model_sp.attributes[ATTR_LATENCY] == 42.0
