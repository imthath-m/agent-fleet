# Evals

How the support agent is evaluated, where the golden data came from, what CI
gates, and what the numbers do and do not mean.

Status notes
- Every number below is read from a file in the repo (cited inline).
- Anything not documented in the repo is marked **unknown** or **unverified**.

## 1. Overview

Five suites, all built in `support-agent/src/triage/eval/suites.py`. The
metric classes come from `shared-infra/src/spine/eval/metrics.py` and
`support-agent/src/triage/eval/metrics.py`.

| Suite | Factory | Metrics (keys in the baseline) | Dataset |
| --- | --- | --- | --- |
| classification | `build_classification_suite` | `schema_pass_rate`, `field_accuracy` | `classification.jsonl` |
| resolution | `build_resolution_suite` | `grounding_rate`, `llm_judge`, `schema_pass_rate` | `resolution.jsonl` |
| actions | `build_actions_suite` | `tool_call_correctness`, `field_accuracy` | `actions.jsonl` |
| escalation | `build_escalation_suite` | `escalation_accuracy`, `escalation_precision`, `escalation_recall` | `escalation.jsonl` |
| triage | `build_triage_suite` | `grounding_rate`, `schema_pass_rate` | `resolution.jsonl` (reused) |

### What each metric measures

- `schema_pass_rate`: all required fields present in the output. No value check.
- `field_accuracy` (classification): mean over examples of the share of
  `intent`, `priority`, `product_area`, `sentiment` that exactly equal the label.
- `field_accuracy` (actions): exact match on `tool_errors` only.
- `grounding_rate`: 1.0 if the answer has at least one citation and every cited
  doc_id exists in the KB. It does **not** compare citations to
  `expected.citations` (`eval/metrics.py`). It checks the ids are real, not
  that they are the right docs.
- `llm_judge`: score 0..1 from a judge prompt comparing the answer to
  `expected.answer`. Fake judge in CI (section 5).
- `tool_call_correctness`: the set of tool names called equals the expected set
  (`ordered=False`). Argument values are not checked.
- `escalation_accuracy`: exact match on `expected.escalated`. Precision and
  recall come from a running confusion matrix lifted into `mean_scores`.

### Model-dependent vs rule-based (verified in code)

| Part | Source | Model-dependent? |
| --- | --- | --- |
| Classification labels | `classify()` parses the model's JSON | Yes |
| Answer text | `resolve()` model call | Yes |
| Citations | `passages_to_citations(retriever.query(...))` in `resolver.py` | No. Retriever output, not model output |
| `grounded` flag, `grounding_rate` | `check_grounding` against the KB | No. Model-independent |
| `retrieval_score` | `passages[0].score` | No (retriever). Depends on the query, which uses the classification's `product_area` |
| Tool calls | `plan_actions` in `actions.py`: regex/keyword rules on ticket text + `classification.intent`/`sentiment` + `resolution.grounded` | Indirect only, via the classification |
| Escalation | `should_escalate` in `escalation.py`: five rules (low confidence, ungrounded, high-risk tool, urgent priority, angry + high/urgent) | Indirect, via classification, `retrieval_score`, tool plan |
| `llm_judge` | Judge model | Yes |

Consequences
- `grounding_rate` cannot reflect model quality. A live model changes the
  answer text but not which docs are cited. It is a retriever/plumbing check.
- Actions and escalation scores move only when the classification (or the
  retriever) changes, not when answer prose changes.
- The escalation suite runs the whole `TriageAgent`. The actions suite runs
  classify, resolve, then `plan_actions`.
- The triage suite runs `TriageAgent` over the resolution set and scores only
  `grounding_rate` and `schema_pass_rate`. An escalated (withheld) ticket
  scores as an empty, uncited prediction (docstring in `suites.py`).

## 2. Golden sets

### Files and sizes

Header line (`schema_version`, `name`, `dataset_version`) plus one JSON row per
example. Counts are rows excluding the header (counted from the files).

| File | Rows | Expected fields | Tags |
| --- | --- | --- | --- |
| `support-agent/data/golden/classification.jsonl` | 18 | `intent`, `priority`, `product_area`, `sentiment` | 5 rows tagged `ported`; the rest are product-area / intent tags |
| `support-agent/data/golden/resolution.jsonl` | 18 | `answer` (reference text), `citations` (doc_ids) | product area only |
| `support-agent/data/golden/actions.jsonl` | 15 | `tool_calls` (list), `tool_errors` | `refund`, `high_risk`, `no_action`, `answerable`, ... |
| `support-agent/data/golden/escalation.jsonl` | 15 (7 `escalated: true`) | `escalated` | `answerable`, `refund`, `high_risk`, `hard_negative`, `off_corpus`, ... |

Row schema (`shared-infra/src/spine/eval/dataset.py`): `id`, `input`, `expected`,
optional `tags`. `input` is a full `Ticket` dict (`ticket_id`, `text`,
`channel`, `customer_id`, `subject`, `received_at`). All four headers have
`dataset_version` `"1"`.

Resolution `expected.citations` are present in the data but no metric reads
them (see `grounding_rate` above).

### Provenance: what the repo documents

From `git log -- support-agent/data/golden` (four commits, one per file) and
`tasks.md`:

| Set | Commit | Documented provenance |
| --- | --- | --- |
| classification | `e1fe0e3` (2.3) | First 5 rows ported from `shared-infra/src/spine/eval/data/support_resolution.jsonl` into the Q1 schema. The rest "hand-written Ubuntu support tickets" chosen so every value of `INTENTS`, `PRIORITIES`, `PRODUCT_AREAS`, `SENTIMENTS` appears at least once. "Labels are hand-assigned from the ticket text." |
| resolution | `f86ef12` (3.3) | Tickets across the six Ubuntu KB areas; `expected.answer` "is a reference written from the chunk that should answer the ticket", `expected.citations` the doc_ids it came from. The commit message says 18 tickets; the file has 18 rows. |
| actions | `410852b` (4.7) | Commit message does not say who wrote the labels. It explains `kb_search` is deliberately absent from every expected list. |
| escalation | `8531a33` (5.4) | "15 hand-labelled rows". The suite docstring says labels are "the human call ... written before any run". |

- None is generated from the synthetic ticket generator. `tasks.md` 6.3
  planned to draw expansion rows from it; that has not happened.
- Each of the four commit messages ends with a `Co-Authored-By:` trailer naming
  a Claude model. The messages call the labels "hand-labelled" or "hand-written".
  The repo does not say whether a person authored or reviewed each label, or
  whether a model drafted them.
- Not documented anywhere in the repo: who the labeller(s) were, whether any
  label was reviewed by a second person, any inter-annotator agreement, or any
  per-row sign-off. Treat labels as **unverified by an independent human**.
- `tasks.md` Q3 ("model-generated or hand-curated") is still listed as open and
  as blocking 6.3, with a recommendation of "generate inputs, hand-correct
  every `expected`". The docstring of `scripts/generate_tickets.py` says "Q3 was
  resolved to keep the Phase 2/3 golden sets at their current size". The two
  statements are inconsistent. Neither names a decision-maker or date.
- Some labels were observed against the fake pipeline while the suite was
  built (for example 5.4 reports measured precision/recall and calls
  `wifi-drops` a deliberate hard negative). Whether any label was changed to
  fit the fake is not recorded. **Unknown.**

### Known gaps

- Small n. The gate threshold is 0.01 (section 4). One example moves a
  per-example-mean metric by 1/n: 1/18 = 0.0556 for classification and
  resolution sets, 1/15 = 0.0667 for actions and escalation. The gate has no
  tolerance between "all identical" and "one example flipped".
- Classification `field_accuracy` averages 4 fields over 18 examples, so one wrong
  field moves it by 1/72 (about 0.0139), still above the 0.01 threshold.
- Escalation precision of 0.875 with recall 1.0 and 7 positives implies 8
  predicted positives (arithmetic, not stated in a file); one flip moves it
  by more than 0.01.
- Task 6.3 (expand every set to at least 60 rows with human-corrected labels,
  coverage test `tests/test_golden_coverage.py`) is marked "Not done" in
  `tasks.md`. `test_golden_coverage.py` does not exist. The Phase 6 exit
  criterion "at least 60 examples per golden set" is unmet.
- `README.md` says the sets are "under 20 cases each". That matches the counts.
- The tests assert only `len(dataset) >= 15` (`MIN_EXAMPLES` in
  `tests/test_eval_*.py`) plus an escalation-positive share between 0.2 and 0.5.
- Coverage that the data admits: `kb_search` never appears in expected tool
  lists; vague tickets are not caught by escalation (suite docstring); rule 2
  (ungrounded) never fires in the escalation set (5.4 commit message).

## 3. Ticket generation

`support-agent/scripts/generate_tickets.py`

- Deterministic and template-based. No model, no network. The docstring says
  tasks.md 6.1 allowed a model but "this project has no live model".
- Inputs: `data/kb/ubuntu_docs.jsonl` (382 chunks, counted) and
  `data/kb/MANIFEST.json` (slug to category).
- Method: a single `random.Random(seed)`; samples `n` chunks (cycles if
  `n` exceeds the corpus); for each, draws priority, sentiment, verbosity,
  ambiguity (`specific`/`vague`) and channel; builds text from fixed templates
  and a topic snippet taken from the chunk. `received_at` counts up from
  2026-01-01 by one minute per ticket (no wall clock).
- Output row: `ticket_id` (`GEN-0001`...), `text`, `channel`, `customer_id`,
  `subject`, `received_at`, `source_doc_id` (the sampled chunk, the intended
  citation), `profile` (the four drawn attributes).
- It writes **no** expected labels. `source_doc_id` is the only ground truth.
  "Specific" ticket text is a lowercased phrase lifted from the chunk, so it is
  formulaic, not realistic.
- Run (from `support-agent/`):
  `uv run python scripts/generate_tickets.py --seed 7 --n 80 [--out PATH]`
  Defaults: seed 7, n 80, out `data/generated/tickets.jsonl`.
- Committed output: `data/generated/tickets.jsonl`, 80 rows, from commit
  `e806e80` (6.1). The commit's `--seed`/`--n` are not recorded beyond the
  defaults and the task's verify line (`--seed 7 --n 80`).
- Consumption today: no eval suite, test or workflow reads
  `data/generated/tickets.jsonl` (the script docstring says the same). The only
  reader found is `scripts/judge_sheet.py` (section 5), for the judge-check pool.

## 4. CI gate

Workflow: `.github/workflows/support-agent-ci.yml` (and `spine-ci.yml` for the
shared library). It triggers on push and pull_request touching `support-agent/**`,
`shared-infra/**` or the workflow file. Python 3.11, `uv`, working dir
`support-agent`. Steps: `uv sync`, `uv run ruff check`, `uv run pytest`, then
five gates. No secrets or env vars are referenced.

```
uv run python -m spine.eval gate --suite triage.eval.suites:<factory> --baseline baselines/<name>.json
```

| Gate | Factory | Baseline |
| --- | --- | --- |
| classification | `build_classification_suite` | `baselines/classification.json` |
| resolution | `build_resolution_suite` | `baselines/resolution.json` |
| actions | `build_actions_suite` | `baselines/actions.json` |
| escalation | `build_escalation_suite` | `baselines/escalation.json` |
| triage | `build_triage_suite` | `baselines/triage.json` |

### Rule (`shared-infra/src/spine/eval/gate.py`)

- For each metric **in the baseline**: `delta = current - baseline`; fail if
  `delta < -threshold`. Default `DEFAULT_THRESHOLD = 0.01`; override with
  `--threshold`.
- A metric missing from the current run counts as `0.0`, so it fails.
- Metrics that exist only in the current run are not checked.
- Improvements never fail. Exit code 0 pass, 1 regression.
- There is no absolute floor in the gate. A baseline of 0.5 gates at 0.49.
- Absolute floors exist only in tests (`support-agent/tests/`):

| Test file | Floors |
| --- | --- |
| `test_eval_classification.py` | `MIN_FIELD_ACCURACY = 0.90`, `MIN_EXAMPLES = 15` |
| `test_eval_resolution.py` | `MIN_GROUNDING_RATE = 0.90`, `MIN_LLM_JUDGE = 0.70`, `MIN_EXAMPLES = 15` |
| `test_eval_actions.py` | `MIN_TOOL_CALL_CORRECTNESS = 0.90` (also applied to `field_accuracy`), `MIN_EXAMPLES = 15` |
| `test_eval_escalation.py` | `MIN_PRECISION = 0.80`, `MIN_RECALL = 0.90`, `MIN_EXAMPLES = 15`, positive share 0.2 to 0.5 |

  There are no floors for the triage suite (its `grounding_rate` baseline is
  below the 0.90 used for the resolution suite).

### Refresh a baseline

From `support-agent/`:

```
uv run python -m spine.eval baseline --suite triage.eval.suites:<factory> --out baselines/<name>.json
```

Then run the matching `gate` command, review the JSON diff, commit it. The
baseline file is just `dataset_name`, `dataset_version`, `mean_scores`.
Refreshing after a regression erases the signal, so the diff should be
explained in the commit message.

### Offline

CI runs entirely on `FakeModelClient` with the committed KB
(`data/kb/ubuntu_docs.jsonl`). No network, no API key, no GCP project. Live runs
are not part of CI (section 5).

## 5. Fake vs live

### What the fake model is

`support-agent/src/triage/fakes.py`; no model is called.

- `classifier_responder`: ordered regex alternations over signal words in the
  ticket text (for example `refund`/`invoice` give `billing`; `wifi`/`dns` give
  `networking`). First matching label wins; fallbacks are `other`, `normal`,
  `neutral`. Does not read ticket ids.
- `resolver_responder`: concatenates every retrieved passage into
  "Based on our documentation: ...". It does not reason; it copies the context.
- `resolution_judge_client` (the fake "LLM judge"): **keyword overlap**, not an
  LLM. Score = share of the reference answer's content words found in the
  answer, rounded to 3 places. Because the fake answer copies the retrieved
  context, `llm_judge` here measures whether retrieval surfaced the reference's
  words.
- Retrieval is an in-memory substring-scoring retriever over 382 chunks.

### What the fake baselines prove and do not prove

- They are a regression harness: they fail when pipeline plumbing, retrieval,
  rules, schemas or a fake responder change in a way that moves a score.
- They are **not** a quality measure of any language model. The fake and the
  labels were developed together in the same repo, so agreement is partly by
  construction.
- `llm_judge` 0.8486 is a keyword-overlap number. It says nothing about how a
  real judge would grade real answers.
- Rule-based parts (`plan_actions`, escalation rules, retriever, grounding) are
  real code under test, but only on 15 to 18 tickets.

### Fake baseline (committed, CI-gated)

Exact values from `support-agent/baselines/*.json`.

| Suite | Metric | Value | Source file |
| --- | --- | --- | --- |
| classification | `schema_pass_rate` | 1.0 | `baselines/classification.json` |
| classification | `field_accuracy` | 0.9722222222222222 | `baselines/classification.json` |
| resolution | `grounding_rate` | 1.0 | `baselines/resolution.json` |
| resolution | `llm_judge` | 0.8485555555555555 | `baselines/resolution.json` |
| resolution | `schema_pass_rate` | 1.0 | `baselines/resolution.json` |
| actions | `tool_call_correctness` | 1.0 | `baselines/actions.json` |
| actions | `field_accuracy` | 1.0 | `baselines/actions.json` |
| escalation | `escalation_accuracy` | 0.9333333333333333 | `baselines/escalation.json` |
| escalation | `escalation_precision` | 0.875 | `baselines/escalation.json` |
| escalation | `escalation_recall` | 1.0 | `baselines/escalation.json` |
| triage | `grounding_rate` | 0.5555555555555556 | `baselines/triage.json` |
| triage | `schema_pass_rate` | 1.0 | `baselines/triage.json` |

Reading the triage row: the 0.5556 follows from the suite design, in which
escalated tickets are withheld and scored as uncited. It is the pipeline's
"current behaviour", not a grounding failure (`build_triage_suite` docstring).
The 10/18 reading is arithmetic on the row count, not stated in a file.

### Live run

Code: `src/triage/eval/live.py`, `src/triage/eval/__main__.py`,
`shared-infra/src/spine/models_anthropic.py`. The live path is covered by offline
tests with a mocked transport and a stand-in client. No real API call has been
made yet (no key was available when this was written).

Run (from `support-agent/`):
  `uv run python scripts/generate_tickets.py --seed 7 --n 80 [--out PATH]`
  Defaults: seed 7, n 80, out `data/generated/tickets.jsonl`.
- Committed output: `data/generated/tickets.jsonl`, 80 rows, from commit
  `e806e80` (6.1). The commit's `--seed`/`--n` are not recorded beyond the
  defaults and the task's verify line (`--seed 7 --n 80`).
- Consumption today: no eval suite, test or workflow reads
  `data/generated/tickets.jsonl` (the script docstring says the same). The only
  reader found is `scripts/judge_sheet.py` (section 5), for the judge-check pool.

## 4. CI gate

Workflow: `.github/workflows/support-agent-ci.yml` (and `spine-ci.yml` for the
shared library). It triggers on push and pull_request touching `support-agent/**`,
`shared-infra/**` or the workflow file. Python 3.11, `uv`, working dir
`support-agent`. Steps: `uv sync`, `uv run ruff check`, `uv run pytest`, then
five gates. No secrets or env vars are referenced.

```
uv run python -m spine.eval gate --suite triage.eval.suites:<factory> --baseline baselines/<name>.json
```

| Gate | Factory | Baseline |
| --- | --- | --- |
| classification | `build_classification_suite` | `baselines/classification.json` |
| resolution | `build_resolution_suite` | `baselines/resolution.json` |
| actions | `build_actions_suite` | `baselines/actions.json` |
| escalation | `build_escalation_suite` | `baselines/escalation.json` |
| triage | `build_triage_suite` | `baselines/triage.json` |

### Rule (`shared-infra/src/spine/eval/gate.py`)

- For each metric **in the baseline**: `delta = current - baseline`; fail if
  `delta < -threshold`. Default `DEFAULT_THRESHOLD = 0.01`; override with
  `--threshold`.
- A metric missing from the current run counts as `0.0`, so it fails.
- Metrics that exist only in the current run are not checked.
- Improvements never fail. Exit code 0 pass, 1 regression.
- There is no absolute floor in the gate. A baseline of 0.5 gates at 0.49.
- Absolute floors exist only in tests (`support-agent/tests/`):

| Test file | Floors |
| --- | --- |
| `test_eval_classification.py` | `MIN_FIELD_ACCURACY = 0.90`, `MIN_EXAMPLES = 15` |
| `test_eval_resolution.py` | `MIN_GROUNDING_RATE = 0.90`, `MIN_LLM_JUDGE = 0.70`, `MIN_EXAMPLES = 15` |
| `test_eval_actions.py` | `MIN_TOOL_CALL_CORRECTNESS = 0.90` (also applied to `field_accuracy`), `MIN_EXAMPLES = 15` |
| `test_eval_escalation.py` | `MIN_PRECISION = 0.80`, `MIN_RECALL = 0.90`, `MIN_EXAMPLES = 15`, positive share 0.2 to 0.5 |

  There are no floors for the triage suite (its `grounding_rate` baseline is
  below the 0.90 used for the resolution suite).

### Refresh a baseline

From `support-agent/`:

```
uv run python -m spine.eval baseline --suite triage.eval.suites:<factory> --out baselines/<name>.json
```

Then run the matching `gate` command, review the JSON diff, commit it. The
baseline file is just `dataset_name`, `dataset_version`, `mean_scores`.
Refreshing after a regression erases the signal, so the diff should be
explained in the commit message.

### Offline

CI runs entirely on `FakeModelClient` with the committed KB
(`data/kb/ubuntu_docs.jsonl`). No network, no API key, no GCP project. Live runs
are not part of CI (section 5).

## 5. Fake vs live

### What the fake model is

`support-agent/src/triage/fakes.py`; no model is called.

- `classifier_responder`: ordered regex alternations over signal words in the
  ticket text (for example `refund`/`invoice` give `billing`; `wifi`/`dns` give
  `networking`). First matching label wins; fallbacks are `other`, `normal`,
  `neutral`. Does not read ticket ids.
- `resolver_responder`: concatenates every retrieved passage into
  "Based on our documentation: ...". It does not reason; it copies the context.
- `resolution_judge_client` (the fake "LLM judge"): **keyword overlap**, not an
  LLM. Score = share of the reference answer's content words found in the
  answer, rounded to 3 places. Because the fake answer copies the retrieved
  context, `llm_judge` here measures whether retrieval surfaced the reference's
  words.
- Retrieval is an in-memory substring-scoring retriever over 382 chunks.

### What the fake baselines prove and do not prove

- They are a regression harness: they fail when pipeline plumbing, retrieval,
  rules, schemas or a fake responder change in a way that moves a score.
- They are **not** a quality measure of any language model. The fake and the
  labels were developed together in the same repo, so agreement is partly by
  construction.
- `llm_judge` 0.8486 is a keyword-overlap number. It says nothing about how a
  real judge would grade real answers.
- Rule-based parts (`plan_actions`, escalation rules, retriever, grounding) are
  real code under test, but only on 15 to 18 tickets.

### Fake baseline (committed, CI-gated)

Exact values from `support-agent/baselines/*.json`.

| Suite | Metric | Value | Source file |
| --- | --- | --- | --- |
| classification | `schema_pass_rate` | 1.0 | `baselines/classification.json` |
| classification | `field_accuracy` | 0.9722222222222222 | `baselines/classification.json` |
| resolution | `grounding_rate` | 1.0 | `baselines/resolution.json` |
| resolution | `llm_judge` | 0.8485555555555555 | `baselines/resolution.json` |
| resolution | `schema_pass_rate` | 1.0 | `baselines/resolution.json` |
| actions | `tool_call_correctness` | 1.0 | `baselines/actions.json` |
| actions | `field_accuracy` | 1.0 | `baselines/actions.json` |
| escalation | `escalation_accuracy` | 0.9333333333333333 | `baselines/escalation.json` |
| escalation | `escalation_precision` | 0.875 | `baselines/escalation.json` |
| escalation | `escalation_recall` | 1.0 | `baselines/escalation.json` |
| triage | `grounding_rate` | 0.5555555555555556 | `baselines/triage.json` |
| triage | `schema_pass_rate` | 1.0 | `baselines/triage.json` |

Reading the triage row: the 0.5556 follows from the suite design, in which
escalated tickets are withheld and scored as uncited. It is the pipeline's
"current behaviour", not a grounding failure (`build_triage_suite` docstring).
The 10/18 reading is arithmetic on the row count, not stated in a file.

### Live run

Described per the spec for this PR. At the time of writing,
`scripts/error_analysis.py`, `scripts/judge_sheet.py` and
`scripts/judge_agreement.py` existed in the working tree. `src/triage/eval/live.py`,
a `triage.eval` `__main__.py` and `spine/models_anthropic.py` did **not** yet, so
the `--live` runner and model client below are described from the spec only and
are unverified. `error_analysis.py` also has an `--allow-fake` flag.

Run (from `support-agent/`):

```
ANTHROPIC_API_KEY=... uv run python -m triage.eval --live
```

- Runs all five suites on a real Claude model through an API-key client
  (`spine/models_anthropic.py`, plain httpx, no GCP project).
- Default model `claude-haiku-5-5`; `SPINE_LIVE_MODEL` overrides it. Cost comes
  from the price table in `models_anthropic.py`; an unpriced model gives
  `cost_usd: null`, never a guess.
- `temperature` is not sent to models that reject non-default sampling (the
  default model included), so live output is at the model's default temperature.
- A per-example failure (unparseable reply, API error) is recorded in the row's
  `error` field and scored 0; it does not stop the run.
- Without `--live` it runs the fake model and writes nothing.
- In live mode the resolution suite uses the real `LlmJudge` prompt
  (`DEFAULT_JUDGE_TEMPLATE`) with the live model, instead of the keyword fake.
- Output: `support-agent/results/<YYYY-MM-DD>/summary.json` plus
  `<suite>.jsonl` with per-example input, expected, prediction, metrics, error.
- Never written to `baselines/`. Live results are never gated against fake
  baselines. CI does not run live.

Error analysis:

```
uv run python scripts/error_analysis.py results/<date>
```

Writes `error_analysis.md`: per-suite scores, top failure patterns, up to 5
examples each.

Judge check (is the live judge any good?):

```
uv run python scripts/judge_sheet.py results/<date> --live
```

- `--target` (default 40) sets the size. Writes a 40-item `judge_sheet.csv`: 18 golden resolution items plus 22
  generated-ticket items judged against their source KB doc. Pool items never
  count toward suite scores.
- `--live` runs the generated tickets through classify, resolve and the real
  judge and saves `judge_pool.jsonl` (per the script docstring: calibration
  only).
- Judge scores are withheld into `judge_key.csv` to avoid anchoring the human.
- A human fills `human_score` (0, 0.25, 0.5, 0.75 or 1) and `human_pass`
  (`y`/`n`) per the rubric the script writes, then:

```
uv run python scripts/judge_agreement.py results/<date>
```

  prints agreement, Cohen's kappa and a confusion matrix.
- **Until the sheet is filled by a human there is no judge-validity number.**
  The judge is unvalidated.

### Live results

Separate from the fake table above. `NOT RUN` means no live run has been
recorded in this file.

<!-- LIVE_RESULTS_TABLE -->

| Suite | Metric | Live value |
| --- | --- | --- |
| classification | `schema_pass_rate` | NOT RUN |
| classification | `field_accuracy` | NOT RUN |
| resolution | `grounding_rate` | NOT RUN |
| resolution | `llm_judge` | NOT RUN |
| resolution | `schema_pass_rate` | NOT RUN |
| actions | `tool_call_correctness` | NOT RUN |
| actions | `field_accuracy` | NOT RUN |
| escalation | `escalation_accuracy` | NOT RUN |
| escalation | `escalation_precision` | NOT RUN |
| escalation | `escalation_recall` | NOT RUN |
| triage | `grounding_rate` | NOT RUN |
| triage | `schema_pass_rate` | NOT RUN |

Why the two tables are not directly comparable
- Different judge: keyword overlap (fake) vs a real model prompt (live).
- Different generators: the fake classifier and resolver are deterministic
  rules; a live model is non-deterministic (even at low temperature) and a
  single run is one sample.
- n is 15 to 18 per suite; one example moves a metric by 0.056 to 0.067.
- Do not read a live score as a regression against the fake baseline, or the
  reverse.

## 6. Known limitations

- Small n (15 to 18 per set). Differences under about 0.06 are one example.
- Gate sensitivity (0.01) is finer than the data resolution. Any single-example
  change fails the gate; the gate cannot express "within noise".
- Golden labels: no documented independent human review (section 2). Some
  commits say hand-labelled and carry a model co-author trailer; the actual
  authorship is **unknown**.
- Fake baselines are a plumbing check, not quality. They were tuned alongside the
  same sets.
- Judge: fake judge is keyword overlap. The live judge is unvalidated until a
  human completes the judge sheet.
- Live results are single-run and non-deterministic; no repeat-run variance
  estimate exists.
- `grounding_rate` is model-independent (verified in code): citations come from
  the retriever and grounding checks the ids exist. It will not move with the
  model, and does not check the cited docs are the right ones.
- Actions and escalation depend on the model only via the classification.
- Sets under 60 rows, task 6.3 not done, Q3 inconsistently recorded.
- Generated tickets have no labels and are not consumed by any suite today.
