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

app = FastAPI(title="triage-api", version="0.1.0")
# One provider for the app's life, so every response carries a real trace_id
# (spans go nowhere without a configured provider). 7.2 reads this same
# exporter's finished spans back for `include_trace`.
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
def create_ticket(body: TicketRequest) -> dict[str, Any]:
    ticket = Ticket(
        ticket_id=body.ticket_id or f"TK-{uuid.uuid4().hex[:8]}",
        text=body.text,
        channel=body.channel,
        customer_id=body.customer_id,
        subject=body.subject,
        received_at=body.received_at or datetime.now(UTC).isoformat(),
    )
    result = _agent.run(ticket)
    return result.to_dict()


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
