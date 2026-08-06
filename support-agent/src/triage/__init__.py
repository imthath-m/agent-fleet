"""triage — support-ticket triage agent built on the spine platform.

Classifier -> Resolver -> Action as a plain sequential pipeline over
`spine.*` (tracing, guardrails, RAG, HITL, eval). See `support-agent/tasks.md`
for the phase-by-phase build plan.
"""

__version__ = "0.1.0"
