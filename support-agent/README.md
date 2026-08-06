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

## Demo

`python -m triage.demo` runs one scripted ticket (an escalated refund
request) through the whole pipeline, no API or network required, and prints
five sections: the span tree, correlated JSON logs, guardrail decisions, the
result (answer, grounded citations with their real help.ubuntu.com URLs,
proposed actions, escalation status), and a metrics summary.

```sh
uv run python -m triage.demo
```

## Attribution

The demo knowledge base (`data/kb/ubuntu_docs.jsonl`) is sourced from the
[Ubuntu Community Help Wiki](https://help.ubuntu.com/community/), licensed
under **CC BY-SA 4.0** (https://creativecommons.org/licenses/by-sa/4.0/). See
[`data/kb/ATTRIBUTION.md`](data/kb/ATTRIBUTION.md) for full details and the
display obligation for any surface showing KB text.
