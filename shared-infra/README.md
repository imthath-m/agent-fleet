# spine

Shared agentic-AI platform library for production agents on GCP. `spine/`
centralizes the cross-cutting concerns — model access, tracing, logging,
evaluation, guardrails, HITL, RAG, memory, and observability — so each product
agent only writes domain logic.

The core is **SDK-free and fully testable with no GCP creds or network**: every
GCP backend sits behind a lazy-import adapter that shares an interface with a
local in-memory/JSONL default. Tests run entirely on in-process fakes.

## Component map

| Module | Purpose | Local default | GCP adapter (lazy) |
| --- | --- | --- | --- |
| `models.py` | Centralized model config, client interface, retry/timeout/cost wrapper | `FakeModelClient` | Vertex/Gemini (`models_vertex`) |
| `agent.py` | Minimal base Agent (instructions + tools + model) | `FakeModelClient` | ADK adapter |
| `tracing.py` | OpenTelemetry span tree + standard metric attributes | `InMemorySpanExporter` | Cloud Trace |
| `logging.py` | Structured JSON logs correlated by `trace_id` | stderr handler | Cloud Logging |
| `eval/` | Golden datasets, metrics + LLM judge, runner, CI regression gate, sinks | `JsonlResultSink` | BigQuery |
| `guardrails.py` | Input/output guards (PII, injection, topic, schema, citation, confidence) | deterministic | — |
| `hitl.py` | Human-in-the-loop escalation queue | `InMemoryEscalationStore` | Firestore |
| `rag.py` | Retrieval + citation plumbing, namespaced per product | `InMemoryRetriever` | Vertex AI Search |
| `memory.py` | Session state + long-term cross-session memory | in-memory stores | Firestore / Memory Bank |
| `obs.py` | Per-request metric sink + metrics report (latency/cost/quality/escalation) | `InMemoryMetricsSink` / `JsonlMetricsSink` | BigQuery |
| `reference_agent.py` | Reference agent composing every component end to end | all of the above | — |

## Install

Requires Python 3.11 and [`uv`](https://docs.astral.sh/uv/). From `shared-infra/`:

```bash
uv sync
```

GCP backends are optional extras (`vertex`, `adk`, `tracing-gcp`, `logging-gcp`,
`bigquery`, `firestore`) — not needed for local dev, tests, or the demo.

## Run the tests and linter

```bash
uv run pytest
uv run ruff check
```

## Run the reference-agent demo

One scripted request through the whole pipeline — prints the span tree,
correlated logs, guardrail decisions, and a metrics summary:

```bash
uv run python -m spine.reference_agent
```

`spine.reference_agent.ReferenceAgent.run(request)` is the single entry point:
input guardrails → RAG retrieval with citations → wrapped model call → output
guardrails + confidence gating → HITL escalation when low-confidence →
session/memory read+write → a tracing span per step → structured logs → a metric
record to the obs sink.

## Run the eval gate

Run a suite and fail on regression against a stored baseline (exit 1 on
regression). The reference agent is gated against its committed baseline (this
is the step CI runs):

```bash
uv run python -m spine.eval gate \
  --suite spine.reference_agent:build_reference_suite \
  --baseline baselines/reference_agent.json
```

`python -m spine.eval` also runs the packaged demo suite
(`spine.eval.example:build_suite`) with `run` / `baseline` / `gate` subcommands.

## Summarize recorded metrics

`obs.py` records per-request metrics to a sink; `metrics_report` (and the CLI)
summarize p50/p95 latency, cost per request, escalation rate, tool-error rate,
and mean quality — the local stand-in for the production Looker dashboard:

```bash
uv run python -m spine.obs path/to/metrics.jsonl
```
