"""Local tool backend for the triage agent (the Cloud Run target in Phase 8).

Mirrors `spine.tool_backend`'s conventions: one `FastAPI` app built at module
scope, pydantic response models, `/healthz` returning `{"status": "ok"}`, and
one route per tool.

The two high-risk routes are `POST` because drafting a refund or a CRM note is
a request to *consider* an effect, not a lookup — but they still cause none:
they return the same `ProposedAction(executed=False)` the in-process tool
returns. There is nothing behind this app that can write.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from triage import tools

app = FastAPI(title="triage-tool-backend", version="0.1.0")


class KbSearchResponse(BaseModel):
    passages: list[dict[str, Any]]


class OrderLookupResponse(BaseModel):
    found: bool
    order: dict[str, Any] | None = None


class ProposedActionResponse(BaseModel):
    tool: str
    args: dict[str, Any]
    idempotency_key: str
    risk: str
    executed: bool


class IssueRefundRequest(BaseModel):
    order_id: str
    amount: float
    reason: str


class CrmUpdateRequest(BaseModel):
    ticket_id: str
    resolution_summary: str
    tags: list[str] = []


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools/kb_search", response_model=KbSearchResponse)
def kb_search(query: str, top_k: int = 4) -> KbSearchResponse:
    """Search the Ubuntu KB. Read-only."""
    return KbSearchResponse(passages=tools.kb_search(query, top_k))


@app.get("/tools/order_lookup", response_model=OrderLookupResponse)
def order_lookup(order_id: str) -> OrderLookupResponse:
    """Look up one order. Read-only; an unknown id is a 200 with `found=false`."""
    result = tools.order_lookup(order_id)
    if not result["found"]:
        return OrderLookupResponse(found=False)
    return OrderLookupResponse(found=True, order=result)


@app.post("/tools/issue_refund", response_model=ProposedActionResponse)
def issue_refund(body: IssueRefundRequest) -> ProposedActionResponse:
    """Draft a refund for human approval. Never executes one."""
    return _draft(lambda: tools.issue_refund(body.order_id, body.amount, body.reason))


@app.post("/tools/crm_update", response_model=ProposedActionResponse)
def crm_update(body: CrmUpdateRequest) -> ProposedActionResponse:
    """Draft a CRM record update for human approval. Never executes one."""
    return _draft(lambda: tools.crm_update(body.ticket_id, body.resolution_summary, body.tags))


def _draft(build) -> ProposedActionResponse:
    """Serialize a drafted action, turning a tool's refusal into a 400.

    A `ValueError` from a tool is bad input (a negative amount, an unknown
    order), not a server fault, so it must not read as a 500 in the logs.
    """
    try:
        action = build()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProposedActionResponse(**action.to_dict())
