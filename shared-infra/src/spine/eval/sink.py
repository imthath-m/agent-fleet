"""Results sinks: persist :class:`EvalResult` summaries for trend tracking.

:class:`ResultSink` is the interface. :class:`JsonlResultSink` is the local,
SDK-free default — it appends one JSON object per run and reads them back, so
tests and local dev need no cloud. :class:`BigQueryResultSink` is a lazy-import
adapter behind the same interface for CI/production (deps under the ``bigquery``
extra); it is never exercised in tests.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from spine.eval.runner import EvalResult


def result_to_row(result: EvalResult, *, run_at: float | None = None) -> dict[str, Any]:
    """Flatten an :class:`EvalResult` into a JSON-serialisable row for a sink."""
    row = result.summary()
    row["run_at"] = time.time() if run_at is None else run_at
    return row


class ResultSink(ABC):
    """Where eval-run summaries are written for later trend analysis."""

    @abstractmethod
    def write(self, result: EvalResult) -> None:
        """Persist one run's summary."""

    @abstractmethod
    def read(self) -> list[dict[str, Any]]:
        """Read back every persisted run summary, oldest first."""


class JsonlResultSink(ResultSink):
    """Local JSONL sink: one run summary per line, appended in write order."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(self, result: EvalResult) -> None:
        row = result_to_row(result)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows


class BigQueryResultSink(ResultSink):
    """BigQuery sink for CI/production trend tracking.

    The ``google-cloud-bigquery`` SDK is imported lazily on first use so importing
    this module (and the whole ``spine.eval`` surface) needs no GCP deps, creds,
    or network. Install the client via the ``bigquery`` extra.
    """

    def __init__(self, table: str, *, client: Any | None = None) -> None:
        self.table = table
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import bigquery  # lazy: keeps core SDK-free

            self._client = bigquery.Client()
        return self._client

    def write(self, result: EvalResult) -> None:
        client = self._get_client()
        errors = client.insert_rows_json(self.table, [result_to_row(result)])
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors}")

    def read(self) -> list[dict[str, Any]]:
        client = self._get_client()
        rows = client.query(f"SELECT * FROM `{self.table}`").result()
        return [dict(row) for row in rows]
