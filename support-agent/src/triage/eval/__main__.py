"""``python -m triage.eval [--live] [--out DIR] [--suite NAME ...] [--limit N]``

Without ``--live``: the five suites on the fake model, table only, nothing
written. With ``--live``: the real model (needs ``ANTHROPIC_API_KEY``); results
go to ``<out>/<UTC date>/``. Exit code 2 if ``--live`` has no key.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spine.models_anthropic import MissingApiKeyError

from triage.eval.live import RESULTS_DIR, SUITES, run_all


def _print_table(summary: dict) -> None:
    for name, s in summary["suites"].items():
        print(f"{name}  (n={s['n_examples']}, errors={s.get('n_errors', 0)})")
        for metric, score in s["mean_scores"].items():
            rate = s["pass_rates"].get(metric)
            extra = f"  pass={rate:.3f}" if rate is not None else ""
            print(f"  {metric:<28}{score:.3f}{extra}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triage.eval")
    parser.add_argument("--live", action="store_true", help="use the real Claude API")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="results root (live only)")
    parser.add_argument("--suite", nargs="+", choices=list(SUITES), help="suites to run")
    parser.add_argument("--limit", type=int, help="only the first N examples per suite")
    args = parser.parse_args(argv)

    try:
        summary = run_all(args.live, args.out, names=args.suite, limit=args.limit)
    except MissingApiKeyError as exc:
        print(f"error: --live needs an API key: {exc}", file=sys.stderr)
        return 2

    _print_table(summary)
    if args.live:
        u = summary["usage"]
        print(f"model={summary['model']} usage={u}")
        print(f"wrote {summary['out_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
