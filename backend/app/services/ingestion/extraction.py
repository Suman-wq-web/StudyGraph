"""
Extracts candidate concepts and relationship triples from a single document
chunk (Phase 6), using the existing Phase 5 `GenerationProvider` abstraction
(app/services/rag/generation.py) completely unmodified -- no new method, no
new provider, no new SDK import site. Concept resolution/dedupe against a
user's existing `concepts` happens one level up, in
app/services/graph_extraction_service.py; this module only turns chunk text
into candidate names/triples.

Structured-output note: Gemini's native `response_schema`/JSON-mode would
give more reliable parsing than what's below, but wiring it up would mean
adding a method to `GenerationProvider` in generation.py -- a file from the
already-verified Phase 5 RAG chat pipeline that this phase deliberately
leaves untouched (see docs/KNOWLEDGE_GRAPH.md). Instead, this module prompts
for raw JSON over the existing `stream_generate()` interface and parses the
buffered response text, retrying once with a stricter prompt on a malformed
first response before giving up on that chunk.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.config import settings
from app.models.chunk import DocumentChunk
from app.services.rag.generation import GenerationProvider, get_generation_provider

logger = logging.getLogger(__name__)

VALID_RELATION_TYPES = {"prerequisite_of", "related_to", "part_of"}


class ExtractionError(Exception):
    """Base for extraction failures local to this module."""


class ExtractionParseError(ExtractionError):
    """Gemini's response wasn't valid JSON matching the expected shape, even
    after one stricter retry. Callers should skip this chunk, not fail the
    whole run -- see app/services/graph_extraction_service.py."""


@dataclass(frozen=True)
class ExtractedConcept:
    name: str
    description: str | None


@dataclass(frozen=True)
class ExtractedRelation:
    source: str
    relation_type: str
    target: str


@dataclass(frozen=True)
class ChunkExtractionResult:
    concepts: list[ExtractedConcept]
    relations: list[ExtractedRelation]


def _system_prompt() -> str:
    return (
        "You are a knowledge-extraction engine for a study app. Read the excerpt "
        "below and identify the distinct academic/technical concepts it teaches or "
        f"references (at most {settings.extraction_max_concepts_per_chunk}), plus "
        "any relationships between those concepts. Respond with ONLY a single JSON "
        "object -- no markdown code fences, no commentary before or after -- in "
        "exactly this shape:\n"
        '{"concepts": [{"name": "string", "description": "string"}], '
        '"relationships": [{"source": "string", "relation_type": '
        '"prerequisite_of" | "related_to" | "part_of", "target": "string"}]}\n'
        "`source` and `target` must each exactly match a `name` from `concepts`. "
        'If the excerpt contains no clear concepts, return exactly '
        '{"concepts": [], "relationships": []}.'
    )


_STRICT_RETRY_SUFFIX = (
    "\n\nYour previous response was not valid JSON matching the required shape. "
    "Respond again with ONLY the raw JSON object described above -- no markdown "
    "fences, no leading or trailing text of any kind."
)


async def extract_from_chunk(
    chunk: DocumentChunk, *, provider: GenerationProvider | None = None
) -> ChunkExtractionResult:
    """
    One (or, on a malformed first response, two) calls to the configured
    GenerationProvider, turning `chunk.text` into candidate concepts and
    relationship triples. Propagates whatever `GenerationError` subclass
    `stream_generate` raises (rate-limit/transient/provider) unmodified, for
    the caller to retry/handle; raises `ExtractionParseError` if the
    response still isn't parseable JSON after the one built-in retry.
    """
    provider = provider or get_generation_provider()

    raw = await _buffer_stream(provider, system_prompt=_system_prompt(), user_prompt=chunk.text)
    result = _try_parse(raw)
    if result is not None:
        return result

    raw_retry = await _buffer_stream(
        provider,
        system_prompt=_system_prompt() + _STRICT_RETRY_SUFFIX,
        user_prompt=chunk.text,
    )
    result = _try_parse(raw_retry)
    if result is not None:
        return result

    raise ExtractionParseError(
        f"Gemini did not return parseable JSON for chunk {chunk.id} after retrying."
    )


async def _buffer_stream(
    provider: GenerationProvider, *, system_prompt: str, user_prompt: str
) -> str:
    """Consumes the existing streaming interface in full rather than reading
    incrementally -- extraction is a background job with no client waiting
    on partial output, so there's nothing to gain from processing deltas as
    they arrive."""
    parts: list[str] = []
    async for piece in provider.stream_generate(system_prompt=system_prompt, user_prompt=user_prompt):
        if piece.text:
            parts.append(piece.text)
    return "".join(parts)


def _try_parse(raw: str) -> ChunkExtractionResult | None:
    """Returns None (never raises) on any malformed input -- the caller
    decides whether to retry or give up."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Extraction response was not valid JSON")
        return None

    if not isinstance(data, dict):
        return None

    try:
        concepts = [
            ExtractedConcept(
                name=str(item["name"]).strip(),
                description=(str(item["description"]).strip() if item.get("description") else None),
            )
            for item in data.get("concepts", [])
            if str(item.get("name", "")).strip()
        ]
        relations = [
            ExtractedRelation(
                source=str(item["source"]).strip(),
                relation_type=str(item["relation_type"]).strip(),
                target=str(item["target"]).strip(),
            )
            for item in data.get("relationships", [])
            if str(item.get("relation_type", "")).strip() in VALID_RELATION_TYPES
            and str(item.get("source", "")).strip()
            and str(item.get("target", "")).strip()
        ]
    except (KeyError, TypeError, AttributeError):
        return None

    return ChunkExtractionResult(concepts=concepts, relations=relations)
