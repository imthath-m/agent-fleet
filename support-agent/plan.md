# Support Ticket Triage & Resolution Agent

One of Fleet's agents. It has the broadest SMB market and exercises **every**
component of the shared platform.

> This project builds **on top of `shared-infra/`**. It does not re-implement
> runtime, eval, tracing, logging, observability, guardrails, memory, or CI/CD —
> it imports `spine/` and adds only the domain logic below.

## What it does

Ingests an inbound support ticket (email/webform/chat), classifies it, drafts or
executes a resolution grounded in the company's knowledge base, takes safe
actions via tools, and escalates to a human when it isn't confident.

## Target buyer

Any SMB with a support inbox and a help center but no large support team. Value
prop: deflect routine tickets, cut first-response time, keep humans for the hard
cases — with full auditability.

## Agent design (sequential in-process chain)

```
        inbound ticket
             │
      ┌──────▼───────┐
      │  Classifier  │  intent, priority, product area, sentiment
      └──────┬───────┘
             │ handoff
      ┌──────▼───────┐
      │   Resolver   │  RAG over KB → grounded answer w/ citations
      └──────┬───────┘
             │
      ┌──────▼───────┐
      │  Action agent│  tools: refund, order lookup, CRM update, KB search
      └──────┬───────┘
             │ confidence gate / high-risk?
      ┌──────▼───────┐
      │ HITL escalate│  → human queue when unsure or high-risk
      └──────────────┘
```

- **Classifier agent** — Gemini structured output: intent, priority, product
  area, sentiment, PII flag.
- **Resolver agent** — retrieves from the KB via `spine/rag.py`, produces a
  grounded, cited answer.
- **Action agent** — tools calling the SMB's systems (order lookup, refund,
  CRM update). Actions are **idempotent** and guarded. Pre-sale they are mock
  adapters that only ever *propose* an action — nothing is executed.
- Handoffs are plain sequential function calls in one process; every hop is
  traced. A2A is deferred until a second agent actually needs a wire protocol.

## Tools

- `kb_search` — query the KB retriever.
- `order_lookup` — read order/customer status (fixture store first, real
  integrations per customer).
- `issue_refund` — high-risk; always routed to HITL as a proposed action.
- `crm_update` — propose resolution + tags for a CRM write; never writes
  pre-sale.

All tools validate inputs, are idempotent, and emit trace spans + structured logs
via the spine.

## Data & memory

Local-first: the in-memory spine stores are the default, and the GCP backends
below sit behind the same interfaces, swapped in during the GCP cutover phase.

- **Session/ticket state**: `spine.memory` stores → Firestore later.
- **Per-customer history** so repeat contacts have context: `spine.memory` →
  Vertex Memory Bank later.
- **KB articles**: help.ubuntu.com docs (CC BY-SA 4.0) for the demo corpus,
  ingested via `spine/rag.py` → Vertex AI Search datastore later.

## Guardrails & HITL

- Input: PII redaction, prompt-injection heuristics (untrusted ticket text).
- Output: answer must be grounded (citation check) or it won't auto-send.
- Confidence gate: below threshold → draft-only + human queue.
- High-risk actions (refunds, account changes) → always HITL unless within an
  auto-approve policy the customer configures.

## Evaluation (uses `spine/eval/`)

Golden dataset: tickets synthesized from real KB chunks → expected
classification, expected resolution, expected action.

Metrics:
- **Classification accuracy / F1** (deterministic).
- **Resolution correctness** (LLM-as-judge vs. expected answer).
- **Hallucination / grounding rate** (citation validity check).
- **Escalation precision & recall** (did it escalate the ones it should?).
- **Tool-call correctness** (right tool, right args).
- **Cost & latency per ticket**.

CI gate blocks deploy on regression against the baseline. Sampled production
tickets are judged online and folded back into the golden set.

## Observability (uses `spine/obs.py`)

Dashboards: deflection rate, escalation rate, p50/p95 latency, cost per ticket,
grounding rate over time, tool error rate, CSAT proxy. Alerts on quality
regression, cost spikes, and error-rate SLO breaches.

## Integrations (go-to-market)

- Ingest: a generic REST endpoint first; email (Gmail/IMAP) and webform webhook
  after.
- KB: upload docs or point at an existing help center.
- CRM: read-only and drafts-only pre-sale — no customer system is written to
  until someone has bought. Which CRM to adapt first stays open until a
  customer names one.

## Build phases

See **[`tasks.md`](./tasks.md)** for the executable decomposition — fixed
decisions, open questions, and 43 numbered tasks across these phases with
per-task verification criteria and a parallelism map.

0. **Scaffold** — package, config, CI job.
1. **KB ingestion** — real Ubuntu docs, chunked and attributed.
2. **Classifier** — structured output, schema-guarded, eval metrics.
3. **Resolver + RAG** — grounded cited answers; grounding rate measured.
4. **Action agent + tools** — mock adapters, idempotent, guarded, drafts-only.
5. **Pipeline + HITL + confidence gating** — human queue UI (minimal).
6. **Golden set + CI eval gate** — regression gate blocks deploy.
7. **Ingestion surface + landing-page trial** — a prospect watches a ticket flow
   through live, with the trace, citation, and escalation decision visible.
8. **GCP cutover (deferred)** — real Gemini, Vertex AI Search, Firestore,
   BigQuery dashboards, real Terraform.

## Definition of done

- A ticket flows ingest → classify → resolve → act/escalate, **fully traced,
  logged, and observable**, with a **green eval gate** in CI.
- Demoable end-to-end against a sample SMB inbox + KB.
- Reuses the spine with **zero** duplicated cross-cutting infrastructure.
