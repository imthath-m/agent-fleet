"""Build a human-label sheet (and hidden judge key) to check the resolution LLM judge.

Usage: uv run python scripts/judge_sheet.py results/<date> [--live] [--target 40]
--live runs extra generated tickets through classify->resolve and the real judge,
saving results/<date>/judge_pool.jsonl (calibration only; never part of a suite score).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TICKETS = ROOT / "data" / "generated" / "tickets.jsonl"
KB = ROOT / "data" / "kb" / "ubuntu_docs.jsonl"
SHUFFLE_SEED = 13
SHEET_COLS = ["item_id", "source", "ticket_subject", "ticket_text", "reference", "model_answer",
              "human_score", "human_pass", "human_notes"]
KEY_COLS = ["item_id", "judge_score", "judge_pass", "judge_reason"]

README = """# Judge check: labelling rubric

Fill the last three columns of `judge_sheet.csv` for every row. Do not open `judge_key.csv`
until you are done (it holds the LLM judge's scores).

- `human_score`: 0, 0.25, 0.5, 0.75 or 1
  - 0 = wrong, unrelated, or harmful
  - 0.25 = mostly wrong; at most one relevant fact
  - 0.5 = partially correct or incomplete; would not resolve the ticket alone
  - 0.75 = correct with minor gaps or noise
  - 1 = fully correct and complete per the reference
- `human_pass`: `y` if the answer correctly resolves the ticket per the reference, else `n`
- `human_notes`: optional free text

Then run `uv run python scripts/judge_agreement.py results/<date>`.
"""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def parse_reason(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return str(obj.get("reason", ""))
    except json.JSONDecodeError:
        pass
    return raw[:300]


def pick_tickets(tickets: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Round-robin across source_doc_id (first-seen order), deterministic."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in tickets:
        groups[t.get("source_doc_id", "")].append(t)
    picked: list[dict[str, Any]] = []
    queues = list(groups.values())
    while len(picked) < n and any(queues):
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop(0))
    return picked


def run_pool(results_dir: Path, n: int) -> list[dict[str, Any]]:
    from spine.eval.metrics import LlmJudge
    from spine.logging import get_logger
    from triage.eval.live import build_live_client

    from triage.classifier import classify
    from triage.kb import load_kb
    from triage.resolver import resolve
    from triage.schemas import Ticket

    client = build_live_client()
    kb = {d["doc_id"]: d["text"] for d in read_jsonl(KB)}
    retriever = load_kb()
    logger = get_logger("triage.judge_pool", stream=io.StringIO())
    judge = LlmJudge(client=client, criterion="resolution correctness", reference_key="answer")
    rows = []
    for t in pick_tickets(read_jsonl(TICKETS), n):
        inp = {k: t[k] for k in ("ticket_id", "text", "subject", "channel", "customer_id",
                                 "received_at")}
        expected = {"answer": kb.get(t.get("source_doc_id"), ""),
                    "citations": [t.get("source_doc_id")]}
        row: dict[str, Any] = {"suite": "judge_pool", "example_id": t["ticket_id"], "input": inp,
                               "expected": expected, "tags": [t.get("source_doc_id")],
                               "prediction": None, "error": None, "metrics": {}}
        try:
            ticket = Ticket.from_dict(inp)
            cls, _ = classify(ticket, model=client, logger=logger)
            if cls is None:
                raise RuntimeError("classification blocked")
            res, _ = resolve(ticket, cls, retriever=retriever, model=client, logger=logger)
            row["prediction"] = {"text": res.answer, "fields": res.to_dict(),
                                 "citations": res.citations, "tool_calls": None,
                                 "escalated": None}
            ex = SimpleNamespace(input=inp, expected=expected)
            m = judge.score(ex, SimpleNamespace(text=res.answer))
            row["metrics"]["llm_judge"] = {"score": m.score, "passed": m.passed,
                                           "detail": m.detail}
        except Exception as e:  # noqa: BLE001 - recorded per row, run continues
            row["error"] = f"{type(e).__name__}: {e}"
        rows.append(row)
    pool_path = results_dir / "judge_pool.jsonl"
    pool_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return rows


def to_item(row: dict[str, Any], source: str) -> tuple[dict[str, str], dict[str, str]]:
    inp = row.get("input") or {}
    pred = row.get("prediction") or {}
    ref = (row.get("expected") or {}).get("answer", "")
    j = (row.get("metrics") or {}).get("llm_judge") or {}
    item_id = f"{source}:{row['example_id']}"
    sheet = {"item_id": item_id, "source": source, "ticket_subject": inp.get("subject", ""),
             "ticket_text": inp.get("text", ""), "reference": ref,
             "model_answer": pred.get("text") or "", "human_score": "", "human_pass": "",
             "human_notes": ""}
    key = {"item_id": item_id, "judge_score": j.get("score", ""),
           "judge_pass": j.get("passed", ""),
           "judge_reason": parse_reason((j.get("detail") or {}).get("raw"))}
    return sheet, key


def write_csv(path: Path, cols: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results_dir", type=Path)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--target", type=int, default=40)
    args = ap.parse_args(argv)
    d: Path = args.results_dir

    res_rows = read_jsonl(d / "resolution.jsonl")
    if not res_rows:
        print(f"error: {d / 'resolution.jsonl'} missing or empty", file=sys.stderr)
        return 2
    if args.live:
        try:
            pool = run_pool(d, max(0, args.target - len(res_rows)))
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    else:
        pool = read_jsonl(d / "judge_pool.jsonl")

    items = [("resolution", r) for r in res_rows] + [("pool", r) for r in pool]
    usable = [(s, r) for s, r in items if not r.get("error") and r.get("prediction")
              and (r.get("metrics") or {}).get("llm_judge")]
    n_err = len(items) - len(usable)
    pairs = [to_item(r, s) for s, r in usable]
    random.Random(SHUFFLE_SEED).shuffle(pairs)
    write_csv(d / "judge_sheet.csv", SHEET_COLS, [p[0] for p in pairs])
    write_csv(d / "judge_key.csv", KEY_COLS, [p[1] for p in pairs])
    (d / "judge_sheet_README.md").write_text(README)
    print(f"wrote {len(pairs)} items to {d / 'judge_sheet.csv'} (key: judge_key.csv)")
    if len(pairs) < args.target:
        print(f"!!! WARNING: only {len(pairs)} items, fewer than the {args.target} target "
              f"({n_err} excluded for errors/missing judge). "
              "Run with --live to build the judge pool.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
