import math

from spine.obs import (
    InMemoryMetricsSink,
    JsonlMetricsSink,
    MetricRecord,
    metrics_report,
    percentile,
)


def _rec(**kw) -> MetricRecord:
    base = dict(request_id="r", agent="a", latency_ms=0.0, cost_usd=0.0, tokens=0)
    base.update(kw)
    return MetricRecord(**base)


# --------------------------------------------------------------------------- #
# Sinks
# --------------------------------------------------------------------------- #


def test_in_memory_sink_round_trip():
    sink = InMemoryMetricsSink()
    sink.record(_rec(request_id="r1", latency_ms=10.0))
    sink.record(_rec(request_id="r2", latency_ms=20.0))

    rows = sink.read()
    assert [r["request_id"] for r in rows] == ["r1", "r2"]
    assert rows[0]["latency_ms"] == 10.0


def test_jsonl_sink_round_trip(tmp_path):
    path = tmp_path / "metrics.jsonl"
    sink = JsonlMetricsSink(path)
    sink.record(_rec(request_id="r1", cost_usd=0.001))
    sink.record(_rec(request_id="r2", cost_usd=0.002))

    rows = sink.read()
    assert [r["request_id"] for r in rows] == ["r1", "r2"]
    assert rows[1]["cost_usd"] == 0.002


def test_jsonl_sink_read_missing_file(tmp_path):
    assert JsonlMetricsSink(tmp_path / "nope.jsonl").read() == []


# --------------------------------------------------------------------------- #
# Percentile
# --------------------------------------------------------------------------- #


def test_percentile_interpolates_like_numpy():
    values = [10, 20, 30, 40]
    assert percentile(values, 50) == 25.0  # midpoint of 20 and 30
    assert math.isclose(percentile(values, 95), 38.5)
    assert percentile(values, 0) == 10.0
    assert percentile(values, 100) == 40.0


def test_percentile_edge_cases():
    assert percentile([], 50) == 0.0
    assert percentile([7.0], 95) == 7.0


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def test_metrics_report_summarises_latency_cost_and_escalation():
    records = [
        _rec(latency_ms=10.0, cost_usd=0.001, tokens=100, quality_score=0.9),
        _rec(latency_ms=20.0, cost_usd=0.002, tokens=200, quality_score=0.5, escalated=True),
        _rec(latency_ms=30.0, cost_usd=0.003, tokens=300, quality_score=1.0, tool_errors=2),
        _rec(latency_ms=40.0, cost_usd=0.004, tokens=400, quality_score=None),
    ]
    report = metrics_report(records)

    assert report.count == 4
    assert report.latency_p50_ms == 25.0
    assert math.isclose(report.latency_p95_ms, 38.5)
    assert math.isclose(report.mean_latency_ms, 25.0)
    assert math.isclose(report.total_cost_usd, 0.010)
    assert math.isclose(report.cost_per_request, 0.0025)
    assert report.total_tokens == 1000
    assert report.escalation_rate == 0.25  # 1 of 4
    assert report.tool_error_rate == 0.25  # 1 of 4 had tool errors
    # mean quality over the three scored records (None is skipped)
    assert math.isclose(report.mean_quality, (0.9 + 0.5 + 1.0) / 3)


def test_metrics_report_accepts_sink_rows():
    sink = InMemoryMetricsSink()
    sink.record(_rec(latency_ms=5.0, escalated=True))
    sink.record(_rec(latency_ms=15.0))

    report = metrics_report(sink.read())
    assert report.count == 2
    assert report.escalation_rate == 0.5
    assert report.latency_p50_ms == 10.0


def test_metrics_report_empty():
    report = metrics_report([])
    assert report.count == 0
    assert report.mean_quality is None
    assert "0 requests" in report.render()
