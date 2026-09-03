"""
Tests for the generation provider abstraction (app/services/rag/generation.py).
No real Gemini API calls -- every provider call is mocked at the SDK client
boundary (`provider._client.aio.models.generate_content_stream`), mirroring
test_embeddings.py's approach for the embedding provider.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.config import settings
from app.services.rag.generation import (
    GeminiGenerationProvider,
    GenerationProvider,
    GenerationProviderError,
    GenerationRateLimitError,
    GenerationTransientError,
    get_generation_provider,
)


def _fake_response(text: str, finish_reason: genai_types.FinishReason | None = None):
    return genai_types.GenerateContentResponse(
        candidates=[
            genai_types.Candidate(
                content=genai_types.Content(parts=[genai_types.Part(text=text)], role="model"),
                finish_reason=finish_reason,
            )
        ]
    )


async def _fake_stream(responses: list):
    for response in responses:
        yield response


async def _raising_stream(error: Exception):
    """An async generator that raises on first iteration -- simulates
    generate_content_stream's returned iterator failing mid-stream, which
    (per the real SDK) is where transport/API errors actually surface."""
    raise error
    yield  # pragma: no cover -- unreachable, only makes this an async generator function


def _provider(**overrides) -> GeminiGenerationProvider:
    defaults = {"api_key": "test-key", "model": "gemini-2.5-flash"}
    defaults.update(overrides)
    return GeminiGenerationProvider(**defaults)


async def _drain(provider: GeminiGenerationProvider, **kwargs) -> list:
    return [chunk async for chunk in provider.stream_generate(**kwargs)]


class TestProviderAbstraction:
    def test_gemini_provider_implements_the_interface(self):
        assert isinstance(_provider(), GenerationProvider)

    def test_model_name_reflects_configured_model(self):
        provider = _provider(model="gemini-2.5-pro")
        assert provider.model_name == "gemini-2.5-pro"

    def test_generation_provider_is_abstract(self):
        with pytest.raises(TypeError):
            GenerationProvider()  # type: ignore[abstract]


class TestGeminiProviderConfiguration:
    def test_missing_api_key_raises_at_construction(self):
        with pytest.raises(GenerationProviderError, match="GEMINI_API_KEY"):
            GeminiGenerationProvider(api_key="", model="gemini-2.5-flash")

    def test_construction_does_not_make_a_network_call(self):
        _provider(api_key="not-a-real-key")

    def test_get_generation_provider_dispatches_to_gemini(self, monkeypatch):
        monkeypatch.setattr(settings, "generation_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", "test-key")
        provider = get_generation_provider()
        assert isinstance(provider, GeminiGenerationProvider)

    def test_get_generation_provider_rejects_unknown_provider(self, monkeypatch):
        monkeypatch.setattr(settings, "generation_provider", "unknown-provider")
        with pytest.raises(GenerationProviderError, match="Unknown GENERATION_PROVIDER"):
            get_generation_provider()

    def test_config_is_passed_through_to_generate_content_config(self):
        provider = _provider(temperature=0.7, max_output_tokens=512)
        mock = AsyncMock(
            return_value=_fake_stream([_fake_response("hi", genai_types.FinishReason.STOP)])
        )
        provider._client.aio.models.generate_content_stream = mock

        asyncio.run(_drain(provider, system_prompt="Be helpful.", user_prompt="Hello"))

        call_kwargs = mock.call_args.kwargs
        config = call_kwargs["config"]
        assert config.system_instruction == "Be helpful."
        assert config.temperature == 0.7
        assert config.max_output_tokens == 512
        assert call_kwargs["contents"] == "Hello"
        assert call_kwargs["model"] == "gemini-2.5-flash"


class TestSuccessfulStreaming:
    def test_stream_yields_deltas_in_order(self):
        provider = _provider()
        provider._client.aio.models.generate_content_stream = AsyncMock(
            return_value=_fake_stream(
                [
                    _fake_response("Hello "),
                    _fake_response("world", genai_types.FinishReason.STOP),
                ]
            )
        )

        chunks = asyncio.run(_drain(provider, system_prompt="sys", user_prompt="q"))

        assert [c.text for c in chunks] == ["Hello ", "world"]
        assert chunks[0].finish_reason is None
        assert chunks[1].finish_reason == "STOP"

    def test_empty_stream_yields_no_chunks(self):
        provider = _provider()
        provider._client.aio.models.generate_content_stream = AsyncMock(
            return_value=_fake_stream([])
        )

        chunks = asyncio.run(_drain(provider, system_prompt="sys", user_prompt="q"))

        assert chunks == []


class TestApiFailureHandling:
    def test_client_error_raises_generation_provider_error(self):
        provider = _provider()
        error = genai_errors.ClientError(
            400, {"error": {"message": "bad request", "status": "INVALID_ARGUMENT"}}
        )
        provider._client.aio.models.generate_content_stream = AsyncMock(
            return_value=_raising_stream(error)
        )

        with pytest.raises(GenerationProviderError):
            asyncio.run(_drain(provider, system_prompt="sys", user_prompt="q"))

    def test_server_error_raises_transient_error(self):
        provider = _provider()
        error = genai_errors.ServerError(
            503, {"error": {"message": "unavailable", "status": "UNAVAILABLE"}}
        )
        provider._client.aio.models.generate_content_stream = AsyncMock(
            return_value=_raising_stream(error)
        )

        with pytest.raises(GenerationTransientError):
            asyncio.run(_drain(provider, system_prompt="sys", user_prompt="q"))


class TestRateLimitHandling:
    def test_429_raises_rate_limit_error(self):
        provider = _provider()
        error = genai_errors.ClientError(
            429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
        )
        provider._client.aio.models.generate_content_stream = AsyncMock(
            return_value=_raising_stream(error)
        )

        with pytest.raises(GenerationRateLimitError):
            asyncio.run(_drain(provider, system_prompt="sys", user_prompt="q"))

    def test_rate_limit_error_is_not_a_provider_error_subclass_confusion(self):
        assert not issubclass(GenerationRateLimitError, GenerationProviderError)
        assert not issubclass(GenerationProviderError, GenerationRateLimitError)

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
        provider._client.aio.models.generate_content_stream = AsyncMock(
            return_value=_raising_stream(error)
        )

        with pytest.raises(GenerationRateLimitError) as exc_info:
            asyncio.run(_drain(provider, system_prompt="sys", user_prompt="q"))

        assert exc_info.value.retry_delay_seconds == pytest.approx(19.0)

    def test_429_without_retry_delay_detail_leaves_it_unset(self):
        provider = _provider()
        error = genai_errors.ClientError(
            429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
        )
        provider._client.aio.models.generate_content_stream = AsyncMock(
            return_value=_raising_stream(error)
        )

        with pytest.raises(GenerationRateLimitError) as exc_info:
            asyncio.run(_drain(provider, system_prompt="sys", user_prompt="q"))

        assert exc_info.value.retry_delay_seconds is None
