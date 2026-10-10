# Agent Fleet

A shared Python library for building and evaluating AI agents, and a
support-ticket triage agent built on top of it.

The idea: each business agent (support, invoices, leads, meetings, contracts)
should only write its own domain logic. Model access, guardrails, human review,
retrieval, memory, tracing and evals live once in a shared library and every
agent reuses them.

## Status

Prototype. What exists today:

- **`shared-infra/`**: the `spine` library. Built and tested.
- **`support-agent/`**: the Triage agent. Built and tested.
- **The other four agents**: design notes (`plan.md`) only.

Everything runs locally on in-memory fakes, including a scripted stand-in for
the model, so tests and evals need no credentials or network. Adapters for
Gemini on Vertex AI, ADK, Vertex AI Search, Firestore and BigQuery are written
behind lazy imports but have not been run against live services yet. Nothing
is deployed.

## Repository layout

| Path | What it is | State |
| --- | --- | --- |
| [`shared-infra/`](shared-infra) | `spine`: model wrapper (retry, timeout, cost), guardrails, human review queue, RAG with citation checks, session and long-term memory, OpenTelemetry tracing, JSON logs, metrics, eval harness with a CI regression gate | Built |
| [`support-agent/`](support-agent) | `triage`: classify a ticket, answer it from a help-docs knowledge base with citations, propose actions (order lookup, CRM update, refund), and escalate to a human by five explicit rules. FastAPI service and a review CLI | Built |
| [`invoice-agent/`](invoice-agent), [`lead-research-agent/`](lead-research-agent), [`meeting-action-agent/`](meeting-action-agent), [`contract-review-agent/`](contract-review-agent) | Product and design plans | Planned |
| [`landing-page/`](landing-page) | Static product page | Built |
| [`overview.md`](overview.md), [`gcp-update.md`](gcp-update.md) | Product vision and the target Google Cloud architecture | Docs |

## How the Triage agent works

```
ticket -> input guardrails -> classify -> retrieve + answer with citations
       -> propose actions -> output guardrails -> escalation rules
       -> answer, or human review queue
```

A ticket goes to a human when any of these fire: low retrieval confidence, a
citation that doesn't resolve to a real document, a high-risk action (refund
or CRM update), urgent priority, or an angry customer on a high-priority
ticket. Every step emits a trace span, a structured log line and a metric
record.

## Evals in CI

Two GitHub Actions workflows run on every push that touches the code:

- `spine-ci`: ruff, pytest and the reference-agent eval gate.
- `support-agent-ci`: ruff, pytest and eval gates for classification,
  resolution, actions, escalation and the end-to-end pipeline.

Each gate compares the run against a committed baseline and fails the build if
a score drops by more than 0.01. The golden sets are small (under 20 cases
each), and the "LLM judge" in CI is a deterministic fake until real model calls
are wired in.

## Run it

Requires Python 3.11 and [`uv`](https://docs.astral.sh/uv/).

```bash
cd support-agent
uv sync
uv run pytest
uv run python -m triage.demo   # one ticket end to end: spans, logs, guardrails, result, metrics
uv run uvicorn triage.api:app  # POST /tickets, GET /queue, POST /queue/{id}/resolve
uv run python -m triage.review list   # review escalated tickets
```

See [`shared-infra/README.md`](shared-infra/README.md) for the library, the
eval gate and the metrics report.
