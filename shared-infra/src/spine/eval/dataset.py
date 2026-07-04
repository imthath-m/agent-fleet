"""Versioned golden-dataset format (input -> expected), loadable from repo files.

A dataset is a JSONL file: an optional header line carries dataset metadata
(``schema_version``, ``name``, ``dataset_version``); every other line is one
:class:`GoldenExample`. This keeps datasets diff-friendly, appendable, and
reviewable in the repo. The loader validates the schema and round-trips with
:func:`dump_dataset`.

SDK-free / no-network: standard-library ``json`` only.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class DatasetError(ValueError):
    """Raised when a dataset file fails schema validation."""


@dataclass(frozen=True)
class GoldenExample:
    """One labelled case: an ``input`` and its ``expected`` output fields."""

    id: str
    input: Any
    expected: dict[str, Any]
    tags: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "id": self.id,
            "input": self.input,
            "expected": self.expected,
        }
        if self.tags:
            row["tags"] = list(self.tags)
        return row

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> GoldenExample:
        if "id" not in row:
            raise DatasetError(f"example missing 'id': {row!r}")
        if "input" not in row:
            raise DatasetError(f"example {row['id']!r} missing 'input'")
        expected = row.get("expected")
        if not isinstance(expected, dict):
            raise DatasetError(f"example {row['id']!r} 'expected' must be an object")
        tags = tuple(row.get("tags", ()))
        return cls(id=str(row["id"]), input=row["input"], expected=expected, tags=tags)


@dataclass(frozen=True)
class GoldenDataset:
    """A named, versioned collection of :class:`GoldenExample`."""

    name: str
    version: str
    examples: tuple[GoldenExample, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __iter__(self) -> Iterable[GoldenExample]:
        return iter(self.examples)

    def __len__(self) -> int:
        return len(self.examples)


def _is_header(row: dict[str, Any]) -> bool:
    return "id" not in row and ("schema_version" in row or "name" in row)


def load_dataset(path: str | Path) -> GoldenDataset:
    """Load and validate a golden dataset from a JSONL file.

    Raises :class:`DatasetError` on malformed JSON, a wrong schema version, a
    missing required field, or duplicate example ids.
    """
    path = Path(path)
    name = path.stem
    version = "0"
    schema_version = SCHEMA_VERSION
    examples: list[GoldenExample] = []
    seen: set[str] = set()

    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise DatasetError(f"{path}:{lineno}: expected a JSON object")

        if _is_header(row):
            schema_version = int(row.get("schema_version", SCHEMA_VERSION))
            if schema_version != SCHEMA_VERSION:
                raise DatasetError(
                    f"{path}: unsupported schema_version {schema_version} "
                    f"(expected {SCHEMA_VERSION})"
                )
            name = str(row.get("name", name))
            version = str(row.get("dataset_version", version))
            continue

        example = GoldenExample.from_json(row)
        if example.id in seen:
            raise DatasetError(f"{path}:{lineno}: duplicate example id {example.id!r}")
        seen.add(example.id)
        examples.append(example)

    if not examples:
        raise DatasetError(f"{path}: dataset has no examples")

    return GoldenDataset(
        name=name,
        version=version,
        examples=tuple(examples),
        schema_version=schema_version,
    )


def dump_dataset(dataset: GoldenDataset, path: str | Path) -> None:
    """Write a dataset back to JSONL (header line + one example per line)."""
    path = Path(path)
    header = {
        "schema_version": dataset.schema_version,
        "name": dataset.name,
        "dataset_version": dataset.version,
    }
    lines = [json.dumps(header)]
    lines.extend(json.dumps(ex.to_json()) for ex in dataset.examples)
    path.write_text("\n".join(lines) + "\n")


def example_dataset_path() -> Path:
    """Path to the packaged example golden dataset used by tests and demos."""
    return Path(__file__).parent / "data" / "support_resolution.jsonl"
