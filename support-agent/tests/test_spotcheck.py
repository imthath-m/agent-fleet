"""Smoke test over real, unmodified Ask Ubuntu questions (Decision 3: spot-check
fixtures only, never golden labels — no `expected` field exists to assert
against). One `TriageAgent` is constructed once and reused across all ten rows
(`load_kb()` seeds 382 rows per instance).
"""

import json
from pathlib import Path

from triage.pipeline import TriageAgent
from triage.schemas import Ticket, TriageResult

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "fixtures" / "askubuntu_spotcheck.jsonl"
)


def _load_fixtures() -> list[dict]:
    return [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line.strip()]


def _ticket(row: dict) -> Ticket:
    return Ticket(
        ticket_id=row["id"],
        text=f"{row['title']}. {row['excerpt']}",
        channel="web_form",
        customer_id=f"spotcheck-{row['id']}",
        subject=row["title"],
        received_at="2026-01-01T00:00:00Z",
    )


def test_real_questions_do_not_crash():
    rows = _load_fixtures()
    assert len(rows) == 10  # noqa: S101 -- plain assert is this repo's test convention

    agent = TriageAgent()
    for row in rows:
        result = agent.run(_ticket(row))
        assert isinstance(result, TriageResult)  # noqa: S101
        # Delivered (not withheld) means the answer went out, so it had better
        # be grounded — an ungrounded delivered answer is exactly what
        # Phase 3's grounding check and Phase 5's escalation policy exist to
        # prevent. (Note from Phase 4: the substring retriever marks almost
        # anything `grounded=True`, so this is easy to pass — a property of
        # the retriever, not proof of answer quality.)
        if not result.withheld:
            assert result.resolution is not None  # noqa: S101
            assert result.resolution.grounded is True  # noqa: S101
