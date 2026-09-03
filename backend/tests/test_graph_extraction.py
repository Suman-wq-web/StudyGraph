"""
Tests for concept/relationship extraction (app/services/ingestion/extraction.py).
No real Gemini calls -- a FakeGenerationProvider test double stands in for
the (unmodified) GenerationProvider interface, mirroring
test_embedding_pipeline.py's FakeEmbeddingProvider pattern.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from app.models.chunk import DocumentChunk
from app.services.ingestion import extraction
from app.services.rag.generation import GenerationChunk, GenerationProvider, GenerationRateLimitError


class FakeGenerationProvider(GenerationProvider):
    """Yields one canned response text per call, in order; optionally raises
    for the first `fail_times` calls to exercise error propagation."""

    def __init__(self, responses=None, *, fail_times: int = 0, error_cls=GenerationRateLimitError):
        self.calls: list[tuple[str, str]] = []
        self._responses = list(responses or [])
        self._fail_times = fail_times
        self._error_cls = error_cls

    @property
    def model_name(self) -> str:
        return "fake-generation-model"

    async def stream_generate(self, *, system_prompt: str, user_prompt: str):
        self.calls.append((system_prompt, user_prompt))
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._error_cls("simulated failure")
        text = self._responses.pop(0) if self._responses else '{"concepts": [], "relationships": []}'
        yield GenerationChunk(text=text, finish_reason="STOP")


def _chunk(text: str = "Gradient descent is an optimization algorithm.", chunk_id: str = "c1") -> DocumentChunk:
    now = datetime.now(timezone.utc)
    return DocumentChunk(
        id=chunk_id,
        user_id="u1",
        resource_id="r1",
        chunk_index=0,
        text=text,
        token_count=5,
        start_token=0,
        end_token=5,
        created_at=now,
        updated_at=now,
    )


class TestSuccessfulExtraction:
    def test_valid_json_parses_into_concepts_and_relations(self):
        response = (
            '{"concepts": [{"name": "Gradient Descent", "description": "an optimization algorithm"}, '
            '{"name": "Calculus"}], '
            '"relationships": [{"source": "Calculus", "relation_type": "prerequisite_of", '
            '"target": "Gradient Descent"}]}'
        )
        provider = FakeGenerationProvider(responses=[response])

        result = asyncio.run(extraction.extract_from_chunk(_chunk(), provider=provider))

        assert [c.name for c in result.concepts] == ["Gradient Descent", "Calculus"]
        assert result.concepts[0].description == "an optimization algorithm"
        assert result.concepts[1].description is None
        assert len(result.relations) == 1
        assert result.relations[0].relation_type == "prerequisite_of"
        assert len(provider.calls) == 1

    def test_markdown_fenced_json_is_stripped(self):
        response = '```json\n{"concepts": [{"name": "X"}], "relationships": []}\n```'
        provider = FakeGenerationProvider(responses=[response])

        result = asyncio.run(extraction.extract_from_chunk(_chunk(), provider=provider))

        assert [c.name for c in result.concepts] == ["X"]

    def test_empty_excerpt_response_yields_no_concepts(self):
        provider = FakeGenerationProvider(responses=['{"concepts": [], "relationships": []}'])

        result = asyncio.run(extraction.extract_from_chunk(_chunk(), provider=provider))

        assert result.concepts == []
        assert result.relations == []

    def test_relationship_with_invalid_type_is_dropped(self):
        response = (
            '{"concepts": [{"name": "A"}, {"name": "B"}], '
            '"relationships": [{"source": "A", "relation_type": "causes", "target": "B"}]}'
        )
        provider = FakeGenerationProvider(responses=[response])

        result = asyncio.run(extraction.extract_from_chunk(_chunk(), provider=provider))

        assert result.relations == []

    def test_concept_with_blank_name_is_dropped(self):
        response = '{"concepts": [{"name": "  "}, {"name": "Real Concept"}], "relationships": []}'
        provider = FakeGenerationProvider(responses=[response])

        result = asyncio.run(extraction.extract_from_chunk(_chunk(), provider=provider))

        assert [c.name for c in result.concepts] == ["Real Concept"]


class TestMalformedResponseRetry:
    def test_malformed_first_response_retries_once_and_succeeds(self):
        provider = FakeGenerationProvider(
            responses=["not json at all", '{"concepts": [{"name": "X"}], "relationships": []}']
        )

        result = asyncio.run(extraction.extract_from_chunk(_chunk(), provider=provider))

        assert [c.name for c in result.concepts] == ["X"]
        assert len(provider.calls) == 2
        assert "not valid JSON" in provider.calls[1][0]  # stricter retry prompt

    def test_malformed_after_retry_raises_extraction_parse_error(self):
        provider = FakeGenerationProvider(responses=["still not json", "still not json either"])

        with pytest.raises(extraction.ExtractionParseError):
            asyncio.run(extraction.extract_from_chunk(_chunk(), provider=provider))

        assert len(provider.calls) == 2


class TestProviderErrorsPropagate:
    def test_rate_limit_error_propagates_unmodified(self):
        provider = FakeGenerationProvider(fail_times=1)

        with pytest.raises(GenerationRateLimitError):
            asyncio.run(extraction.extract_from_chunk(_chunk(), provider=provider))
