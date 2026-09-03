"""
Splits normalized resource text into token-bounded chunks for future
embedding, using tiktoken to encode/decode/count tokens. Chunk size and
overlap default to app/config.py's `chunk_size_tokens`/`chunk_overlap_tokens`
(512/64) but are overridable per call rather than hard-coded.

Pure and side-effect-free -- no Mongo/FastAPI imports -- so it can be unit
tested independently. See backend/tests/test_chunking.py.
"""

from dataclasses import dataclass

import tiktoken

from app.config import settings


@dataclass(frozen=True)
class TextChunk:
    """One chunk's text, its token count, and the token-index window (in the
    source token stream) it was decoded from. `end_token` is exclusive."""

    text: str
    token_count: int
    start_token: int
    end_token: int


def chunk_text(
    text: str,
    *,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
    encoding_name: str | None = None,
) -> list[TextChunk]:
    """
    Splits `text` into `TextChunk`s of at most `max_tokens` tokens each, with
    `overlap_tokens` tokens of overlap between consecutive chunks.

    Guarantees:
    - Chunks are returned in source order.
    - No chunk is ever empty -- a token window that decodes to only
      whitespace is skipped rather than emitted.
    - The last chunk always reaches the end of the token stream, so content
      is never silently truncated, however large the document.
    - Deterministic: the same input and config always produce the same
      output (tiktoken's BPE encoding is itself deterministic).
    """
    max_tokens = settings.chunk_size_tokens if max_tokens is None else max_tokens
    overlap_tokens = settings.chunk_overlap_tokens if overlap_tokens is None else overlap_tokens
    encoding_name = settings.tiktoken_encoding if encoding_name is None else encoding_name

    if max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    stripped = text.strip()
    if not stripped:
        return []

    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(stripped)
    if not tokens:
        return []

    step = max_tokens - overlap_tokens
    total = len(tokens)
    chunks: list[TextChunk] = []

    start = 0
    while start < total:
        end = min(start + max_tokens, total)
        window = tokens[start:end]
        piece_text = encoding.decode(window)
        if piece_text.strip():
            chunks.append(
                TextChunk(text=piece_text, token_count=len(window), start_token=start, end_token=end)
            )
        if end == total:
            break
        start += step

    return chunks
