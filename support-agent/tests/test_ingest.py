import json
from pathlib import Path

from triage.ingest import chunk, extract_title, normalize, to_documents

KB_PATH = Path(__file__).resolve().parents[1] / "data" / "kb" / "ubuntu_docs.jsonl"

_SAMPLE_HTML = """<html><head><title>Sudo - Community Help Wiki</title></head>
<body>
<div id="header"><a href="/">nav chrome</a></div>
<div id="content" lang="en">
<h1 id="Usage">Usage</h1>
<p>Use <tt>sudo</tt> to run a command as root:</p>
<pre>sudo apt-get update
sudo apt-get upgrade</pre>
<p>That's it.</p>
</div>
<div id="pagebottom"></div>
<div id="footer">Community Wiki footer chrome</div>
</body></html>"""


# --------------------------------------------------------------------------- #
# normalize() / extract_title()
# --------------------------------------------------------------------------- #


def test_normalize_strips_chrome_and_preserves_command_blocks():
    text = normalize(_SAMPLE_HTML)

    assert "nav chrome" not in text
    assert "footer chrome" not in text
    assert "Usage" in text
    assert "sudo apt-get update" in text
    assert "sudo apt-get upgrade" in text

    # the two-line command block stays together, not split apart
    idx = text.index("sudo apt-get update")
    assert "sudo apt-get upgrade" in text[idx : idx + 200]


def test_extract_title_strips_wiki_suffix():
    assert extract_title(_SAMPLE_HTML) == "Sudo"


# --------------------------------------------------------------------------- #
# chunk()
# --------------------------------------------------------------------------- #


def test_chunk_on_large_fixture_yields_overlapping_chunks_covering_input():
    paragraphs = [
        f"Paragraph {i}. " + ("Ubuntu networking configuration details. " * 10) for i in range(12)
    ]
    fixture = "\n\n".join(paragraphs)
    assert len(fixture) > 4000

    chunks = chunk(fixture, target_chars=1200, overlap=150)

    assert len(chunks) > 1
    # concatenation covers the input: every paragraph marker survives somewhere
    joined = "\n".join(chunks)
    for i in range(12):
        assert f"Paragraph {i}." in joined

    # overlap: consecutive chunks share trailing/leading text
    assert chunks[0][-100:][-20:] in chunks[1]


def test_chunk_never_splits_a_fenced_command_block():
    text = (
        "Intro paragraph about the tool.\n\n"
        "```\nsudo apt-get update\nsudo apt-get upgrade\n```\n\n"
        "Trailing paragraph."
    )
    chunks = chunk(text, target_chars=1200, overlap=150)
    block = "sudo apt-get update\nsudo apt-get upgrade"
    assert any(block in c for c in chunks)


# --------------------------------------------------------------------------- #
# to_documents()
# --------------------------------------------------------------------------- #


def test_to_documents_have_unique_ids_source_and_license():
    chunks = ["First chunk text.", "Second chunk text.", "Third chunk text."]
    docs = to_documents(
        "ExampleSlug", "https://help.ubuntu.com/community/ExampleSlug", chunks, title="Example"
    )

    ids = [d.doc_id for d in docs]
    assert len(ids) == len(set(ids))
    for d in docs:
        assert d.source
        assert d.metadata["license"] == "CC BY-SA 4.0"


# --------------------------------------------------------------------------- #
# Committed corpus (Phase 1 exit criteria, checkable in CI)
# --------------------------------------------------------------------------- #


def test_committed_corpus_meets_phase_exit_target():
    rows = [json.loads(line) for line in KB_PATH.read_text().splitlines() if line.strip()]
    assert len(rows) >= 300

    ids = [r["doc_id"] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        assert r["source"]
        assert r["metadata"]["license"] == "CC BY-SA 4.0"
