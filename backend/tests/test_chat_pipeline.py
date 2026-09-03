"""
Tests for app/services/rag/pipeline.py (retrieve_context, stream_generation,
answer_query). No real Gemini/Atlas calls -- retrieval.hybrid_search_with_scores,
citations.build_citations, and the generation provider are all mocked/injected.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from app.models.chat import Citation
from app.models.chunk import DocumentChunk
from app.models.resource import ResourceType
from app.services.rag import citations as citations_module
from app.services.rag import pipeline, retrieval
from app.services.rag.generation import (
    GenerationChunk,
    GenerationProvider,
    GenerationProviderError,
    GenerationRateLimitError,
    GenerationTransientError,
)


class FakeGenerationProvider(GenerationProvider):
    """Configurable fake: yields `chunks` in order, optionally raising a
    transient error on the first N calls (simulating rate-limit/transient
    failures before the first chunk), or raising mid-stream right before a
    given chunk index (simulating a failure after output has already
    reached the client)."""

    def __init__(
        self,
        chunks: list[GenerationChunk] | None = None,
        *,
        transient_failures_before_success: int = 0,
        fail_after_chunk_index: int | None = None,
    ):
        self._chunks = chunks if chunks is not None else [GenerationChunk(text="answer", finish_reason="STOP")]
        self._transient_failures_before_success = transient_failures_before_success
        self._fail_after_chunk_index = fail_after_chunk_index
        self._call_count = 0
        self.captured_prompts: list[tuple[str, str]] = []

    @property
    def model_name(self) -> str:
        return "fake-generation-model"

    async def stream_generate(self, *, system_prompt: str, user_prompt: str):
        self.captured_prompts.append((system_prompt, user_prompt))
        self._call_count += 1
        if self._call_count <= self._transient_failures_before_success:
            raise GenerationTransientError("temporary failure")
        for index, chunk in enumerate(self._chunks):
            if self._fail_after_chunk_index is not None and index == self._fail_after_chunk_index:
                raise GenerationProviderError("failed mid-stream")
            yield chunk


def _make_chunk(
    chunk_id: str,
    *,
    resource_id: str = "r1",
    text: str = "chunk text",
    chunk_index: int = 0,
    user_id: str = "u1",
) -> DocumentChunk:
    now = datetime.now(timezone.utc)
    return DocumentChunk(
        id=chunk_id,
        user_id=user_id,
        resource_id=resource_id,
        chunk_index=chunk_index,
        text=text,
        token_count=1,
        start_token=0,
        end_token=1,
        created_at=now,
        updated_at=now,
    )


class FakeRateLimitedGenerationProvider(GenerationProvider):
    """Raises a GenerationRateLimitError carrying `retry_delay_seconds` on
    its first `fail_times` calls, then succeeds -- isolates retryDelay
    honoring from FakeGenerationProvider's plain-transient-failure
    scenarios above, which never set that attribute."""

    def __init__(self, *, retry_delay_seconds: float, fail_times: int = 1):
        self._retry_delay_seconds = retry_delay_seconds
        self._fail_times = fail_times
        self._call_count = 0

    @property
    def model_name(self) -> str:
        return "fake-rate-limited-model"

    async def stream_generate(self, *, system_prompt: str, user_prompt: str):
        self._call_count += 1
        if self._call_count <= self._fail_times:
            raise GenerationRateLimitError(
                "rate limited", retry_delay_seconds=self._retry_delay_seconds
            )
        yield GenerationChunk(text="ok", finish_reason="STOP")


def _make_citation(chunk_id: str, *, resource_id: str = "r1", score: float = 0.5) -> Citation:
    return Citation(
        resource_id=resource_id,
        resource_title="Some Resource",
        resource_type=ResourceType.NOTE,
        chunk_id=chunk_id,
        chunk_index=0,
        snippet="chunk text",
        score=score,
    )


async def _drain(agen) -> list:
    return [item async for item in agen]


class TestRetrieveContext:
    def test_propagates_embedding_unavailable_error(self, monkeypatch):
        async def raiser(*args, **kwargs):
            raise retrieval.EmbeddingUnavailableError("boom")

        monkeypatch.setattr(retrieval, "hybrid_search_with_scores", raiser)

        with pytest.raises(retrieval.EmbeddingUnavailableError):
            asyncio.run(pipeline.retrieve_context("u1", "query"))

    def test_propagates_retrieval_unavailable_error(self, monkeypatch):
        async def raiser(*args, **kwargs):
            raise retrieval.RetrievalUnavailableError("boom")

        monkeypatch.setattr(retrieval, "hybrid_search_with_scores", raiser)

        with pytest.raises(retrieval.RetrievalUnavailableError):
            asyncio.run(pipeline.retrieve_context("u1", "query"))

    def test_attaches_fused_rrf_score_onto_each_citation(self, monkeypatch):
        chunk = _make_chunk("656565656565656565656561")

        async def fake_hybrid(*args, **kwargs):
            return [(chunk, 0.123)]

        async def fake_build_citations(chunks, user_id):
            return [_make_citation(chunk.id, score=0.0)]  # citations.py never sets a real score

        monkeypatch.setattr(retrieval, "hybrid_search_with_scores", fake_hybrid)
        monkeypatch.setattr(citations_module, "build_citations", fake_build_citations)

        context = asyncio.run(pipeline.retrieve_context("u1", "query"))

        assert context.chunks == [chunk]
        assert context.citations[0].score == pytest.approx(0.123)


class TestStreamGeneration:
    def test_citations_event_is_always_first_even_when_empty(self):
        context = pipeline.RagContext(query="q", chunks=[], citations=[])
        provider = FakeGenerationProvider()

        events = asyncio.run(_drain(pipeline.stream_generation(context, provider=provider)))

        assert events[0].event == "citations"
        assert events[0].data.citations == []
        assert events[-1].event == "done"

    def test_zero_chunk_context_prompts_with_no_relevant_material_marker(self):
        context = pipeline.RagContext(query="what is X?", chunks=[], citations=[])
        provider = FakeGenerationProvider()

        asyncio.run(_drain(pipeline.stream_generation(context, provider=provider)))

        _, user_prompt = provider.captured_prompts[0]
        assert "No relevant saved material" in user_prompt
        assert "what is X?" in user_prompt

    def test_tokens_stream_in_order_before_done(self):
        chunk = _make_chunk("656565656565656565656562")
        citation = _make_citation(chunk.id)
        context = pipeline.RagContext(query="q", chunks=[chunk], citations=[citation])
        provider = FakeGenerationProvider(
            chunks=[GenerationChunk(text="Hello "), GenerationChunk(text="world", finish_reason="STOP")]
        )

        events = asyncio.run(_drain(pipeline.stream_generation(context, provider=provider)))

        assert [e.event for e in events] == ["citations", "token", "token", "done"]
        assert [e.data.delta for e in events[1:3]] == ["Hello ", "world"]
        assert events[-1].data.finish_reason == "STOP"

    def test_mid_stream_failure_yields_terminal_error_not_an_exception(self):
        context = pipeline.RagContext(query="q", chunks=[], citations=[])
        provider = FakeGenerationProvider(
            chunks=[GenerationChunk(text="first"), GenerationChunk(text="second")],
            fail_after_chunk_index=1,
        )

        events = asyncio.run(_drain(pipeline.stream_generation(context, provider=provider)))

        assert [e.event for e in events] == ["citations", "token", "error"]

    def test_transient_failures_before_first_chunk_are_retried_transparently(self, monkeypatch):
        monkeypatch.setattr(pipeline, "BASE_BACKOFF_SECONDS", 0.0)
        context = pipeline.RagContext(query="q", chunks=[], citations=[])
        provider = FakeGenerationProvider(
            chunks=[GenerationChunk(text="ok", finish_reason="STOP")],
            transient_failures_before_success=2,
        )

        events = asyncio.run(_drain(pipeline.stream_generation(context, provider=provider)))

        assert [e.event for e in events] == ["citations", "token", "done"]

    def test_retry_budget_exhausted_yields_terminal_error(self, monkeypatch):
        monkeypatch.setattr(pipeline, "BASE_BACKOFF_SECONDS", 0.0)
        context = pipeline.RagContext(query="q", chunks=[], citations=[])
        provider = FakeGenerationProvider(transient_failures_before_success=99)

        events = asyncio.run(_drain(pipeline.stream_generation(context, provider=provider)))

        assert [e.event for e in events] == ["citations", "error"]

    def test_misconfigured_provider_yields_terminal_error(self, monkeypatch):
        context = pipeline.RagContext(query="q", chunks=[], citations=[])

        def failing_get_provider():
            raise GenerationProviderError("GEMINI_API_KEY is not configured.")

        monkeypatch.setattr(pipeline, "get_generation_provider", failing_get_provider)

        events = asyncio.run(_drain(pipeline.stream_generation(context)))

        assert [e.event for e in events] == ["citations", "error"]


class TestGenerationRetryDelayHandling:
    def test_retry_honors_gemini_retry_delay_when_present(self, monkeypatch):
        sleep_calls: list[float] = []
        monkeypatch.setattr(pipeline.asyncio, "sleep", _recording_sleep(sleep_calls))
        context = pipeline.RagContext(query="q", chunks=[], citations=[])
        provider = FakeRateLimitedGenerationProvider(retry_delay_seconds=7.0)

        events = asyncio.run(_drain(pipeline.stream_generation(context, provider=provider)))

        assert sleep_calls == [7.0]
        assert [e.event for e in events] == ["citations", "token", "done"]

    def test_retry_delay_is_capped_at_the_configured_maximum(self, monkeypatch):
        sleep_calls: list[float] = []
        monkeypatch.setattr(pipeline.asyncio, "sleep", _recording_sleep(sleep_calls))
        context = pipeline.RagContext(query="q", chunks=[], citations=[])
        provider = FakeRateLimitedGenerationProvider(
            retry_delay_seconds=pipeline.MAX_RETRY_DELAY_SECONDS + 100
        )

        asyncio.run(_drain(pipeline.stream_generation(context, provider=provider)))

        assert sleep_calls == [pipeline.MAX_RETRY_DELAY_SECONDS]

    def test_retry_falls_back_to_exponential_backoff_without_a_retry_delay(self, monkeypatch):
        monkeypatch.setattr(pipeline, "BASE_BACKOFF_SECONDS", 0.25)
        sleep_calls: list[float] = []
        monkeypatch.setattr(pipeline.asyncio, "sleep", _recording_sleep(sleep_calls))
        context = pipeline.RagContext(query="q", chunks=[], citations=[])
        provider = FakeGenerationProvider(
            chunks=[GenerationChunk(text="ok", finish_reason="STOP")],
            transient_failures_before_success=2,
        )

        asyncio.run(_drain(pipeline.stream_generation(context, provider=provider)))

        assert sleep_calls == [0.25 * 1, 0.25 * 2]


def _recording_sleep(sleep_calls: list[float]):
    async def _sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    return _sleep


class TestAnswerQuery:
    def test_buffers_tokens_into_answer_and_returns_citations(self, monkeypatch):
        chunk = _make_chunk("656565656565656565656563")
        citation = _make_citation(chunk.id)

        async def fake_hybrid(*args, **kwargs):
            return [(chunk, citation.score)]

        async def fake_build_citations(chunks, user_id):
            return [citation]

        monkeypatch.setattr(retrieval, "hybrid_search_with_scores", fake_hybrid)
        monkeypatch.setattr(citations_module, "build_citations", fake_build_citations)
        monkeypatch.setattr(
            pipeline,
            "get_generation_provider",
            lambda: FakeGenerationProvider(
                chunks=[
                    GenerationChunk(text="The answer "),
                    GenerationChunk(text="is 42.", finish_reason="STOP"),
                ]
            ),
        )

        response = asyncio.run(pipeline.answer_query("u1", "what is the answer?"))

        assert response.query == "what is the answer?"
        assert response.answer == "The answer is 42."
        assert response.citations == [citation]

    def test_terminal_error_event_raises_runtime_error(self, monkeypatch):
        async def fake_hybrid(*args, **kwargs):
            return []

        async def fake_build_citations(chunks, user_id):
            return []

        monkeypatch.setattr(retrieval, "hybrid_search_with_scores", fake_hybrid)
        monkeypatch.setattr(citations_module, "build_citations", fake_build_citations)
        monkeypatch.setattr(
            pipeline,
            "get_generation_provider",
            lambda: FakeGenerationProvider(transient_failures_before_success=99),
        )
        monkeypatch.setattr(pipeline, "BASE_BACKOFF_SECONDS", 0.0)

        with pytest.raises(RuntimeError):
            asyncio.run(pipeline.answer_query("u1", "query"))
