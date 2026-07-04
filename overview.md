# Production Agents — Program Overview

## Why we're building this

Primary goal: **learn production-grade agentic AI system design** deeply enough
to be credible in **Forward Deployed Engineer (FDE)** interviews and on the job.
Most target companies run on **GCP**, so everything deploys on the Google stack
and leans on Google's agent tooling (**Gemini on Vertex AI, ADK, A2A, Agent
Engine, Vertex Evaluation, Document AI, Cloud Trace/Logging, BigQuery**).

Secondary goal: each project is a **real, sellable product** for SMBs and early
startups. We list them on one landing page. If a buyer shows up, great. If not,
the portfolio + learning stands on its own.

Non-goal: toy demos that wrap a single LLM call. Every project must have the
full production picture — evaluation, tracing, logging, observability, guardrails,
human-in-the-loop, and cost/latency control.

## Core strategy: one spine, many verticals

We build **one shared platform spine** (the hard, transferable engineering) and
ship each product as a thin **vertical** on top of it.

- The spine is where 60% of the learning lives: eval harness, tracing, logging,
  observability, agent runtime, guardrails, memory, orchestration.
- Each vertical proves the spine is reusable and becomes an independent product.

```
                 ┌─────────────────────────────┐
                 │      SHARED INFRA (spine)    │
                 │  runtime · eval · tracing ·  │
                 │  logging · observability ·   │
                 │  guardrails · memory · CI/CD │
                 └─────────────┬───────────────┘
        ┌──────────┬──────────┼──────────┬──────────┐
      Project1   Project2   Project3   Project4   Project5
      Support    Invoice     Lead       Meeting    Contract
      triage     (AP) ops    research   → action   review
```

## The five products (sellability-ranked)

1. **Support ticket triage & resolution agent** — build first. Easiest to demo,
   broadest SMB market, exercises every spine component.
2. **AP / invoice-processing agent** — Document AI + deterministic validation +
   agentic exception handling. High willingness to pay.
3. **Lead research & outreach agent** — web-grounded enrichment, scoring, drafts.
4. **Meeting → action agent** — async Pub/Sub pipeline, cross-session memory.
5. **Contract / compliance review agent** — high-stakes eval, citation grounding.

## Google stack mapping (shared across all)

| Concern            | Component                                   |
|--------------------|---------------------------------------------|
| Model              | Gemini on Vertex AI                         |
| Agent framework    | ADK (Agent Development Kit)                  |
| Multi-agent        | A2A protocol                                 |
| Managed runtime    | Vertex AI Agent Engine (or Cloud Run)       |
| RAG / grounding    | Vertex AI Search / RAG Engine               |
| Doc extraction     | Document AI                                  |
| Eval               | Vertex AI Evaluation + custom LLM-as-judge  |
| Tracing            | OpenTelemetry → Cloud Trace                 |
| Logging            | Cloud Logging (structured per step)         |
| Observability      | spans + evals → BigQuery → Looker           |
| Async orchestration| Pub/Sub + Cloud Tasks                       |
| State / memory     | Firestore + Vertex Memory Bank              |

## Roadmap

1. **Phase 0** — Build the spine end-to-end with a trivial reference agent that
   exercises every component (trace, log, eval, deploy).
2. **Phase 1** — Build **Project One** (support triage) on the spine. This is the
   real proof of the platform.
3. **Phase 2** — Clone the spine for Project Two; prove reusability + second sale.
4. **Phase 3+** — Add Projects 3–5 as appetite holds.
5. **Landing page** — single site listing all products, shared auth + billing.

## Success criteria

- Spine: any new agent can be scaffolded, traced, evaluated, and deployed to GCP
  in under a day using shared libraries.
- Each product ships with a versioned **eval suite** and a green CI gate that
  blocks deploys on regressions.
- Every production request is fully **traceable** (per-step spans) and
  **observable** (latency, cost, quality dashboards).
- At least one product is demoable to a real prospect end-to-end.

## Repository layout

```
prod-agents/
├── overview.md       # this file
├── shared-infra/     # the spine — plan.md here
├── support-agent/    # support triage agent (Project One) — plan.md here
└── ...               # project-two/ etc. added later
```
