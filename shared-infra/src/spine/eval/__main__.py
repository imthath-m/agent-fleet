"""``python -m spine.eval`` — run an eval suite, write a baseline, or gate a run.

Subcommands:
  run       run a suite and print its summary (optionally append to a JSONL sink)
  baseline  run a suite and save its mean scores as a baseline JSON file
  gate      run a suite and fail (exit 1) on regression against a baseline

Every subcommand takes ``--suite module:factory`` (default: the packaged demo
suite), so the harness is runnable locally with no model, creds, or network.
"""

from __future__ import annotations

import argparse
import json
import sys

from spine.eval.gate import DEFAULT_THRESHOLD, gate_main
from spine.eval.runner import load_suite
from spine.eval.sink import JsonlResultSink

DEFAULT_SUITE = "spine.eval.example:build_suite"


def _cmd_run(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    result = suite.run()
    if args.sink:
        JsonlResultSink(args.sink).write(result)
    print(json.dumps(result.summary(), indent=2))
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    from spine.eval.gate import Baseline, save_baseline

    suite = load_suite(args.suite)
    result = suite.run()
    save_baseline(Baseline.from_result(result), args.out)
    print(f"wrote baseline for {result.dataset_name} v{result.dataset_version} -> {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spine.eval")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run a suite and print its summary")
    p_run.add_argument("--suite", default=DEFAULT_SUITE, help="'module:factory' EvalSuite")
    p_run.add_argument("--sink", help="append the summary to this JSONL file")
    p_run.set_defaults(func=_cmd_run)

    p_base = sub.add_parser("baseline", help="run a suite and save a baseline")
    p_base.add_argument("--suite", default=DEFAULT_SUITE, help="'module:factory' EvalSuite")
    p_base.add_argument("--out", required=True, help="path to write the baseline JSON")
    p_base.set_defaults(func=_cmd_baseline)

    p_gate = sub.add_parser("gate", help="fail on regression against a baseline")
    p_gate.add_argument("--suite", default=DEFAULT_SUITE, help="'module:factory' EvalSuite")
    p_gate.add_argument("--baseline", required=True, help="path to baseline JSON")
    p_gate.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)

    args = parser.parse_args(argv)

    if args.command == "gate":
        return gate_main(
            ["--suite", args.suite, "--baseline", args.baseline, "--threshold", str(args.threshold)]
        )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
