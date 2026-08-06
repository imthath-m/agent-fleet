from fastapi.testclient import TestClient

from triage.tool_backend import app
from triage.tools.order_lookup import ORDERS_PATH

client = TestClient(app)


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --------------------------------------------------------------------------- #
# Read-only routes
# --------------------------------------------------------------------------- #


def test_kb_search_route():
    resp = client.get("/tools/kb_search", params={"query": "add a user to a group", "top_k": 2})
    assert resp.status_code == 200
    passages = resp.json()["passages"]
    assert 0 < len(passages) <= 2
    assert set(passages[0]) == {"doc_id", "text", "source", "score"}


def test_order_lookup_route_known_and_unknown():
    known = client.get("/tools/order_lookup", params={"order_id": "ORD-1001"})
    assert known.status_code == 200
    assert known.json()["found"] is True
    assert known.json()["order"]["order_id"] == "ORD-1001"

    unknown = client.get("/tools/order_lookup", params={"order_id": "ORD-9999"})
    assert unknown.status_code == 200
    assert unknown.json() == {"found": False, "order": None}


# --------------------------------------------------------------------------- #
# Drafting routes — high risk, still no effect
# --------------------------------------------------------------------------- #


def test_issue_refund_route_drafts_only():
    before = ORDERS_PATH.read_bytes()

    resp = client.post(
        "/tools/issue_refund",
        json={"order_id": "ORD-1001", "amount": 49.0, "reason": "duplicate charge"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "issue_refund"
    assert body["risk"] == "high"
    assert body["executed"] is False
    assert body["idempotency_key"]
    assert ORDERS_PATH.read_bytes() == before


def test_crm_update_route_drafts_only():
    resp = client.post(
        "/tools/crm_update",
        json={
            "ticket_id": "TK-5001",
            "resolution_summary": "Reset the password from recovery mode.",
            "tags": ["account", "high"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "crm_update"
    assert body["risk"] == "high"
    assert body["executed"] is False


def test_a_tool_refusal_is_a_400_not_a_500():
    resp = client.post(
        "/tools/issue_refund",
        json={"order_id": "ORD-9999", "amount": 49.0, "reason": "no such order"},
    )
    assert resp.status_code == 400
    assert "unknown order_id" in resp.json()["detail"]
