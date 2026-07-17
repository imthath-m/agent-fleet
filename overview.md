# Fleet — Company & Product Overview

## What Fleet is

**Fleet** is a software company that provides the AI agents a small business
needs to run its back office. Each agent takes over one operational job — the
recurring, headcount-eating work most SMBs and early startups do by hand — and
runs it as production software: evaluated, traced, and kept under human control.

An SMB **opts into any combination**: one agent, all of them, or any mix in
between. You add the agents that match the work you actually have, and add more
as we ship them. Everything runs on Google Cloud's AI stack.

Non-goal: toy demos that wrap a single LLM call. Every agent ships with the full
production picture — evaluation gates, tracing, structured logging,
observability, guardrails, human-in-the-loop, and cost/latency control.

## The five agents available today

Each covers one operational job. They stay exactly as designed; the platform
under them is shared.

1. **Triage** — support ticket triage & resolution. Answers routine tickets with
   cited answers from your own help docs, and hands the hard ones to a human.
2. **Payable** — AP / invoice processing. Reads every invoice, checks the math,
   catches duplicates, and only escalates the genuine exceptions.
3. **Prospect** — lead research & outreach. Researches each lead on the open web,
   scores it against your ICP, and drafts outreach you approve before it sends.
4. **Follow-Through** — meeting → action. Turns every meeting into owned, dated
   action items and remembers what was promised last week.
5. **Redline** — contract / compliance review. First-pass contract review against
   your own playbook; every flag cites the exact clause and the rule it breaks.
   (A review-assist tool, not legal advice — a human reviews every report.)

## Buy model: opt into any combination

- **Per-agent pricing.** Adopt Triage alone, Payable alone, or any subset.
- **Bundle discount** when an SMB takes all five.
- Onboarding is per agent: you wire it into your stack (helpdesk, ledger, CRM,
  tracker, contract folder) and go live on the ones you chose.

## One spine, many verticals — the shared platform

Fleet is built on **one shared platform spine** (the hard, transferable
engineering) and ships each agent as a thin **vertical** on top of it. This is
why we can offer five agents with the same production guarantees, and why new
agents ship faster than they would as standalone products.

- The spine owns the cross-cutting concerns: agent runtime, eval harness,
  tracing, logging, observability, guardrails, memory, and orchestration.
- Each vertical writes only its domain logic and inherits the platform's
  production guarantees unchanged.

```
                 ┌─────────────────────────────┐
                 │      SHARED PLATFORM (spine) │
                 │  runtime · eval · tracing ·  │
                 │  logging · observability ·   │
                 │  guardrails · memory · CI/CD │
                 └─────────────┬───────────────┘
        ┌──────────┬──────────┼──────────┬──────────┐
      Triage     Payable    Prospect  Follow-     Redline
      Support    Invoice     Lead     Through     Contract
      triage     (AP) ops    research  → action    review
```

## Why this is credible (engineering facts, true today)

Fleet's credibility comes from how the agents are built, not marketing claims:

- **Eval-gated releases.** Every agent ships with a versioned test suite of real
  cases; a release that scores worse than the last one is blocked from deploying.
- **Full audit trail.** Every step — every retrieval, decision, and action — is
  traced and logged, so "why did it do that?" always has an answer.
- **Human-in-the-loop by design.** Anything high-stakes (refunds, outbound
  email, contract findings) waits for a person; thresholds are enforced in code.
- **Runs on Google Cloud.** Gemini on Vertex AI, with per-customer data
  isolation.

## Google stack mapping (shared across all agents)

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

The five agents above are the starting lineup. Fleet's platform is built to
carry more, and the roadmap is to cover the rest of startup/SMB operations over
time.

- **Platform first.** The spine is built end-to-end with a reference agent that
  exercises every component (trace, log, eval, deploy).
- **The five agents** ship on the spine, each fully traced, evaluated, and
  observable, reusing the platform with zero duplicated infrastructure.
- **More agents to come.** New operational jobs become new verticals on the same
  spine — the same production guarantees, faster to ship each time.
- **One account.** Shared auth + billing across whatever combination a customer
  runs.

## Success criteria

- **Platform:** any new agent can be scaffolded, traced, evaluated, and deployed
  to GCP in under a day using shared libraries.
- **Every agent** ships with a versioned **eval suite** and a green CI gate that
  blocks deploys on regressions.
- **Every production request** is fully **traceable** (per-step spans) and
  **observable** (latency, cost, quality dashboards).
- **Onboarding:** a customer can adopt any agent and see it run end-to-end
  against their own systems.

## Repository layout

```
prod-agents/
├── overview.md              # this file
├── shared-infra/            # the platform spine — plan.md + spine/ library
├── support-agent/           # Triage — plan.md
├── invoice-agent/           # Payable — plan.md
├── lead-research-agent/     # Prospect — plan.md
├── meeting-action-agent/    # Follow-Through — plan.md
├── contract-review-agent/   # Redline — plan.md
└── landing-page/            # Fleet marketing site — plan/design/copy/signup
```
