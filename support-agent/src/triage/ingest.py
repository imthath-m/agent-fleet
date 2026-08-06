"""Normalize and chunk help.ubuntu.com KB pages into `spine.rag.Document` rows.

Reads the raw HTML fetched by `scripts/fetch_kb.py` (this module never
touches the network itself) and writes `data/kb/ubuntu_docs.jsonl` -- the
committed corpus every later phase queries offline.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path

from spine.rag import Document

KB_LICENSE = "CC BY-SA 4.0"
KB_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BREAK_TAGS = _HEADING_TAGS | {"p", "li"}
_SKIP_TAGS = {"script", "style"}
_TITLE_SUFFIX = " - Community Help Wiki"


class _ContentExtractor(HTMLParser):
    """Pulls plain text out of the `#content` div of a help.ubuntu.com wiki
    page. Inserts blank-line breaks at headings/paragraphs/list items (so
    `chunk()` can split on them) and preserves `<pre>` command blocks
    verbatim, fenced, so a chunk boundary never lands inside a command."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._in_content = False
        self._content_div_depth = 0
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_tag(tag, attrs, is_end=False)

    def handle_endtag(self, tag: str) -> None:
        self._handle_tag(tag, [], is_end=True)

    def _handle_tag(self, tag: str, attrs: list[tuple[str, str | None]], *, is_end: bool) -> None:
        if tag == "title":
            self._in_title = not is_end
            return

        if not self._in_content:
            if not is_end and tag == "div" and dict(attrs).get("id") == "content":
                self._in_content = True
                self._content_div_depth = 1
            return

        if tag == "div":
            self._content_div_depth += -1 if is_end else 1
            if self._content_div_depth <= 0:
                self._in_content = False
            return

        if tag in _SKIP_TAGS:
            self._skip_depth += -1 if is_end else 1
        elif tag == "pre":
            self._parts.append("\n```\n\n" if is_end else "\n\n```\n")
        elif tag in _BREAK_TAGS and not is_end:
            self._parts.append("\n\n")
        elif tag == "br":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._in_content and not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def extract_title(html: str) -> str:
    """The wiki page title, with the ` - Community Help Wiki` suffix stripped."""
    parser = _ContentExtractor()
    parser.feed(html)
    title = parser.title.strip()
    if title.endswith(_TITLE_SUFFIX):
        title = title[: -len(_TITLE_SUFFIX)]
    return title


def normalize(html: str) -> str:
    """Strip nav/chrome/scripts; return the `#content` div's plain text with
    blank-line breaks at headings/paragraphs and fenced ``` command blocks."""
    parser = _ContentExtractor()
    parser.feed(html)
    text = parser.text()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk(text: str, *, target_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Split into ~target_chars chunks, preferring blank-line (heading /
    paragraph / fenced command block) boundaries so a chunk never splits a
    shell command block in the middle. Falls back to a hard, overlapping
    split only for a single unit larger than target_chars on its own."""
    units = [u.strip() for u in re.split(r"\n\s*\n", text) if u.strip()]
    if not units:
        return []

    packed: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if not current or len(candidate) <= target_chars:
            current = candidate
        else:
            packed.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n\n{unit}" if tail else unit
    if current:
        packed.append(current)

    result: list[str] = []
    for piece in packed:
        if len(piece) <= target_chars * 1.5:
            result.append(piece)
        else:
            result.extend(_hard_split(piece, target_chars, overlap))
    return result


def _hard_split(text: str, target_chars: int, overlap: int) -> list[str]:
    step = max(target_chars - overlap, 1)
    pieces: list[str] = []
    i = 0
    while i < len(text):
        pieces.append(text[i : i + target_chars])
        if i + target_chars >= len(text):
            break
        i += step
    return pieces


def to_documents(slug: str, url: str, chunks: list[str], *, title: str = "") -> list[Document]:
    """Wrap `chunks` as `spine.rag.Document` rows, carrying attribution."""
    return [
        Document(
            doc_id=f"{slug}#{i}",
            text=text,
            source=url,
            metadata={
                "license": KB_LICENSE,
                "license_url": KB_LICENSE_URL,
                "title": title,
                "url": url,
            },
        )
        for i, text in enumerate(chunks)
    ]


# --------------------------------------------------------------------------- #
# Build driver: raw HTML + MANIFEST.json -> committed JSONL corpus. Reads
# local files only; scripts/fetch_kb.py is the sole network touchpoint.
# --------------------------------------------------------------------------- #

RAW_DIR = Path("data/kb/raw")
MANIFEST_PATH = Path("data/kb/MANIFEST.json")
OUTPUT_PATH = Path("data/kb/ubuntu_docs.jsonl")


def build_corpus() -> list[Document]:
    manifest = json.loads(MANIFEST_PATH.read_text())
    documents: list[Document] = []
    for entry in manifest:
        slug = entry["slug"]
        html = (RAW_DIR / (slug.replace("/", "__") + ".html")).read_text()
        text = normalize(html)
        documents.extend(
            to_documents(slug, entry["url"], chunk(text), title=extract_title(html))
        )
    return documents


def main() -> None:
    documents = build_corpus()
    with OUTPUT_PATH.open("w") as f:
        for doc in documents:
            f.write(json.dumps(asdict(doc)) + "\n")
    sys.stdout.write(f"Wrote {len(documents)} chunks -> {OUTPUT_PATH}\n")


if __name__ == "__main__":
    main()
