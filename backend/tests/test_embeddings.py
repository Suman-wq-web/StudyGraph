"""
Tests for the embedding provider abstraction (app/services/rag/embeddings.py).
No real Gemini API calls -- every provider call is mocked at the SDK client
boundary (`provider._client.aio.models.embed_content`).
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.config import settings
from app.services.rag.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingTransientError,
    GeminiEmbeddingProvider,
    get_embedding_provider,
)


def _fake_response(vectors: list[list[float]]) -> genai_types.EmbedContentResponse:
    return genai_types.EmbedContentResponse(
        embeddings=[genai_types.ContentEmbedding(values=v) for v in vectors]
    )


def _provider(**overrides) -> GeminiEmbeddingProvider:
    defaults = {"api_key": "test-key", "model": "gemini-embedding-001"}
    defaults.update(overrides)
    return GeminiEmbeddingProvider(**defaults)


class TestProviderAbstraction:
    def test_gemini_provider_implements_the_interface(self):
        assert isinstance(_provider(), EmbeddingProvider)

    def test_model_name_reflects_configured_model(self):
        provider = _provider(model="gemini-embedding-001")
        assert provider.model_name == "gemini-embedding-001"

    def test_embedding_provider_is_abstract(self):
        with pytest.raises(TypeError):
            EmbeddingProvider()  # type: ignore[abstract]


class TestGeminiProviderConfiguration:
    def test_missing_api_key_raises_at_construction(self):
        with pytest.raises(EmbeddingProviderError, match="GEMINI_API_KEY"):
            GeminiEmbeddingProvider(api_key="", model="gemini-embedding-001")

    def test_construction_does_not_make_a_network_call(self):
        # If this reached the network, it would hang/fail in this sandboxed
        # test environment; succeeding at all proves the client is lazy.
        _provider(api_key="not-a-real-key")

    def test_get_embedding_provider_dispatches_to_gemini(self, monkeypatch):
        monkeypatch.setattr(settings, "embedding_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", "test-key")
        provider = get_embedding_provider()
        assert isinstance(provider, GeminiEmbeddingProvider)

    def test_get_embedding_provider_rejects_unknown_provider(self, monkeypatch):
        monkeypatch.setattr(settings, "embedding_provider", "unknown-provider")
        with pytest.raises(EmbeddingProviderError, match="Unknown EMBEDDING_PROVIDER"):
            get_embedding_provider()

    def test_output_dimensionality_is_passed_through_when_set(self):
        provider = _provider(output_dimensionality=768)
        provider._client.aio.models.embed_content = AsyncMock(
            return_value=_fake_response([[0.1] * 768])
        )

        result = asyncio.run(provider.embed_documents(["hello"]))

        call_kwargs = provider._client.aio.models.embed_content.call_args.kwargs
        assert call_kwargs["config"].output_dimensionality == 768
        assert result[0].dimensions == 768


class TestSuccessfulEmbedding:
    def test_embed_documents_returns_vectors_in_order(self):
        provider = _provider()
        provider._client.aio.models.embed_content = AsyncMock(
            return_value=_fake_response([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
        )

        result = asyncio.run(provider.embed_documents(["a", "b", "c"]))

        assert [v.values for v in result] == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        assert all(v.dimensions == 2 for v in result)

    def test_embed_documents_uses_retrieval_document_task_type(self):
        provider = _provider()
        mock = AsyncMock(return_value=_fake_response([[0.1]]))
        provider._client.aio.models.embed_content = mock

        asyncio.run(provider.embed_documents(["a"]))

        assert mock.call_args.kwargs["config"].task_type == "RETRIEVAL_DOCUMENT"

    def test_embed_query_uses_retrieval_query_task_type(self):
        provider = _provider()
        mock = AsyncMock(return_value=_fake_response([[0.1]]))
        provider._client.aio.models.embed_content = mock

        vector = asyncio.run(provider.embed_query("what is gradient descent?"))

        assert mock.call_args.kwargs["config"].task_type == "RETRIEVAL_QUERY"
        assert vector.values == [0.1]

    def test_embed_documents_with_empty_list_does_not_call_provider(self):
        provider = _provider()
        mock = AsyncMock()
        provider._client.aio.models.embed_content = mock

        result = asyncio.run(provider.embed_documents([]))

        assert result == []
        mock.assert_not_called()

    def test_dimensions_reflect_actual_response_not_a_hardcoded_value(self):
        # Deliberately a size that doesn't match any "expected" constant --
        # proves dimensions are read off the response, not assumed.
        provider = _provider()
        provider._client.aio.models.embed_content = AsyncMock(
            return_value=_fake_response([[0.0] * 17])
        )

        result = asyncio.run(provider.embed_documents(["x"]))

        assert result[0].dimensions == 17


class TestApiFailureHandling:
    def test_client_error_raises_embedding_provider_error(self):
        provider = _provider()
        error = genai_errors.ClientError(
            400, {"error": {"message": "bad request", "status": "INVALID_ARGUMENT"}}
        )
        provider._client.aio.models.embed_content = AsyncMock(side_effect=error)

        with pytest.raises(EmbeddingProviderError):
            asyncio.run(provider.embed_documents(["a"]))

    def test_server_error_raises_transient_error(self):
        provider = _provider()
        error = genai_errors.ServerError(
            503, {"error": {"message": "unavailable", "status": "UNAVAILABLE"}}
        )
        provider._client.aio.models.embed_content = AsyncMock(side_effect=error)

        with pytest.raises(EmbeddingTransientError):
            asyncio.run(provider.embed_documents(["a"]))

    def test_mismatched_embedding_count_raises_provider_error(self):
        provider = _provider()
        provider._client.aio.models.embed_content = AsyncMock(
            return_value=_fake_response([[0.1]])  # only 1, but 2 texts submitted
        )

        with pytest.raises(EmbeddingProviderError, match="different number"):
            asyncio.run(provider.embed_documents(["a", "b"]))

    def test_empty_vector_in_response_raises_provider_error(self):
        provider = _provider()
        response = genai_types.EmbedContentResponse(
            embeddings=[genai_types.ContentEmbedding(values=[])]
        )
        provider._client.aio.models.embed_content = AsyncMock(return_value=response)

        with pytest.raises(EmbeddingProviderError, match="empty embedding"):
            asyncio.run(provider.embed_documents(["a"]))


class TestRateLimitHandling:
    def test_429_raises_rate_limit_error(self):
        provider = _provider()
        error = genai_errors.ClientError(
            429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
        )
        provider._client.aio.models.embed_content = AsyncMock(side_effect=error)

        with pytest.raises(EmbeddingRateLimitError):
            asyncio.run(provider.embed_documents(["a"]))

    def test_rate_limit_error_is_not_a_provider_error_subclass_confusion(self):
        # EmbeddingRateLimitError and EmbeddingProviderError are siblings, not
        # parent/child -- callers that only catch EmbeddingProviderError
        # should NOT accidentally swallow rate limits as non-retryable.
        assert not issubclass(EmbeddingRateLimitError, EmbeddingProviderError)
        assert not issubclass(EmbeddingProviderError, EmbeddingRateLimitError)

    def test_429_with_retry_delay_detail_is_captured_on_the_error(self):
        provider = _provider()
        error = genai_errors.ClientError(
            429,
            {
                "error": {
                    "message": "quota exceeded",
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "19s",
                        }
                    ],
                }
            },
        )
        provider._client.aio.models.embed_content = AsyncMock(side_effect=error)

        with pytest.raises(EmbeddingRateLimitError) as exc_info:
            asyncio.run(provider.embed_documents(["a"]))

        assert exc_info.value.retry_delay_seconds == pytest.approx(19.0)

    def test_429_without_retry_delay_detail_leaves_it_unset(self):
        provider = _provider()
        error = genai_errors.ClientError(
            429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
        )
        provider._client.aio.models.embed_content = AsyncMock(side_effect=error)

        with pytest.raises(EmbeddingRateLimitError) as exc_info:
            asyncio.run(provider.embed_documents(["a"]))

        assert exc_info.value.retry_delay_seconds is None
