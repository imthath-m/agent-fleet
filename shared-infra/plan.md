# Shared Infra ("the spine") — Detailed Plan

The spine is a reusable platform that every product agent builds on. It provides
the runtime, orchestration, evaluation, tracing, logging, observability,
guardrails, memory, and CI/CD — so each vertical only writes domain logic.

## Design principles

- **Reuse over rebuild.** ADK + Agent Engine give us runtime, sessions, and
  native OpenTelemetry spans. We do not reinvent an agent framework.
- **Deterministic where possible, agentic only where needed.** Validation,
  routing rules, and schema checks are plain code. The LLM handles ambiguity.
- **Everything is measured.** No step ships without a trace span, structured log,
  and a way to evaluate its output.
- **One library, many agents.** Cross-cutting concerns live in a shared Python
  package (`spine/`) that every project imports.

## Component architecture

### 1. Agent runtime & orchestration
- **ADK** for agent definition (tools, instructions, sub-agents).
- **A2A protocol** for specialist agent handoffs (e.g. classifier → resolver).
- **Vertex AI Agent Engine** as the managed runtime for stateful, deployed
  agents; **Cloud Run** for stateless HTTP services and tool backends.
- **Pub/Sub + Cloud Tasks** for async / long-running or fan-out workloads.

### 2. Model access
- **Gemini on Vertex AI** as default model. Model IDs and generation params are
  centralized in `spine/models.py` so every agent shares config and we can swap
  or A/B models in one place.
- A thin wrapper adds **retry, timeout, and cost accounting** per call.

### 3. Grounding / RAG
- **Vertex AI Search** (RAG Engine) as the shared retrieval layer. Each product
  owns a datastore; the spine provides ingest + query helpers and citation
  plumbing so answers can be grounded and traced back to sources.

### 4. Memory & state
- **Firestore** for session/conversation state and app data.
- **Vertex Memory Bank** for long-term, cross-session agent memory.
- Shared `spine/memory.py` abstracts read/write so products don't hardcode it.

### 5. Guardrails & human-in-the-loop
- Input guardrails: PII detection, prompt-injection heuristics, allow/deny topics.
- Output guardrails: schema validation, grounding/citation checks, confidence
  gating.
- **HITL escalation**: when confidence < threshold or action is high-risk, the
  agent pauses and routes to a human queue (Firestore + notification). Shared
  `spine/guardrails.py` and `spine/hitl.py`.

### 6. Evaluation (the differentiator)
- **Offline eval suite** per product: versioned golden datasets (input →
  expected) stored in the repo + BigQuery.
- **Vertex AI Evaluation Service** for pointwise/pairwise model-graded metrics.
- **Custom LLM-as-judge** metrics for domain quality (e.g. resolution
  correctness, hallucination rate, citation validity).
- **Deterministic metrics** where possible (field-level accuracy, schema pass
  rate, tool-call correctness).
- **CI gate**: eval runs on every PR; a regression against the baseline **blocks
  the deploy**. Results written to BigQuery for trend tracking.
- **Online eval**: sampled production traffic scored by judges, fed back into the
  golden set.

### 7. Tracing
- **OpenTelemetry** instrumentation; ADK/Agent Engine emit agent, tool, and model
  spans natively. Exported to **Cloud Trace**.
- Every request carries a `trace_id`; every step (retrieval, tool call, model
  call, guardrail) is a span with attributes (tokens, cost, latency, decision).
- Shared `spine/tracing.py` sets up the exporter and custom span helpers.

### 8. Logging
- **Cloud Logging** with **structured JSON** logs, correlated by `trace_id`.
- Standard fields: request id, agent, step, tool, tokens, cost, latency, outcome,
  guardrail decisions. Shared `spine/logging.py` gives a preconfigured logger.

### 9. Observability
- Trace spans + eval results + structured logs land in **BigQuery**.
- **Looker (or Looker Studio)** dashboards for: latency (p50/p95), cost per
  request, quality metrics over time, escalation rate, tool error rate, token
  usage.
- Alerting via **Cloud Monitoring** on SLO breaches (latency, error rate, cost
  spikes, quality regression).

### 10. Security & tenancy
- **Secret Manager** for keys; **IAM** least-privilege per service.
- Per-tenant isolation for data (Firestore/RAG datastore namespacing).
- Audit logging for all high-risk agent actions.

### 11. CI/CD & IaC
- **Terraform** for all GCP resources (reproducible, reviewable infra).
- **Cloud Build / GitHub Actions**: lint → unit tests → **eval gate** → deploy.
- Environments: `dev` → `staging` → `prod`, each its own project or namespace.

## The `spine/` shared library (import surface)

```
spine/
├── models.py       # Gemini config, wrapper, cost accounting
├── agent.py        # ADK base agent + A2A helpers
├── rag.py          # Vertex AI Search ingest/query + citations
├── memory.py       # Firestore + Memory Bank abstraction
├── guardrails.py   # input/output guards
├── hitl.py         # escalation queue
├── eval/           # datasets, judges, runners, CI gate
├── tracing.py      # OTel → Cloud Trace setup
├── logging.py      # structured Cloud Logging
└── obs.py          # BigQuery sinks, metric emitters
```

## Build phases

1. **Runtime skeleton** — ADK agent on Agent Engine + Cloud Run tool backend,
   deployed via Terraform. Verify: a "hello" agent responds in `dev`.
2. **Tracing + logging** — wire OTel → Cloud Trace and structured Cloud Logging.
   Verify: one request produces a full span tree + correlated logs.
3. **Eval harness** — golden dataset format, judges, runner, BigQuery sink, CI
   gate. Verify: a deliberately-bad change fails the gate.
4. **Guardrails + HITL** — input/output guards and escalation queue. Verify: a
   low-confidence case routes to the human queue.
5. **RAG + memory** — Vertex AI Search ingest/query and Memory Bank. Verify:
   grounded answer with working citations; memory persists across sessions.
6. **Observability** — BigQuery + Looker dashboards + Cloud Monitoring alerts.
   Verify: dashboard shows latency, cost, and quality for the reference agent.

## Definition of done

- A new agent can be scaffolded from `spine/`, traced, evaluated, and deployed to
  GCP in **under a day**.
- The reference agent has: full trace tree, structured logs, a green eval gate,
  live dashboards, and Terraform-managed infra.
