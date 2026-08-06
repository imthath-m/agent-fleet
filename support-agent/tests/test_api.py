from fastapi.testclient import TestClient

from triage.api import app

client = TestClient(app)


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --------------------------------------------------------------------------- #
# POST /tickets — a deflected ticket
# --------------------------------------------------------------------------- #


def test_post_ticket_returns_grounded_answer():
    resp = client.post(
        "/tickets",
        json={
            "text": "I need to add a new user account on Ubuntu and put that username in a group.",
            "subject": "How do I add a user to a group?",
            "customer_id": "cust-api-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"]
    assert body["classification"]["product_area"] == "users_permissions"
    assert body["resolution"]["citations"]
    assert body["withheld"] is False
    assert body["escalation"] is None


# --------------------------------------------------------------------------- #
# POST /tickets — an escalated (high-risk) ticket, and the queue it lands in
# --------------------------------------------------------------------------- #


def test_refund_ticket_escalates_and_appears_in_queue():
    resp = client.post(
        "/tickets",
        json={
            "text": "My card was charged twice for order ORD-1001. Please refund $49.00 of it.",
            "subject": "Charged twice for ORD-1001",
            "customer_id": "cust-api-2",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["withheld"] is True
    assert body["escalation"] is not None
    escalation_id = body["escalation"]["id"]

    queue = client.get("/queue").json()
    matches = [item for item in queue if item["id"] == escalation_id]
    assert len(matches) == 1
    assert matches[0]["ticket_id"] == body["ticket"]["ticket_id"]
    assert matches[0]["trace_id"] == body["trace_id"]


def test_resolve_removes_item_from_queue():
    resp = client.post(
        "/tickets",
        json={
            "text": "URGENT: production server is down, need help immediately.",
            "subject": "Server down",
            "customer_id": "cust-api-3",
        },
    )
    escalation_id = resp.json()["escalation"]["id"]

    resolved = client.post(f"/queue/{escalation_id}/resolve", json={"note": "handled by hand"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    queue = client.get("/queue").json()
    assert all(item["id"] != escalation_id for item in queue)


def test_resolve_unknown_id_is_404():
    resp = client.post("/queue/does-not-exist/resolve", json={"note": "n/a"})
    assert resp.status_code == 404
