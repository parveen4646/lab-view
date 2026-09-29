"""Token-aware chunking for RAG ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    text: str
    index: int
    token_count: int


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def chunk_text(text: str, chunk_tokens: int = 400, overlap_tokens: int = 60) -> List[Chunk]:
    """
    Split text into overlapping token-bounded chunks.

    Splits on paragraph boundaries first so a chunk never cuts a sentence
    mid-word when the source has natural breaks; falls back to a hard
    token-window slice for one giant paragraph.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: List[Chunk] = []
    current_parts: List[str] = []
    current_tokens = 0

    def _flush() -> None:
        nonlocal current_parts, current_tokens
        if not current_parts:
            return
        joined = "\n\n".join(current_parts)
        chunks.append(Chunk(text=joined, index=len(chunks), token_count=count_tokens(joined)))
        current_parts = []
        current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # One paragraph alone exceeds the budget — hard-slice it by tokens.
        if para_tokens > chunk_tokens:
            _flush()
            tokens = _ENCODING.encode(para)
            start = 0
            while start < len(tokens):
                end = min(start + chunk_tokens, len(tokens))
                piece = _ENCODING.decode(tokens[start:end])
                chunks.append(Chunk(text=piece, index=len(chunks), token_count=end - start))
                if end == len(tokens):
                    break
                start = end - overlap_tokens
            continue

        if current_tokens + para_tokens > chunk_tokens:
            _flush()

        current_parts.append(para)
        current_tokens += para_tokens

    _flush()

    # Stitch a small token overlap onto the front of each chunk (after the first)
    # so retrieval doesn't lose context that sat right at a chunk boundary.
    if overlap_tokens > 0:
        for i in range(1, len(chunks)):
            prev_tokens = _ENCODING.encode(chunks[i - 1].text)
            tail = _ENCODING.decode(prev_tokens[-overlap_tokens:])
            stitched = tail + "\n\n" + chunks[i].text
            chunks[i] = Chunk(text=stitched, index=chunks[i].index, token_count=count_tokens(stitched))

    return chunks
