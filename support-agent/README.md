# triage (support-agent)

A support-ticket triage agent: Classifier -> Resolver -> Action, composed as a
plain sequential pipeline over [`spine`](../shared-infra), the shared
agentic-AI platform library. Runs entirely on in-memory fakes — no GCP creds,
no network — until Phase 8.

See [`tasks.md`](tasks.md) for the phase-by-phase build plan and
[`plan.md`](plan.md) for the product spec.

## Install

Requires Python 3.11 and [`uv`](https://docs.astral.sh/uv/). From
`support-agent/`:

```sh
uv sync
uv run pytest
uv run ruff check
```
