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

## Agent design (multi-agent via A2A)

```
        inbound ticket
             │
      ┌──────▼───────┐
      │  Classifier  │  intent, priority, product area, sentiment
      └──────┬───────┘
             │ A2A handoff
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
- **Resolver agent** — retrieves from the product's **Vertex AI Search** KB
  datastore, produces a grounded, cited answer.
- **Action agent** — ADK tools calling the SMB's systems (order lookup, refund,
  CRM update). Actions are **idempotent** and guarded.
- Handoffs use **A2A**; every hop is traced.

## Tools (Cloud Run backends)

- `kb_search` — query the product's Vertex AI Search datastore.
- `order_lookup` — read order/customer status (mock adapter first, real
  integrations per customer).
- `issue_refund` — high-risk; requires confidence + policy check, else HITL.
- `crm_update` — write resolution + tags back to CRM.

All tools validate inputs, are idempotent, and emit trace spans + structured logs
via the spine.

## Data & memory

- **Firestore**: ticket state, conversation, escalation status.
- **Vertex Memory Bank**: per-customer history so repeat contacts have context.
- **Vertex AI Search datastore**: the SMB's help-center/KB articles, ingested via
  `spine/rag.py`.

## Guardrails & HITL

- Input: PII redaction, prompt-injection heuristics (untrusted ticket text).
- Output: answer must be grounded (citation check) or it won't auto-send.
- Confidence gate: below threshold → draft-only + human queue.
- High-risk actions (refunds, account changes) → always HITL unless within an
  auto-approve policy the customer configures.

## Evaluation (uses `spine/eval/`)

Golden dataset: real-ish tickets → expected classification, expected resolution,
expected action.

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

- Ingest: email (Gmail/IMAP), webform webhook, and a generic REST endpoint.
- KB: upload docs or point at an existing help center.
- CRM: start with one (e.g. HubSpot or Zendesk) via adapter; add more per demand.

## Build phases

1. **Classifier only** on the spine — traced, logged, with an eval set. Verify:
   classification metrics reported in CI + dashboard.
2. **Resolver + RAG** — ingest a sample KB, grounded cited answers. Verify:
   grounding rate measured; hallucinations caught by the gate.
3. **Action agent + tools** — mock adapters, idempotent, guarded. Verify:
   tool-call correctness in eval; high-risk actions route to HITL.
4. **HITL + confidence gating** — human queue UI (minimal) + escalation flow.
   Verify: low-confidence tickets escalate; precision/recall tracked.
5. **End-to-end demo** — one real inbox → resolution or escalation, fully traced
   and observable. Verify: a prospect can watch a ticket flow through live.

## Definition of done

- A ticket flows ingest → classify → resolve → act/escalate, **fully traced,
  logged, and observable**, with a **green eval gate** in CI.
- Demoable end-to-end against a sample SMB inbox + KB.
- Reuses the spine with **zero** duplicated cross-cutting infrastructure.
