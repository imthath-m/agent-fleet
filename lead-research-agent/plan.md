# Project Three — Lead Research & Outreach Agent

Third product. Chosen because it turns the spine's grounding + guardrail stack
toward an outbound use case: take a raw lead, **research it on the open web**,
**score it against the customer's ICP**, and **draft cited, personalized
outreach** a human approves before anything is sent. It is the first vertical
where the primary input (fetched web pages) is **untrusted**, so prompt-injection
defense and citation validity are load-bearing, not nice-to-have.

> This project builds **on top of `shared-infra/`**. It does not re-implement
> runtime, eval, tracing, logging, observability, guardrails, memory, RAG, or
> CI/CD — it imports `spine/` and adds only the domain logic below. Where the
> spine has no primitive (web search / page fetch), the vertical defines a small
> interface with a local fake and a lazy GCP adapter, following the spine's own
> lazy-adapter pattern.

## What it does

Ingests a lead (name / company / domain, from a CSV row or a CRM webhook),
**enriches** it via web-grounded research (Grounding with Google Search on Vertex
AI + a direct fetch of the company's own site + public signals), **scores** the
enriched profile against the customer's ICP rubric with **deterministic rules
over extracted structured fields** (the LLM only extracts and summarizes
evidence — it never assigns the score), **drafts** an email and a LinkedIn
message grounded in cited evidence, routes **every** draft to a human review
queue, and on approval writes the result back to the CRM.

**v1 never auto-sends.** HITL approval is mandatory for all outbound drafts.

## Target buyer

Early-stage B2B startups and SMB sales teams doing founder-led or 1–2 rep
outbound, who spend hours per lead on manual research and generic templates.
Value prop: minutes of research per lead, personalized to real evidence, with an
auditable citation trail and a human in the loop on every send.

## Agent design

```
   CSV row / CRM webhook  (name, company, domain)
             │
      ┌──────▼───────┐
      │   Enricher   │  web_search + fetch_page → LLM extracts structured
      │              │  fields (industry, size, tech, signals) w/ evidence passages
      └──────┬───────┘
      ┌──────▼───────┐
      │    Scorer    │  DETERMINISTIC rules over extracted fields vs ICP rubric
      │              │  → numeric score + tier (A/B/C); LLM does NOT score
      └──────┬───────┘
      ┌──────▼───────┐
      │   Drafter    │  RAG over customer collateral → email + LinkedIn draft,
      │              │  every claim cites an evidence passage
      └──────┬───────┘
             │ output guardrails: schema, citations, confidence(=evidence coverage)
      ┌──────▼───────┐
      │ HITL review  │  ALWAYS: human approves/edits every draft before send
      │    queue     │  → on approve: crm_write
      └──────────────┘
```

**Honest note on runtime.** Locally these four stages are **steps in one
pipeline**, exactly like `spine.reference_agent.ReferenceAgent.run` in
`shared-infra/src/spine/reference_agent.py`: one `request_span(...)` per request
and a `span("enrich" | "score" | "draft", step=StepType.*)` per stage (see
`spine.tracing.span` / `request_span` / `StepType` in
`shared-infra/src/spine/tracing.py`). **There is no multi-agent framework and no
A2A in the spine today** — `spine.agent.Agent.run` is a single-turn prompt→text
call with no function-calling loop, and there are **no A2A helpers**. Do not
design around ADK sub-agents or A2A handoffs. ADK, A2A, and Agent Engine enter
only at the GCP deploy phase (Phase 5), where each stage *may* become a deployed
ADK agent; the local pipeline stays the source of truth and the thing evals run.

### Stages

- **Enricher** — calls `web_search` and `fetch_page` tools, feeds retrieved page
  text to a `ModelClient` that returns **structured JSON** (industry, employee
  band, tech stack, funding/hiring/expansion signals), each field tagged with the
  `doc_id` of the evidence passage it came from. LLM = extraction + summarization
  only.
- **Scorer** — plain Python. Applies the customer's ICP rubric (weighted rules
  over the extracted fields, e.g. `industry in target_set → +30`,
  `50 ≤ employees ≤ 500 → +20`) to produce a score, a tier, and a per-field
  "has cited evidence?" map. Deterministic and unit-testable; no model call.
- **Drafter** — retrieves the customer's own collateral (case studies,
  one-pagers) via `spine.rag`, then prompts the model to write outreach where
  **every factual claim cites an evidence `doc_id`** (lead evidence or
  collateral). Emits `AgentOutput(data=..., text=..., confidence=..., citations=...)`.
- **HITL review queue** — every draft is enqueued via `spine.hitl.HumanQueue`;
  the agent returns "draft pending review", never a sent message.

## Tools

Each tool is a plain `spine.agent.Tool(name, description, fn)` (from
`shared-infra/src/spine/agent.py`) wrapping a function. **Mock adapters first**
(pure Python over fixtures); Cloud Run / real backends later. Note `Tool` is just
a named callable — there is no automatic tool-calling loop, so the pipeline
invokes tools explicitly via `agent.call_tool(name, ...)`.

| Tool | Inputs → Outputs | Risk | Idempotent? |
| --- | --- | --- | --- |
| `web_search` | query → list of `{title, url, snippet}` | Low (read) | Yes (pure read) |
| `fetch_page` | url → `{url, status, text}` (respects robots.txt) | Low–Med (untrusted output) | Yes (pure read) |
| `crm_read` | lead_id → lead record dict | Low (read) | Yes |
| `crm_write` | lead_id, enrichment+score+draft → ack | Med (external write) | **Yes** — idempotency key = `(lead_id, run_id)`; upsert, never append |
| `send_email` | **v2 only** — draft → send | **High** | Must be idempotent; **always HITL-gated**, never called in v1 |

- `fetch_page` output is untrusted: it flows through `PromptInjectionGuard`
  before ever reaching a model prompt (see Guardrails).
- Every tool validates inputs, emits a `span(step=StepType.TOOL_CALL)`, and a
  structured log via `spine.logging.log_event`. Tool failures increment
  `MetricRecord.tool_errors`.

## Data & memory

- **Firestore** (via `spine.memory.FirestoreSessionStore`, lazy adapter): per-lead
  state + the research **dossier** (extracted fields, evidence passages, score,
  drafts, review status). Local default: `InMemorySessionStore`.
- **Per-account knowledge** (`spine.memory.MemoryStore`): facts that persist
  **across leads at the same company** — key the store by
  `(company_domain, agent_id)` so a second contact at an already-researched
  company reuses the earlier dossier instead of re-fetching. `MemoryStore` is
  keyed by `(user_id, agent_id)` and is *not* session-scoped — pass the company
  domain as `user_id`. Local default: `InMemoryMemoryStore`; GCP: `MemoryBankStore`.
- **RAG namespace for customer collateral** (`spine.rag`): the customer's case
  studies / one-pagers are ingested into a per-customer namespace and queried by
  the Drafter to personalize copy. Local default: `InMemoryRetriever`; GCP:
  `VertexSearchRetriever` (see `shared-infra/src/spine/rag.py`). The lead's own
  fetched pages are *also* held as `spine.rag.Document`s (in a per-run namespace)
  so their `doc_id`s are valid citations resolvable by `resolve_citations`.

## Guardrails & HITL

Map to real guards in `shared-infra/src/spine/guardrails.py`:

- **Input** (`run_guardrails(input_guards, text)`):
  - `PiiGuard` — redact/flag PII in the lead record and in fetched text.
  - `PromptInjectionGuard` — **CRITICAL.** Fetched web pages are attacker-
    controllable input ("ignore previous instructions…"). Run every `fetch_page`
    result through this guard *before* it enters any model prompt; a `BLOCK`
    drops that page from the evidence set (do not fail the whole lead).
- **Output** (`run_guardrails(output_guards, AgentOutput(...))`):
  - `SchemaGuard(required_fields=[...])` — dossier + draft have the required
    structured fields.
  - `CitationGuard(required=True, min_citations=1)` — a draft with zero citations
    is blocked. (Note: `CitationGuard` checks citation **count** only; **validity**
    is checked separately with `resolve_citations` — see Evaluation.)
  - `ConfidenceGuard(threshold=…)` — gates on **evidence coverage** (below).
- **HITL** (`spine.hitl`): outreach is high-risk by definition, so **every draft
  routes to `HumanQueue`** regardless of confidence — call
  `queue.enqueue(reason="outreach draft review", payload={draft, dossier, citations})`
  directly (do not rely on `escalate_if_needed`, which only routes `ESCALATE`
  decisions; a passing draft still needs review). Low-confidence or
  injection-flagged leads additionally carry that reason into the queue payload.

**Confidence for this agent = evidence coverage**: the fraction of ICP-rubric
fields that have at least one *valid* cited evidence passage. A lead scored on 3
of 5 rubric fields → confidence `0.6`. This is what `ConfidenceGuard` gates and
what lands in `MetricRecord.quality_score`.

## Evaluation (uses `spine.eval`)

**Golden dataset.** JSONL at `lead-research-agent/eval/data/leads.jsonl`, loaded
with `spine.eval.dataset.load_dataset` into a `GoldenDataset` of `GoldenExample`s
(`shared-infra/src/spine/eval/dataset.py`). Each example's `input` is a lead;
`expected` holds hand-labeled fields, ICP score, tier, and expected `tool_calls`.
Evals are **deterministic and offline**: every company's web pages are **frozen
fixtures** (`eval/fixtures/<domain>/*.html`, `search/*.json`) served by the fake
`SearchClient`/`PageFetcher` — no live network, no model.

**Existing spine metrics that apply** (`spine.eval.metrics`):
- `FieldAccuracy(fields=["industry","employee_band","tier", ...])` — enrichment +
  tier correctness vs labels.
- `SchemaPassRate(required_fields=[...])` — dossier/draft shape.
- `ToolCallCorrectness()` — right tools in the right (multi)set per lead.
- `LlmJudge(client=..., criterion="outreach personalization vs rubric")` — draft
  quality, driven by `FakeModelClient` returning canned JSON scores in CI.

**New `Metric` implementations the intern writes** (implement the
`spine.eval.metrics.Metric` protocol — a `name` attribute + `score(example,
prediction) -> MetricResult`):
- `ScoringAccuracy` — predicted ICP score/tier vs the hand-labeled score
  (exact-tier match, or `1 - |Δscore|/max` for the numeric score).
- `CitationValidityRate` — of the citations in the draft, the fraction that
  resolve to a real evidence doc via
  `spine.rag.resolve_citations(retriever, namespace, citations)` (returns the
  **unresolvable** subset; validity = `1 - len(bad)/len(citations)`).
- `HallucinatedFactRate` — fraction of extracted dossier fields **not** backed by
  any cited evidence passage (uses the Scorer's per-field evidence map).

**Suite + CI gate.** Expose `build_suite() -> EvalSuite` in
`lead_research/eval.py` (an `EvalSuite` = dataset + predictor + metrics; the
predictor runs the pipeline over each lead — cf. `build_reference_suite`). CI
runs its **own** workflow, mirroring `.github/workflows/spine-ci.yml`:
`lint → pytest → python -m spine.eval gate --suite lead_research.eval:build_suite
--baseline baselines/lead_research.json`. A regression past the gate threshold
(`spine.eval.gate`, default `0.01`) exits non-zero and blocks merge. Capture the
committed baseline once from a known-good run with
`spine.eval.gate.save_baseline`.

## Observability (uses `spine.obs`)

Emit one `spine.obs.MetricRecord` per lead (fields in
`shared-infra/src/spine/obs.py`) and summarize with `metrics_report`:

| Dashboard metric | `MetricRecord` source |
| --- | --- |
| **Cost per lead** (web research is token-heavy — the #1 cost lever) | `cost_usd` → `cost_per_request` |
| p50 / p95 latency | `latency_ms` |
| Draft approval / edit rate (quality proxy) | `outcome` (`approved`/`edited`/`rejected`), fed back from the review queue |
| Escalation rate | `escalated` |
| Tool error rate (`fetch_page`/`web_search` failures) | `tool_errors` |
| Evidence coverage (quality) | `quality_score` → `mean_quality` |

Local: `InMemoryMetricsSink` / `JsonlMetricsSink` + `python -m spine.obs
metrics.jsonl`. GCP: `BigQueryMetricsSink` → Looker.

## Integrations (go-to-market)

- **CSV upload** — batch a list of leads; one pipeline run per row.
- **CRM: HubSpot first** — `crm_read`/`crm_write` behind a `CrmAdapter`
  interface; mock adapter over fixtures locally, HubSpot REST adapter later. Add
  Salesforce/Pipedrive per demand.
- **Email** — v1: the agent **drafts only**; the human sends via the customer's
  own tool (Gmail/Outreach/etc.). No `send_email` tool ships in v1.

## Local-first development

**Repo layout** (all new, under `lead-research-agent/`):

```
lead-research-agent/
├── plan.md
├── pyproject.toml          # own package; uv path dep on ../shared-infra
├── baselines/
│   └── lead_research.json  # committed eval baseline
├── src/lead_research/
│   ├── pipeline.py         # the 4-stage run() (mirrors ReferenceAgent.run)
│   ├── tools.py            # web_search / fetch_page / crm_* as spine Tools
│   ├── search.py           # SearchClient + PageFetcher interfaces + fakes + lazy adapters
│   ├── scoring.py          # deterministic ICP rubric
│   ├── metrics.py          # ScoringAccuracy / CitationValidityRate / HallucinatedFactRate
│   └── eval.py             # build_suite() -> EvalSuite
├── eval/
│   ├── data/leads.jsonl    # golden dataset
│   └── fixtures/           # frozen HTML pages + search JSON per company
└── tests/
```

`pyproject.toml` declares a path dependency on the spine (uv):

```toml
[project]
dependencies = ["spine"]

[tool.uv.sources]
spine = { path = "../shared-infra", editable = true }
```

Run everything offline: `uv sync && uv run pytest && uv run ruff check`.

**Fakes to develop against** (all SDK-free, no GCP, no network):
- `spine.models.FakeModelClient(responder=...)` — a custom responder that parses
  the prompt's evidence block and returns canned extraction/draft JSON
  (cf. `default_responder` in `reference_agent.py`).
- `spine.rag.InMemoryRetriever` — collateral + per-run lead-evidence corpus;
  its `.get()` powers `resolve_citations`.
- `spine.memory.InMemorySessionStore` (dossier) and `InMemoryMemoryStore`
  (per-account knowledge).
- `spine.obs.InMemoryMetricsSink`; `spine.hitl.InMemoryEscalationStore` (behind
  `HumanQueue`).

**Web search / fetch have no local emulator** — the vertical owns these. In
`search.py`, define two interfaces and follow the spine's lazy-adapter pattern
(see `spine.rag.VertexSearchRetriever` and `spine.models_vertex.VertexModelClient`
for the exact shape — import the SDK lazily inside methods):

- `SearchClient.search(query) -> list[SearchResult]`
  - `FakeSearchClient` — returns fixture JSON from `eval/fixtures/.../search/`.
  - `GroundedSearchClient` — lazy-imports `google-genai`; uses **Grounding with
    Google Search** on Vertex AI (a `GenerateContentConfig` grounding tool) to
    return grounded results + source URIs.
- `PageFetcher.fetch(url) -> Page`
  - `FakePageFetcher` — returns frozen local HTML by domain.
  - `HttpPageFetcher` — plain HTTPS `httpx` GET, honoring `robots.txt` and a
    timeout; strips boilerplate to text. **No LinkedIn scraping.**

## Build phases

1. **Enricher, local-only** — `FakeSearchClient` + `FakePageFetcher` +
   `FakeModelClient` extract structured fields with evidence `doc_id`s; injection
   guard filters fetched pages. *Verify:* `pytest` extracts the expected fields
   from fixture pages, and a page containing "ignore previous instructions" is
   dropped from evidence (not fed to the model).
2. **Scorer + ICP rubric** — deterministic scoring over extracted fields; tier
   + evidence-coverage confidence. *Verify:* `ScoringAccuracy` on the golden set
   matches hand labels; scoring has zero model calls.
3. **Drafter + RAG + citations** — collateral ingested to an `InMemoryRetriever`;
   drafts carry cited claims; `CitationGuard` + `CitationValidityRate` +
   `HallucinatedFactRate` wired. *Verify:* a draft with a fabricated citation is
   caught by `resolve_citations`; a claim with no evidence raises hallucination
   rate.
4. **HITL + eval gate in CI** — every draft enqueues to `HumanQueue`; own CI
   workflow runs the gate against a committed baseline; `MetricRecord`s to the
   obs sink; `metrics_report` renders cost/latency/coverage. *Verify:* a
   deliberately worse rubric fails the gate; every run produces a pending review
   item and one metric record.
5. **GCP wiring (real adapters)** — swap fakes for `GroundedSearchClient`,
   `HttpPageFetcher`, `VertexModelClient`, `VertexSearchRetriever`,
   `FirestoreSessionStore`, HubSpot `crm_*`; optionally deploy stages as ADK
   agents on Agent Engine / Cloud Run. *Verify:* one real lead flows end-to-end
   to a pending, human-approvable draft, fully traced and observable — no
   auto-send.

## Definition of done

- A lead flows ingest → enrich → score → draft → **human review** → CRM write-back,
  **fully traced, logged, and observable**, with a **green eval gate** in CI.
- Enrichment and scoring are evaluated against a hand-labeled golden set;
  citation validity and hallucination rate are measured every run.
- **No draft is ever auto-sent.** Every outbound draft is human-approved.
- Reuses the spine with **zero** duplicated cross-cutting infrastructure; only
  `SearchClient`/`PageFetcher` and the ICP rubric are net-new.

## References

**Official docs**
- Grounding with Google Search on Vertex AI — https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/overview
- Gemini structured output (JSON) — https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output
- ADK (Agent Development Kit) — https://google.github.io/adk-docs/
- A2A protocol — https://github.com/google-a2a/A2A (spine has no A2A helpers yet)
- Vertex AI Agent Engine — https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview
- Vertex AI Search (RAG) — https://cloud.google.com/generative-ai-app-builder/docs/introduction
- Firestore — https://cloud.google.com/firestore/docs
- Vertex AI Memory Bank — https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/overview
- HubSpot CRM API — https://developers.hubspot.com/docs/api/crm/understanding-the-crm
- robots.txt (compliant scraping) — https://developers.google.com/search/docs/crawling-indexing/robots/intro
- CAN-SPAM (US): every commercial email needs a valid physical address + working opt-out; no deceptive headers — https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- GDPR (EU): outreach to EU persons needs a lawful basis (legitimate interest) + easy opt-out; log consent/basis per lead — https://gdpr.eu/

**Spine source pointers (trickiest wiring)**
- Pipeline shape (span per stage, one `run` entry point): `shared-infra/src/spine/reference_agent.py`
- Eval gate + baseline JSON + CLI: `shared-infra/src/spine/eval/gate.py`, `__main__.py`; CI shape: `.github/workflows/spine-ci.yml`
- Citation plumbing (`passages_to_citations`, `resolve_citations`, `.get()`): `shared-infra/src/spine/rag.py`
- Guardrail composition (`run_guardrails`, `AgentOutput`, `ConfidenceGuard`): `shared-infra/src/spine/guardrails.py`
- HITL queue (`HumanQueue.enqueue`, `escalate_if_needed`): `shared-infra/src/spine/hitl.py`
- Lazy-adapter pattern to copy for `search.py`: `spine.rag.VertexSearchRetriever`, `spine.models_vertex.VertexModelClient`
- Metric records → dashboard: `shared-infra/src/spine/obs.py`
