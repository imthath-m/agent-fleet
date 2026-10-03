# Triage (Support Agent) — Task Decomposition

Executable decomposition of `support-agent/plan.md` against the spine as it
actually exists today. **Done** = a synthetic-or-real support ticket enters
`triage.api` (or `triage.pipeline` directly), flows Classifier → Resolver →
Action → HITL gate as a sequential in-process chain on `spine/`, produces either
a grounded cited answer or an escalation with proposed (never executed) actions,
and every step is a span + structured log + `MetricRecord`; a `support-agent` CI
job runs ruff + pytest + an eval gate against committed baselines; and the
landing-page trial renders the span tree, the resolved citation into the real
help.ubuntu.com KB, the grounding check, and the confidence/escalation decision.
All of it runs locally on `FakeModelClient` + in-memory stores with zero GCP.

**Consumer note:** each task is independently actionable. IDs are stable. Do not
renumber. `PARALLEL` tasks within a phase may be fanned out simultaneously;
`SEQ` tasks must complete before the tasks listed in their `After:` line start.
A phase is not complete until **every** `Verify:` in it passes.

---

## Decisions (fixed — do not re-litigate)

1. **No A2A.** Classifier → Resolver → Action is a plain sequential in-process
   function chain in `triage/pipeline.py`. *Rationale: A2A is named in
   `support-agent/plan.md` and `shared-infra/plan.md` but exists nowhere in the
   repo; a single-process chain is the honest shape until a second agent needs a
   wire protocol. Do not build A2A in these tasks.*
2. **Demo KB = help.ubuntu.com** (CC BY-SA 4.0), fetched, normalized, chunked
   and ingested for real. *Rationale: verified-open real documentation beats
   invented corpora, and its ShareAlike/attribution terms are satisfiable — so
   attribution must be carried through `Document.metadata` into the demo UI.*
3. **Tickets are synthetic, generated from the real KB chunks.** *Rationale:
   Stack Exchange dump terms restrict LLM use; real forum questions are often
   unanswerable from the docs; synthetic generation is the only way to get
   deliberate coverage of priority/sentiment/ambiguity. ~10 unmodified Ask Ubuntu
   questions are kept as spot-check fixtures only — never as golden labels.*
4. **Drafts-only, read-only integrations pre-sale.** `issue_refund` and
   `crm_update` are mock adapters returning a `ProposedAction` routed to HITL;
   `order_lookup` reads a fixture store. *Rationale: no customer system exists to
   write to, and a demo that mutates anything is unsellable.*
5. **The trace IS the demo.** The trial surface must render span tree, resolved
   citation → real KB URL, grounding check result, and the
   confidence/escalation decision — not just answer text. *Rationale: the
   differentiator in `overview.md` is auditability; answer text alone is
   indistinguishable from a chat wrapper.*
6. **Local-first, zero GCP.** Everything runs on `FakeModelClient` +
   `InMemoryRetriever` + `InMemory*Store` + `InMemoryMetricsSink`, mirroring
   `spine.reference_agent`. *Rationale: the spine already proves every GCP
   backend sits behind a lazy adapter; cutover is Phase 8, behind unchanged
   interfaces.*

---

## Open questions (unresolved — resolve before the phase that needs them)

| # | Question | Options | Resolved by |
| --- | --- | --- | --- |
| Q1 | ✅ **Resolved** — enums pinned in `triage/schemas.py`. Exact classifier output schema. | (a) 4 fields `intent/priority/product_area/sentiment` + `pii_flag` per plan.md; (b) add free-text `reason` for judge/debug; (c) add `confidence` self-report (unreliable, prefer retrieval score). Enum vocabularies for each field also undecided. | Blocks **2.1**. Decide by writing 20 candidate tickets and checking which fields a human labeller can agree on; pin the enums in `triage/schemas.py` and never widen without a dataset version bump. |
| Q2 | Which CRM adapter first, if ever pre-sale. | (a) none — `crm_update` stays a mock forever until a paying customer names one; (b) HubSpot (free dev tier, generous API); (c) Zendesk (closer to the support inbox). | Only relevant at Phase 8+. Decision 4 makes (a) the default; a signed customer overrides. |
| Q3 | Golden set: model-generated or hand-curated. | (a) fully generated from KB chunks + spot-reviewed; (b) generated then 100% human-corrected labels; (c) hand-written. (a) scales but risks the eval measuring the generator; (b) is the honest middle. | Still blocks **6.3** (the only open Phase 0–7 task). Recommendation: (b) — generate inputs, hand-correct every `expected`. Whoever owns eval credibility decides. |
| Q4 | Real-Gemini cutover timing. | (a) after Phase 6 (gate exists, so regressions are visible); (b) after Phase 7 (trial demoable first, cheapest path to a prospect); (c) never pre-revenue. | Blocks **8.1**. Needs a cost ceiling per ticket and a funded GCP project; neither exists yet. |
| Q5 | Multi-tenancy model. | Today the only tenancy primitive is the `namespace: str` argument on `spine.rag.Retriever.ingest/query`. Options: (a) namespace-per-customer string only; (b) namespace + a `tenant_id` threaded through `MetricRecord`/`SessionStore`/`HumanQueue` keys; (c) process-per-tenant. | Blocks any second tenant, and blocks **8.3**/**8.5**. (a) is sufficient for one demo tenant — do not build (b) speculatively, but do not hardcode the namespace anywhere outside `triage/config.py`. |

---

## Conventions (apply to every task)

- Python package name is **`triage`** under `support-agent/src/triage/`; the
  directory stays `support-agent/` for repo continuity.
- Mirror `shared-infra/pyproject.toml`: hatchling, `requires-python = "==3.11.*"`,
  `[tool.ruff] line-length = 100`, `select = ["E","F","I","UP","B"]`,
  `[tool.pytest.ini_options] testpaths = ["tests"]`, `addopts = "-q"`.
- Tests mirror `shared-infra/tests/`: flat `tests/test_<module>.py`, plain
  `assert`, no mocking framework, banner comments separating concern groups,
  `FakeModelClient` for anything model-shaped.
- Never re-implement a spine concern. If a task needs tracing, logging, metrics,
  guards, memory, retrieval, eval, or a queue, it imports `spine.*`.
- Every commit must leave `uv run ruff check` and `uv run pytest` green in
  `support-agent/`.

---

## Phase 0 — Scaffold — ✅ done

**Goal:** an importable, lintable, testable `triage` package that depends on
`spine` and has its own CI job. **Depends on:** nothing.

- **0.1** `SEQ` · sonnet — Create the package skeleton and packaging.
  - Creates: `support-agent/pyproject.toml`, `support-agent/README.md`,
    `support-agent/src/triage/__init__.py`, `support-agent/tests/.gitkeep`.
  - `pyproject.toml`: `name = "triage"`, dependency on the local spine via
    `[tool.uv.sources] spine = { path = "../shared-infra", editable = true }`
    plus `dependencies = ["spine", "fastapi>=0.110", "httpx>=0.27"]`;
    `[dependency-groups] dev = ["pytest>=8.0", "ruff>=0.5"]`.
  - Reuses: `spine` (import only).
  - **Verify:** `cd support-agent && uv sync && uv run python -c "import triage, spine.reference_agent; print(triage.__version__)"` exits 0 and prints `0.1.0`.
  - **After:** unblocks everything.

- **0.2** `SEQ` · sonnet — Domain schemas.
  - Creates: `src/triage/schemas.py`, `tests/test_schemas.py`.
  - Frozen dataclasses: `Ticket(ticket_id, text, channel, customer_id, subject, received_at)`,
    `Classification(intent, priority, product_area, sentiment, pii_flag)` (fields
    per **Q1**), `Resolution(answer, citations, grounded, retrieval_score)`,
    `ProposedAction(tool, args, idempotency_key, risk, executed=False)`,
    `TriageResult(request_id, trace_id, ticket, classification, resolution,
    proposed_actions, escalation, withheld, metric)` — deliberately shaped like
    `spine.reference_agent.ReferenceResult` so the same assertions transfer.
  - Each carries `to_dict()`/`from_dict()` (plain `dataclasses.asdict`-based) so
    golden JSONL rows and the API response share one serialization path.
  - Reuses: `spine.guardrails.AgentOutput`, `spine.hitl.EscalationItem`,
    `spine.obs.MetricRecord` as field types.
  - **Verify:** `uv run pytest tests/test_schemas.py` — includes
    `test_every_schema_round_trips_through_dict` asserting
    `X.from_dict(x.to_dict()) == x` for all five types.
  - **After:** 0.1.

- **0.3** `PARALLEL` · haiku — Central config module.
  - Creates: `src/triage/config.py`.
  - Constants only, no logic: `AGENT_ID = "triage-agent"`,
    `KB_NAMESPACE = "ubuntu-docs"` (the sole tenancy primitive per **Q5** — must
    not be hardcoded anywhere else), `MODEL_CONFIG = ModelConfig(...)`,
    `CONFIDENCE_THRESHOLD = 0.6`, `RETRIEVAL_TOP_K = 4`,
    `HIGH_RISK_TOOLS = ("issue_refund", "crm_update")`.
  - Reuses: `spine.models.ModelConfig`.
  - **Verify:** `uv run ruff check` clean and
    `grep -rn "ubuntu-docs" src/ | grep -v config.py` returns nothing.
  - **After:** 0.1.

- **0.4** `PARALLEL` · haiku — CI workflow for the support agent.
  - Creates: `.github/workflows/support-agent-ci.yml` (the only file outside
    `support-agent/` this phase touches).
  - Copy the shape of `.github/workflows/spine-ci.yml` exactly: `astral-sh/setup-uv@v5`,
    `uv python install 3.11`, `uv sync`, `uv run ruff check`, `uv run pytest`,
    `defaults.run.working-directory: support-agent`. Triggers on
    `support-agent/**`, `shared-infra/**` (a spine change can break the vertical),
    and the workflow file itself. Leave the eval-gate step out — **6.5** adds it.
  - **Verify:** `actionlint .github/workflows/support-agent-ci.yml` (or
    `python -c "import yaml,sys;yaml.safe_load(open(...))"` if unavailable) exits 0,
    and the same command sequence run locally in `support-agent/` is green.
  - **After:** 0.1.

**Phase 0 exit:** `uv sync && uv run ruff check && uv run pytest` green in
`support-agent/`; CI file present and valid.

---

## Phase 1 — KB ingestion (real Ubuntu docs) — ✅ done

**Goal:** a real, attributed, chunked corpus queryable through
`spine.rag.InMemoryRetriever`, committed to the repo so every later phase is
offline-deterministic. **Depends on:** Phase 0.

- **1.1** `SEQ` · sonnet — Fetch script for help.ubuntu.com.
  - Creates: `scripts/fetch_kb.py`, `data/kb/raw/` (gitignored), `data/kb/MANIFEST.json`.
  - Fetch a fixed, enumerated page list (start with ~40 pages across install,
    networking, packaging, users/permissions, hardware) over `httpx`. Write raw
    HTML to `data/kb/raw/<slug>.html` and record `{slug, url, fetched_at, sha256}`
    in `MANIFEST.json`. Network runs **only** in this script — never at import,
    test, or request time.
  - **Verify:** `uv run python scripts/fetch_kb.py --limit 5` writes 5 files and 5
    manifest entries; re-running is idempotent (identical `sha256` set).

- **1.2** `SEQ` · sonnet — Normalize + chunk into `Document` rows.
  - Creates: `src/triage/ingest.py`, `data/kb/ubuntu_docs.jsonl` (committed),
    `tests/test_ingest.py`.
  - `normalize(html) -> str` strips nav/chrome/scripts to plain text;
    `chunk(text, *, target_chars=1200, overlap=150) -> list[str]`;
    `to_documents(slug, url, chunks) -> list[Document]` producing
    `spine.rag.Document(doc_id=f"{slug}#{i}", text=..., source=url,
    metadata={"license": "CC BY-SA 4.0", "license_url": ..., "title": ..., "url": ...})`.
  - Chunk boundaries must prefer heading/paragraph breaks — a chunk that splits a
    command block is a grounding failure later.
  - **Verify:** `uv run pytest tests/test_ingest.py` — asserts every emitted
    `Document` has a unique `doc_id`, non-empty `source`, and a `metadata["license"]`;
    asserts `chunk()` on a 5000-char fixture yields overlapping chunks whose
    concatenation covers the input.
  - **After:** 1.1.

- **1.3** `SEQ` · sonnet — KB loader.
  - Creates: `src/triage/kb.py`, `tests/test_kb.py`.
  - `load_kb(path=DEFAULT_KB_PATH) -> InMemoryRetriever` seeded into
    `config.KB_NAMESPACE`; `attribution_for(retriever, doc_id) -> dict` returning
    `{title, url, license, license_url}` for the trial UI;
    `check_grounding(retriever, citations) -> list[str]` thin wrapper over
    `spine.rag.resolve_citations`.
  - Reuses: `spine.rag.InMemoryRetriever`, `Document`, `resolve_citations`,
    `passages_to_citations`.
  - **Verify:** `uv run pytest tests/test_kb.py` — `test_load_kb_is_queryable`
    asserts a known query (e.g. `"how do I add a user to a group"`) returns ≥1
    passage whose `doc_id` is in the corpus; `test_fabricated_citation_is_caught`
    asserts `check_grounding(r, ["not-a-real-doc#0"]) == ["not-a-real-doc#0"]`.
  - **After:** 1.2.

- **1.4** `PARALLEL` · haiku — Attribution artifacts.
  - Creates: `support-agent/data/kb/ATTRIBUTION.md`; adds an "Attribution" section
    to `support-agent/README.md`.
  - Names help.ubuntu.com as the source, CC BY-SA 4.0 with a link, and states that
    any surface displaying KB text must display the source URL and licence
    (obligation carried into **7.3**).
  - **Verify:** `grep -c "CC BY-SA 4.0" data/kb/ATTRIBUTION.md README.md` ≥ 1 each;
    the licence string matches `metadata["license"]` emitted by 1.2 exactly.
  - **After:** 1.2.

**Phase 1 exit:** `data/kb/ubuntu_docs.jsonl` committed (target ≥ 300 chunks);
`load_kb()` returns a retriever answering ≥ 8 of 10 hand-written probe queries
with a relevant chunk; attribution present.

---

## Phase 2 — Classifier — ✅ done

**Goal:** structured classification of a ticket, schema-guarded, traced, with a
deterministic eval suite. **Depends on:** Phase 0 (Phase 1 not required).

- **2.1** `SEQ` · opus — Classifier stage.
  - Creates: `src/triage/classifier.py`, `tests/test_classifier.py`.
  - `classify(ticket, *, model, logger) -> tuple[Classification, GuardrailReport]`.
  - Input guards, in this order:
    `PromptInjectionGuard()` then `PiiGuard(block_on_detect=False)`. **PII must
    not block** — support tickets legitimately contain emails and phone numbers;
    use `GuardrailResult.redacted_text` from the PII result as the text sent to
    the model, and set `Classification.pii_flag` from whether PII was found.
    A `Decision.BLOCK` from the injection guard short-circuits the whole pipeline.
  - Model call inside `span("classify", step=StepType.MODEL_CALL)`; parse with
    `spine.eval.runner.parse_json_prediction`; validate with
    `SchemaGuard(required_fields=[...], types={...})` over an
    `AgentOutput(data=parsed)`. A schema `BLOCK` is a hard failure, not an
    escalation (bad model output, not an ambiguous ticket).
  - Enum vocabularies come from **Q1** and live in `schemas.py`.
  - Reuses: `spine.guardrails.{PromptInjectionGuard, PiiGuard, SchemaGuard,
    AgentOutput, run_guardrails, Decision}`, `spine.tracing.{span, StepType,
    record_metrics}`, `spine.logging.log_event`, `spine.models.WrappedModelClient`.
  - **Verify:** `uv run pytest tests/test_classifier.py` — includes
    `test_pii_is_redacted_not_blocked` (ticket containing an email classifies
    successfully, `pii_flag is True`, and the prompt passed to the
    `FakeModelClient` contains `[REDACTED_EMAIL]` and not the raw address),
    `test_injection_blocks`, `test_malformed_model_json_fails_schema_guard`.

- **2.2** `PARALLEL` · sonnet — Deterministic classifier fake.
  - Creates: `src/triage/fakes.py`.
  - `classifier_responder(prompt) -> str` returning canned JSON keyed off
    keywords in the embedded ticket text — the classifier's analogue of
    `spine.reference_agent.default_responder`. Every local run and test uses
    `FakeModelClient(responder=classifier_responder)`.
  - **Verify:** `uv run pytest tests/test_classifier.py` passes with no network
    and no `models_vertex` import (`grep -rn "models_vertex" src/ tests/` returns
    nothing).
  - **After:** 2.1.

- **2.3** `PARALLEL` · sonnet — Bootstrap classification golden set.
  - Creates: `data/golden/classification.jsonl`.
  - Seed by porting the 5 rows of
    `shared-infra/src/spine/eval/data/support_resolution.jsonl` into the **Q1**
    schema, then hand-add rows until ≥ 15 examples covering every enum value at
    least once. Header line: `{"schema_version": 1, "name": "triage_classification", "dataset_version": "1"}`.
  - Reuses: `spine.eval.dataset.{load_dataset, GoldenExample}` format.
  - **Verify:** `uv run python -c "from spine.eval import load_dataset; d=load_dataset('data/golden/classification.jsonl'); print(len(d))"` prints ≥ 15 with no `DatasetError`.
  - **After:** 2.1 (needs the pinned schema).

- **2.4** `SEQ` · sonnet — Classification eval suite.
  - Creates: `src/triage/eval/__init__.py`, `src/triage/eval/suites.py`,
    `tests/test_eval_classification.py`.
  - `build_classification_suite() -> EvalSuite` — no-arg factory (required by
    `spine.eval.runner.load_suite`) over `data/golden/classification.jsonl`, with
    metrics `SchemaPassRate(required_fields=[...])` and
    `FieldAccuracy(fields=["intent","priority","product_area","sentiment"])`.
    Predictor calls `classify()` and returns a `Prediction`.
  - **Verify:** `uv run python -m spine.eval run --suite triage.eval.suites:build_classification_suite` exits 0 and prints `mean_scores` with `field_accuracy >= 0.90` and `schema_pass_rate == 1.0`.
  - **After:** 2.1, 2.2, 2.3.

- **2.5** `SEQ` · haiku — Classifier baseline.
  - Creates: `baselines/classification.json`.
  - **Verify:** `uv run python -m spine.eval baseline --suite triage.eval.suites:build_classification_suite --out baselines/classification.json` then `uv run python -m spine.eval gate --suite triage.eval.suites:build_classification_suite --baseline baselines/classification.json` exits 0.
  - **After:** 2.4.

**Phase 2 exit:** classification gate passes; `field_accuracy ≥ 0.90`,
`schema_pass_rate = 1.0`; no network in tests.

---

## Phase 3 — Resolver + RAG grounding — ✅ done

**Goal:** grounded, cited answers over the real KB, with a grounding metric that
catches fabricated citations. **Depends on:** Phase 1, Phase 2.

- **3.1** `SEQ` · opus — Resolver stage.
  - Creates: `src/triage/resolver.py`, `tests/test_resolver.py`.
  - `resolve(ticket, classification, *, retriever, model, logger) -> tuple[Resolution, GuardrailReport]`.
  - Steps, each its own span: `span("retrieval", step=StepType.RETRIEVAL)` calling
    `retriever.query(config.KB_NAMESPACE, query, top_k=config.RETRIEVAL_TOP_K)`
    (query = ticket text, optionally prefixed with `classification.product_area`);
    `passages_to_citations`; `span("resolve", step=StepType.MODEL_CALL)` building
    a `Context:`/`User:` prompt in the same shape
    `spine.reference_agent._build_prompt` uses so `default_responder`-style fakes
    work; then output guards
    `[SchemaGuard(required_fields=["answer"]), CitationGuard(required=True, min_citations=1), ConfidenceGuard(threshold=config.CONFIDENCE_THRESHOLD)]`.
  - `Resolution.grounded` = `citations non-empty AND kb.check_grounding(...) == []`.
    `Resolution.retrieval_score` = `passages[0].score` (the confidence signal fed
    to `ConfidenceGuard`, exactly as `ReferenceAgent` does).
  - Reuses: `spine.rag.{passages_to_citations, resolve_citations}`,
    `spine.guardrails.{SchemaGuard, CitationGuard, ConfidenceGuard, AgentOutput,
    run_guardrails}`, `spine.tracing.{span, StepType, record_metrics}`.
  - **Verify:** `uv run pytest tests/test_resolver.py` — includes
    `test_answer_cites_a_real_kb_doc` (every returned citation resolves via
    `check_grounding`), `test_no_retrieval_hits_yields_ungrounded_resolution`
    (empty corpus → `grounded is False`, `CitationGuard` blocks),
    `test_fabricated_citation_marks_ungrounded`.

- **3.2** `PARALLEL` · sonnet — `GroundingRate` metric.
  - Creates: `src/triage/eval/metrics.py`, `tests/test_eval_metrics.py`.
  - Dataclass implementing the `spine.eval.metrics.Metric` protocol (`name`,
    `score(example, prediction) -> MetricResult`): score `1.0` when
    `prediction.output["citations"]` is non-empty and every citation resolves in
    the retriever, else `0.0`. Detail carries the unresolved ids.
  - Reuses: `spine.eval.metrics.{Metric, MetricResult, Prediction}`,
    `spine.rag.resolve_citations`.
  - **Verify:** `uv run pytest tests/test_eval_metrics.py` — asserts score `1.0`
    for a real citation, `0.0` for a fabricated one, `0.0` for none.
  - **After:** 3.1.

- **3.3** `SEQ` · sonnet — Resolution golden set + suite.
  - Creates: `data/golden/resolution.jsonl`, extends `src/triage/eval/suites.py`
    with `build_resolution_suite()`.
  - ≥ 15 examples; `expected` carries `answer` (reference text for the judge) and
    `citations` (the KB `doc_id`s a correct answer should reach). Metrics:
    `GroundingRate()`, `LlmJudge(client=FakeModelClient(...), criterion="resolution correctness", reference_key="answer")`,
    `SchemaPassRate(required_fields=["answer","citations"])`.
  - The judge client is a `FakeModelClient` returning canned JSON scores (copy the
    pattern in `spine.eval.example.demo_judge_client`) — a real judge is Phase 8.
  - **Verify:** `uv run python -m spine.eval run --suite triage.eval.suites:build_resolution_suite` exits 0 with `grounding_rate >= 0.90` and `llm_judge >= 0.70`.
  - **After:** 3.1, 3.2.

- **3.4** `SEQ` · haiku — Resolver baseline.
  - Creates: `baselines/resolution.json`.
  - **Verify:** `uv run python -m spine.eval baseline --suite triage.eval.suites:build_resolution_suite --out baselines/resolution.json` then the matching `gate` invocation exits 0.
  - **After:** 3.3.

**Phase 3 exit:** grounding rate ≥ 0.90 on the resolution set; a deliberately
fabricated citation demonstrably drives the metric to 0.

---

## Phase 4 — Tools + action agent (mocks, drafts-only) — ✅ done

**Goal:** four named tools that validate inputs, are idempotent, emit tool spans,
and never cause a real side effect. **Depends on:** Phase 1 (for `kb_search`),
Phase 3 (for the action agent's inputs).

- **4.1** `PARALLEL` · sonnet — `kb_search` tool.
  - Creates: `src/triage/tools/__init__.py`, `src/triage/tools/kb_search.py`.
  - `kb_search(query: str, top_k: int = 4) -> list[dict]` over the loaded
    retriever; wrapped as `spine.agent.Tool(name="kb_search", ...)`. Read-only,
    `risk="low"`. Executes inside `timed_span("tool.kb_search", step=StepType.TOOL_CALL)`.
  - **Verify:** `uv run pytest tests/test_tools.py::test_kb_search_returns_cited_passages`.

- **4.2** `PARALLEL` · sonnet — `order_lookup` mock adapter.
  - Creates: `src/triage/tools/order_lookup.py`, `data/fixtures/orders.json`.
  - Reads a committed fixture store keyed by `order_id`; unknown id returns a
    structured `{"found": false}`, never raises. Read-only, `risk="low"`.
  - **Verify:** `uv run pytest tests/test_tools.py::test_order_lookup_known_and_unknown`.

- **4.3** `PARALLEL` · sonnet — `issue_refund` mock (high-risk, drafts-only).
  - Creates: `src/triage/tools/issue_refund.py`.
  - Returns `ProposedAction(tool="issue_refund", args={...},
    idempotency_key=sha256(order_id|amount|reason), risk="high", executed=False)`.
    **Must contain no write path at all** — not even a disabled one. Validates
    `amount > 0` and a known `order_id` before proposing.
  - **Verify:** `uv run pytest tests/test_tools.py` — includes
    `test_issue_refund_never_executes` (asserts `executed is False` and that the
    fixture store is byte-identical before and after) and
    `test_issue_refund_idempotency_key_is_stable` (same args → same key, different
    args → different key).

- **4.4** `PARALLEL` · sonnet — `crm_update` mock (high-risk, drafts-only).
  - Creates: `src/triage/tools/crm_update.py`.
  - Same contract as 4.3: proposes `{ticket_id, resolution_summary, tags}`, never
    writes. **Q2** governs whether a real adapter ever lands.
  - **Verify:** `uv run pytest tests/test_tools.py::test_crm_update_proposes_only`.

- **4.5** `SEQ` · opus — Action agent.
  - Creates: `src/triage/actions.py`, `tests/test_actions.py`.
  - `plan_actions(ticket, classification, resolution) -> list[ProposedAction]`:
    deterministic routing rules (plain code, not a model call — per
    `shared-infra/plan.md` "deterministic where possible"). Any tool in
    `config.HIGH_RISK_TOOLS` yields a `ProposedAction` that forces escalation in
    Phase 5. Counts failures into a `tool_errors` int that flows to
    `MetricRecord.tool_errors`.
  - Reuses: `spine.agent.Tool`, `spine.tracing.{timed_span, StepType}`,
    `spine.logging.log_event` (with `tool=` set).
  - **Verify:** `uv run pytest tests/test_actions.py` — includes
    `test_high_risk_action_is_never_auto_executed`,
    `test_tool_span_emitted_per_call` (asserts one span per tool call with
    `spine.step == "tool_call"` via `configure_tracing()` + `get_finished_spans()`),
    `test_repeat_run_produces_identical_idempotency_keys`.
  - **After:** 4.1–4.4.

- **4.6** `PARALLEL` · sonnet — Tool HTTP backend.
  - Creates: `src/triage/tool_backend.py`, `tests/test_tool_backend.py`.
  - FastAPI app mirroring `spine.tool_backend` exactly (`/healthz` + one route per
    tool). This is the Cloud Run target; it stays local until Phase 8.
  - **Verify:** `uv run pytest tests/test_tool_backend.py` using
    `fastapi.testclient.TestClient` — `/healthz` returns `{"status": "ok"}` and each
    of the four routes returns its schema.
  - **After:** 4.1–4.4.

- **4.7** `SEQ` · sonnet — Tool-call correctness eval.
  - Creates: `data/golden/actions.jsonl`, `build_actions_suite()` in
    `src/triage/eval/suites.py`.
  - `expected.tool_calls` per example; metric `ToolCallCorrectness(ordered=False)`.
  - **Verify:** `uv run python -m spine.eval run --suite triage.eval.suites:build_actions_suite` prints `tool_call_correctness >= 0.90`.
  - **After:** 4.5.

**Phase 4 exit:** all four tools present, idempotent, span-emitting; zero write
paths in the codebase (`grep -rn "requests.post\|httpx.post\|\.write(" src/triage/tools/`
returns nothing); tool-call correctness ≥ 0.90.

---

## Phase 5 — Pipeline, HITL, confidence gating, queue UI — ✅ done

**Goal:** the three stages composed into one traced request, with an explicit
escalation policy and a minimal human queue. **Depends on:** Phases 2, 3, 4.

- **5.1** `SEQ` · opus — The pipeline.
  - Creates: `src/triage/pipeline.py`, `tests/test_pipeline.py`.
  - `TriageAgent.run(ticket) -> TriageResult`, structurally mirroring
    `spine.reference_agent.ReferenceAgent.run`: one
    `request_span(request_id=..., agent=config.AGENT_ID)` parent; children
    `input_guardrail`, `classify`, `retrieval`, `resolve`, `tool_call*`,
    `output_guardrail`; `current_trace_id()` captured; `log_event` at every step;
    session append via `InMemorySessionStore`, per-customer history via
    `InMemoryMemoryStore.get_all(customer_id, AGENT_ID)`; one `MetricRecord`
    written to the sink on every exit path including blocks.
  - Constructor takes injectable `retriever`, `model`, `hitl`, `session_store`,
    `memory_store`, `obs_sink`, `logger` with in-memory defaults — same signature
    style as `ReferenceAgent.__init__`.
  - No A2A. This is a function chain (Decision 1).
  - **Verify:** `uv run pytest tests/test_pipeline.py::test_pipeline_end_to_end`
    — modelled on `shared-infra/tests/test_reference_agent.py::test_reference_agent_end_to_end`:
    asserts (a) the exact expected span-name set with all children parented to the
    request span, (b) every structured log line shares `result.trace_id`, (c)
    guardrail decisions recorded on both guardrail spans, (d) memory readable on a
    second run, (e) a `MetricRecord` in the sink with the right `request_id`.

- **5.2** `SEQ` · opus — Escalation policy.
  - Creates: `src/triage/escalation.py`, `tests/test_escalation.py`.
  - `should_escalate(classification, resolution, actions, output_report) -> tuple[bool, str]`
    with explicit, individually-testable rules: (1) `output_report.decision ==
    Decision.ESCALATE` (low confidence), (2) `not resolution.grounded`, (3) any
    action whose `tool` is in `config.HIGH_RISK_TOOLS`, (4) `priority == "urgent"`,
    (5) `sentiment == "angry"` combined with `priority in ("high","urgent")`.
    Escalating routes through `escalate_if_needed(report, queue, payload={...})`;
    payload must carry `trace_id`, ticket text, draft answer, citations, and the
    `ProposedAction` list so a reviewer can decide without the code.
  - Reuses: `spine.hitl.{HumanQueue, escalate_if_needed, EscalationItem}`,
    `spine.guardrails.Decision`.
  - **Verify:** `uv run pytest tests/test_escalation.py` — one test per rule
    asserting it fires in isolation, plus
    `test_escalated_ticket_withholds_answer` (`TriageResult.withheld is True`,
    `resolution.answer` not delivered, item present in `hitl.pending()`).
  - **After:** 5.1.

- **5.3** `PARALLEL` · sonnet — Minimal human queue UI.
  - Creates: `src/triage/review.py`, `tests/test_review.py`.
  - A CLI (`python -m triage.review list|show <id>|resolve <id> --note "..."`)
    over `HumanQueue.pending()` / `.resolve()`. `show` prints trace id, ticket,
    draft answer, citations with their source URLs (via `kb.attribution_for`), and
    each proposed action with its risk. This is the "minimal queue UI" of
    plan.md phase 4 — deliberately a CLI, not a web app; the web view is **7.3**.
  - **Verify:** `uv run pytest tests/test_review.py` — enqueue → `list` shows it →
    `resolve` moves it out of `pending()` and sets `resolution`.
  - **After:** 5.2.

- **5.4** `SEQ` · sonnet — Escalation precision/recall metric.
  - Creates: `EscalationPrecisionRecall` in `src/triage/eval/metrics.py`,
    `data/golden/escalation.jsonl`, `build_escalation_suite()` in `suites.py`.
  - Per-example score is exact match on `expected["escalated"]` (a
    `FieldAccuracy(fields=["escalated"])` suffices for the mean); the suite
    additionally reports aggregate precision and recall over the dataset in the
    metric `detail` so the CI gate has a single number and humans can see both.
  - **Verify:** `uv run python -m spine.eval run --suite triage.eval.suites:build_escalation_suite` prints escalation precision ≥ 0.80 and recall ≥ 0.90 (recall weighted higher: a missed escalation is the expensive error).
  - **After:** 5.2.

**Phase 5 exit:** `test_pipeline_end_to_end` green; a low-confidence ticket and a
refund ticket both land in `hitl.pending()` with full payloads; the review CLI can
list and resolve them.

---

## Phase 6 — Golden set expansion + CI eval gate — ✅ done except 6.3

**Goal:** a golden set big enough that the gate means something, wired into CI.
**Depends on:** Phases 2, 3, 4, 5. Resolve **Q3** before 6.3.

- **6.1** `SEQ` · sonnet — Synthetic ticket generator.
  - Creates: `scripts/generate_tickets.py`, `data/generated/tickets.jsonl`.
  - Reads `data/kb/ubuntu_docs.jsonl`; for each sampled chunk emits ticket text
    that is answerable from that chunk, with a deliberately varied
    priority/sentiment/verbosity/ambiguity profile, plus a `source_doc_id` field
    (the ground-truth citation). Deterministic under `--seed`. Generation may use
    a model; the output is committed so downstream runs are offline.
  - **Verify:** `uv run python scripts/generate_tickets.py --seed 7 --n 80` twice
    produces byte-identical output; every row's `source_doc_id` exists in the KB.

- **6.2** `PARALLEL` · haiku — Ask Ubuntu spot-check fixtures.
  - Creates: `data/fixtures/askubuntu_spotcheck.jsonl`.
  - ~10 real, **unmodified** Ask Ubuntu questions with their URLs and no expected
    labels. Used only by a smoke test asserting the pipeline runs and either
    answers-with-citations or escalates — never as golden labels (Decision 3).
  - **Verify:** `uv run pytest tests/test_spotcheck.py::test_real_questions_do_not_crash`
    — all 10 produce a `TriageResult` and none produce an ungrounded delivered answer.

- **6.3** `SEQ` · fable — Expand the golden sets. **⏳ Not done** — sets are 16–19 rows each; `test_golden_coverage.py` absent.
  - Touches: `data/golden/classification.jsonl`, `resolution.jsonl`,
    `actions.jsonl`, `escalation.jsonl`; bump each header's `dataset_version`.
  - Target ≥ 60 examples per set drawn from 6.1, with **every `expected` field
    human-corrected** (per **Q3** recommendation). Coverage requirements: every
    intent, every priority, every sentiment; ≥ 20% deliberately ambiguous or
    unanswerable-from-KB cases labelled `escalated: true`; ≥ 10% containing PII.
  - **Verify:** `uv run pytest tests/test_golden_coverage.py` — asserts per-set
    size ≥ 60, no duplicate ids, every enum value present ≥ 3 times, and
    escalation-positive share between 20% and 40%.
  - **After:** 6.1.

- **6.4** `SEQ` · sonnet — Combined suite + fresh baselines.
  - Creates: `build_triage_suite()` in `src/triage/eval/suites.py`;
    regenerates `baselines/{classification,resolution,actions,escalation}.json`.
  - `build_triage_suite()` runs the full `TriageAgent` as the predictor over the
    resolution set, so the gate covers the composed pipeline and not just stages —
    the analogue of `spine.reference_agent.build_reference_suite`.
  - **Verify:** for each of the four suites,
    `uv run python -m spine.eval baseline --suite ... --out baselines/<name>.json`
    followed by `gate --suite ... --baseline baselines/<name>.json` exits 0.
  - **After:** 6.3.

- **6.5** `SEQ` · sonnet — Wire the gate into CI.
  - Touches: `.github/workflows/support-agent-ci.yml`.
  - Add one eval-gate step per suite, copying the shape of the
    `Eval gate (reference agent)` step in `spine-ci.yml`.
  - **Verify:** locally run every gate command in the workflow — all exit 0. Then
    prove the gate bites: temporarily make `classify()` return a constant
    `intent`, confirm the classification gate exits 1, revert.
  - **After:** 6.4.

**Phase 6 exit:** ≥ 60 examples per golden set; four gates green in CI; a
deliberately degraded classifier fails the gate.

---

## Phase 7 — Ingestion surface + landing-page trial — ✅ done

**Goal:** a ticket can be submitted over HTTP and a prospect can watch the trace.
**Depends on:** Phase 5 (Phase 6 not strictly required; run in parallel with 6).

- **7.1** `SEQ` · sonnet — REST ingestion endpoint.
  - Creates: `src/triage/api.py`, `tests/test_api.py`.
  - FastAPI, mirroring `spine.tool_backend` conventions: `GET /healthz`,
    `POST /tickets` (body → `Ticket` → `TriageAgent.run` → serialized
    `TriageResult`), `GET /queue`, `POST /queue/{id}/resolve`. Email/webform
    intake from plan.md is **out of scope** — a generic REST endpoint is the
    single ingestion surface until a customer needs more.
  - **Verify:** `uv run pytest tests/test_api.py` with `TestClient` — a POSTed
    ticket returns 200 with `trace_id`, `classification`, `answer` or
    `escalation`, and `citations`; a refund ticket returns an escalation and shows
    up in `GET /queue`.

- **7.2** `SEQ` · sonnet — Trace serialization.
  - Creates: `src/triage/trace_view.py`, `tests/test_trace_view.py`.
  - `span_tree(exporter) -> list[dict]` producing
    `{name, step, depth, latency_ms, tokens, cost_usd, decision, children}` —
    generalize `spine.reference_agent._render_span_tree` into JSON rather than
    printed text. Add `include_trace=true` to `POST /tickets` to attach it.
  - Reuses: `spine.tracing.{configure_tracing, ATTR_STEP, ATTR_TOKENS, ATTR_COST,
    ATTR_LATENCY, ATTR_DECISION}`.
  - **Verify:** `uv run pytest tests/test_trace_view.py` — one run yields a tree
    whose root is `request`, containing `classify`, `retrieval`, `resolve`, and
    `output_guardrail` as descendants, each with a `spine.step` value.
  - **After:** 7.1.

- **7.3** `SEQ` · sonnet — Landing-page trial surface.
  - Creates: `landing-page/site/trial.html`, `landing-page/site/trial.js`; links
    it from the Triage card in `landing-page/site/index.html` next to the existing
    `data-sample="triage"` button.
  - Must render, per Decision 5: the **span tree** (7.2), the **resolved
    citation** as a clickable help.ubuntu.com URL with its title, the **grounding
    check** result (green/red), and the **confidence score + escalation
    decision**. Must render the CC BY-SA 4.0 attribution wherever KB text is shown
    (Decision 2 / task 1.4). Match `landing-page/design.md` tokens; vanilla JS +
    Tailwind classes only, no framework — same constraints as `index.html`.
  - Points at `POST /tickets?include_trace=true` on a configurable base URL;
    falls back to a committed canned response JSON when the API is unreachable, so
    GitHub Pages works with no backend.
  - **Verify:** open `trial.html` locally, submit the seeded demo ticket, and
    confirm all four elements render; then stop the API and confirm the canned
    fallback still renders all four. Page usable at 360px width.
  - **After:** 7.2.

- **7.4** `PARALLEL` · haiku — Runnable local demo.
  - Creates: `src/triage/demo.py` (`python -m triage.demo`), README section.
  - Copy `spine.reference_agent.demo`: one scripted ticket, printing span tree,
    correlated logs, guardrail decisions, citations with URLs, proposed actions,
    escalation status, and `metrics_report(...).render()`.
  - Reuses: `spine.obs.metrics_report`, `spine.tracing.configure_tracing`,
    `spine.logging.get_logger`.
  - **Verify:** `uv run python -m triage.demo` exits 0 and prints all five
    sections; asserted by `tests/test_demo.py::test_demo_prints_full_trace`.
  - **After:** 7.1.

**Phase 7 exit:** `POST /tickets` returns a full traced result; the trial page
shows trace + citation + grounding + confidence for both a deflected and an
escalated ticket.

---

## Phase 8 — GCP cutover (deferred)

**Goal:** swap local defaults for GCP backends behind unchanged interfaces. **Do
not start** before Phases 0–7 are green and **Q4** is resolved. Every task here
is a constructor swap plus config, not a rewrite — if any task requires changing
a call site outside `triage/config.py` and the pipeline constructor, the earlier
phases got the seams wrong.

- **8.1** `SEQ` · sonnet — Real Gemini. Construct `spine.models_vertex.VertexModelClient`
  (currently defined but never instantiated anywhere in the repo) behind a
  `TRIAGE_MODEL_BACKEND` env switch, still wrapped in `WrappedModelClient`.
  **Verify:** the full local test suite passes unchanged with the fake backend;
  one manual live run produces a grounded answer and non-zero `cost_usd`.
- **8.2** `PARALLEL` · sonnet — Ingest `data/kb/ubuntu_docs.jsonl` into
  `spine.rag.VertexSearchRetriever`. **Verify:** the same 10 probe queries from
  Phase 1 return relevant passages; `resolve_citations` works (requires adding a
  `get` method to the adapter — `spine.rag.resolve_citations` raises
  `NotImplementedError` without it).
- **8.3** `PARALLEL` · sonnet — Firestore for state: `FirestoreSessionStore`,
  `MemoryBankStore`, `FirestoreEscalationStore`. Resolve **Q5** first — the
  collection naming encodes the tenancy model. **Verify:** an escalation survives
  a process restart.
- **8.4** `PARALLEL` · sonnet — `BigQueryMetricsSink` + `BigQueryResultSink`, and
  a Looker Studio dashboard over them: deflection rate, escalation rate, p50/p95
  latency, cost per ticket, grounding rate, tool error rate. **Verify:** the
  dashboard shows ≥ 100 real requests.
- **8.5** `SEQ` · opus — Real Terraform. `shared-infra/infra/*.tf` is a two-resource
  placeholder (a Cloud Run service and a staging bucket) that explicitly "cannot
  be applied". Add Firestore, Vertex AI Search datastore, BigQuery datasets,
  Pub/Sub, and per-environment workspaces. **Verify:** `terraform validate` and
  `terraform plan` succeed against a real dev project.
- **8.6** `PARALLEL` · haiku — Export to Cloud Trace / Cloud Logging via
  `spine.tracing.cloud_trace_exporter` and `spine.logging.cloud_logging_handler`.
  **Verify:** one request's span tree is visible in Cloud Trace with logs
  correlated by `trace_id`.

**Phase 8 exit:** one ticket flows end-to-end on GCP with the same
`TriageResult` shape as local, the CI gate still green, and the dashboards live.

---

## Parallelism map (for fan-out)

| Wave | Tasks | Notes |
| --- | --- | --- |
| 1 | 0.1 | Hard blocker for everything. |
| 2 | 0.2, 0.3, 0.4 | 0.3/0.4 need only 0.1. |
| 3 | 1.1, 2.1 | Phase 1 and Phase 2 are independent of each other. |
| 4 | 1.2, 2.2, 2.3 | |
| 5 | 1.3, 1.4, 2.4 | |
| 6 | 2.5, 3.1 | 3.1 needs 1.3 + 2.1. |
| 7 | 3.2, 4.1, 4.2, 4.3, 4.4, 4.6 | Tools only need Phase 1. |
| 8 | 3.3, 4.5 | |
| 9 | 3.4, 4.7, 5.1 | |
| 10 | 5.2, 6.1, 6.2 | |
| 11 | 5.3, 5.4, 6.3, 7.1 | Phase 7 may run alongside Phase 6. |
| 12 | 6.4, 7.2, 7.4 | |
| 13 | 6.5, 7.3 | |
| 14 | Phase 8 | Gated on **Q4**. |
