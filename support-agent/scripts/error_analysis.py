"""Mechanical error analysis of a live eval results dir.

Usage: uv run python scripts/error_analysis.py results/<date> [--allow-fake]
Writes <dir>/error_analysis.md. Patterns are derived only from the result files.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SUITES = ["classification", "resolution", "actions", "escalation", "triage"]
MAX_EXAMPLES = 5
JUDGE_THRESHOLD = 0.7


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _metric(row: dict[str, Any], name: str) -> dict[str, Any]:
    m = (row.get("metrics") or {}).get(name)
    return m if isinstance(m, dict) else {}


def _detail(row: dict[str, Any], name: str) -> dict[str, Any]:
    d = _metric(row, name).get("detail")
    return d if isinstance(d, dict) else {}


def _failed(row: dict[str, Any], name: str) -> bool:
    m = _metric(row, name)
    return bool(m) and m.get("passed") is False


def is_failure(row: dict[str, Any]) -> bool:
    if row.get("error"):
        return True
    return any(isinstance(m, dict) and m.get("passed") is False for m in
               (row.get("metrics") or {}).values())


def judge_reason(row: dict[str, Any]) -> str:
    raw = _detail(row, "llm_judge").get("raw")
    if not isinstance(raw, str):
        return ""
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return str(obj.get("reason", ""))
    except json.JSONDecodeError:
        pass
    return raw[:200]


def patterns(suite: str, row: dict[str, Any]) -> list[str]:
    """Failure-pattern labels for one failing row (a row may have several)."""
    out: list[str] = []
    if row.get("error"):
        out.append("pipeline error")
    if _failed(row, "schema_pass_rate"):
        d = _detail(row, "schema_pass_rate")
        out.append(f"schema fail (missing: {', '.join(map(str, d.get('missing') or [])) or '-'})")
    if _failed(row, "grounding_rate"):
        out.append("grounding fail")
    if _failed(row, "llm_judge"):
        s = _metric(row, "llm_judge").get("score")
        if isinstance(s, int | float):
            out.append("judge score < 0.3" if s < 0.3 else "judge score 0.3-0.7")
        else:
            out.append("judge fail (no score)")
    for f, mm in (_detail(row, "field_accuracy").get("mismatches") or {}).items():
        if isinstance(mm, dict):
            out.append(f"{f}: expected {mm.get('expected')} -> got {mm.get('got')}")
    if suite == "actions" and _failed(row, "tool_call_correctness"):
        d = _detail(row, "tool_call_correctness")
        exp, got = Counter(d.get("expected") or []), Counter(d.get("got") or [])
        out += [f"missing tool: {t}" for t in sorted(exp - got)]
        out += [f"extra tool: {t}" for t in sorted(got - exp)]
    if suite == "escalation" and _failed(row, "escalation_accuracy"):
        d = _detail(row, "escalation_accuracy")
        out.append("false negative (missed escalation)" if d.get("expected")
                   else "false positive (needless escalation)")
    return out or ["failed (no recognised metric detail)"]


def _clip(x: Any, n: int = 200) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _fmt(v: Any) -> str:
    return f"{v:.3f}" if isinstance(v, int | float) else "n/a"


def _example(suite: str, row: dict[str, Any]) -> list[str]:
    pred = row.get("prediction") or {}
    inp = row.get("input") or {}
    lines = [f"- `{row.get('example_id')}` tags={row.get('tags') or []}",
             f"  - ticket: {_clip(inp.get('text', inp))}",
             f"  - expected: {_clip(row.get('expected'))}"]
    shown = {k: v for k, v in pred.items() if v not in (None, "", [], {})}
    if suite in ("resolution", "triage"):
        shown = {k: shown[k] for k in ("text", "citations") if k in shown}
    lines.append(f"  - predicted: {_clip(shown)}")
    if row.get("error"):
        lines.append(f"  - error: {_clip(row['error'])}")
    for name, m in (row.get("metrics") or {}).items():
        if isinstance(m, dict) and m.get("passed") is False:
            d = m.get("detail")
            extra = judge_reason(row) if name == "llm_judge" else _clip(d, 160)
            lines.append(f"  - {name}: score={_fmt(m.get('score'))} {extra}")
    return lines


def suite_table(summary: dict[str, Any]) -> list[str]:
    lines = ["| suite | n | metric means | pass rates | errors |", "|---|---|---|---|---|"]
    for name in SUITES:
        s = (summary.get("suites") or {}).get(name)
        if not s:
            lines.append(f"| {name} | - | missing | - | - |")
            continue
        means = ", ".join(f"{k}={_fmt(v)}" for k, v in (s.get("mean_scores") or {}).items())
        rates = ", ".join(f"{k}={_fmt(v)}" for k, v in (s.get("pass_rates") or {}).items())
        lines.append(f"| {name} | {s.get('n_examples')} | {means} | {rates} | "
                     f"{s.get('n_errors')} |")
    return lines


def build_report(results_dir: Path, summary: dict[str, Any]) -> str:
    usage = summary.get("usage") or {}
    cost = usage.get("cost_usd")
    out = [
        f"# Error analysis ({str(summary.get('mode')).upper()} run)", "",
        f"**MODE: {str(summary.get('mode')).upper()}**", "",
        f"- model: {summary.get('model')}", f"- judge_model: {summary.get('judge_model')}",
        f"- run_at: {summary.get('run_at')}", f"- git_sha: {summary.get('git_sha')}",
        f"- usage: {usage.get('calls')} calls, {usage.get('input_tokens')} in, "
        f"{usage.get('output_tokens')} out, cost_usd={'n/a' if cost is None else cost}",
        "", "## Scores", "", *suite_table(summary), "",
    ]
    for suite in SUITES:
        rows = _load_rows(results_dir / f"{suite}.jsonl")
        out += [f"## {suite}", ""]
        if not rows:
            out += [f"No {suite}.jsonl rows found.", ""]
            continue
        fails = [r for r in rows if is_failure(r)]
        if not fails:
            out += [f"No failures in {len(rows)} examples.", ""]
            continue
        counts: Counter[str] = Counter()
        tag_counts: Counter[str] = Counter()
        for r in fails:
            counts.update(set(patterns(suite, r)))
            tag_counts.update(r.get("tags") or [])
        out += [f"{len(fails)} of {len(rows)} examples failed.", "", "Failure patterns:", ""]
        out += [f"- {n}x {p}" for p, n in counts.most_common()]
        if tag_counts:
            out += ["", "Tags of failing examples: "
                    + ", ".join(f"{t} ({n})" for t, n in tag_counts.most_common())]
        out += ["", f"Examples (up to {MAX_EXAMPLES}):", ""]
        for r in fails[:MAX_EXAMPLES]:
            out += _example(suite, r)
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results_dir", type=Path)
    ap.add_argument("--allow-fake", action="store_true")
    args = ap.parse_args(argv)
    sp = args.results_dir / "summary.json"
    if not sp.exists():
        print(f"error: {sp} not found", file=sys.stderr)
        return 2
    summary = json.loads(sp.read_text())
    if summary.get("mode") != "live" and not args.allow_fake:
        print(f"error: summary mode is {summary.get('mode')!r}, not 'live'; "
              "pass --allow-fake to analyse anyway", file=sys.stderr)
        return 2
    out = args.results_dir / "error_analysis.md"
    out.write_text(build_report(args.results_dir, summary) + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
