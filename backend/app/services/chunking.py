"""Text chunking that keeps page numbers and headings attached to every chunk.

The splitter is a recursive character splitter (the same strategy LangChain's
``RecursiveCharacterTextSplitter`` uses): it prefers paragraph boundaries, then
line breaks, then sentences, then words, and only cuts mid-word as a last resort.
Sizes are measured in characters (~4 characters per token), so the default
2000/200 configuration produces roughly 500-token chunks with 50-token overlap.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]
HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|unit\s*[-:]?\s*[ivx\d]+.*|chapter\s+\d+.*|lecture\s+\d+.*|[A-Z][A-Z0-9 ,&/\-]{6,60})$",
    re.IGNORECASE,
)


@dataclass
class PageText:
    page_no: int | None
    text: str


@dataclass
class TextChunk:
    index: int
    content: str
    page_no: int | None = None
    heading: str | None = None
    char_start: int = 0

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.content) // 4)


@dataclass
class ChunkingConfig:
    chunk_size: int = 2000
    chunk_overlap: int = 200
    min_chunk_size: int = 80
    separators: list[str] = field(default_factory=lambda: list(SEPARATORS))


def _split_recursive(text: str, cfg: ChunkingConfig, separators: list[str]) -> list[str]:
    """Split ``text`` into pieces no longer than ``cfg.chunk_size``."""
    if len(text) <= cfg.chunk_size:
        return [text] if text.strip() else []
    sep = separators[-1]
    rest: list[str] = []
    for i, s in enumerate(separators):
        if s == "" or s in text:
            sep = s
            rest = separators[i + 1 :]
            break
    parts = text.split(sep) if sep else list(text)
    pieces: list[str] = []
    buffer = ""
    for part in parts:
        candidate = f"{buffer}{sep}{part}" if buffer else part
        if len(candidate) <= cfg.chunk_size:
            buffer = candidate
            continue
        if buffer:
            pieces.append(buffer)
        if len(part) > cfg.chunk_size:
            pieces.extend(_split_recursive(part, cfg, rest) if rest else [part[: cfg.chunk_size]])
            buffer = ""
        else:
            buffer = part
    if buffer:
        pieces.append(buffer)
    return [p for p in pieces if p.strip()]


def _merge_with_overlap(pieces: list[str], cfg: ChunkingConfig) -> list[str]:
    """Merge small pieces and prepend an overlap tail from the previous chunk."""
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + 1 + len(piece) <= cfg.chunk_size:
            current = f"{current}\n{piece}"
        else:
            chunks.append(current)
            overlap = current[-cfg.chunk_overlap :] if cfg.chunk_overlap else ""
            # start the overlap at a word boundary
            if overlap and " " in overlap:
                overlap = overlap[overlap.index(" ") + 1 :]
            current = f"{overlap}{piece}" if overlap else piece
    if current:
        chunks.append(current)
    return chunks


def detect_heading(text: str) -> str | None:
    for line in text.strip().splitlines()[:3]:
        line = line.strip()
        if 4 <= len(line) <= 80 and HEADING_RE.match(line):
            return line.lstrip("# ").strip()
    return None


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"-\n(?=[a-z])", "", text)  # de-hyphenate line breaks
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def chunk_pages(pages: list[PageText], cfg: ChunkingConfig | None = None) -> list[TextChunk]:
    """Chunk a parsed document while tracking which page each chunk starts on."""
    cfg = cfg or ChunkingConfig()
    offsets: list[int] = []
    page_numbers: list[int | None] = []
    full_parts: list[str] = []
    cursor = 0
    for page in pages:
        text = clean_text(page.text)
        if not text:
            continue
        offsets.append(cursor)
        page_numbers.append(page.page_no)
        full_parts.append(text)
        cursor += len(text) + 2
    full = "\n\n".join(full_parts)
    if not full.strip():
        return []

    # Split to (chunk_size - overlap) so that chunks stay within chunk_size once the
    # overlap tail from the previous chunk is prepended.
    inner = ChunkingConfig(
        chunk_size=max(200, cfg.chunk_size - cfg.chunk_overlap),
        chunk_overlap=cfg.chunk_overlap,
        min_chunk_size=cfg.min_chunk_size,
        separators=cfg.separators,
    )
    pieces = _split_recursive(full, inner, inner.separators)
    merged = _merge_with_overlap(pieces, inner)

    chunks: list[TextChunk] = []
    search_from = 0
    current_heading: str | None = None
    for i, content in enumerate(merged):
        probe = content[: min(60, len(content))].lstrip()
        start = full.find(probe, search_from) if probe else search_from
        if start < 0:
            start = search_from
        search_from = max(search_from, start + 1)
        page_idx = bisect.bisect_right(offsets, start) - 1
        page_no = page_numbers[page_idx] if 0 <= page_idx < len(page_numbers) else None
        heading = detect_heading(content)
        if heading:
            current_heading = heading
        chunks.append(
            TextChunk(index=i, content=content.strip(), page_no=page_no, heading=current_heading, char_start=start)
        )
    # drop fragments that are too small to be useful, unless it's the only chunk
    if len(chunks) > 1:
        chunks = [c for c in chunks if len(c.content) >= cfg.min_chunk_size]
        for i, c in enumerate(chunks):
            c.index = i
    return chunks


def chunk_text(text: str, cfg: ChunkingConfig | None = None) -> list[TextChunk]:
    return chunk_pages([PageText(page_no=None, text=text)], cfg)
