"""Deterministic synthetic ticket generator.

Reads the committed `data/kb/ubuntu_docs.jsonl` corpus and, for each sampled
chunk, emits a ticket whose text is answerable from that chunk plus a
`source_doc_id` field naming the chunk as ground truth. "May use a model" per
tasks.md 6.1, but this project has no live model (Decision 6) — a seeded
`random.Random` plus a small template table stands in, so output is exactly
reproducible under `--seed` with no network call.

The committed `data/generated/tickets.jsonl` is a seed for later golden-set
expansion; nothing in this repo consumes it yet (Q3 was resolved to keep the
Phase 2/3 golden sets at their current size).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "data" / "kb" / "ubuntu_docs.jsonl"
MANIFEST_PATH = ROOT / "data" / "kb" / "MANIFEST.json"
OUT_PATH = ROOT / "data" / "generated" / "tickets.jsonl"

PRIORITIES = ("low", "normal", "high", "urgent")
SENTIMENTS = ("neutral", "frustrated", "angry", "positive")
VERBOSITIES = ("terse", "verbose")
AMBIGUITIES = ("specific", "vague")
CHANNELS = ("email", "chat", "web_form")

_PRIORITY_LEAD = {
    "urgent": "URGENT: ",
    "high": "This is blocking my work — ",
    "normal": "",
    "low": "No rush, but ",
}
_SENTIMENT_TAIL = {
    "angry": " This is completely unacceptable.",
    "frustrated": " I've tried this three times already and I'm getting nowhere.",
    "neutral": "",
    "positive": " Thanks for any help you can offer.",
}
_CATEGORY_LABEL = {
    "install": "installing Ubuntu",
    "networking": "my network connection",
    "packaging": "installing packages",
    "users_permissions": "user accounts and permissions",
    "hardware": "a hardware device",
}


def _load_kb(path: Path) -> list[dict]:
    # File order is already deterministic (a committed, static JSONL corpus),
    # so no re-sort is needed for reproducibility.
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _load_categories(path: Path) -> dict[str, str]:
    manifest = json.loads(path.read_text())
    return {entry["slug"]: entry["category"] for entry in manifest}


def _category_for(doc_id: str, categories: dict[str, str]) -> str:
    slug = doc_id.rsplit("#", 1)[0]
    return categories.get(slug, "other")


def topic_snippet(text: str) -> str:
    """A short, lowercased, code-fence-free phrase describing what a chunk
    covers, used to ground a "specific" ticket in its source chunk."""
    for block in text.split("\n\n"):
        block = block.strip()
        if "```" in block:
            continue
        if block[:1].islower():
            # An overlap tail from `ingest.chunk()` can start mid-word; the
            # word straddling that cut is garbage, so drop it.
            block = block.partition(" ")[2]
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", block)
        if len(words) >= 6:
            return " ".join(words[:10]).lower()
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    return " ".join(words[:10]).lower() or "this"


def build_subject(category: str, snippet: str, ambiguity: str) -> str:
    if ambiguity == "specific":
        return snippet[:60].capitalize()
    return f"Problem with {_CATEGORY_LABEL.get(category, 'Ubuntu')}"


def build_text(
    category: str,
    snippet: str,
    *,
    priority: str,
    sentiment: str,
    verbosity: str,
    ambiguity: str,
) -> str:
    lead = _PRIORITY_LEAD[priority]
    tail = _SENTIMENT_TAIL[sentiment]
    if ambiguity == "specific":
        core = f"How do I {snippet}?"
        if verbosity == "verbose":
            core = (
                f"I've been trying to sort out {snippet} on my Ubuntu machine and keep "
                f"getting stuck. {core}"
            )
    else:
        topic = _CATEGORY_LABEL.get(category, "this issue")
        core = f"Something is wrong with {topic} and I don't know how to fix it."
        if verbosity == "verbose":
            core += (
                " It's been happening for a while now and I've tried a few things "
                "already but nothing has worked."
            )
    return f"{lead}{core}{tail}"


def generate(*, seed: int, n: int) -> list[dict]:
    """Deterministic under `seed`: same inputs always produce the same rows,
    byte-for-byte, because every random choice is drawn from one seeded RNG in
    a fixed order and nothing here reads the wall clock."""
    rng = random.Random(seed)  # noqa: S311 -- deterministic template sampling, not security
    docs = _load_kb(KB_PATH)
    categories = _load_categories(MANIFEST_PATH)
    chosen = (
        rng.sample(docs, n)
        if n <= len(docs)
        else [docs[i % len(docs)] for i in range(n)]
    )

    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    tickets: list[dict] = []
    for i, doc in enumerate(chosen):
        category = _category_for(doc["doc_id"], categories)
        priority = rng.choice(PRIORITIES)
        sentiment = rng.choice(SENTIMENTS)
        verbosity = rng.choice(VERBOSITIES)
        ambiguity = rng.choice(AMBIGUITIES)
        channel = rng.choice(CHANNELS)
        snippet = topic_snippet(doc["text"])
        received_at = (base_time + timedelta(minutes=i)).isoformat().replace("+00:00", "Z")
        tickets.append(
            {
                "ticket_id": f"GEN-{i + 1:04d}",
                "text": build_text(
                    category,
                    snippet,
                    priority=priority,
                    sentiment=sentiment,
                    verbosity=verbosity,
                    ambiguity=ambiguity,
                ),
                "channel": channel,
                "customer_id": f"cust-gen-{i + 1:04d}",
                "subject": build_subject(category, snippet, ambiguity),
                "received_at": received_at,
                "source_doc_id": doc["doc_id"],
                "profile": {
                    "priority": priority,
                    "sentiment": sentiment,
                    "verbosity": verbosity,
                    "ambiguity": ambiguity,
                },
            }
        )
    return tickets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--n", type=int, default=80)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    tickets = generate(seed=args.seed, n=args.n)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for ticket in tickets:
            f.write(json.dumps(ticket) + "\n")
    sys.stdout.write(f"Wrote {len(tickets)} tickets (seed={args.seed}) -> {args.out}\n")


if __name__ == "__main__":
    main()
