# Contract / Compliance Review Agent

The **high-stakes** agent in Fleet's lineup: it uploads a contract, checks each
clause against a customer **playbook**, flags risks, and drafts redlines — but
**every finding must cite the exact source clause and the playbook rule it
violates**, and **every report is reviewed by a human before use**. It uniquely
stresses two platform components harder than any other agent: **citation
grounding** (`spine.rag.resolve_citations` + `CitationGuard`, zero tolerance for
fabricated citations) and **high-stakes evaluation** (the most rigorous eval
gate of the five, with absolute floors, not just regression checks). Framing is
non-negotiable: this is a **paralegal-style assist tool, not legal advice** — a
qualified human reviews everything, nothing auto-sends, and the report says so.

> This project builds **on top of `shared-infra/`**. It does not re-implement
> runtime, eval, tracing, logging, observability, guardrails, memory, RAG, or
> CI/CD — it imports `spine/` and adds only the domain logic below.

## What it does

Ingests a contract (PDF/DOCX/plain text), parses and segments it into clauses,
classifies each clause against the customer's playbook (required / forbidden /
negotiable terms — liability caps, indemnification, auto-renewal, data-processing
/ DPA terms, governing law, termination), flags risks with a severity, drafts
suggested redline language for problem clauses, and produces a reviewer report.
**Each finding carries a citation to the source clause text and to the playbook
rule it maps to.** Findings that can't be grounded are dropped or escalated —
never shown as fact. A human reviews and edits the report; nothing is sent.

## Target buyer

Startups and SMBs that sign routine contracts (NDAs, MSAs, DPAs, vendor
agreements, order forms) but have **no in-house counsel bandwidth** to first-pass
every one. Value prop: cut the reviewer's time-to-first-pass, catch the obvious
playbook violations before they reach a lawyer, and keep a full audit trail —
without pretending to replace the lawyer.

## Agent design

Locally this is **one pipeline**, not a multi-agent mesh: a single
`ContractReviewAgent.run(request)` threads the stages below, each wrapped in a
`spine.tracing.span(...)` (mirroring `ReferenceAgent.run` in
`shared-infra/src/spine/reference_agent.py`). **The spine has no A2A / multi-agent
helpers today** — `spine.agent` is a single base `Agent` — so do **not** design
around agent handoffs. ADK sub-agents, A2A, and Agent Engine are a **GCP
deploy-phase** concern (§Local-first, §References); the local build is plain
Python stages.

**Deterministic where possible.** Playbook rules that have a regex/keyword
precondition (e.g. "auto-renewal" → match `renew`/`evergreen`; "governing law" →
match `governed by the laws of`) run as **plain code** — no model call. The LLM
is used only to (a) classify clauses the deterministic pass left ambiguous and
(b) draft redline language.

```
   upload (PDF / DOCX / text)
             │
     ┌───────▼────────┐
     │ Parser/Segmenter│  parse_document → clauses (id, heading, text, span)
     └───────┬────────┘
             │  one spine.rag.Document per clause (contract namespace)
     ┌───────▼────────┐
     │ Clause classifier│  deterministic regex/keyword first; LLM for ambiguous
     └───────┬────────┘
             │
     ┌───────▼────────┐
     │ Playbook matcher│  RAG: retrieve matching rule from playbook namespace
     │      (RAG)      │  → each clause paired with its governing rule + score
     └───────┬────────┘
             │
     ┌───────▼────────┐
     │  Risk flagger  │  rule + clause → finding{severity, rationale, citations}
     └───────┬────────┘
             │
     ┌───────▼────────┐
     │ Redline drafter │  LLM: suggested alternative language (marked SUGGESTION)
     └───────┬────────┘
             │  output guardrails: CitationGuard, SchemaGuard, ConfidenceGuard
     ┌───────▼────────┐
     │ Human-review    │  100% → HumanQueue; reviewer edits; export_report
     │    report       │
     └────────────────┘
```

- **Parser/Segmenter** — turns an uploaded file into an ordered list of clauses.
  V1 is plain-text/markdown segmentation (split on numbered headings / double
  newlines) behind a `DocParser` interface; the Document AI Layout Parser adapter
  comes later (§Local-first, §References).
- **Clause classifier** — assigns each clause a type. Deterministic
  regex/keyword rules run first; only clauses they don't confidently label go to
  a Gemini structured-output call.
- **Playbook matcher** — for each classified clause, `retriever.query(playbook_ns,
  clause_text, top_k=k)` returns the governing playbook rule(s). The retrieval
  `score` feeds the confidence signal.
- **Risk flagger** — deterministic mapping of (clause, matched rule) → a
  `Finding` with `severity` (`critical` / `high` / `medium` / `low` / `info`) and
  a rationale. Its `citations` are the clause `doc_id` **and** the rule `doc_id`.
- **Redline drafter** — LLM drafts alternative language for problem clauses,
  clearly labelled a **suggestion, not advice**.
- **Human-review report** — `escalate_if_needed` routes **every** report to
  `HumanQueue`; the reviewer edits/approves; `export_report` renders it.

## Tools

Analysis-heavy, action-light. **All read-only except `export_report`; no writes
to external systems in v1.** Register as `spine.agent.Tool` instances.

- `parse_document(uri) -> [Clause]` — parse + segment an uploaded file. Local:
  read a text/markdown fixture. Later: Document AI Layout Parser adapter.
- `playbook_lookup(clause_text) -> [Rule]` — thin wrapper over
  `retriever.query(playbook_ns, ...)`; returns matched rules with scores.
- `export_report(review) -> path` — render the reviewed findings to an annotated
  **PDF/DOCX** report (with the assist-not-advice disclaimer). Local: emit
  Markdown/HTML; PDF/DOCX rendering is a lazy adapter.

## Data & memory

- **Firestore** (`spine.memory.FirestoreSessionStore`, lazy adapter in
  `shared-infra/src/spine/memory.py`; local default `InMemorySessionStore`):
  review state — uploaded contract metadata, clause list, findings, reviewer
  edits, approval status.
- **RAG namespaces** (`spine.rag.Retriever`, `shared-infra/src/spine/rag.py`):
  - **one playbook namespace per tenant** — the customer's rules as
    `spine.rag.Document`s (`doc_id` = rule id, e.g. `rule-liability-cap`).
  - **one namespace per uploaded contract** — each **clause** ingested as a
    `Document` (`doc_id` = clause id, e.g. `clause-7.2`). This is what makes
    `CitationGuard` and `resolve_citations` able to verify a finding cites a
    **real** clause.
- **Per-tenant isolation is mandatory** (contracts are confidential):
  **namespace per tenant** (`{tenant}:playbook`, `{tenant}:contract:{id}`), never
  a shared namespace. In production add **encryption at rest** (CMEK on the
  Firestore/Vertex AI Search datastore) and **access logging** (Cloud Audit Logs)
  on every read of contract data.

## Guardrails & HITL

The **strictest** guard stack of all five products. Compose with
`spine.guardrails.run_guardrails(guards, value, span=...)`
(`shared-infra/src/spine/guardrails.py`).

**Input guards** (contract text is **untrusted** — a contract can embed
adversarial instructions in a clause):
- `PromptInjectionGuard()` — on raw clause text before it reaches the model.
- `PiiGuard(block_on_detect=False)` — detect + redact PII for logs/telemetry;
  keep the clause text for review rather than hard-blocking.

**Output guards** (on each finding's `AgentOutput`):
- **`CitationGuard(required=True, min_citations=2)`** on **every** finding — a
  finding must cite ≥1 clause and ≥1 rule. A finding without a resolvable
  citation is **dropped or escalated, never shown as fact**.
- **Citation validity** — beyond count, call
  `spine.rag.resolve_citations(retriever, namespace, finding.citations)`; a
  non-empty return means a fabricated/stale citation → drop + escalate. (Count is
  what `CitationGuard` checks; validity is what `resolve_citations` checks — see
  the module docstring in `rag.py`.)
- **`SchemaGuard(required_fields=[...])`** — the findings schema (below) must be
  well-formed or the finding is blocked.
- **`ConfidenceGuard(threshold=<HIGH>, on_low=Decision.ESCALATE)`** — a HIGH
  threshold (e.g. 0.8). Low-confidence findings escalate rather than assert.

**Concrete "confidence"** per finding = combination of (a) **classifier
certainty** for the clause type and (b) the **retrieval score** of the matched
playbook rule (`Passage.score` from `retriever.query`). Define it explicitly in
code (e.g. `min(classifier_conf, retrieval_score)`) so the threshold is
meaningful.

**HITL is the product's UX, not an exception path.** **100% of reports** go
through `spine.hitl.HumanQueue` (`shared-infra/src/spine/hitl.py`): each review is
enqueued via `escalate_if_needed(...)` / `queue.enqueue(...)`, a reviewer edits
and approves, `export_report` runs only after approval, and **nothing
auto-sends**. Local store: `InMemoryEscalationStore`; production:
`FirestoreEscalationStore`.

**Findings schema** (the `AgentOutput.data` shape `SchemaGuard` enforces):
`clause_id`, `clause_type`, `rule_id`, `severity`, `rationale`,
`suggested_redline`, `citations` (list of `clause_id` + `rule_id`), `confidence`.

## Evaluation

The showcase section — the most rigorous of the five. Uses
`spine.eval` (`shared-infra/src/spine/eval/`).

**Golden dataset** — `spine.eval.dataset.GoldenDataset` of annotated contracts.
Seed from **CUAD** (Contract Understanding Atticus Dataset — public, clause-level
labels) plus **hand-made synthetic contracts with planted issues** (a known
missing liability cap, an unlimited-indemnity clause, an evergreen auto-renewal).
Store as JSONL at `contract-review-agent/eval/data/contracts.jsonl` (header line +
one `GoldenExample` per line, per `dataset.py`); each example's `expected` holds
the labelled findings (clause_id, clause_type, severity, rule_id).

**Existing spine metrics** (`shared-infra/src/spine/eval/metrics.py`):
- `FieldAccuracy(fields=["clause_type"])` — clause classification accuracy.
- `SchemaPassRate(required_fields=[...])` — findings are well-formed.
- `LlmJudge(client=..., criterion="redline quality")` — redline usefulness /
  safety, scored by a model (a `FakeModelClient` drives it locally).

**New `Metric` implementations** (add in `contract-review-agent/src/.../metrics.py`,
each a class with `name` + `score(example, prediction) -> MetricResult`, matching
the `Metric` Protocol):
- **`FindingPrecisionRecall`** per severity — **a false negative (missing a
  `critical` finding) is weighted far worse than a false positive.** Report
  per-severity precision/recall; make **critical-issue recall** its own scored
  metric so the gate can floor it.
- **`CitationValidityRate`** — fraction of findings whose citations all resolve
  via `spine.rag.resolve_citations`. **Zero-tolerance:** any fabricated citation
  drives this below 1.0 and must fail CI.
- **`PlaybookRuleCoverage`** — fraction of applicable playbook rules the run
  actually checked (did it look at every required term?).

**CI gate** — mirror `.github/workflows/spine-ci.yml`: a `contract-review-ci.yml`
running `ruff` → `pytest` → `uv run python -m spine.eval gate --suite
contract_review.eval:build_suite --baseline baselines/contract_review.json`, with
the baseline committed (like `shared-infra/baselines/reference_agent.json`).

**Honest note on absolute thresholds.** `spine.eval.gate.compare_to_baseline`
(`shared-infra/src/spine/eval/gate.py`) only checks **regression** — it flags a
metric that dropped more than `--threshold` below the committed baseline
`mean_scores`; it has **no native "absolute floor"** concept. Two ways to get the
zero-tolerance / minimum-recall behaviour this product needs:
1. **Reuse the existing gate** — commit a baseline whose `mean_scores` equal the
   floors (`citation_validity_rate: 1.0`, `critical_issue_recall: <target>`) and
   run with `--threshold 0`, so any value below the floor regresses and fails.
   Works today, zero new code — best for `citation_validity_rate` (floor 1.0).
2. **Add a tiny `assert_floors(result, {...})` helper** in the product that exits
   1 if any metric is below its floor, run alongside the regression gate — use
   for the recall floors if you want them decoupled from the baseline file.

## Observability

Every run emits one `spine.obs.MetricRecord` (`shared-infra/src/spine/obs.py`) to
a sink; `metrics_report(...)` summarises it (local stand-in for Looker). Map to
dashboards:
- **findings per contract** (count) and **severity mix** — via `outcome` /
  per-finding rows.
- **citation-validity rate over time** — the zero-tolerance metric trended.
- **human-review edit rate** — fraction of findings the reviewer changed (proxy
  for quality); record as `quality_score`.
- **cost + p50/p95 latency per contract** — `cost_usd`, `latency_ms`
  (`percentile(...)`).
- **token usage on long contracts** — `tokens`; watch for long-context blowups.
Production sink: `BigQueryMetricsSink` (lazy, `bigquery` extra) → Looker.

## Integrations (go-to-market)

- **Ingest** — an upload UI / REST endpoint first (drop a PDF/DOCX). Later:
  **Google Drive folder watch** (review new contracts in a folder) and
  **email-in** (forward a contract to an inbox).
- **Export** — annotated **PDF/DOCX** review report via `export_report`, always
  carrying the assist-not-advice disclaimer.

## Local-first development

Everything below runs with **no GCP creds and no network**, exactly like the
spine (`shared-infra/README.md`).

**Repo layout** (own package, uv path-dependency on the spine):
```
contract-review-agent/
├── plan.md                      # this file
├── pyproject.toml               # deps: spine @ path ../shared-infra (editable)
├── src/contract_review/
│   ├── parser.py                # DocParser interface + FakeDocParser + (later) DocAI adapter
│   ├── segment.py               # text/markdown → clauses
│   ├── classify.py              # deterministic rules + LLM fallback
│   ├── playbook.py              # rule model + matcher over the playbook namespace
│   ├── findings.py              # Finding dataclass + schema + risk flagger
│   ├── redline.py               # LLM redline drafter
│   ├── agent.py                 # ContractReviewAgent.run — the pipeline
│   ├── report.py                # export_report renderer
│   ├── metrics.py               # new Metric impls (precision/recall, citation validity, coverage)
│   └── eval.py                  # build_suite() factory for the gate
├── tests/
├── eval/data/contracts.jsonl    # golden dataset (CUAD seed + synthetic)
├── fixtures/                    # plain-text/markdown fixture contracts + a playbook
└── baselines/contract_review.json
```
`pyproject.toml` mirrors `shared-infra/pyproject.toml` (Python 3.11, `hatchling`,
`ruff`, `pytest`) and adds a path dependency:
`[tool.uv.sources] spine = { path = "../shared-infra", editable = true }`.

**Fakes (local defaults):**
- `spine.models.FakeModelClient(responder=...)` — a custom responder that returns
  canned clause classifications and redlines keyed off the prompt (the pattern in
  `reference_agent.default_responder`).
- `spine.rag.InMemoryRetriever(corpus=...)` — seed **two** namespaces: the
  playbook rules and the contract clauses. `InMemoryRetriever.get(...)` is what
  `resolve_citations` needs, so the whole citation-validity check works locally.
- `spine.memory.InMemorySessionStore` — review state.
- `spine.obs.InMemoryMetricsSink` — metrics.
- `spine.hitl.InMemoryEscalationStore` (via `HumanQueue()`) — the review queue.

**Document parsing — start dependency-free.** V1 reads **plain-text/markdown
fixture contracts** and segments them in `segment.py` (no parser dependency).
Define a `DocParser` interface with a `FakeDocParser` (reads a fixture) and, later,
a **lazy Document AI Layout Parser adapter** following the spine's lazy-adapter
pattern — exactly how `spine.rag.VertexSearchRetriever` and
`spine.models_vertex.VertexModelClient` import their SDKs only on first use, so
the core stays SDK-free. GCP client deps go under an optional extra (like the
spine's `vertex` extra), never a core dependency.

## Build phases

1. **Segment + playbook match over text fixtures (local only).** `segment.py`
   turns a fixture contract into clauses; ingest clauses + a fixture playbook into
   `InMemoryRetriever`; deterministic classifier + `playbook_lookup` pair each
   clause with a rule. **Verify:** a fixture NDA produces the expected clause list
   and each clause maps to the right playbook rule (unit tests, no model).
2. **Eval harness + citation grounding (arrives early — high-stakes).** Build the
   `GoldenDataset` (CUAD seed + synthetic planted-issue contracts), the new
   metrics (`FindingPrecisionRecall`, `CitationValidityRate`,
   `PlaybookRuleCoverage`), `build_suite()`, and the committed baseline; wire
   `resolve_citations` into the flow. **Verify:** `python -m spine.eval gate`
   passes on the good agent; a deliberately fabricated citation drives
   `citation_validity_rate` below 1.0 and **fails** the gate.
3. **Risk flagger + redline drafter + full guardrail stack.** Add severity
   flagging, LLM redline drafting, and the output guards
   (`CitationGuard`/`SchemaGuard`/`ConfidenceGuard`) plus input
   `PromptInjectionGuard`/`PiiGuard`. **Verify:** findings without resolvable
   citations are dropped/escalated; low-confidence findings escalate; an injection
   embedded in a clause is caught.
4. **HITL review + report export.** Route 100% of reports through `HumanQueue`;
   add reviewer edit/approve; `export_report` renders an annotated report with the
   disclaimer. **Verify:** no report is emitted without an approval step; edit rate
   is recorded to the obs sink.
5. **GCP deploy path (later).** Swap fakes for lazy adapters — Document AI Layout
   Parser, `VertexSearchRetriever`, `VertexModelClient`, `FirestoreSessionStore`,
   `BigQueryMetricsSink` — and (if warranted) ADK/Agent Engine packaging. **Verify:**
   the same pipeline runs on GCP with a grounded, cited, human-reviewed report and
   a green gate in CI.

## Definition of done

- A contract flows **upload → segment → classify → match → flag → redline →
  human-review → report**, fully **traced, logged, and observable**, with a
  **green eval gate** in CI.
- **Zero fabricated citations**: `citation_validity_rate` is floored at **1.0** in
  the gate; every finding resolves to a real clause and a real rule.
- **Critical-issue recall** meets its committed floor; false negatives on
  `critical` findings fail CI.
- **100% of reports** pass through human review; nothing auto-sends; every report
  states it is a paralegal-style **assist, not legal advice**.
- Reuses the spine with **zero** duplicated cross-cutting infrastructure.

## References

Spine source (the trickiest wiring):
- Citation count guard — `CitationGuard` in
  `shared-infra/src/spine/guardrails.py`.
- Citation **validity** — `resolve_citations` + `passages_to_citations` in
  `shared-infra/src/spine/rag.py` (only backends exposing `.get(...)` support it;
  `InMemoryRetriever` does).
- CI gate semantics (regression-only; how to encode floors) —
  `compare_to_baseline` / `run_gate` in `shared-infra/src/spine/eval/gate.py`.
- Metric Protocol + examples — `shared-infra/src/spine/eval/metrics.py`;
  dataset format — `shared-infra/src/spine/eval/dataset.py`.
- End-to-end pipeline pattern — `ReferenceAgent.run` in
  `shared-infra/src/spine/reference_agent.py`.

Official docs:
- Document AI Layout Parser (parse + chunk):
  https://cloud.google.com/document-ai/docs/layout-parse-chunk
- Vertex AI Search / RAG Engine: https://cloud.google.com/vertex-ai-search-and-conversation
- Gemini structured output:
  https://ai.google.dev/gemini-api/docs/structured-output
- Gemini long context:
  https://ai.google.dev/gemini-api/docs/long-context
- CUAD dataset: https://www.atticusprojectai.org/cuad
  (GitHub: https://github.com/TheAtticusProject/cuad)
- ADK (Agent Development Kit): https://google.github.io/adk-docs/
- Vertex AI Agent Engine:
  https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview
- Vertex AI Evaluation:
  https://cloud.google.com/vertex-ai/generative-ai/docs/models/evaluation-overview
