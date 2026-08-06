"""REST ingestion endpoint: the single surface a ticket enters over HTTP.

Mirrors `spine.tool_backend` / `triage.tool_backend` conventions: one FastAPI
app built at module scope, pydantic request models, `/healthz` returning
`{"status": "ok"}`. Email/webform intake from plan.md is explicitly
out of scope — a generic REST endpoint is the single ingestion surface until a
customer needs more.

One `TriageAgent` is built at import time and reused for every request:
its defaults call `load_kb()` (382 rows) per instance, so constructing one per
request would reload the whole corpus on every ticket. `GET /queue` reads the
same `HumanQueue` instance `POST /tickets` writes to, since `HumanQueue` is
in-memory and process-local (there is exactly one worker process behind this
app; Decision 6 is local-first, not concurrent-safe).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from spine.tracing import configure_tracing

from triage.pipeline import TriageAgent
from triage.schemas import Ticket
from triage.trace_view import span_tree

app = FastAPI(title="triage-api", version="0.1.0")
# A provider from app start, so every response carries a real trace_id (spans
# go nowhere without one configured). `?include_trace=true` reconfigures with a
# fresh exporter right before that one run, so its tree is exactly that
# request's spans — safe here because this app is single-process and requests
# are handled sequentially (Decision 6: local-first, not built for concurrency).
configure_tracing(service_name="triage-api")
_agent = TriageAgent()


class TicketRequest(BaseModel):
    text: str
    subject: str = ""
    channel: str = "webform"
    customer_id: str = "anonymous"
    ticket_id: str | None = None
    received_at: str | None = None


class ResolveRequest(BaseModel):
    note: str


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tickets")
def create_ticket(body: TicketRequest, include_trace: bool = False) -> dict[str, Any]:
    # Reconfigure with a fresh exporter right before this run, so its finished
    # spans are exactly (and only) this request's tree.
    exporter = configure_tracing(service_name="triage-api") if include_trace else None

    ticket = Ticket(
        ticket_id=body.ticket_id or f"TK-{uuid.uuid4().hex[:8]}",
        text=body.text,
        channel=body.channel,
        customer_id=body.customer_id,
        subject=body.subject,
        received_at=body.received_at or datetime.now(UTC).isoformat(),
    )
    result = _agent.run(ticket)
    payload = result.to_dict()
    if exporter is not None:
        payload["trace"] = span_tree(exporter)
    return payload


@app.get("/queue")
def list_queue() -> list[dict[str, Any]]:
    """Pending escalations, in the shape `triage.pipeline.escalation_payload`
    builds — `id`/`status`/`reason` from the queue item, the rest from its
    payload (trace id, ticket text, draft answer, citations, proposed actions)."""
    return [
        {"id": item.id, "status": item.status, "reason": item.reason, **item.payload}
        for item in _agent.hitl.pending()
    ]


@app.post("/queue/{item_id}/resolve")
def resolve_queue_item(item_id: str, body: ResolveRequest) -> dict[str, Any]:
    try:
        item = _agent.hitl.resolve(item_id, resolution=body.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": item.id, "status": item.status, "resolution": item.resolution}
