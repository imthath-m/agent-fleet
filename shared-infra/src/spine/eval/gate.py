"""CI gate: compare a run against a stored baseline and fail on regression.

The baseline is a small JSON file of per-metric mean scores. A run regresses
when any baseline metric drops by more than ``threshold``. :func:`run_gate`
returns a process exit code (0 = pass, 1 = regression) so CI can call it
directly; :func:`gate_main` wires it to ``argv``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from spine.eval.runner import EvalResult, EvalSuite

DEFAULT_THRESHOLD = 0.01


@dataclass
class Baseline:
    """Stored reference metrics a run is gated against."""

    dataset_name: str
    dataset_version: str
    mean_scores: dict[str, float] = field(default_factory=dict)

    def to_json(self) -> dict[str, object]:
        return {
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "mean_scores": self.mean_scores,
        }

    @classmethod
    def from_result(cls, result: EvalResult) -> Baseline:
        return cls(
            dataset_name=result.dataset_name,
            dataset_version=result.dataset_version,
            mean_scores=dict(result.mean_scores),
        )


@dataclass
class Regression:
    """One metric that dropped past the threshold."""

    metric: str
    baseline: float
    current: float
    delta: float


@dataclass
class GateReport:
    """Outcome of comparing a run to a baseline."""

    passed: bool
    threshold: float
    regressions: list[Regression] = field(default_factory=list)
    checked: dict[str, float] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1

    def render(self) -> str:
        lines = [
            f"eval gate: {'PASS' if self.passed else 'FAIL'} "
            f"(threshold={self.threshold})",
        ]
        for metric, delta in sorted(self.checked.items()):
            marker = "  ok " if delta >= -self.threshold else "REGR "
            lines.append(f"  {marker} {metric}: delta={delta:+.4f}")
        for r in self.regressions:
            lines.append(
                f"  regression in {r.metric}: {r.baseline:.4f} -> "
                f"{r.current:.4f} (delta {r.delta:+.4f})"
            )
        return "\n".join(lines)


def load_baseline(path: str | Path) -> Baseline:
    data = json.loads(Path(path).read_text())
    return Baseline(
        dataset_name=data.get("dataset_name", ""),
        dataset_version=data.get("dataset_version", ""),
        mean_scores=data.get("mean_scores", {}),
    )


def save_baseline(baseline: Baseline, path: str | Path) -> None:
    Path(path).write_text(json.dumps(baseline.to_json(), indent=2) + "\n")


def compare_to_baseline(
    result: EvalResult,
    baseline: Baseline,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> GateReport:
    """Flag every baseline metric whose current score dropped by > ``threshold``."""
    regressions: list[Regression] = []
    checked: dict[str, float] = {}
    for metric, base_score in baseline.mean_scores.items():
        current = result.mean_scores.get(metric, 0.0)
        delta = current - base_score
        checked[metric] = delta
        if delta < -threshold:
            regressions.append(
                Regression(
                    metric=metric,
                    baseline=base_score,
                    current=current,
                    delta=delta,
                )
            )
    return GateReport(
        passed=not regressions,
        threshold=threshold,
        regressions=regressions,
        checked=checked,
    )


def run_gate(
    suite: EvalSuite,
    baseline: Baseline,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[int, GateReport, EvalResult]:
    """Run ``suite`` and gate it against ``baseline``.

    Returns ``(exit_code, report, result)``. ``exit_code`` is non-zero on any
    regression, so callers can ``sys.exit(exit_code)``.
    """
    result = suite.run()
    report = compare_to_baseline(result, baseline, threshold=threshold)
    return report.exit_code, report, result


def gate_main(argv: list[str] | None = None) -> int:
    """CLI-facing gate: build a suite from a factory, run it, print, exit code."""
    import argparse

    from spine.eval.runner import load_suite

    parser = argparse.ArgumentParser(prog="spine.eval gate")
    parser.add_argument(
        "--suite",
        required=True,
        help="dotted path 'module:factory' returning an EvalSuite",
    )
    parser.add_argument("--baseline", required=True, help="path to baseline JSON")
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD, help="max allowed drop"
    )
    args = parser.parse_args(argv)

    suite = load_suite(args.suite)
    baseline = load_baseline(args.baseline)
    exit_code, report, _ = run_gate(suite, baseline, threshold=args.threshold)
    print(report.render())
    return exit_code
