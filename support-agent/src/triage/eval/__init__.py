"""Triage eval suites, built on `spine.eval`. Nothing is re-implemented here —
datasets, metrics, the runner and the gate all come from the spine.
"""

from triage.eval.suites import build_classification_suite

__all__ = ["build_classification_suite"]
