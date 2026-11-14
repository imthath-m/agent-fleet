"""Agreement between the LLM judge and human labels.

Usage: uv run python scripts/judge_agreement.py results/<date>
Reads judge_sheet.csv (human-filled) and judge_key.csv; writes judge_agreement.md.
Exit 2 if any human_pass is blank.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

TRUE = {"y", "yes", "true", "1", "pass"}
FALSE = {"n", "no", "false", "0", "fail"}


def to_bool(v: str) -> bool | None:
    s = str(v).strip().lower()
    return True if s in TRUE else False if s in FALSE else None


def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / (sx * sy)


def ranks(v: list[float]) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def _f(v: float | None) -> str:
    return "undefined" if v is None else f"{v:.3f}"


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    d = Path(args[0])
    sheet = read(d / "judge_sheet.csv")
    key = {r["item_id"]: r for r in read(d / "judge_key.csv")}
    blank = [r for r in sheet if to_bool(r.get("human_pass", "")) is None]
    if blank:
        print(f"{len(blank)} of {len(sheet)} unlabelled (human_pass blank or not y/n)",
              file=sys.stderr)
        return 2

    rows = []
    for r in sheet:
        k = key.get(r["item_id"])
        jp = to_bool(k["judge_pass"]) if k else None
        if jp is None:
            continue
        rows.append((r, k, jp, to_bool(r["human_pass"])))
    n = len(rows)
    if n == 0:
        print("no joinable rows", file=sys.stderr)
        return 2
    pairs = [(jp, hp) for _, _, jp, hp in rows]
    tp = sum(j and h for j, h in pairs)
    fp = sum(j and not h for j, h in pairs)
    fn = sum(not j and h for j, h in pairs)
    tn = sum(not j and not h for j, h in pairs)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    out = [
        "# Judge vs human agreement", "", f"- n: {n}",
        f"- raw agreement (pass/fail): {(tp + tn) / n:.3f}",
        f"- Cohen's kappa: {_f(kappa(pairs))}",
        f"- judge precision vs human (of judge-pass, human-pass): {_f(prec)}",
        f"- judge recall vs human (of human-pass, judge-pass): {_f(rec)}", "",
        "| | human pass | human fail |", "|---|---|---|",
        f"| judge pass | {tp} | {fp} |", f"| judge fail | {fn} | {tn} |", "",
    ]
    sc = []
    for r, k, _, _ in rows:
        try:
            sc.append((float(r["human_score"]), float(k["judge_score"])))
        except (ValueError, KeyError):
            pass
    if sc and len(sc) == n:
        h, j = [a for a, _ in sc], [b for _, b in sc]
        mae = sum(abs(a - b) for a, b in sc) / n
        out += ["Score agreement:", "", f"- Pearson: {_f(pearson(h, j))}",
                f"- Spearman: {_f(pearson(ranks(h), ranks(j)))}", f"- MAE: {mae:.3f}", ""]
    else:
        out += ["human_score not (fully) filled; score correlation skipped.", ""]
    out += ["## Disagreements", ""]
    dis = [(r, k, jp, hp) for r, k, jp, hp in rows if jp != hp]
    if not dis:
        out.append("None.")
    for r, k, jp, hp in dis:
        out += [f"- `{r['item_id']}` judge={'pass' if jp else 'fail'} "
                f"({k.get('judge_score')}) human={'pass' if hp else 'fail'} "
                f"({r.get('human_score') or '-'})",
                f"  - judge reason: {k.get('judge_reason', '')}",
                f"  - human notes: {r.get('human_notes', '')}"]
    (d / "judge_agreement.md").write_text("\n".join(out) + "\n")
    print(d / "judge_agreement.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
