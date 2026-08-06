from spine.hitl import HumanQueue
from spine.rag import Document, InMemoryRetriever

from triage import config
from triage.review import main

PAYLOAD = {
    "trace_id": "0af7651916cd43dd8448eb211c80319c",
    "ticket_id": "TK-5101",
    "ticket_text": "Charged twice for ORD-1001. Please refund $49.00 of it.",
    "draft_answer": "Refunds are issued to the original payment method.",
    "citations": ["Refunds#0", "not-a-real-doc#0"],
    "proposed_actions": [
        {
            "tool": "issue_refund",
            "args": {"order_id": "ORD-1001", "amount": 49.0},
            "idempotency_key": "k",
            "risk": "high",
            "executed": False,
        }
    ],
}


def _retriever() -> InMemoryRetriever:
    retriever = InMemoryRetriever()
    retriever.ingest(
        config.KB_NAMESPACE,
        Document(
            doc_id="Refunds#0",
            text="Refunds are issued to the original payment method.",
            source="https://help.ubuntu.com/community/Refunds",
            metadata={
                "title": "Refunds",
                "url": "https://help.ubuntu.com/community/Refunds",
                "license": "CC BY-SA 4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            },
        ),
    )
    return retriever


def test_list_show_resolve_round_trip(capsys):
    queue = HumanQueue()
    item = queue.enqueue(reason="high-risk action proposed: issue_refund", payload=PAYLOAD)

    assert main(["list"], queue=queue) == 0
    listed = capsys.readouterr().out
    assert item.id in listed
    assert "TK-5101" in listed
    assert "issue_refund" in listed

    assert main(["show", item.id], queue=queue, retriever=_retriever()) == 0
    shown = capsys.readouterr().out
    assert PAYLOAD["trace_id"] in shown
    assert PAYLOAD["draft_answer"] in shown
    # Citations carry their real source URL and licence (Decision 2).
    assert "https://help.ubuntu.com/community/Refunds" in shown
    assert "CC BY-SA 4.0" in shown
    assert "UNRESOLVED" in shown  # the fabricated id is named as such
    assert "risk=high" in shown
    assert "awaiting approval" in shown

    assert main(["resolve", item.id, "--note", "approved, refund issued"], queue=queue) == 0
    assert "approved, refund issued" in capsys.readouterr().out
    assert queue.pending() == []
    assert queue.store.get(item.id).resolution == "approved, refund issued"


def test_empty_queue_lists_nothing(capsys):
    assert main(["list"], queue=HumanQueue()) == 0
    assert capsys.readouterr().out.strip() == "queue empty"


def test_unknown_id_is_an_error(capsys):
    assert main(["show", "nope"], queue=HumanQueue()) == 1
    assert "nope" in capsys.readouterr().err
