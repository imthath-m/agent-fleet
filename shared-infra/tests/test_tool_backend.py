from fastapi.testclient import TestClient

from spine.tool_backend import app

client = TestClient(app)


def test_hello_default():
    resp = client.get("/tools/hello")
    assert resp.status_code == 200
    assert resp.json() == {"message": "hello, world"}


def test_hello_named():
    resp = client.get("/tools/hello", params={"name": "spine"})
    assert resp.status_code == 200
    assert resp.json() == {"message": "hello, spine"}


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
