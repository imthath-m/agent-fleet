"""Observability sink + metric emitters (plan.md §9).

Every request emits one :class:`MetricRecord` — latency, cost, tokens, quality
(eval) score, escalation, and tool errors — to a :class:`MetricsSink`.
:class:`InMemoryMetricsSink` and :class:`JsonlMetricsSink` are the local,
SDK-free defaults used in tests and local dev; :class:`BigQueryMetricsSink` is a
lazy-import adapter behind the same interface for production (deps under the
``bigquery`` extra, mirroring ``spine.eval.sink``); it is never exercised in
tests.

:func:`metrics_report` summarises recorded metrics (p50/p95 latency, cost per
request, escalation rate, tool-error rate, mean quality) — the local stand-in
for the Looker dashboard. ``python -m spine.obs <file.jsonl>`` prints that
report for a JSONL sink.

Import-safe / no-network: standard-library ``json`` + ``statistics`` only.
"""

from __future__ import annotations

import json
import math
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Record
# --------------------------------------------------------------------------- #


@dataclass
class MetricRecord:
    """Per-request metrics emitted at the end of a run.

    ``quality_score`` is the run's eval/quality signal (``None`` when unscored).
    ``decision`` is the aggregate guardrail decision; ``outcome`` is a coarse
    delivered/withheld label. Field names double as the row keys a sink stores.
    """

    request_id: str
    agent: str
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    tokens: int = 0
    quality_score: float | None = None
    escalated: bool = False
    tool_errors: int = 0
    decision: str = ""
    outcome: str = ""
    timestamp: float = field(default_factory=time.time)


def record_to_row(record: MetricRecord) -> dict[str, Any]:
    """Flatten a :class:`MetricRecord` into a JSON-serialisable row for a sink."""
    return asdict(record)


# --------------------------------------------------------------------------- #
# Sink interface + implementations
# --------------------------------------------------------------------------- #


class MetricsSink(ABC):
    """Where per-request metric records are written for later analysis."""

    @abstractmethod
    def record(self, record: MetricRecord) -> None:
        """Persist one request's metrics."""

    @abstractmethod
    def read(self) -> list[dict[str, Any]]:
        """Read back every persisted metric row, oldest first."""


class InMemoryMetricsSink(MetricsSink):
    """Local, SDK-free sink backed by a list. Default for tests and local dev."""

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def record(self, record: MetricRecord) -> None:
        self._rows.append(record_to_row(record))

    def read(self) -> list[dict[str, Any]]:
        return list(self._rows)


class JsonlMetricsSink(MetricsSink):
    """Local JSONL sink: one metric row per line, appended in write order."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(self, record: MetricRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record_to_row(record)) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows


class BigQueryMetricsSink(MetricsSink):
    """BigQuery sink for production dashboards (Looker reads this table).

    The ``google-cloud-bigquery`` SDK is imported lazily on first use so
    importing this module (and the whole ``spine`` surface) needs no GCP deps,
    creds, or network. Install the client via the ``bigquery`` extra.
    """

    def __init__(self, table: str, *, client: Any | None = None) -> None:
        self.table = table
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import bigquery  # lazy: keeps core SDK-free

            self._client = bigquery.Client()
        return self._client

    def record(self, record: MetricRecord) -> None:
        client = self._get_client()
        errors = client.insert_rows_json(self.table, [record_to_row(record)])
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors}")

    def read(self) -> list[dict[str, Any]]:
        client = self._get_client()
        rows = client.query(f"SELECT * FROM `{self.table}`").result()
        return [dict(row) for row in rows]


# --------------------------------------------------------------------------- #
# Report (local stand-in for the Looker dashboard)
# --------------------------------------------------------------------------- #


@dataclass
class MetricsReport:
    """Aggregate view of recorded metrics, as the dashboard would show them."""

    count: int
    latency_p50_ms: float
    latency_p95_ms: float
    mean_latency_ms: float
    cost_per_request: float
    total_cost_usd: float
    total_tokens: int
    escalation_rate: float
    tool_error_rate: float
    mean_quality: float | None

    def render(self) -> str:
        quality = "n/a" if self.mean_quality is None else f"{self.mean_quality:.3f}"
        return "\n".join(
            [
                f"metrics report ({self.count} requests)",
                f"  latency p50/p95 ms : {self.latency_p50_ms:.1f} / {self.latency_p95_ms:.1f}",
                f"  mean latency ms    : {self.mean_latency_ms:.1f}",
                f"  cost / request usd : {self.cost_per_request:.6f}",
                f"  total cost usd     : {self.total_cost_usd:.6f}",
                f"  total tokens       : {self.total_tokens}",
                f"  escalation rate    : {self.escalation_rate:.3f}",
                f"  tool error rate    : {self.tool_error_rate:.3f}",
                f"  mean quality       : {quality}",
            ]
        )


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile (``pct`` in ``[0, 100]``). Empty -> 0.0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (pct / 100.0)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(ordered[lo])
    return ordered[lo] * (hi - rank) + ordered[hi] * (rank - lo)


def _as_row(item: MetricRecord | Mapping[str, Any]) -> Mapping[str, Any]:
    return record_to_row(item) if isinstance(item, MetricRecord) else item


def metrics_report(records: Sequence[MetricRecord | Mapping[str, Any]]) -> MetricsReport:
    """Summarise recorded metrics into a :class:`MetricsReport`.

    Accepts either :class:`MetricRecord` objects or the row dicts a sink's
    :meth:`~MetricsSink.read` returns.
    """
    rows = [_as_row(r) for r in records]
    n = len(rows)
    if n == 0:
        return MetricsReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, None)

    latencies = [float(r.get("latency_ms", 0.0)) for r in rows]
    costs = [float(r.get("cost_usd", 0.0)) for r in rows]
    tokens = [int(r.get("tokens", 0)) for r in rows]
    escalations = sum(1 for r in rows if r.get("escalated"))
    with_tool_errors = sum(1 for r in rows if int(r.get("tool_errors", 0)) > 0)
    qualities = [float(r["quality_score"]) for r in rows if r.get("quality_score") is not None]

    total_cost = sum(costs)
    return MetricsReport(
        count=n,
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
        mean_latency_ms=sum(latencies) / n,
        cost_per_request=total_cost / n,
        total_cost_usd=total_cost,
        total_tokens=sum(tokens),
        escalation_rate=escalations / n,
        tool_error_rate=with_tool_errors / n,
        mean_quality=(sum(qualities) / len(qualities)) if qualities else None,
    )


def report_main(argv: list[str] | None = None) -> int:
    """``python -m spine.obs <file.jsonl>`` — print a report for a JSONL sink."""
    import argparse

    parser = argparse.ArgumentParser(prog="spine.obs")
    parser.add_argument("path", help="path to a JSONL metrics sink file")
    args = parser.parse_args(argv)

    report = metrics_report(JsonlMetricsSink(args.path).read())
    print(report.render())
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(report_main())
