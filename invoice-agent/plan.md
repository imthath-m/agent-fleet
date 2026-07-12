# Project Two — AP / Invoice-Processing Agent

Second product. Chosen to **prove the spine is reusable**: it should reach a
working, traced, evaluated local build by importing `spine/` and writing only
domain logic — extraction, deterministic validation, and agentic exception
handling. Document AI does the reading; plain Python does the checking; the LLM
is used **only** for the ambiguous exceptions. High willingness to pay because
AP is a headcount line item.

> This project builds **on top of `shared-infra/`**. It does not re-implement
> runtime, eval, tracing, logging, observability, guardrails, memory, HITL, or
> CI/CD — it imports `spine/` (a `uv` path dependency on `../shared-infra`) and
> adds only the domain logic below. Every spine class named here is a real
> export of `shared-infra/src/spine/__init__.py`; check it before adding a
> dependency on something that isn't there (there is **no A2A helper** today —
> see Agent design).

## What it does

Ingests an invoice (PDF or email attachment) → extracts fields with **Document
AI Invoice Parser** → runs **deterministic validation** (schema, totals
arithmetic, PO match, duplicate detection, vendor lookup) → invokes the **LLM
only for exceptions** (mismatches, missing PO, unusual amounts) → routes for
**approval with HITL** when above threshold or low-confidence → **exports** the
approved invoice to the accounting system (QuickBooks/Xero — mock adapter
first).

## Target buyer

Any SMB or early startup with a growing pile of vendor invoices and no AP clerk:
bookkeepers, ops leads, fractional CFOs. Value prop: **straight-through
processing** for clean invoices, humans only for exceptions, and a full audit
trail per invoice.

## Agent design

```
        invoice (PDF / email attachment)
                     │
              ┌──────▼───────┐
              │  1. Ingest   │  normalize source → InvoiceJob{doc_bytes, source}
              └──────┬───────┘
              ┌──────▼───────┐
              │ 2. Extract   │  Document AI Invoice Parser → fields + confidences
              └──────┬───────┘   (FakeDocParser locally; DocumentAiParser on GCP)
              ┌──────▼───────┐
              │ 3. Validate  │  DETERMINISTIC, plain code:
              │  (no LLM)    │  schema · totals arithmetic · PO match ·
              └──────┬───────┘  duplicate detection · vendor lookup
                     │  clean?  ──────────────► (skip step 4)
              ┌──────▼───────┐
              │ 4. Exception │  AGENTIC, LLM only: explain/resolve the flagged
              │   handler    │  cases, propose a corrected field or a reason
              └──────┬───────┘
              ┌──────▼───────┐
              │ 5. Approval  │  confidence + amount threshold → PASS or ESCALATE
              │   + HITL     │  → spine HumanQueue when unsure / above-threshold
              └──────┬───────┘
              ┌──────▼───────┐
              │  6. Export   │  post approved invoice to accounting (mock first)
              └──────────────┘
```

**Be honest about what runs locally.** Locally this is **one pipeline** — a
single `InvoiceAgent.run(job)` that walks the six steps in order, opening one
tracing span per step, exactly like `spine.reference_agent.ReferenceAgent.run`
in `shared-infra/src/spine/reference_agent.py` (see its `with span(...)` blocks
and `record_metrics` calls). There are **no separate agents and no A2A
handoffs**: `spine.agent.Agent`/`Tool` (`shared-infra/src/spine/agent.py`) is a
plain prompt-composer with **no function-calling loop**, and the spine ships
**no A2A module** at all. Do not design around A2A. The multi-agent split (ADK
sub-agents, A2A, Agent Engine managed runtime) is a **GCP-deploy-phase** concern
only (Phase 5); the local build is deliberately a linear, fully-traced pipeline.

Per stage:

- **1. Ingest** — normalize the input (uploaded PDF, email attachment) into an
  `InvoiceJob` (raw bytes + source). Local: read a fixture file. GCP: Pub/Sub
  push from a GCS-landing bucket or email inbound.
- **2. Extract** — call a `DocParser` (domain interface, see Local-first)
  returning a `ParsedInvoice` with **per-field confidence scores**. Local:
  `FakeDocParser`. GCP: `DocumentAiParser`.
- **3. Validate** — **plain Python, no model call.** Runs the deterministic
  checks below and emits `ValidationIssue`s. Where "deterministic where
  possible" lives.
- **4. Exception handler** — **only runs if step 3 produced issues.** Prompts
  Gemini (wrapped model client) with the flagged fields + AP-policy passages
  (RAG) to explain or propose a correction. Feeds the confidence score.
- **5. Approval + HITL** — deterministic routing: compute one `confidence`
  float, run output guardrails, escalate to `spine.hitl.HumanQueue` when
  ConfidenceGuard escalates or the amount exceeds the auto-approve threshold.
- **6. Export** — post the approved invoice to accounting via an idempotent tool
  (mock adapter first).

## Tools

Tools are plain `spine.agent.Tool(name, description, fn)` instances
(`shared-infra/src/spine/agent.py`). Each `fn` validates inputs, is wrapped in a
`spine.tracing.span(step=StepType.TOOL_CALL)`, and returns a structured result.
**Mock adapters first** (in-process Python); a **Cloud Run** backend per tool
comes at the deploy phase.

| Tool | Inputs → Outputs | Risk | Idempotency |
| --- | --- | --- | --- |
| `parse_invoice` | `doc_bytes` → `ParsedInvoice` (fields + confidences) | low (read) | Yes — pure function of the bytes |
| `lookup_vendor` | `vendor_name`/`tax_id` → `Vendor` record or `None` | low (read) | Yes |
| `match_po` | `po_number`, line items → `POMatch{matched, deltas}` | low (read) | Yes |
| `check_duplicate` | invoice fingerprint (vendor+number+amount) → `bool` + prior id | low (read) | Yes — keyed lookup |
| `post_to_ledger` | approved `Invoice` → `{ledger_id}` | **high (write)** | Yes — dedupe on `(vendor, invoice_number)` idempotency key; re-post returns the existing `ledger_id` |

`post_to_ledger` is the only high-risk tool: it never runs on an un-approved or
duplicate invoice, and it carries an idempotency key so a retried Pub/Sub
delivery cannot double-book. Every tool emits a trace span + structured log via
the spine; a raised tool error increments `MetricRecord.tool_errors`.

## Data & memory

- **Invoice state** — persisted through `spine.memory.SessionStore`
  (`shared-infra/src/spine/memory.py`). Local: `InMemorySessionStore`. GCP:
  `FirestoreSessionStore`. Key by `invoice_id`; append each step's outcome to
  the session so the audit trail is reconstructable. The **duplicate-detection
  index** (seen `(vendor, invoice_number, amount)` fingerprints) also lives in
  Firestore in production; locally it's an in-memory set seeded from prior
  session state.
- **RAG namespace** — ingest **vendor contracts and the AP policy doc** (payment
  terms, tolerance thresholds, approval matrix) into `spine.rag` under namespace
  `"ap-policy"` via `Retriever.ingest` (`shared-infra/src/spine/rag.py`; local
  `InMemoryRetriever`, GCP `VertexSearchRetriever`). Step 4 calls
  `retriever.query("ap-policy", <issue>, top_k=3)`, converts hits with
  `passages_to_citations`, and puts them in `AgentOutput.citations` so
  `CitationGuard` can require grounding. Clean invoices skip RAG entirely.
- **Cross-session memory** — optional: `spine.memory.MemoryStore`
  (`InMemoryMemoryStore` / `MemoryBankStore`) keyed by `(vendor_id, agent_id)`
  to remember per-vendor quirks (e.g. "always omits the PO").

## Guardrails & HITL

All from `spine.guardrails` and `spine.hitl` (real exports —
`shared-infra/src/spine/guardrails.py`, `hitl.py`). Compose them with
`run_guardrails(guards, value, span=...)`, which aggregates to the worst
`Decision` (`PASS` < `ESCALATE` < `BLOCK`).

- **Input** (`PiiGuard`) — invoices carry bank/routing/tax numbers.
  `PiiGuard(block_on_detect=False)` redacts them (it always computes
  `redacted_text`) so PII doesn't reach the model or logs, without hard-blocking
  the invoice. `PromptInjectionGuard` on any free-text (email body, memo line),
  since attachment text is untrusted.
- **Output** — `SchemaGuard(required_fields=[...])` asserts the extracted
  invoice has every required field (`vendor`, `invoice_number`, `invoice_date`,
  `total`, `line_items`). `CitationGuard(required=True, min_citations=1)` on the
  **exception path** so an LLM resolution must cite the AP policy it relied on.
  `ConfidenceGuard(threshold=...)` gates delivery.
- **HITL** — `escalate_if_needed(report, queue, payload=...)` routes an
  `ESCALATE` decision into `HumanQueue` (local `InMemoryEscalationStore`, GCP
  `FirestoreEscalationStore`). The reviewer payload carries the parsed invoice,
  the validation issues, and the LLM's proposed resolution.

**Define "confidence" concretely.** `ConfidenceGuard` only thresholds a single
`AgentOutput.confidence` float, so the agent must compute one. Use:

```
confidence = min(
    min(field_confidence for field in required_fields),   # Document AI scores
    validation_pass_rate,                                  # checks passed / total
)
```

i.e. the invoice is only as trustworthy as its **weakest extracted field** and
its **validation pass rate** together. A clean invoice with high Document AI
confidences scores near 1.0 and auto-processes; a missing-PO or arithmetic
mismatch drops `validation_pass_rate` and escalates. Separately, **any invoice
whose `total` exceeds the auto-approve amount always escalates** regardless of
confidence — a deterministic amount check ORed into the escalate decision, not
confidence alone.

## Evaluation

Uses `spine.eval` (`shared-infra/src/spine/eval/`).

- **Golden dataset** — sample invoices as a JSONL golden set at
  `invoice-agent/eval/data/invoices.jsonl`, in the
  `spine.eval.dataset.GoldenDataset` format: a header line
  (`{"schema_version": 1, "name": "invoices", "dataset_version": "1"}`) then one
  `GoldenExample` per line — `input` is the fixture id / raw text, `expected`
  holds the ground-truth extracted fields, a `duplicate` bool, the expected
  `tool_calls`, and (for exception cases) an `answer`. Load with
  `spine.eval.dataset.load_dataset(path)`; the predictor runs `InvoiceAgent` per
  example and returns a `spine.eval.metrics.Prediction`.
- **Existing spine metrics that apply** (`shared-infra/src/spine/eval/metrics.py`):
  - `FieldAccuracy(fields=["vendor","invoice_number","invoice_date","total"])` —
    extraction accuracy vs. ground truth.
  - `SchemaPassRate(required_fields=[...])` — every required field present.
  - `ToolCallCorrectness()` — the exception handler called the right tools
    (e.g. `match_po`, `lookup_vendor`) with the right multiset.
  - `LlmJudge(client=..., criterion="exception-resolution quality")` — grades
    the LLM's explanation/correction on exception examples.
- **New `Metric`s the intern must write** — implement the
  `spine.eval.metrics.Metric` protocol (a `name` attribute + a
  `score(example, prediction) -> MetricResult`, score in `[0,1]`):
  - `StraightThroughProcessingRate` — fraction of invoices that reached export
    with **no** escalation (measures automation, the core value prop).
  - `DuplicateDetectionPrecision` / `DuplicateDetectionRecall` — vs. the
    `expected["duplicate"]` label; both matter (a false positive blocks a real
    invoice, a false negative double-pays).
- **CI gate** — commit a baseline at `invoice-agent/baselines/invoice_agent.json`
  (same shape as `shared-infra/baselines/reference_agent.json`: `dataset_name`,
  `dataset_version`, `mean_scores`). Expose the suite via a
  `build_invoice_suite()` factory returning a `spine.eval.EvalSuite`, and gate
  in CI with `python -m spine.eval gate --suite
  invoice_agent.eval:build_invoice_suite --baseline
  baselines/invoice_agent.json`. Add a workflow `.github/workflows/invoice-ci.yml`
  mirroring `.github/workflows/spine-ci.yml` (uv sync → ruff → pytest → eval
  gate), scoped to `invoice-agent/**`. A regression past the default 0.01
  threshold fails the build (`spine.eval.gate.compare_to_baseline`).

## Observability

Emit one `spine.obs.MetricRecord` per invoice
(`shared-infra/src/spine/obs.py`) to a `MetricsSink` (local
`InMemoryMetricsSink` / `JsonlMetricsSink`, GCP `BigQueryMetricsSink`).
`spine.obs.metrics_report` is the local stand-in for the Looker dashboard.

| Dashboard metric | Source field(s) on `MetricRecord` |
| --- | --- |
| STP rate | `1 − escalation_rate` (from `escalated`), plus `outcome` = exported |
| Exception rate | `escalation_rate` (share with `escalated=True`) |
| Cost per invoice | `cost_per_request` (from `cost_usd`) |
| p50 / p95 latency | `latency_p50_ms` / `latency_p95_ms` (from `latency_ms`) |
| Tool error rate | `tool_error_rate` (from `tool_errors`) |
| Extraction quality | `mean_quality` (from `quality_score` = eval score) |
| HITL queue depth | **not on `MetricRecord`** — read `HumanQueue.pending()` length separately; surface it as its own gauge |

Note the queue-depth gap honestly: `MetricRecord` has no queue field, so depth
comes from the escalation store, not the metrics sink.

## Integrations (go-to-market)

- **Ingest channels** — upload endpoint (REST), email inbound (attachment →
  bytes), and a GCS-landing bucket that fires Pub/Sub on new objects.
- **Accounting adapters** — a `LedgerAdapter` interface with a `MockLedger`
  first (in-memory, returns a fake `ledger_id`), then **QuickBooks Online** and
  **Xero** adapters per demand. Same lazy-import adapter pattern as the spine's
  GCP backends: the SDK is imported inside the method, never at module top.

## Local-first development

Mirror the spine: **SDK-free core, everything testable with no GCP creds or
network.** Repo layout:

```
invoice-agent/
├── plan.md                     # this file
├── pyproject.toml              # own package; uv path dep on ../shared-infra
├── src/invoice_agent/
│   ├── __init__.py
│   ├── agent.py                # InvoiceAgent.run(job): the 6-step pipeline
│   ├── parser.py               # DocParser interface + FakeDocParser + DocumentAiParser
│   ├── validation.py           # deterministic checks (no LLM)
│   ├── tools.py                # spine.agent.Tool wrappers (mock adapters)
│   ├── ledger.py               # LedgerAdapter + MockLedger (+ QBO/Xero later)
│   ├── metrics.py              # StraightThroughProcessingRate, DuplicateDetection*
│   └── eval.py                 # build_invoice_suite() factory
├── tests/
├── eval/data/invoices.jsonl    # golden dataset
└── baselines/invoice_agent.json
```

`pyproject.toml` mirrors `shared-infra/pyproject.toml` (Python 3.11, hatchling,
ruff, pytest) and adds a `uv` path dependency:

```toml
[project]
name = "invoice-agent"
requires-python = "==3.11.*"
dependencies = ["spine"]

[tool.uv.sources]
spine = { path = "../shared-infra", editable = true }
```

**Fakes to develop against** (all real spine exports):

- `spine.models.FakeModelClient(responder=...)` — a custom responder that reads
  the exception prompt and returns canned resolution JSON, so the exception
  handler is deterministic in tests (see `default_responder` in
  `reference_agent.py` for the prompt-parsing pattern). Wrap it in
  `WrappedModelClient` for retry + cost accounting.
- `spine.rag.InMemoryRetriever` — seed the `"ap-policy"` namespace with a few
  `Document`s of AP policy text.
- `spine.memory.InMemorySessionStore` — invoice state / audit trail.
- `spine.obs.InMemoryMetricsSink` — per-invoice metrics.
- `spine.hitl.InMemoryEscalationStore` (via `HumanQueue`) — the review queue.

**Document AI has no local emulator.** Follow the spine's lazy-adapter pattern
(exactly how `spine.rag.VertexSearchRetriever` and
`spine.models_vertex.VertexModelClient` import their SDK **inside** a method, not
at module top). Define in `parser.py`:

- `DocParser` — an ABC with `parse(doc_bytes) -> ParsedInvoice`.
- `FakeDocParser` — the local default; loads a fixture JSON of a pre-parsed
  invoice (fields + confidence scores) keyed by fixture id. Tests and the eval
  suite run entirely on this — no network.
- `DocumentAiParser` — production adapter; `from google.cloud import documentai`
  **lazily on first use**, calls the Invoice Parser processor, maps its entities
  + confidences into `ParsedInvoice`. Never imported in tests.

This keeps `uv run pytest` and the eval gate fully offline, identical to the
spine's test story.

## Build phases

1. **Extract + validate, local only** — `FakeDocParser` fixtures →
   `ParsedInvoice` → deterministic `validation.py`. No LLM, no GCP.
   **Verify:** `uv run pytest` passes; a fixture with a totals mismatch produces
   a `ValidationIssue`; a clean fixture produces none.
2. **Pipeline + eval gate** — wire the 6-step `InvoiceAgent.run` with a span per
   step (mirroring `ReferenceAgent`), the golden dataset, `FieldAccuracy` +
   `SchemaPassRate` + the new `StraightThroughProcessingRate`, and a committed
   baseline. **Verify:** `python -m spine.eval gate --suite
   invoice_agent.eval:build_invoice_suite --baseline baselines/invoice_agent.json`
   exits 0; deliberately corrupting a fixture's expected `total` fails the gate.
3. **Exception handler + guardrails + HITL** — `FakeModelClient` responder for
   the LLM, RAG grounding over `"ap-policy"`, `run_guardrails` with
   `ConfidenceGuard`, and `escalate_if_needed`. **Verify:** a missing-PO invoice
   escalates to `HumanQueue.pending()`; a clean invoice does not; add
   `LlmJudge` + `DuplicateDetection*` metrics to the suite.
4. **Export + observability** — `MockLedger` behind `LedgerAdapter` (idempotent
   `post_to_ledger`), `MetricRecord` per invoice to a sink,
   `spine.obs.metrics_report`. **Verify:** running the sample set prints STP
   rate, exception rate, cost/invoice, and p50/p95 latency; re-posting the same
   invoice returns the same `ledger_id` (no double-book).
5. **GCP deploy** — swap fakes for adapters (`DocumentAiParser`,
   `VertexSearchRetriever`, `FirestoreSessionStore`, `MemoryBankStore`,
   `BigQueryMetricsSink`), package the pipeline for Agent Engine / Cloud Run,
   ingest via Pub/Sub, wire Cloud Trace + Cloud Logging + Looker. **Verify:** a
   real PDF flows ingest → export end-to-end in `dev`, fully traced and on the
   dashboard.

## Definition of done

- An invoice flows ingest → extract → validate → (exception) → approve/escalate
  → export, **fully traced, logged, and observable**, with a **green eval gate**
  in CI (`invoice-ci.yml`).
- Deterministic validation carries the clean cases; the LLM is invoked **only**
  on flagged exceptions.
- Local build runs with **zero GCP creds** on spine fakes; GCP adapters are
  lazy and swap in without touching domain logic.
- Reuses the spine with **zero** duplicated cross-cutting infrastructure — the
  proof that the platform is reusable.

## References

Official Google Cloud docs:

- Document AI processor list — https://cloud.google.com/document-ai/docs/processors-list
- Document AI Invoice Parser — https://cloud.google.com/document-ai/docs/processors-list#processor_invoice-processor
- Handling the processor response / confidence scores — https://cloud.google.com/document-ai/docs/handle-response
- Firestore (native mode) — https://cloud.google.com/firestore/docs
- Pub/Sub — https://cloud.google.com/pubsub/docs
- Vertex AI Gemini API — https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini
- Agent Development Kit (ADK) — https://google.github.io/adk-docs/
- A2A protocol — https://a2a-protocol.org (spec: https://github.com/google-a2a/A2A)
- Vertex AI Agent Engine — https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview
- Vertex AI Evaluation Service — https://cloud.google.com/vertex-ai/generative-ai/docs/models/evaluation-overview

Spine source (the trickiest wiring — read before implementing):

- Eval gate & baseline — `shared-infra/src/spine/eval/gate.py` (`run_gate`,
  `compare_to_baseline`), runner/suite in `shared-infra/src/spine/eval/runner.py`.
- Guardrails composition — `shared-infra/src/spine/guardrails.py`
  (`run_guardrails`, `ConfidenceGuard`, `Decision`) and HITL routing in
  `shared-infra/src/spine/hitl.py` (`escalate_if_needed`, `HumanQueue`).
- Tracing (span per step) — `shared-infra/src/spine/tracing.py` (`request_span`,
  `span`, `record_metrics`, `StepType`); the end-to-end wiring to copy is
  `shared-infra/src/spine/reference_agent.py` (`ReferenceAgent.run`).
- Lazy-adapter pattern to mirror for `DocumentAiParser` —
  `spine.rag.VertexSearchRetriever` and the GCP sinks/stores in `obs.py`,
  `memory.py`, `hitl.py`.
