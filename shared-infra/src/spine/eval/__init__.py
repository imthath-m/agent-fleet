"""spine.eval — offline evaluation harness (Phase 3).

Public surface: versioned golden datasets, deterministic + LLM-judge metrics, a
runner that aggregates a predictor over a dataset, a CI gate that fails on
regression against a baseline, and result sinks (local JSONL; BigQuery adapter).

SDK-free and runnable locally with no GCP creds/network. Run the demo gate with
``python -m spine.eval``.
"""

from spine.eval.dataset import (
    SCHEMA_VERSION,
    DatasetError,
    GoldenDataset,
    GoldenExample,
    dump_dataset,
    example_dataset_path,
    load_dataset,
)
from spine.eval.gate import (
    Baseline,
    GateReport,
    Regression,
    compare_to_baseline,
    gate_main,
    load_baseline,
    run_gate,
    save_baseline,
)
from spine.eval.metrics import (
    FieldAccuracy,
    LlmJudge,
    Metric,
    MetricResult,
    Prediction,
    SchemaPassRate,
    ToolCallCorrectness,
    parse_judge_score,
)
from spine.eval.runner import (
    EvalResult,
    EvalSuite,
    ExampleResult,
    Predictor,
    agent_predictor,
    load_suite,
    parse_json_prediction,
    prediction_from_expected,
    run_eval,
)
from spine.eval.sink import (
    BigQueryResultSink,
    JsonlResultSink,
    ResultSink,
    result_to_row,
)

__all__ = [
    # dataset
    "SCHEMA_VERSION",
    "DatasetError",
    "GoldenDataset",
    "GoldenExample",
    "dump_dataset",
    "example_dataset_path",
    "load_dataset",
    # metrics
    "FieldAccuracy",
    "LlmJudge",
    "Metric",
    "MetricResult",
    "Prediction",
    "SchemaPassRate",
    "ToolCallCorrectness",
    "parse_judge_score",
    # runner
    "EvalResult",
    "EvalSuite",
    "ExampleResult",
    "Predictor",
    "agent_predictor",
    "load_suite",
    "parse_json_prediction",
    "prediction_from_expected",
    "run_eval",
    # gate
    "Baseline",
    "GateReport",
    "Regression",
    "compare_to_baseline",
    "gate_main",
    "load_baseline",
    "run_gate",
    "save_baseline",
    # sink
    "BigQueryResultSink",
    "JsonlResultSink",
    "ResultSink",
    "result_to_row",
]
